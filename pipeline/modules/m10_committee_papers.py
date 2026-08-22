"""Module 10 — Council committee papers (semi-automated).

One adapter per committee system, plus a null adapter that records the
authority for review rather than pretending to have searched it. The system
is detected from path signatures on the authority's committee URL, not
assumed: 'unknown' is a real answer that this module records.

Search terms come from pipeline/keywords.COMMITTEE_SEARCH_TERMS, and results
are candidates only. A ModernGov search hit means a document's title or text
matched a phrase — "TUPE" or "public health grant" appear in plenty of papers
that have nothing to do with drug and alcohol services — so nothing is
promoted to committee_papers without a human confirming it.

## The ModernGov adapter

This module previously recorded that ModernGov's document search "needs a
POST carrying ASP.NET viewstate". That was wrong, and it was wrong in the way
this project is supposed to guard against: it was inferred from two failing
GETs rather than checked against the form. The form at /ieDocSearch.aspx has
no __VIEWSTATE field at all. It posts to /ieSearchResults.aspx, which
immediately redirects to **/ieSearchResults2.aspx with everything in the query
string** — and that URL answers a plain GET:

    {committee_url}/ieSearchResults2.aspx?SS={term}&DT=3&ADV=0&CA=false&SB=true&PG={page}

The paths the old code tried (/mgSearchResults.aspx, /mgDocumentSearch.aspx)
are not the document search; they 302 to mgError.aspx on every ModernGov
instance tested. Verified against three live councils on 2026-08-11: Kent,
Kirklees and Darlington.

The second bug was in the parser. ModernGov search hits are not links to
files: they are links to `ieListDocuments.aspx?CId=&MID=#AI…` (an agenda item)
and `mgIssueHistoryHome.aspx?IId=` (a key issue). The old parser kept only
hrefs ending in .pdf/.doc, so even a successful search produced nothing. Two
independent faults, both of which looked like "this council publishes nothing
about drug and alcohol services".

Results are read structurally rather than as a bag of links: each hit is one
`<hr />`-delimited block carrying its own match quality, a meeting or issue
header, zero or more agenda items, and the matched text. A block's agenda
items are emitted in preference to the meeting itself, because the item URL is
the more specific record and the meeting URL is its prefix.

One candidate row is one document, not one document per search term: the row
exists for a human to verify, and verifying the same PDF three times because
three terms found it is more work rather than better evidence. Which terms
agreed is still evidence, so they accumulate in `matched_terms`.

## Coverage

Bounded by the committee URL, which cannot be derived. Three sources, in
precedence order:

  1. pipeline/authority_websites.py — confirmed by request against the exact
     paths this module uses.
  2. A link on the council's own home page pointing at a committee-system
     path, where the target then answers a ModernGov signature path. Two
     confirmations from the source itself. Recorded with url_source =
     'homepage_link' so it is distinguishable from a hand-verified entry.
  3. Nothing — recorded as 'committee_url_unknown' in review_queue.

Councils that link their committee system only from a second-level navigation
page are not found by (2), which is a real limit and not a silent one: they
land in (3) and are countable.

## Personal data

ModernGov prints the matched text under each hit, and it routinely names
officers ("Presented by <name>, Head of Health Improvement"). That is the most
useful field for a reviewer and the least publishable, so it goes to
restricted_committee_result_snippets and never to committee_paper_candidates,
which is exportable.
"""
from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse

import structlog

from pipeline import db
from pipeline.authority_websites import (
    COMMITTEE_LINK_SIGNATURES,
    detect_committee_system,
    website_for,
)
from pipeline.http import RobotsDisallowed
from pipeline.keywords import COMMITTEE_SEARCH_TERMS
from pipeline.parallel import fetch_in_parallel, worker_count
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "council_committee_systems"

# ModernGov paginates ten hits to a page. Three pages per term is 30 hits,
# which is already more than a human will triage per council per term; the
# limit is here so a common word cannot turn one authority into a hundred
# requests at one every two seconds.
MAX_RESULT_PAGES = 3

_TAG_RE = re.compile(r"<[^>]+>")
_HR_RE = re.compile(r"<hr\s*/?>", re.IGNORECASE)
_TITLE_P_RE = re.compile(r'<p[^>]*class="mgAiTitleTxt"[^>]*>(.*?)</p>', re.IGNORECASE | re.DOTALL)
_BULLET_RE = re.compile(r'<ul[^>]*class="mgBulletList"[^>]*>(.*?)</ul>', re.IGNORECASE | re.DOTALL)
_WORD_PARA_RE = re.compile(r'<div[^>]*class="mgWordPara"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_QUALITY_RE = re.compile(r'alt="(Excellent|Good|Average) match"', re.IGNORECASE)
_NO_RESULTS_RE = re.compile(r"No results found for your query", re.IGNORECASE)
_RESULT_COUNT_RE = re.compile(r"Results\s+(\d+)\s+to\s+(\d+)\s+for your search", re.IGNORECASE)
_NEXT_PAGE_RE = re.compile(
    r'<a[^>]*href="([^"]+)"[^>]*title="Next page of search results"', re.IGNORECASE)

# "20/01/2022 - Health Reform and Public Health Cabinet Committee" and
# "08/02/2011, 10:00 - Safer Stronger Communities Partnership Board".
_MEETING_HEADING_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})(?:,\s*\d{1,2}:\d{2})?\s*[-–]\s*(.+)$")
# ModernGov appends the number of matches in the record: "… Committee (3)".
_MATCH_COUNT_SUFFIX_RE = re.compile(r"\s*\(\d+\)\s*$")

DOCUMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".odt")


def _text(raw: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(_TAG_RE.sub(" ", raw or ""))).strip()


def committee_links_on_page(page_html: str, page_url: str) -> list[str]:
    """Committee-system URLs a council links from its own page.

    Only the roots are returned, deduplicated: a link to
    democracy.example.gov.uk/ieDocHome.aspx yields
    https://democracy.example.gov.uk. The caller still has to probe it — a
    link is a claim by the council, and this module verifies claims.
    """
    roots: list[str] = []
    seen: set[str] = set()
    for href, _text_ in _LINK_RE.findall(page_html or ""):
        candidate = html_lib.unescape(href.strip())
        if not any(signature in candidate.lower() for signature in COMMITTEE_LINK_SIGNATURES):
            continue
        absolute = urljoin(page_url, candidate)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            continue
        # Keep any path prefix before the signature: some councils mount
        # ModernGov under a subdirectory (…/moderngov/ieDocHome.aspx).
        directory = parsed.path.rsplit("/", 1)[0]
        root = f"{parsed.scheme}://{parsed.netloc}{directory}".rstrip("/")
        if root not in seen:
            seen.add(root)
            roots.append(root)
    return roots


def build_moderngov_search_url(committee_url: str, term: str, page: int = 1) -> str:
    """ModernGov's document search results, as a GET.

    DT=3 is the DocType the search form itself submits (all published
    documents); ADV=0 is the non-advanced form; CA=false excludes cancelled
    meetings; SB=true sorts by best match, which is what makes match_quality
    meaningful. These are the form's own hidden defaults, not tuning.
    """
    base = committee_url.rstrip("/") + "/"
    query = (f"ieSearchResults2.aspx?SS={quote(term)}&DT=3&ADV=0"
              f"&CA=false&SB=true&PG={page}")
    return urljoin(base, query)


def next_result_page_url(page_html: str, page_url: str) -> str | None:
    match = _NEXT_PAGE_RE.search(page_html or "")
    if not match:
        return None
    return urljoin(page_url, html_lib.unescape(match.group(1)))


def has_no_results(page_html: str) -> bool:
    """True when ModernGov states there were no matches.

    This is the difference between "searched and found nothing" and "could not
    search", and the page says which. Without it, a broken adapter and an
    empty council look identical.
    """
    return bool(_NO_RESULTS_RE.search(page_html or ""))


# ModernGov labels each hit with the kind of record it matched. Kent prints
# "Issue:" where Kirklees prints "Key issue:", so the labels are normalised to
# a shared vocabulary rather than stored verbatim — but an unrecognised label
# is kept as itself, not flattened to 'other', because a new record type is
# something to notice rather than something to discard.
_KNOWN_LABELS = {
    "meeting": "meeting",
    "issue": "key_issue",
    "key issue": "key_issue",
    "decision": "decision",
    "document": "document",
}


def _classify(prefix: str, title: str) -> str:
    label = prefix.strip().rstrip(":").strip().lower()
    if label in _KNOWN_LABELS:
        return _KNOWN_LABELS[label]
    # An item number ("183.", "Item5") is not a record type.
    if label and not re.fullmatch(r"(item\s*)?[\d.\s]+", label):
        return re.sub(r"[^a-z0-9]+", "_", label).strip("_")[:40] or "other"
    if _MEETING_HEADING_RE.match(title):
        return "meeting"
    return "other"


def _split_heading(title: str) -> tuple[str | None, str | None, str]:
    """(meeting_date_raw, committee_name, cleaned_title)."""
    cleaned = _MATCH_COUNT_SUFFIX_RE.sub("", title).strip()
    match = _MEETING_HEADING_RE.match(cleaned)
    if match:
        return match.group(1), match.group(2).strip(), cleaned
    return None, None, cleaned


def _iso_date(raw: str | None) -> str | None:
    """ModernGov prints DD/MM/YYYY. Reformatting that is not inference; a
    value that does not parse returns None so the caller can log it rather
    than store a guess.
    """
    if not raw:
        return None
    parts = raw.split("/")
    if len(parts) != 3:
        return None
    day, month, year = (p.strip() for p in parts)
    if not (day.isdigit() and month.isdigit() and year.isdigit()):
        return None
    try:
        from datetime import date

        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _first_link(fragment: str) -> tuple[str, str, str] | None:
    """(href, link_text, text_before_the_link) for the first anchor."""
    match = _LINK_RE.search(fragment)
    if not match:
        return None
    prefix = _text(fragment[:match.start()])
    return (html_lib.unescape(match.group(1).strip()),
            _text(match.group(2)),
            prefix.rstrip(":").strip())


def parse_moderngov_results(page_html: str, page_url: str, term: str) -> list[dict]:
    """Candidate rows from one ModernGov results page.

    Each `<hr />`-delimited block is one hit. Within a block the most specific
    linked records win: agenda items and attached documents are emitted in
    preference to the meeting that contains them, because the meeting URL is
    just their prefix and a reviewer opening it would have to find the item
    again by hand.
    """
    out: list[dict] = []
    seen: set[str] = set()

    for block in _HR_RE.split(page_html or ""):
        if "mgAiTitleTxt" not in block:
            continue

        paragraphs = _TITLE_P_RE.findall(block)
        if not paragraphs:
            continue

        header = _first_link(paragraphs[0])
        if header is None:
            continue
        header_href, header_title, header_prefix = header

        quality_match = _QUALITY_RE.search(block)
        match_quality = quality_match.group(1).lower() if quality_match else None

        result_type = _classify(header_prefix, header_title)
        meeting_date_raw, committee_name, report_title = _split_heading(header_title)

        snippet_match = _WORD_PARA_RE.search(block)
        snippet = _text(snippet_match.group(1)) if snippet_match else None

        common = {
            "committee_name": committee_name,
            "meeting_date_raw": meeting_date_raw,
            "meeting_date": _iso_date(meeting_date_raw),
            "report_title": report_title[:300] or None,
            "match_quality": match_quality,
            "matched_term": term,
            "snippet": snippet,
        }

        rows: list[dict] = []

        for paragraph in paragraphs[1:]:
            item = _first_link(paragraph)
            if item is None:
                continue
            item_href, item_title, item_prefix = item
            rows.append({**common,
                          "document_url": urljoin(page_url, item_href),
                          "agenda_item_title": item_title[:300] or None,
                          "item_reference": item_prefix or None,
                          "result_type": "agenda_item"})

        # The bullet list under a meeting header is its attached documents.
        # ModernGov links most of them through a viewer rather than by file
        # extension, so the type is taken from the list they are in, not from
        # the URL — but a direct file link is still worth marking as one.
        for bullet in _BULLET_RE.findall(block):
            for href, link_text in _LINK_RE.findall(bullet):
                url = urljoin(page_url, html_lib.unescape(href.strip()))
                path = url.lower().split("?")[0]
                rows.append({**common,
                              "document_url": url,
                              "agenda_item_title": _text(link_text)[:300] or None,
                              "item_reference": None,
                              "result_type": "file"
                                  if path.endswith(DOCUMENT_EXTENSIONS) else "document"})

        if not rows:
            rows.append({**common,
                          "document_url": urljoin(page_url, header_href),
                          "agenda_item_title": None,
                          "item_reference": None,
                          "result_type": result_type})

        for row in rows:
            if row["document_url"] in seen:
                continue
            seen.add(row["document_url"])
            out.append(row)

    return out


def merge_matched_terms(conn, ons_code: str, document_url: str, term: str) -> str:
    """The full set of search terms that have found this document, sorted.

    A candidate row is one document, because the row exists for a human to
    verify and verifying the same PDF once per matching term is more work
    rather than better evidence. But which terms agreed is itself evidence, so
    they accumulate here instead of the last one overwriting the rest.
    """
    row = conn.execute(
        "SELECT matched_terms FROM committee_paper_candidates "
        "WHERE authority_ons_code = ? AND document_url = ?", (ons_code, document_url)).fetchone()
    existing = (row["matched_terms"] or "") if row else ""
    terms = {part.strip() for part in existing.split(",") if part.strip()}
    terms.add(term)
    return ", ".join(sorted(terms))


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


@dataclass
class AuthorityFindings:
    """Everything one authority's fetching produced, and nothing written yet.

    Workers run on a thread pool and must not touch the module's connection,
    so what they would have written is carried back here and written by the
    main thread. That is not only a threading concession: it separates what
    the source said from what we recorded, which is the distinction this
    pipeline is organised around anyway.
    """

    ons_code: str
    name: str
    committee_url: str | None = None
    url_source: str = "none"
    system: str = "unknown"
    signature: str | None = None
    candidates: list[dict] = field(default_factory=list)
    review_items: list[tuple[str, str, dict]] = field(default_factory=list)
    parse_failures: list[tuple[str, str, str, str]] = field(default_factory=list)
    searched: bool = False
    searched_cleanly: bool = True
    unreadable: bool = False

    def flag(self, item_type: str, raw_value: str, context: dict) -> None:
        self.review_items.append((item_type, raw_value, context))


def _discover_committee_url(client, findings: AuthorityFindings, site) -> None:
    """Registry first, then a committee-system link on the council's own home
    page. The caller probes whatever comes back, so a link that does not
    answer is not accepted.
    """
    if site is not None and site.committee_url:
        # Say which kind of answer it was. Labelling a reviewer's confirmed
        # URL 'registry' would make `url_source` — the column that exists to
        # record how much confidence an entry has earned — a lie.
        findings.committee_url = site.committee_url
        findings.url_source = "human_verified" if site.source == "human_verified" else "registry"
        return
    if site is None or not site.base_url:
        return

    try:
        result = client.get(site.base_url)
    except RobotsDisallowed:
        findings.flag("committee_homepage_robots_disallowed", site.base_url,
                       {"authority": findings.name})
        return
    if not result.ok:
        findings.flag("committee_homepage_unavailable", site.base_url,
                       {"authority": findings.name, "status": result.status_code})
        return

    links = committee_links_on_page(result.body.decode("utf-8", errors="replace"), result.url)
    if links:
        findings.committee_url, findings.url_source = links[0], "homepage_link"


def _search_moderngov(client, findings: AuthorityFindings) -> None:
    """Every configured term against one ModernGov instance.

    Fetches and parses only. Candidates carry the term that found them and
    their snippet; the main thread merges terms across candidates and splits
    the snippet off to the restricted table.
    """
    committee_url = findings.committee_url
    assert committee_url is not None

    for term in COMMITTEE_SEARCH_TERMS:
        url = build_moderngov_search_url(committee_url, term)
        for _page in range(MAX_RESULT_PAGES):
            try:
                result = client.get(url)
            except RobotsDisallowed:
                findings.flag("committee_search_robots_disallowed", url,
                               {"authority": findings.name})
                findings.searched_cleanly = False
                break
            if not result.ok:
                # 403 is common: several councils sit behind bot protection
                # that refuses this User-Agent. Recorded, because a blocked
                # council must not look like a council with nothing to find.
                findings.flag("committee_search_blocked", url,
                               {"authority": findings.name, "term": term,
                                "status": result.status_code})
                findings.searched_cleanly = False
                break

            page_html = result.body.decode("utf-8", errors="replace")
            rows = parse_moderngov_results(page_html, result.url, term)

            if not rows and not has_no_results(page_html):
                # Neither hits nor ModernGov's own no-results message: the
                # page is not the shape this adapter understands, and saying
                # so is the whole point of the check.
                findings.flag("moderngov_results_unrecognised", result.url,
                               {"authority": findings.name, "term": term,
                                "note": "page carried neither result blocks nor a "
                                         "no-results message"})
                findings.unreadable = True
                break

            provenance = _provenance(result)
            for row in rows:
                meeting_date_raw = row.pop("meeting_date_raw", None)
                if meeting_date_raw and row["meeting_date"] is None:
                    findings.parse_failures.append(
                        ("meeting_date", meeting_date_raw,
                         "meeting heading date is not DD/MM/YYYY", result.url))
                findings.candidates.append({**row, **provenance})

            following = next_result_page_url(page_html, result.url)
            if not following:
                break
            url = following


# --- The CMIS adapter -------------------------------------------------------------
#
# CMIS is the second committee system this module can search, added
# 2026-08-22 after being flagged 'committee_system_unsupported' for months.
# Verified live against three unrelated installs that day -- Derby
# (democracy.derby.gov.uk, no path prefix), Nottinghamshire
# (nottinghamshire.gov.uk/dms/, under the council's own domain) and
# Harborough (cmis.harborough.gov.uk/cmis5/, the standalone layout the old
# signature already recognised). All three are DNN-hosted ASP.NET WebForms
# apps sharing one detail that matters: unlike ModernGov, the search form
# genuinely does carry __VIEWSTATE and __EVENTVALIDATION, so a plain GET
# cannot answer it. Every field this adapter posts is read off the page that
# came back, never hardcoded -- the DNN control id (ctr424 on all three
# installs checked) is treated as an artefact of those three sites, not a
# constant, and the same goes for the pager's own control name.
#
# CMIS shows no matched-text snippet under a hit (unlike ModernGov's
# mgWordPara), so there is nothing here that needs the restricted table.

_CMIS_HIDDEN_NAMES = ("__EVENTTARGET", "__EVENTARGUMENT", "__LASTFOCUS",
                       "__VIEWSTATE", "__VIEWSTATEGENERATOR",
                       "__VIEWSTATEENCRYPTED", "__EVENTVALIDATION")

_CMIS_MONTHS = {name: i for i, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}


def _cmis_hidden_value(page_html: str, name: str) -> str:
    match = re.search(rf'name="{re.escape(name)}"[^>]*value="([^"]*)"', page_html or "")
    return html_lib.unescape(match.group(1)) if match else ""


def harvest_cmis_postback_fields(page_html: str) -> dict[str, str]:
    """The hidden fields every CMIS postback must carry, read off whatever
    page produced them. A fresh __VIEWSTATE accompanies every response and
    the one from the previous request is invalid on the next -- this must be
    called again against each new response, never reused.
    """
    return {name: _cmis_hidden_value(page_html, name) for name in _CMIS_HIDDEN_NAMES}


def find_cmis_search_fields(page_html: str) -> dict[str, str] | None:
    """This install's DNN control names for the search form, or None if
    `page_html` does not carry the fields this adapter expects at all.

    The control id is not assumed to be universal (see module note above) --
    it is read from the field names themselves, the same way a document URL
    is read from a link rather than constructed.
    """
    search_for = re.search(r'name="([\w$]+SimpleSearchFor)"', page_html or "")
    selector = re.search(r'name="([\w$]+SimpleSearchSelector)"', page_html or "")
    submit = re.search(r'name="([\w$]+SimpleSearchSubmit)"', page_html or "")
    if not (search_for and selector and submit):
        return None
    return {"search_for": search_for.group(1), "selector": selector.group(1),
            "submit": submit.group(1)}


def build_cmis_search_data(page_html: str, term: str) -> dict[str, str] | None:
    """POST body for a first-page CMIS document search, or None if
    `page_html` is not a CMIS search form this module recognises.

    __EVENTTARGET is set to the submit control's own name: that is what the
    form's onclick handler (WebForm_DoPostBackWithOptions) does before
    submitting, in place of the plain click a JS-free browser would send, so
    replicating the click means replicating that override rather than
    including the button as a normal field.
    """
    fields = find_cmis_search_fields(page_html)
    if fields is None:
        return None
    data = harvest_cmis_postback_fields(page_html)
    data["__EVENTTARGET"] = fields["submit"]
    data[fields["search_for"]] = term
    data[fields["selector"]] = "documents"
    return data


_CMIS_PAGER_TARGET_RE = re.compile(r"__doPostBack\('([^']+grdDocuments)','Page\$(\d+)'\)")


def cmis_pager_targets(page_html: str) -> dict[int, str]:
    """{page_number: grid_control_name} for every page link CMIS printed in
    its own pager row. Read from the page rather than derived from the
    search fields, the same discipline this module already applies to
    ModernGov's next-page link -- and the only page numbers present are the
    ones CMIS is actually offering, so an absent page number means there is
    no next page rather than something to construct.
    """
    return {int(page): name for name, page in _CMIS_PAGER_TARGET_RE.findall(page_html or "")}


def build_cmis_page_data(page_html: str, page: int) -> dict[str, str] | None:
    """POST body for page `page` of the current CMIS result set, built from
    the *previous response* -- each response carries the only viewstate its
    own next postback will accept. None means CMIS did not offer this page
    (either there is no pager at all, or it stopped short of `page`).
    """
    grid_name = cmis_pager_targets(page_html).get(page)
    if grid_name is None:
        return None
    data = harvest_cmis_postback_fields(page_html)
    data["__EVENTTARGET"] = grid_name
    data["__EVENTARGUMENT"] = f"Page${page}"
    return data


_CMIS_NO_RESULTS_RE = re.compile(r"pnlNoResults|produced no results", re.IGNORECASE)


def has_cmis_no_results(page_html: str) -> bool:
    """True when CMIS states there were no matches -- the difference between
    "searched and found nothing" and "could not search", same as ModernGov's
    has_no_results.
    """
    return bool(_CMIS_NO_RESULTS_RE.search(page_html or ""))


def _cmis_iso_date(raw: str | None) -> str | None:
    """CMIS prints D/Mon/YYYY ('01/Sep/2026'). A value that does not parse
    returns None so the caller logs it rather than storing a guess.
    """
    if not raw:
        return None
    match = re.fullmatch(r"(\d{1,2})/([A-Za-z]{3})/(\d{4})", raw.strip())
    if not match:
        return None
    day, month_name, year = match.groups()
    month = _CMIS_MONTHS.get(month_name.title())
    if month is None:
        return None
    try:
        from datetime import date

        return date(int(year), month, int(day)).isoformat()
    except ValueError:
        return None


_CMIS_ROW_RE = re.compile(
    r'<tr class="CMIS_Grid_(?:Row|AlternatingRow)Style">(.*?)</tr>', re.DOTALL)
_CMIS_CELL_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
_CMIS_MEETING_PARENT_RE = re.compile(r"^Meeting:\s*(.+?)\s*-\s*(\d{1,2}/[A-Za-z]{3}/\d{4})$")


def parse_cmis_results(page_html: str, page_url: str, term: str) -> list[dict]:
    """Candidate rows from one CMIS results page.

    Each row of the CMIS_Grid table is one document: a hit-highlight icon,
    hit count, a title (usually linked -- a small number of hits are
    login-gated previews with no href at all, and those fall back to the
    row's meeting/folder link rather than being invented), document type,
    size, and the meeting or folder it belongs to. A row with neither link
    carries nothing citable and is skipped rather than written with a NULL
    document_url.
    """
    out: list[dict] = []
    for row_html in _CMIS_ROW_RE.findall(page_html or ""):
        cells = _CMIS_CELL_RE.findall(row_html)
        if len(cells) < 6:
            continue
        _hit_icon, _hits, document_cell, type_cell, _size_cell, parent_cell = cells[:6]

        doc_link = _first_link(document_cell)
        parent_link = _first_link(parent_cell)
        parent_text = parent_link[1] if parent_link else _text(parent_cell)

        document_url = urljoin(page_url, doc_link[0]) if doc_link else None
        if document_url is None and parent_link is not None:
            document_url = urljoin(page_url, parent_link[0])
        if document_url is None:
            continue

        title = doc_link[1] if doc_link else _text(document_cell)
        meeting_match = _CMIS_MEETING_PARENT_RE.match(parent_text)
        committee_name = meeting_match.group(1) if meeting_match else None
        meeting_date_raw = meeting_match.group(2) if meeting_match else None

        out.append({
            "document_url": document_url,
            "agenda_item_title": None,
            "item_reference": None,
            "committee_name": committee_name,
            "meeting_date_raw": meeting_date_raw,
            "meeting_date": _cmis_iso_date(meeting_date_raw),
            "report_title": (title or "")[:300] or None,
            "match_quality": None,
            "matched_term": term,
            "snippet": None,
            "result_type": (_text(type_cell) or "document").lower().replace(" ", "_") or "document",
        })
    return out


def _search_cmis(client, findings: AuthorityFindings) -> None:
    """Every configured term against one CMIS instance.

    The search page is fetched fresh per term rather than once for all of
    them: a viewstate is only valid for the postback it was issued with, and
    reusing one across terms would mean the second term's request carries a
    viewstate the server has already moved past.
    """
    search_url = urljoin(findings.committee_url.rstrip("/") + "/", "Search.aspx")

    for term in COMMITTEE_SEARCH_TERMS:
        try:
            form_result = client.get(search_url)
        except RobotsDisallowed:
            findings.flag("committee_search_robots_disallowed", search_url,
                           {"authority": findings.name})
            findings.searched_cleanly = False
            break
        if not form_result.ok:
            findings.flag("committee_search_blocked", search_url,
                           {"authority": findings.name, "term": term,
                            "status": form_result.status_code})
            findings.searched_cleanly = False
            break

        form_html = form_result.body.decode("utf-8", errors="replace")
        data = build_cmis_search_data(form_html, term)
        if data is None:
            findings.flag("cmis_search_form_unrecognised", search_url,
                           {"authority": findings.name, "term": term,
                            "note": "Search.aspx did not carry the CMIS search form "
                                     "fields this module expects"})
            findings.unreadable = True
            break

        for page_number in range(1, MAX_RESULT_PAGES + 1):
            try:
                result = client.post(search_url, data=data)
            except RobotsDisallowed:
                findings.flag("committee_search_robots_disallowed", search_url,
                               {"authority": findings.name})
                findings.searched_cleanly = False
                break
            if not result.ok:
                findings.flag("committee_search_blocked", search_url,
                               {"authority": findings.name, "term": term,
                                "status": result.status_code})
                findings.searched_cleanly = False
                break

            page_html = result.body.decode("utf-8", errors="replace")
            rows = parse_cmis_results(page_html, result.url, term)

            if not rows and not has_cmis_no_results(page_html):
                findings.flag("cmis_results_unrecognised", result.url,
                               {"authority": findings.name, "term": term,
                                "note": "page carried neither a results grid nor a "
                                         "no-results message"})
                findings.unreadable = True
                break

            provenance = _provenance(result)
            for row in rows:
                meeting_date_raw = row.pop("meeting_date_raw", None)
                if meeting_date_raw and row["meeting_date"] is None:
                    findings.parse_failures.append(
                        ("meeting_date", meeting_date_raw,
                         "CMIS meeting heading date is not D/Mon/YYYY", result.url))
                findings.candidates.append({**row, **provenance})

            data = build_cmis_page_data(page_html, page_number + 1)
            if data is None:
                break


def collect_authority(unit, client) -> AuthorityFindings:
    """One authority's entire fetch workload. Runs on a pool thread."""
    authority, site = unit
    findings = AuthorityFindings(ons_code=authority["ons_code"], name=authority["name"])

    _discover_committee_url(client, findings, site)
    if not findings.committee_url:
        findings.flag("committee_url_unknown", findings.ons_code,
                       {"authority": findings.name,
                        "note": "no verified entry in pipeline/authority_websites.py "
                                 "and no committee-system link on the council's home "
                                 "page; add a verified committee_url"})
        return findings

    def probe(path: str) -> str | bool:
        try:
            result = client.get(
                urljoin(findings.committee_url.rstrip("/") + "/", path.lstrip("/")))
        except RobotsDisallowed:
            return False
        if not result.ok:
            return False
        # A marker-bearing signature needs the body to check against; a
        # bare-path one only needed the bool truthiness this string also
        # has, so one fetch serves both signature shapes.
        return result.body.decode("utf-8", errors="replace")

    findings.system, findings.signature = detect_committee_system(probe)

    if findings.system == "moderngov":
        findings.searched = True
        _search_moderngov(client, findings)
    elif findings.system == "cmis":
        findings.searched = True
        _search_cmis(client, findings)
    else:
        # Null adapter: Democracy and any other system remain unimplemented,
        # and an unknown system cannot be searched at all. Recorded rather
        # than skipped silently.
        findings.flag("committee_system_unsupported", findings.ons_code,
                       {"authority": findings.name, "system": findings.system,
                        "committee_url": findings.committee_url,
                        "note": "no adapter for this system; search manually or add one"})
        return findings

    if not findings.candidates and findings.searched_cleanly and not findings.unreadable:
        # Every term returned the system's own no-results message. Worth
        # recording as a fact about the council rather than leaving it as an
        # absence indistinguishable from a failure.
        findings.flag("committee_search_no_matches", findings.ons_code,
                       {"authority": findings.name,
                        "committee_url": findings.committee_url,
                        "terms": COMMITTEE_SEARCH_TERMS,
                        "note": "search ran and the system reported no matches for any term"})
    return findings


def write_findings(conn, module_name: str, findings: AuthorityFindings) -> int:
    """Everything one authority found, written on the module's connection.

    Single-threaded by design, so the CLI's commit-per-module and
    roll-back-on-failure semantics are exactly what they were before the
    fetching was parallelised. Returns the number of distinct documents.
    """
    for item_type, raw_value, context in findings.review_items:
        db.record_review_item(conn, module_name, item_type, raw_value, json.dumps(context))
    for field_name, raw, reason, source_url in findings.parse_failures:
        db.record_parse_failure(conn, module_name, field_name, raw, reason,
                                 source_url=source_url)

    if findings.committee_url:
        db.upsert(conn, "authority_committee_systems", {
            "ons_code": findings.ons_code,
            "committee_system": findings.system,
            "committee_url": findings.committee_url,
            "detected_by": findings.signature,
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "url_source": findings.url_source,
        }, natural_key=["ons_code"])

    documents: set[str] = set()
    for candidate in findings.candidates:
        row = dict(candidate)
        snippet = row.pop("snippet", None)
        term = row.pop("matched_term")

        db.upsert(conn, "committee_paper_candidates", {
            "authority_ons_code": findings.ons_code,
            **row,
            "matched_terms": merge_matched_terms(
                conn, findings.ons_code, row["document_url"], term),
            "committee_system": findings.system,
            # Initial values for a candidate nobody has seen yet, and
            # preserved so re-finding the link cannot un-promote it.
            "verified": 0,
            "verified_at": None,
            "rejected": 0,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }, natural_key=["authority_ons_code", "document_url"],
            preserve=db.DECISION_COLUMNS)
        documents.add(row["document_url"])

        if snippet:
            db.upsert(conn, "restricted_committee_result_snippets", {
                "authority_ons_code": findings.ons_code,
                "document_url": row["document_url"],
                "matched_term": term,
                "snippet_text": snippet,
                "source_url": row["source_url"],
                "retrieved_at": row["retrieved_at"],
                "http_status": row["http_status"],
                "source_system": row["source_system"],
                "payload_sha256": row["payload_sha256"],
            }, natural_key=["authority_ons_code", "document_url", "matched_term"])

    return len(documents)


@register_module(
    "m10_committee_papers",
    supports_since=False,
    depends_on=("m00_geography", "m15_foi",),
    depends_note="same website registry as m09; m15 supplies the home page a "
                  "committee link is discovered from",
    since_note="committee search returns whatever the system indexes now; candidates carry discovered_at",
)
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

    # website_for reads authority_foi_profiles, so it happens here on the
    # module's connection rather than inside a worker.
    units = [(authority, website_for(authority["ons_code"], conn))
             for authority in authorities]

    searched = unconfigured = unknown_system = discovered = candidates = 0
    workers = worker_count(ctx.settings, ctx.limit)

    stream = fetch_in_parallel(units, collect_authority,
                                source_system=SOURCE_SYSTEM, settings=ctx.settings,
                                max_workers=workers, cache_conn=conn)
    for outcome in ctx.track(stream, "councils", total=len(units)):
        authority, _site = outcome.unit
        if not outcome.ok:
            # One council with a broken TLS chain costs one council. Before
            # the pool, an unexpected exception aborted the whole module.
            db.record_review_item(
                conn, module_name, "committee_collection_failed", authority["ons_code"],
                json.dumps({"authority": authority["name"],
                             "error": f"{type(outcome.error).__name__}: {outcome.error}"}))
            if not ctx.dry_run:
                conn.commit()
            continue

        findings = outcome.value
        candidates += write_findings(conn, module_name, findings)

        if not findings.committee_url:
            unconfigured += 1
        elif findings.url_source == "homepage_link":
            discovered += 1
        if findings.searched:
            searched += 1
        elif findings.committee_url:
            unknown_system += 1

        if not ctx.dry_run:
            conn.commit()

    log.info("committee.run_complete", authorities_searched=searched,
              authorities_unconfigured=unconfigured, unsupported_systems=unknown_system,
              committee_urls_discovered=discovered, candidates=candidates,
              fetch_workers=workers)
