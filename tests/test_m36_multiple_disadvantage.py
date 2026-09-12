from __future__ import annotations

import pytest

from pipeline.modules import m30_statutory_homelessness as hclic
from pipeline.modules import m36_multiple_disadvantage as md

# Real header text and real England-row totals, downloaded and read directly
# from the January-March 2026 edition
# (MDIS_Tables_202603.ods, retrieved 2026-09-12) while writing
# docs/m30-multiple-disadvantage-feasibility.md. Adur's row in Table 2 is
# also the real published figure; the other local-authority rows below are
# illustrative (small numbers and one [x]/[z] placeholder case), the same
# convention tests/test_m30_statutory_homelessness.py uses for its own
# "Somewhere Unitary" row.

def _pct_sheet_rows():
    return [
        ["Table 1 - Duties owed where homelessness was prevented or relieved "
         "for households experiencing multiple disadvantage, January to "
         "March 2026, England, [note 1]"],
        ["Return to contents"],
        ["This worksheet contains one table."],
        ["Some cells refer to notes which can be found in a table on the "
         "notes worksheet."],
        ["Some shorthand is used in this table, [z] = not applicable, "
         "[x] = missing data."],
        ["Organisation Identification Code", "Area Name",
         "Duties owed where homelessness was prevented or relieved for "
         "households experiencing multiple disadvantage (%)[note 2]",
         "Assessed as owed a dutyOwed a prevention or relief dutyMultiple "
         "disadvantage total[note 3]",
         "Households who secured accommodation for 6 or more months "
         "following prevention duty endedMultiple disadvantage total",
         "Households who secured accommodation for 6 or more months "
         "following relief duty endedMultiple disadvantage total"],
        ["E92000001", "ENGLAND", "36.9%", "7,340", "640", "2,070"],
        ["E12000007", "London", "39.1%", "640", "30", "220"],
        ["[z]", "Rest of England", "36.7%", "6,700", "610", "1,850"],
        ["E07000066", "Basildon", "[x]", "[x]", "[x]", "[x]"],
    ]


def _assessed_sheet_rows():
    return [
        ["Table 2 - Duties owed for households experiencing multiple "
         "disadvantage, January to March 2026, England, [note 1], [note 3]"],
        ["Return to contents"],
        ["This worksheet contains one table."],
        ["Organisation Identification Code", "Area Name",
         "Assessed as owed a dutyOwed a prevention or relief dutyMultiple "
         "disadvantage total",
         "Assessed as owed a dutyOwed a prevention or relief dutyDomestic "
         "abuse victim total",
         "Assessed as owed a dutyOwed a prevention or relief dutyMental "
         "health total",
         "Assessed as owed a dutyOwed a prevention or relief dutySubstance "
         "dependency total",
         "Assessed as owed a dutyOwed a prevention or relief "
         "dutyHomelessness/ rough sleeping total",
         "Assessed as owed a dutyOwed a prevention or relief dutyInteraction "
         "with criminal justice system total"],
        ["E92000001", "ENGLAND", "7,340", "11,300", "25,960", "8,310",
         "12,240", "9,840"],
        ["E12000007", "London", "640", "1,600", "3,300", "690", "1,780", "1,060"],
        ["[z]", "Rest of England", "6,700", "9,700", "22,660", "7,620",
         "10,460", "8,780"],
        ["E07000223", "Adur", "4", "9", "35", "13", "6", "4"],
        ["E07000066", "Basildon", "[x]", "[x]", "[x]", "[x]", "[x]", "[x]"],
    ]


def _prevention_sheet_rows():
    return [
        ["Table 3 - Prevention duty ended with accommodation secured for 6 "
         "or more months for households experiencing multiple disadvantage, "
         "January to March 2026, England, [note 1]"],
        ["Return to contents"],
        ["Organisation Identification Code", "Area Name",
         "Households who secured accommodation for 6 or more months "
         "following prevention duty endedMultiple disadvantage total",
         "Households who secured accommodation for 6 or more "
         "monthsDomestic abuse victim total",
         "Households who secured accommodation for 6 or more monthsMental "
         "health total",
         "Households who secured accommodation for 6 or more "
         "monthsSubstance dependency total",
         "Households who secured accommodation for 6 or more monthsHomeless/ "
         "rough sleeping total",
         "Households who secured accommodation for 6 or more "
         "monthsInteraction with criminal justice system total"],
        ["E92000001", "ENGLAND", "640", "1,920", "4,810", "940", "980", "1,020"],
        ["E07000223", "Adur", "0", "1", "2", "1", "0", "0"],
    ]


def _relief_sheet_rows():
    return [
        ["Table 4 - Relief duty ended with accommodation secured for 6 or "
         "more months for households experiencing multiple disadvantage, "
         "January to March 2026, England, [note 1]"],
        ["Return to contents"],
        ["Organisation Identification Code", "Area Name",
         "Households who secured accommodation for 6 or more months "
         "following relief duty endedMultiple disadvantage total",
         "Households who secured accommodation for 6 or more "
         "monthsDomestic abuse victim total",
         "Households who secured accommodation for 6 or more monthsMental "
         "health total",
         # Real quirk (§5 of the feasibility report): this sheet says
         # "Substance misuse", the other two say "Substance dependency" —
         # the column locator must match both under one keyword.
         "Households who secured accommodation for 6 or more "
         "monthsSubstance misuse total",
         "Households who secured accommodation for 6 or more monthsHomeless/ "
         "rough sleeping total",
         "Households who secured accommodation for 6 or more "
         "monthsInteraction with criminal justice system total"],
        ["E92000001", "ENGLAND", "2,070", "2,420", "5,970", "2,390", "3,830", "2,550"],
        ["E07000223", "Adur", "1", "1", "3", "1", "1", "1"],
    ]


# --- percentage column ------------------------------------------------------

def test_locates_the_percentage_column():
    rows = _pct_sheet_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = md.locate_pct_column(rows, anchor)
    assert columns == {"md_pct": 2}


def test_percentage_column_missing_raises():
    rows = [["Organisation Identification Code", "Area Name", "Some other metric"],
            ["E92000001", "ENGLAND", "1"]]
    with pytest.raises(hclic.StatutoryHomelessnessParseError):
        md.locate_pct_column(rows, hclic.find_anchor_row(rows))


@pytest.mark.parametrize("raw,expected", [
    ("36.9%", 36.9), ("100%", 100.0), ("104.2%", 104.2),
    ("[x]", None), ("[z]", None), ("", None),
])
def test_to_pct_strips_the_percent_sign_and_handles_placeholders(raw, expected):
    assert md.to_pct(raw) == expected


# --- category columns, shared shape across all three stage sheets ----------

@pytest.mark.parametrize("rows_fn,expected", [
    (_assessed_sheet_rows, {
        "md_total": 2, "domestic_abuse_total": 3, "mental_health_total": 4,
        "substance_dependency_total": 5, "homelessness_rough_sleeping_total": 6,
        "criminal_justice_total": 7,
    }),
    (_prevention_sheet_rows, {
        "md_total": 2, "domestic_abuse_total": 3, "mental_health_total": 4,
        "substance_dependency_total": 5, "homelessness_rough_sleeping_total": 6,
        "criminal_justice_total": 7,
    }),
    (_relief_sheet_rows, {
        "md_total": 2, "domestic_abuse_total": 3, "mental_health_total": 4,
        # "Substance misuse" on this sheet, still claimed as
        # substance_dependency_total — see the sheet's own header comment.
        "substance_dependency_total": 5, "homelessness_rough_sleeping_total": 6,
        "criminal_justice_total": 7,
    }),
])
def test_locates_every_category_column_on_every_stage_sheet(rows_fn, expected):
    rows = rows_fn()
    anchor = hclic.find_anchor_row(rows)
    columns = md.locate_category_columns(rows, anchor)
    assert columns == expected


def test_category_columns_missing_raises():
    rows = [["Organisation Identification Code", "Area Name", "Some other metric"],
            ["E92000001", "ENGLAND", "1"]]
    with pytest.raises(hclic.StatutoryHomelessnessParseError):
        md.locate_category_columns(rows, hclic.find_anchor_row(rows))


# --- extraction --------------------------------------------------------------

def test_extracts_only_genuine_local_authority_rows():
    """England (E92), region (E12) and 'Rest of England' ('[z]') rows must
    not be extracted as if they were local authorities."""
    rows = _assessed_sheet_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = md.locate_category_columns(rows, anchor)
    entries = hclic.extract_a1_rows(rows, anchor, columns)
    codes = {e["ons_code"] for e in entries}
    assert "E92000001" not in codes
    assert "E12000007" not in codes
    assert "[z]" not in codes
    assert codes == {"E07000223", "E07000066"}


def test_extracted_values_match_the_real_published_adur_row_by_position():
    """Adur's row in the assessed sheet is the real published figure, not a
    fabricated one — see the module docstring above."""
    rows = _assessed_sheet_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = md.locate_category_columns(rows, anchor)
    entries = {e["ons_code"]: e for e in hclic.extract_a1_rows(rows, anchor, columns)}
    adur = entries["E07000223"]
    assert adur["md_total"] == "4"
    assert adur["domestic_abuse_total"] == "9"
    assert adur["mental_health_total"] == "35"
    assert adur["substance_dependency_total"] == "13"
    assert adur["homelessness_rough_sleeping_total"] == "6"
    assert adur["criminal_justice_total"] == "4"


def test_the_five_categories_do_not_sum_to_the_qualifying_total():
    """Documents the double-counting caveat (docs/CAVEATS.md's Module 36
    entry) against the real published England row: the five categories sum
    to several times the qualifying total, because qualifying for
    'multiple disadvantage' requires three or more of the five flags.
    """
    rows = _assessed_sheet_rows()
    anchor = hclic.find_anchor_row(rows)
    columns = md.locate_category_columns(rows, anchor)
    entries = {e["ons_code"]: e for e in hclic.extract_a1_rows(rows, anchor, columns)}
    england = entries.get("E92000001")
    assert england is None  # not extracted -- confirms the exclusion above
    # Read directly off the fixture's own England row instead.
    england_row = next(r for r in rows if r and r[0] == "E92000001")
    md_total = int(england_row[2].replace(",", ""))
    category_sum = sum(int(v.replace(",", "")) for v in england_row[3:8])
    assert category_sum > md_total * 5


# --- title / publication discovery, sharing m30's parse_quarter_title -------

@pytest.mark.parametrize("title,expected", [
    ("Multiple Disadvantage Detailed Local Authority Data: January to March 2026",
     ("2026-01-01", 2026, "January to March 2026")),
    ("Multiple Disadvantage Detailed Local Authority Data: October to "
     "December 2025 (revised)",
     ("2025-10-01", 2025, "October to December 2025")),
])
def test_md_title_re_parses_through_m30s_shared_helper(title, expected):
    assert hclic.parse_quarter_title(title, md.MD_TITLE_RE) == expected


@pytest.mark.parametrize("title", [
    "Detailed local authority level tables: January to March 2026",
    "Detailed local authority level tables: October to December 2025 (revised)",
    "Table A1 - Number of households by initial assessment",
])
def test_md_title_re_excludes_m30s_own_titles(title):
    """The reverse of m30's own exclusion test: m30's Table A1 titles must
    not be mistaken for Multiple Disadvantage attachments."""
    assert hclic.parse_quarter_title(title, md.MD_TITLE_RE) is None


def test_m30s_title_re_still_excludes_multiple_disadvantage_titles():
    """Regression guard: the title_re parameter must not have changed m30's
    own default behaviour, pinned by
    tests/test_m30_statutory_homelessness.py already, restated here because
    it is the exact assumption this module's sharing relies on.
    """
    assert hclic.parse_quarter_title(
        "Multiple Disadvantage Detailed Local Authority Data: July to "
        "September 2025 (revised)") is None
