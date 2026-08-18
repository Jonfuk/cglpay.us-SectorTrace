"""The geography map's overlay layers (Phase 13: W-19).

The pins here are that the map's layers are the export layers, so the portal
and the downloads cannot drift apart, and that a layer never appears without
the caveats that govern it:

  * every layer the map can toggle carries caveats from the payload;
  * the contracts, CQC and treatment caveats are the export layers' own —
    read from the same source, word for word, not copied into the API;
  * the treatment overlay is the export's data row for row;
  * PFD reports are deliberately not a layer: they have no geometry, and
    coroner areas are not local authorities and must not be mapped as if
    they were — the absence is a decision, pinned the same way W-15 pins
    the absence of a CQC link;
  * the coverage layer is W-12's data — how many evidence kinds the
    warehouse holds per authority — so it agrees with the authority page's
    ticks row for row.

The browser half — the overlays rendering over the choropleth — is a
deliberate human check, as elsewhere in this suite.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.exports import geojson as geojson_export
from pipeline.web import public_queries, queries
from pipeline.web.server import build_server

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"

BIRMINGHAM = "E08000025"
STAFFORDSHIRE = "E10000028"

GEOMETRY = ('{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}')


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Authorities with geometry, contracts for two of them, two CQC
    locations with coordinates, and a treatment series — enough for every
    layer to have features."""
    for ons_code, name in [(BIRMINGHAM, "Birmingham"), (STAFFORDSHIRE, "Staffordshire")]:
        conn.execute(
            "INSERT INTO authorities (ons_code, name, type, region, geometry_geojson, "
            " active_from, first_seen_vintage, last_seen_vintage, "
            " source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (?, ?, 'county', 'West Midlands', ?, '2021-04-01', '2024', '2026', "
            " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
            (ons_code, name, GEOMETRY))

    for notice_id, ons_code, value in [("n1", BIRMINGHAM, 4_200_000),
                                       ("n2", BIRMINGHAM, 800_000),
                                       ("n3", STAFFORDSHIRE, None)]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, 'A Council', ?, 'Supplier Ltd', 'Treatment services', "
            " ?, 'GBP', '2025-06-01', 'open', 'psr', 'https://find.example/n', "
            " '2026-08-01T00:00:00Z', 200, 'find_a_tender', 'abc123')",
            (notice_id, f"ocds-{notice_id}", ons_code, value))

    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_name, registration_status, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('prov1', 'A Provider', 'Registered', 'https://cqc.example/p', "
        " '2026-08-01T00:00:00Z', 200, 'cqc', 'c')")
    for location_id, ons_code, latitude, longitude in [
        ("loc1", BIRMINGHAM, 52.48, -1.89), ("loc2", STAFFORDSHIRE, 52.80, -2.11)]:
        conn.execute(
            "INSERT INTO cqc_locations (location_id, provider_id, location_name, "
            " local_authority_raw, local_authority_ons_code, region, overall_rating, "
            " latitude, longitude, registration_status, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (?, 'prov1', 'A regulated service', 'Birmingham', ?, "
            " 'West Midlands', 'Good', ?, ?, 'Registered', 'https://cqc.example/l', "
            " '2026-08-01T00:00:00Z', 200, 'cqc', 'c')",
            (location_id, ons_code, latitude, longitude))

    conn.execute(
        "INSERT INTO fingertips_indicators (indicator_id, indicator_name, topic, "
        " unit, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (92454, 'Numbers in treatment', 'numbers_in_treatment', 'rate', "
        " 'https://fingertips.example/i', '2026-08-01T00:00:00Z', 200, 'ohid', 'f')")
    for ons_code, period, value in [(BIRMINGHAM, "2023-24", 18.4),
                                    (BIRMINGHAM, "2024-25", 17.9),
                                    (STAFFORDSHIRE, "2024-25", 11.2)]:
        conn.execute(
            "INSERT INTO fingertips_la_values (indicator_id, area_code, area_type_id, "
            " time_period, area_name, ons_code, area_level, value, time_period_sortable, "
            " source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (92454, ?, 102, ?, 'Birmingham', ?, 'local_authority', ?, ?, "
            " 'https://fingertips.example/v', '2026-08-01T00:00:00Z', 200, 'ohid', 'f')",
            (ons_code, period, ons_code, value, period))

    conn.commit()
    return conn


@pytest.fixture
def ro(warehouse, settings):
    connection = queries.readonly_connection(settings)
    yield connection
    connection.close()


@pytest.fixture
def client(warehouse, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=15.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- every toggleable layer carries its own caveats ---------------------------


def test_every_layer_carries_its_own_caveats(ro):
    layers = public_queries.layers(ro)["layers"]
    assert set(layers) == {"contracts", "cqc_locations", "treatment", "coverage"}

    for key, layer in layers.items():
        assert layer["caveats"], f"{key} has no caveats"
        assert layer["label"]

    # The coverage layer is the absence caveat, verbatim — the layer's whole
    # point is that a hole on the map is a hole in collection.
    assert "absence" in layers["coverage"]["caveats"][0].lower()


def test_the_layer_caveats_are_the_export_layers_own(ro):
    """The API's caveats come from pipeline.exports.geojson.LAYER_CAVEATS,
    read by the portal rather than copied. A change to either side is a
    change to the other, and this test would fail the moment that stopped
    being true."""
    payload = public_queries.layers(ro)["layers"]

    assert payload["cqc_locations"]["caveats"] == geojson_export.LAYER_CAVEATS["cqc_locations"]
    assert payload["treatment"]["caveats"] == geojson_export.LAYER_CAVEATS["treatment_numbers"]

    # The contracts layer carries the export's caveats plus one of its own in
    # front: the portal aggregates the corpus to one point per authority, and
    # that aggregation is stated rather than left for the reader to infer.
    export_caveats = geojson_export.LAYER_CAVEATS["contracts"]
    api_caveats = payload["contracts"]["caveats"]
    assert api_caveats[1:] == export_caveats
    assert "Aggregated" in api_caveats[0]


def test_the_treatment_layer_agrees_with_the_export_row_for_row(ro, tmp_path):
    """The overlay and treatment_numbers.geojson are the same data: latest
    period per authority, as the export defines it. If one of them changes
    shape, the other is a second dataset wearing the same name."""
    geojson_export.export_all(ro, tmp_path)
    exported = json.loads((tmp_path / "treatment_numbers.geojson").read_text())
    from_export = {f["properties"]["ons_code"]: f["properties"]["value"]
                   for f in exported["features"]}
    from_api = {f["ons_code"]: f["value"]
                for f in public_queries.layers(ro)["layers"]["treatment"]["features"]}
    assert from_api == from_export
    # The export emits each authority's latest published period; the fixture
    # has two periods for Birmingham and the layer must keep the later one.
    assert from_api[BIRMINGHAM] == 17.9


def test_pfd_reports_are_not_a_layer(ro):
    """Deliberate absence, pinned like W-15's CQC decision. PFD reports have
    no geometry — coroner areas are not local authorities and must not be
    mapped as if they were (docs/CAVEATS.md) — so the export keeps the layer
    geometry-free and the map does not draw it at all. The map is for things
    that have a place."""
    payload = public_queries.layers(ro)
    keys = " ".join(payload["layers"])
    assert "pfd" not in keys


def test_the_contracts_layer_aggregates_per_buyer(ro):
    layer = public_queries.layers(ro)["layers"]["contracts"]
    by_code = {f["ons_code"]: f for f in layer["features"]}

    assert by_code[BIRMINGHAM]["count"] == 2
    assert by_code[BIRMINGHAM]["value_gbp"] == 5_000_000
    assert by_code[STAFFORDSHIRE]["count"] == 1
    assert by_code[STAFFORDSHIRE]["value_gbp"] == 0
    # A notice with no value is still counted — its zero is not its absence.
    assert by_code[STAFFORDSHIRE]["count"] == 1


# --- the coverage layer is W-12's data ----------------------------------------


def test_the_coverage_layer_agrees_with_the_authority_page(ro):
    layer = public_queries.layers(ro)["layers"]["coverage"]
    by_code = {f["ons_code"]: f for f in layer["features"]}

    for code in (BIRMINGHAM, STAFFORDSHIRE):
        cells = public_queries.authority(ro, code)["coverage"]["cells"]
        assert by_code[code]["kinds_held"] == sum(1 for count in cells.values()
                                                  if count > 0)

    # Only authorities with at least one kind are features: a zero here would
    # be a statement about the authority, and the layer makes none.
    assert all(f["kinds_held"] >= 1 for f in layer["features"])


# --- over HTTP and in the page -------------------------------------------------


def test_the_layers_route_answers_over_http(client):
    response = client.get("/api/v1/layers")
    assert response.status_code == 200
    body = response.json()
    assert set(body["layers"]) == {"contracts", "cqc_locations", "treatment", "coverage"}
    assert body["layers"]["cqc_locations"]["features"]
    assert "max-age" in response.headers["Cache-Control"]


@pytest.fixture(scope="module")
def geographyjs() -> str:
    return (PORTAL / "js" / "pages" / "geography.js").read_text(encoding="utf-8")


def test_the_map_toggles_are_built_from_the_payload(geographyjs):
    """The toggle panel iterates the payload's layers and renders each
    layer's caveats from the payload — so a layer added to /api/v1/layers
    gains a toggle here with its caveat by construction, and a layer with no
    caveats cannot be toggled on at all."""
    assert "fetchJSON('layers')" in geographyjs
    assert "Object.entries(payload.layers" in geographyjs
    assert "layer.caveats.join(' ')" in geographyjs
    assert "pinnedCaveat" in geographyjs


def test_the_point_layers_use_positron_and_keep_authority_navigation(geographyjs):
    """The three point layers are alternative maps, and a click still opens
    the authority evidence page rather than a map-only dead end."""
    assert "POSITRON_LAYERS" in geographyjs
    assert "basemaps.cartocdn.com/light_all" in geographyjs
    assert "drawLeafletPoints" in geographyjs
    assert "location.hash = `#/authorities/${point.ons_code}`" in geographyjs


def test_no_layer_caveat_text_is_hardcoded_in_the_map_page(geographyjs):
    """The layer caveats live in the payload, which reads them from the same
    source as the exports. A sentence written into the page would be a second
    copy free to drift — the shape this finding is about."""
    for phrase in ("not a map of services", "centroid of the commissioning",
                   "rate per 1,000", "absence of collection"):
        assert phrase.lower() not in geographyjs.lower()
