"""Evidence discrepancy explorer (BETA-096).

Where two or more public sources report a different value for the same
verified entity and field, both are shown with their source; nothing is
reconciled, ranked, or called an error.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import discrepancy
from pipeline.web.queries import QueryError

_NOW = "2026-01-01T00:00:00Z"


def _cgl(conn):
    conn.execute("INSERT INTO providers (provider_key, canonical_name, "
                 "is_target, notes) VALUES ('cgl', 'Change Grow Live', 1, NULL)")


def _company(conn, name, number="07688213"):
    conn.execute(
        "INSERT INTO companies (company_number, provider_key, company_name, "
        " match_basis, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES (%s, 'cgl', %s, 'seed', 'https://ch/1', %s, 200, "
        " 'ch', 'h')", (number, name, _NOW))


def _cqc_provider(conn, name):
    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_name, provider_key, "
        " match_basis, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('1-1', %s, 'cgl', 'exact_name', "
        " 'https://cqc/1', %s, 200, 'cqc', 'h')", (name, _NOW))


def test_differing_names_are_surfaced_with_every_source(conn: sqlite3.Connection) -> None:
    _cgl(conn)
    _company(conn, "CHANGE GROW LIVE")
    _cqc_provider(conn, "Change, Grow, Live Services Limited")
    conn.commit()

    out = discrepancy.check(conn, provider_key="cgl")
    name = next(d for d in out["discrepancies"] if d["id"] == "legal_name")
    assert set(name["distinct_values"]) == {
        "Change Grow Live", "CHANGE GROW LIVE", "Change, Grow, Live Services Limited"}
    assert {o["source"] for o in name["observations"]} == {
        "SectorTrace canonical", "Companies House", "CQC provider register"}
    assert "never called an error" in out["note"].lower()
    # no field on a discrepancy claims a resolution
    for d in out["discrepancies"]:
        assert not ({"correct", "resolved", "error", "canonical"} & set(d))


def test_a_field_the_sources_agree_on_is_listed_as_agreed(conn: sqlite3.Connection) -> None:
    _cgl(conn)
    _company(conn, "CHANGE GROW LIVE")
    conn.execute("INSERT INTO provider_identifiers (provider_key, scheme, "
                 "identifier, status, discovered_by) VALUES "
                 "('cgl', 'company_number', '07688213', 'confirmed', 'config')")
    conn.commit()
    out = discrepancy.check(conn, provider_key="cgl")
    agreed = {a["id"]: a for a in out["agreed"]}
    assert agreed["company_number"]["value"] == "07688213"
    assert not any(d["id"] == "company_number" for d in out["discrepancies"])


def test_cqc_rating_channels_that_disagree_are_a_discrepancy(conn: sqlite3.Connection) -> None:
    _cgl(conn)
    _cqc_provider(conn, "Change Grow Live")  # provider_id '1-1' for the FK
    conn.execute(
        "INSERT INTO cqc_locations (location_id, provider_id, provider_key, "
        " location_name, overall_rating, overall_rating_date, "
        " bulk_overall_rating, bulk_overall_rating_date, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "('1-loc', '1-1', 'cgl', 'Camden hub', 'Good', '2024-01-01', "
        " 'Requires improvement', '2023-06-01', 'https://cqc/l', %s, 200, "
        " 'cqc', 'h')", (_NOW,))
    conn.commit()
    out = discrepancy.check(conn, provider_key="cgl")
    rating = next(d for d in out["discrepancies"] if d["id"].startswith("cqc_rating:"))
    srcs = {o["source"]: o["value"] for o in rating["observations"]}
    assert srcs == {"CQC syndication API": "Good",
                    "CQC bulk export": "Requires improvement"}


def test_exactly_one_endpoint_and_unknown_entity(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        discrepancy.check(conn)
    with pytest.raises(QueryError):
        discrepancy.check(conn, provider_key="nope")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/discrepancies" in openapi.document()["paths"]
