from __future__ import annotations

import re

import pytest

from pipeline import fingertips_indicators as cfg
from pipeline.modules import m12_fingertips as ft
from pipeline.registry import ModuleContext

API = "https://fingertips.phe.org.uk/api"

# Header of a real Fingertips all_data CSV export.
CSV_HEADER = (
    "Indicator ID,Indicator Name,Parent Code,Parent Name,Area Code,Area Name,Area Type,"
    "Sex,Age,Category Type,Category,Time period,Value,Lower CI 95.0 limit,"
    "Upper CI 95.0 limit,Lower CI 99.8 limit,Upper CI 99.8 limit,Count,Denominator,"
    "Value note,Recent Trend,Compared to England value or percentiles,"
    "Compared to Regions (statistical) value or percentiles,Time period Sortable,"
    "New data,Compared to goal,Time period range"
)


def _csv(*rows: str) -> str:
    return "\n".join([CSV_HEADER, *rows])


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://fingertips.phe.org.uk/robots.txt",
                             status_code=200, text="", is_reusable=True)


def _seed_authority(conn, ons_code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (%s, %s, 'unitary', '2020-01-01', 'x', 'x', 'https://example.com', "
        "'2020-01-01T00:00:00Z', 200, 'test', 'abc')", (ons_code, name))


# --- area level classification -------------------------------------------------

@pytest.mark.parametrize("code,expected", [
    ("E92000001", "england"),
    ("E12000006", "region"),
    ("E06000022", "local_authority"),
    ("E08000025", "local_authority"),
    ("E09000002", "local_authority"),
    ("E10000003", "local_authority"),
    ("W06000001", "other"),
    ("", "other"),
])
def test_classify_area_level(code, expected):
    assert ft.classify_area_level(code) == expected


def test_england_row_is_not_treated_as_an_authority():
    """The England comparator row must never be mistaken for an LA value."""
    assert ft.classify_area_level("E92000001") != "local_authority"


# --- CSV parsing ------------------------------------------------------------------

def test_parse_indicator_csv_reads_a_real_row():
    row = ("92454,Adults in treatment at specialist drug misuse services: rate per 1000 population,"
           ",,E06000022,Bath and North East Somerset,Upper tier local authorities,Persons,18+ yrs,,,"
           "2023/24,5.5,5.1,5.9,,,320,58000,,,Not compared,Not compared,20230000,,,1y")
    parsed = ft.parse_indicator_csv(_csv(row))
    assert len(parsed) == 1
    r = parsed[0]
    assert r["indicator_id"] == 92454
    assert r["area_code"] == "E06000022"
    assert r["value"] == 5.5
    assert r["lower_ci_95"] == 5.1
    assert r["count_numerator"] == 320
    assert r["denominator"] == 58000
    assert r["time_period"] == "2023/24"


def test_parse_indicator_csv_reads_columns_by_name_not_position():
    """The export has gained columns over time, so fixed indices would shift."""
    header = "Area Code,Indicator ID,Value,Time period,Indicator Name"
    text = header + "\nE06000022,92454,7.7,2024/25,Some indicator"
    parsed = ft.parse_indicator_csv(text)
    assert parsed[0]["value"] == 7.7
    assert parsed[0]["indicator_id"] == 92454


def test_parse_indicator_csv_keeps_suppressed_values_as_null():
    """Disclosure markers must not silently become zero."""
    row = ("92454,Name,,,E06000022,Somewhere,UTLA,Persons,18+ yrs,,,2023/24,*,,,,,,,"
           "Value suppressed,,Not compared,Not compared,20230000,,,1y")
    parsed = ft.parse_indicator_csv(_csv(row))
    assert parsed[0]["value"] is None
    assert parsed[0]["value_note"] == "Value suppressed"


def test_parse_indicator_csv_skips_rows_without_area_code():
    row = "92454,Name,,,,,,,,,,2023/24,5.5,,,,,,,,,,,,,,"
    assert ft.parse_indicator_csv(_csv(row)) == []


def test_parse_indicator_csv_empty_input():
    assert ft.parse_indicator_csv(CSV_HEADER) == []


# --- indicator configuration --------------------------------------------------------

def test_configured_indicators_cover_the_brief_targets():
    topics = {v["topic"] for v in cfg.INDICATORS.values()}
    assert "numbers_in_treatment" in topics
    assert "successful_completions" in topics
    assert "waiting_times" in topics


def test_unmet_need_is_not_claimed_as_an_indicator():
    """Fingertips publishes prevalence, not unmet need. Nothing may be
    labelled as unmet need, and the module must not derive it.
    """
    slugs = {v["slug"] for v in cfg.INDICATORS.values()}
    topics = {v["topic"] for v in cfg.INDICATORS.values()}
    assert not any("unmet" in s for s in slugs)
    assert not any("unmet" in t for t in topics)
    assert "prevalence" in topics  # stored as what it actually is


def test_discontinued_indicators_use_their_own_area_type():
    """91123 and 91182 return nothing under the current geography (502) — they
    were discontinued before it — so they are fetched under 402 instead.
    """
    assert cfg.area_type_ids_for(91123) == [402]
    assert cfg.area_type_ids_for(91182) == [402]


def test_live_indicators_use_the_current_geography_only():
    """Fetching a live indicator under two vintages would produce two rows for
    the same authority-period, which naive aggregation would double-count.
    """
    assert cfg.area_type_ids_for(92454) == cfg.DEFAULT_AREA_TYPE_IDS
    assert cfg.area_type_ids_for(92454) == [502]


def test_indicator_ids_are_explicit_not_searched():
    """Guards the design choice: an id list, so the collected set cannot
    change silently when OHID adds or renames indicators.
    """
    assert all(isinstance(k, int) for k in cfg.INDICATORS)
    assert len(cfg.INDICATORS) >= 8


# --- end to end -----------------------------------------------------------------------

def _register_mocks(httpx_mock, csv_body: str):
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/indicator_metadata/by_indicator_id.*"),
        json={"92454": {"Descriptive": {"Name": "Adults in treatment at specialist drug misuse services",
                                          "Definition": "Rate per 1000"},
                         "Unit": {"Label": "per 1,000"}}})
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/all_data/csv/by_indicator_id.*"),
        content=csv_body.encode("utf-8"), is_reusable=True)


def test_run_stores_la_rows_and_joins_to_authorities(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _seed_authority(conn, "E06000022", "Bath and North East Somerset")
    monkeypatch.setattr(cfg, "INDICATORS", {92454: cfg.INDICATORS[92454]})
    monkeypatch.setattr(ft, "INDICATORS", {92454: cfg.INDICATORS[92454]})

    body = _csv(
        "92454,Drug treatment rate,,,E92000001,England,England,Persons,18+ yrs,,,2023/24,4.9,,,,,210293,42359366,,,,,20230000,,,1y",
        "92454,Drug treatment rate,,,E12000006,East of England,Region,Persons,18+ yrs,,,2023/24,4.2,,,,,1000,200000,,,,,20230000,,,1y",
        "92454,Drug treatment rate,,,E06000022,Bath and North East Somerset,UTLA,Persons,18+ yrs,,,2023/24,5.5,5.1,5.9,,,320,58000,,,,,20230000,,,1y",
    )
    _register_mocks(httpx_mock, body)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ft.run(ctx)

    rows = conn.execute("SELECT * FROM fingertips_la_values ORDER BY area_code").fetchall()
    assert len(rows) == 3
    levels = {r["area_code"]: r["area_level"] for r in rows}
    assert levels["E92000001"] == "england"
    assert levels["E12000006"] == "region"
    assert levels["E06000022"] == "local_authority"

    # ons_code set only for the authority row
    codes = {r["area_code"]: r["ons_code"] for r in rows}
    assert codes["E06000022"] == "E06000022"
    assert codes["E92000001"] is None


def test_view_exposes_only_local_authority_rows(httpx_mock, settings, conn, monkeypatch):
    """A national comparator must not be readable as an authority's value."""
    _allow_all_robots(httpx_mock)
    _seed_authority(conn, "E06000022", "Bath and North East Somerset")
    monkeypatch.setattr(cfg, "INDICATORS", {92454: cfg.INDICATORS[92454]})
    monkeypatch.setattr(ft, "INDICATORS", {92454: cfg.INDICATORS[92454]})

    body = _csv(
        "92454,Drug treatment rate,,,E92000001,England,England,Persons,18+ yrs,,,2023/24,4.9,,,,,1,2,,,,,20230000,,,1y",
        "92454,Drug treatment rate,,,E06000022,Bath and North East Somerset,UTLA,Persons,18+ yrs,,,2023/24,5.5,,,,,320,58000,,,,,20230000,,,1y",
    )
    _register_mocks(httpx_mock, body)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ft.run(ctx)

    view = conn.execute("SELECT * FROM v_fingertips_la_latest").fetchall()
    assert len(view) == 1
    assert view[0]["authority_name"] == "Bath and North East Somerset"
    assert view[0]["value"] == 5.5


def test_rerun_is_idempotent(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _seed_authority(conn, "E06000022", "Bath and North East Somerset")
    monkeypatch.setattr(cfg, "INDICATORS", {92454: cfg.INDICATORS[92454]})
    monkeypatch.setattr(ft, "INDICATORS", {92454: cfg.INDICATORS[92454]})

    body = _csv(
        "92454,Drug treatment rate,,,E06000022,Bath and North East Somerset,UTLA,Persons,18+ yrs,,,2023/24,5.5,,,,,320,58000,,,,,20230000,,,1y")
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/indicator_metadata/by_indicator_id.*"),
        json={"92454": {"Descriptive": {"Name": "x"}}}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/all_data/csv/by_indicator_id.*"),
        content=body.encode("utf-8"), is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ft.run(ctx)
    ft.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM fingertips_la_values").fetchone()["c"] == 1
