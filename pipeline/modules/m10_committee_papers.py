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
from datetime import datetime, timezone
from urllib.parse import quote, urljoin, urlparse

import structlog

from pipeline import db
from pipeline.authority_websites import (
    COMMITTEE_LINK_SIGNATURES,
    SYSTEM_SIGNATURES,
    website_for,
)
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.keywords import COMMITTEE_SEARCH_TERMS
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


def _resolve_committee_url(client, conn, module_name: str, authority, site) -> tuple[str | None, str]:
    """(committee_url, url_source).

    Registry first. Failing that, read the council's own home page and take
    any committee-system link it publishes — the caller then probes it, so a
    link that does not answer is not accepted.
    """
    if site is not None and site.committee_url:
        return site.committee_url, "registry"
    if site is None or not site.base_url:
        return None, "none"

    try:
        result = client.get(site.base_url)
    except RobotsDisallowed:
        db.record_review_item(conn, module_name, "committee_homepage_robots_disallowed",
                               site.base_url, json.dumps({"authority": authority["name"]}))
        return None, "none"
    if not result.ok:
        db.record_review_item(
            conn, module_name, "committee_homepage_unavailable", site.base_url,
            json.dumps({"authority": authority["name"], "status": result.status_code}))
        return None, "none"

    links = committee_links_on_page(result.body.decode("utf-8", errors="replace"), result.url)
    if not links:
        return None, "none"
    return links[0], "homepage_link"


def _search_moderngov(client, conn, module_name: str, authority, committee_url: str,
                       system: str, dry_run: bool) -> tuple[int, bool, bool]:
    """(distinct_candidates, searched_cleanly, any_page_unreadable).

    Counted as distinct documents, not upserts: one paper is routinely found
    by three of the six search terms, and reporting 600 where the table holds
    191 is the kind of number that ends up in a campaign document.
    """
    documents: set[str] = set()
    searched_cleanly = True
    unreadable = False

    for term in COMMITTEE_SEARCH_TERMS:
        url = build_moderngov_search_url(committee_url, term)
        for _page in range(MAX_RESULT_PAGES):
            try:
                result = client.get(url)
            except RobotsDisallowed:
                db.record_review_item(conn, module_name, "committee_search_robots_disallowed",
                                       url, json.dumps({"authority": authority["name"]}))
                searched_cleanly = False
                break
            if not result.ok:
                # 403 is common: several councils sit behind bot protection
                # that refuses this User-Agent. Recorded, because a blocked
                # council must not look like a council with nothing to find.
                db.record_review_item(
                    conn, module_name, "committee_search_blocked", url,
                    json.dumps({"authority": authority["name"], "term": term,
                                 "status": result.status_code}))
                searched_cleanly = False
                break

            page_html = result.body.decode("utf-8", errors="replace")
            rows = parse_moderngov_results(page_html, result.url, term)

            if not rows and not has_no_results(page_html):
                # Neither hits nor ModernGov's own "no results" message: the
                # page is not the shape this adapter understands, and saying
                # so is the whole point of the check.
                db.record_review_item(
                    conn, module_name, "moderngov_results_unrecognised", result.url,
                    json.dumps({"authority": authority["name"], "term": term,
                                 "note": "page carried neither result blocks nor a "
                                          "'No results found' message"}))
                unreadable = True
                break

            provenance = _provenance(result)
            for row in rows:
                snippet = row.pop("snippet", None)
                meeting_date_raw = row.pop("meeting_date_raw", None)
                term_found = row.pop("matched_term")
                if meeting_date_raw and row["meeting_date"] is None:
                    db.record_parse_failure(
                        conn, module_name, "meeting_date", meeting_date_raw,
                        "meeting heading date is not DD/MM/YYYY", source_url=result.url)

                terms = merge_matched_terms(
                    conn, authority["ons_code"], row["document_url"], term_found)
                db.upsert(conn, "committee_paper_candidates", {
                    "authority_ons_code": authority["ons_code"],
                    **row,
                    "matched_terms": terms,
                    "committee_system": system,
                    "verified": 0,
                    "verified_at": None,
                    "rejected": 0,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    **provenance,
                }, natural_key=["authority_ons_code", "document_url"])
                documents.add(row["document_url"])

                if snippet:
                    db.upsert(conn, "restricted_committee_result_snippets", {
                        "authority_ons_code": authority["ons_code"],
                        "document_url": row["document_url"],
                        "matched_term": term,
                        "snippet_text": snippet,
                        **provenance,
                    }, natural_key=["authority_ons_code", "document_url", "matched_term"])

            following = next_result_page_url(page_html, result.url)
            if not following:
                break
            url = following

        if not dry_run:
            conn.commit()

    return len(documents), searched_cleanly, unreadable


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

    searched = 0
    unconfigured = 0
    unknown_system = 0
    discovered = 0
    candidates = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for authority in authorities:
            site = website_for(authority["ons_code"], conn)
            committee_url, url_source = _resolve_committee_url(
                client, conn, module_name, authority, site)

            if not committee_url:
                db.record_review_item(
                    conn, module_name, "committee_url_unknown", authority["ons_code"],
                    json.dumps({"authority": authority["name"],
                                 "note": "no verified entry in pipeline/authority_websites.py "
                                          "and no committee-system link on the council's home "
                                          "page; add a verified committee_url"}))
                unconfigured += 1
                continue

            if url_source == "homepage_link":
                discovered += 1

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
                "url_source": url_source,
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
            written, searched_cleanly, unreadable = _search_moderngov(
                client, conn, module_name, authority, committee_url, system, ctx.dry_run)
            candidates += written

            if written == 0 and searched_cleanly and not unreadable:
                # Every term returned ModernGov's own "no results" message.
                # Worth recording as a fact about the council rather than
                # leaving it as an absence indistinguishable from a failure.
                db.record_review_item(
                    conn, module_name, "committee_search_no_matches", authority["ons_code"],
                    json.dumps({"authority": authority["name"],
                                 "committee_url": committee_url,
                                 "terms": COMMITTEE_SEARCH_TERMS,
                                 "note": "search ran and the system reported no matches "
                                          "for any term"}))

            if not ctx.dry_run:
                conn.commit()

    log.info("committee.run_complete", authorities_searched=searched,
              authorities_unconfigured=unconfigured, unsupported_systems=unknown_system,
              committee_urls_discovered=discovered, candidates=candidates)
