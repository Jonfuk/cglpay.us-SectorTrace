"""The public CQC-registered-location explorer (BETA-065).

What this pins: only tracked providers' locations are returned, the column
set is an allowlist with no personal data, the six filters and the facets
work, `without_coordinate` is honest, and the caveat says in words that this
is not a service map.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import public_queries
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute(
        "INSERT INTO providers (provider_key, canonical_name, is_target) "
        "VALUES ('cgl', 'Change Grow Live', 1), ('wdp', 'WDP', 0)")
    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_key, provider_name, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('P1', 'cgl', 'Change Grow Live', 'https://cqc/p1', "
        " '2026-08-01T00:00:00Z', 200, 'cqc', 'h')")

    def loc(location_id, **kw):
        cols = {
            "location_id": location_id, "provider_id": "P1",
            "provider_key": kw.get("provider_key", "cgl"),
            "location_name": kw.get("name", location_id),
            "latitude": kw.get("lat"), "longitude": kw.get("lon"),
            "local_authority_raw": kw.get("la_raw", "Leeds"),
            "local_authority_ons_code": kw.get("ons", "E08000035"),
            "region": kw.get("region", "Yorkshire and The Humber"),
            "registration_status": kw.get("status", "Registered"),
            "overall_rating": kw.get("rating"),
            "bulk_overall_rating": kw.get("bulk_rating"),
            "regulated_activities": kw.get("activities",
                                          "Treatment of disease, disorder or injury"),
            "service_types": kw.get("services", "Substance misuse services"),
        }
        placeholders = ", ".join("%s" for _ in cols)
        conn.execute(
            f"INSERT INTO cqc_locations ({', '.join(cols)}, source_url, "
            f" retrieved_at, http_status, source_system, payload_sha256) "
            f"VALUES ({placeholders}, 'https://cqc/{location_id}', "
            f" '2026-08-01T00:00:00Z', 200, 'cqc', 'h')",
            list(cols.values()))

    loc("L1", name="Leeds hub", lat=53.80, lon=-1.55, rating="Good")
    loc("L2", name="Bradford annexe", lat=53.79, lon=-1.75,
        status="Registered", bulk_rating="Requires improvement",
        services="Substance misuse services,Community health care services")
    loc("L3", name="No coordinate site", la_raw="Wakefield",
        ons="E08000036", rating="Outstanding")
    # A location with no provider_key — matched to nothing, must never appear.
    loc("L9", provider_key=None, name="Unmatched", lat=51.5, lon=-0.1)
    conn.commit()
    return conn


def test_only_tracked_provider_locations_are_returned(warehouse):
    result = public_queries.cqc_locations(warehouse)
    ids = {row["location_id"] for row in result["results"]}
    assert ids == {"L1", "L2", "L3"}
    assert result["total"] == 3


def test_no_personal_or_off_allowlist_column_is_returned(warehouse):
    row = public_queries.cqc_locations(warehouse)["results"][0]
    allowed = set(public_queries._CQC_LOCATION_COLUMNS) | {
        "provider_name", "rating_source"}
    assert set(row) <= allowed
    for banned in ("person_name", "contact_ref", "person_role"):
        assert banned not in row


def test_the_rating_falls_back_to_the_bulk_export_and_says_so(warehouse):
    by_id = {r["location_id"]: r
             for r in public_queries.cqc_locations(warehouse)["results"]}
    assert by_id["L1"]["overall_rating"] == "Good"
    assert by_id["L1"]["rating_source"] == "api"
    assert by_id["L2"]["overall_rating"] == "Requires improvement"
    assert by_id["L2"]["rating_source"] == "bulk_export"


def test_each_filter_narrows_the_result(warehouse):
    q = public_queries.cqc_locations
    assert {r["location_id"] for r in q(warehouse, rating="Outstanding")["results"]} == {"L3"}
    assert {r["location_id"] for r in q(warehouse, rating="Requires improvement")["results"]} == {"L2"}
    assert q(warehouse, authority_ons_code="E08000036")["total"] == 1
    assert q(warehouse, registration_status="Registered")["total"] == 3
    assert q(warehouse, registration_status="Deregistered")["total"] == 0
    # Exact service-type token, not a substring of another token.
    assert q(warehouse, service_type="Substance misuse services")["total"] == 3
    assert q(warehouse, service_type="misuse")["total"] == 0
    assert q(warehouse, service_type="Community health care services")["total"] == 1
    # Contains match for the comma-bearing activity name.
    assert q(warehouse, regulated_activity="disease, disorder")["total"] == 3
    assert q(warehouse, provider_key="wdp")["total"] == 0


def test_without_coordinate_is_counted_for_the_current_filter(warehouse):
    result = public_queries.cqc_locations(warehouse)
    assert result["without_coordinate"] == 1
    only_wakefield = public_queries.cqc_locations(warehouse, authority_ons_code="E08000036")
    assert only_wakefield["without_coordinate"] == 1
    assert public_queries.cqc_locations(
        warehouse, authority_ons_code="E08000035")["without_coordinate"] == 0


def test_facets_are_over_the_tracked_scope(warehouse):
    facets = public_queries.cqc_locations(warehouse)["facets"]
    assert {f["value"] for f in facets["registration_status"]} == {"Registered"}
    assert {f["value"] for f in facets["overall_rating"]} == {
        "Good", "Requires improvement", "Outstanding"}
    services = {f["value"]: f["count"] for f in facets["service_type"]}
    assert services["Substance misuse services"] == 3
    assert services["Community health care services"] == 1


def test_pagination_clamps_and_pages(warehouse):
    page = public_queries.cqc_locations(warehouse, limit=2, offset=0)
    assert len(page["results"]) == 2 and page["total"] == 3
    assert public_queries.cqc_locations(warehouse, limit=9999)["limit"] == 500
    assert public_queries.cqc_locations(warehouse, offset=-5)["offset"] == 0


def test_the_caveat_says_it_is_not_a_service_map(warehouse):
    caveat = public_queries.cqc_locations(warehouse)["caveat"].lower()
    assert "not a service map" in caveat or "never a complete service map" in caveat
    assert "neither coverage nor quality" in caveat


@pytest.fixture
def client(warehouse, settings: Settings):
    warehouse.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_route_answers_and_is_public(client):
    ok = client.get("/api/v1/cqc_locations?rating=Good")
    assert ok.status_code == 200
    body = ok.json()
    assert body["results"][0]["location_id"] == "L1"
    assert "max-age" in ok.headers["Cache-Control"]
    assert client.get("/api/admin/cqc_locations").status_code == 404
