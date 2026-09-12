"""Temporal coverage navigator (BETA-097).

For one selected provider or authority, exactly which periods each source
holds. Nothing is gap-filled: a source's `periods` list is the distinct
periods actually held, and a source with nothing for the entity is shown,
not hidden.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import coverage_timeline
from pipeline.web.queries import QueryError


def _provider(conn):
    conn.execute("INSERT INTO providers (provider_key, canonical_name, "
                 "is_target, notes) VALUES ('cgl', 'Change Grow Live', 1, NULL)")
    conn.execute("INSERT INTO provider_identifiers (provider_key, scheme, "
                 "identifier, status, discovered_by) VALUES "
                 "('cgl', 'charity_number', '1099511', 'confirmed', 'config')")
    for year_end in ("2019-03-31", "2020-03-31", "2022-03-31"):
        conn.execute(
            "INSERT INTO charity_financials (charity_number, financial_year_end, "
            " source_url, retrieved_at, http_status, source_system, "
            " payload_sha256) VALUES ('1099511', %s, 'https://cc/x', "
            " '2026-01-01T00:00:00Z', 200, 'charity_commission', 'h')",
            (year_end,))
    conn.commit()


def test_periods_are_held_exactly_and_not_gap_filled(conn: sqlite3.Connection) -> None:
    _provider(conn)
    out = coverage_timeline.timeline(conn, provider_key="cgl")
    charity = next(s for s in out["sources"] if s["dataset_id"] == "charity-finance")
    assert charity["periods"] == ["2019", "2020", "2022"]   # 2021 stays a gap
    assert charity["held"] is True
    assert out["span"] == {"min": 2019, "max": 2022}
    assert out["years"] == [2019, 2020, 2021, 2022]         # axis is contiguous
    assert "never gap-filled" in out["note"].lower()
    assert out["entity"] == {"kind": "provider", "id": "cgl",
                              "name": "Change Grow Live"}


def test_a_source_with_no_data_is_shown_not_hidden(conn: sqlite3.Connection) -> None:
    _provider(conn)
    out = coverage_timeline.timeline(conn, provider_key="cgl")
    ids = {s["dataset_id"] for s in out["sources"]}
    assert {"nhs-job-adverts", "tribunals", "pfd-reports"} <= ids
    empty = next(s for s in out["sources"] if s["dataset_id"] == "tribunals")
    assert empty["held"] is False and empty["periods"] == []
    assert out["held_count"] == sum(1 for s in out["sources"] if s["held"])


def test_authority_probes_read_by_ons_code(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "('E09000007', 'Camden', 'london_borough', '1965-04-01', '2021', "
        " '2024', 'https://ons/x', '2026-01-01T00:00:00Z', 200, 'ons', 'h')")
    for fy in ("2023-24", "2024-25"):
        conn.execute(
            "INSERT INTO public_health_grants (ons_code, financial_year, "
            " grant_type, allocation_status, unit, amount, source_column_header, "
            " source_document, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) VALUES ('E09000007', %s, "
            " 'total_consolidated_public_health_grant', 'confirmed', 'gbp', "
            " 1000000, 'Grant', 'doc', 'https://g/x', '2026-01-01T00:00:00Z', "
            " 200, 'dhsc', 'h')", (fy,))
    conn.commit()
    out = coverage_timeline.timeline(conn, ons_code="E09000007")
    grant = next(s for s in out["sources"] if s["dataset_id"] == "public-health-grant")
    assert grant["periods"] == ["2023-24", "2024-25"] and grant["held"] is True
    assert out["entity"]["kind"] == "authority"


def test_exactly_one_endpoint_is_required(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        coverage_timeline.timeline(conn)
    with pytest.raises(QueryError):
        coverage_timeline.timeline(conn, provider_key="cgl", ons_code="E09000007")


def test_an_unknown_entity_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        coverage_timeline.timeline(conn, provider_key="nope")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/coverage_timeline" in openapi.document()["paths"]
