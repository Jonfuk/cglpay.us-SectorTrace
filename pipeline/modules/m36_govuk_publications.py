"""Module 36 — GOV.UK Search API and Content API publication discovery.

JON-15: structured discovery of DHSC/OHID publications, policy papers,
consultations, grants, allocations, workforce and commissioning guidance,
followed to their attachments. Two documented, JSON, unauthenticated APIs
under the OGL:

  * **Search API** (`https://www.gov.uk/api/search.json`) — GOV.UK's own
    relevance-ranked search, restricted to `filter_organisations` and queried
    once per substance-misuse keyword. Using GOV.UK's own search rather than
    crawling links (the way m09 has to for council sites) means the ranking
    is the publisher's, is documented, and is reproducible from the query
    alone.
  * **Content API** (`https://www.gov.uk/api/content{base_path}`) — the full
    content item for each search hit, which is where `details.attachments`
    lives. A search hit is a page; the attachments are what this pipeline
    actually wants archived.

Discovery, not extraction, same as m09 and the same reason: GOV.UK's
`document_type` is real controlled vocabulary, not a regex guess, but
*relevance* is not a judgement this pipeline is willing to make silently — a
DHSC policy paper on general practice funding is not evidence about the
substance misuse sector merely because DHSC published it, and "alcohol"
matches licensing guidance as often as treatment policy. So every attachment
is written to `govuk_document_candidates` and nothing crosses into
`govuk_publication_documents` without a person confirming it via
`pipeline/promote.py` (kind `"govuk_publication"`) — the trigger in migration
0116 refuses the insert otherwise, the same guarantee migration 0030 gives
the other three candidate kinds.

Two honest limits, both said out loud rather than silently applied:

  * Each (organisation, keyword) query is paged to GOV.UK's own `total`,
    capped at MAX_PAGES. A query that hits the cap raises a review item
    naming it, so "everything DHSC has published on drug treatment" is never
    silently "the first 200".
  * Only `attachment_type == "file"` attachments become candidates. GOV.UK
    content items also list `"external"` attachments (links to someone
    else's site) and `"html"` attachments (a page, not a file) — this module
    is not fetching arbitrary third-party targets from GOV.UK's index, and an
    HTML attachment has no bytes to archive on promotion.

A content item found under more than one keyword (or, in principle, more
than one organisation search) has its Content API page fetched once per run;
`matched_terms` accumulates the same way m19's `data_gov_uk_datasets` does,
so a candidate's row says everything this pipeline has found it under.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUBSTANCE_MISUSE_KEYWORDS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "govuk_publications"
SEARCH_API = "https://www.gov.uk/api/search.json"
CONTENT_API_BASE = "https://www.gov.uk/api/content"
PAGE_SIZE = 50
MAX_PAGES = 4  # 200 results per (organisation, keyword) query before the cap review item fires

# The organisations JON-15 names. Adding a third is a scope decision (a new
# organisation slug added here), not a code change -- but it is still a
# decision, and one this module does not make for itself.
ORGANISATIONS: list[str] = [
    "department-of-health-and-social-care",
    "office-for-health-improvement-and-disparities",
]

SEARCH_FIELDS = "content_id,title,link,public_timestamp,format"

# GOV.UK's own content_store document_type vocabulary. Not every content item
# that matches a keyword is a document worth a reviewer's time -- a press
# release quoting a minister is not a policy document -- so the type itself
# is one of the confidence signals, not a filter: everything is still stored,
# with a lower score, so a genuinely relevant press release is not dropped.
SUBSTANTIVE_DOCUMENT_TYPES = {
    "policy_paper", "guidance", "consultation", "statistics_announcement",
    "statistics", "corporate_report", "research", "impact_assessment",
    "correspondence", "transparency", "independent_report", "form",
    "national_statistics",
}

# Content types that are a real file worth archiving, as opposed to GOV.UK
# marking the attachment "external" or "html" (handled before this is
# reached) or a content type this pipeline has no reader for.
DOCUMENT_CONTENT_TYPES = (
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.oasis.opendocument.text",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing(conn, table: str, key: dict) -> dict | None:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {' AND '.join(f'{k} = %s' for k in key)}",
        tuple(key.values())).fetchone()
    return dict(row) if row else None


def _terms_from(terms: str | None, extra: str) -> str | None:
    """Comma-joined matched terms, or None when there are none -- mirrors
    m19's helper of the same name so a candidate found under no keyword
    (there is currently no such path here, but a future organisation-only
    pass could add one) reads as having none, not an empty string."""
    values = [v for v in (terms or "").split(",") if v]
    if extra and extra not in values:
        values.append(extra)
    return ",".join(values) or None


def _org_slug(organisations: list[dict], fallback: str) -> str:
    """The publishing organisation's slug, from the Content API's own
    `links.organisations`, falling back to the search facet that found it.
    The Content API is the more authoritative source when a content item
    lists more than one organisation -- the first is used, and this module
    makes no attempt to fan a document out to every co-publishing body."""
    for org in organisations:
        base_path = org.get("base_path") or ""
        slug = base_path.rstrip("/").rsplit("/", 1)[-1]
        if slug:
            return slug
    return fallback


def confidence(document_type: str | None, organisation: str | None,
               attachment_content_type: str | None) -> float:
    """0-1. Counts independent signals: the search hit itself (always true by
    the time this is called), a health-relevant publishing organisation, a
    substantive GOV.UK document type, and a real file attachment. A triage
    aid for the review worklist, never a probability and never a substitute
    for someone opening the document."""
    signals = 1
    if organisation in ORGANISATIONS:
        signals += 1
    if document_type in SUBSTANTIVE_DOCUMENT_TYPES:
        signals += 1
    if attachment_content_type in DOCUMENT_CONTENT_TYPES:
        signals += 1
    return round(signals / 4, 2)


def render_candidates_markdown(rows: list[dict]) -> str:
    """Review worklist grouped by publishing organisation."""
    lines = [
        "# GOV.UK publication candidates",
        "",
        "Each row is an attachment on a GOV.UK content item that matched a",
        "substance-misuse keyword. **None of it is in the evidence base yet.**",
        "Open each one, and promote the good ones via the admin candidate",
        "review UI (kind `govuk_publication`) or `pipeline/promote.py`.",
        "",
        "Confidence counts matching signals (health-relevant organisation,",
        "substantive GOV.UK document type, real file attachment). It is a",
        "triage aid, not a probability, and does not mean a document is what",
        "its title claims.",
        "",
    ]
    by_org: dict[str, list[dict]] = {}
    for row in rows:
        by_org.setdefault(row["publishing_organisation"], []).append(row)

    for org in sorted(by_org):
        lines.append(f"## {org}")
        lines.append("")
        lines.append("| Type (guess) | Conf. | Title | URL |")
        lines.append("| --- | ---: | --- | --- |")
        for row in sorted(by_org[org], key=lambda r: -r["confidence"]):
            title = (row.get("title") or "").replace("|", "\\|")[:90]
            lines.append(
                f"| {row.get('document_type_guess') or '(unknown)'} | "
                f"{row['confidence']:.2f} | {title} | <{row['candidate_url']}> |")
        lines.append("")

    if not rows:
        lines.append("*No candidates discovered.*")
        lines.append("")
    return "\n".join(lines)


def _store_attachment(conn, org_slug: str, content_id: str, base_path: str,
                       detail: dict, attachment: dict, term: str,
                       provenance: dict) -> int:
    if attachment.get("attachment_type") != "file":
        return 0
    url = attachment.get("url")
    if not url:
        return 0
    url = urljoin("https://www.gov.uk", url)
    document_type = detail.get("document_type")

    existing = _existing(conn, "govuk_document_candidates",
                          {"publishing_organisation": org_slug, "candidate_url": url})
    row = {
        "publishing_organisation": org_slug,
        "candidate_url": url,
        "content_id": content_id,
        "base_path": base_path,
        "title": attachment.get("title") or detail.get("title"),
        "document_type_guess": document_type,
        "attachment_content_type": attachment.get("content_type"),
        "confidence": confidence(document_type, org_slug, attachment.get("content_type")),
        "matched_terms": _terms_from(existing.get("matched_terms") if existing else None, term),
        "public_updated_at": detail.get("public_updated_at"),
        "first_published_at": detail.get("first_published_at"),
        "discovered_at": _now(),
        "discovery_method": f"search:{term}",
        # Initial values for a candidate nobody has seen yet; preserved by
        # db.upsert's `preserve=db.DECISION_COLUMNS` so a re-run cannot
        # silently un-promote or un-reject one already decided.
        "verified": 0,
        "verified_at": None,
        "rejected": 0,
        **provenance,
    }
    db.upsert(conn, "govuk_document_candidates", row,
              natural_key=["publishing_organisation", "candidate_url"],
              preserve=db.DECISION_COLUMNS)
    return 1


def _process_hit(client, conn, module_name: str, org_facet: str, term: str,
                  hit: dict, fetched_content: dict) -> int:
    content_id = hit.get("content_id")
    base_path = hit.get("link")
    if not content_id or not base_path:
        return 0

    cached = fetched_content.get(content_id)
    if cached is None:
        content_url = f"{CONTENT_API_BASE}{base_path}"
        result = client.get(content_url)
        if not result.ok:
            db.record_review_item(
                conn, module_name, "govuk_content_unavailable", content_url,
                json.dumps({"status": result.status_code}))
            fetched_content[content_id] = None
            return 0
        detail = json.loads(result.body)
        cached = {
            "detail": detail,
            "provenance": {
                "source_url": result.url,
                "retrieved_at": result.retrieved_at.isoformat(),
                "http_status": result.status_code,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": result.payload_sha256,
            },
        }
        fetched_content[content_id] = cached
    if cached is None:
        return 0

    detail = cached["detail"]
    organisations = ((detail.get("links") or {}).get("organisations")) or []
    org_slug = _org_slug(organisations, org_facet)
    attachments = ((detail.get("details") or {}).get("attachments")) or []

    written = 0
    for attachment in attachments:
        written += _store_attachment(conn, org_slug, content_id, base_path,
                                      detail, attachment, term, cached["provenance"])
    return written


def _search(client, conn, module_name: str, org: str, term: str,
            fetched_content: dict) -> int:
    """One paged (organisation, keyword) query. Returns candidate rows
    written. A failed page stops the query and is recorded, never retried
    silently."""
    params = {"q": term, "filter_organisations": org, "count": PAGE_SIZE,
              "start": 0, "fields": SEARCH_FIELDS}
    written = 0
    for _page in range(MAX_PAGES):
        result = client.get(SEARCH_API, params=params)
        if not result.ok:
            db.record_review_item(
                conn, module_name, "govuk_search_failed", f"{org}:{term}",
                json.dumps({"status": result.status_code, "params": params}))
            return written
        payload = json.loads(result.body)
        hits = payload.get("results") or []
        for hit in hits:
            written += _process_hit(client, conn, module_name, org, term, hit, fetched_content)
        total = payload.get("total", 0)
        params["start"] += len(hits)
        if params["start"] >= total or not hits:
            break
    else:
        db.record_review_item(
            conn, module_name, "govuk_search_capped", f"{org}:{term}",
            json.dumps({"note": f"results exceed {MAX_PAGES} pages of {PAGE_SIZE}; "
                                 f"stored only the first {MAX_PAGES * PAGE_SIZE}"}))
    return written


@register_module(
    "m36_govuk_publications",
    supports_since=False,
    depends_on=(),
    since_note="the search/content APIs are a discovery index of current publications, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m36_govuk_publications"
    conn = ctx.conn
    verification_dir = Path(ctx.settings.logs_dir).parent / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)

    # Fetched once per run per content item, even when the same publication
    # matches more than one keyword -- see the module docstring.
    fetched_content: dict[str, dict | None] = {}
    candidates_found = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for org in ORGANISATIONS:
            ctx.phase(f"searching GOV.UK for {org}")
            for term in ctx.track(SUBSTANCE_MISUSE_KEYWORDS, f"keywords:{org}"):
                candidates_found += _search(client, conn, module_name, org, term, fetched_content)
                if not ctx.dry_run:
                    conn.commit()

    rows = [dict(r) for r in conn.execute(
        "SELECT publishing_organisation, candidate_url, title, "
        "document_type_guess, confidence "
        "FROM govuk_document_candidates WHERE verified = 0 AND rejected = 0 "
        "ORDER BY publishing_organisation, confidence DESC")]
    out_path = verification_dir / "govuk_publication_candidates.md"
    out_path.write_text(render_candidates_markdown(rows), encoding="utf-8")

    log.info("govuk_publications.run_complete", candidates=candidates_found,
              content_items=len([v for v in fetched_content.values() if v]),
              verification=str(out_path))
