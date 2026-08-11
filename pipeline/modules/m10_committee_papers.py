"""Module 10 — Council committee papers (semi-automated).

One adapter per committee system, plus a null adapter that records the
authority for review rather than pretending to have searched it. The system
is detected from path signatures on the authority's committee URL, not
assumed: 'unknown' is a real answer that this module records.

Search terms come from pipeline/keywords.COMMITTEE_SEARCH_TERMS, and results
are candidates only. A ModernGov search hit means a document's title matched
a phrase — "TUPE" or "public health grant" appear in plenty of papers that
have nothing to do with drug and alcohol services — so nothing is promoted
to committee_papers without a human confirming it.

KNOWN LIMITATION, verified against a live ModernGov instance: the document
search at /mgSearchResults.aspx answers a plain GET with a 302, and
/mgDocumentSearch.aspx with a 400. It is an ASP.NET form that needs a POST
carrying viewstate, which this module does not implement. The adapter still
detects the system and issues the searches, but when a ModernGov site
returns no document links for any term it records
'moderngov_search_requires_post' for that authority rather than reporting a
clean run with nothing found — an adapter that quietly finds nothing is
worse than one that says it cannot search.

Coverage is bounded by pipeline/authority_websites.py, which holds only
verified entries. Authorities without one are queued, so the gap is
countable rather than silently absent.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import structlog

from pipeline import db
from pipeline.authority_websites import SYSTEM_SIGNATURES, website_for
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.keywords import COMMITTEE_SEARCH_TERMS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "council_committee_systems"

_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(
    r"(\d{1,2}(?:st|nd|rd|th)?\s+"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})",
    re.IGNORECASE)
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt")


def _text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def detect_committee_system(probe) -> tuple[str, str | None]:
    """(system, signature_path). `probe` is called with a path and returns
    True if it exists. Returns ('unknown', None) when nothing matches — a
    recorded answer, not a fallback guess.
    """
    for system, paths in SYSTEM_SIGNATURES.items():
        for path in paths:
            if probe(path):
                return system, path
    return "unknown", None


def build_moderngov_search_url(committee_url: str, term: str) -> str:
    """ModernGov exposes a document search at /mgSearchResults.aspx."""
    from urllib.parse import quote_plus

    return urljoin(committee_url.rstrip("/") + "/", f"mgSearchResults.aspx?txtSearch={quote_plus(term)}")


def parse_moderngov_results(page_html: str, page_url: str, term: str) -> list[dict]:
    """Candidate documents from a ModernGov search results page.

    Only links to actual documents are kept; navigation and calendar links
    share the same markup and would otherwise flood the review worklist.
    """
    host = urlparse(page_url).netloc
    seen: set[str] = set()
    out: list[dict] = []

    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, html_lib.unescape(href.strip())).split("#")[0]
        if urlparse(url).netloc != host:
            continue
        lowered = url.lower().split("?")[0]
        is_document = lowered.endswith(DOCUMENT_EXTENSIONS) or "/documents/" in lowered
        if not is_document or url in seen:
            continue
        seen.add(url)

        title = _text(raw_text)
        if not title:
            continue
        date_match = _DATE_RE.search(title)
        out.append({
            "document_url": url,
            "report_title": title[:300],
            "meeting_date": date_match.group(1) if date_match else None,
            "committee_name": None,
            "agenda_item_title": None,
            "matched_term": term,
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


@register_module("m10_committee_papers")
def run(ctx: ModuleContext) -> None:
    module_name = "m10_committee_papers"
    conn = ctx.conn

    authorities = conn.execute(
        "SELECT ons_code, name FROM authorities WHERE active_to IS NULL "
        "AND type IN ('county','unitary','london_borough','metropolitan_district') "
        "ORDER BY name"
    ).fetchall()
    if not authorities:
        log.info("committee.no_authorities", note="run m00_geography first")
        return
    if ctx.limit:
        authorities = authorities[:ctx.limit]

    searched = 0
    unconfigured = 0
    unknown_system = 0
    candidates = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for authority in authorities:
            site = website_for(authority["ons_code"])
            if site is None or not site.committee_url:
                db.record_review_item(
                    conn, module_name, "committee_url_unknown", authority["ons_code"],
                    json.dumps({"authority": authority["name"],
                                 "note": "add a verified committee_url to "
                                          "pipeline/authority_websites.py"}))
                unconfigured += 1
                continue

            committee_url = site.committee_url

            def probe(path: str) -> bool:
                try:
                    result = client.get(urljoin(committee_url.rstrip("/") + "/", path.lstrip("/")))
                except RobotsDisallowed:
                    return False
                return result.ok

            system, signature = detect_committee_system(probe)
            db.upsert(conn, "authority_committee_systems", {
                "ons_code": authority["ons_code"],
                "committee_system": system,
                "committee_url": committee_url,
                "detected_by": signature,
                "detected_at": datetime.now(timezone.utc).isoformat(),
            }, natural_key=["ons_code"])

            if system != "moderngov":
                # Null adapter: CMIS and Democracy search interfaces are not
                # implemented, and an unknown system cannot be searched at
                # all. Recorded rather than skipped silently.
                db.record_review_item(
                    conn, module_name, "committee_system_unsupported", authority["ons_code"],
                    json.dumps({"authority": authority["name"], "system": system,
                                 "committee_url": committee_url,
                                 "note": "no adapter for this system; search manually or add one"}))
                unknown_system += 1
                if not ctx.dry_run:
                    conn.commit()
                continue

            searched += 1
            authority_candidates = 0
            for term in COMMITTEE_SEARCH_TERMS:
                url = build_moderngov_search_url(committee_url, term)
                try:
                    result = client.get(url)
                except RobotsDisallowed:
                    db.record_review_item(conn, module_name, "committee_search_robots_disallowed",
                                           url, json.dumps({"authority": authority["name"]}))
                    continue
                if not result.ok:
                    continue

                provenance = _provenance(result)
                for row in parse_moderngov_results(
                        result.body.decode("utf-8", errors="replace"), result.url, term):
                    db.upsert(conn, "committee_paper_candidates", {
                        "authority_ons_code": authority["ons_code"],
                        **row,
                        "committee_system": system,
                        "verified": 0,
                        "verified_at": None,
                        "rejected": 0,
                        "discovered_at": datetime.now(timezone.utc).isoformat(),
                        **provenance,
                    }, natural_key=["authority_ons_code", "document_url"])
                    candidates += 1
                    authority_candidates += 1

            if authority_candidates == 0:
                # Distinguish "searched and found nothing" from "could not
                # search". ModernGov's document search is a POST form; a GET
                # redirects, so every term legitimately returns no documents.
                db.record_review_item(
                    conn, module_name, "moderngov_search_requires_post", authority["ons_code"],
                    json.dumps({"authority": authority["name"],
                                 "committee_url": committee_url,
                                 "note": "ModernGov document search needs a POST with ASP.NET "
                                          "viewstate; GET returns 302. Search manually, or extend "
                                          "the adapter to post the form."}))

            if not ctx.dry_run:
                conn.commit()

    log.info("committee.run_complete", authorities_searched=searched,
              authorities_unconfigured=unconfigured, unsupported_systems=unknown_system,
              candidates=candidates)
