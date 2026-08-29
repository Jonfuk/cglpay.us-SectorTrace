from __future__ import annotations

import pytest

from pipeline.modules import m31_temporary_accommodation as ta
from pipeline.modules.m30_statutory_homelessness import (
    ODS_MIME,
    StatutoryHomelessnessParseError,
    read_workbook_sheet,
)


# Shape 1: the older multi-row header layout (2017-2025 files), from the
# real October-December 2019 workbook's Table TA1. Data values are that
# quarter's actual published England totals.
def _old_shape_rows():
    return [
        ["Table TA1 - Number of households bytype of temporary "
         "accommodation providedEngland, 31st December 2019"],
        ["", "", "", "", "Total number of households in TA1,2,3,4",
         "Number of households in area5(000s)",
         "Total number of households in TA per (000s)",
         "Total number of households in TA with children",
         "Total number of children in TA", "",
         "Bed and breakfast hotels (including shared annexes)"],
        ["", "", "", "", "", "", "", "", "", "", "Total number of households",
         "Total with children"],
        ["E92000001", "ENGLAND", "", "", "88,310", "23,386", "3.78",
         "62,560", "128,310", "", "7,330", "1,900"],
        ["E12000007", "London", "", "", "58,670", "3,545", "16.55",
         "43,910", "90,080", "", "3,400", "780"],
        ["-", "Rest of England", "", "", "29,640", "19,841", "1.49",
         "18,650", "38,230", "", "3,930", "1,120"],
        ["E07000223", "Adur", "", "", "53", "28", "1.87", "30", "45", "",
         "10", "5"],
    ]


# Shape 2: the newer flat single-header-row layout, from the real
# January-March 2026 file.
def _flat_shape_rows():
    return [
        ["Organisation Identification Code", "Area Name",
         "Households in TATotal[note 34]",
         "Households in area(thousands)[note 5]",
         "Households in TATotal(per thousand)Total",
         "Households in TA with childrenTotal", "Children in TATotal",
         "Households in B&Bs including shared annexesTotal"],
        ["E92000001", "ENGLAND", "135,580", "24,637", "5.5", "86,460",
         "177,530", "12,220"],
        ["[z]", "Rest of England", "59,560", "21,039", "2.8", "35,280",
         "75,920", "8,650"],
        ["E07000223", "Adur", "129", "28", "4.6", "63", "108", "0"],
    ]


_EXPECTED_FIELDS = {
    "total_households_ta", "households_ta_with_children", "children_in_ta",
    "households_in_area_thousands",
}


# --- column resolution -------------------------------------------------------

@pytest.mark.parametrize("rows_fn", [_old_shape_rows, _flat_shape_rows])
def test_resolves_every_required_column_in_both_real_shapes(rows_fn):
    rows = rows_fn()
    anchor = ta.find_anchor_row(rows)
    columns = ta.locate_ta1_columns(rows, anchor)
    assert _EXPECTED_FIELDS <= columns.keys()
    assert len(set(columns.values())) == len(columns)


def test_old_shape_total_column_is_not_the_per_thousand_rate_column():
    """Regression test for a real bug: the source appends footnote digits
    to the total column's own header with no separating space
    ("...in TA1,2,3,4"), and an earlier version of the column-matching
    regex required a word boundary right after "ta" -- which a digit
    directly following does not produce, since both count as \\w. That
    silently failed to match the true total column and let the per-1,000
    rate column (whose text also contains "households in ta", just
    further right in the row) win the claim instead. Caught by checking
    the resolved value against the real published England total (88,310,
    not the rate 3.78), not by the regex looking wrong on its own."""
    rows = _old_shape_rows()
    anchor = ta.find_anchor_row(rows)
    columns = ta.locate_ta1_columns(rows, anchor)
    england_column = columns["total_households_ta"]
    assert rows[anchor][england_column] == "88,310"


def test_old_shape_columns_match_known_real_positions():
    rows = _old_shape_rows()
    columns = ta.locate_ta1_columns(rows, ta.find_anchor_row(rows))
    assert columns["total_households_ta"] == 4
    assert columns["households_in_area_thousands"] == 5
    assert columns["households_ta_with_children"] == 7
    assert columns["children_in_ta"] == 8


def test_flat_shape_columns_match_known_real_positions():
    rows = _flat_shape_rows()
    columns = ta.locate_ta1_columns(rows, ta.find_anchor_row(rows))
    assert columns["total_households_ta"] == 2
    assert columns["households_in_area_thousands"] == 3
    assert columns["households_ta_with_children"] == 5
    assert columns["children_in_ta"] == 6


def test_raises_when_required_columns_cannot_be_located():
    rows = [["Organisation Identification Code", "Area Name", "Some other metric"],
            ["E92000001", "ENGLAND", "1"]]
    with pytest.raises(StatutoryHomelessnessParseError):
        ta.locate_ta1_columns(rows, ta.find_anchor_row(rows))


# --- extraction --------------------------------------------------------------

def test_extracts_only_genuine_local_authority_rows():
    rows = _old_shape_rows()
    anchor = ta.find_anchor_row(rows)
    columns = ta.locate_ta1_columns(rows, anchor)
    entries = ta.extract_ta1_rows(rows, anchor, columns)
    codes = {e["ons_code"] for e in entries}
    assert codes == {"E07000223"}


def test_flat_shape_extracted_values_match_the_real_published_row():
    rows = _flat_shape_rows()
    anchor = ta.find_anchor_row(rows)
    columns = ta.locate_ta1_columns(rows, anchor)
    entries = {e["ons_code"]: e for e in ta.extract_ta1_rows(rows, anchor, columns)}
    adur = entries["E07000223"]
    assert adur["total_households_ta"] == "129"
    assert adur["households_ta_with_children"] == "63"
    assert adur["children_in_ta"] == "108"


# --- the bed-and-breakfast breakdown (BETA-064) ----------------------------

def _bb_columns(rows):
    anchor = ta.find_anchor_row(rows)
    snapshot = ta.locate_ta1_columns(rows, anchor)
    return anchor, ta.locate_ta1_breakdown_columns(rows, anchor, snapshot)


def test_old_shape_splits_bb_households_and_with_children():
    _anchor, (measures, unknown) = _bb_columns(_old_shape_rows())
    assert set(measures) == {"bb_households", "bb_households_with_children"}
    assert unknown == []
    # The two claims are distinct columns and are not any snapshot column.
    assert len(set(measures.values())) == 2


def test_flat_shape_has_only_the_bb_households_total():
    _anchor, (measures, unknown) = _bb_columns(_flat_shape_rows())
    assert set(measures) == {"bb_households"}
    assert unknown == []


def test_bb_values_match_the_real_published_rows():
    rows = _old_shape_rows()
    anchor, (measures, _unknown) = _bb_columns(rows)
    by_code = {e["ons_code"]: e for e in ta.extract_ta1_rows(rows, anchor, measures)}
    assert by_code["E07000223"]["bb_households"] == "10"
    assert by_code["E07000223"]["bb_households_with_children"] == "5"

    flat = _flat_shape_rows()
    f_anchor, (f_measures, _u) = _bb_columns(flat)
    f_by_code = {e["ons_code"]: e
                 for e in ta.extract_ta1_rows(flat, f_anchor, f_measures)}
    assert f_by_code["E07000223"]["bb_households"] == "0"


def test_an_unrecognised_bb_column_is_reported_not_guessed():
    rows = [
        ["Organisation Identification Code", "Area Name",
         "Households in TATotal", "Households in area(thousands)",
         "Households in TA with childrenTotal", "Children in TATotal",
         "Households in B&Bs Total number of households",
         "Households in B&Bs Total for more than 6 weeks"],
        ["E92000001", "ENGLAND", "135580", "24637", "86460", "177530", "12220", "3100"],
        ["E07000223", "Adur", "129", "28", "63", "108", "10", "4"],
    ]
    _anchor, (measures, unknown) = _bb_columns(rows)
    assert set(measures) == {"bb_households"}
    assert any("more than 6 weeks" in text for text in unknown)


def test_no_bb_column_is_not_an_error():
    rows = [
        ["Organisation Identification Code", "Area Name",
         "Households in TATotal", "Households in area(thousands)",
         "Households in TA with childrenTotal", "Children in TATotal"],
        ["E92000001", "ENGLAND", "135580", "24637", "86460", "177530"],
        ["E07000223", "Adur", "129", "28", "63", "108"],
    ]
    _anchor, (measures, unknown) = _bb_columns(rows)
    assert measures == {} and unknown == []


# --- the shared sheet-name-fallback fix, exercised through this module -------

def test_reads_the_ta1_sheet_under_its_real_misnamed_variant():
    """A real edition (January-March 2023) published Table TA1 under the
    sheet name 'TA1_' (trailing underscore) while every other sheet in the
    same workbook -- including A1, already read by Module 30 -- was named
    normally. read_workbook_sheet (shared with Module 30) must resolve
    this without guessing among multiple candidates."""
    import io

    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    doc = OpenDocumentSpreadsheet()
    table = Table(name="TA1_")
    for values in [["Organisation Identification Code", "Area Name",
                     "Households in TATotal", "Households in area(thousands)",
                     "rate", "Households in TA with children",
                     "Children in TATotal"],
                   ["E92000001", "ENGLAND", "135580", "24637", "5.5",
                    "86460", "177530"]]:
        row = TableRow()
        for value in values:
            cell = TableCell()
            cell.addElement(P(text=value))
            row.addElement(cell)
        table.addElement(row)
    doc.spreadsheet.addElement(table)
    buf = io.BytesIO()
    doc.write(buf)

    rows = read_workbook_sheet(buf.getvalue(), ODS_MIME, "TA1")
    anchor = ta.find_anchor_row(rows)
    assert anchor is not None
    columns = ta.locate_ta1_columns(rows, anchor)
    assert rows[anchor][columns["total_households_ta"]] == "135580"


def test_raises_rather_than_guess_when_no_sheet_matches_even_loosely():
    import io

    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table

    doc = OpenDocumentSpreadsheet()
    doc.spreadsheet.addElement(Table(name="SomethingElse"))
    buf = io.BytesIO()
    doc.write(buf)

    with pytest.raises(StatutoryHomelessnessParseError):
        read_workbook_sheet(buf.getvalue(), ODS_MIME, "TA1")
