"""Module 9 — Combating Drugs Partnership documents (semi-automated).

Discovery, not extraction. There is no common schema across 150+
authorities, so this finds candidate documents and a human confirms them via
docs/verification/cdp_candidates.md. Nothing reaches cdp_documents without
that confirmation.

Discovery works by crawling a small set of likely paths on the authority's
own domain and scoring links whose URL or text matches CDP / needs-assessment
/ outcomes-framework vocabulary. It does not use a third-party search engine:
that would put the pipeline's queries through someone else's ranking, which
is neither reproducible nor auditable.

An authority without a verified entry in pipeline/authority_websites.py is
written to review_queue rather than guessed at. Council hostnames are not
predictable — democracy.kent.gov.uk exists, the same pattern applied to five
other authorities resolved to nothing — and an invented base URL would either
hit an unrelated site or quietly find nothing while appearing to have
searched.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import structlog

from pipeline import db
from pipeline.authority_websites import website_for
from pipeline.http import RobotsDisallowed
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "authority_websites_cdp"

# Paths commonly used for public health / partnership publications. Tried in
# order; a 404 is expected and unremarkable.
CANDIDATE_PATHS = [
    "/",
    "/public-health",
    "/health-and-social-care",
    "/drug-and-alcohol",
    "/drugs-and-alcohol",
    "/jsna",
    "/joint-strategic-needs-assessment",
]

DOCUMENT_TYPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("cdp_strategy", re.compile(
        r"combating[\s\-]?drugs?|drug[\s\-]?and[\s\-]?alcohol[\s\-]?strategy|"
        r"substance[\s\-]?misuse[\s\-]?strategy|drug[\s\-]?strategy|delivery[\s\-]?plan",
        re.IGNORECASE)),
    ("needs_assessment", re.compile(
        r"needs[\s\-]?assessment|jsna|joint[\s\-]?strategic[\s\-]?needs", re.IGNORECASE)),
    ("outcomes_framework", re.compile(
        r"outcomes?[\s\-]?framework", re.IGNORECASE)),
]

# A candidate must look substance-related, not merely be a strategy or
# assessment. Deliberately excludes bare "needs assessment", which is a
# document type rather than a subject signal — including it matched things
# like "climate needs assessment". JSNA is kept because the brief names the
# JSNA chapter specifically as a target document.
SUBSTANCE_HINT_RE = re.compile(
    r"drug|alcohol|substance|misuse|combating|jsna", re.IGNORECASE)

_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt")


def _link_text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def classify_document(url: str, text: str) -> tuple[str | None, float]:
    """(document_type_guess, confidence).

    Confidence counts independent signals — the document-type vocabulary, a
    substance-related hint, and a document file extension — so the review
    worklist can be triaged. It is not a probability and never substitutes
    for someone opening the file.
    """
    haystack = f"{url} {text}"
    if not SUBSTANCE_HINT_RE.search(haystack):
        return None, 0.0

    document_type = None
    for candidate_type, pattern in DOCUMENT_TYPE_PATTERNS:
        if pattern.search(haystack):
            document_type = candidate_type
            break
    if document_type is None:
        return None, 0.0

    signals = 1
    if SUBSTANCE_HINT_RE.search(text or ""):
        signals += 1
    if url.lower().split("?")[0].endswith(DOCUMENT_EXTENSIONS):
        signals += 1
    if re.search(r"strategy|assessment|framework|plan", text or "", re.IGNORECASE):
        signals += 1
    return document_type, round(min(signals / 4, 1.0), 2)


def extract_candidates(page_html: str, page_url: str) -> list[dict]:
    """Scored candidate links from one page, restricted to the same host so a
    crawl cannot wander onto unrelated domains.
    """
    host = urlparse(page_url).netloc
    seen: set[str] = set()
    candidates: list[dict] = []

    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, html_lib.unescape(href.strip()))
        if urlparse(url).netloc != host:
            continue
        url = url.split("#")[0]
        if url in seen:
            continue
        seen.add(url)

        text = _link_text(raw_text)
        document_type, confidence = classify_document(url, text)
        if document_type is None or confidence <= 0:
            continue
        candidates.append({
            "candidate_url": url,
            "title": text[:300] or None,
            "document_type_guess": document_type,
            "confidence": confidence,
        })
    return candidates


def render_candidates_markdown(rows: list[dict]) -> str:
    """Review worklist grouped by region, as the brief requires."""
    lines = [
        "# Combating Drugs Partnership document candidates",
        "",
        "Each row is a link that *looked* like a CDP strategy, needs assessment or",
        "outcomes framework. **None of it is in the evidence base yet.** Open each",
        "one, and mark the good ones verified:",
        "",
        "```sql",
        "UPDATE cdp_document_candidates SET verified = 1, verified_at = datetime('now')",
        " WHERE authority_ons_code = 'E10000016' AND candidate_url = '...';",
        "```",
        "",
        "Confidence counts matching signals (vocabulary, substance hint, file type).",
        "It is a triage aid, not a probability, and does not mean a document is what",
        "its link text claims.",
        "",
    ]
    by_region: dict[str, list[dict]] = {}
    for row in rows:
        by_region.setdefault(row.get("region") or "(region not recorded)", []).append(row)

    for region in sorted(by_region):
        lines.append(f"## {region}")
        lines.append("")
        lines.append("| Authority | Type (guess) | Conf. | Title | URL |")
        lines.append("| --- | --- | ---: | --- | --- |")
        for row in sorted(by_region[region], key=lambda r: (r["authority_name"], -r["confidence"])):
            title = (row.get("title") or "").replace("|", "\\|")[:90]
            lines.append(
                f"| {row['authority_name']} | {row['document_type_guess']} | "
                f"{row['confidence']:.2f} | {title} | <{row['candidate_url']}> |")
        lines.append("")

    if not rows:
        lines.append("*No candidates discovered. Check authority_websites.py coverage.*")
        lines.append("")
    return "\n".join(lines)


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def crawl_authority(unit, client) -> tuple[list[dict], list[tuple[str, str, dict]]]:
    """One authority's candidate paths. Runs on a pool thread.

    Fetches and parses only: it returns (candidates, review_items) and the
    main thread writes both. Nothing here touches the module's connection.
    """
    authority, site = unit
    candidates: list[dict] = []
    review_items: list[tuple[str, str, dict]] = []

    if site is None:
        # Not guessed: council hostnames are unpredictable, and an invented
        # base URL would search the wrong site or silently find nothing while
        # appearing to have worked.
        review_items.append((
            "authority_website_unknown", authority["ons_code"],
            {"authority": authority["name"],
             "note": "add a verified entry to pipeline/authority_websites.py "
                      "so this authority can be searched"}))
        return candidates, review_items

    for path in CANDIDATE_PATHS:
        url = urljoin(site.base_url, path)
        try:
            result = client.get(url)
        except RobotsDisallowed:
            review_items.append(("cdp_path_robots_disallowed", url,
                                  {"authority": authority["name"]}))
            continue
        if not result.ok:
            continue

        page_html = result.body.decode("utf-8", errors="replace")
        provenance = _provenance(result)
        for candidate in extract_candidates(page_html, result.url):
            candidates.append({**candidate,
                                "discovery_method": f"path_crawl:{path}",
                                **provenance})

    return candidates, review_items


@register_module(
    "m09_cdp_documents",
    supports_since=False,
    depends_on=("m00_geography", "m15_foi",),
    depends_note="m15 supplies an authoritative website for every authority; without it only the hand-verified handful can be searched",
    since_note="document discovery crawls current pages; candidates carry discovered_at, not a source date",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m09_cdp_documents"
    conn = ctx.conn
    verification_dir = Path(ctx.settings.logs_dir).parent / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)

    authorities = conn.execute(
        "SELECT ons_code, name, region FROM authorities WHERE active_to IS NULL "
        "AND type IN ('county','unitary','london_borough','metropolitan_district') "
        "ORDER BY name"
    ).fetchall()
    if not authorities:
        log.info("cdp.no_authorities", note="run m00_geography first")
        return

    if ctx.limit:
        authorities = authorities[:ctx.limit]

    # website_for reads authority_foi_profiles, so it happens on the module's
    # connection rather than inside a worker.
    units = [(authority, website_for(authority["ons_code"], conn))
             for authority in authorities]

    searched = 0
    unconfigured = 0
    candidates_found = 0
    workers = worker_count(ctx.settings, ctx.limit)

    stream = fetch_in_parallel(units, crawl_authority,
                                source_system=SOURCE_SYSTEM, settings=ctx.settings,
                                max_workers=workers, cache_conn=conn)
    for outcome in ctx.track(stream, "councils", total=len(units)):
        authority, site = outcome.unit
        if not outcome.ok:
            # One council with a broken TLS chain costs one council, not the
            # crawl. Recorded, because a failure that leaves no trace is
            # indistinguishable from a council with nothing to publish.
            db.record_review_item(
                conn, module_name, "cdp_collection_failed", authority["ons_code"],
                json.dumps({"authority": authority["name"],
                             "error": f"{type(outcome.error).__name__}: {outcome.error}"}))
            if not ctx.dry_run:
                conn.commit()
            continue

        candidates, review_items = outcome.value
        for item_type, raw_value, context in review_items:
            db.record_review_item(conn, module_name, item_type, raw_value, json.dumps(context))

        if site is None:
            unconfigured += 1
        else:
            searched += 1

        for candidate in candidates:
            db.upsert(conn, "cdp_document_candidates", {
                "authority_ons_code": authority["ons_code"],
                **candidate,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "verified": 0,
                "verified_at": None,
                "rejected": 0,
            }, natural_key=["authority_ons_code", "candidate_url"])
            candidates_found += 1

        if not ctx.dry_run:
            conn.commit()

    rows = [dict(r) for r in conn.execute(
        "SELECT c.authority_ons_code, a.name AS authority_name, a.region, c.candidate_url, "
        "c.title, c.document_type_guess, c.confidence "
        "FROM cdp_document_candidates c JOIN authorities a ON a.ons_code = c.authority_ons_code "
        "WHERE c.verified = 0 AND c.rejected = 0 ORDER BY a.region, a.name, c.confidence DESC")]
    out_path = verification_dir / "cdp_candidates.md"
    out_path.write_text(render_candidates_markdown(rows), encoding="utf-8")

    log.info("cdp.run_complete", authorities_searched=searched,
              authorities_unconfigured=unconfigured, candidates=candidates_found,
              verification=str(out_path))
