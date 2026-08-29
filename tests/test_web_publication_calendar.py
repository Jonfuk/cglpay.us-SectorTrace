"""Source publication calendar (BETA-091).

Each source's stated cadence (registry metadata) and observed interval
(measured from retrieval history) are reported in separate fields and never
merged. A next-expected date is projected from whichever basis applies; a
status of "overdue" only says the freshness needs explaining, not why.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from pipeline.web import public_queries as pq


def _stat_rate(conn: sqlite3.Connection, period: str, retrieved_at: str) -> None:
    conn.execute(
        "INSERT INTO statutory_pay_rates (period_label, band_label, band_role, "
        " amount, value_text, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) VALUES "
        "(?, '21 and over', 'national_living_wage', 12.21, '£12.21', "
        " 'https://www.gov.uk/national-minimum-wage-rates', ?, 200, "
        " 'gov_uk_nmw', 'x')", (period, retrieved_at))


def _company(conn: sqlite3.Connection, number: str, retrieved_at: str) -> None:
    conn.execute(
        "INSERT INTO companies (company_number, company_name, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "(?, 'ACME PROVIDER LTD', 'https://find-and-update.company-information"
        ".service.gov.uk/company/' || ?, ?, 200, 'companies_house', 'x')",
        (number, number, retrieved_at))


def _row(out: dict, dataset_id: str) -> dict:
    return next(d for d in out["datasets"] if d["dataset_id"] == dataset_id)


def test_stated_and_observed_cadences_are_separate_fields(conn: sqlite3.Connection) -> None:
    out = pq.publication_calendar(conn, today="2026-08-29")
    assert set(out["counts"]) == {"by_status", "by_basis"}
    assert "total" not in out["counts"]
    assert set(out["statuses"]) == {"overdue", "due", "current", "unknown"}
    assert "estimate" in out["note"].lower()
    assert "does not tell the two apart" in out["caveat"].lower()
    for d in out["datasets"]:
        assert "stated_cadence_days" in d and "observed_interval_days" in d
        assert d["cadence_basis"] in {"stated", "observed", "unknown"}
    # a source that names an annual schedule carries the transcribed period
    assert _row(out, "statutory-pay-rates")["stated_cadence_days"] == 365
    # one described only as "Continuous" asserts no stated period
    assert _row(out, "companies-house")["stated_cadence_days"] is None


def test_a_stated_cadence_projects_the_next_expected_date(conn: sqlite3.Connection) -> None:
    _stat_rate(conn, "April 2025", "2025-04-01T00:00:00Z")
    conn.commit()
    out = pq.publication_calendar(conn, today="2025-05-01")
    row = _row(out, "statutory-pay-rates")
    assert row["cadence_basis"] == "stated"
    assert row["last_publication"] == "2025-04-01"
    assert row["next_expected"] == "2026-04-01"   # last + 365 days
    assert row["status"] == "current"             # a year still to run
    # evaluated far in the future the same row is overdue, by a counted margin
    later = _row(pq.publication_calendar(conn, today="2027-01-01"),
                 "statutory-pay-rates")
    assert later["status"] == "overdue"
    assert later["overdue_by_days"] == (date(2027, 1, 1) - date(2026, 4, 1)).days


def test_observed_interval_needs_three_dated_retrievals_and_is_labelled(
        conn: sqlite3.Connection) -> None:
    # two dated retrievals: one gap is not a cadence
    _company(conn, "00000001", "2026-01-01T00:00:00Z")
    _company(conn, "00000002", "2026-02-01T00:00:00Z")
    conn.commit()
    two = _row(pq.publication_calendar(conn, today="2026-08-29"), "companies-house")
    assert two["observed_interval_days"] is None
    assert two["cadence_basis"] == "unknown"   # no stated cadence to fall back to

    # a third moves it to an observed estimate, carrying its sample size
    _company(conn, "00000003", "2026-03-01T00:00:00Z")
    conn.commit()
    three = _row(pq.publication_calendar(conn, today="2026-08-29"), "companies-house")
    assert three["observed_interval_days"] in (28, 29, 30, 31)
    assert three["cadence_basis"] == "observed"
    assert three["observed_sample"] == 3
    assert three["stated_cadence_days"] is None   # never merged into the estimate


def test_today_is_deterministic_and_echoed(conn: sqlite3.Connection) -> None:
    out = pq.publication_calendar(conn, today="2099-06-15")
    assert out["as_of"] == "2099-06-15"
    # nothing retrieved in the empty warehouse -> every row is "unknown"
    assert out["counts"]["by_status"] == {"unknown": len(out["datasets"])}


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/publication_calendar" in openapi.document()["paths"]
