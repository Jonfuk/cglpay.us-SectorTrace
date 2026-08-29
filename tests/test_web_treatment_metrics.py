"""Treatment metric catalogue (BETA-075).

The metric catalogue is read before a chart: definition, unit, whether a 95%
CI is published, the exact periods held, authority/England coverage and
provenance. It is computed from the same tables the treatment page charts, so
a catalogue row cannot claim coverage the chart does not have. Missing periods
stay missing — never zeroed or interpolated.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import public_queries as pq


@pytest.fixture
def treatment(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute(
        "INSERT INTO fingertips_indicators (indicator_id, indicator_name, slug, "
        " topic, substance, definition, unit, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "(2201, 'Adults in treatment: opiates', 'a', 'numbers_in_treatment', "
        " 'opiates', 'Number of adults in structured treatment.', 'count', "
        " 'https://ft.example/2201', '2026-08-01T00:00:00Z', 200, 'ohid', 'i1')")
    conn.execute(
        "INSERT INTO fingertips_indicators (indicator_id, indicator_name, slug, "
        " topic, substance, definition, unit, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "(2202, 'Completions: alcohol', 'b', 'successful_completions', "
        " 'alcohol', 'Planned completions.', 'percent', 'https://ft.example/2202', "
        " '2026-08-01T00:00:00Z', 200, 'ohid', 'i2')")
    rows = [
        ("2021/22", 202122, 1200, None, None, "local_authority", "E08000025"),
        ("2022/23", 202223, 1310, None, None, "local_authority", "E08000025"),
        ("2023/24", 202324, 1288, 1200, 1370, "local_authority", "E08000025"),
        ("2023/24", 202324, 380000, None, None, "england", "E92000001"),
    ]
    for tp, ts, val, lo, hi, level, ons in rows:
        conn.execute(
            "INSERT INTO fingertips_la_values (indicator_id, area_code, "
            " area_type_id, time_period, area_name, ons_code, area_level, value, "
            " lower_ci_95, upper_ci_95, time_period_sortable, source_url, "
            " retrieved_at, http_status, source_system, payload_sha256) VALUES "
            "(2201, ?, 102, ?, 'x', ?, ?, ?, ?, ?, ?, 'https://ft.example/v', "
            " '2026-08-01T00:00:00Z', 200, 'ohid', ?)",
            (ons, tp, ons, level, val, lo, hi, ts, f"v{ts}{level}"))
    conn.commit()
    return conn


def test_catalogue_carries_the_metadata_before_a_chart(treatment) -> None:
    out = pq.treatment_metrics(treatment)
    by_key = {m["key"]: m for m in out["metrics"]}

    opiates = by_key["fingertips:2201"]
    assert opiates["unit"] == "count"
    assert opiates["definition"]
    assert opiates["has_confidence_interval"] is True   # one row has a CI
    assert opiates["periods"] == ["2021/22", "2022/23", "2023/24"]
    assert opiates["period_range"] == ["2021/22", "2023/24"]
    assert opiates["period_count"] == 3
    assert opiates["authority_count"] == 1
    assert opiates["england_available"] is True
    assert opiates["source_url"] == "https://ft.example/2201"


def test_a_metric_with_no_values_reports_no_coverage_not_zero(treatment) -> None:
    out = pq.treatment_metrics(treatment)
    completions = next(m for m in out["metrics"] if m["key"] == "fingertips:2202")
    assert completions["periods"] == []          # missing, not [0]
    assert completions["period_range"] is None
    assert completions["has_confidence_interval"] is False
    assert completions["authority_count"] == 0
    assert completions["england_available"] is False


def test_periods_are_exactly_what_was_published_in_order(treatment) -> None:
    # No interpolation: a gap year is simply absent from the list.
    treatment.execute(
        "DELETE FROM fingertips_la_values "
        "WHERE indicator_id = 2201 AND time_period = '2022/23'")
    treatment.commit()
    opiates = next(m for m in pq.treatment_metrics(treatment)["metrics"]
                   if m["key"] == "fingertips:2201")
    assert opiates["periods"] == ["2021/22", "2023/24"]
    assert opiates["period_count"] == 2


def test_the_route_and_catalogue_list_it() -> None:
    from pipeline.web import openapi
    doc = openapi.document()
    assert "/api/v1/treatment_metrics" in doc["paths"]
