"""Module 25: Skills for Care workforce intelligence.

The access-shape review (Phase 19, G2) verified the five workbooks on the
Data downloads page are fetchable, OGL per the data.gov.uk catalogue entry,
and robots-clean. These tests pin the parser to the real shape — a data
sheet whose header row names the standard columns — and the honest limits
around it: the appendix and trended workbooks are fetched and archived but
their shapes are not parsed, suppression markers are NULL not failures, and
a workbook this module cannot read is a review item, never a skip.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from pipeline.modules import m25_skills_for_care as sfc
from pipeline.registry import ModuleContext
from pipeline.xlsx import iter_sheet, read_sheet

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url=re.compile(r"https://www\.skillsforcare\.org\.uk/robots\.txt.*"),
                            status_code=200, text="", is_reusable=True)


def _xlsx_bytes(sheets: dict[str, list[list[str]]]) -> bytes:
    """A minimal workbook from row lists, written the way the real files are:
    shared strings, cells with r attributes, one sheet per name. Numbers are
    written as inline values (the real files write numbers directly, which is
    what the parser keys on).
    """
    import io
    from xml.sax.saxutils import escape, quoteattr

    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def string_index(value: str) -> int:
        if value not in shared_index:
            shared_index[value] = len(shared)
            shared.append(value)
        return shared_index[value]

    def cell(ref: str, value: str) -> str:
        if value == "":
            return f'<c r="{ref}"/>'
        try:
            float(value)
            return f'<c r="{ref}"><v>{value}</v></c>'
        except ValueError:
            idx = string_index(value)
            return f'<c r="{ref}" t="s"><v>{idx}</v></c>'

    def column_letters(index: int) -> str:
        letters = ""
        index += 1
        while index:
            index, rem = divmod(index - 1, 26)
            letters = chr(65 + rem) + letters
        return letters

    sheet_xml = []
    for name, rows in sheets.items():
        body = []
        for r, row in enumerate(rows, start=1):
            cells = "".join(cell(f"{column_letters(i)}{r}", v)
                            for i, v in enumerate(row))
            body.append(f'<row r="{r}">{cells}</row>')
        sheet_xml.append(
            f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>')

    shared_xml = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                  f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                  f'count="{len(shared)}" uniqueCount="{len(shared)}">'
                  + "".join(f"<si><t>{escape(s)}</t></si>" for s in shared)
                  + "</sst>")
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>' + "".join(
            f'<sheet name={quoteattr(name)} sheetId="{i + 1}" '
            f'r:id="rId{i + 1}"/>' for i, name in enumerate(sheets)) +
        '</sheets></workbook>')
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(len(sheets))) +
        '</Relationships>')

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("[Content_Types].xml",
                    ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                     '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                     + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                               f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                               for i in range(len(sheets))) +
                     '</Types>'))
        zf.writestr("_rels/.rels",
                    ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                     '<Relationship Id="rId1" '
                     'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                     'Target="xl/workbook.xml"/></Relationships>'))
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/sharedStrings.xml", shared_xml)
        for i, xml in enumerate(sheet_xml):
            zf.writestr(f"xl/worksheets/sheet{i + 1}.xml", xml)
    return buffer.getvalue()


def _data_sheet(rows: list[list[str]]) -> dict[str, list[list[str]]]:
    header = ["Year", "Area code", "Area Level", "Region", "Area", "Sector",
              "Service", "Job role group", "Job role", "Total posts",
              "Filled posts", "FTE Filled post", "FTE Ratio", "Employees",
              "Turnover rate", "Leavers", "Vacancy rate", "Vacant posts"]
    # pad the header to DX/DY (column 128) so the pay columns exist at their
    # real positions
    while len(header) <= 128:
        header.append(f"c{len(header)}")
    header[127] = "FTE Annual Pay"
    header[128] = "Hourly Pay"
    out = [header]
    out.extend(rows)
    return {"Region area 2024-25": out}


def _add_authority(conn, ons_code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'utla', '2023-01-01', '2023', '2026', "
        "'https://example.com/spine', '2026-01-01T00:00:00+00:00', 200, "
        "'test', 'abc')", (ons_code, name))


def _region_row(area_code: str = "E92000001", area: str = "England",
                level: str = "National", hourly: str = "13.32",
                fte: str = "25600", turnover: str = "0.23",
                vacancy: str = "0.07") -> list[str]:
    row = [""] * 129
    row[0] = "2024/25"
    row[1] = area_code
    row[2] = level
    row[3] = "England" if level != "National" else "England"
    row[4] = area
    row[5] = "All sectors - LA, IND and DPR"
    row[6] = "All services"
    row[7] = "All job roles"
    row[8] = "All job roles"
    row[14] = turnover
    row[16] = vacancy
    row[127] = fte
    row[128] = hourly
    return row


# --- the parser ---------------------------------------------------------------


def test_number_reading():
    assert sfc._as_number("13.32") == 13.32
    assert sfc._as_number("1,600,000") == 1600000.0
    assert sfc._as_number("3.91338268153E-06") == 3.91338268153e-06
    assert sfc._as_number("") is None
    assert sfc._as_number("  ") is None
    assert sfc._as_number("*") is None, "the suppression marker is a deliberate absence"


def _header_dict(**extra) -> dict[str, str]:
    """A header row in iter_sheet's shape: {column letter: column name}."""
    header = {"A": "Year", "B": "Area code", "C": "Area Level", "D": "Region",
              "E": "Area", "F": "Sector", "G": "Service", "H": "Job role group",
              "I": "Job role", "P": "Turnover rate", "R": "Vacancy rate",
              "DX": "FTE Annual Pay", "DY": "Hourly Pay"}
    header.update(extra)
    return header


def test_parse_estimates_reads_by_column_name():
    rows = [
        _header_dict(),
        {"A": "2024/25", "B": "E92000001", "C": "National", "D": "England",
         "E": "England", "F": "All sectors", "G": "All services",
         "H": "All job roles", "I": "All job roles", "P": "0.23",
         "R": "0.07", "DX": "25600", "DY": "13.32"},
    ]
    estimates, failures = sfc.parse_estimates(rows)
    assert failures == []
    assert len(estimates) == 1
    est = estimates[0]
    assert est["area_code"] == "E92000001"
    assert est["hourly_pay"] == 13.32
    assert est["fte_annual_pay"] == 25600.0
    assert est["turnover_rate"] == 0.23
    assert est["vacancy_rate"] == 0.07


def test_parse_estimates_skips_rows_without_identifiers():
    rows = [
        _header_dict(),
        {"A": "2024/25", "C": "National", "E": "England"},
        {"A": "2024/25", "B": "E92000001", "E": "England"},
    ]
    estimates, failures = sfc.parse_estimates(rows)
    assert estimates == []
    assert failures == []


def test_suppression_marker_is_null_not_a_failure():
    data = _data_sheet([_region_row(hourly="*", fte="*")])
    rows = iter_sheet(_xlsx_bytes(data), "Region area 2024-25")
    estimates, failures = sfc.parse_estimates(rows)
    assert failures == [], "the publisher's own suppression marker is not a parse failure"
    assert estimates[0]["hourly_pay"] is None
    assert estimates[0]["fte_annual_pay"] is None


def test_genuinely_unreadable_value_is_a_parse_failure():
    data = _data_sheet([_region_row(hourly="not a number")])
    rows = iter_sheet(_xlsx_bytes(data), "Region area 2024-25")
    estimates, failures = sfc.parse_estimates(rows)
    assert estimates[0]["hourly_pay"] is None
    assert ("hourly_pay", "not a number") in failures


# --- the reader ---------------------------------------------------------------


def test_reader_round_trips_shared_strings_and_numbers():
    sheets = {"S1": [["Name", "Value"], ["Alpha", "12.5"], ["Beta", ""]]}
    rows = read_sheet(_xlsx_bytes(sheets), "S1")
    # Trailing empty cells collapse: a row is as wide as its last value, and
    # nothing about the source is lost by not padding it back out.
    assert rows == [["Name", "Value"], ["Alpha", "12.5"], ["Beta"]]


def test_iter_sheet_returns_only_requested_columns():
    sheets = {"S1": [["A", "B", "C"], ["1", "2", "3"]]}
    rows = iter_sheet(_xlsx_bytes(sheets), "S1", keep={"A", "C"})
    assert rows == [{"A": "A", "C": "C"}, {"A": "1", "C": "3"}]


def test_iter_sheet_matches_read_sheet_content():
    sheets = {"S1": [["Year", "Area code"], ["2024/25", "E92000001"]]}
    assert read_sheet(_xlsx_bytes(sheets), "S1") == [
        ["Year", "Area code"], ["2024/25", "E92000001"]]


def test_unknown_sheet_is_refused():
    import pytest

    from pipeline.xlsx import XlsxError

    with pytest.raises(XlsxError):
        read_sheet(_xlsx_bytes({"S1": [["x"]]}), "nope")


# --- end to end ---------------------------------------------------------------


def test_run_parses_current_year_workbooks_and_records_the_rest(
        httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _add_authority(conn, "E92000001", "England")

    page = ('<html><a href="https://www.skillsforcare.org.uk/Adult-Social-Care-'
            'Workforce-Data/workforceintelligence/resources/Our-data/'
            'Current-year-data-download-regional-2024-25.xlsx">Regional</a>'
            '<a href="https://www.skillsforcare.org.uk/Adult-Social-Care-'
            'Workforce-Data/workforceintelligence/resources/Our-data/'
            'Trended-data-download-2016-17-to-2025-26.xlsx">Trended</a></html>')
    httpx_mock.add_response(
        url=re.compile(r".*About-our-data/Data-downloads\.aspx.*"),
        text=page, status_code=200, is_reusable=True)
    regional = _xlsx_bytes(_data_sheet([_region_row()]))
    httpx_mock.add_response(
        url=re.compile(r".*Current-year-data-download-regional-2024-25\.xlsx.*"),
        content=regional, status_code=200, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*Trended-data-download-2016-17-to-2025-26\.xlsx.*"),
        content=_xlsx_bytes({"Trended": [["Year"], ["2024/25"]]}),
        status_code=200, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    sfc.run(ctx)

    files = {r["file_url"]: dict(r) for r in conn.execute(
        "SELECT * FROM skills_for_care_files").fetchall()}
    assert len(files) == 2
    regional_row = next(v for k, v in files.items() if "regional" in k)
    assert regional_row["parse_status"] == "parsed"
    assert regional_row["row_count"] == 1
    trended_row = next(v for k, v in files.items() if "Trended" in k)
    assert trended_row["parse_status"] == "unreadable", (
        "the trended workbook is fetched and archived but its shape is not parsed")

    estimates = conn.execute(
        "SELECT * FROM skills_for_care_estimates").fetchall()
    assert len(estimates) == 1
    assert estimates[0]["area_code"] == "E92000001"
    assert estimates[0]["hourly_pay"] == 13.32

    # The trended file's unread shape is a review item, never a silent skip.
    items = {r["item_type"] for r in conn.execute(
        "SELECT item_type FROM review_queue").fetchall()}
    assert "skills_for_care_shape_unread" in items


def test_run_records_an_unreadable_workbook(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    page = ('<a href="https://www.skillsforcare.org.uk/Adult-Social-Care-'
            'Workforce-Data/workforceintelligence/resources/Our-data/'
            'Current-year-data-download-regional-2024-25.xlsx">Regional</a>')
    httpx_mock.add_response(
        url=re.compile(r".*About-our-data/Data-downloads\.aspx.*"),
        text=page, status_code=200, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*Current-year-data-download-regional-2024-25\.xlsx.*"),
        content=b"not a zip file", status_code=200, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    sfc.run(ctx)

    files = conn.execute("SELECT * FROM skills_for_care_files").fetchall()
    assert len(files) == 1
    assert files[0]["parse_status"] == "unreadable"
    assert conn.execute("SELECT COUNT(*) FROM parse_failures").fetchone()[0] == 1


def test_run_resolves_relative_workbook_links(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    page = ('<a href="/Adult-Social-Care-Workforce-Data/workforceintelligence/'
            'resources/Our-data/Current-year-data-download-regional-2024-25.xlsx">'
            'Regional</a>')
    httpx_mock.add_response(
        url=re.compile(r".*About-our-data/Data-downloads\.aspx.*"),
        text=page, status_code=200, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*Current-year-data-download-regional-2024-25\.xlsx.*"),
        content=b"not a zip file", status_code=200, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    sfc.run(ctx)

    row = conn.execute("SELECT * FROM skills_for_care_files").fetchone()
    assert row["file_url"].startswith("https://www.skillsforcare.org.uk/")


def test_run_page_unavailable_is_a_review_item(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    # 404 rather than 500: the client retries a 5xx six times before raising,
    # and a page that genuinely is not there answers 404 once.
    httpx_mock.add_response(
        url=re.compile(r".*About-our-data/Data-downloads\.aspx.*"),
        status_code=404, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=None)
    sfc.run(ctx)

    items = {r["item_type"] for r in conn.execute(
        "SELECT item_type FROM review_queue").fetchall()}
    assert "skills_for_care_page_unavailable" in items
    assert conn.execute("SELECT COUNT(*) FROM skills_for_care_files").fetchone()[0] == 0
