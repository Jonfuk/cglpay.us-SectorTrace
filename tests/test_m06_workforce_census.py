from __future__ import annotations

import pytest

from pipeline.modules import m06_workforce_census as census

# --- segment classification ------------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("8% vacancy rate in the delivery workforce (treatment provider and LERO combined)", "delivery"),
    ("9% vacancy rate for the commissioning workforce", "commissioning"),
    ("50% of the treatment provider workforce were drug and alcohol workers", "treatment_provider"),
    ("Vacancy rates for all staff were 11%", "all_staff"),
    ("The rate was 12% last period", "unspecified"),
])
def test_classify_segment(line, expected):
    assert census.classify_segment(line) == expected


def test_multi_segment_line_is_ambiguous_not_guessed():
    """Real 2022 line naming all three segments. Resolving it by priority
    attributed the all-sectors total (11,851 WTE) to the commissioning
    workforce, which has 398 — a 30x error that reads as plausible.
    """
    line = ("Across all sectors 11,851 whole time equivalent (WTE) staff were reported, "
            "11,269 WTE (95%) for the treatment provider workforce, "
            "398 WTE (3%) commissioning staff")
    assert census.classify_segment(line) == "ambiguous"


def test_delivery_compound_term_beats_ambiguity():
    """'delivery workforce' is the census's own name for treatment providers
    and LEROs combined, so naming its components is not ambiguity.
    """
    line = "19% turnover rate in the delivery workforce (treatment provider and LERO combined)"
    assert census.classify_segment(line) == "delivery"


# --- metric extraction -------------------------------------------------------------

def test_extracts_percent_metric_value_first_phrasing():
    """2024 phrasing: '8% vacancy rate ...'"""
    line = "8% vacancy rate in the delivery workforce, in line with the 10% reported in 2023"
    metrics = census.extract_metrics_from_text(line, 6)
    vacancy = [m for m in metrics if m["metric"] == "vacancy_rate"]
    assert vacancy and vacancy[0]["value"] == 8
    assert vacancy[0]["unit"] == "percent"


def test_extracts_percent_metric_value_last_phrasing():
    """2023 phrasing: 'An overall vacancy rate of 10% was reported'"""
    line = "An overall vacancy rate of 10% was reported"
    metrics = census.extract_metrics_from_text(line, 5)
    assert [m["value"] for m in metrics if m["metric"] == "vacancy_rate"] == [10]


def test_extracts_wte_total():
    line = "There were 14,121 whole time equivalents (WTEs) reported in the 2024 census"
    metrics = census.extract_metrics_from_text(line, 6)
    wte = [m for m in metrics if m["metric"] == "wte_total"]
    assert wte and wte[0]["value"] == 14121
    assert wte[0]["unit"] == "wte"


def test_extracts_volunteer_and_full_time_shares():
    text = ("11% of the treatment provider workforce were unpaid or volunteers\n"
            "68% of the treatment provider workforce was contracted to work full time")
    metrics = {m["metric"]: m["value"] for m in census.extract_metrics_from_text(text, 6)}
    assert metrics["volunteer_share"] == 11
    assert metrics["full_time_share"] == 68


def test_every_metric_keeps_its_verbatim_source_line():
    line = "8% vacancy rate in the delivery workforce"
    for m in census.extract_metrics_from_text(line, 6):
        assert m["raw_text"] == line
        assert m["source_page"] == 6


def test_metrics_are_line_scoped():
    """A value must not be attached to a metric named on a different line."""
    text = "Vacancy rates are discussed below.\nSome unrelated sentence with 42% in it."
    assert census.extract_metrics_from_text(text, 1) == []


def test_implausible_percentages_are_rejected():
    assert census.extract_metrics_from_text("vacancy rate of 250%", 1) == []


def test_empty_text_yields_nothing():
    assert census.extract_metrics_from_text("", 0) == []
    assert census.extract_metrics_from_text(None, 0) == []


# --- report discovery ----------------------------------------------------------------

def test_discover_reports_finds_relative_and_absolute_links():
    html = '''
      <a href="/s/DA-workforce-census-FINAL-report-2024.pdf">2024</a>
      <a href="https://s3.eu-west-2.amazonaws.com/x/Drug%20and%20Alcohol%20Workforce%20Census%202023%20-%20V3.pdf">2023</a>
    '''
    reports = census.discover_reports(html)
    years = [r["census_year"] for r in reports]
    assert years == [2023, 2024]
    assert reports[1]["document_url"].startswith("https://www.wfbenchmarking.nhs.uk/s/")


def test_discover_reports_uses_census_year_not_publication_date():
    """Real 2022 filename carries a 20230301 publication stamp as well."""
    html = ('<a href="https://www.hee.nhs.uk/x/Drug%20and%20Alcohol%20Workforce%20Census%20'
            '2022%20Final%20Report%2020230301.pdf">2022</a>')
    reports = census.discover_reports(html)
    assert [r["census_year"] for r in reports] == [2022]


def test_discover_reports_ignores_unrelated_pdfs():
    html = ('<a href="/s/DA-FAQs-19724.pdf">FAQ</a>'
            '<a href="/s/some-other-2024-report.pdf">other</a>'
            '<a href="/s/mental-health-workforce-census-2024.pdf">different census</a>')
    assert census.discover_reports(html) == []


# --- verification markdown -------------------------------------------------------------

def test_verification_markdown_pairs_value_with_source_line():
    metrics = [{
        "metric": "vacancy_rate", "workforce_segment": "delivery", "value": 8.0,
        "unit": "percent", "source_page": 6,
        "raw_text": "8% vacancy rate in the delivery workforce",
    }]
    md = census.render_verification_markdown(2024, "https://example.com/r.pdf", metrics)
    assert "8% vacancy rate in the delivery workforce" in md
    assert "vacancy_rate" in md
    assert "https://example.com/r.pdf" in md
    # must tell the reader the years are not comparable
    assert "not like-for-like" in md


def test_verification_markdown_escapes_pipes_in_source_text():
    metrics = [{
        "metric": "wte_total", "workforce_segment": "unspecified", "value": 100.0,
        "unit": "wte", "source_page": 1, "raw_text": "a | b | c",
    }]
    md = census.render_verification_markdown(2024, "u", metrics)
    assert r"a \| b \| c" in md


def test_verification_markdown_handles_no_metrics():
    md = census.render_verification_markdown(2024, "u", [])
    assert "no metrics matched" in md


# --- schema guarantees -------------------------------------------------------------------

def test_metrics_table_has_no_provider_column(conn):
    """The census publishes sector aggregates only; attributing a figure to a
    named provider would be inference presented as measurement.
    """
    columns = [r[1] for r in conn.execute("PRAGMA table_info(workforce_census_metrics)")]
    assert not any("provider" in c for c in columns)


def test_metrics_default_to_unverified(conn):
    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, workforce_segment, value, "
        "unit, source_page, raw_text, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES (2024, 'vacancy_rate', 'delivery', 8, 'percent', 6, 'line', "
        "'https://example.com', '2026-01-01T00:00:00Z', 200, 'test', 'abc')")
    row = conn.execute("SELECT verified FROM workforce_census_metrics").fetchone()
    assert row["verified"] == 0
