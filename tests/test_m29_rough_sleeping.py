from __future__ import annotations

import pytest

from pipeline.modules import m29_rough_sleeping as rough_sleeping


# Shape of the real MHCLG Table_1_Total / Table_5_Rates sheets: a title row,
# a "return to contents" row, a notes row naming the [x]/[z]/[n] shorthand,
# a coverage row, then the identifier header, then data — region and England
# aggregate rows carry "[z]" as their own authority code, exactly like
# Module 13's RA sheets.
def _real_shape_rows():
    return [
        ["Table 1: Estimated number of people sleeping rough, by local authority "
         "district and region, 2010 - 2025"],
        ["Return to Contents"],
        ["This worksheet contains one table. Some shorthand is used in this "
         "table, [x] = Not Available. [z] = Not Applicable. [n] = No data "
         "available as the authority was created through reorganisation."],
        ["This publication covers England only."],
        ["Local Authority Code", "Local Authority Name", "Region Code",
         "Region Name", "2010", "2011", "2025"],
        ["[z]", "[z]", "E92000001", "England", "1,768", "2,181", "4,793"],
        ["[z]", "[z]", "E12000007", "London", "415", "446", "1,137"],
        ["E07000223", "Adur", "E12000008", "South East", "0", "0", "3"],
        ["E08000025", "Birmingham", "E12000005", "West Midlands", "9", "12", "68"],
        ["E06000058", "New Unitary", "E12000009", "South West", "[n]", "[n]", "5"],
        ["E07000999", "Missing Year Cell", "E12000009", "South West", "2", "1"],
    ]


# --- header and structure detection ---------------------------------------------

def test_finds_header_row_by_local_authority_code_label():
    assert rough_sleeping.find_header_row(_real_shape_rows()) == 4


def test_raises_when_no_header_row_is_found():
    with pytest.raises(rough_sleeping.RoughSleepingParseError):
        rough_sleeping.extract_year_series([["Some other sheet"], ["with no header"]])


def test_raises_when_the_header_has_no_year_columns():
    rows = [["Local Authority Code", "Local Authority Name"],
            ["E07000223", "Adur"]]
    with pytest.raises(rough_sleeping.RoughSleepingParseError):
        rough_sleeping.extract_year_series(rows)


# --- extraction --------------------------------------------------------------------

def test_extracts_one_entry_per_authority_per_year():
    series = rough_sleeping.extract_year_series(_real_shape_rows())
    assert series[("E07000223", 2010)] == "0"
    assert series[("E07000223", 2025)] == "3"
    assert series[("E08000025", 2011)] == "12"


def test_excludes_region_and_england_aggregate_rows():
    """England and region rows carry [z] as their own authority code —
    Module 13's exact filter for the same reason: these are not local
    authorities and must not be stored as if they were one."""
    series = rough_sleeping.extract_year_series(_real_shape_rows())
    codes = {ons_code for (ons_code, _year) in series}
    assert "E92000001" not in codes  # England total lives under the [z] code, not this one
    assert all(rough_sleeping.ONS_CODE_RE.match(code) for code in codes)


def test_a_reorganisation_placeholder_is_kept_as_text_not_silently_dropped():
    """[n] means 'no data because the authority was created through
    reorganisation' — a real, documented answer, not a missing row."""
    series = rough_sleeping.extract_year_series(_real_shape_rows())
    assert series[("E06000058", 2010)] == "[n]"


def test_a_row_shorter_than_the_year_columns_does_not_crash():
    """'Missing Year Cell' has no 2025 column at all (a short row), which a
    real workbook can produce from a trailing blank cell odfpy compresses
    differently. The years it does have are still read."""
    series = rough_sleeping.extract_year_series(_real_shape_rows())
    assert series[("E07000999", 2010)] == "2"
    assert ("E07000999", 2025) not in series


# --- value parsing -----------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("3", 3), ("1,768", 1768), ("4,793", 4793),
    ("[x]", None), ("[z]", None), ("[n]", None), ("", None), ("-", None),
])
def test_to_int_handles_commas_and_placeholders(raw, expected):
    assert rough_sleeping._to_int(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("4.6", 4.6), ("0", 0.0), ("[x]", None), ("[z]", None), ("", None),
])
def test_to_float_handles_placeholders(raw, expected):
    assert rough_sleeping._to_float(raw) == expected


