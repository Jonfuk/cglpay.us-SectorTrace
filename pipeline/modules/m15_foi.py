"""Module 15 — FOI evidence (discovery).

Publicly published FOI evidence, never "all FOI responses". Two limits stack
and both belong on anything built from this:

  1. WhatDoTheyKnow only holds requests routed through that platform. The UK
     FOI system is far larger and most requests never appear there.
  2. This module cannot read WhatDoTheyKnow's request pages. They sit behind
     a Cloudflare bot challenge that answers any automated client with a 403.
     That is the site's access control, and it is respected rather than
     worked around — no user-agent spoofing, no challenge solving. If a full
     WDTK corpus is wanted, ask mySociety; they offer data access to
     researchers.

What this does collect, both permitted:

  * mySociety's published authority CSV, which they serve as a data file.
    Their tags carry the GSS code, so all 317 English authorities join to
    `authorities` exactly. This is also the pipeline's first authoritative
    source of a website URL for every authority — Modules 9 and 10 fall back
    to it, which lifts their coverage from a hand-verified handful.

  * FOI disclosure logs on councils' own websites, where the polite crawler
    is welcome. Around a third of authorities publish one.

Discovery only. A link whose text matched a search term is a candidate, not
an FOI response about substance misuse, and nothing is promoted without a
human confirming it.
"""
from __future__ import annotations

import csv
import html as html_lib
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "foi_disclosure"
WDTK_AUTHORITIES_CSV = "https://www.whatdotheyknow.com/body/all-authorities.csv"
WDTK_BODY_BASE = "https://www.whatdotheyknow.com/body/"

# Topic -> search terms, from the brief's FOI corpus list. Terms are matched
# against link text and URLs on a council's disclosure log.
FOI_TOPICS: dict[str, list[str]] = {
    "budget_and_spend": ["substance misuse budget", "drug and alcohol budget",
                          "drug and alcohol spend", "treatment expenditure",
                          "public health grant"],
    "commissioning": ["recommissioning", "commissioned services", "contract value",
                       "contract extension", "treatment and recovery contract"],
    # Qualified rather than bare, for the same reason as Module 14: a bare
    # "vacancies" on a council site matches the jobs page, and the first live
    # run's only candidate was "Jobs and careers - Council vacancies".
    "workforce": ["staffing levels", "staffing numbers", "staff vacancies",
                   "vacancy rate", "staff turnover", "agency workers", "agency staff",
                   "sickness absence", "pay scales", "caseload", "caseloads", "TUPE"],
    "service_delivery": ["waiting list", "waiting times", "service closure",
                          "service users", "unmet need", "residential treatment",
                          "detoxification", "naloxone", "needle exchange"],
    "context": ["rough sleeping", "drug related death", "drug-related death"],
}

_GSS_RE = re.compile(r"\b(?:gss|statistical_geography|lad\d{2}cd_code):(E\d{8})")
_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_gss_code(tags: str) -> str | None:
    """The GSS/ONS code from mySociety's tag string, which is how their
    authority register joins to ONS geography.
    """
    m = _GSS_RE.search(tags or "")
    return m.group(1) if m else None


def parse_authorities_csv(csv_text: str, known_ons_codes: set[str]) -> list[dict]:
    """English authorities from mySociety's register, restricted to codes this
    pipeline already knows so unrelated bodies are not imported.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for row in csv.DictReader(io.StringIO(csv_text)):
        ons_code = extract_gss_code(row.get("Tags") or "")
        if not ons_code or ons_code not in known_ons_codes or ons_code in seen:
            continue
        seen.add(ons_code)
        slug = (row.get("URL name") or "").strip()
        out.append({
            "ons_code": ons_code,
            "authority_name": (row.get("Name") or "").strip(),
            "wdtk_body_slug": slug or None,
            "wdtk_body_url": f"{WDTK_BODY_BASE}{slug}" if slug else None,
            "home_page_url": (row.get("Home page") or "").strip() or None,
            "publication_scheme_url": (row.get("Publication scheme") or "").strip() or None,
            "disclosure_log_url": (row.get("Disclosure log") or "").strip() or None,
        })
    return out


def _link_text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def match_foi_topic(text: str) -> tuple[str, str] | None:
    """(topic, matched_term) for the first configured term appearing in text."""
    lowered = (text or "").lower()
    for topic, terms in FOI_TOPICS.items():
        for term in terms:
            if term.lower() in lowered:
                return topic, term
    return None


def extract_foi_candidates(page_html: str, page_url: str) -> list[dict]:
    """Links on a disclosure log whose text or URL matches a search term.

    Same-host only, so a crawl cannot wander off the council's site.
    """
    host = urlparse(page_url).netloc
    seen: set[str] = set()
    out: list[dict] = []

    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, html_lib.unescape(href.strip())).split("#")[0]
        if urlparse(url).netloc != host or url in seen:
            continue
        seen.add(url)

        text = _link_text(raw_text)
        matched = match_foi_topic(f"{text} {url}")
        if not matched:
            continue
        topic, term = matched
        out.append({
            "candidate_url": url,
            "title": text[:300] or None,
            "matched_term": term,
            "topic": topic,
        })
    return out


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@register_module(
    "m15_foi",
    supports_since=False,
    depends_on=("m00_geography",),
    depends_note="restricts the register to authorities this pipeline knows",
    since_note="disclosure logs publish whatever is currently listed; candidates carry discovered_at rather than a source date",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m15_foi"
    conn = ctx.conn

    known = {r["ons_code"] for r in conn.execute(
        "SELECT ons_code FROM authorities WHERE active_to IS NULL")}
    if not known:
        log.info("foi.no_authorities", note="run m00_geography first")
        return

    profiles_written = 0
    logs_crawled = 0
    candidates_found = 0
    no_log = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        # --- authority register (the route mySociety publish) ---------------
        result = client.get(WDTK_AUTHORITIES_CSV)
        if not result.ok:
            db.record_review_item(conn, module_name, "wdtk_authority_csv_unavailable",
                                   WDTK_AUTHORITIES_CSV,
                                   json.dumps({"status": result.status_code}))
            return

        provenance = _provenance(result)
        profiles = parse_authorities_csv(
            result.body.decode("utf-8", errors="replace"), known)
        for profile in profiles:
            db.upsert(conn, "authority_foi_profiles", {**profile, **provenance},
                       natural_key=["ons_code"])
            profiles_written += 1
        if not ctx.dry_run:
            conn.commit()
        log.info("foi.profiles_written", count=profiles_written,
                  with_disclosure_log=sum(1 for p in profiles if p["disclosure_log_url"]))

        # --- disclosure logs on councils' own sites --------------------------
        targets = [p for p in profiles if p["disclosure_log_url"]]
        no_log = len(profiles) - len(targets)
        for profile in targets:
            if profile["ons_code"] not in known:
                continue
            db.record_review_item(
                conn, module_name, "foi_wdtk_requests_not_retrievable", profile["ons_code"],
                json.dumps({"wdtk_body_url": profile["wdtk_body_url"],
                             "note": "WhatDoTheyKnow request pages answer automated clients with "
                                      "a Cloudflare 403; per-request ingestion needs permission "
                                      "from mySociety rather than a workaround"}))
            if ctx.limit and logs_crawled >= ctx.limit:
                break
            try:
                page = client.get(profile["disclosure_log_url"])
            except RobotsDisallowed:
                db.record_review_item(conn, module_name, "foi_log_robots_disallowed",
                                       profile["disclosure_log_url"],
                                       json.dumps({"ons_code": profile["ons_code"]}))
                continue
            except Exception as exc:
                db.record_review_item(conn, module_name, "foi_log_unreachable",
                                       profile["disclosure_log_url"],
                                       json.dumps({"ons_code": profile["ons_code"],
                                                    "error": f"{type(exc).__name__}"}))
                continue
            if not page.ok:
                db.record_review_item(conn, module_name, "foi_log_unavailable",
                                       profile["disclosure_log_url"],
                                       json.dumps({"ons_code": profile["ons_code"],
                                                    "status": page.status_code}))
                continue

            logs_crawled += 1
            log_provenance = _provenance(page)
            for candidate in extract_foi_candidates(
                    page.body.decode("utf-8", errors="replace"), page.url):
                db.upsert(conn, "foi_request_candidates", {
                    "ons_code": profile["ons_code"],
                    **candidate,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "discovery_source": "disclosure_log",
                    "verified": 0,
                    "verified_at": None,
                    "rejected": 0,
                    **log_provenance,
                }, natural_key=["ons_code", "candidate_url"])
                candidates_found += 1

            if not ctx.dry_run:
                conn.commit()

    log.info("foi.run_complete", profiles=profiles_written, disclosure_logs_crawled=logs_crawled,
              authorities_without_a_disclosure_log=no_log, candidates=candidates_found)
