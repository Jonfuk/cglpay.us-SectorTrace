"""Module 34 — Integrated Care Board governance documents.

An ICB is a statutory NHS body that plans and funds most NHS services in its
area; there are 42. This module captures the documents each publishes under
its meetings/governance area — the Board *and* every standing committee, with
agendas, reports, minutes and enclosures.

WHY THIS IS COLLECTED, AND THE LIMIT THAT SHAPES IT. Drug and alcohol
treatment in England is commissioned by local authorities out of the public
health grant, not by the NHS. An ICB is therefore NOT a commissioner of the
services this campaign is about. What its board packs carry, in passing, is
dual-diagnosis / mental-health commissioning that overlaps the treatment
population, Combating Drugs Partnership updates, and named provider contracts,
TUPE and pay pressure where a provider also holds an NHS contract. A mention
in a 300-page pack is *context* for a person to weigh, never a figure. This
module extracts no spend, no headcount, and nothing that needs knowing which
LA an ICB "covers". See docs/CAVEATS.md, "ICB board papers (Module 34)".

DISCOVERY, NOT EXTRACTION. Same discipline as Modules 9, 10 and 32: a
candidate is a document that was published under an ICB's governance area,
captured in full so a person can read it. Nothing reaches ``icb_board_papers``
without a person promoting it.

CAPTURE ALL DOCUMENTS. Every governance document is archived, text-extracted
and indexed regardless of subject. The subject index (substance-misuse and
workforce term frequency, plus tracked-provider mentions) only ranks the
review worklist: ``subject_hits = 0`` means "not surfaced for review now",
never "discarded". A later question runs against the full captured text.

SPINE. The 42 ICBs are seeded from the NHS England "integrated care in your
area" directory into ``integrated_care_boards`` with provenance. Each ICB's
board_url is a hand-verified entry in ``pipeline/icb_boards.py`` where one
exists, otherwise the directory link's origin with ``MEETING_PATHS`` probed
against it (m32's approach). An ICB with neither is an ``icb_board_url_unknown``
review item, so the coverage gap stays countable.

``--since`` is honoured: an ICB pack carries a reliable meeting date in its
link text, and re-fetching a multi-year back-catalogue every run is real
crawl time and real ``data/raw/`` growth. The full listing is still walked to
notice additions; only the fetch of an already-old document is skipped.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.icb_boards import (
    GOVERNANCE_VOCAB,
    MEETING_PATHS,
    board_url_for,
    normalise_name,
    ods_code_for,
)
from pipeline.keywords import PFD_CONCERN_INDEX_TERMS, SUBSTANCE_MISUSE_KEYWORDS
from pipeline.modules import m28_sar_reports as m28
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "icb_websites_governance"

DIRECTORY_URL = (
    "https://www.england.nhs.uk/integratedcare/integrated-care-in-your-area/")
SOURCE_DIRECTORY = "nhs_england_icb_directory"

# Bounds, as safety ceilings rather than targets. An ICB with ~6 committees x
# ~8 meetings/year x ~10 documents over a multi-year back-catalogue reaches a
# few hundred on the first run; --since holds routine runs to a meeting or two.
MAX_SUBPAGES_PER_ICB = 25
MAX_PAGES_PER_ICB = len(MEETING_PATHS) + MAX_SUBPAGES_PER_ICB
MAX_DOCS_PER_ICB = 400

_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

# document_kind, from the link text / URL. First match wins; 'unknown' is a
# real answer, not a default to be ashamed of.
_KIND_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("agenda", re.compile(r"\bagenda\b", re.IGNORECASE)),
    ("minutes", re.compile(r"\bminutes\b|\bdraft minutes\b", re.IGNORECASE)),
    ("committee_pack", re.compile(
        r"committee.*(pack|papers)|(pack|papers).*committee", re.IGNORECASE)),
    ("board_pack", re.compile(
        r"board.*(pack|papers)|(pack|papers).*board|meeting papers", re.IGNORECASE)),
    ("enclosure", re.compile(
        r"\benclosure\b|\bappendix\b|\bannex\b|\bitem \d", re.IGNORECASE)),
    ("report", re.compile(r"\breport\b|\bupdate\b|\bpaper\b", re.IGNORECASE)),
]

# "Finance and Performance Committee", "Quality Committee", "Audit Committee",
# "People Committee", "Remuneration Committee", "Committees in Common". The
# capitalised-word run is greedy within a 5-word window so a multi-word
# committee name is kept whole ("Finance and Performance Committee"), not
# trimmed to its last word.
_COMMITTEE_RE = re.compile(
    r"((?:[A-Z][A-Za-z&'-]+(?:\s+(?:and|&|of|in)\s+)?\s*){1,5}"
    r"(?:Committee(?:s)?(?:\s+in\s+Common)?|Sub-Committee))\b")

_MONTHS = {name.lower(): i for i, name in enumerate(
    ("January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"), start=1)}
_MONTHS.update({name.lower(): i for i, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
     "Nov", "Dec"), start=1)})

# A date sitting in a filename or link label. Ordered most-specific first.
_DATE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                       # 2025-09-25
    re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"),            # 25/09/2025
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{4})\b"),  # 25 September 2025
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b"),  # September 25, 2025
    re.compile(r"\b([A-Za-z]{3,9})\s+(\d{4})\b"),                    # September 2025 (day unknown)
]

# A string that looks like it carries a date but did not parse — worth a
# parse_failures row rather than a silent NULL.
_LOOKS_DATED_RE = re.compile(
    r"\b\d{1,2}[./ ]\d{1,2}[./ ]\d{2,4}\b|\b\d{4}\b.*\b(19|20)\d{2}\b|"
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", re.IGNORECASE)


def _link_text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def _host_key(netloc: str) -> str:
    """Host for same-site comparison, insensitive to a leading www. — ICB
    sites link between the www and bare forms freely (the m32 lesson)."""
    return (netloc or "").lower().split("@")[-1].removeprefix("www.")


def parse_directory(page_html: str) -> list[dict]:
    """(name, url) for every ICB on the NHS England directory page.

    Kept permissive but filtered: an anchor is an ICB only when its text names
    an Integrated Care Board (or ICB) and its href leaves nhs.uk's own site or
    points at an *.icb.nhs.uk host. Deduplicated by normalised name so the
    same ICB linked twice is one row.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for href, raw_text in _LINK_RE.findall(page_html or ""):
        text = _link_text(raw_text)
        low = text.lower()
        if "integrated care board" not in low and not re.search(r"\bicb\b", low):
            continue
        url = html_lib.unescape(href.strip())
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        host = parsed.netloc.lower()
        if "icb.nhs.uk" not in host and host.endswith("england.nhs.uk"):
            continue
        if host.endswith("nhs.uk") and host.split(".")[0] in ("www", "digital"):
            continue
        key = normalise_name(text)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"name": text, "url": url})
    return out


def _classify_kind(url: str, text: str) -> str:
    haystack = f"{url} {text}"
    for kind, pattern in _KIND_PATTERNS:
        if pattern.search(haystack):
            return kind
    return "unknown"


def _committee_name(url: str, text: str) -> str | None:
    """The committee a document belongs to, where the URL path or link text
    names one. NULL for the Board itself, and for anything that does not say.
    """
    for source in (text, url.replace("-", " ").replace("_", " ").replace("/", " ")):
        match = _COMMITTEE_RE.search(source or "")
        if match:
            name = re.sub(r"\s+", " ", match.group(1)).strip(" -")
            return name[:120] or None
    return None


def parse_meeting_date(text: str) -> str | None:
    """An ISO date from a filename or link label, or None. Reformatting a
    written date is not inference; a string that does not parse returns None
    so the caller can record it rather than store a guess.
    """
    if not text:
        return None
    cleaned = re.sub(r"[_]+", " ", html_lib.unescape(text))
    for pattern in _DATE_PATTERNS:
        match = pattern.search(cleaned)
        if not match:
            continue
        groups = match.groups()
        try:
            if pattern.pattern.startswith(r"\b(\d{4})-"):
                y, m, d = int(groups[0]), int(groups[1]), int(groups[2])
            elif pattern.pattern.startswith(r"\b(\d{1,2})[./]"):
                d, m, y = int(groups[0]), int(groups[1]), int(groups[2])
            elif groups[0].isdigit() and len(groups) == 3:
                d, m, y = int(groups[0]), _MONTHS.get(groups[1].lower(), 0), int(groups[2])
            elif len(groups) == 3 and groups[1].isdigit():
                m, d, y = _MONTHS.get(groups[0].lower(), 0), int(groups[1]), int(groups[2])
            else:  # "September 2025" — day is unknown, take the first
                m, y, d = _MONTHS.get(groups[0].lower(), 0), int(groups[-1]), 1
            if not m:
                continue
            return date(y, m, d).isoformat()
        except (ValueError, IndexError):
            continue
    return None


def _subject_terms(text: str) -> dict[str, int]:
    """Count of each watched substance-misuse / workforce term in the text.

    A finding aid only — the same role sar_concern_terms plays. Combines the
    substance-misuse vocabulary with the workforce-pressure terms Module 8
    indexes, because a provider's staffing problem in an ICB pack is exactly
    what a reviewer is looking for.
    """
    lowered = (text or "").lower()
    counts: dict[str, int] = {}
    for term in list(SUBSTANCE_MISUSE_KEYWORDS) + list(PFD_CONCERN_INDEX_TERMS):
        n = len(re.findall(rf"\b{re.escape(term.lower())}\b", lowered))
        if n:
            counts[term] = counts.get(term, 0) + n
    return counts


_SNIPPET_RADIUS = 300


def _snippet_for(text: str, term: str) -> str | None:
    match = re.search(rf"\b{re.escape(term.lower())}\b", (text or "").lower())
    if not match:
        return None
    start = max(0, match.start() - _SNIPPET_RADIUS)
    end = min(len(text), match.end() + _SNIPPET_RADIUS)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def _before_since(since: str | None, meeting_date: str | None) -> bool:
    """True when a parsed meeting date predates --since. Missing/unparseable
    dates are never skipped — dropping a document because its date could not
    be read would be a silent loss."""
    if not since or not meeting_date:
        return False
    try:
        return date.fromisoformat(meeting_date) < date.fromisoformat(since[:10])
    except ValueError:
        return False


@dataclass
class IcbCrawl:
    """What one ICB's fetching produced. Built on a pool thread; nothing is
    written until the main thread has it (m32's BoardCrawl pattern)."""

    icb_name: str
    seed_url: str
    from_registry: bool
    board_url: str = ""
    board_url_source: str | None = None
    pages_fetched: int = 0
    index_status: int = 0
    index_sha: str = ""
    ceiling_reached: bool = False
    # (FetchResult, link_text, from_index, discovery_method)
    candidates: list = field(default_factory=list)
    review_items: list = field(default_factory=list)   # (item_type, raw_value, context)
    robots_blocked: bool = False
    unreachable: bool = False


def crawl_icb(unit: tuple[str, str, bool, str | None], client) -> IcbCrawl:
    """One ICB's entire fetch workload. Runs on a pool thread — fetch only,
    no database."""
    icb_name, seed_url, from_registry, since = unit
    crawl = IcbCrawl(icb_name=icb_name, seed_url=seed_url, from_registry=from_registry)

    parsed_seed = urlparse(seed_url)
    origin = f"{parsed_seed.scheme}://{parsed_seed.netloc}"
    host = parsed_seed.netloc
    seed_path = parsed_seed.path or "/"

    candidate_links: list[tuple[str, str, bool, str]] = []   # url, text, from_index, method
    subpages: list[str] = []
    fetched_pages: set[str] = set()
    reached_anything = False
    resolved_index: str | None = None

    def scan(result, is_index: bool, method: str) -> None:
        nonlocal reached_anything, resolved_index, host
        reached_anything = True
        crawl.pages_fetched += 1
        page_url = result.final_url or result.url
        fetched_pages.add(page_url.split("#")[0])
        if is_index and resolved_index is None:
            resolved_index = page_url
        page_html = result.body.decode("utf-8", "replace")
        for href, raw_text in _LINK_RE.findall(page_html):
            url = urljoin(page_url, href.strip()).split("#")[0]
            if _host_key(urlparse(url).netloc) != _host_key(host):
                continue
            path = url.lower().split("?")[0]
            text = _link_text(raw_text)
            if path.endswith(m28._DOCUMENT_EXTENSIONS):
                candidate_links.append((url, text, is_index, method))
            elif GOVERNANCE_VOCAB.search(f"{url} {text}") and url not in fetched_pages:
                if url not in subpages:
                    subpages.append(url)

    paths = [seed_path, *MEETING_PATHS] if from_registry else list(MEETING_PATHS)
    for path in dict.fromkeys(paths):   # de-dup, keep order
        if crawl.pages_fetched >= MAX_PAGES_PER_ICB:
            break
        url = urljoin(origin + "/", path.lstrip("/"))
        try:
            result = client.get(url)
        except RobotsDisallowed:
            crawl.review_items.append(
                ("icb_paper_robots_disallowed", url, {"icb": icb_name}))
            crawl.robots_blocked = True
            continue
        if not result.ok:
            continue
        if path in ("/", ""):
            crawl.index_status = result.status_code
            crawl.index_sha = result.payload_sha256
            landed = urlparse(result.final_url or result.url).netloc
            if landed:
                host = landed
        is_index = (path == seed_path and from_registry) or bool(GOVERNANCE_VOCAB.search(path))
        scan(result, is_index=is_index, method=f"path_crawl:{path}")

    for sub in subpages[:MAX_SUBPAGES_PER_ICB]:
        if crawl.pages_fetched >= MAX_PAGES_PER_ICB:
            break
        if sub.split("#")[0] in fetched_pages:
            continue
        try:
            result = client.get(sub)
        except RobotsDisallowed:
            crawl.review_items.append(
                ("icb_paper_robots_disallowed", sub, {"icb": icb_name}))
            continue
        if result.ok:
            scan(result, is_index=True, method="subpage_hop")

    if not reached_anything and not crawl.robots_blocked:
        crawl.unreachable = True
        return crawl

    crawl.board_url = resolved_index or seed_url
    crawl.board_url_source = (
        "registry" if from_registry and resolved_index in (None, seed_url)
        else "path_probe" if resolved_index else "directory_link")

    # Collapse duplicate document URLs: keep the first link text, treat a
    # document as index-found if it was linked from any index page.
    merged: dict[str, tuple[str, bool, str]] = {}
    for url, text, from_index, method in candidate_links:
        prev_text, prev_idx, prev_method = merged.get(url, ("", False, method))
        merged[url] = (prev_text or text, prev_idx or from_index, prev_method)

    for doc_url, (link_text, from_index, method) in merged.items():
        if len(crawl.candidates) >= MAX_DOCS_PER_ICB:
            crawl.ceiling_reached = True
            crawl.review_items.append(
                ("icb_doc_ceiling_reached", icb_name,
                 {"icb": icb_name, "ceiling": MAX_DOCS_PER_ICB,
                  "note": "crawl truncated; raise MAX_DOCS_PER_ICB or tighten MEETING_PATHS"}))
            break
        if _before_since(since, parse_meeting_date(link_text) or parse_meeting_date(doc_url)):
            continue
        try:
            fetched = client.get(doc_url)
        except RobotsDisallowed:
            crawl.review_items.append(
                ("icb_paper_robots_disallowed", doc_url, {"icb": icb_name}))
            continue
        if not fetched.ok:
            crawl.review_items.append(
                ("icb_doc_unavailable", doc_url,
                 {"icb": icb_name, "status": fetched.status_code}))
            continue
        crawl.candidates.append((fetched, link_text, from_index, method))
    return crawl


def _already_processed(conn, icb_name: str, document_url: str) -> bool:
    """Whether an earlier run already got everything out of this document.

    Not simply "a row exists": a row with has_body_text = 0 recorded a
    document this module could not read at the time (a .doc, or a PDF whose
    reader has since improved). Mirrors m28._already_processed.
    """
    row = conn.execute(
        "SELECT has_body_text FROM icb_board_paper_candidates "
        "WHERE icb_name = ? AND document_url = ?", (icb_name, document_url)).fetchone()
    if row is None:
        return False
    if row["has_body_text"]:
        return True
    ext = m28.document_extension(document_url)
    return ext not in (".pdf", ".docx")


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _stored_directory(conn) -> list[dict]:
    """The ICB list rebuilt from whatever integrated_care_boards already
    holds, so a flaky directory page does not undo a working set."""
    return [dict(r) for r in conn.execute(
        "SELECT name, region, directory_url FROM integrated_care_boards").fetchall()]


def _collect_directory(ctx: ModuleContext, module_name: str) -> list[dict]:
    """Fetch and store the NHS England ICB directory; return its rows. A
    failure here is not fatal — the crawl falls back to the rows already
    stored, or (first run) records the failure and stops."""
    conn = ctx.conn
    with PipelineHTTPClient(SOURCE_DIRECTORY, settings=ctx.settings, conn=conn) as client:
        try:
            page = client.get(DIRECTORY_URL)
        except RobotsDisallowed:
            db.record_review_item(conn, module_name, "icb_directory_robots_disallowed",
                                   DIRECTORY_URL, json.dumps({}))
            return _stored_directory(conn)
        except httpx.HTTPError as exc:
            db.record_review_item(conn, module_name, "icb_directory_unavailable",
                                   DIRECTORY_URL,
                                   json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            return _stored_directory(conn)
        if not page.ok:
            db.record_review_item(conn, module_name, "icb_directory_unavailable",
                                   DIRECTORY_URL, json.dumps({"status": page.status_code}))
            return _stored_directory(conn)

        boards = parse_directory(page.body.decode("utf-8", "replace"))
        if not boards:
            db.record_parse_failure(
                conn, module_name, "directory", DIRECTORY_URL,
                "no ICB entries recognised on the NHS England directory page; "
                "its markup may have changed", source_url=DIRECTORY_URL)
            return _stored_directory(conn)

        provenance = {
            "source_url": page.url,
            "retrieved_at": page.retrieved_at.isoformat(),
            "http_status": page.status_code,
            "source_system": SOURCE_DIRECTORY,
            "payload_sha256": page.payload_sha256,
        }
        rows: list[dict] = []
        for board in boards:
            registry_url = board_url_for(board["name"])
            row = {
                "name": board["name"],
                "ods_code": ods_code_for(board["name"]),
                "region": None,
                "directory_url": board["url"],
                "board_url": registry_url,
                "board_url_source": "registry" if registry_url else None,
                **provenance,
            }
            db.upsert(conn, "integrated_care_boards", row, natural_key=["name"])
            rows.append(row)
        if not ctx.dry_run:
            conn.commit()
        log.info("icb.directory", boards=len(rows))
        return rows


def _render_worklist(rows: list[dict]) -> str:
    lines = [
        "# ICB governance documents — review worklist",
        "",
        "Every governance document these 42 ICBs publish is captured. This list",
        "is only the ones whose text mentions the substance-misuse sector or",
        "names a tracked provider — ranked by hit count, newest meeting first.",
        "**None of it is in the evidence base.** Open each one, confirm the",
        "mention is real and relevant, and promote the good ones.",
        "",
        "```sql",
        "UPDATE icb_board_paper_candidates SET verified = 1, verified_at = datetime('now')",
        " WHERE icb_name = '...' AND document_url = '...';",
        "```",
        "",
    ]
    by_region: dict[str, list[dict]] = {}
    for row in rows:
        by_region.setdefault(row.get("region") or "(region not recorded)", []).append(row)
    for region in sorted(by_region):
        lines += [f"## {region}", "",
                  "| ICB | Committee | Meeting | Kind | Subject hits | Providers | URL |",
                  "| --- | --- | --- | --- | ---: | ---: | --- |"]
        for row in sorted(by_region[region],
                           key=lambda r: (r["icb_name"], -(r["subject_hits"] or 0),
                                          r["meeting_date"] or "")):
            lines.append(
                f"| {row['icb_name']} | {row.get('committee_name') or ''} "
                f"| {row.get('meeting_date') or ''} | {row.get('document_kind') or ''} "
                f"| {row['subject_hits']} | {row['provider_mentions']} "
                f"| <{row['document_url']}> |")
        lines.append("")
    if not rows:
        lines.append("*No sector-relevant documents surfaced this run.*")
        lines.append("")
    return "\n".join(lines)


@register_module(
    "m34_icb_board_papers", supports_since=True,
    since_note="governance documents carry a meeting date in the link text; an "
                "already-old document is not re-fetched, though the full listing "
                "is still walked to notice additions",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m34_icb_board_papers"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    ctx.phase("reading the NHS England ICB directory")
    directory = _collect_directory(ctx, module_name)
    if not directory:
        log.info("icb.no_directory",
                  note="NHS England directory could not be read and nothing is stored yet")
        return
    if ctx.limit:
        directory = directory[:ctx.limit]

    units: list[tuple[str, str, bool, str | None]] = []
    for board in directory:
        registry_url = board.get("board_url") or board_url_for(board["name"])
        seed_url = registry_url or board.get("directory_url")
        if not seed_url or not str(seed_url).startswith("http"):
            db.record_review_item(
                conn, module_name, "icb_board_url_unknown", board["name"],
                json.dumps({"note": "no verified entry in pipeline/icb_boards.py and no "
                             "usable directory link; add a verified board_url"}))
            continue
        units.append((board["name"], seed_url, bool(registry_url), ctx.since))
    if not ctx.dry_run:
        conn.commit()

    documents = subject_documents = provider_mentions = 0
    workers = worker_count(ctx.settings, ctx.limit)
    stream = fetch_in_parallel(units, crawl_icb, source_system=SOURCE_SYSTEM,
                                settings=ctx.settings, max_workers=workers, cache_conn=conn)

    for outcome in ctx.track(stream, "ICBs", total=len(units)):
        icb_name, seed_url, _from_registry, _since = outcome.unit
        now = datetime.now(timezone.utc).isoformat()
        crawl_row = {
            "icb_name": icb_name, "board_url": seed_url,
            "pages_fetched": 0, "docs_found": 0, "docs_with_subject": 0,
            "ceiling_reached": 0, "status": "unreachable", "last_crawled": now,
            "source_url": seed_url, "retrieved_at": now, "http_status": 0,
            "source_system": SOURCE_SYSTEM, "payload_sha256": "",
        }

        if not outcome.ok:
            db.record_review_item(
                conn, module_name, "icb_collection_failed", icb_name,
                json.dumps({"seed_url": seed_url,
                             "error": f"{type(outcome.error).__name__}: {outcome.error}"}))
            db.upsert(conn, "icb_site_crawls", crawl_row, natural_key=["icb_name"])
            if not ctx.dry_run:
                conn.commit()
            continue

        crawl: IcbCrawl = outcome.value
        for item_type, raw_value, context in crawl.review_items:
            db.record_review_item(conn, module_name, item_type, raw_value, json.dumps(context))

        if crawl.board_url:
            conn.execute(
                "UPDATE integrated_care_boards SET board_url = ?, board_url_source = ? "
                "WHERE name = ? AND (board_url IS NULL OR board_url_source != 'registry')",
                (crawl.board_url, crawl.board_url_source, icb_name))

        icb_docs = icb_subject = 0
        for fetched, link_text, from_index, method in crawl.candidates:
            document_url = fetched.final_url or fetched.url
            ext = m28.document_extension(document_url)
            if ext is None or _already_processed(conn, icb_name, document_url):
                continue

            body_text = body_source = None
            if ext == ".pdf":
                ctx.phase(f"reading {link_text[:60] or document_url.rsplit('/', 1)[-1]}")
                body_text, body_source = m28._read_pdf(ctx, module_name, document_url, fetched)
            elif ext == ".docx":
                ctx.phase(f"reading {link_text[:60] or document_url.rsplit('/', 1)[-1]}")
                body_text, body_source = m28._read_docx(conn, module_name, document_url, fetched)
            else:
                db.record_parse_failure(
                    conn, module_name, "body_text", document_url,
                    f"document is {ext}, not a PDF or DOCX; text was not extracted",
                    source_url=document_url)

            meeting_date = parse_meeting_date(link_text) or parse_meeting_date(document_url)
            if meeting_date is None and _LOOKS_DATED_RE.search(f"{link_text} {document_url}"):
                db.record_parse_failure(
                    conn, module_name, "meeting_date", link_text or document_url,
                    "link text/URL looks dated but no date parsed", source_url=document_url)

            terms = _subject_terms(body_text or "")
            subject_hits = sum(terms.values())
            mentions = m28.find_provider_mentions(body_text or "")

            db.upsert(conn, "icb_board_paper_candidates", {
                "icb_name": icb_name,
                "document_url": document_url,
                "meeting_title": (link_text or None) and link_text[:300],
                "committee_name": _committee_name(document_url, link_text),
                "meeting_date": meeting_date,
                "document_kind": _classify_kind(document_url, link_text),
                "from_index_page": int(bool(from_index)),
                "has_body_text": int(bool(body_text)),
                "subject_hits": subject_hits,
                "provider_mentions": len(mentions),
                "verified": 0,
                "verified_at": None,
                "rejected": 0,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
                "discovery_method": method,
                **_provenance(fetched),
            }, natural_key=["icb_name", "document_url"], preserve=db.DECISION_COLUMNS)
            documents += 1
            icb_docs += 1

            for term, occurrences in terms.items():
                db.upsert(conn, "icb_paper_subject_terms", {
                    "document_url": document_url, "term": term, "occurrences": occurrences,
                }, natural_key=["document_url", "term"])
                snippet = _snippet_for(body_text or "", term)
                if snippet:
                    db.upsert(conn, "restricted_icb_paper_snippets", {
                        "document_url": document_url, "term": term, "snippet_text": snippet,
                        **_provenance(fetched),
                    }, natural_key=["document_url", "term"])

            for provider_key, variant in mentions:
                db.upsert(conn, "icb_paper_provider_mentions", {
                    "document_url": document_url, "provider_key": provider_key,
                    "matched_name": variant,
                }, natural_key=["document_url", "provider_key"])
                provider_mentions += 1

            if subject_hits or mentions:
                icb_subject += 1
                subject_documents += 1

        status = ("robots_disallowed" if crawl.robots_blocked and not crawl.pages_fetched
                  else "unreachable" if crawl.unreachable
                  else "no_documents_found" if not crawl.candidates
                  else "ok")
        crawl_row.update({
            "board_url": crawl.board_url or seed_url,
            "pages_fetched": crawl.pages_fetched,
            "docs_found": icb_docs,
            "docs_with_subject": icb_subject,
            "ceiling_reached": int(crawl.ceiling_reached),
            "status": status,
            "http_status": crawl.index_status,
            "payload_sha256": crawl.index_sha,
        })
        db.upsert(conn, "icb_site_crawls", crawl_row, natural_key=["icb_name"])
        if status == "no_documents_found":
            db.record_review_item(
                conn, module_name, "icb_no_documents_found", icb_name,
                json.dumps({"board_url": crawl.board_url or seed_url,
                             "pages_fetched": crawl.pages_fetched}))

        if not ctx.dry_run:
            conn.commit()

    worklist = [dict(r) for r in conn.execute(
        "SELECT c.icb_name, b.region, c.committee_name, c.meeting_date, c.document_kind, "
        "c.subject_hits, c.provider_mentions, c.document_url "
        "FROM icb_board_paper_candidates c "
        "LEFT JOIN integrated_care_boards b ON b.name = c.icb_name "
        "WHERE c.verified = 0 AND c.rejected = 0 "
        "AND (c.subject_hits > 0 OR c.provider_mentions > 0) "
        "ORDER BY b.region, c.icb_name, c.subject_hits DESC")]
    out_dir = Path(ctx.settings.logs_dir).parent / "docs" / "verification"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "icb_board_papers.md"
    out_path.write_text(_render_worklist(worklist), encoding="utf-8")

    log.info("icb.run_complete", icbs=len(units), documents=documents,
              subject_documents=subject_documents, provider_mentions=provider_mentions,
              fetch_workers=workers, verification=str(out_path))
