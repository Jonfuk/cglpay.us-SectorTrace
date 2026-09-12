"""Human alias-resolution workflow (BETA-056).

Every resolution is a named, append-only decision. A fuzzy match is never
promoted to canonical identity: `decide()` requires a reviewer name and, for
`accepted`, a `canonical_id` that exists. `verified_aliases` is the
deterministic registry — the latest accepted, non-superseded decision per
name.
"""
from __future__ import annotations

import inspect
import threading

import httpx
import pytest

from pipeline import catalog
from pipeline.config import Settings
from pipeline.web import alias_resolution
from pipeline.web.queries import QueryError
from pipeline.web.server import build_server


def _authority(conn, ons_code, name):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, active_to, "
        " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES (%s, %s, 'unitary', "
        " '2021-04-01', NULL, '2024', '2026', 'https://x', "
        " '2026-08-01T00:00:00Z', 200, 'ons', 'x')", (ons_code, name))


def _review(conn, item_type, raw_value):
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, status, "
        "created_at) VALUES ('m01_procurement', %s, %s, 'pending', "
        "'2026-08-01T00:00:00Z')", (item_type, raw_value))


@pytest.fixture
def warehouse(conn):
    _authority(conn, "E06000019", "Herefordshire, County of")
    _authority(conn, "E08000025", "Birmingham City Council")
    _review(conn, "unmatched_buyer_name", "Hereford Council")
    _review(conn, "unmatched_buyer_name", "Some Other Buyer")
    conn.commit()
    return conn


def test_the_table_and_view_exist(warehouse):
    tables = {row["name"] for row in catalog.list_objects(warehouse)}
    assert "alias_decisions" in tables and "verified_aliases" in tables


def test_a_named_reviewer_is_required(warehouse):
    with pytest.raises(QueryError):
        alias_resolution.decide(warehouse, unmatched_name="Hereford Council",
                                 target_scheme="buyer", status="accepted",
                                 decided_by="   ", canonical_id="E06000019")


def test_accepted_needs_a_canonical_id_that_exists(warehouse):
    with pytest.raises(QueryError):
        alias_resolution.decide(warehouse, unmatched_name="Hereford Council",
                                 target_scheme="buyer", status="accepted",
                                 decided_by="Jon")
    with pytest.raises(QueryError):
        alias_resolution.decide(warehouse, unmatched_name="Hereford Council",
                                 target_scheme="buyer", status="accepted",
                                 decided_by="Jon", canonical_id="E99999999")


def test_a_rejected_decision_must_not_carry_a_canonical_id(warehouse):
    with pytest.raises(QueryError):
        alias_resolution.decide(warehouse, unmatched_name="Hereford Council",
                                 target_scheme="buyer", status="rejected",
                                 decided_by="Jon", canonical_id="E06000019")


def test_accept_then_supersede_updates_the_verified_registry(warehouse):
    first = alias_resolution.decide(
        warehouse, unmatched_name="Hereford Council", target_scheme="buyer",
        status="accepted", decided_by="Jon", canonical_id="E06000019")
    reg = alias_resolution.verified(warehouse)["aliases"]
    assert len(reg) == 1
    assert reg[0]["canonical_id"] == "E06000019"
    assert reg[0]["canonical_name"] == "Herefordshire, County of"

    # A correction: a new accepted decision naming the one it replaces.
    import time
    time.sleep(0.01)
    alias_resolution.decide(
        warehouse, unmatched_name="Hereford Council", target_scheme="buyer",
        status="accepted", decided_by="Sam", canonical_id="E08000025",
        supersedes_id=first["decision_id"])

    reg = alias_resolution.verified(warehouse)["aliases"]
    assert len(reg) == 1
    assert reg[0]["canonical_id"] == "E08000025"
    # The superseded row is still in the history, untouched.
    rows = warehouse.execute(
        "SELECT COUNT(*) FROM alias_decisions WHERE unmatched_name = 'Hereford Council'"
    ).fetchone().values().__iter__().__next__()
    assert rows == 2


def test_unresolved_lists_review_names_with_their_state(warehouse):
    alias_resolution.decide(
        warehouse, unmatched_name="Hereford Council", target_scheme="buyer",
        status="accepted", decided_by="Jon", canonical_id="E06000019")
    data = alias_resolution.unresolved(warehouse, scheme="buyer")
    by_name = {i["unmatched_name"]: i for i in data["items"]}
    assert by_name["Hereford Council"]["resolved"] is True
    assert by_name["Some Other Buyer"]["resolved"] is False
    assert "nothing applies it automatically" in data["caveat"]


def test_nothing_applies_a_fuzzy_match_automatically():
    source = inspect.getsource(alias_resolution)
    # The module never calls the ranking or writes an alias without decide().
    assert "name_matches" not in source and "suggestions(" not in source
    assert source.count("INSERT INTO alias_decisions") == 1
    assert "UPDATE alias_decisions" not in source
    assert "DELETE FROM alias_decisions" not in source


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


def test_the_routes_are_admin_only(client):
    assert client.get("/api/admin/aliases?scheme=buyer").status_code == 200
    assert client.get("/api/admin/aliases/verified").status_code == 200
    assert client.get("/api/v1/admin/aliases").status_code == 404

    accept = client.post("/api/admin/aliases/decide", json={
        "unmatched_name": "Hereford Council", "target_scheme": "buyer",
        "status": "accepted", "decided_by": "Jon", "canonical_id": "E06000019",
    }, headers={"Content-Type": "application/json",
                "Origin": str(client.base_url)})
    assert accept.status_code == 200
    assert client.get("/api/admin/aliases/verified").json()["count"] == 1

    bad = client.post("/api/admin/aliases/decide", json={
        "unmatched_name": "X", "target_scheme": "buyer", "status": "accepted",
        "decided_by": "", "canonical_id": "E06000019",
    }, headers={"Content-Type": "application/json",
                "Origin": str(client.base_url)})
    assert bad.status_code == 400
