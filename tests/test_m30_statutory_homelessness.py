from __future__ import annotations

import pytest

from pipeline.modules import m30_statutory_homelessness as hclic


# Shape 1: the older multi-row merged-header layout (2017-2025 files, both
# .xlsx and .ods), reconstructed from real downloaded quarters (2019 Q4,
# 2023 Q1/Q4, 2024 Q1) with genuine header text. Data values are Q1 2024's
# real published England totals.
def _old_shape_rows():
    return [
        ["Table A1 - Number of households by initial assessment of "
         "homelessness circumstances and needs\nEngland, January to March 2024"],
        ["", "", "", "", "Total number of households assessed1,2", "",
         "Total households assessed as owed a duty",
         "Threatened with homelessness - Prevention duty owed",
         "     Of which: due to service of valid Section 21 Notice",
         "Homeless - Relief duty owed", "",
         "Not threatened with homelessness within 56 days - no duty owed",
         "Withdrew application  before assessment - no duty owed",
         "Not eligible / no longer eligible - no duty owed"],
        ["", "", "", "", "Grand Total", "", "",
         "Threatened with homelessness – Prevention Duty owed",
         "Threatened with homelessness due to service of valid Section 21 "
         "Notice – Prevention Duty owed",
         "Already homeless – Relief Duty owed", "",
         "Not threatened with homelessness within 56 days",
         "Withdrew application  before assessment - no duty owed",
         "Not eligible / no longer eligible - no duty owed"],
        ["", "", "", "", "", "", "", "", "", "", "", "Number of households"],
        ["", "", "", "", "Total initial assessments1,2,6", "",
         "Assessed as owed a duty", "", "", "", "",
         "Not homeless nor threatened with homelessness within 56 days - "
         "no duty owed",
         "Withdrew application  before assessment - no duty owed",
         "Not eligible / no longer eligible - no duty owed", "",
         "Number of households\n in area5 (000s)"],
        ["", "", "", "", "", "", "Total owed a prevention or relief duty",
         "Threatened with homelessness within 56 days - \nPrevention duty owed",
         "Of which:", "Homeless - \nRelief duty owed4"],
        ["", "", "", "", "", "", "", "", "due to service of valid Section 21 Notice3"],
        ["E92000001", "ENGLAND", "", "", "96860", "", "88690", "39370",
         "6770", "49330", "", "4080", "3370", "720", "", "24209.0"],
        ["E12000007", "London", "", "", "20270", "", "18420", "7570",
         "1180", "10850", "", "840", "800", "220", "", "3659.5"],
        ["-", "Rest of England", "", "", "76580", "", "70280", "31800",
         "5590", "38480", "", "3240", "2570", "490", "", "20549.6"],
        ["E08000025", "Birmingham", "", "", "3500", "", "3100", "1400",
         "200", "1700", "", "250", "100", "50", "", "1145.0"],
        ["E06000058", "Somewhere Unitary", "", "", "[c]", "", "[c]", "[x]",
         "[z]", "[n]", "", "10", "5", "[c]", "", "80.0"],
    ]


# Shape 2: the newer flat single-header-row layout, from the real
# January-March 2026 file (England row's values are the actual published
# totals for that quarter).
def _flat_shape_rows():
    return [
        ["Organisation Identification Code", "Area Name",
         "Initial assessmentsTotal[note 2]",
         "Assessed as owed a dutyOwed a prevention or relief dutyTotal",
         "Assessed as owed a dutyThreatened with homelessness within 56 "
         "days, Prevention duty owed",
         "Assessed as owed a dutyThreatened with homelessness due to "
         "service of valid section 21 notice[note 3]",
         "Assessed as owed a dutyHomeless, Relief duty owed[note 4]",
         "No duty owedNot threatened with homelessness within 56 days",
         "No duty owedWithdrew application before assessment",
         "No duty owedNot eligible or no longer eligible",
         "Households in area(thousands)[note 5]"],
        ["E92000001", "ENGLAND", "92,200", "83,850", "39,200", "6,540",
         "44,650", "4,130", "3,600", "610", "24,637"],
        ["E12000007", "London", "18,490", "16,510", "6,670", "1,140",
         "9,840", "910", "950", "120", "3,598"],
        ["[z]", "Rest of England", "73,700", "67,340", "32,530", "5,400",
         "34,820", "3,220", "2,650", "490", "21,039"],
        ["E08000025", "Birmingham", "3,900", "3,400", "1,500", "300",
         "1,900", "300", "150", "50", "1,145"],
    ]


_EXPECTED_FIELDS = {
    "total_initial_assessments", "total_owed_duty", "prevention_duty_owed",
    "relief_duty_owed", "not_threatened_no_duty", "withdrew_no_duty",
    "not_eligible_no_duty", "households_in_area_thousands",
}


# --- anchor / column resolution ---------------------------------------------

@pytest.mark.parametrize("rows_fn", [_old_shape_rows, _flat_shape_rows])
def test_finds_the_england_anchor_row(rows_fn):
    rows = rows_fn()
    anchor = hclic.find_anchor_row(rows)
    assert rows[anchor][0] == "E92000001"


def test_raises_when_no_anchor_row_is_found():
    assert hclic.find_anchor_row([["nothing"], ["here"]]) is None


@pytest.mark.parametrize("rows_fn", [_old_shape_rows, _flat_shape_rows])
def test_resolves_every_required_column_in_both_real_shapes(rows_fn):
    rows = rows_fn()
    anchor = hclic.find_anchor_row(rows)
    columns = hclic.locate_a1_columns(rows, anchor)
    assert _EXPECTED_FIELDS <= columns.keys()
    # every claimed column index must be distinct -- no field stole another's
    assert len(set(columns.values())) == len(columns)


def test_old_shape_columns_match_known_real_positions():
    """Locked against the actual column positions in the real 2024 Q1
    file, confirmed by hand against MHCLG's own published England totals."""
    rows = _old_shape_rows()
    columns = hclic.locate_a1_columns(rows, hclic.find_anchor_row(rows))
    assert columns["total_initial_assessments"] == 4
    assert columns["total_owed_duty"] == 6
    assert columns["prevention_duty_owed"] == 7
    assert columns["relief_duty_owed"] == 9
    assert columns["not_threatened_no_duty"] == 11
    assert columns["withdrew_no_duty"] == 12
    assert columns["not_eligible_no_duty"] == 13


def test_flat_shape_columns_match_known_real_positions():
    rows = _flat_shape_rows()
    columns = hclic.locate_a1_columns(rows, hclic.find_anchor_row(rows))
    assert columns["total_initial_assessments"] == 2
    assert columns["total_owed_duty"] == 3
    assert columns["prevention_duty_owed"] == 4
    assert columns["relief_duty_owed"] == 6
    assert columns["not_threatened_no_duty"] == 7
    assert columns["withdrew_no_duty"] == 8
    assert columns["not_eligible_no_duty"] == 9
    assert columns["households_in_area_thousands"] == 10


def test_raises_when_required_columns_cannot_be_located():
    rows = [["Organisation Identification Code", "Area Name", "Some other metric"],
            ["E92000001", "ENGLAND", "1"]]
    with pytest.raises(hclic.StatutoryHomelessnessParseError):
        hclic.locate_a1_columns(rows, hclic.find_anchor_row(rows))


# --- extraction --------------------------------------------------------------

def test_extracts_only_genuine_local_authority_rows():
    """England (E92), region (E12) and 'Rest of England' ('-') rows must
    not be extracted as if they were local authorities -- unlike m29's
    source, this one puts real ONS codes in those rows, not a '[z]'
    placeholder, so the filter has to be prefix-aware, not just
    shape-aware. See ONS_CODE_RE's own comment."""
    rows = _old_shape_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = hclic.locate_a1_columns(rows, anchor)
    entries = hclic.extract_a1_rows(rows, anchor, columns)
    codes = {e["ons_code"] for e in entries}
    assert "E92000001" not in codes
    assert "E12000007" not in codes
    assert "-" not in codes
    assert codes == {"E08000025", "E06000058"}


def test_extracted_values_match_the_real_published_england_row_by_position():
    """Row values are read positionally once columns are resolved -- this
    checks Birmingham's row (a real local authority row, not the England
    total) comes back with the right value in the right field."""
    rows = _old_shape_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = hclic.locate_a1_columns(rows, anchor)
    entries = {e["ons_code"]: e for e in hclic.extract_a1_rows(rows, anchor, columns)}
    birmingham = entries["E08000025"]
    assert birmingham["total_initial_assessments"] == "3500"
    assert birmingham["prevention_duty_owed"] == "1400"
    assert birmingham["relief_duty_owed"] == "1700"


# --- value parsing, including [c] suppression not seen in m29's source -------

@pytest.mark.parametrize("raw,expected", [
    ("0", 0), ("3,500", 3500), ("96860", 96860),
    ("[x]", None), ("[z]", None), ("[n]", None), ("[c]", None),
    ("", None), ("-", None),
])
def test_to_int_handles_commas_and_all_four_placeholders(raw, expected):
    assert hclic.to_int(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("24,209.0", 24209.0), ("0", 0.0), ("[c]", None), ("", None),
])
def test_to_float_handles_placeholders(raw, expected):
    assert hclic.to_float(raw) == expected


# --- title / publication discovery -------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Detailed local authority level tables: January to March 2026",
     ("2026-01-01", 2026, "January to March 2026")),
    ("Detailed local authority level tables: October to December 2025 (revised)",
     ("2025-10-01", 2025, "October to December 2025")),
    ("Detailed local authority level homelessness figures: April to June 2017",
     ("2017-04-01", 2017, "April to June 2017")),
])
def test_parses_quarterly_titles(title, expected):
    assert hclic.parse_quarter_title(title) == expected


@pytest.mark.parametrize("title", [
    "Detailed local authority level tables: financial year 2019-20 (revised)",
    "Detailed local authority level tables: financial year 2024-25",
    "Detailed local authority level homelessness figures: 2014 to 2015",
    "Detailed local authority level homelessness figures: 2009 to 2016",
    "Detailed local authority level tables: July to September 2025 "
    "(revised) - Accessible",
    "Multiple Disadvantage Detailed Local Authority Data: July to "
    "September 2025 (revised)",
    "Table A1 - Number of households by initial assessment",
])
def test_excludes_non_quarterly_or_duplicate_titles(title):
    """Financial-year summaries would double-count quarters already read
    individually; Multiple Disadvantage is a different table set; an
    '- Accessible' title is a duplicate-format copy of a quarter already
    read under its primary title."""
    assert hclic.parse_quarter_title(title) is None
