"""Safeguarding Adult Reviews, read from the National SAR Library.

The library gives no structured metadata per document -- no board name, no
date, no distribution list -- so most of what this module does is extraction
from raw HTML and from a document's own text, the same kind of work
m08_pfd_reports does against judiciary.uk. These tests mirror that file's
shape: pure-function tests against a captured shape of the source, then one
end-to-end run against a small mocked library page.
"""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest

from pipeline.exports import guard_columns
from pipeline.modules import m28_sar_reports as sar
from pipeline.registry import ModuleContext


def _build_docx(paragraphs: list[str]) -> bytes:
    """A minimal, real DOCX package -- same technique as
    tests/test_documents.py's DOCXParser coverage -- so the module's DOCX
    path is exercised against actual zip + word/document.xml bytes rather
    than a placeholder that only ever hits the failure branch.
    """
    body = "".join(
        f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>" for text in paragraphs)
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", document_xml)
    return buffer.getvalue()

# Shape of the real library page: a "SARs <year>" collapsible heading over a
# <table> of <tr><td>title</td><td><a href="...">Download</a></td></tr> rows,
# captured from nationalnetwork.org.uk/search.html.
LIBRARY_HTML = """
<div>
 <button type="button" class="collapsible">SARs 2026</button>
 <div class="content">
  <table>
   <tr>
    <td>HSAB SAR Edward report.pdf</td>
    <td> <a href="./2026/HSAB SAR Edward report.pdf"><img src="../download-button.png"> Download</a></td>
   </tr>
   <tr>
    <td>Mr B SAR Final Report</td>
    <td> <a href="./2026/MrBSARFinalReport.docx"><img src="../download-button.png"> Download</a></td>
   </tr>
  </table>
 </div>
 <button type="button" class="collapsible">SARs 2025</button>
 <div class="content">
  <table>
   <tr>
    <td>Camden Hannah</td>
    <td> <a href="./2025/Camden Hannah (1).pdf"><img src="./download-button.png"> Download</a></td>
   </tr>
  </table>
 </div>
</div>
"""

# The opening of a plausible SAR PDF's text layer.
REPORT_TEXT = """
Hertfordshire Safeguarding Adults Board
Safeguarding Adult Review: Edward

Executive summary. Edward was known to several agencies. Change Grow Live
provided his community treatment. Staffing levels on the ward were a
recurring theme and vacancy rates had been high for months.
"""

# A plausible SAR published as DOCX rather than PDF -- boards submit
# whatever file they have.
DOCX_PARAGRAPHS = [
    "Turning Point Safeguarding Adults Board",
    "Safeguarding Adult Review: Mr B",
    "Turning Point managed his care in the community. Caseload pressures "
    "were significant during the review period.",
]


# --- reading a document's text --------------------------------------------------

def test_read_docx_extracts_paragraph_text(conn):
    body = _build_docx(DOCX_PARAGRAPHS)
    text, source = sar._read_docx(
        conn, "m28_sar_reports", "https://example.org/doc.docx", SimpleNamespace(body=body))
    assert source == "docx"
    assert "Turning Point Safeguarding Adults Board" in text
    assert "Caseload pressures" in text


def test_read_docx_records_a_parse_failure_for_a_corrupt_file(conn):
    text, source = sar._read_docx(
        conn, "m28_sar_reports", "https://example.org/bad.docx",
        SimpleNamespace(body=b"not a zip archive"))
    assert text is None
    assert source is None
    failure = conn.execute(
        "SELECT reason FROM parse_failures WHERE source_url = ?",
        ("https://example.org/bad.docx",)).fetchone()
    assert "DOCX could not be opened" in failure["reason"]


# --- parsing the library page ---------------------------------------------------

def test_parse_library_page_reads_title_href_and_year():
    rows = sar.parse_library_page(LIBRARY_HTML)
    assert len(rows) == 3
    assert rows[0] == {
        "title": "HSAB SAR Edward report.pdf",
        "href": "./2026/HSAB SAR Edward report.pdf",
        "library_year": 2026,
        "base": sar.LIBRARY_URL,
    }
    assert rows[2]["library_year"] == 2025
    assert rows[2]["title"] == "Camden Hannah"


def test_parse_library_page_on_empty_html_returns_nothing():
    assert sar.parse_library_page("") == []
    assert sar.parse_library_page("<p>nothing here</p>") == []


# --- URL resolution ---------------------------------------------------------------

def test_resolve_document_url_encodes_spaces_and_ampersands():
    url = sar.resolve_document_url("./2026/HSAB & Essex SAB Daniel SAR 2026.pdf")
    assert url == (
        "https://nationalnetwork.org.uk/2026/HSAB%20%26%20Essex%20SAB%20"
        "Daniel%20SAR%202026.pdf")


def test_resolve_document_url_is_absolute_and_stable():
    url = sar.resolve_document_url("./2026/report.pdf")
    assert url == "https://nationalnetwork.org.uk/2026/report.pdf"
    # Idempotent: resolving twice must not double-encode.
    assert sar.resolve_document_url("./2026/report.pdf") == url


@pytest.mark.parametrize("href,ext", [
    ("./2026/report.pdf", ".pdf"),
    ("./2020/notes.DOCX", ".docx"),
    ("./2020/plan.odt", ".odt"),
    ("./2020/page.html", None),
])
def test_document_extension(href, ext):
    assert sar.document_extension(sar.resolve_document_url(href)) == ext


# --- board name extraction ---------------------------------------------------------

def test_extract_sab_name_reads_the_boards_own_words():
    assert sar.extract_sab_name(REPORT_TEXT) == "Hertfordshire Safeguarding Adults Board"


def test_extract_sab_name_handles_multi_word_authorities():
    text = "This review was commissioned by the Bath and North East Somerset Safeguarding Adults Board."
    assert sar.extract_sab_name(text) == "Bath and North East Somerset Safeguarding Adults Board"


def test_extract_sab_name_none_when_not_stated():
    assert sar.extract_sab_name("A review into the death of an adult in our care.") is None
    assert sar.extract_sab_name(None) is None


def test_extract_sab_name_only_searches_the_opening():
    """A board named in passing deep in the text (a neighbouring board in a
    multi-agency review) must not be picked up as the commissioning board."""
    text = "x " * 3000 + "Neighbouring Safeguarding Adults Board helped too."
    assert sar.extract_sab_name(text) is None


@pytest.mark.parametrize("text,expected", [
    # Boards that have renamed to a "Partnership" style, and the "Adult
    # Safeguarding Board" word order — all the same body.
    ("Published by the Merton Safeguarding Adults Partnership Board.",
     "Merton Safeguarding Adults Partnership Board"),
    ("A new SAR commissioned by Suffolk Safeguarding Partnership Board.",
     "Suffolk Safeguarding Partnership Board"),
    ("This review was overseen by the Camden Adult Safeguarding Board.",
     "Camden Adult Safeguarding Board"),
])
def test_extract_sab_name_accepts_partnership_and_word_order_variants(text, expected):
    assert sar.extract_sab_name(text) == expected


def test_extract_sab_name_collapses_a_line_wrapped_name():
    text = "Report of the Manchester Safeguarding\nAdults Board\n\n1. Introduction"
    assert sar.extract_sab_name(text) == "Manchester Safeguarding Adults Board"


def test_extract_sab_name_falls_back_to_the_stated_commissioner():
    """When the name is not in the strict phrase position, "commissioned by
    X" is a firmer attribution than a bare mention, so it is used."""
    text = ("Executive Summary\n\nThis Safeguarding Adults Review was "
            "commissioned by the Telford and Wrekin Safeguarding Adults "
            "Board following the death of an adult.")
    assert sar.extract_sab_name(text) == "Telford and Wrekin Safeguarding Adults Board"


# --- the SAB directory and layered resolution -------------------------------------

def test_parse_sab_directory_groups_by_nation():
    boards = sar.parse_sab_directory(SAB_DIRECTORY_HTML)
    by_name = {b["name"]: b for b in boards}
    assert by_name["Leeds Safeguarding Adults Board"]["nation"] == "England"
    assert by_name["Leeds Safeguarding Adults Board"]["website_url"] == "https://example.gov.uk/leeds-sab"
    assert by_name["Cardiff and Vale Safeguarding Board"]["nation"] == "Wales"
    # Scotland's "Adult Support and Protection" naming is recognised.
    assert by_name["Dundee Adult Support and Protection Committee"]["nation"] == "Scotland"
    # A trailing parenthetical member-authority list is dropped from the name.
    assert "Mid and West Wales Safeguarding Board" in by_name
    # The site's own nav ("What is a Safeguarding Adults Review?") is not a board.
    assert not any("What is a" in b["name"] for b in boards)


def test_build_sab_index_is_england_only_and_place_keyed():
    index = sar.build_sab_index(sar.parse_sab_directory(SAB_DIRECTORY_HTML))
    assert index["camden"] == "Camden Safeguarding Adults Partnership Board"
    assert index["leeds"] == "Leeds Safeguarding Adults Board"
    assert "cardiff and vale" not in index  # Wales excluded


_IDX = {"camden": "Camden Safeguarding Adults Partnership Board",
        "leeds": "Leeds Safeguarding Adults Board"}


def test_resolve_sab_name_canonicalises_a_text_match_to_the_directory():
    # The document says "Camden Safeguarding Adults Board"; the directory's
    # official name is the "...Partnership Board" form. The canonical wins.
    name, source = sar.resolve_sab_name(
        "This Safeguarding Adults Review was commissioned by Camden Safeguarding Adults Board.",
        "Hannah SAR.pdf", _IDX)
    assert name == "Camden Safeguarding Adults Partnership Board"
    assert source == "document_text"


def test_resolve_sab_name_falls_back_to_the_library_title():
    name, source = sar.resolve_sab_name(
        "An executive summary. No board is named anywhere in this short brief.",
        "Leeds SAR - Executive Summary - Adult K.pdf", _IDX)
    assert name == "Leeds Safeguarding Adults Board"
    assert source == "sab_directory"


def test_resolve_sab_name_keeps_an_unverified_text_name_when_not_in_the_directory():
    name, source = sar.resolve_sab_name(
        "Commissioned by the Barsetshire Safeguarding Adults Board.", "x.pdf", _IDX)
    assert name == "Barsetshire Safeguarding Adults Board"
    assert source == "document_text_unverified"


def test_resolve_sab_name_none_when_nothing_matches():
    assert sar.resolve_sab_name("Nothing here.", "Violet SAR V2.pdf", _IDX) == (None, None)


def test_directory_fetch_failure_falls_back_to_stored_boards(httpx_mock, settings, conn):
    """A flaky directory page must not wipe out a working set of board names:
    the resolution index rebuilds from safeguarding_adults_boards rows."""
    conn.execute(
        "INSERT INTO safeguarding_adults_boards (name, nation, website_url, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('Leeds Safeguarding Adults Board', 'England', 'https://x', "
        "'https://x', '2026-01-01T00:00:00Z', 200, 'test', 'h')")
    conn.commit()

    httpx_mock.add_response(url="https://www.anncrafttrust.org/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(url=sar.SAB_DIRECTORY_URL, status_code=403, text="Forbidden")

    index = sar._collect_sab_directory(
        ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None),
        "m28_sar_reports")
    assert index.get("leeds") == "Leeds Safeguarding Adults Board"


def test_parse_scie_library_page_reads_the_collection_table():
    rows = sar.parse_scie_library_page(SCIE_HTML)
    assert len(rows) == 1
    assert rows[0]["title"] == "01 Croydon Mr A Exec Summary March 2016"
    assert rows[0]["library_year"] == 2015
    assert rows[0]["base"] == sar.SCIE_LIBRARY_URL
    # Its href resolves against the SCIE directory, not search.html — the
    # bug that 404'd every SCIE document on the first attempt.
    url = sar.resolve_document_url(rows[0]["href"], rows[0]["base"])
    assert url == ("https://nationalnetwork.org.uk/SCIE%20Library%202015-2018/"
                   "01%20Croydon%20Mr%20A%20Exec%20Summary%20March%202016.pdf")


def test_run_folds_in_the_scie_collection(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _mock_aux_sources(httpx_mock, with_scie_doc=True)
    httpx_mock.add_response(url=sar.LIBRARY_URL, text=LIBRARY_HTML, is_reusable=True)
    for href in ("./2026/HSAB SAR Edward report.pdf", "./2025/Camden Hannah (1).pdf"):
        httpx_mock.add_response(url=sar.resolve_document_url(href), content=b"%PDF-1.4 fake")
    httpx_mock.add_response(url=sar.resolve_document_url("./2026/MrBSARFinalReport.docx"),
                            content=_build_docx(DOCX_PARAGRAPHS))
    scie_url = sar.resolve_document_url(
        "./01 Croydon Mr A Exec Summary March 2016.pdf", sar.SCIE_LIBRARY_URL)
    httpx_mock.add_response(url=scie_url, content=b"%PDF-1.4 fake")
    monkeypatch.setattr(sar.pdftext, "page_texts", lambda *a, **k: [REPORT_TEXT])

    sar.run(ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None))

    rows = {r["document_url"]: dict(r) for r in
            conn.execute("SELECT * FROM sar_documents").fetchall()}
    assert scie_url in rows
    assert rows[scie_url]["library_year"] == 2015
    assert conn.execute("SELECT COUNT(*) AS n FROM safeguarding_adults_boards").fetchone()["n"] == 6


# --- provider mentions --------------------------------------------------------------

def test_find_provider_mentions_matches_known_variant():
    found = sar.find_provider_mentions("Change Grow Live provided his community treatment.")
    assert ("change_grow_live", "Change Grow Live") in found


def test_find_provider_mentions_is_whole_token():
    """'Via' must not match inside an unrelated word."""
    assert sar.find_provider_mentions("He was referred via another service.") == []


def test_find_provider_mentions_empty_text():
    assert sar.find_provider_mentions("") == []


# --- concern term index -------------------------------------------------------------

def test_index_concern_terms_counts_occurrences():
    counts = sar.index_concern_terms("Staffing was short. Staffing pressures continued.")
    assert counts["staffing"] == 2
    assert "vacancy" not in counts


def test_index_concern_terms_welded_drops_word_boundary():
    assert sar.index_concern_terms("xstaffingx", welded=False) == {}
    assert sar.index_concern_terms("xstaffingx", welded=True) == {"staffing": 1}


# --- restricted tables ---------------------------------------------------------------

def test_sar_documents_is_exportable():
    guard_columns("sar_documents", ["document_url", "sab_name", "library_year"])


def test_restricted_sar_persons_is_blocked_from_export():
    with pytest.raises(ValueError, match="restricted_"):
        guard_columns("restricted_sar_persons", ["document_url", "title_raw"])


def test_restricted_sar_report_text_is_blocked_from_export():
    with pytest.raises(ValueError, match="restricted_"):
        guard_columns("restricted_sar_report_text", ["document_url", "body_text"])


# --- end to end ------------------------------------------------------------------------

def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://nationalnetwork.org.uk/robots.txt",
                             status_code=404, text="", is_reusable=True)


SAB_DIRECTORY_HTML = """
<html><body>
 <p><a href="https://www.anncrafttrust.org/x">What is a Safeguarding Adults Review?</a></p>
 <h2>England</h2>
 <ul>
  <li><a href="https://example.gov.uk/camden-sab">Camden Safeguarding Adults Partnership Board</a></li>
  <li><a href="https://example.gov.uk/herts-sab">Hertfordshire Safeguarding Adults Board</a></li>
  <li><a href="https://example.gov.uk/leeds-sab">Leeds Safeguarding Adults Board</a></li>
 </ul>
 <h2>Wales</h2>
 <ul>
  <li><a href="https://example.wales/cardiff">Cardiff and Vale Safeguarding Board</a></li>
  <li><a href="https://example.wales/mww">Mid and West Wales Safeguarding Board (Carmarthenshire, Ceredigion, Pembrokeshire, Powys)</a></li>
 </ul>
 <h2>Scotland</h2>
 <ul><li><a href="https://example.scot/dundee">Dundee Adult Support and Protection Committee</a></li></ul>
</body></html>
"""

# The SCIE page: same <table> + <button class="collapsible"> shape as the
# main library, under one "SCIE Library 2015-2018" heading, hrefs relative
# to the SCIE directory.
SCIE_HTML = """
<html><body>
 <button type="button" class="collapsible">SCIE Library 2015-2018</button>
 <div class="content">
  <table border="0">
   <tr><td> 01 Croydon Mr A Exec Summary March 2016 </td>
    <td> <a href="./01 Croydon Mr A Exec Summary March 2016.pdf"><img src="../download-button.png"> Download</a></td></tr>
  </table>
 </div>
</body></html>
"""


def _mock_aux_sources(httpx_mock, *, with_scie_doc: bool = False) -> None:
    """Mock the two sources run() now reads before the main library: the Ann
    Craft Trust board directory and the SCIE collection page."""
    httpx_mock.add_response(url="https://www.anncrafttrust.org/robots.txt",
                             status_code=404, text="", is_reusable=True)
    httpx_mock.add_response(url=sar.SAB_DIRECTORY_URL, text=SAB_DIRECTORY_HTML,
                             is_reusable=True)
    httpx_mock.add_response(url=sar.SCIE_LIBRARY_URL,
                             text=SCIE_HTML if with_scie_doc else "<html><body><h1>SCIE</h1></body></html>",
                             is_reusable=True)


def test_run_end_to_end(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _mock_aux_sources(httpx_mock)
    httpx_mock.add_response(url=sar.LIBRARY_URL, text=LIBRARY_HTML, is_reusable=True)
    edward_url = sar.resolve_document_url("./2026/HSAB SAR Edward report.pdf")
    mr_b_url = sar.resolve_document_url("./2026/MrBSARFinalReport.docx")
    hannah_url = sar.resolve_document_url("./2025/Camden Hannah (1).pdf")
    httpx_mock.add_response(url=edward_url, content=b"%PDF-1.4 fake")
    httpx_mock.add_response(url=mr_b_url, content=_build_docx(DOCX_PARAGRAPHS))
    httpx_mock.add_response(url=hannah_url, content=b"%PDF-1.4 fake")

    monkeypatch.setattr(sar.pdftext, "page_texts", lambda *a, **k: [REPORT_TEXT])

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    sar.run(ctx)

    documents = {r["document_url"]: dict(r)
                 for r in conn.execute("SELECT * FROM sar_documents").fetchall()}
    assert len(documents) == 3

    pdf_row = documents[edward_url]
    assert pdf_row["sab_name"] == "Hertfordshire Safeguarding Adults Board"
    assert pdf_row["library_year"] == 2026
    assert pdf_row["document_ext"] == ".pdf"
    assert pdf_row["has_body_text"] == 1

    docx_row = documents[mr_b_url]
    assert docx_row["document_ext"] == ".docx"
    assert docx_row["has_body_text"] == 1
    assert docx_row["sab_name"] == "Turning Point Safeguarding Adults Board"

    # The title never reaches the public table as its own field. (The
    # document_url/source_url are exempt: they are links to the public PDF
    # itself, which -- like judiciary.uk's own report URLs -- can carry an
    # incidental name-derived slug from the source's own filename.)
    for row in documents.values():
        blob = " ".join(str(v) for k, v in row.items()
                          if v is not None and k not in ("document_url", "source_url"))
        assert "Edward" not in blob
        assert "Hannah" not in blob

    # ...but it is kept, restricted.
    restricted_titles = {r["document_url"]: r["title_raw"] for r in conn.execute(
        "SELECT document_url, title_raw FROM restricted_sar_persons").fetchall()}
    assert restricted_titles[edward_url] == "HSAB SAR Edward report.pdf"

    # Both PDFs share the mocked text, plus the DOCX's own mention of
    # Turning Point -- one row per document, keyed on (document_url, provider_key).
    mentions = conn.execute(
        "SELECT document_url, provider_key FROM sar_provider_mentions").fetchall()
    assert {(r["document_url"], r["provider_key"]) for r in mentions} == {
        (edward_url, "change_grow_live"), (hannah_url, "change_grow_live"),
        (mr_b_url, "turning_point")}

    terms = {r["term"]: r["occurrences"] for r in conn.execute(
        "SELECT term, occurrences FROM sar_concern_terms WHERE document_url = ?",
        (edward_url,)).fetchall()}
    assert terms["staffing"] == 1
    assert terms["vacancy"] == 1

    docx_terms = {r["term"]: r["occurrences"] for r in conn.execute(
        "SELECT term, occurrences FROM sar_concern_terms WHERE document_url = ?",
        (mr_b_url,)).fetchall()}
    assert docx_terms["caseload"] == 1


def _insert_sar_document(conn, document_url: str, *, ext: str, year: int,
                          sab_name: str | None, has_body_text: int) -> None:
    conn.execute(
        "INSERT INTO sar_documents (document_url, document_ext, library_year, sab_name, "
        "has_body_text, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, '2026-01-01T00:00:00Z', 200, 'test', 'abc')",
        (document_url, ext, year, sab_name, has_body_text, document_url))
    conn.commit()


def test_run_skips_a_document_already_processed(httpx_mock, settings, conn):
    """The expensive part -- fetching and reading ~800 documents -- must not
    repeat on a second run once text has actually been extracted from a
    document. httpx_mock fails the test if an unregistered URL is requested,
    which is what proves the skip: only the library index and the one truly
    new document are mocked.
    """
    _allow_all_robots(httpx_mock)
    _mock_aux_sources(httpx_mock)
    httpx_mock.add_response(url=sar.LIBRARY_URL, text=LIBRARY_HTML, is_reusable=True)

    already = sar.resolve_document_url("./2026/HSAB SAR Edward report.pdf")
    _insert_sar_document(conn, already, ext=".pdf", year=2026,
                         sab_name="Hertfordshire Safeguarding Adults Board", has_body_text=1)

    other_pdf = sar.resolve_document_url("./2025/Camden Hannah (1).pdf")
    _insert_sar_document(conn, other_pdf, ext=".pdf", year=2025, sab_name=None, has_body_text=1)

    httpx_mock.add_response(
        url="https://nationalnetwork.org.uk/2026/MrBSARFinalReport.docx",
        content=b"fake docx bytes")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    sar.run(ctx)

    assert conn.execute("SELECT COUNT(*) AS n FROM sar_documents").fetchone()["n"] == 3


def test_run_retries_a_document_recorded_with_no_text(httpx_mock, settings, conn, monkeypatch):
    """A document read before this module could handle its format -- the
    real case this covers is every DOCX read before DOCX support existed --
    stayed `has_body_text = 0` forever under the old "any existing row is
    done" rule. A plain rerun must pick it up without any special command.
    """
    _allow_all_robots(httpx_mock)
    _mock_aux_sources(httpx_mock)
    httpx_mock.add_response(url=sar.LIBRARY_URL, text=LIBRARY_HTML, is_reusable=True)

    mr_b_url = sar.resolve_document_url("./2026/MrBSARFinalReport.docx")
    _insert_sar_document(conn, mr_b_url, ext=".docx", year=2026, sab_name=None, has_body_text=0)

    edward_url = sar.resolve_document_url("./2026/HSAB SAR Edward report.pdf")
    hannah_url = sar.resolve_document_url("./2025/Camden Hannah (1).pdf")
    httpx_mock.add_response(url=edward_url, content=b"%PDF-1.4 fake")
    httpx_mock.add_response(url=hannah_url, content=b"%PDF-1.4 fake")
    httpx_mock.add_response(url=mr_b_url, content=_build_docx(DOCX_PARAGRAPHS))
    monkeypatch.setattr(sar.pdftext, "page_texts", lambda *a, **k: [REPORT_TEXT])

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    sar.run(ctx)

    row = conn.execute(
        "SELECT has_body_text, sab_name FROM sar_documents WHERE document_url = ?",
        (mr_b_url,)).fetchone()
    assert row["has_body_text"] == 1
    assert row["sab_name"] == "Turning Point Safeguarding Adults Board"


@pytest.mark.parametrize("ext", [".doc", ".odt"])
def test_already_processed_does_not_retry_a_permanently_unreadable_extension(conn, ext):
    """A .doc or .odt document with no text is not this module gaining a new
    capability -- it is a format this module still cannot read at all -- so
    it stays settled rather than being refetched every run for nothing.
    """
    url = f"https://nationalnetwork.example/2020/legacy-review{ext}"
    _insert_sar_document(conn, url, ext=ext, year=2020, sab_name=None, has_body_text=0)
    assert sar._already_processed(conn, url) is True


def test_already_processed_retries_a_readable_extension_with_no_text(conn):
    url = "https://nationalnetwork.example/2026/report.docx"
    _insert_sar_document(conn, url, ext=".docx", year=2026, sab_name=None, has_body_text=0)
    assert sar._already_processed(conn, url) is False


def test_already_processed_is_false_for_an_unseen_url(conn):
    assert sar._already_processed(conn, "https://nationalnetwork.example/never-seen.pdf") is False
