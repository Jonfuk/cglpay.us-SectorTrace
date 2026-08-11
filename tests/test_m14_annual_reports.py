from __future__ import annotations

import pytest

from pipeline.modules import m14_annual_reports as ar


# --- passage extraction ---------------------------------------------------------

def test_finds_a_topic_and_keeps_the_passage_verbatim():
    page = ("Our people\nStaff recruitment remained challenging in several regions during "
            "the year, and we invested in a new applicant tracking system.")
    found = ar.find_passages(page, 19)
    topics = {p["topic"] for p in found}
    assert "recruitment" in topics
    passage = next(p for p in found if p["topic"] == "recruitment")
    assert "applicant tracking system" in passage["passage_text"]
    assert passage["page_number"] == 19


def test_records_which_wording_actually_matched():
    """The evidence trail should show the term that appeared, not just that
    the topic did.
    """
    found = ar.find_passages("Staff turnover was discussed by the board.", 5)
    turnover = [p for p in found if p["topic"] == "staff_turnover_rate"]
    assert turnover and turnover[0]["matched_term"] == "staff turnover"


def test_one_row_per_topic_per_page():
    """A page mentioning several synonyms of one topic yields one row, not one
    per synonym, so page counts are not inflated.
    """
    page = "Staff retention, retention of staff and employee retention were all considered."
    retention = [p for p in ar.find_passages(page, 1) if p["topic"] == "retention"]
    assert len(retention) == 1


def test_multiple_topics_on_one_page_are_separate_rows():
    page = ("Recruitment and retention pressures continued, alongside a "
            "restructuring of services.")
    topics = {p["topic"] for p in ar.find_passages(page, 1)}
    assert {"recruitment", "retention", "restructuring"} <= topics


def test_matching_is_case_insensitive():
    assert any(p["topic"] == "equality" for p in ar.find_passages("GENDER PAY gap report", 1))


# --- false positives found in live output, locked in as regressions ---------------

def test_charitable_objects_clause_is_not_read_as_staff_absence():
    """Real text from CGL's accounts. Bare "sickness" matched the charity's
    objects clause, producing a confident but entirely wrong topic label.
    """
    page = ("The Charity's Objects are to relieve poverty, sickness and distress "
            "among persons affected by substance use.")
    topics = {p["topic"] for p in ar.find_passages(page, 39)}
    assert "sickness_absence" not in topics


def test_contract_retentions_are_not_read_as_staff_retention():
    """Real text from CGL's accounts: "Retentions" there lists services won and
    kept, nothing to do with staff turnover.
    """
    page = ("Retentions New contract Location and Service start date "
            "Lambeth Young People's Substance Use Service 01/04/24")
    topics = {p["topic"] for p in ar.find_passages(page, 11)}
    assert "retention" not in topics


def test_service_user_wellbeing_is_not_read_as_staff_wellbeing():
    """In a treatment charity, unqualified "wellbeing" almost always describes
    service users.
    """
    page = "We measure the wellbeing of the people who use our services each quarter."
    topics = {p["topic"] for p in ar.find_passages(page, 6)}
    assert "staff_wellbeing" not in topics


def test_workforce_qualified_wording_still_matches():
    """Tightening the terms must not silence genuine workforce discussion."""
    assert any(p["topic"] == "retention"
                for p in ar.find_passages("Staff retention improved this year.", 1))
    assert any(p["topic"] == "sickness_absence"
                for p in ar.find_passages("Sickness absence fell to 4.1%.", 1))
    assert any(p["topic"] == "staff_wellbeing"
                for p in ar.find_passages("Our staff wellbeing programme expanded.", 1))
    assert any(p["topic"] == "staff_turnover_rate"
                for p in ar.find_passages("Staff turnover was 22% in the year.", 1))


def test_empty_page_yields_nothing():
    assert ar.find_passages("", 1) == []
    assert ar.find_passages(None, 1) == []


# --- disclosure summary ------------------------------------------------------------

def test_every_configured_topic_appears_in_the_summary():
    """Absence is the point: a topic with no match must still be recorded."""
    summary = ar.summarise_disclosure([])
    assert set(summary) == set(ar.TOPICS)
    assert all(v["matched"] == 0 for v in summary.values())


def test_summary_counts_distinct_pages():
    passages = [
        {"topic": "recruitment", "page_number": 3, "matched_term": "recruitment"},
        {"topic": "recruitment", "page_number": 9, "matched_term": "recruitment"},
    ]
    summary = ar.summarise_disclosure(passages)
    assert summary["recruitment"]["matched"] == 1
    assert summary["recruitment"]["pages_matched"] == 2
    assert summary["sickness_absence"]["matched"] == 0


def test_summary_records_exactly_what_was_searched_for():
    """A claimed gap is only meaningful next to the terms that produced it."""
    summary = ar.summarise_disclosure([])
    assert "sickness" in summary["sickness_absence"]["search_terms"]
    assert "turnover rate" in summary["staff_turnover_rate"]["search_terms"]


def test_topics_cover_the_workforce_measures_the_brief_names():
    for topic in ("recruitment", "retention", "vacancy_rate", "sickness_absence",
                   "restructuring", "executive_pay", "equality", "employee_engagement"):
        assert topic in ar.TOPICS


# --- the gap view and its caveat -------------------------------------------------------

def _seed(conn, topic, matched):
    from pipeline import providers
    providers.seed_providers(conn)
    conn.execute(
        "INSERT INTO provider_report_disclosure (provider_key, financial_year_end, topic, "
        "matched, pages_matched, search_terms, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('change_grow_live','2025-03-31',?,?,0,'a, b',"
        "'u','t',200,'s','h')", (topic, matched))


def test_gap_view_lists_only_unmatched_topics(conn):
    _seed(conn, "sickness_absence", 0)
    _seed(conn, "recruitment", 1)
    rows = conn.execute("SELECT topic FROM v_provider_disclosure_gaps").fetchall()
    assert [r["topic"] for r in rows] == ["sickness_absence"]


def test_gap_view_carries_the_weaker_than_not_disclosed_caveat(conn):
    """A term-based miss is not proof the provider publishes nothing on the
    subject, and the row must say so.
    """
    _seed(conn, "sickness_absence", 0)
    row = conn.execute("SELECT * FROM v_provider_disclosure_gaps").fetchone()
    assert 'weaker than "not disclosed"' in row["caveat"]
    assert row["search_terms"]


def test_gap_view_names_the_provider(conn):
    _seed(conn, "vacancy_rate", 0)
    row = conn.execute("SELECT * FROM v_provider_disclosure_gaps").fetchone()
    assert row["provider_name"]


# --- provenance inheritance ----------------------------------------------------------------

def test_provenance_is_inherited_not_invented():
    """The PDF is read from local disk; claiming a fresh retrieval would be a
    false provenance record.
    """
    row = {"source_url": "https://example.com/a.pdf", "retrieved_at": "2026-01-01T00:00:00Z",
            "http_status": 200, "payload_sha256": "abc"}
    provenance = ar._provenance(row)
    assert provenance["source_url"] == "https://example.com/a.pdf"
    assert provenance["retrieved_at"] == "2026-01-01T00:00:00Z"
    assert provenance["payload_sha256"] == "abc"
