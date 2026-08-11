from __future__ import annotations

import re

import pytest

from pipeline.keywords import COMMITTEE_SEARCH_TERMS
from pipeline.modules import m10_committee_papers as cp


# --- system detection ------------------------------------------------------------

def test_detects_moderngov_from_its_signature_path():
    system, signature = cp.detect_committee_system(lambda p: p == "/mgWhatsNew.aspx")
    assert system == "moderngov"
    assert signature == "/mgWhatsNew.aspx"


def test_detects_cmis_from_its_signature_path():
    system, _ = cp.detect_committee_system(lambda p: "CMIS5" in p)
    assert system == "cmis"


def test_unknown_system_is_a_recorded_answer_not_a_guess():
    """Nothing matching must yield 'unknown', which routes the authority to
    the null adapter — never a default like 'moderngov'.
    """
    system, signature = cp.detect_committee_system(lambda p: False)
    assert system == "unknown"
    assert signature is None


# --- search URL ---------------------------------------------------------------------

def test_moderngov_search_url_encodes_the_term():
    url = cp.build_moderngov_search_url("https://democracy.kent.gov.uk", "drug and alcohol")
    assert url.startswith("https://democracy.kent.gov.uk/mgSearchResults.aspx?txtSearch=")
    assert "drug+and+alcohol" in url


def test_moderngov_search_url_tolerates_trailing_slash():
    a = cp.build_moderngov_search_url("https://x.gov.uk", "TUPE")
    b = cp.build_moderngov_search_url("https://x.gov.uk/", "TUPE")
    assert a == b


# --- results parsing -------------------------------------------------------------------

RESULTS_HTML = '''
  <a href="/documents/s12345/Drug%20and%20Alcohol%20Recommissioning%2012th%20March%202025.pdf">
     Drug and Alcohol Recommissioning 12th March 2025</a>
  <a href="/mgCalendarMonthView.aspx?GL=1">Calendar</a>
  <a href="/mgMemberIndex.aspx">Councillors</a>
  <a href="https://other.example.com/documents/s1/External.pdf">External doc</a>
'''


def test_parses_only_document_links():
    """Navigation and calendar links share the markup and would otherwise
    flood the review worklist.
    """
    rows = cp.parse_moderngov_results(RESULTS_HTML, "https://democracy.kent.gov.uk/x", "drug and alcohol")
    assert len(rows) == 1
    assert rows[0]["document_url"].endswith(".pdf")
    assert "Recommissioning" in rows[0]["report_title"]


def test_parsing_stays_on_the_same_host():
    rows = cp.parse_moderngov_results(RESULTS_HTML, "https://democracy.kent.gov.uk/x", "t")
    assert all("democracy.kent.gov.uk" in r["document_url"] for r in rows)


def test_extracts_meeting_date_when_present_in_the_title():
    rows = cp.parse_moderngov_results(RESULTS_HTML, "https://democracy.kent.gov.uk/x", "t")
    assert rows[0]["meeting_date"] == "12th March 2025"


def test_meeting_date_is_none_when_absent():
    html = '<a href="/documents/s1/Report.pdf">Substance misuse update</a>'
    rows = cp.parse_moderngov_results(html, "https://x.gov.uk/y", "t")
    assert rows[0]["meeting_date"] is None


def test_records_which_term_found_the_document():
    rows = cp.parse_moderngov_results(RESULTS_HTML, "https://democracy.kent.gov.uk/x", "recommissioning")
    assert rows[0]["matched_term"] == "recommissioning"


def test_parse_empty_html():
    assert cp.parse_moderngov_results("", "https://x.gov.uk/y", "t") == []


# --- search terms -------------------------------------------------------------------------

def test_search_terms_come_from_config():
    for term in ("drug and alcohol", "substance misuse", "TUPE", "public health grant"):
        assert term in COMMITTEE_SEARCH_TERMS


# --- verification discipline ------------------------------------------------------------------

def _seed_authority(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000016','Kent','county','2020-01-01','x','x','u','t',200,'s','h')")


def test_candidates_default_to_unverified(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, report_title, "
        "matched_term, discovered_at, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('E10000016','https://x/y.pdf','T','TUPE','2026-01-01','u','t',"
        "200,'s','h')")
    row = conn.execute("SELECT * FROM committee_paper_candidates").fetchone()
    assert row["verified"] == 0
    assert row["rejected"] == 0


def test_committee_papers_starts_empty(conn):
    """A search hit means a title matched a phrase — "TUPE" and "public
    health grant" appear in plenty of unrelated papers — so nothing is
    promoted without confirmation.
    """
    assert conn.execute("SELECT COUNT(*) c FROM committee_papers").fetchone()["c"] == 0


def test_moderngov_get_search_limitation_is_recorded(conn, settings, httpx_mock, monkeypatch):
    """Verified against a live ModernGov site: the document search answers a
    plain GET with a 302. An adapter that reports a clean run with nothing
    found would hide that, so the inability to search is recorded.
    """
    from pipeline import authority_websites
    from pipeline.registry import ModuleContext

    _seed_authority(conn)
    monkeypatch.setitem(
        authority_websites.AUTHORITY_WEBSITES, "E10000016",
        authority_websites.AuthorityWebsite(
            ons_code="E10000016", name="Kent", base_url="https://x.gov.uk",
            committee_url="https://democracy.example.gov.uk",
            committee_system="moderngov", verified_on="2026-01-01"))

    httpx_mock.add_response(url="https://democracy.example.gov.uk/robots.txt",
                             status_code=200, text="", is_reusable=True)
    # signature path exists -> detected as moderngov
    httpx_mock.add_response(url="https://democracy.example.gov.uk/mgWhatsNew.aspx",
                             text="<html>ok</html>", is_reusable=True)
    # every search returns a page with no document links, as a real GET does
    httpx_mock.add_response(
        url=re.compile(r".*mgSearchResults\.aspx.*"),
        text="<html><a href='/mgCalendarMonthView.aspx'>Cal</a></html>", is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    cp.run(ctx)

    assert conn.execute(
        "SELECT committee_system FROM authority_committee_systems"
    ).fetchone()["committee_system"] == "moderngov"
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='moderngov_search_requires_post'"
    ).fetchone()["c"] == 1


def test_system_detection_is_persisted_including_unknown(conn):
    _seed_authority(conn)
    conn.execute(
        "INSERT INTO authority_committee_systems (ons_code, committee_system, committee_url, "
        "detected_at) VALUES ('E10000016','unknown','https://x','2026-01-01')")
    row = conn.execute("SELECT * FROM authority_committee_systems").fetchone()
    assert row["committee_system"] == "unknown"
