"""Module 28 — Safeguarding Adult Reviews (SARs).

There is no equivalent of judiciary.uk for Safeguarding Adults Boards: ~150
of them, each an independent partnership publishing on its own council's
website with no shared platform. But the National Network for Chairs of
Adult Safeguarding Boards runs a single library that boards submit their
published SARs to — nationalnetwork.org.uk/search.html, covering documents
back to 2015. That is the source this module reads, for the same reason m08
reads judiciary.uk rather than crawling 150 coroners' courts: one source with
real coverage beats 150 with none.

THE LIBRARY IS A FLAT LIST, NOT A DATABASE. Every entry the library carries
is a title (as submitted — very often a bare filename) and a download link,
grouped only by the year it was added. There is no board-name field, no
publication date, no distribution list — nothing structured to key on beyond
the document's own URL. Two things follow from that:

  * `sab_name` is read from the DOCUMENT'S OWN TEXT — SAR reports name their
    commissioning board on the cover page or in the opening paragraph, the
    same way a PFD report states its coroner area — never guessed from the
    title or from which year-folder the library filed it under. Unfound is
    NULL plus a parse_failures row.
  * There is no attempt at a PFD-style "matters of concern" excerpt. That
    works for PFD because judiciary.uk reports share one template; SAR
    reports are written by ~150 different boards over a decade and share
    none, so no fixed pattern for "where the findings start" would be
    trustworthy — see docs/CAVEATS.md on guessing across heterogeneous
    sources. What this module gives instead is a term-frequency finding aid
    (sar_concern_terms, the same term list PFD uses) and provider mentions
    across the full text, neither of which requires knowing the document's
    structure.

PERSONAL DATA. A SAR's title is very often the subject's own name or a
chosen pseudonym ("Hannah", "Mr Z", "Ruth Mitchell"), and the source gives no
way to tell which. Rather than guess, every title goes to
restricted_sar_persons and never to a public column — restricted_ tables are
kept out of every export by guard_columns() and the reveal gate, not by
this module remembering to redact.

SCALE. Roughly 800 documents across the whole library. A document already
read successfully is skipped on a later run (see `_already_processed`) —
there is no per-document date to filter on with --since, so revisiting the
full listing every run is the only way to notice additions, but re-fetching
a document already read would cost real crawl time for nothing. A document
recorded with no text is retried rather than skipped forever, because this
module's ability to read it can improve after the fact — DOCX support was
added after the first run, and every DOCX read before that stayed
`has_body_text = 0` until the very next plain rerun picked them up under
this rule.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import structlog

from pipeline import db, ocr, pdftext, providers
from pipeline.documents.inspect import DOCX_MIME
from pipeline.documents.parsers import DOCXParser
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.keywords import PFD_CONCERN_INDEX_TERMS, SUPPLIER_NAME_VARIANTS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "national_sar_library"
LIBRARY_URL = "https://nationalnetwork.org.uk/search.html"

# Each year's documents sit in a <table> under a "SARs <year>" collapsible
# heading; see docs/verification notes in the module's PR for a captured
# sample. Non-greedy up to the next heading (or end of page) so one year's
# rows are never attributed to another's.
_SECTION_RE = re.compile(
    r'<button[^>]*class="collapsible"[^>]*>\s*SARs?\s+(\d{4})\s*</button>(.*?)'
    r'(?=<button[^>]*class="collapsible"|\Z)', re.IGNORECASE | re.DOTALL)
_ROW_RE = re.compile(
    r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>\s*<td[^>]*>\s*<a\s+href="([^"]+)"',
    re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")

_DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt")

# The board's own name for itself, read the same way pfd_reports.coroner_area
# is read from a PFD header: literal extraction, not validated against a
# fixed list. Up to six capitalised words (or "and"/"&") immediately before
# the phrase, which covers multi-authority boards ("Bath and North East
# Somerset Safeguarding Adults Board") without also swallowing an entire
# preceding sentence.
#
# The naming phrase varies more than the first cut allowed for, and 269 of
# the library's documents were left with a NULL board as a result: boards
# have renamed to "Safeguarding Adults Partnership Board", some style
# themselves "... Safeguarding Partnership", and a minority write "Adult
# Safeguarding Board" in that word order. All name the same body — the
# partnership that commissioned the review — so all are accepted.
_SAB_NAME_PHRASE = (
    r"Safeguarding\s+Adults?\s+Partnership\s+Board"
    r"|Safeguarding\s+Adults?\s+Partnership"
    r"|Safeguarding\s+Adults?\s+Board"
    r"|Safeguarding\s+Partnership\s+Board"
    r"|Adults?\s+Safeguarding\s+Board")
_SAB_NAME_RE = re.compile(
    r"\b((?:[A-Z][A-Za-z'\-]*|and|&)(?:\s+(?:[A-Z][A-Za-z'\-]*|and|&)){0,5}?"
    r"\s+(?:" + _SAB_NAME_PHRASE + r"))\b")

# Fallback, reached only when the phrase above is not found: the review
# routinely says who set it up ("This review was commissioned by the X
# Safeguarding Adults Board"). A named commissioner attributes the review
# more firmly than a bare mention, which is why this is safe to fall back
# to; it stays inside the opening window for the same reason.
_SAB_COMMISSIONED_RE = re.compile(
    r"(?:[Cc]ommissioned|[Ii]nitiated|[Rr]equested|[Pp]repared|[Pp]ublished)\s+"
    r"(?:by|for|on behalf of)\s+(?:the\s+)?"
    r"((?:[A-Z][A-Za-z'\-]*|and|&)(?:\s+(?:[A-Z][A-Za-z'\-]*|and|&)){0,6}?"
    r"\s+(?:" + _SAB_NAME_PHRASE + r"))\b")

# Only the opening of the document is searched. SAR reports state their
# commissioning board on the cover page or in the first paragraph; searching
# the whole text risked matching a board named only in passing, as a
# multi-agency review often names a neighbouring board once.
_SAB_NAME_SEARCH_CHARS = 4000


def strip_html(raw_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw_html or "")
    text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_library_page(page_html: str) -> list[dict]:
    """Every (title, href, library_year) row on the library page.

    A row that produces no usable title or link is dropped rather than kept
    with a blank field — there is nothing to fetch or to show for it.
    """
    rows: list[dict] = []
    for year_text, section_html in _SECTION_RE.findall(page_html or ""):
        year = int(year_text)
        for raw_title, href in _ROW_RE.findall(section_html):
            title = strip_html(raw_title)
            link = html_lib.unescape(href.strip())
            if not title or not link:
                continue
            rows.append({"title": title, "href": link, "library_year": year})
    return rows


def resolve_document_url(href: str) -> str:
    """An absolute, fetchable URL from a raw href.

    The source writes hrefs as literal filesystem paths — spaces and
    ampersands included, unescaped — which is invalid HTML but is what every
    browser tolerates by re-encoding on request. This does the same
    re-encoding explicitly, on the path only, so the query string (there
    never is one here) and any already-encoded byte are not touched twice.
    """
    joined = urljoin(LIBRARY_URL, href)
    parts = urlsplit(joined)
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe="/%"),
                        parts.query, parts.fragment))


def document_extension(url: str) -> str | None:
    path = urlsplit(url).path.lower()
    for ext in _DOCUMENT_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return None


# Words that can sit in the capitalised run in front of the naming phrase
# but are never part of a board's name — report/title vocabulary the greedy
# prefix would otherwise swallow ("SAFEGUARDING ADULT REVIEW Walsall
# Safeguarding Adults Partnership"). The leftward walk in _clean_sab_name
# stops at the first of these.
_SAB_PREFIX_STOPWORDS = frozenset(
    "safeguarding adult adults review reviews report reports sar sars "
    "executive summary serious case overview thematic learning brief "
    "briefing practitioner proforma final draft published foreword "
    "official criteria methodology introduction confidential the of".split())


def _clean_sab_name(raw: str) -> str | None:
    """Trim a raw regex capture back to '<place> <naming phrase>'.

    The capitalised-words prefix in `_SAB_NAME_RE` matches greedily across a
    preceding title ("Bradley Safeguarding Adults Review Havering
    Safeguarding Adults Board"), so this re-anchors on the *rightmost* start
    of the naming phrase and keeps only the run of capitalised place words
    immediately before it, stopping at the first title-vocabulary or
    lower-case token. A capture with no place word left in front of the
    phrase is not a usable board name and returns None.
    """
    tokens = re.sub(r"\s+", " ", raw).strip().split()
    lowered = [t.lower() for t in tokens]

    phrase_start = None
    for i, low in enumerate(lowered):
        if low != "safeguarding":
            continue
        # "Adult Safeguarding Board" word order: the phrase starts one token
        # earlier, and that "Adult" is part of the name, not a trimmable
        # prefix word.
        phrase_start = i - 1 if lowered[i - 1:i] in (["adult"], ["adults"]) else i
    if not phrase_start:
        return None

    start = phrase_start
    # Up to six place words: multi-authority boards run long ("Bracknell
    # Forest and Windsor and Maidenhead Safeguarding Adults Board").
    while start > 0 and phrase_start - start < 6:
        prev = tokens[start - 1]
        low = prev.lower()
        if low in _SAB_PREFIX_STOPWORDS:
            break
        if not (prev[:1].isupper() or low in ("and", "&")):
            break
        start -= 1
    while start < phrase_start and tokens[start].lower() in _SAB_PREFIX_STOPWORDS | {"and", "&"}:
        start += 1
    # "Local Safeguarding Adults Board" with nothing else in front is the
    # generic statutory term, not a named board.
    if " ".join(tokens[start:phrase_start]).lower() in ("", "local", "a local"):
        return None
    return " ".join(tokens[start:])


def extract_sab_name(text: str | None) -> str | None:
    if not text:
        return None
    head = text[:_SAB_NAME_SEARCH_CHARS]
    match = _SAB_NAME_RE.search(head) or _SAB_COMMISSIONED_RE.search(head)
    return _clean_sab_name(match.group(1)) if match else None


def index_concern_terms(text: str, welded: bool = False) -> dict[str, int]:
    """Count of each watched term anywhere in the document. A finding aid
    only — see pfd_reports.index_concern_terms, which this mirrors.

    `welded` drops the word boundary for OCR text, which occasionally runs
    words together; see m08_pfd_reports for the fuller reasoning.
    """
    counts: dict[str, int] = {}
    lowered = (text or "").lower()
    prefix = "" if welded else r"\b"
    for term in PFD_CONCERN_INDEX_TERMS:
        n = len(re.findall(rf"{prefix}{re.escape(term.lower())}", lowered))
        if n:
            counts[term] = n
    return counts


def _normalise(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(limited|ltd|llp|plc|cic)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Short/ambiguous variants that would produce nonsense matches in free text.
_UNSAFE_VARIANTS = {"cgl", "via", "inclusion"}

_PROVIDER_VARIANTS: list[tuple[str, str, list[str]]] = []
for _key, _variants in SUPPLIER_NAME_VARIANTS.items():
    for _variant in _variants:
        _n = _normalise(_variant)
        if _n and _n not in _UNSAFE_VARIANTS:
            _PROVIDER_VARIANTS.append((_key, _variant, _n.split()))


def find_provider_mentions(text: str) -> list[tuple[str, str]]:
    """(provider_key, matched_variant) for providers named anywhere in
    `text`. Whole-token matching, as in m08_pfd_reports — a false positive
    here would attribute a safeguarding review to an organisation with no
    part in it.

    Unlike PFD there is only one kind of mention: the library gives no
    distribution list to distinguish "sent to" from "named in".
    """
    tokens = _normalise(text).split()
    if not tokens:
        return []
    found: dict[str, str] = {}
    for provider_key, variant, variant_tokens in _PROVIDER_VARIANTS:
        window = len(variant_tokens)
        if window > len(tokens):
            continue
        for start in range(len(tokens) - window + 1):
            if tokens[start:start + window] == variant_tokens:
                found.setdefault(provider_key, variant)
                break
    return sorted(found.items())


def _already_processed(conn, document_url: str) -> bool:
    """Whether an earlier run already got everything out of this document
    that this module currently knows how to get.

    Not simply "does a row exist": a row with `has_body_text = 0` recorded
    a document this module could not read *at the time* -- most concretely,
    every DOCX document read before DOCX support existed. Read ability can
    change under a document that has not itself changed (this module gaining
    a new parser, OCR being enabled), so a document is only treated as
    settled once text was actually extracted, or its extension is one this
    module still cannot read at all. Mirrors m08_pfd_reports'
    `_already_has_concerns`, which retries a report's PDF for the same
    reason: existing but empty is not the same as done.
    """
    row = conn.execute(
        "SELECT has_body_text, document_ext FROM sar_documents WHERE document_url = ?",
        (document_url,)).fetchone()
    if row is None:
        return False
    if row["has_body_text"]:
        return True
    return row["document_ext"] not in (".pdf", ".docx")


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _read_pdf(ctx: ModuleContext, module_name: str, document_url: str,
              fetch_result) -> tuple[str | None, str | None]:
    """The text of one SAR PDF, with an OCR fallback for scans.

    Returns (text, source) where source is "pdf" or "ocr", or (None, None)
    with a parse_failures row recorded explaining why. Mirrors
    m08_pfd_reports.fetch_pdf_report's PDF/OCR handling.
    """
    conn = ctx.conn
    try:
        pages = pdftext.page_texts(ctx.settings, SOURCE_SYSTEM,
                                    fetch_result.payload_sha256, fetch_result.body)
    except Exception as exc:
        log.warning("sar.pdf_unreadable", url=document_url, error=f"{type(exc).__name__}: {exc}")
        db.record_parse_failure(conn, module_name, "body_text", document_url,
                                 f"PDF could not be opened: {type(exc).__name__}",
                                 source_url=document_url)
        return None, None

    text = "\n".join(page_text for page_text in pages if page_text).strip()
    if text:
        return text, "pdf"

    if not ocr.enabled(ctx.settings):
        db.record_parse_failure(
            conn, module_name, "body_text", document_url,
            f"the document is a scan with no text layer ({len(pages)} pages); "
            + ("OCR is installed but switched off (set OCR_ENABLED)"
                if ocr.available() else "reading it needs the ocr extra"),
            source_url=document_url)
        return None, None

    try:
        ocr_pages = ocr.page_texts(ctx.settings, SOURCE_SYSTEM,
                                    fetch_result.payload_sha256, fetch_result.body)
    except Exception as exc:
        log.warning("sar.ocr_failed", url=document_url, error=f"{type(exc).__name__}: {exc}")
        db.record_parse_failure(conn, module_name, "body_text", document_url,
                                 f"OCR failed: {type(exc).__name__}", source_url=document_url)
        return None, None

    ocr_text = "\n".join(page_text for page_text in ocr_pages if page_text).strip()
    if not ocr_text:
        db.record_parse_failure(
            conn, module_name, "body_text", document_url,
            f"OCR read the {len(ocr_pages)}-page scan and found no text on any page",
            source_url=document_url)
        return None, None
    return ocr_text, "ocr"


def _read_docx(conn, module_name: str, document_url: str,
                fetch_result) -> tuple[str | None, str | None]:
    """The text of one SAR document published as DOCX rather than PDF.

    A meaningful minority of the library is DOCX -- boards submit whatever
    file they have. Reads it with the stdlib-only DOCX parser already built
    for the document-analysis worker (zipfile + xml.etree against
    word/document.xml) rather than adding a python-docx dependency for a
    handful of documents; that parser has no optional-extra requirement.
    """
    try:
        parsed = DOCXParser().parse(fetch_result.body, DOCX_MIME)
    except Exception as exc:
        log.warning("sar.docx_unreadable", url=document_url, error=f"{type(exc).__name__}: {exc}")
        db.record_parse_failure(conn, module_name, "body_text", document_url,
                                 f"DOCX could not be opened: {type(exc).__name__}",
                                 source_url=document_url)
        return None, None

    text = parsed.text.strip()
    if not text:
        db.record_parse_failure(
            conn, module_name, "body_text", document_url,
            "DOCX opened but contained no extractable text", source_url=document_url)
        return None, None
    return text, "docx"


@register_module(
    "m28_sar_reports", supports_since=False,
    since_note="the library gives no per-document date; a document already read is skipped "
                "rather than re-fetched, which is what makes revisiting the full listing "
                "every run affordable",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m28_sar_reports"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    documents_written = 0
    texts_read = 0
    provider_mentions = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("reading the SAR library index")
        try:
            index = client.get(LIBRARY_URL)
        except RobotsDisallowed:
            db.record_review_item(conn, module_name, "sar_library_robots_disallowed",
                                   LIBRARY_URL, json.dumps({}))
            if not ctx.dry_run:
                conn.commit()
            return

        if not index.ok:
            db.record_review_item(conn, module_name, "sar_library_unavailable", LIBRARY_URL,
                                   json.dumps({"status": index.status_code}))
            if not ctx.dry_run:
                conn.commit()
            return

        rows = parse_library_page(index.body.decode("utf-8", "replace"))
        if not rows:
            db.record_parse_failure(
                conn, module_name, "listing", LIBRARY_URL,
                "the library page returned no recognisable document rows; "
                "its markup may have changed", source_url=LIBRARY_URL)
            if not ctx.dry_run:
                conn.commit()
            return

        for row in ctx.track(rows, "SAR library entries"):
            if ctx.limit and documents_written >= ctx.limit:
                break

            document_url = resolve_document_url(row["href"])
            ext = document_extension(document_url)
            if ext is None or _already_processed(conn, document_url):
                continue

            try:
                fetch_result = client.get(document_url)
            except RobotsDisallowed:
                db.record_review_item(conn, module_name, "sar_document_robots_disallowed",
                                       document_url, json.dumps({"title": row["title"]}))
                if not ctx.dry_run:
                    conn.commit()
                continue
            if not fetch_result.ok:
                db.record_review_item(
                    conn, module_name, "sar_document_unavailable", document_url,
                    json.dumps({"title": row["title"], "status": fetch_result.status_code}))
                if not ctx.dry_run:
                    conn.commit()
                continue

            body_text: str | None = None
            body_source: str | None = None
            if ext == ".pdf":
                ctx.phase(f"reading {row['title'][:60]}")
                body_text, body_source = _read_pdf(ctx, module_name, document_url, fetch_result)
            elif ext == ".docx":
                ctx.phase(f"reading {row['title'][:60]}")
                body_text, body_source = _read_docx(conn, module_name, document_url, fetch_result)
            else:
                db.record_parse_failure(
                    conn, module_name, "body_text", document_url,
                    f"document is {ext}, not a PDF or DOCX; text was not extracted",
                    source_url=document_url)

            sab_name = extract_sab_name(body_text)
            if body_text and not sab_name:
                db.record_parse_failure(
                    conn, module_name, "sab_name", document_url,
                    "no board name found in the document's own text", source_url=document_url)

            db.upsert(conn, "sar_documents", {
                "document_url": document_url,
                "document_ext": ext,
                "library_year": row["library_year"],
                "sab_name": sab_name,
                "has_body_text": int(bool(body_text)),
                **_provenance(fetch_result),
            }, natural_key=["document_url"])
            documents_written += 1

            # RESTRICTED: the title is, very often, the subject's own name.
            db.upsert(conn, "restricted_sar_persons", {
                "document_url": document_url, "title_raw": row["title"],
            }, natural_key=["document_url"])

            if body_text:
                texts_read += 1
                # RESTRICTED: full text names the subject throughout, not
                # only in the title.
                db.upsert(conn, "restricted_sar_report_text", {
                    "document_url": document_url, "body_text": body_text,
                }, natural_key=["document_url"])

                for provider_key, variant in find_provider_mentions(body_text):
                    db.upsert(conn, "sar_provider_mentions", {
                        "document_url": document_url, "provider_key": provider_key,
                        "matched_name": variant,
                    }, natural_key=["document_url", "provider_key"])
                    provider_mentions += 1

                for term, occurrences in index_concern_terms(
                        body_text, welded=body_source == "ocr").items():
                    db.upsert(conn, "sar_concern_terms", {
                        "document_url": document_url, "term": term, "occurrences": occurrences,
                    }, natural_key=["document_url", "term"])

            if not ctx.dry_run:
                conn.commit()

    log.info("sar.run_complete", documents=documents_written, texts_read=texts_read,
              provider_mentions=provider_mentions)
