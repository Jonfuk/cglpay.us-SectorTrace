from __future__ import annotations

import pytest

from pipeline.modules import m13_la_budgets as budgets


# Shape of the real MHCLG RA sheet: a preamble stating the denomination,
# three self-describing marker rows, then the identifier header, then data.
def _real_shape_rows():
    return [
        ["Worksheet 2: Revenue Account Budget"],
        ["This worksheet contains 2 tables."],
        ["Data are reported in £ thousand."],
        ["Produced on a non-IAS19 basis"],
        ["Source: Local authorities' Revenue returns"],
        ["Last updated: 11 June 2026"],
        ["This row contains the data base Asset ID", "", "", "", "eduerl", "transpblopr", "transpblcrd"],
        ["This row contains section headings for", "", "", "", "Education Services", "Public Health", ""],
        ["This row contains the 'line number'", "", "", "", "110", "271", "272"],
        ["E-code", "ONS Code", "Local authority", "Class", "", "", ""],
        ["E3831", "E07000223", "Adur", "SD", "1,234", "3", "-199"],
        ["E9999", "England", "England total", "", "9,999", "9", "9"],
    ]


# --- units ------------------------------------------------------------------------

def test_detect_multiplier_from_the_sheets_own_preamble():
    assert budgets.detect_multiplier(_real_shape_rows()) == 1000


def test_detect_multiplier_handles_millions():
    assert budgets.detect_multiplier([["Data are reported in £ million."]]) == 1_000_000


def test_detect_multiplier_accepts_later_preamble_cells():
    rows = [
        ["Worksheet"],
        ["Notes", "", "The amounts are expressed in £000s."],
        ["E-code", "ONS Code", "Local authority"],
    ]
    assert budgets.detect_multiplier(rows) == 1000


def test_detect_multiplier_returns_none_when_absent():
    """Never a default: being wrong here is a 1,000x error on a public figure."""
    assert budgets.detect_multiplier([["Some sheet"], ["with no denomination"]]) is None


def test_amounts_are_null_when_the_multiplier_is_unknown():
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, None)
    assert extracted
    assert all(e["amount"] is None for e in extracted)
    # the verbatim cell is still kept
    assert any(e["value_text"] for e in extracted)


# --- structure detection --------------------------------------------------------------

def test_finds_header_row_by_ons_code_column():
    assert budgets.find_header_row(_real_shape_rows()) == 9


def test_marker_rows_are_found_by_their_own_labels():
    """Keyed on the sheet's self-description rather than fixed offsets: the
    column count changes between years (213 in 2026-27) and offsets drift.
    """
    rows = _real_shape_rows()
    assert budgets.find_marker_row(rows, budgets.ASSET_ID_MARKER) == 6
    assert budgets.find_marker_row(rows, budgets.SECTION_MARKER) == 7
    assert budgets.find_marker_row(rows, budgets.LINE_NUMBER_MARKER) == 8


def test_sheets_without_a_header_row_are_skipped():
    assert budgets.find_header_row([["Front page"], ["Notes"]]) is None


def test_section_headings_are_forward_filled():
    """A section heading appears once at the start of the columns it covers."""
    filled = budgets.forward_fill(["", "A", "", "", "B", ""], 6)
    assert filled == ["", "A", "A", "A", "B", "B"]


# --- extraction --------------------------------------------------------------------------

def test_extracts_one_row_per_authority_and_budget_line():
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    adur = [e for e in extracted if e["ons_code"] == "E07000223"]
    assert len(adur) == 3
    assert {e["line_code"] for e in adur} == {"eduerl", "transpblopr", "transpblcrd"}


def test_public_health_lines_carry_their_section():
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    ph = [e for e in extracted if e["section"] == "Public Health"]
    assert {e["line_code"] for e in ph} == {"transpblopr", "transpblcrd"}


def test_amounts_are_scaled_by_the_declared_multiplier():
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    by_code = {e["line_code"]: e for e in extracted if e["ons_code"] == "E07000223"}
    assert by_code["eduerl"]["amount"] == 1_234_000
    assert by_code["transpblopr"]["amount"] == 3_000


def test_negative_budget_lines_are_kept():
    """Recharges and income lines are legitimately negative."""
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    by_code = {e["line_code"]: e for e in extracted if e["ons_code"] == "E07000223"}
    assert by_code["transpblcrd"]["amount"] == -199_000


def test_accounting_parentheses_read_as_negative():
    assert budgets._to_number("(500)") == -500


def test_non_authority_rows_are_skipped():
    """England totals and footnotes have no ONS code and must not become rows."""
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    assert all(e["ons_code"].startswith("E0") or e["ons_code"].startswith("E1")
                for e in extracted)
    assert not any(e["ons_code"] == "England" for e in extracted)


def test_identifier_columns_are_not_treated_as_budget_lines():
    rows = _real_shape_rows()
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    assert not any(e["line_code"].lower() in ("ons code", "local authority", "class")
                    for e in extracted)


@pytest.mark.parametrize("code,expected", [
    ("E07000223", "local_authority"),
    ("E10000015", "local_authority"),
    ("E23000034", "police"),
    ("E31000001", "fire"),
    ("E47000007", "combined_authority"),
    ("E26000001", "national_park"),
    ("E50000001", "waste_authority"),
    ("E12000007", "greater_london_authority"),
    ("E92000001", "england_total"),
    ("E99000001", "other_precepting_body"),
])
def test_body_type_classification(code, expected):
    """MHCLG covers every precepting body, not just local authorities. Those
    have no row in `authorities`, and recording what they are keeps a correct
    absence from reading as a failed join. Prefixes were confirmed against the
    authority names the sheet itself publishes.
    """
    assert budgets.classify_body_type(code) == expected


def test_non_local_authority_rows_are_kept_and_labelled():
    rows = _real_shape_rows()
    rows.append(["E1234", "E23000034", "Some Police and Crime Commissioner", "PCC", "5", "6", "7"])
    structure = budgets.parse_budget_sheet(rows)
    extracted = budgets.extract_budget_rows(rows, structure, 1000)
    police = [e for e in extracted if e["ons_code"] == "E23000034"]
    assert police, "police body rows should be kept, not dropped"
    assert all(e["body_type"] == "police" for e in police)


def test_parse_budget_sheet_raises_without_a_header():
    with pytest.raises(budgets.BudgetParseError):
        budgets.parse_budget_sheet([["nothing"], ["useful"]])


# --- publication titles -------------------------------------------------------------------

def test_parse_publication_title():
    title = ("Local authority revenue expenditure and financing England: "
             "2026 to 2027 budget individual local authority data")
    assert budgets.parse_publication_title(title) == "2026-27"


@pytest.mark.parametrize("title", [
    # the aggregate release, not the per-authority one
    "Local authority revenue expenditure and financing England: 2026 to 2027 budget",
    "Local authority revenue expenditure and financing England: 2024 to 2025 outturn",
    "",
])
def test_parse_publication_title_rejects_other_releases(title):
    assert budgets.parse_publication_title(title) is None


# --- schema separation ----------------------------------------------------------------------

def test_budget_view_does_not_join_to_the_grant(conn):
    """Budgeted spend and grant allocation are different measurements from
    different departments; the view must not silently difference them.
    """
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='v_la_public_health_budget'").fetchone()["sql"]
    assert "public_health_grants" not in sql
    assert "budget" in sql.lower()


def test_budget_view_states_what_the_figure_is(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E07000223','Adur','non_metropolitan_district','2020-01-01','x','x','u','t',200,'s','h')")
    conn.execute(
        "INSERT INTO la_revenue_budgets (ons_code, financial_year, line_code, section, amount, "
        "source_document, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E07000223','2026-27','transpblopr','Public Health',3000,'d','u','t',200,'s','h')")
    row = conn.execute("SELECT * FROM v_la_public_health_budget").fetchone()
    assert row["budget_gbp"] == 3000
    assert "NOT what it was allocated" in row["basis_note"]
