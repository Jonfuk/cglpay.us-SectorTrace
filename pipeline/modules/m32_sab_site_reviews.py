"""Module 32 — SARs on a Safeguarding Adults Board's own website.

Module 28's founding decision was one aggregator (the National SAR Library)
over ~150 independent board sites. This module is the deliberate exception,
scoped in docs/m32-sab-site-crawl.md: for each **England** board it crawls a
bounded set of likely paths on the board's own domain — from the website_url
m28 stored in safeguarding_adults_boards — and looks for reviews the board
published but never submitted to the library.

WHAT IT DOES NOT DO. It does not re-store a document already in the library:
a byte-for-byte match on payload_sha256 is skipped silently. A differently
formatted copy of a library review is stored as its own row (different URL,
different bytes) and flagged possible_duplicate_of_library_sar for a person.

HYBRID INGEST. A document is auto-ingested into sar_documents when either:
  * the link that led to it unambiguously says "Safeguarding Adults Review"
    AND its text names *this* board (resolve_sab_name agrees); or
  * it sits on a confirmed SAR *index* page on this board's own site (a
    guessed path that names SARs, or a page reached by following a SAR
    link) AND its text either names this board or names no board at all.
Never when the URL or link text looks like process furniture — a referral
form, a template, terms of reference (_TEMPLATE_RE) — and never when the
text names a *different* board (sab_site_sar_board_mismatch: a board site
linking to a neighbour's review is the expected false positive). Everything
else is a sab_site_sar_candidate review item; nothing reaches the canonical
table on a guess, the same gate m09 puts on cdp_documents.

sab_name is known here (it is the board whose site this is), so it is set to
that board's official directory name with sab_name_source = 'sab_website',
the highest-confidence tier. discovered_via = 'sab_website' on every row.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import unquote, urljoin, urlparse

import structlog

from pipeline import db, providers
from pipeline.http import RobotsDisallowed
from pipeline.modules import m28_sar_reports as m28
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "sab_website"

# Likely locations for a board's SAR / publications listing. Tried in order;
# a 404 is expected and unremarkable, exactly as in m09/m24.
SAR_PATHS = [
    "/",
    # observed on real board sites, 2026-08 (see docs/m32-sab-site-crawl.md)
    "/safeguarding-adults-reviews",
    "/safeguarding-adult-reviews",
    "/safeguarding-adults-reviews-sar",
    "/safeguarding-adult-reviews-sar",
    "/safeguarding-adults-reviews-sars",
    "/safeguarding-adult-reviews-sars",
    "/published-sars",
    "/sar",
    "/sars",
    "/sar-reports",
    "/sars-published",
    "/reviews",
    "/case-reviews",
    "/case-reviews/safeguarding-adult-reviews",
    "/adult-reviews",
    "/learning-from-reviews",
    "/learning-reviews",
    "/learning-from-safeguarding-adults-reviews",
    "/learning-and-improvement",
    "/publications",
    "/resources",
    "/serious-case-reviews",
    "/professionals",
    "/professionals/safeguarding-adult-reviews",
    "/professionals/safeguarding-adult-review-sar-reports",
    "/safeguarding/reviews",
    "/about-us/safeguarding-adults-reviews",
    "/about-us/safeguarding-adult-reviews",
]

# One hop past a discovery page: a link whose text says SAR but which points
# at another same-host *page* (not a document) is followed once and scanned
# too. Many boards keep their reviews one click below any of the guessed
# paths, behind a "Safeguarding Adults Reviews" link on the homepage.
MAX_SUBPAGES_PER_SAB = 8
MAX_PAGES_PER_SAB = len(SAR_PATHS) + MAX_SUBPAGES_PER_SAB
MAX_DOCS_PER_SAB = 40


def _host_key(netloc: str) -> str:
    """Host for same-site comparison, insensitive to a leading www. — board
    sites link between the www and bare forms freely, and treating them as
    different hosts dropped every candidate on sites that do."""
    return (netloc or "").lower().split("@")[-1].removeprefix("www.")

_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                      re.IGNORECASE | re.DOTALL)

# What makes a link worth following at all.
_SAR_LINK_VOCAB = re.compile(
    r"safeguarding[\s\-]?adults?[\s\-]?review|safeguarding[\s\-]?adult[\s\-]?review|"
    r"\bSARs?\b|serious[\s\-]?case[\s\-]?review|learning[\s\-]?review|"
    r"learning[\s\-]?brief|\d[\s\-]?minute[\s\-]?briefing", re.IGNORECASE)
# What makes it unambiguous enough to auto-ingest without a person looking.
_SAR_LINK_STRONG = re.compile(
    r"safeguarding[\s\-]?adults?[\s\-]?review|safeguarding[\s\-]?adult[\s\-]?review",
    re.IGNORECASE)

# A board's SAR page also links its process furniture — referral forms,
# templates, terms of reference, checklists. Those are not reviews; a
# document whose URL or link text matches this is never auto-ingested (it
# still becomes a review-queue candidate, so a misfiled real review is
# recoverable).
_TEMPLATE_RE = re.compile(
    r"referral[\s\-]?form|\bform\s*\d|\bproforma\b|template|toolkit|"
    r"terms?[\s\-]?of[\s\-]?reference|\bToR\b|checklist|flow[\s\-]?chart|"
    r"process[\s\-]?map|\bpathway\b|guidance|\bpolicy\b|procedure|protocol|"
    r"application[\s\-]?form|nomination|self[\s\-]?assessment|quality[\s\-]?mark|"
    r"agenda|minutes|annual[\s\-]?report|newsletter|action[\s\-]?plan|"
    r"strategic[\s\-]?plan|business[\s\-]?plan", re.IGNORECASE)

_YEAR_RE = re.compile(r"\b(20[0-2]\d)\b")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _link_text(raw: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or "")).strip()


def sar_links_on_page(page_html: str, page_url: str, host: str,
                       is_sar_index: bool = False) -> list[tuple[str, str]]:
    """(document_url, link_text) for links on one page that point at a
    document (pdf/docx/odt) on the same host.

    Normally the link's URL or text must also carry SAR vocabulary. On a page
    reached *via* a SAR-vocabulary link (`is_sar_index`) that filter is
    dropped: the page context already vouches for it, so a document linked
    only as "Anne (2023)" is still collected. The hybrid gate downstream
    then decides auto-ingest vs. review, so relaxing here only widens what a
    person gets to look at, never what is stored on a guess.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, href.strip())
        if _host_key(urlparse(url).netloc) != _host_key(host):
            continue
        path = url.lower().split("?")[0]
        if not path.endswith(m28._DOCUMENT_EXTENSIONS):
            continue
        text = _link_text(raw_text)
        if not is_sar_index and not _SAR_LINK_VOCAB.search(f"{url} {text}"):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append((url, text))
    return out


def sar_subpages_on_page(page_html: str, page_url: str, host: str) -> list[str]:
    """Same-host links that are NOT documents but whose text/URL says SAR —
    a "Safeguarding Adults Reviews" page one click below the guessed paths."""
    out: list[str] = []
    seen: set[str] = set()
    for href, raw_text in _LINK_RE.findall(page_html or ""):
        url = urljoin(page_url, href.strip()).split("#")[0]
        if _host_key(urlparse(url).netloc) != _host_key(host) or url == page_url:
            continue
        path = url.lower().split("?")[0]
        if path.endswith(m28._DOCUMENT_EXTENSIONS):
            continue
        if not _SAR_LINK_VOCAB.search(f"{url} {_link_text(raw_text)}"):
            continue
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


@dataclass
class BoardCrawl:
    """What one board's fetching produced. Built on a pool thread; nothing is
    written until the main thread has it (m24's SpendFindings pattern)."""

    sab_name: str
    base_url: str
    pages_fetched: int = 0
    homepage_status: int = 0
    homepage_sha: str = ""
    candidates: list = field(default_factory=list)   # (FetchResult, link_text)
    review_items: list = field(default_factory=list)  # (item_type, raw_value, context)
    robots_blocked: bool = False
    unreachable: bool = False


def crawl_board(unit: tuple[str, str], client) -> BoardCrawl:
    """One board's entire fetch workload. Runs on a pool thread — fetch only,
    no database."""
    sab_name, base_url = unit
    crawl = BoardCrawl(sab_name=sab_name, base_url=base_url)
    host = urlparse(base_url).netloc

    candidate_urls: list[tuple[str, str]] = []
    subpages: list[str] = []
    fetched_pages: set[str] = set()
    reached_anything = False

    def scan(result, is_index: bool) -> None:
        nonlocal reached_anything
        reached_anything = True
        crawl.pages_fetched += 1
        page_url = result.final_url or result.url
        fetched_pages.add(page_url.split("#")[0])
        html_text = result.body.decode("utf-8", "replace")
        for u, t in sar_links_on_page(html_text, page_url, host, is_index):
            candidate_urls.append((u, t, is_index))
        for sub in sar_subpages_on_page(html_text, page_url, host):
            if sub not in subpages and sub.split("#")[0] not in fetched_pages:
                subpages.append(sub)

    for path in SAR_PATHS:
        if crawl.pages_fetched >= MAX_PAGES_PER_SAB:
            break
        url = urljoin(base_url, path)
        try:
            result = client.get(url)
        except RobotsDisallowed:
            crawl.review_items.append((
                "sab_site_robots_disallowed", url, {"sab_name": sab_name}))
            crawl.robots_blocked = True
            continue
        if not result.ok:
            continue
        if path == "/":
            crawl.homepage_status = result.status_code
            crawl.homepage_sha = result.payload_sha256
            # A homepage that redirects to another domain (a stale directory
            # URL, or www/bare canonicalisation) is followed: same-site is
            # then judged against where it actually landed.
            landed = urlparse(result.final_url or result.url).netloc
            if landed:
                host = landed
        # A path that itself names SARs is an index page: harvest every
        # document on it, not only the ones whose link text repeats the word.
        scan(result, is_index=bool(_SAR_LINK_VOCAB.search(path)))

    # One hop: follow up to MAX_SUBPAGES_PER_SAB "Safeguarding Adults
    # Reviews" links found above and scan those for documents too.
    for sub in subpages[:MAX_SUBPAGES_PER_SAB]:
        if crawl.pages_fetched >= MAX_PAGES_PER_SAB:
            break
        if sub.split("#")[0] in fetched_pages:
            continue
        try:
            result = client.get(sub)
        except RobotsDisallowed:
            crawl.review_items.append((
                "sab_site_robots_disallowed", sub, {"sab_name": sab_name}))
            continue
        if result.ok:
            scan(result, is_index=True)   # reached via a SAR-vocabulary link

    if not reached_anything and not crawl.robots_blocked:
        crawl.unreachable = True
        return crawl

    # Collapse duplicates, keeping the first link text seen and treating a
    # document as index-found if it was linked from any SAR index page.
    merged: dict[str, tuple[str, bool]] = {}
    for doc_url, link_text, from_index in candidate_urls:
        text, idx = merged.get(doc_url, (link_text, False))
        merged[doc_url] = (text or link_text, idx or from_index)

    for doc_url, (link_text, from_index) in merged.items():
        if len(crawl.candidates) >= MAX_DOCS_PER_SAB:
            break
        try:
            fetched = client.get(doc_url)
        except RobotsDisallowed:
            crawl.review_items.append((
                "sab_site_robots_disallowed", doc_url, {"sab_name": sab_name}))
            continue
        if not fetched.ok:
            crawl.review_items.append((
                "sab_site_doc_unavailable", doc_url,
                {"sab_name": sab_name, "status": fetched.status_code}))
            continue
        crawl.candidates.append((fetched, link_text, from_index))
    return crawl


def _same_board(name_a: str | None, name_b: str | None) -> bool:
    if not name_a or not name_b:
        return False
    return m28._sab_key(m28._place_of(name_a)) == m28._sab_key(m28._place_of(name_b))


def _year_for(*texts: str) -> int:
    """A publication year from the filename or link text, else the crawl
    year. Best-effort — sab_website rows carry no real library year."""
    for text in texts:
        cleaned = re.sub(r"[^0-9A-Za-z]+", " ", unquote(text or ""))
        m = _YEAR_RE.search(cleaned)
        if m:
            return int(m.group(1))
    return datetime.now(timezone.utc).year


@register_module(
    "m32_sab_site_reviews", supports_since=False,
    depends_on=("m28_sar_reports",),
    depends_note="crawls each board's own site using the website_url m28 stores "
                  "in safeguarding_adults_boards from the Ann Craft Trust directory",
    since_note="SAR pages carry no per-document date and the crawl is bounded, so "
                "a full pass every run is affordable",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m32_sab_site_reviews"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    directory_rows = [dict(r) for r in conn.execute(
        "SELECT name, nation, website_url FROM safeguarding_adults_boards").fetchall()]
    sab_index = m28.build_sab_index(directory_rows)

    boards = [(r["name"], r["website_url"]) for r in directory_rows
              if r["nation"] == "England" and (r["website_url"] or "").startswith("http")]
    for r in directory_rows:
        if r["nation"] == "England" and not (r["website_url"] or "").startswith("http"):
            db.record_review_item(conn, module_name, "sab_website_unknown", r["name"],
                                   json.dumps({"note": "no usable website_url in the directory"}))
    if not boards:
        log.info("sab_site.no_boards",
                  note="run m28_sar_reports first to populate safeguarding_adults_boards")
        if not ctx.dry_run:
            conn.commit()
        return
    if ctx.limit:
        boards = boards[:ctx.limit]

    existing_sha = {row["payload_sha256"] for row in conn.execute(
        "SELECT payload_sha256 FROM sar_documents").fetchall()}

    ingested = candidates = 0
    workers = worker_count(ctx.settings, ctx.limit)
    stream = fetch_in_parallel(boards, crawl_board, source_system=SOURCE_SYSTEM,
                                settings=ctx.settings, max_workers=workers, cache_conn=conn)

    for outcome in ctx.track(stream, "board sites", total=len(boards)):
        sab_name, base_url = outcome.unit
        now = _utcnow()
        crawl_row = {
            "sab_name": sab_name, "website_url": base_url,
            "pages_fetched": 0, "docs_found": 0, "docs_ingested": 0,
            "docs_candidate": 0, "status": "unreachable", "last_crawled": now,
            "source_url": base_url, "retrieved_at": now, "http_status": 0,
            "source_system": SOURCE_SYSTEM, "payload_sha256": "",
        }

        if not outcome.ok:
            db.record_review_item(
                conn, module_name, "sab_site_collection_failed", sab_name,
                json.dumps({"website_url": base_url,
                             "error": f"{type(outcome.error).__name__}: {outcome.error}"}))
            db.upsert(conn, "sab_site_crawls", crawl_row, natural_key=["sab_name"])
            if not ctx.dry_run:
                conn.commit()
            continue

        crawl: BoardCrawl = outcome.value
        for item_type, raw_value, context in crawl.review_items:
            db.record_review_item(conn, module_name, item_type, raw_value, json.dumps(context))

        board_ingested = board_candidate = 0
        for fetched, link_text, from_index in crawl.candidates:
            document_url = fetched.final_url or fetched.url
            ext = m28.document_extension(document_url)
            if ext is None:
                continue
            if _already_ingested(conn, document_url):
                continue

            duplicate_of_library = fetched.payload_sha256 in existing_sha

            body_text = body_source = None
            if ext == ".pdf":
                body_text, body_source = m28._read_pdf(ctx, module_name, document_url, fetched)
            elif ext == ".docx":
                body_text, body_source = m28._read_docx(conn, module_name, document_url, fetched)
            else:
                db.record_parse_failure(
                    conn, module_name, "body_text", document_url,
                    f"document is {ext}, not a PDF or DOCX; text was not extracted",
                    source_url=document_url)

            text_board, _src = m28.resolve_sab_name(body_text, link_text, sab_index)
            names_other_board = bool(text_board) and not _same_board(text_board, sab_name)
            names_this_board = _same_board(text_board, sab_name)

            haystack = f"{document_url} {link_text}"
            strong_link = bool(_SAR_LINK_STRONG.search(haystack))
            looks_template = bool(_TEMPLATE_RE.search(haystack))

            if names_other_board:
                db.record_review_item(
                    conn, module_name, "sab_site_sar_board_mismatch", document_url,
                    json.dumps({"sab_name": sab_name, "text_names": text_board,
                                 "link_text": link_text[:200]}))
                continue

            # Auto-ingest when the source is trustworthy enough that a person
            # would only be rubber-stamping:
            #   * an unambiguous "Safeguarding Adults Review" link whose text
            #     also names this board (the original strict path), OR
            #   * a document found on a confirmed SAR index page on this
            #     board's own site whose text either names this board or
            #     names no board at all (the loosening).
            # Never a template/form, and never one naming a different board.
            auto = (not looks_template) and (
                (strong_link and names_this_board)
                or (from_index and (names_this_board or not text_board)))

            if not auto:
                reason = ("looks like a template or form, not a review" if looks_template
                          else "not on a confirmed SAR index page and the link is not unambiguous"
                          if not from_index
                          else "document text does not clearly name this board")
                db.record_review_item(
                    conn, module_name, "sab_site_sar_candidate", document_url,
                    json.dumps({"sab_name": sab_name, "link_text": link_text[:200],
                                 "has_body_text": bool(body_text),
                                 "from_index_page": from_index, "reason": reason}))
                board_candidate += 1
                continue

            if duplicate_of_library:
                db.record_review_item(
                    conn, module_name, "possible_duplicate_of_library_sar", document_url,
                    json.dumps({"sab_name": sab_name,
                                 "note": "same bytes as a document already in sar_documents; "
                                         "not re-stored"}))
                continue

            provenance = {
                "source_url": fetched.url,
                "retrieved_at": fetched.retrieved_at.isoformat(),
                "http_status": fetched.status_code,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": fetched.payload_sha256,
            }
            db.upsert(conn, "sar_documents", {
                "document_url": document_url,
                "document_ext": ext,
                "library_year": _year_for(link_text, document_url),
                "sab_name": sab_name,
                "sab_name_source": "sab_website",
                "has_body_text": int(bool(body_text)),
                "discovered_via": "sab_website",
                **provenance,
            }, natural_key=["document_url"])
            existing_sha.add(fetched.payload_sha256)
            board_ingested += 1

            # RESTRICTED: the link text may be the subject's pseudonym.
            db.upsert(conn, "restricted_sar_persons", {
                "document_url": document_url,
                "title_raw": link_text[:500] or document_url.rsplit("/", 1)[-1],
            }, natural_key=["document_url"])

            if body_text:
                db.upsert(conn, "restricted_sar_report_text", {
                    "document_url": document_url, "body_text": body_text,
                }, natural_key=["document_url"])
                for provider_key, variant in m28.find_provider_mentions(body_text):
                    db.upsert(conn, "sar_provider_mentions", {
                        "document_url": document_url, "provider_key": provider_key,
                        "matched_name": variant,
                    }, natural_key=["document_url", "provider_key"])
                for term, occurrences in m28.index_concern_terms(
                        body_text, welded=body_source == "ocr").items():
                    db.upsert(conn, "sar_concern_terms", {
                        "document_url": document_url, "term": term,
                        "occurrences": occurrences,
                    }, natural_key=["document_url", "term"])

        status = ("robots_disallowed" if crawl.robots_blocked and not crawl.pages_fetched
                  else "no_sars_found" if not crawl.candidates
                  else "ok")
        crawl_row.update({
            "pages_fetched": crawl.pages_fetched,
            "docs_found": len(crawl.candidates),
            "docs_ingested": board_ingested,
            "docs_candidate": board_candidate,
            "status": status,
            "http_status": crawl.homepage_status,
            "payload_sha256": crawl.homepage_sha,
        })
        db.upsert(conn, "sab_site_crawls", crawl_row, natural_key=["sab_name"])
        if status == "no_sars_found":
            db.record_review_item(
                conn, module_name, "sab_no_sars_found", sab_name,
                json.dumps({"website_url": base_url,
                             "pages_fetched": crawl.pages_fetched}))

        ingested += board_ingested
        candidates += board_candidate
        if not ctx.dry_run:
            conn.commit()

    log.info("sab_site.run_complete", boards=len(boards), ingested=ingested,
              candidates=candidates)


def _already_ingested(conn, document_url: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sar_documents WHERE document_url = %s", (document_url,)
    ).fetchone() is not None
