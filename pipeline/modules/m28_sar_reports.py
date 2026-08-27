"""Module 28 — Safeguarding Adult Reviews (SARs).

There is no equivalent of judiciary.uk for Safeguarding Adults Boards: ~150
of them, each an independent partnership publishing on its own council's
website with no shared platform. But the National Network for Chairs of
Adult Safeguarding Boards runs a single library that boards submit their
published SARs to — nationalnetwork.org.uk/search.html, covering documents
back to 2015. That is the source this module reads, for the same reason m08
reads judiciary.uk rather than crawling 150 coroners' courts: one source with
real coverage beats 150 with none.

That decision has a documented exception: `m32_sab_site_reviews` crawls each
England board's own site (using the website_url this module stores in
`safeguarding_adults_boards`) for reviews a board published but never
submitted here. See docs/m32-sab-site-crawl.md. This module stays the
aggregator; m32 is the supplement, and depends on it.

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

import collections
import html as html_lib
import json
import re
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

import httpx
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

# The library kept a separate collection for the documents SCIE (the Social
# Care Institute for Excellence) held before the National Network took the
# register on. Same site, same flat-list shape, different page — folded into
# the same processing so the corpus is the whole library, not just the part
# added since 2019.
SCIE_LIBRARY_URL = "https://nationalnetwork.org.uk/SCIE%20Library%202015-2018/"

# The Ann Craft Trust's directory of Safeguarding Adults Boards — the one
# maintained national index of them. Fetched to populate
# safeguarding_adults_boards and, more usefully, to give sab_name resolution
# a fixed set of official names to land on. See migration 0063.
SAB_DIRECTORY_URL = (
    "https://www.anncrafttrust.org/resources/"
    "find-your-nearest-safeguarding-adults-board/")
SOURCE_SAB_DIRECTORY = "anncrafttrust_sab_directory"

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
            rows.append({"title": title, "href": link, "library_year": year,
                          "base": LIBRARY_URL})
    return rows


# The SCIE page is the SAME <table> shape as the main page, under one
# "SCIE Library 2015-2018" collapsible instead of per-year ones, and its
# hrefs ("./file.pdf") are relative to SCIE_LIBRARY_URL, not to search.html —
# so both the section heading and the base URL differ. library_year is the
# collection's start; it has only ever meant "when added to the library".
_SCIE_SECTION_RE = re.compile(
    r'<button[^>]*class="collapsible"[^>]*>\s*SCIE\s+Library[^<]*</button>(.*?)'
    r'(?=<button[^>]*class="collapsible"|\Z)', re.IGNORECASE | re.DOTALL)


def parse_scie_library_page(page_html: str) -> list[dict]:
    """(title, href, library_year, base) rows from the SCIE 2015-2018 page."""
    match = _SCIE_SECTION_RE.search(page_html or "")
    section = match.group(1) if match else (page_html or "")
    rows: list[dict] = []
    for raw_title, href in _ROW_RE.findall(section):
        title = strip_html(raw_title)
        link = html_lib.unescape(href.strip())
        if not title or not link:
            continue
        rows.append({"title": title, "href": link, "library_year": 2015,
                      "base": SCIE_LIBRARY_URL})
    return rows


# Ann Craft Trust directory: nation headings, each over a list of
# "<a href="board site">Board Name</a>". The page also links to unrelated
# resources (the site's own menu, "What is a SAR?", etc.), so an anchor is
# kept only when its text reads like a board's name.
_NATION_HEADING_RE = re.compile(
    r"<h[1-6][^>]*>\s*(England|Wales|Scotland|Northern Ireland)\b",
    re.IGNORECASE)
# Up to 240 chars: some Welsh regional boards carry a parenthetical list of
# their member authorities ("Mid and West Wales Safeguarding Board
# (Carmarthenshire, Ceredigion, Pembrokeshire, Powys)"), trimmed off below.
_DIR_LINK_RE = re.compile(
    r'<a\s+[^>]*href="([^"]+)"[^>]*>([^<]{4,240})</a>', re.IGNORECASE)
# "Adult Support and Protection" is Scotland's term; "Public Protection" a
# couple of Scottish committees. Not just "board" as the body word.
_SAB_NAME_LOOKS_RIGHT = re.compile(
    r"safeguarding|adult (support and )?protection|public protection",
    re.IGNORECASE)
_SAB_BODY_WORD = re.compile(r"board|committee|partnership|team", re.IGNORECASE)


def parse_sab_directory(page_html: str) -> list[dict]:
    """(name, nation, website_url) for every board in the directory.

    Each anchor is attributed to the nearest nation heading above it and
    kept only when its text carries a safeguarding/adult-protection phrase
    and a body word (board / committee / partnership / team). A trailing
    parenthetical member-authority list is dropped from the stored name.
    """
    headings = [(m.start(), m.group(1).title())
                for m in _NATION_HEADING_RE.finditer(page_html or "")]
    out: list[dict] = []
    seen: set[str] = set()
    for m in _DIR_LINK_RE.finditer(page_html or ""):
        text = re.sub(r"\s+", " ", html_lib.unescape(m.group(2))).strip()
        text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
        low = text.lower()
        if not _SAB_NAME_LOOKS_RIGHT.search(low) or not _SAB_BODY_WORD.search(low):
            continue
        if low in seen:
            continue
        seen.add(low)
        nation = "England"
        for pos, name in headings:
            if pos < m.start():
                nation = name
            else:
                break
        out.append({"name": text, "nation": nation,
                    "website_url": html_lib.unescape(m.group(1).strip())})
    return out


def resolve_document_url(href: str, base: str = LIBRARY_URL) -> str:
    """An absolute, fetchable URL from a raw href, resolved against `base`.

    The source writes hrefs as literal filesystem paths — spaces and
    ampersands included, unescaped — which is invalid HTML but is what every
    browser tolerates by re-encoding on request. This does the same
    re-encoding explicitly, on the path only, so the query string (there
    never is one here) and any already-encoded byte are not touched twice.

    `base` matters: a SCIE-collection href is "./file.pdf" relative to
    SCIE_LIBRARY_URL, whose path ends in a directory ("/SCIE Library
    2015-2018/"); resolved against search.html it would lose that directory
    and 404.
    """
    joined = urljoin(base, href)
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
    """The board named in the document's own opening — the 0057 primitive,
    kept as-is. resolve_sab_name() layers on top of this."""
    if not text:
        return None
    head = text[:_SAB_NAME_SEARCH_CHARS]
    match = _SAB_NAME_RE.search(head) or _SAB_COMMISSIONED_RE.search(head)
    return _clean_sab_name(match.group(1)) if match else None


_SAB_KEY_DROP = re.compile(
    r"\b(safeguarding|adults?|partnership|board|committee|protection|"
    r"the|of|council|county|borough|city|metropolitan|district|"
    r"unitary|and)\b")


def _sab_key(s: str | None) -> str:
    """A board or place name reduced to its distinguishing tokens, so
    'Camden', 'Camden Safeguarding Adults Board' and 'Camden Safeguarding
    Adults Partnership Board' all key the same."""
    s = re.sub(r"[^a-z0-9 &]+", " ", (s or "").lower())
    s = _SAB_KEY_DROP.sub(" ", s)
    return re.sub(r"\s+", " ", s.replace("&", " and ")).strip()


def _place_of(board_name: str) -> str:
    """The board name with its 'Safeguarding ... Board' tail removed."""
    return re.sub(r"\s*safeguarding.*$", "", board_name or "", flags=re.IGNORECASE)


def build_sab_index(directory_rows: list[dict]) -> dict[str, str]:
    """`_sab_key` of a board's place -> its official name, England only.

    England only because the campaign is England-wide and a Welsh or Scottish
    board sharing a place word ("Cardiff", "Highland") would otherwise
    resolve an English SAR to the wrong nation's body.
    """
    index: dict[str, str] = {}
    for row in directory_rows:
        if row.get("nation") != "England":
            continue
        official = row["name"]
        for key in (_sab_key(official), _sab_key(_place_of(official))):
            if key:
                index.setdefault(key, official)
    return index


def resolve_sab_name(body_text: str | None, title: str | None,
                      sab_index: dict[str, str]) -> tuple[str | None, str | None]:
    """(sab_name, source) for one SAR, resolved in layers strongest first.

    An empty `sab_index` (the directory fetch failed) degrades to the 0057
    behaviour: opening-window text only, always 'document_text_unverified'.
    """
    text = body_text or ""

    def canon(name: str) -> str | None:
        return sab_index.get(_sab_key(_place_of(name))) or sab_index.get(_sab_key(name))

    # 1. The board names itself in the opening.
    head = text[:_SAB_NAME_SEARCH_CHARS]
    m = _SAB_NAME_RE.search(head) or _SAB_COMMISSIONED_RE.search(head)
    opening = _clean_sab_name(m.group(1)) if m else None
    if opening:
        return (canon(opening) or opening,
                "document_text" if canon(opening) else "document_text_unverified")

    # 2. Whole document: the board it names most often that resolves to the
    #    directory (a neighbouring board mentioned once does not), or failing
    #    that a board named four or more times.
    counts: collections.Counter = collections.Counter()
    for mm in _SAB_NAME_RE.finditer(text):
        cleaned = _clean_sab_name(mm.group(1))
        if cleaned:
            counts[cleaned] += 1
    resolved: collections.Counter = collections.Counter()
    for name, n in counts.items():
        official = canon(name)
        if official:
            resolved[official] += n
    if resolved:
        top, n = resolved.most_common(1)[0]
        if n >= 2 or len(resolved) == 1:
            return top, "document_text"
    for name, n in counts.most_common(1):
        if n >= 4:
            return name, "document_text_unverified"

    # 3. A directory board's place name sitting next to "Safeguarding" / "SAB"
    #    at least three times in the text.
    low = text.lower()
    for key, official in sab_index.items():
        if len(key) < 5 or low.count(key) < 3:
            continue
        if re.search(re.escape(key) + r"\W{0,40}(safeguarding|\bsab\b)", low):
            return official, "document_text"

    # 4. The library title carries a place that is exactly one directory board.
    toks = _sab_key(title).split()
    hits = {sab_index[" ".join(toks[i:i + j])]
            for i in range(len(toks)) for j in (5, 4, 3, 2, 1)
            if " ".join(toks[i:i + j]) in sab_index}
    if len(hits) == 1:
        return hits.pop(), "sab_directory"

    return None, None


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


def _stored_sab_index(conn) -> dict[str, str]:
    """The resolution index rebuilt from whatever the directory table
    already holds. Used when this run's fetch of the directory fails, so a
    flaky page does not undo a working set of board names."""
    rows = conn.execute(
        "SELECT name, nation, website_url FROM safeguarding_adults_boards").fetchall()
    return build_sab_index([dict(r) for r in rows])


def _collect_sab_directory(ctx: ModuleContext, module_name: str) -> dict[str, str]:
    """Fetch and store the Ann Craft Trust board directory; return the
    resolution index. A failure here is not fatal — resolution falls back to
    the directory rows already stored, or runs without a canonical list."""
    conn = ctx.conn
    with PipelineHTTPClient(SOURCE_SAB_DIRECTORY, settings=ctx.settings, conn=conn) as client:
        try:
            page = client.get(SAB_DIRECTORY_URL)
        except RobotsDisallowed:
            db.record_review_item(conn, module_name, "sab_directory_robots_disallowed",
                                   SAB_DIRECTORY_URL, json.dumps({}))
            return _stored_sab_index(conn)
        except httpx.HTTPError as exc:
            # A third-party page being down or slow is not a reason to abandon
            # the whole SAR run — fall back to the directory rows already stored.
            db.record_review_item(conn, module_name, "sab_directory_unavailable",
                                   SAB_DIRECTORY_URL,
                                   json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
            return _stored_sab_index(conn)
        if not page.ok:
            db.record_review_item(conn, module_name, "sab_directory_unavailable",
                                   SAB_DIRECTORY_URL, json.dumps({"status": page.status_code}))
            return _stored_sab_index(conn)

        boards = parse_sab_directory(page.body.decode("utf-8", "replace"))
        if not boards:
            db.record_parse_failure(
                conn, module_name, "sab_directory", SAB_DIRECTORY_URL,
                "no board entries recognised on the directory page; its markup "
                "may have changed", source_url=SAB_DIRECTORY_URL)
            return _stored_sab_index(conn)

        provenance = {
            "source_url": page.url,
            "retrieved_at": page.retrieved_at.isoformat(),
            "http_status": page.status_code,
            "source_system": SOURCE_SAB_DIRECTORY,
            "payload_sha256": page.payload_sha256,
        }
        for board in boards:
            db.upsert(conn, "safeguarding_adults_boards", {
                "name": board["name"],
                "nation": board["nation"],
                "website_url": board["website_url"],
                **provenance,
            }, natural_key=["name"])
        if not ctx.dry_run:
            conn.commit()
        log.info("sar.sab_directory", boards=len(boards))
        return build_sab_index(boards)


def _reresolve_missing_sab_names(ctx: ModuleContext, sab_index: dict[str, str]) -> int:
    """Re-run sab_name resolution over already-archived text for documents
    that still have none. No re-fetch: this is what lets the resolver
    improve and every existing row catch up on the next plain run."""
    conn = ctx.conn
    pending = conn.execute(
        "SELECT d.document_url, p.title_raw, t.body_text "
        "FROM sar_documents d "
        "JOIN restricted_sar_report_text t ON t.document_url = d.document_url "
        "LEFT JOIN restricted_sar_persons p ON p.document_url = d.document_url "
        "WHERE d.sab_name IS NULL AND d.has_body_text = 1"
    ).fetchall()
    healed = 0
    for row in pending:
        name, source = resolve_sab_name(row["body_text"], row["title_raw"], sab_index)
        if not name:
            continue
        conn.execute(
            "UPDATE sar_documents SET sab_name = ?, sab_name_source = ? WHERE document_url = ?",
            (name, source, row["document_url"]))
        healed += 1
    if healed and not ctx.dry_run:
        conn.commit()
    return healed


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

    ctx.phase("reading the Safeguarding Adults Board directory")
    sab_index = _collect_sab_directory(ctx, module_name)

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

        # The SCIE 2015-2018 collection, folded in. Its own failure is a
        # review item, not a reason to abandon the main library.
        ctx.phase("reading the SCIE 2015-2018 collection")
        try:
            scie = client.get(SCIE_LIBRARY_URL)
            if scie.ok:
                scie_rows = parse_scie_library_page(scie.body.decode("utf-8", "replace"))
                if scie_rows:
                    rows = rows + scie_rows
                else:
                    db.record_parse_failure(
                        conn, module_name, "listing", SCIE_LIBRARY_URL,
                        "the SCIE collection page returned no recognisable rows",
                        source_url=SCIE_LIBRARY_URL)
            else:
                db.record_review_item(conn, module_name, "sar_library_unavailable",
                                       SCIE_LIBRARY_URL,
                                       json.dumps({"status": scie.status_code}))
        except RobotsDisallowed:
            db.record_review_item(conn, module_name, "sar_library_robots_disallowed",
                                   SCIE_LIBRARY_URL, json.dumps({}))
        if not ctx.dry_run:
            conn.commit()

        # Two libraries can list the same document; the resolved URL is the
        # natural key, so keep the first occurrence of each.
        seen_urls: set[str] = set()
        deduped: list[dict] = []
        for row in rows:
            url = resolve_document_url(row["href"], row.get("base", LIBRARY_URL))
            if url in seen_urls:
                continue
            seen_urls.add(url)
            deduped.append(row)
        rows = deduped

        for row in ctx.track(rows, "SAR library entries"):
            if ctx.limit and documents_written >= ctx.limit:
                break

            document_url = resolve_document_url(row["href"], row.get("base", LIBRARY_URL))
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

            sab_name, sab_source = resolve_sab_name(body_text, row["title"], sab_index)
            if body_text and not sab_name:
                db.record_parse_failure(
                    conn, module_name, "sab_name", document_url,
                    "no board name found in the document's text, the directory, "
                    "or the library title", source_url=document_url)

            db.upsert(conn, "sar_documents", {
                "document_url": document_url,
                "document_ext": ext,
                "library_year": row["library_year"],
                "sab_name": sab_name,
                "sab_name_source": sab_source,
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

    ctx.phase("resolving board names for documents already read")
    healed = _reresolve_missing_sab_names(ctx, sab_index)

    log.info("sar.run_complete", documents=documents_written, texts_read=texts_read,
              provider_mentions=provider_mentions, sab_names_backfilled=healed)
