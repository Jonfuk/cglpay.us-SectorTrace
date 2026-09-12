from __future__ import annotations

import io

import pytest
from odf.opendocument import OpenDocumentSpreadsheet
from odf.table import Table, TableCell, TableRow
from odf.text import P

from pipeline.modules import m36_police_recorded_crime as prc

# --- discovering the current CSP-level attachment ---------------------------

def _attachment(title, content_type=prc.ODS_MIME, url="https://example.com/f.ods"):
    return {"title": title, "content_type": content_type, "url": url}


def test_picks_the_attachment_with_the_latest_end_year():
    """The page lists the current rolling window alongside four closed
    historical windows; the current one is always the one still being
    extended forward, so its own end year is always the largest."""
    attachments = [
        _attachment("Police recorded crime data by Community Safety "
                    "Partnership year ending March 2003 to year ending March 2007"),
        _attachment("Police recorded crime open data Community Safety "
                    "Partnership tables from year ending March 2008 to "
                    "year ending March 2011"),
        _attachment("Police recorded crime Community Safety Partnership "
                    "open data, year ending March 2021 to year ending "
                    "March 2026", url="https://example.com/current.ods"),
        _attachment("Police recorded crime Community Safety Partnership "
                    "open data tables, from year ending March 2012 to "
                    "year ending March 2015"),
    ]
    picked = prc.find_current_csp_attachment(attachments)
    assert picked["url"] == "https://example.com/current.ods"


def test_ignores_non_csp_and_non_ods_attachments():
    attachments = [
        _attachment("Police recorded crime open data Police Force Area "
                    "tables, year ending March 2013 onwards"),
        _attachment("Police recorded crime Community Safety Partnership "
                    "open data, year ending March 2021 to year ending "
                    "March 2026", content_type="application/pdf"),
    ]
    assert prc.find_current_csp_attachment(attachments) is None


def test_returns_none_when_nothing_matches():
    assert prc.find_current_csp_attachment([]) is None
    assert prc.find_current_csp_attachment(
        [_attachment("Outcomes open data, year ending March 2026")]) is None


def test_a_title_with_only_one_year_mention_does_not_match():
    """A malformed or unexpectedly-worded title should be skipped, not
    crash on a missing second year."""
    attachments = [_attachment(
        "Community Safety Partnership tables, year ending March 2026 only")]
    assert prc.find_current_csp_attachment(attachments) is None


# --- streaming the workbook --------------------------------------------------

_HEADER = list(prc.EXPECTED_HEADER)


def _make_ods(sheets: dict[str, list[list]]) -> bytes:
    """A minimal real .ods with one sheet per (name, rows) pair, numeric
    columns (Financial Quarter, Offence Count) written with a real
    `office:value` the way a spreadsheet application would, matching the
    real published file's own shape (verified during JON-34's research)."""
    doc = OpenDocumentSpreadsheet()
    for name, rows in sheets.items():
        table = Table(name=name)
        header_row = TableRow()
        for label in _HEADER:
            cell = TableCell(valuetype="string")
            cell.addElement(P(text=label))
            header_row.addElement(cell)
        table.addElement(header_row)
        for row in rows:
            tr = TableRow()
            for i, value in enumerate(row):
                if i in (1, 8):
                    cell = TableCell(valuetype="float", value=value)
                else:
                    cell = TableCell(valuetype="string")
                cell.addElement(P(text=str(value)))
                tr.addElement(cell)
            table.addElement(tr)
        doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.write(buf)
    return buf.getvalue()


def test_only_data_sheets_are_read():
    body = _make_ods({
        "Cover_sheet": [["Not", "a", "real", "row"]],
        "Notes": [["Some notes"]],
        "2020_21": [["2020/21", 1, "Avon and Somerset",
                     "Bath and North East Somerset", "Other drug offences",
                     "Drug offences", "Possession of drugs", "92C", 5]],
    })
    sheets_seen = {sheet for sheet, _cells in prc.iter_csp_sheet_rows(body)}
    assert sheets_seen == {"2020_21"}


def test_header_row_is_read_back_exactly():
    body = _make_ods({"2020_21": []})
    rows = list(prc.iter_csp_sheet_rows(body))
    assert len(rows) == 1
    sheet, cells = rows[0]
    assert sheet == "2020_21"
    assert tuple(text for text, _numeric in cells) == prc.EXPECTED_HEADER


def test_numeric_columns_carry_the_ods_value_alongside_the_text():
    body = _make_ods({"2020_21": [
        ["2020/21", 1, "Avon and Somerset", "Bath and North East Somerset",
         "Other drug offences", "Drug offences", "Possession of drugs",
         "92C", 5],
    ]})
    rows = list(prc.iter_csp_sheet_rows(body))
    _header, (sheet, data_cells) = rows
    assert sheet == "2020_21"
    quarter_cell = data_cells[1]
    count_cell = data_cells[8]
    assert quarter_cell == ("1", 1.0)
    assert count_cell == ("5", 5.0)


def test_a_trailing_filler_cell_does_not_expand_into_the_row():
    """A real sheet's rows end with one `table:number-columns-repeated`
    filler cell tens of thousands of columns wide -- expanding it would
    make every row far longer than the nine real columns."""
    body = _make_ods({"2020_21": [
        ["2020/21", 1, "Avon and Somerset", "Bath and North East Somerset",
         "Burglary", "Theft offences", "Residential burglary", "29B", 10],
    ]})
    rows = list(prc.iter_csp_sheet_rows(body))
    _header, (_sheet, data_cells) = rows
    assert len(data_cells) == len(prc.EXPECTED_HEADER)


# --- financial-year quarter arithmetic ---------------------------------------

@pytest.mark.parametrize("year,quarter,expected", [
    ("2025/26", 1, "2025-04-01"),
    ("2025/26", 2, "2025-07-01"),
    ("2025/26", 3, "2025-10-01"),
    ("2025/26", 4, "2026-01-01"),  # Q4 crosses into the second calendar year
    ("2020/21", 1, "2020-04-01"),
])
def test_financial_quarter_start_matches_home_office_convention(year, quarter, expected):
    assert prc.financial_quarter_start(year, quarter) == expected


@pytest.mark.parametrize("year,quarter", [
    ("not a year", 1), ("2025/26", 0), ("2025/26", 5), ("2025/26", None), ("", 1),
])
def test_financial_quarter_start_refuses_to_guess(year, quarter):
    assert prc.financial_quarter_start(year, quarter) is None


# --- cell value parsing -------------------------------------------------------

@pytest.mark.parametrize("pair,expected", [
    (("5", 5.0), 5), (("1,234", None), 1234), (("0", 0.0), 0),
    (("", None), None), (("not a number", None), None),
])
def test_to_int_cell_prefers_the_ods_numeric_value(pair, expected):
    assert prc._to_int_cell(pair) == expected


# --- CSP name matching --------------------------------------------------------

def test_normalise_csp_name_matches_the_authoritys_own_spelling():
    assert (prc._normalise_csp_name("Bath and North East Somerset")
            == prc._normalise_csp_name("Bath and North East Somerset"))
    assert prc._normalise_csp_name("Barking & Dagenham") == "barking and dagenham"


def test_authority_lookup_matches_published_csp_names(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E06000022', 'Bath and North East Somerset', 'unitary', '2020-01-01', 'x', 'x', "
        "'https://example.com', '2020-01-01T00:00:00Z', 200, 'test', 'abc')")
    lookup = prc.build_authority_lookup(conn)
    assert lookup[prc._normalise_csp_name("Bath and North East Somerset")] == "E06000022"


# --- assembling a stored row --------------------------------------------------

_PROVENANCE = {
    "source_url": "https://example.com/f.ods",
    "retrieved_at": "2026-09-12T00:00:00+00:00",
    "http_status": 200,
    "source_system": prc.SOURCE_SYSTEM,
    "payload_sha256": "abc123",
}


def _cells(*values) -> list[tuple[str, float | None]]:
    """Plain text cells (no ODS numeric fallback) for a hand-built row."""
    return [(str(v), None) for v in values]


def test_a_non_drug_offence_row_is_rejected_without_a_review_item():
    cells = _cells("2020/21", 1, "Avon and Somerset",
                    "Bath and North East Somerset", "Burglary",
                    "Theft offences", "Residential burglary", "29B", 10)
    record, reason = prc.build_drug_offence_row(cells, {}, _PROVENANCE)
    assert record is None
    assert reason == "not_drug_offence"


def test_the_offence_group_match_is_case_insensitive():
    """The CSP-level file itself uses 'Drug offences' (lower-case 'o'); a
    sibling Home Office file in the same publication family uses 'Drug
    Offences' (title case) for the same concept -- matched here regardless
    of which case a future edition uses."""
    lookup = {prc._normalise_csp_name("Bath and North East Somerset"): "E06000022"}
    cells = _cells("2020/21", 1, "Avon and Somerset",
                    "Bath and North East Somerset", "Other drug offences",
                    "DRUG OFFENCES", "Possession of drugs", "92C", 5)
    record, reason = prc.build_drug_offence_row(cells, lookup, _PROVENANCE)
    assert reason is None
    assert record["offence_subgroup"] == "Possession of drugs"


def test_an_unmatched_csp_name_is_rejected_not_guessed():
    """A combined CSP, a historic sub-district CSP, or a Welsh CSP (this
    source covers England and Wales) all have no exact match here -- this
    is a normal, expected outcome, not a crash."""
    cells = _cells("2020/21", 1, "South Wales", "Cardiff",
                    "Other drug offences", "Drug offences",
                    "Possession of drugs", "92C", 3)
    record, reason = prc.build_drug_offence_row(cells, {}, _PROVENANCE)
    assert record is None
    assert reason == "unmatched_csp"


def test_a_matched_row_carries_provenance_and_the_sources_own_names():
    lookup = {prc._normalise_csp_name("Bath and North East Somerset"): "E06000022"}
    cells = _cells("2025/26", 4, "Avon and Somerset",
                    "Bath and North East Somerset", "Other drug offences",
                    "Drug offences", "Possession of drugs", "92C", 5)
    record, reason = prc.build_drug_offence_row(cells, lookup, _PROVENANCE)
    assert reason is None
    assert record == {
        "ons_code": "E06000022",
        "csp_name": "Bath and North East Somerset",
        "financial_year": "2025/26",
        "financial_quarter": 4,
        "quarter_start": "2026-01-01",
        "offence_subgroup": "Possession of drugs",
        "offence_count": 5,
        "offence_count_text": "5",
        **_PROVENANCE,
    }


def test_an_unresolvable_quarter_is_flagged_rather_than_stored():
    lookup = {prc._normalise_csp_name("Bath and North East Somerset"): "E06000022"}
    cells = _cells("not a year", 1, "Avon and Somerset",
                    "Bath and North East Somerset", "Other drug offences",
                    "Drug offences", "Possession of drugs", "92C", 5)
    record, reason = prc.build_drug_offence_row(cells, lookup, _PROVENANCE)
    assert record is None
    assert reason == "unresolvable_quarter"
