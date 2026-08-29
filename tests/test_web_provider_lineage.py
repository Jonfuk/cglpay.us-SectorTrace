"""Verified provider lineage (BETA-066).

The edges are typed and directional, they come only from the lifecycle
config, the forward chain follows `superseded_by` with a cycle guard, and the
caveat says in words that this is not a statement about continuity of service.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import public_queries
from pipeline.web.queries import QueryError
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    rows = [
        ("with_you", "With You", 0, "active", None),
        ("addaction", "Addaction", 0, "renamed", "with_you"),
        ("kca", "Kent Council on Addictions", 0, "merged", "with_you"),
        ("waythrough", "Waythrough", 0, "active", None),
        ("humankind", "Humankind", 0, "renamed", "waythrough"),
        ("recovery_focus", "Recovery Focus", 0, "renamed", "waythrough"),
        ("lifeline_project", "Lifeline Project", 0, "dissolved", None),
        # A deliberate two-hop chain: addaction -> with_you is one hop; make
        # another entity point through addaction to test multi-hop.
        ("old_addaction", "Old Addaction", 0, "renamed", "addaction"),
        # A cycle: loop_a <-> loop_b. The chain must not spin.
        ("loop_a", "Loop A", 0, "renamed", "loop_b"),
        ("loop_b", "Loop B", 0, "renamed", "loop_a"),
    ]
    conn.executemany(
        "INSERT INTO providers (provider_key, canonical_name, is_target, status, "
        "superseded_by) VALUES (?, ?, ?, ?, ?)", rows)
    conn.executemany(
        "INSERT INTO provider_identifiers (provider_key, scheme, identifier, "
        "role, status) VALUES (?, ?, ?, ?, ?)", [
            ("with_you", "company_number", "02580377", "registered company", "verified"),
            ("with_you", "charity_number", "1001957", "registered charity", "verified"),
            ("with_you", "cqc_provider_id", "1-abc", None, "unverified"),
        ])
    conn.commit()
    return conn


def test_a_renamed_provider_points_forward_at_its_current_name(warehouse):
    result = public_queries.provider_lineage(warehouse, "addaction")
    forward = [e for e in result["edges"] if e["direction"] == "successor"]
    assert len(forward) == 1
    assert forward[0]["relationship"] == "renamed_to"
    assert forward[0]["provider_key"] == "with_you"
    assert forward[0]["canonical_name"] == "With You"
    assert forward[0]["basis"]
    assert [n["provider_key"] for n in result["chain"]] == ["addaction", "with_you"]


def test_the_surviving_entity_lists_its_predecessors(warehouse):
    result = public_queries.provider_lineage(warehouse, "with_you")
    assert not [e for e in result["edges"] if e["direction"] == "successor"]
    preds = {e["provider_key"]: e["relationship"]
             for e in result["edges"] if e["direction"] == "predecessor"}
    assert preds == {"addaction": "renamed_from", "kca": "merged_from"}
    assert len(result["chain"]) == 1


def test_a_fork_shows_both_successors_as_predecessors_of_the_survivor(warehouse):
    result = public_queries.provider_lineage(warehouse, "waythrough")
    preds = {e["provider_key"] for e in result["edges"]
             if e["direction"] == "predecessor"}
    assert preds == {"humankind", "recovery_focus"}


def test_a_dissolved_provider_has_a_terminal_edge_and_no_target(warehouse):
    result = public_queries.provider_lineage(warehouse, "lifeline_project")
    assert result["edges"] == [{
        "relationship": "dissolved", "direction": "terminal",
        "provider_key": None, "canonical_name": None,
        "basis": result["edges"][0]["basis"]}]
    assert len(result["chain"]) == 1


def test_the_chain_follows_multiple_hops(warehouse):
    chain = public_queries.provider_lineage(warehouse, "old_addaction")["chain"]
    assert [n["provider_key"] for n in chain] == [
        "old_addaction", "addaction", "with_you"]


def test_a_cycle_in_the_config_does_not_spin_the_chain(warehouse):
    chain = public_queries.provider_lineage(warehouse, "loop_a")["chain"]
    keys = [n["provider_key"] for n in chain]
    assert keys == ["loop_a", "loop_b"]  # stops when it revisits loop_a


def test_only_config_verified_identifiers_are_returned(warehouse):
    ids = public_queries.provider_lineage(warehouse, "with_you")["identifiers"]
    schemes = {i["scheme"] for i in ids}
    assert schemes == {"company_number", "charity_number"}
    assert all("role" in i for i in ids)
    assert not any(i["identifier"] == "1-abc" for i in ids)


def test_an_unknown_provider_is_refused(warehouse):
    with pytest.raises(QueryError):
        public_queries.provider_lineage(warehouse, "nope")


def test_the_caveat_disclaims_continuity_of_service(warehouse):
    caveat = public_queries.provider_lineage(warehouse, "addaction")["caveat"].lower()
    assert "not a statement about continuity" in caveat
    assert "no individual officer is named" in caveat


def test_it_reads_only_the_two_config_tables():
    import inspect

    source = inspect.getsource(public_queries.provider_lineage)
    marker = '_public(["providers", "provider_identifiers"])'
    assert marker in source


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


def test_the_route_answers_and_is_public_and_cacheable(client):
    ok = client.get("/api/v1/providers/addaction/lineage")
    assert ok.status_code == 200
    assert ok.json()["chain"][-1]["provider_key"] == "with_you"
    assert "max-age" in ok.headers["Cache-Control"]
    assert client.get("/api/v1/providers/nope/lineage").status_code == 400
