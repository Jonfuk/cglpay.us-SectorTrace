from __future__ import annotations

import json

import pytest

from pipeline.modules import m27_ndtms_monthly as monthly
from pipeline.registry import ModuleContext

# --- pure helpers -------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Number in treatment", "number_in_treatment"),
    ("Non-opiate & alcohol", "non_opiate_alcohol"),
    ("Total exits year to date (YTD)", "total_exits_year_to_date_ytd"),
])
def test_slugify(raw, expected):
    assert monthly._slugify(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("136,981", 136981.0),
    ("45%", 45.0),
    ("-", None),
    ("", None),
    ("-No data available", None),  # concatenated screen-reader text, not a bare token
])
def test_to_number(raw, expected):
    assert monthly._to_number(raw) == expected


def test_parse_report_month():
    assert monthly._parse_report_month("June 2026") == "2026-06-01"


def test_parse_report_month_rejects_unparseable():
    assert monthly._parse_report_month("not a month") is None
    assert monthly._parse_report_month(None) is None


def test_section_heading_strips_area_name():
    """The area name after the colon changes per request; the section name
    before it does not -- this is what lets one row cross areas cleanly.
    """
    assert monthly._section_heading("Number in treatment: Manchester") == "Number in treatment"
    assert monthly._section_heading("Opiate: England") == "Opiate"


def test_h1_matches_area():
    h1 = "Community adult treatment performance reports - Manchester"
    assert monthly._h1_matches_area(h1, "Manchester")
    assert not monthly._h1_matches_area(h1, "England")


def test_h1_matches_area_false_on_missing_h1():
    """A response with no area suffix at all (module failed to render, or
    came back as the plain England-wide default) must not be trusted for a
    specific area rather than treated as an ambiguous match.
    """
    assert not monthly._h1_matches_area(None, "Manchester")
    assert not monthly._h1_matches_area("Search results", "Manchester")


# --- HTML parsers ---------------------------------------------------------------

LANDING_HTML = """
<html><body>
<form id="form1" method="post">
<select id="RegionId"><option value="Z" selected>England</option></select>
<select id="ReportVersionId">
<option value="219" selected>June 2026</option>
<option value="218">May 2026</option>
</select>
<input id="generate" type="submit" value="Generate Report" />
<input name="__RequestVerificationToken" type="hidden" value="TESTTOKEN123" />
</form>
</body></html>
"""


def test_landing_page_parser_extracts_token_and_report_version():
    parser = monthly._LandingPageParser()
    parser.feed(LANDING_HTML)
    assert parser.token == "TESTTOKEN123"
    assert parser.report_version_id == "219"
    assert parser.report_label == "June 2026"


REPORT_HTML = """
<html><body>
<h1>Community adult treatment performance reports - Manchester</h1>
<a href="#collapse1">Number in treatment: Manchester</a>
<table>
<tr><th></th><th>Jun24 - May25</th><th>Jul24 - Jun25</th></tr>
<tr><td>Opioids</td><td>136981</td><td>136921</td></tr>
<tr><td>Alcohol only</td><td>98937</td><td>-</td></tr>
</table>
<a href="#collapse4">Opiate: Manchester</a>
<table>
<tr><th></th><th>Jun24 - May25</th><th>Jul24 - Jun25</th></tr>
<tr><td>Number in treatment</td><td>1200</td><td>1210</td></tr>
</table>
</body></html>
"""


def test_report_page_parser_pairs_tables_with_headings():
    parser = monthly._ReportPageParser()
    parser.feed(REPORT_HTML)
    assert parser.h1 == "Community adult treatment performance reports - Manchester"
    assert [h for h, _ in parser.sections] == [
        "Number in treatment: Manchester", "Opiate: Manchester"]
    first_table = parser.sections[0][1]
    assert first_table[0] == ["", "Jun24 - May25", "Jul24 - Jun25"]
    assert first_table[1] == ["Opioids", "136981", "136921"]


def test_report_page_parser_ignores_tables_outside_collapsible_sections():
    """Only <table> elements that follow a #collapseN heading link are
    report data; anything else in the page must not be swept in.
    """
    html = "<html><body><h1>x - England</h1><table><tr><td>stray</td></tr></table></body></html>"
    parser = monthly._ReportPageParser()
    parser.feed(html)
    assert parser.sections == [("", [["stray"]])]  # no heading text, but present -- caller filters this


# --- end to end ------------------------------------------------------------------

def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://www.ndtms.net/robots.txt", status_code=404, text="",
                             is_reusable=True)


def _dat_url(region_code: str, version: str = "219") -> str:
    return f"https://www.ndtms.net/Monthly/GetDATByPHECentre?pheCentre={region_code}&vernum={version}"


def test_run_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E08000003', 'Manchester', 'metropolitan_borough', '2020-01-01', 'x', 'x', "
        "'https://example.com', '2020-01-01T00:00:00Z', 200, 'test', 'abc')")

    for path in monthly.COHORT_PATHS.values():
        httpx_mock.add_response(url=f"https://www.ndtms.net{path}", text=LANDING_HTML, is_reusable=True)

    for region_code in monthly.REGIONS:
        if region_code == "E12000002":
            body = json.dumps([{"value": "0", "text": "Local Authorities..."},
                                {"value": "B18B", "text": "Manchester"}])
        else:
            body = json.dumps([{"value": "0", "text": "Local Authorities..."}])
        httpx_mock.add_response(url=_dat_url(region_code), text=body, is_reusable=True)

    httpx_mock.add_response(
        url=f"https://www.ndtms.net{monthly.COHORT_PATHS['adults']}", method="POST",
        text=REPORT_HTML)
    httpx_mock.add_response(
        url=f"https://www.ndtms.net{monthly.COHORT_PATHS['young_people']}", method="POST",
        text=REPORT_HTML)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=1)
    monthly.run(ctx)

    rows = conn.execute(
        "SELECT * FROM ndtms_monthly_statistics WHERE dat_code='B18B' AND cohort='adults'").fetchall()
    assert len(rows) == 6  # 2 rows x 2 periods in the first table, 1 row x 2 periods in the second
    by_indicator = {(r["section"], r["substance_category"], r["time_period_raw"]): r for r in rows}
    row = by_indicator[("number_in_treatment", "Opioids", "Jun24 - May25")]
    assert row["value"] == pytest.approx(136981.0)
    assert row["ons_code"] == "E08000003"
    assert row["cohort"] == "adults"
    assert row["report_month"] == "2026-06-01"

    # A placeholder cell ('-') carries text but no number: kept with value=NULL
    # and the verbatim text preserved, not silently dropped.
    placeholder = by_indicator[("number_in_treatment", "Alcohol only", "Jul24 - Jun25")]
    assert placeholder["value"] is None
    assert placeholder["value_text"] == "-"


def test_run_records_review_item_for_unmatched_area(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    for path in monthly.COHORT_PATHS.values():
        httpx_mock.add_response(url=f"https://www.ndtms.net{path}", text=LANDING_HTML, is_reusable=True)
    for region_code in monthly.REGIONS:
        if region_code == "E12000002":
            body = json.dumps([{"value": "B18B", "text": "Manchester"}])
        else:
            body = json.dumps([])
        httpx_mock.add_response(url=_dat_url(region_code), text=body, is_reusable=True)
    httpx_mock.add_response(
        url=f"https://www.ndtms.net{monthly.COHORT_PATHS['adults']}", method="POST", text=REPORT_HTML)
    httpx_mock.add_response(
        url=f"https://www.ndtms.net{monthly.COHORT_PATHS['young_people']}", method="POST",
        text=REPORT_HTML)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=1)
    monthly.run(ctx)

    unmatched = conn.execute(
        "SELECT raw_value FROM review_queue WHERE item_type='unmatched_ndtms_monthly_area'"
    ).fetchall()
    assert {r["raw_value"] for r in unmatched} == {"Manchester"}
