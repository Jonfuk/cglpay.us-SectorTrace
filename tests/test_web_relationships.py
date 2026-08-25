"""The relationship explorer: a one-hop commissioning neighbourhood from the
evidence graph (docs/evidence-graph.md, migration 0050), not a map of the
whole corpus.

Pins that matter here:

  * only AWARDED_TO edges with derivation_type SOURCE_FACT or
    DERIVED_RELATIONSHIP are ever returned — REGISTERED_AS (ownership) and
    anything EXTRACTED_CLAIM/ANALYTICAL_SIGNAL (a not-yet-built extraction
    pipeline) must never leak into this view;
  * an authority or provider that exists but has no matched relationship
    returns an empty neighbourhood, never a 404 — absence of a connection
    is not absence of the entity;
  * a warehouse that predates the graph tables (migration 0050) degrades
    gracefully rather than 500ing the whole route.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.graph.backfill import seed_existing_evidence
from pipeline.web import public_queries, queries
from pipeline.web.server import build_server

BIRMINGHAM = "E08000025"
STAFFORDSHIRE = "E10000028"


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """One authority with a matched contract award to one provider, and a
    second authority with none — so both the populated and empty
    neighbourhood paths have a real fixture."""
    for ons_code, name in [(BIRMINGHAM, "Birmingham"), (STAFFORDSHIRE, "Staffordshire")]:
        conn.execute(
            "INSERT INTO authorities (ons_code, name, type, active_from, "
            " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (?, ?, 'county', '2021-04-01', '2024', '2026', "
            " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', ?)",
            (ons_code, name, f"authority-hash-{ons_code}"))
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
                 "VALUES ('change-grow-live', 'Change Grow Live', 1, NULL)")
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, canonical_name) "
                 "VALUES ('Change Grow Live Ltd', 'change-grow-live', 'Change Grow Live')")
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, buyer_ons_code, "
        " supplier_name_raw, date_start, date_end, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES ('notice-1', 'supplier-1', 'ocid-1', ?, 'Change Grow Live Ltd', "
        " '2024-01-01', '2025-01-01', 'https://find-a-tender.example/n', "
        " '2026-08-01T00:00:00Z', 200, 'fts', 'contract-hash')",
        (BIRMINGHAM,))
    conn.commit()
    seed_existing_evidence(conn)
    return conn


@pytest.fixture
def client(warehouse, settings):
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


def test_needs_exactly_one_selector(warehouse, settings):
    ro = queries.readonly_connection(settings)
    try:
        with pytest.raises(queries.QueryError):
            public_queries.relationships(ro)
        with pytest.raises(queries.QueryError):
            public_queries.relationships(ro, ons_code=BIRMINGHAM, provider_key="change-grow-live")
    finally:
        ro.close()


def test_an_authority_lists_the_provider_it_awarded_a_contract_to(client):
    payload = client.get(f"/api/v1/relationships?ons_code={BIRMINGHAM}").json()

    assert payload["center"]["canonical_name"] == "Birmingham"
    assert payload["center"]["entity_type"] == "LOCAL_AUTHORITY"
    assert [n["canonical_name"] for n in payload["neighbours"]] == ["Change Grow Live"]
    assert len(payload["edges"]) == 1
    edge = payload["edges"][0]
    assert edge["source_url"] == "https://find-a-tender.example/n"
    assert edge["valid_from"] == "2024-01-01"
    assert "caveat" in payload and payload["caveat"]


def test_a_provider_lists_the_authority_that_awarded_it_a_contract(client):
    payload = client.get("/api/v1/relationships?provider_key=change-grow-live").json()

    assert payload["center"]["canonical_name"] == "Change Grow Live"
    assert payload["center"]["entity_type"] == "PROVIDER"
    assert [n["canonical_name"] for n in payload["neighbours"]] == ["Birmingham"]


def test_an_entity_with_no_matched_relationship_returns_an_empty_neighbourhood(client):
    """Staffordshire exists and was backfilled into the graph, but awarded
    nothing to a matched supplier. Absence of a connection, not absence of
    the authority."""
    payload = client.get(f"/api/v1/relationships?ons_code={STAFFORDSHIRE}").json()

    assert payload["center"]["canonical_name"] == "Staffordshire"
    assert payload["neighbours"] == []
    assert payload["edges"] == []


def test_an_unknown_entity_is_a_clean_error_not_a_stack_trace(client):
    response = client.get("/api/v1/relationships?ons_code=E99999999")
    assert response.status_code == 400
    assert "error" in response.json()


def test_registered_as_ownership_edges_are_excluded(warehouse, settings):
    """This view is commissioning relationships only. Ownership (v-15/G3
    territory) is a separate, not-yet-published view — see the module
    docstring in pipeline/web/public_queries.py."""
    warehouse.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, "
        " canonical_name_normalized, created_at, updated_at) "
        "VALUES ('company:00000001', 'LEGAL_ENTITY', 'Example Ltd', "
        " 'example ltd', 'now', 'now')")
    warehouse.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, payload_sha256, created_at) "
        "VALUES ('evidence:ch:x', 'companies_house', 'https://ch.example/x', "
        " 'now', 'x', 'now')")
    warehouse.execute(
        "INSERT INTO entity_relationships (relationship_id, subject_entity_id, "
        " predicate, object_entity_id, relationship_type, evidence_id, "
        " confidence, derivation_type, created_at, updated_at) "
        "VALUES ('rel:1', 'provider:change-grow-live', 'REGISTERED_AS', "
        " 'company:00000001', 'REGISTERED_AS', 'evidence:ch:x', 1.0, "
        " 'SOURCE_FACT', 'now', 'now')")
    warehouse.commit()

    ro = queries.readonly_connection(settings)
    try:
        payload = public_queries.relationships(ro, provider_key="change-grow-live")
    finally:
        ro.close()

    names = {n["canonical_name"] for n in payload["neighbours"]}
    assert "Example Ltd" not in names, "ownership edges leaked into the commissioning view"


def test_extracted_claim_relationships_are_excluded(warehouse, settings):
    """graph_claims.review_status exists for a not-yet-built extraction
    pipeline (see beta.md's BETA-009 entry). Nothing writes EXTRACTED_CLAIM
    today, but this query must not rely on that absence."""
    warehouse.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, "
        " canonical_name_normalized, created_at, updated_at) "
        "VALUES ('provider:unverified-lead', 'PROVIDER', 'Unverified Lead Ltd', "
        " 'unverified lead ltd', 'now', 'now')")
    warehouse.execute(
        "INSERT INTO entity_relationships (relationship_id, subject_entity_id, "
        " predicate, object_entity_id, relationship_type, "
        " confidence, derivation_type, created_at, updated_at) "
        "VALUES ('rel:2', ?, 'AWARDED_TO', 'provider:unverified-lead', "
        " 'AWARDED_TO', 0.4, 'EXTRACTED_CLAIM', 'now', 'now')",
        (f"authority:{BIRMINGHAM}",))
    warehouse.commit()

    ro = queries.readonly_connection(settings)
    try:
        payload = public_queries.relationships(ro, ons_code=BIRMINGHAM)
    finally:
        ro.close()

    names = {n["canonical_name"] for n in payload["neighbours"]}
    assert "Unverified Lead Ltd" not in names, \
        "an unreviewed EXTRACTED_CLAIM relationship reached the public API"


def test_survives_a_warehouse_that_predates_the_graph_tables(conn, settings):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES (?, 'Birmingham', 'county', '2021-04-01', '2024', '2026', "
        " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
        (BIRMINGHAM,))
    for table in ("entity_relationships", "graph_claims", "entity_aliases",
                  "entity_identifiers", "evidence_records", "entities"):
        conn.execute(f"DROP TABLE {table}")
    conn.commit()

    ro = queries.readonly_connection(settings)
    try:
        payload = public_queries.relationships(ro, ons_code=BIRMINGHAM)
    finally:
        ro.close()

    assert payload["center"]["canonical_name"] == "Birmingham"
    assert payload["neighbours"] == []
    assert payload["edges"] == []


def test_route_is_documented_and_frozen():
    """See tests/test_portal_isolation.py for the full frozen-surface pins;
    this is a quick sanity check that the route this file exercises is one
    of them, not a route this file invented ad hoc."""
    from tests.test_portal_isolation import PUBLIC_API_ROUTES
    assert "relationships" in PUBLIC_API_ROUTES
