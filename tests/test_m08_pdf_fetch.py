"""Reading a PFD report that is published only as a PDF.

Two thirds of the corpus — 1,067 of 1,539 reports — put nothing but a metadata
header in judiciary.uk's REST content. The report itself is a PDF, and it is
not linked from the API response either, so the module has to go to the
report's own page and find it. Until it did, those reports sat in the review
queue asking a person to decide something no person could decide.

Most of what follows is about the ways that goes wrong. The one that matters
most is the redaction case: PDF text is full prose and coroners name the
deceased inside the matters of concern, so text that arrives this way has none
of the protection the structured REST stub had.
"""
from __future__ import annotations

import json
import re

import pytest

from pipeline.http import PipelineHTTPClient
from pipeline.modules import m08_pfd_reports as pfd
from pipeline.registry import ModuleContext

REPORT_PAGE = """
<html><body>
  <a href="https://www.judiciary.uk/wp-content/uploads/2024/09/A-Roe-Prevention-of-Future-Deaths-Report-2026-0285.pdf">Report</a>
  <a href="https://www.judiciary.uk/wp-content/uploads/2024/09/2026-0285-Response-from-Someone.pdf">Response</a>
</body></html>
"""

# The shape judiciary.uk actually returns for these: a clean structured header
# and nothing else. 321 characters is typical.
STUB_CONTENT = (
    "Date of report: 27/04/2026 \n Ref: 2026-0285 \n Deceased name: Alex Roe\n"
    " Coroners name: Sam Casey\n Coroners Area: East Riding\n"
    " Category: Alcohol, drug and medication related deaths\n"
    " This report is being sent to: Change Grow Live"
)

PAGE_URL = "https://www.judiciary.uk/prevention-of-future-death-reports/a-roe/"


# --- choosing which PDF is the report --------------------------------------------


def test_the_report_pdf_is_chosen_over_the_response():
    """A page carries the coroner's report and the replies to it. Those make
    different claims, and only the report holds the matters of concern."""
    chosen = pfd.choose_report_pdf([
        "https://x/2026-0285-Response-from-Someone.pdf",
        "https://x/A-Roe-Prevention-of-Future-Deaths-Report-2026-0285.pdf",
    ])
    assert chosen.endswith("Report-2026-0285.pdf")


def test_a_page_with_only_responses_yields_no_report():
    """Better nothing than filing somebody's reply as the coroner's concerns."""
    assert pfd.choose_report_pdf(["https://x/2026-0285-Response-from-A.pdf"]) is None
    assert pfd.choose_report_pdf([]) is None


def test_a_lone_unlabelled_pdf_is_taken_as_the_report():
    assert pfd.choose_report_pdf(["https://x/2026-0285.pdf"]) == "https://x/2026-0285.pdf"


# --- fetching ---------------------------------------------------------------------


def _mock_page_and_pdf(httpx_mock, page_status=200):
    httpx_mock.add_response(url="https://www.judiciary.uk/robots.txt",
                             status_code=200, text="", is_reusable=True)
    if page_status != 200:
        # No PDF response registered: a page that cannot be read must not lead
        # to a PDF fetch, and pytest_httpx fails the test if it does not.
        httpx_mock.add_response(url=PAGE_URL, status_code=page_status, is_reusable=True)
        return
    httpx_mock.add_response(url=PAGE_URL, text=REPORT_PAGE, is_reusable=True)
    httpx_mock.add_response(url=re.compile(r".*\.pdf"), content=b"%PDF-1.4 fake",
                             is_reusable=True)


def test_the_pdf_text_is_read_from_the_report_page(httpx_mock, settings, monkeypatch):
    _mock_page_and_pdf(httpx_mock)
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Staffing was short.", "ACTION SHOULD BE TAKEN"])

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)

    assert "Staffing was short" in read.text
    assert read.chosen.endswith("Report-2026-0285.pdf")
    assert len(read.urls) == 2, "both PDFs on the page come back for pfd_documents"
    assert read.reason is None
    assert read.source == "pdf"


def test_an_unreachable_report_page_is_not_an_error(httpx_mock, settings):
    _mock_page_and_pdf(httpx_mock, page_status=404)
    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)
    assert (read.text, read.urls, read.chosen) == (None, [], None)
    assert "404" in read.reason


def test_a_scanned_pdf_says_it_needs_ocr(httpx_mock, settings, monkeypatch):
    """Seven of twelve sampled reports are scans with no text layer, mostly
    2014 to 2018. A review item saying that is worth far more than one saying
    "the concerns are in a PDF" — one needs OCR, not a person."""
    _mock_page_and_pdf(httpx_mock)
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: ["", "", "", ""])

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)

    assert read.text is None
    assert read.chosen is not None
    assert "no text layer" in read.reason
    assert "4 pages" in read.reason


def test_a_pdf_pdfplumber_cannot_open_does_not_stop_the_run(httpx_mock, settings,
                                                              monkeypatch):
    _mock_page_and_pdf(httpx_mock)

    def explode(*a, **k):
        raise ValueError("not a PDF")

    monkeypatch.setattr(pfd.pdftext, "page_texts", explode)
    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)

    assert read.text is None
    assert read.chosen is not None, "the URL is reported, so the failure is diagnosable"
    assert "could not be opened" in read.reason


# --- the whole path, through run() -------------------------------------------------


@pytest.fixture
def ctx(conn, settings):
    return ModuleContext(conn=conn, settings=settings, since=None,
                          dry_run=False, limit=None)


def _run(ctx, httpx_mock, content=STUB_CONTENT):
    """m08's run() over a listing of one report.

    Every response is reusable: the module walks several report categories, so
    it asks for the listing once per category and would otherwise run out of
    registered responses part way through.
    """
    httpx_mock.add_response(url="https://www.judiciary.uk/robots.txt",
                             status_code=200, text="", is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.judiciary\.uk/wp-json/wp/v2/pfd.*"),
        is_reusable=True,
        json=[{
            "link": PAGE_URL,
            "title": {"rendered": "Alex Roe: Prevention of future deaths report"},
            "content": {"rendered": content},
        }])
    httpx_mock.add_response(url=PAGE_URL, text=REPORT_PAGE, is_reusable=True)
    httpx_mock.add_response(url=re.compile(r".*\.pdf"), content=b"%PDF-1.4 fake",
                             is_reusable=True)
    pfd.run(ctx)


def test_a_stub_report_gets_its_concerns_from_the_pdf(ctx, conn, httpx_mock, monkeypatch):
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "REGULATION 28 REPORT\n5. MATTERS OF CONCERN (1) Staffing was short and "
        "vacancy rates were high.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    row = conn.execute("SELECT matters_of_concern FROM pfd_reports "
                        "WHERE report_ref='2026-0285'").fetchone()
    assert row is not None
    assert "Staffing was short" in row["matters_of_concern"]

    # And no review item: it was never a decision, it was a document nobody
    # had gone and read.
    assert conn.execute("SELECT COUNT(*) FROM review_queue "
                         "WHERE item_type='pfd_concerns_in_pdf_only'").fetchone()[0] == 0


def test_the_deceased_is_redacted_out_of_concerns_taken_from_a_pdf(
        ctx, conn, httpx_mock, monkeypatch):
    """The reason this is not a plain download. The REST stub was structured
    and safe; PDF text is prose, and coroners name the deceased in it."""
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Alex Roe waited nine hours before triage. "
        "Roe was not reviewed again.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    matters = conn.execute("SELECT matters_of_concern FROM pfd_reports "
                            "WHERE report_ref='2026-0285'").fetchone()["matters_of_concern"]
    assert "Alex Roe" not in matters
    assert "Roe" not in matters, "the surname alone is redacted too"
    assert "[name redacted]" in matters
    assert "waited nine hours" in matters, "the substance survives the redaction"


def test_concerns_are_withheld_when_there_is_no_name_to_redact_against(
        ctx, conn, httpx_mock, monkeypatch):
    """Eight of the 1,067 have no deceased name in the header. Without one
    there is no way to know whether the coroner used a name in this section,
    and "probably not" is not a standard to publish personal data against."""
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Someone waited nine hours.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock, content=STUB_CONTENT.replace(" Deceased name: Alex Roe\n", "\n"))

    row = conn.execute("SELECT matters_of_concern FROM pfd_reports "
                        "WHERE report_ref='2026-0285'").fetchone()
    assert not (row["matters_of_concern"] or "").strip(), \
        "nothing public without a name to redact against"

    failure = conn.execute(
        "SELECT reason FROM parse_failures WHERE module='m08_pfd_reports' "
        "AND field_name='deceased_name'").fetchone()
    assert failure is not None, "and the reason it was withheld is recorded"
    assert "no name to redact against" in failure["reason"]


def test_the_full_pdf_text_is_restricted_not_public(ctx, conn, httpx_mock, monkeypatch):
    """A PFD report names the deceased throughout, not only in the header."""
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "Alex Roe died on the ward. MATTERS OF CONCERN (1) Staffing was short.\n"
        "6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    restricted = conn.execute(
        "SELECT body_text FROM restricted_pfd_report_text "
        "WHERE report_ref='2026-0285'").fetchone()["body_text"]
    assert "Alex Roe died on the ward" in restricted, "the evidence is kept"

    public = conn.execute("SELECT * FROM pfd_reports "
                           "WHERE report_ref='2026-0285'").fetchone()
    assert not any("Alex Roe" in str(value) for value in tuple(public)), \
        "and it appears nowhere in the public row"


def test_a_report_whose_pdf_cannot_be_read_still_raises_the_review_item(
        ctx, conn, httpx_mock, monkeypatch):
    """The item stops being noise and becomes what it always claimed to be: a
    report this pipeline genuinely could not read."""
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [""])
    _run(ctx, httpx_mock)

    item = conn.execute("SELECT raw_value, context_json FROM review_queue "
                         "WHERE item_type='pfd_concerns_in_pdf_only'").fetchone()
    assert item["raw_value"] == "2026-0285"
    context = json.loads(item["context_json"])
    assert context["pdfs_on_page"], \
        "the URLs it tried are in the item, so it can be checked by hand"
    assert "no text layer" in context["reason"], \
        "and why it failed, so the residue can be triaged rather than read"


def test_pdfs_found_on_the_page_are_recorded_as_documents(ctx, conn, httpx_mock,
                                                            monkeypatch):
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Staffing.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    rows = conn.execute("SELECT document_type FROM pfd_documents "
                         "WHERE report_ref='2026-0285'").fetchall()
    assert {r["document_type"] for r in rows} == {"report", "response"}


# --- affordable to repeat -----------------------------------------------------------


def test_a_report_whose_concerns_are_already_held_is_not_fetched_again(conn):
    """What makes a seventy-minute pass affordable to run twice."""
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, matters_of_concern, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('2026-0285','u','Staffing was short.','u','t',200,'s','h')")
    assert pfd._already_has_concerns(conn, "2026-0285") is True
    assert pfd._already_has_concerns(conn, "2026-9999") is False


def test_an_empty_concerns_column_does_not_count_as_already_held(conn):
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, matters_of_concern, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('2026-0285','u','   ','u','t',200,'s','h')")
    assert pfd._already_has_concerns(conn, "2026-0285") is False


# --- OCR, for the reports that are scans -------------------------------------------
#
# Seven of every twelve. The engine is an optional extra and off by default, so
# these drive the seam rather than the engine: what the module does when OCR is
# unavailable, when it is switched off, when it succeeds, and -- the one that
# matters -- when its output defeats the redaction.


def _scanned(monkeypatch):
    """A PDF pdfplumber opens and finds no text in."""
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: ["", "", "", ""])


def test_a_scan_says_the_extra_is_missing_when_it_is(httpx_mock, settings, monkeypatch):
    _mock_page_and_pdf(httpx_mock)
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "available", lambda: False)

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)
    assert "needs the ocr extra" in read.reason


def test_a_scan_says_ocr_is_installed_but_off(httpx_mock, settings, monkeypatch):
    """Two switches, and the review item says which one is closed."""
    _mock_page_and_pdf(httpx_mock)
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "available", lambda: True)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: False)

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)
    assert "switched off" in read.reason
    assert "OCR_ENABLED" in read.reason


def test_ocr_text_is_used_and_marked_as_ocr(httpx_mock, settings, monkeypatch):
    _mock_page_and_pdf(httpx_mock)
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)
    monkeypatch.setattr(pfd.ocr, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Staffing was short."])

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)

    assert "Staffing was short" in read.text
    assert read.source == "ocr", "so the row can record that this is not a transcript"
    assert read.reason is None


def test_ocr_failing_is_reported_not_raised(httpx_mock, settings, monkeypatch):
    _mock_page_and_pdf(httpx_mock)
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)

    def explode(*a, **k):
        raise RuntimeError("model missing")

    monkeypatch.setattr(pfd.ocr, "page_texts", explode)
    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)
    assert read.text is None
    assert "OCR failed" in read.reason


def test_ocr_that_reads_nothing_says_so(httpx_mock, settings, monkeypatch):
    _mock_page_and_pdf(httpx_mock)
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)
    monkeypatch.setattr(pfd.ocr, "page_texts", lambda *a, **k: ["", ""])

    with PipelineHTTPClient("test", settings=settings) as client:
        read = pfd.fetch_pdf_report(client, settings, PAGE_URL)
    assert read.text is None
    assert "found no text on any page" in read.reason


def test_concerns_read_by_ocr_are_recorded_as_ocr(ctx, conn, httpx_mock, monkeypatch):
    """A quotation from this column may end up in a campaign document, and "a
    machine read this off a photocopy" is a different claim from "the coroner
    wrote this"."""
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)
    monkeypatch.setattr(pfd.ocr, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Staffing was short.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    row = conn.execute("SELECT matters_of_concern, concerns_source FROM pfd_reports "
                        "WHERE report_ref='2026-0285'").fetchone()
    assert "Staffing was short" in row["matters_of_concern"]
    assert row["concerns_source"] == "ocr"


def test_concerns_read_from_a_text_layer_are_recorded_as_pdf(ctx, conn, httpx_mock,
                                                              monkeypatch):
    monkeypatch.setattr(pfd.pdftext, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) Staffing was short.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)
    assert conn.execute("SELECT concerns_source FROM pfd_reports "
                         "WHERE report_ref='2026-0285'").fetchone()[0] == "pdf"


# --- the post-condition ---------------------------------------------------------------


def test_nothing_is_published_when_the_name_survives_redaction(ctx, conn, httpx_mock,
                                                                monkeypatch):
    """The real failure this guards. OCR loses spaces, so a genuine report
    produced "MsRichardson died some 9 days later" -- no word boundary, so the
    boundary-anchored redaction missed it and the surname was heading for a
    public column. Redaction is now checked, not trusted."""
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)
    # "Roe" is three characters, below the substring threshold, so welding it
    # to the previous word defeats every pattern -- exactly the OCR failure.
    monkeypatch.setattr(pfd.ocr, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) MrRoe waited nine hours.\n6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock)

    row = conn.execute("SELECT matters_of_concern FROM pfd_reports "
                        "WHERE report_ref='2026-0285'").fetchone()
    assert not (row["matters_of_concern"] or "").strip(),         "the name was still in there, so nothing is published"

    failure = conn.execute(
        "SELECT reason FROM parse_failures WHERE field_name='matters_of_concern'"
    ).fetchone()
    assert failure is not None and "Roe" in failure["reason"]


def test_a_long_surname_welded_to_a_word_is_still_removed(ctx, conn, httpx_mock,
                                                            monkeypatch):
    """The common case, and why the substring pass exists: "MsRichardson" has
    no word boundary but is long enough to remove safely."""
    _scanned(monkeypatch)
    monkeypatch.setattr(pfd.ocr, "enabled", lambda s: True)
    monkeypatch.setattr(pfd.ocr, "page_texts", lambda *a, **k: [
        "MATTERS OF CONCERN (1) MsRichardson died some 9 days later.\n"
        "6. ACTION SHOULD BE TAKEN"])
    _run(ctx, httpx_mock,
         content=STUB_CONTENT.replace("Alex Roe", "Amanda Richardson"))

    matters = conn.execute("SELECT matters_of_concern FROM pfd_reports "
                            "WHERE report_ref='2026-0285'").fetchone()["matters_of_concern"]
    assert matters, "this one is publishable"
    assert "Richardson" not in matters
    assert "died some 9 days later" in matters


def test_surviving_name_part_finds_a_name_hidden_in_a_word():
    assert pfd.surviving_name_part("MrRoe waited", "Alex Roe") == "Roe"
    assert pfd.surviving_name_part("nothing here", "Alex Roe") is None
    assert pfd.surviving_name_part("the REDACTED family", "REDACTED") is None


def test_surviving_name_part_ignores_initials():
    """A one or two letter part appears inside half the words in English."""
    assert pfd.surviving_name_part("a nurse recorded it", "A B Roe") is None


# --- OCR loses spaces, and the finding aid has to survive it -------------------------


def test_watched_terms_are_found_inside_a_run_together_word():
    """The recogniser welds words on tightly-set lines: a real report gave
    "foraperiodofaboutsixmonths". Boundary-anchored matching finds a term only
    when the welded run happens to start with it, so the reports hardest to
    read become the least findable."""
    welded = "therewerestaffingshortagesandhighvacancyrates"
    assert pfd.index_concern_terms(welded) == {}
    found = pfd.index_concern_terms(welded, welded=True)
    assert "staffing" in found


def test_boundary_matching_is_still_the_default_for_clean_text():
    assert pfd.index_concern_terms("understaffing was raised") == {}
    assert "staffing" in pfd.index_concern_terms("staffing was raised")
