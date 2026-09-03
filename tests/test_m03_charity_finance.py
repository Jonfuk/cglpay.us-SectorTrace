from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.charity_accounts_config import DEFAULT_PROFILE, AccountsProfile, profile_for
from pipeline.modules import m03_charity_finance as cf

FIXTURES = Path(__file__).parent / "fixtures"
REAL_NOTE = (FIXTURES / "charity_accounts_staff_note.txt").read_text(encoding="utf-8")


# --- units detection ----------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Group Group\n£’000 £’000", 1000),          # typographic apostrophe (real CGL accounts)
    ("amounts in £'000", 1000),                   # ascii apostrophe
    ("£000 £000", 1000),                          # no apostrophe
    ("figures are in thousands", 1000),
    ("Amounts are presented in £000s", 1000),
    ("Amounts are shown in millions", 1_000_000),
    ("£m £m", 1_000_000),
    ("£ million", 1_000_000),
])
def test_detect_amounts_multiplier(text, expected):
    assert cf.detect_amounts_multiplier(text) == expected


def test_detect_amounts_multiplier_returns_none_when_absent():
    """Must be None, never a default: a silent 1000x error here would
    misstate every pay figure in the campaign.
    """
    assert cf.detect_amounts_multiplier("Wages and salary costs 190,266 174,659") is None


def test_real_accounts_note_units_are_detected():
    assert cf.detect_amounts_multiplier(REAL_NOTE) == 1000


# --- number handling -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("190,266", 190266.0),
    ("1,438,676", 1438676.0),
    ("-", 0.0),      # accounts use a dash for nil
    ("–", 0.0),
    ("", 0.0),
])
def test_to_number(raw, expected):
    assert cf._to_number(raw) == expected


def test_to_number_returns_none_for_unparseable():
    assert cf._to_number("not a number") is None


def test_labelled_numbers_prefers_line_start_match():
    text = "Some prose mentioning wages and salaries 999 in passing\nWages and salaries 100 200"
    found = cf._match_labelled_numbers(text, ["wages and salaries"])
    assert found == [100.0, 200.0]  # the prose line must not win


def test_labelled_numbers_finds_mid_line_table_row():
    """Real case: pdfplumber interleaves a two-column layout, so a genuine
    table row surfaces appended to unrelated text (CGL 2021-2023 accounts).
    """
    line = "Trustee remuneration and expenses are disclosed in note 20. Average number of employees 4,933 4,380"
    found = cf._match_labelled_numbers(line, ["average number of employees"])
    assert found == [4933.0, 4380.0]


def test_labelled_numbers_rejects_prose_with_a_single_number():
    """The mid-line fallback needs two adjacent numbers, so narrative text
    mentioning the label followed by one figure must not match.
    """
    text = "During the year wages and salaries rose 12 per cent against forecast"
    assert cf._match_labelled_numbers(text, ["wages and salaries"]) is None


def test_real_note_agency_label_variants_both_supported():
    """CGL hyphenates 'third-party' from 2024 but not before; both spellings
    must resolve or the agency-spend series breaks in the middle.
    """
    hyphen = "£’000\nAgency and third-party organisations 27,719 26,333"
    plain = "£’000\nAgency and third party organisations 27,233 21,324"
    assert cf.extract_figures_from_text(hyphen, DEFAULT_PROFILE)["agency_and_third_party"] == 27_719_000
    assert cf.extract_figures_from_text(plain, DEFAULT_PROFILE)["agency_and_third_party"] == 27_233_000


# --- pay bands -----------------------------------------------------------------

def test_extract_pay_bands_from_real_note():
    bands, total = cf.extract_pay_bands(REAL_NOTE)
    assert len(bands) == 16
    assert total == 194
    first = bands[0]
    assert first["band_lower"] == 60000
    assert first["band_upper"] == 69999
    assert first["employees"] == 59
    # band totals must equal the sum of the bands, not be read off separately
    assert sum(b["employees"] for b in bands) == total


def test_extract_pay_bands_empty_when_absent():
    assert cf.extract_pay_bands("no bands here") == ([], None)


# --- full extraction against the real note -------------------------------------

def test_extract_figures_from_real_accounts_note():
    """Values asserted here were read by eye from CGL's published 2025
    accounts (staff costs note), so this test fails if parsing drifts.
    """
    f = cf.extract_figures_from_text(REAL_NOTE, DEFAULT_PROFILE)

    assert f["_problems"] == []
    assert f["amounts_multiplier"] == 1000
    assert f["wages_and_salaries"] == 190_266_000
    assert f["social_security_costs"] == 19_046_000
    assert f["agency_and_third_party"] == 27_719_000
    assert f["redundancy_costs"] == 371_000
    assert f["staff_costs_total"] == 248_872_000
    assert f["key_management_headcount"] == 7
    assert f["key_management_remuneration"] == 1_438_676


def test_headcount_and_fte_are_captured_separately():
    """The whole point of the caveat in the brief: these differ materially
    (5,715 vs 4,623) and must never be conflated.
    """
    f = cf.extract_figures_from_text(REAL_NOTE, DEFAULT_PROFILE)
    assert f["average_employees"] == 5715
    assert f["employees_basis"] == "headcount"
    assert f["average_employees_fte"] == 4623
    assert f["average_employees"] != f["average_employees_fte"]


def test_staff_costs_total_rejects_the_pay_band_total():
    """The note is two-column, so 'TOTAL' appears twice — once for staff
    costs (248,872) and once for the pay-band headcount (194). The smaller
    one must never be taken as a monetary total.
    """
    f = cf.extract_figures_from_text(REAL_NOTE, DEFAULT_PROFILE)
    assert f["staff_costs_total"] == 248_872_000
    assert f["staff_costs_total"] >= f["wages_and_salaries"]


def test_fallback_locator_finds_a_page_with_unanticipated_wording():
    """A note headed "Personnel costs" / "Employee benefit expenses" matches
    none of DEFAULT_PROFILE's groups; the shared fallback groups still
    locate it so the parser gets a page to work on."""
    pages = [
        "Trustees' report and other narrative.",
        "Personnel costs\n£’000\nWages and salaries 1,000 900\n"
        "Average number of employees 50 45",
    ]
    located = cf.find_staff_costs_pages(pages, DEFAULT_PROFILE)
    assert [i for i, _ in located] == [1]


def test_explicitly_labelled_total_staff_costs_is_used():
    note = ("£’000\n"
            "Wages and salaries 1,000 900\n"
            "Social security costs 100 90\n"
            "Total staff costs 1,100 990\n")
    f = cf.extract_figures_from_text(note, DEFAULT_PROFILE)
    assert f["staff_costs_total"] == 1_100_000
    assert not any("staff_costs_total" in p for p in f["_problems"])


def test_money_fields_are_null_when_units_unknown():
    """No multiplier -> no monetary values, plus a recorded problem."""
    note = "Wages and salary costs 190,266 174,659\nAverage number of employees 5,715 5,314"
    f = cf.extract_figures_from_text(note, DEFAULT_PROFILE)
    assert f["amounts_multiplier"] is None
    assert f["wages_and_salaries"] is None
    assert any("could not determine" in p for p in f["_problems"])
    # non-monetary counts are still usable
    assert f["average_employees"] == 5715


def test_missing_labels_are_reported_not_guessed():
    note = "£’000\nSomething unrelated 123 456"
    f = cf.extract_figures_from_text(note, DEFAULT_PROFILE)
    assert f["wages_and_salaries"] is None
    assert f["average_employees"] is None
    assert f["employees_basis"] == "unknown"  # never defaulted to headcount
    assert any("wages_and_salaries" in p for p in f["_problems"])


def test_custom_profile_matches_alternative_labels():
    profile = AccountsProfile(
        wages_and_salaries=["employee salary expenditure"],
        employees_basis="fte",
    )
    note = "£’000\nEmployee salary expenditure 1,000 900\nAverage number of employees 50 45"
    f = cf.extract_figures_from_text(note, profile)
    assert f["wages_and_salaries"] == 1_000_000
    assert f["employees_basis"] == "fte"


def test_profile_for_returns_default_when_unconfigured():
    assert profile_for("9999999") is DEFAULT_PROFILE


# --- accounts page link parsing -------------------------------------------------

def test_parse_accounts_links():
    html = (
        '<a aria-label="Download the accounts and TAR submitted on 31 March 2025, PDF" '
        'class="govuk-link accounts-download-link" href="https://example.com/doc?a=1&amp;b=2">Download</a>'
        '<a aria-label="Download the accounts and TAR submitted on 31 March 2024, PDF" '
        'class="govuk-link accounts-download-link" href="https://example.com/doc2">Download</a>'
    )
    docs = cf.parse_accounts_links(html)
    assert [d["financial_year_end"] for d in docs] == ["2025-03-31", "2024-03-31"]
    assert docs[0]["document_url"] == "https://example.com/doc?a=1&b=2"  # entities decoded


def test_parse_accounts_links_ignores_links_without_a_date():
    html = ('<a aria-label="Download something else, PDF" '
            'class="govuk-link accounts-download-link" href="https://example.com/x">D</a>')
    assert cf.parse_accounts_links(html) == []


def test_parse_accounts_links_empty_html():
    assert cf.parse_accounts_links("") == []


# --- the derived view and its mandatory caveats ---------------------------------

def _insert_extract(conn, **overrides):
    row = {
        "charity_number": "1079327", "financial_year_end": "2025-03-31",
        "amounts_multiplier": 1000, "wages_and_salaries": 190_266_000.0,
        "average_employees": 5715.0, "employees_basis": "headcount",
        "average_employees_fte": 4623.0,
        "source_url": "https://example.com/a.pdf", "retrieved_at": "2026-01-01T00:00:00Z",
        "http_status": 200, "source_system": "test", "payload_sha256": "abc",
    }
    row.update(overrides)
    cols = ", ".join(row)
    placeholders = ", ".join(f"%({c})s" for c in row)
    conn.execute(f"INSERT INTO charity_accounts_extracts ({cols}) VALUES ({placeholders})", row)


def test_view_computes_both_per_head_and_per_fte(conn):
    _insert_extract(conn)
    row = conn.execute("SELECT * FROM v_wage_per_employee").fetchone()
    # 190,266,000 / 5,715 and / 4,623 respectively
    assert round(row["indicative_wage_per_head"]) == 33292
    assert round(row["indicative_wage_per_fte"]) == 41156
    # the two differ by ~19% — quoting the per-head figure as a salary would
    # materially understate pay, which is why both are exposed
    assert row["indicative_wage_per_fte"] > row["indicative_wage_per_head"]


def test_view_never_exposes_a_column_called_average_salary(conn):
    _insert_extract(conn)
    columns = [d[0] for d in conn.execute("SELECT * FROM v_wage_per_employee").description]
    assert "indicative_wage_per_head" in columns
    assert not any("average_salary" in c or "avg_salary" in c for c in columns)


def test_view_carries_both_mandatory_annotation_columns(conn):
    _insert_extract(conn)
    row = conn.execute("SELECT * FROM v_wage_per_employee").fetchone()
    assert row["denominator_basis_note"]
    assert "headcount" in row["denominator_basis_note"]
    assert "NOT a salary" in row["denominator_basis_note"]
    assert row["numerator_scope_note"]
    assert "senior" in row["numerator_scope_note"].lower()


def test_view_excludes_rows_without_wages(conn):
    _insert_extract(conn, wages_and_salaries=None)
    assert conn.execute("SELECT COUNT(*) c FROM v_wage_per_employee").fetchone()["c"] == 0
