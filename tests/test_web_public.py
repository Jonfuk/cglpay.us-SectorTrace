"""The public evidence portal's API.

The portal is the copy of this warehouse that gets handed to people outside
the team, so the tests that matter most are about what it refuses to do:
publish personal data, publish a figure without its caveat, or publish a
number the pipeline's own caveats say must not be computed.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import httpx
import pytest

from pipeline import db
from pipeline.web import public_export, public_queries, queries
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """A small but structurally real warehouse: a provider, an authority, a
    contract, a framework-sized notice, and a personal-data table."""
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
                  "VALUES ('change_grow_live', 'Change Grow Live', 1, 'Campaign subject.')")
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target) "
                  "VALUES ('turning_point', 'Turning Point', 0)")
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, geometry_geojson, "
        " active_from, first_seen_vintage, last_seen_vintage, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "('E08000025', 'Birmingham', 'MD', 'West Midlands', "
        " '{\"type\":\"Polygon\",\"coordinates\":[[[0,0],[1,0],[1,1],[0,0]]]}', "
        " '2021-04-01', '2024', '2026', "
        " 'https://ons.example/boundaries', '2026-08-01T00:00:00Z', 200, "
        " 'ons_open_geography_portal', 'geo123')")
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, canonical_name) "
                  "VALUES ('Change Grow Live', 'change_grow_live', 'Change Grow Live')")

    for notice_id, supplier, value in [
        ("n1", "Change Grow Live", 4_200_000),
        ("n2", "Someone Else Ltd", 15_000_000),
        ("n3", "Big Framework Ltd", 120_000_000_000),
    ]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, 'Birmingham City Council', 'E08000025', ?, "
            " 'Treatment services', ?, 'GBP', '2026-03-01', 'open', 'psr', "
            " 'https://find.example/n', '2026-08-01T00:00:00Z', 200, "
            " 'find_a_tender', 'abc123')",
            (notice_id, f"ocds-{notice_id}", supplier, value))

    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, workforce_segment, "
        " value, unit, verified, raw_text, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (2024, 'vacancy_rate', 'all_staff', 7.0, 'percent', 0, "
        " 'Vacancy rate 7.0%', 'https://nhsbn.example/census', "
        " '2026-08-01T00:00:00Z', 200, 'nhs_benchmarking', 'cen123')")

    conn.execute("CREATE TABLE IF NOT EXISTS restricted_people "
                  "(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO restricted_people (name) VALUES ('A Person')")
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


# --- the guarantee that matters ----------------------------------------------


def test_no_public_query_touches_a_restricted_table(ro):
    """Every function declares the tables it reads and the declaration is
    enforced, so this is a property of the code rather than a claim."""
    public_queries.summary(ro)
    public_queries.providers(ro)
    public_queries.contracts(ro)
    public_queries.pay(ro)
    public_queries.geography(ro, metric="grant_total")
    public_queries.fingertips(ro)
    public_queries.boundaries(ro)
    public_queries.authorities(ro)


def test_the_guard_actually_refuses_a_restricted_table():
    """If _public() could be handed a restricted table without complaint, every
    test above would be worthless."""
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["restricted_people"])
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["contracts", "restricted_pfd_persons"])


def test_no_public_endpoint_serves_a_restricted_table(client):
    """Reachability, from the outside. A restricted table must not be
    addressable through the portal's API at all."""
    for path in ["/api/v1/restricted_people", "/api/v1/table/restricted_people",
                  "/api/v1/summary/restricted_people"]:
        assert client.get(path).status_code == 404

    body = json.dumps(client.get("/api/v1/summary").json())
    assert "restricted_" not in body
    assert "A Person" not in body


# --- caveats travel with figures ---------------------------------------------


def test_every_headline_payload_carries_its_caveat(ro):
    assert public_queries.summary(ro)["contracts"]["caveat"]
    assert public_queries.contracts(ro)["caveats"]["value"]
    assert public_queries.pay(ro)["caveats"]["indicative_wage_note"]
    assert public_queries.geography(ro, metric="grant_total")["caveat"]
    assert public_queries.fingertips(ro)["caveat"]


def test_unverified_census_figures_are_marked_as_such(ro):
    """docs/CAVEATS.md says to filter on `verified` before publishing. The
    portal cannot do that unless the API tells it which rows are unverified."""
    summary = public_queries.summary(ro)
    assert summary["workforce"]["all_unverified"] is True
    assert summary["workforce"]["caveat"]

    pay = public_queries.pay(ro)
    assert pay["census_all_unverified"] is True
    assert all(row["verified"] == 0 for row in pay["workforce_census"])


# --- the framework-ceiling problem -------------------------------------------


def test_a_corpus_dominated_by_framework_ceilings_is_reported_as_such(ro):
    """One £120bn framework notice among three makes the sum meaningless. The
    API has to say so, or the portal will headline it."""
    data = public_queries.contracts(ro)
    concentration = data["value_concentration"]

    assert concentration["notices_over_1bn"] == 1
    assert concentration["share_over_1bn"] > 0.99
    assert concentration["median_value_gbp"] == 15_000_000
    # The mean is three orders of magnitude above the middle notice.
    assert concentration["mean_to_median_ratio"] > 100
    assert public_queries.summary(ro)["contracts"]["value_is_concentrated"] is True


def test_a_corpus_without_ceilings_keeps_its_headline(warehouse, settings):
    """The warning is measured per request, so a corpus that does not have the
    problem does not carry the warning."""
    warehouse.execute("DELETE FROM contracts WHERE notice_id = 'n3'")
    warehouse.commit()
    connection = queries.readonly_connection(settings)
    assert public_queries.summary(connection)["contracts"]["value_is_concentrated"] is False
    connection.close()


def test_provider_matching_is_reported_as_a_floor(ro):
    data = public_queries.contracts(ro)
    assert data["matched_to_provider"] == 1
    assert data["total"] == 3
    assert "floor" in data["caveats"]["provider_match"]


# --- shapes the portal depends on --------------------------------------------


def test_geography_returns_one_row_per_authority(ro):
    """A choropleth needs one value per area. Without a year default, these
    queries return a row per authority per year and the map colours each area
    by whichever row was drawn last."""
    data = public_queries.geography(ro, metric="contract_value")
    codes = [f["ons_code"] for f in data["features"]]
    assert len(codes) == len(set(codes))


def test_an_unknown_geography_metric_is_refused(ro):
    with pytest.raises(queries.QueryError, match="Unknown metric"):
        public_queries.geography(ro, metric="whatever_i_like")


def test_boundaries_come_from_the_warehouse_with_provenance(ro):
    geo = public_queries.boundaries(ro)
    assert geo["type"] == "FeatureCollection"
    assert geo["features"][0]["properties"]["ons_code"] == "E08000025"
    assert geo["features"][0]["geometry"]["type"] == "Polygon"
    assert geo["meta"]["source_url"] == "https://ons.example/boundaries"


def test_providers_carry_their_counts(ro):
    providers = {p["provider_key"]: p for p in public_queries.providers(ro)}
    assert providers["change_grow_live"]["is_target"] == 1
    assert providers["change_grow_live"]["contract_count"] == 1
    assert providers["turning_point"]["contract_count"] == 0


def test_an_unknown_provider_timeline_is_refused(ro):
    with pytest.raises(queries.QueryError, match="No provider"):
        public_queries.provider_timeline(ro, "not_a_provider")


# --- over HTTP ----------------------------------------------------------------


def test_the_portal_and_the_operator_ui_are_both_served(client):
    portal = client.get("/")
    admin = client.get("/admin/")
    assert portal.status_code == 200
    assert admin.status_code == 200
    assert "SectorTrace" in portal.text
    assert portal.text != admin.text


def test_public_endpoints_answer(client):
    for path in ["/api/v1/summary", "/api/v1/providers", "/api/v1/contracts",
                  "/api/v1/pay", "/api/v1/geography", "/api/v1/fingertips",
                  "/api/v1/authorities", "/api/v1/boundaries"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "max-age=300, private"


def test_operator_answers_are_never_cached(client):
    """The review queue changes as it is worked on; a cached page would show
    decisions that are not there."""
    assert client.get("/api/overview").headers["cache-control"] == "no-store"


def test_the_public_api_is_read_only(client):
    """No write route exists under /api/v1, whatever is posted at it."""
    for path in ["/api/v1/summary", "/api/v1/contracts"]:
        assert client.post(path, json={"anything": 1}).status_code == 404


# --- exports ------------------------------------------------------------------


def test_a_csv_export_carries_its_provenance(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "providers", "format": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    body = response.text
    assert body.startswith("# SectorTrace export")
    assert "# exported_at:" in body
    assert "docs/CAVEATS.md" in body
    assert "change_grow_live" in body

    # And in a header, for anything reading the response rather than the file.
    provenance = json.loads(response.headers["x-provenance"])
    assert provenance["source_endpoint"] == "/api/v1/providers"


def test_a_json_export_carries_its_provenance(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "contracts", "format": "json",
                                    "provider_key": "change_grow_live"})
    payload = response.json()
    assert payload["_provenance"]["filters_applied"] == {"provider_key": "change_grow_live"}
    assert isinstance(payload["contracts"], list)


def test_export_refuses_an_endpoint_it_cannot_flatten(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "boundaries", "format": "csv"})
    assert response.status_code == 400
    assert "cannot be exported" in response.json()["error"]


def test_export_refuses_an_unknown_format(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "providers", "format": "xlsx"})
    assert response.status_code == 400


def test_csv_export_keeps_columns_that_only_later_rows_have():
    """Rows from a view can legitimately differ in shape. Taking the header
    from row one would silently truncate the export."""
    csv = public_export.to_csv(
        [{"a": 1}, {"a": 2, "b": 3}],
        public_export.provenance("providers", {}))
    assert "a,b" in csv
    assert "2,3" in csv
