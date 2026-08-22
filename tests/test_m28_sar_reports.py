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


def test_run_end_to_end(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
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


def test_run_skips_a_document_already_processed(httpx_mock, settings, conn):
    """The expensive part -- fetching and reading ~800 documents -- must not
    repeat on a second run. httpx_mock fails the test if an unregistered URL
    is requested, which is what proves the skip: only the library index is
    mocked, no document fetch.
    """
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=sar.LIBRARY_URL, text=LIBRARY_HTML, is_reusable=True)

    already = sar.resolve_document_url("./2026/HSAB SAR Edward report.pdf")
    conn.execute(
        "INSERT INTO sar_documents (document_url, document_ext, library_year, sab_name, "
        "has_body_text, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '.pdf', 2026, 'Hertfordshire Safeguarding Adults Board', 1, ?, "
        "'2026-01-01T00:00:00Z', 200, 'test', 'abc')", (already, already))
    conn.commit()

    other_pdf = sar.resolve_document_url("./2025/Camden Hannah (1).pdf")
    conn.execute(
        "INSERT INTO sar_documents (document_url, document_ext, library_year, sab_name, "
        "has_body_text, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '.pdf', 2025, NULL, 0, ?, '2026-01-01T00:00:00Z', 200, 'test', 'abc')",
        (other_pdf, other_pdf))
    conn.commit()

    httpx_mock.add_response(
        url="https://nationalnetwork.org.uk/2026/MrBSARFinalReport.docx",
        content=b"fake docx bytes")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    sar.run(ctx)

    assert conn.execute("SELECT COUNT(*) AS n FROM sar_documents").fetchone()["n"] == 3
