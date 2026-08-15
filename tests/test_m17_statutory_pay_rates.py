"""Module 17: the statutory floor as a reference table.

The source is the gov.uk rates page via the content API; the parsing rules
each exist because a real page shape would break a naive reader — trailing
non-breaking spaces, whole-pound values, and a band set that changes between
eras. The "must not compute" side of the finding is the module's contract:
it stores rates and nothing else, and the tests pin that nothing here
multiplies or divides them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.modules import m17_statutory_pay_rates as rates
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str = "https://www.gov.uk") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="", is_reusable=True)


# --- parsing ------------------------------------------------------------------

def test_parse_effective_from_handles_both_period_shapes():
    assert rates.parse_effective_from("April 2026") == "2026-04-01"
    assert rates.parse_effective_from("April 2025 to March 2026") == "2025-04-01"
    assert rates.parse_effective_from("sometime in 2023") is None


def test_parse_amount_strips_nbsp_and_whole_pounds():
    assert rates.parse_amount("\u00a312.71") == 12.71
    assert rates.parse_amount("\u00a38") == 8.0
    assert rates.parse_amount("\u00a310\u00a0") == 10.0
    assert rates.parse_amount("not a rate") is None


def test_rates_table_parsing_reads_era_column_sets():
    fixture = json.loads((FIXTURES / "govuk_content_nmw_rates.json").read_text())
    rows = rates.parse_rates_table(fixture["details"]["body"])

    # 1 current + 1 (2024-26) + 2 (2021-24) + 1 (2019-20) periods, each with
    # its own era's band set.
    periods = {}
    for row in rows:
        periods.setdefault(row["period_label"], []).append(row)

    assert set(periods) == {
        "April 2026", "April 2025 to March 2026", "April 2023 to March 2024",
        "April 2022 to March 2023", "April 2019 to March 2020",
    }

    current = periods["April 2026"]
    assert [r["band_label"] for r in current] == ["21 and over", "18 to 20",
                                                   "Under 18", "Apprentice"]
    # The living wage column is the first data column, whatever its label.
    assert current[0]["band_role"] == "national_living_wage"
    assert all(r["band_role"] == "national_minimum_wage" for r in current[1:])

    older = periods["April 2019 to March 2020"]
    assert [r["band_label"] for r in older] == ["25 and over", "21 to 24",
                                                 "18 to 20", "Under 18", "Apprentice"]
    assert older[0]["band_role"] == "national_living_wage"

    values = {r["band_label"]: r for r in periods["April 2025 to March 2026"]}
    assert values["21 and over"]["value_text"] == "\u00a312.21"
    # trailing non-breaking space must not break the amount or the verbatim text
    assert values["18 to 20"]["value_text"] == "\u00a310"
    assert rates.parse_amount(values["18 to 20"]["value_text"]) == 10.0


def test_parse_amount_of_unparseable_cell_is_null_not_guessed():
    rows = rates.parse_rates_table("<table><tr><th></th><th>21 and over</th></tr>"
                                    "<tr><th>April 2026</th><td>circa eight quid</td></tr></table>")
    assert len(rows) == 1
    assert rates.parse_amount(rows[0]["value_text"]) is None


# --- end to end ---------------------------------------------------------------

def test_run_parses_the_page_and_writes_rates(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    fixture = json.loads((FIXTURES / "govuk_content_nmw_rates.json").read_text())
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=fixture)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    rates.run(ctx)

    rows = conn.execute("SELECT * FROM statutory_pay_rates ORDER BY period_label, band_label").fetchall()
    assert len(rows) == 23
    april_2026 = {r["band_label"]: r for r in rows if r["period_label"] == "April 2026"}
    assert april_2026["21 and over"]["amount"] == 12.71
    assert april_2026["21 and over"]["effective_from"] == "2026-04-01"
    assert april_2026["21 and over"]["band_role"] == "national_living_wage"
    assert april_2026["Apprentice"]["band_role"] == "national_minimum_wage"
    assert april_2026["21 and over"]["source_url"].endswith("/api/content/national-minimum-wage-rates")

    # every row carries provenance
    assert all(r["source_url"] and r["payload_sha256"] for r in rows)


def test_run_is_idempotent_and_refreshes(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    fixture = json.loads((FIXTURES / "govuk_content_nmw_rates.json").read_text())
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=fixture,
        is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    rates.run(ctx)
    rates.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM statutory_pay_rates").fetchone()["c"] == 23
    assert conn.execute("SELECT COUNT(*) c FROM parse_failures").fetchone()["c"] == 0


def test_run_records_a_parse_failure_for_an_unreadable_cell(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    body = ("<table><tr><th></th><th>21 and over</th></tr>"
            "<tr><th>April 2026</th><td>some unreadable figure</td></tr></table>")
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             json={"details": {"body": body}})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    rates.run(ctx)

    row = conn.execute("SELECT * FROM statutory_pay_rates").fetchone()
    assert row["amount"] is None
    assert row["value_text"] == "some unreadable figure"
    failure = conn.execute("SELECT * FROM parse_failures").fetchone()
    assert failure["field_name"] == "rate_amount"


def test_run_records_when_the_page_has_no_tables(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             json={"details": {"body": "<p>no rates here</p>"}})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    rates.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM statutory_pay_rates").fetchone()["c"] == 0
    failure = conn.execute("SELECT * FROM parse_failures WHERE field_name='rates_table'").fetchone()
    assert failure is not None
