"""Module 15 — FOI evidence (discovery).

Publicly published FOI evidence, never "all FOI responses". Three limits
stack and all three belong on anything built from this:

  1. WhatDoTheyKnow only holds requests routed through that platform. The UK
     FOI system is far larger and most requests never appear there.

  2. This module gets *discovery* from WDTK, not full text during collection. The search feed
     returns a truncated, search-highlighted `snippet` per event and never a
     message body. Full text lives behind the JSON read API, which is
     blocked (see below). So this module can tell you a request exists, who
     it went to, and what state it reached — not what the authority actually
     said. The snippet is stored in its own column and never in
     `foi_requests.response_text`. An explicitly enabled m15-only Bright Data
     Web Unlocker may retrieve one request detail page during human promotion;
     it never auto-promotes or bulk-fetches.

  3. A term match is a candidate, not evidence about substance misuse.
     Nothing is promoted without a human confirming it.

What this collects:

  * mySociety's published authority CSV, served as a data file. Their tags
    carry the GSS code, so all 317 English authorities join to `authorities`
    exactly. This is also the pipeline's first authoritative source of a
    website URL for every authority — Modules 9 and 10 fall back to it.

  * `/feed/search/<query>.json`, one search per configured term, restricted
    to authorities this pipeline knows via the GSS tag on the body.

  * FOI disclosure logs on councils' own websites, where the polite crawler
    is welcome. Around a third of authorities publish one.

What is blocked, measured 2026-08-11 from this machine with the pipeline's
own identifying User-Agent, one request each and no retries:

    200  /robots.txt
    200  /body/all-authorities.csv       (24 MB)
    200  /feed/search/<query>.json       (application/json, ~70 KB/page)
    403  /body/<slug>                    5.8 KB text/html challenge
    403  /body/<slug>.json               ditto
    403  /list/all.json?page=1           ditto
    403  /request/<slug>.json            ditto

The 403s are a Cloudflare bot challenge. Ordinary collection respects that
boundary. If mySociety has authorised access, an operator may set
`WDTK_WEB_UNLOCKER_ENABLED=true` with a Bright Data key; that exception is
limited to one WDTK request URL at a time during human promotion, is recorded
in `review_queue`, and is archived under the promotion source system. It is
not available to the collector or any other module. Without that explicit
setting, the 403 remains a refusal and the candidate stays unpromoted. Ask
mySociety first (docs/mysociety-access-request.md); `pipeline/alaveteli.py`
already parses the read-API shape.

ON THE FEED AND ROBOTS.TXT. mySociety's robots.txt disallows `*/feed/*` and
`*/search/*`, so `/feed/search/` is doubly disallowed, and this pipeline
honours robots.txt everywhere else. It is fetched here under a single
explicit exception in `Settings.robots_exceptions`, which carries the
reasoning; each run that uses it logs `http.robots_override` and raises a
`robots_override_in_use` review item, so the override stays visible in the
audit trail. This is a judgement call and a reversible one — the access
request in docs/mysociety-access-request.md is still the right way to put it
on a permitted footing, and the exception should be removed when they answer
either way.
"""
from __future__ import annotations

import csv
import hashlib
import html as html_lib
import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse

import httpx
import structlog

from pipeline import alaveteli, db
from pipeline.http import FetchResult, PipelineHTTPClient, RobotsDisallowed, _archive_raw
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "foi_disclosure"
WDTK_AUTHORITIES_CSV = "https://www.whatdotheyknow.com/body/all-authorities.csv"
WDTK_BODY_BASE = "https://www.whatdotheyknow.com/body/"
WDTK_FEED_SEARCH = "https://www.whatdotheyknow.com/feed/search/{query}.json"
BRIGHTDATA_REQUEST_API = "https://api.brightdata.com/request"

# Pages per search term. Each page is 25 events, so 4 pages is up to 100 per
# term. A cap rather than "until exhausted" because a broad term like
# "waiting list" matches tens of thousands of events across all of WDTK, and
# almost all of them belong to authorities and topics this pipeline does not
# cover — paginating to the end would be a large amount of traffic for a
# shrinking yield. Raise it with --limit when a specific term needs depth.
FEED_PAGES_PER_TERM = 4

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


def feed_search_url(term: str) -> str:
    """The feed URL for one search term, as a quoted phrase.

    Quoted because Alaveteli treats a bare multi-word query as OR-ish: an
    unquoted `staffing levels` returns everything matching either word, which
    for these terms is most of the site. The phrase goes in the *path*, so it
    is percent-encoded with `quote` and no safe characters — a raw space or
    quote mark there produces a 404, not a bad search.
    """
    return WDTK_FEED_SEARCH.format(query=quote(f'"{term}"', safe=""))


def is_wdtk_request_url(url: str) -> bool:
    """Only the public request-detail route may use the unlocker.

    Keeping this check here makes the m15 exception impossible to apply to a
    council URL, the authority CSV, or the search feed by accident.
    """
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.netloc.lower() == "www.whatdotheyknow.com"
            and parsed.path.startswith("/request/") and len(parsed.path) > len("/request/"))


def fetch_with_web_unlocker(url: str, settings, source_system: str) -> FetchResult:
    """Fetch one WDTK request through Bright Data, then archive exact bytes.

    This is intentionally not part of PipelineHTTPClient. Bright Data is an
    explicit m15-only exception for a human promotion fetch, not a second
    transport available to every collector. The original WDTK URL remains the
    provenance URL; the Bright Data endpoint is only the transport.
    """
    if not is_wdtk_request_url(url):
        raise ValueError(f"m15 Web Unlocker refuses a non-WDTK request URL: {url}")

    target_url = url if url.rstrip("/").endswith(".json") else url.rstrip("/") + ".json"
    response = httpx.post(
        BRIGHTDATA_REQUEST_API,
        headers={"Authorization": f"Bearer {settings.require_brightdata_key()}",
                 "Content-Type": "application/json"},
        # Bright Data's direct API uses `raw` for the target body itself and
        # `json` for the structured envelope containing status, headers, and
        # body. The latter is what this adapter needs for provenance.
        json={"zone": settings.brightdata_unlocker_zone, "url": target_url, "format": "json"},
        timeout=60.0,
    )
    response.raise_for_status()
    try:
        envelope = response.json()
    except ValueError as exc:
        raise RuntimeError("Bright Data returned a non-JSON unlocker envelope") from exc

    status_code = envelope.get("status_code")
    raw_body = envelope.get("body")
    if not isinstance(status_code, int) or not isinstance(raw_body, str):
        raise RuntimeError("Bright Data returned an unusable unlocker response")
    body = raw_body.encode("utf-8")
    target_headers = httpx.Headers(envelope.get("headers") or {})
    content_type = target_headers.get("content-type", "text/html; charset=utf-8")
    sha256 = hashlib.sha256(body).hexdigest()
    archived_path = (_archive_raw(settings.raw_archive_dir, source_system, sha256,
                                  content_type, body) if body else None)
    log.info("http.wdtk_web_unlocker", url=url, source_system=source_system,
             target_status=status_code, payload_sha256=sha256)
    return FetchResult(
        url=target_url, status_code=status_code, body=body, headers=target_headers,
        retrieved_at=datetime.now(timezone.utc), payload_sha256=sha256,
        not_modified=False, archived_path=archived_path,
        final_url=target_url,
    )


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _collect_feed_candidates(client, conn, known: set[str], ctx, module_name: str) -> tuple[int, int]:
    """Search the WDTK feed for each configured term. Returns (candidates, terms_searched).

    Restricted to authorities this pipeline knows, via the GSS code in the
    body's tags. A hit against a police force or an NHS trust is dropped —
    those are real FOI requests but they are not this campaign's
    commissioning areas, and letting them in would inflate coverage with rows
    that join to nothing.
    """
    pages_per_term = ctx.limit or FEED_PAGES_PER_TERM
    candidates = 0
    terms_searched = 0

    for topic, terms in FOI_TOPICS.items():
        for term in terms:
            url = feed_search_url(term)
            terms_searched += 1
            for page in range(1, pages_per_term + 1):
                try:
                    result = client.get(url, params={"page": page})
                except RobotsDisallowed:
                    # Reachable only if the Settings.robots_exceptions entry
                    # has been removed — which is a legitimate end state, so
                    # it is recorded and the module continues on its other
                    # sources rather than failing the run.
                    db.record_review_item(
                        conn, module_name, "foi_feed_robots_disallowed", url,
                        json.dumps({"note": "no robots exception configured for the WDTK feed; "
                                            "disclosure-log collection is unaffected"}))
                    return candidates, terms_searched
                except Exception as exc:
                    db.record_review_item(
                        conn, module_name, "foi_feed_unreachable", url,
                        json.dumps({"term": term, "page": page, "error": type(exc).__name__}))
                    break

                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "foi_feed_unavailable", url,
                        json.dumps({"term": term, "page": page, "status": result.status_code}))
                    break

                try:
                    payload = json.loads(result.body.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    db.record_review_item(
                        conn, module_name, "foi_feed_not_json", url,
                        json.dumps({"term": term, "page": page,
                                    "content_type": result.content_type}))
                    break

                records, failures = alaveteli.parse_feed_page(payload)
                for failure in failures:
                    db.record_parse_failure(conn, module_name, failure.field_name,
                                             failure.raw_fragment, failure.reason, result.url)

                provenance = _provenance(result)
                for rec in records:
                    ons_code = rec["ons_code"]
                    if not ons_code or ons_code not in known:
                        continue
                    db.upsert(conn, "foi_request_candidates", {
                        "ons_code": ons_code,
                        "candidate_url": rec["request_url"],
                        "title": (rec["subject"] or "")[:300] or None,
                        "matched_term": term,
                        "topic": topic,
                        "request_slug": rec["request_slug"],
                        "authority_slug": rec["authority_slug"],
                        "wdtk_status": rec["status"],
                        "disclosed": None if rec["disclosed"] is None else int(rec["disclosed"]),
                        "request_date": rec["request_date"],
                        "last_updated": rec["last_updated"],
                        "event_type": rec["event_type"],
                        "event_date": rec["event_date"],
                        # Deliberately `snippet`, never `response_text`. It is
                        # a truncated search extract; see migration 0021.
                        "snippet": rec["snippet"],
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        "discovery_source": "wdtk_feed_search",
                        # Initial values for a candidate nobody has seen yet,
                        # and preserved so re-finding a request in a later
                        # feed page cannot un-promote it.
                        "verified": 0,
                        "verified_at": None,
                        "rejected": 0,
                        **provenance,
                    }, natural_key=["ons_code", "candidate_url"],
                        preserve=db.DECISION_COLUMNS)
                    candidates += 1

                if not ctx.dry_run:
                    conn.commit()

                # A short page is the last page. Alaveteli serves 25 per page.
                if len(payload) < 25:
                    break

    return candidates, terms_searched


def crawl_disclosure_log(profile, client) -> tuple[list[dict], list[tuple[str, str, dict]]]:
    """One council's disclosure log. Runs on a pool thread.

    Fetches and parses only, returning (candidates, review_items) for the main
    thread to write. A non-empty review_items means the log was not read, so
    the caller must not count it as crawled.
    """
    url = profile["disclosure_log_url"]
    try:
        page = client.get(url)
    except RobotsDisallowed:
        return [], [("foi_log_robots_disallowed", url, {"ons_code": profile["ons_code"]})]
    if not page.ok:
        return [], [("foi_log_unavailable", url,
                     {"ons_code": profile["ons_code"], "status": page.status_code})]

    provenance = _provenance(page)
    candidates = [{**candidate, **provenance} for candidate in extract_foi_candidates(
        page.body.decode("utf-8", errors="replace"), page.url)]
    return candidates, []


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
        targets = [p for p in profiles
                   if p["disclosure_log_url"] and p["ons_code"] in known]
        no_log = len(profiles) - len([p for p in profiles if p["disclosure_log_url"]])
        if ctx.limit:
            targets = targets[:ctx.limit]

        # Each council is a different host, so these were 300 unrelated sites
        # read strictly one after another at one request every two seconds.
        # The per-host interval is enforced process-wide, so fetching them
        # concurrently changes nothing any single council experiences.
        workers = worker_count(ctx.settings, ctx.limit)
        stream = fetch_in_parallel(targets, crawl_disclosure_log,
                                    source_system=SOURCE_SYSTEM, settings=ctx.settings,
                                    max_workers=workers, cache_conn=conn)
        for outcome in ctx.track(stream, "disclosure logs", total=len(targets)):
            profile = outcome.unit
            db.record_review_item(
                conn, module_name, "foi_response_text_not_retrievable", profile["ons_code"],
                json.dumps({"wdtk_body_url": profile["wdtk_body_url"],
                             "note": "the WDTK feed gives discovery only (a truncated snippet); "
                                      "full response text needs /request/<slug>.json, which "
                                      "answers automated clients with a Cloudflare 403"}))

            if not outcome.ok:
                db.record_review_item(
                    conn, module_name, "foi_log_unreachable", profile["disclosure_log_url"],
                    json.dumps({"ons_code": profile["ons_code"],
                                 "error": f"{type(outcome.error).__name__}"}))
                if not ctx.dry_run:
                    conn.commit()
                continue

            candidates, review_items = outcome.value
            for item_type, raw_value, context in review_items:
                db.record_review_item(conn, module_name, item_type, raw_value,
                                       json.dumps(context))
            if not review_items:
                logs_crawled += 1

            for candidate in candidates:
                db.upsert(conn, "foi_request_candidates", {
                    "ons_code": profile["ons_code"],
                    **candidate,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "discovery_source": "disclosure_log",
                    # Initial values for a candidate nobody has seen yet, and
                    # preserved so re-finding the link cannot un-promote it.
                    "verified": 0,
                    "verified_at": None,
                    "rejected": 0,
                }, natural_key=["ons_code", "candidate_url"],
                    preserve=db.DECISION_COLUMNS)
                candidates_found += 1

            if not ctx.dry_run:
                conn.commit()

        # --- WhatDoTheyKnow feed search ---------------------------------------
        feed_candidates, terms_searched = _collect_feed_candidates(
            client, conn, known, ctx, module_name)
        candidates_found += feed_candidates

    log.info("foi.run_complete", profiles=profiles_written, disclosure_logs_crawled=logs_crawled,
              authorities_without_a_disclosure_log=no_log, candidates=candidates_found,
              feed_candidates=feed_candidates, feed_terms_searched=terms_searched)
