"""Relationship pathfinder (BETA-093).

The shortest *verified* path between two entities through `v_entity_edges`.
An edge whose basis is an unconfirmed name match has not passed its review
gate and is never followed; the traversal is deterministic and hop-bounded.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import pathfinder
from pipeline.web.queries import QueryError


def _company(conn, number, provider_key, *, basis="seed"):
    conn.execute(
        "INSERT INTO companies (company_number, provider_key, company_name, "
        " match_basis, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES (%s, %s, %s, %s, 'https://ch/x', "
        " '2026-01-01T00:00:00Z', 200, 'companies_house', 'h')",
        (number, provider_key, f"{provider_key.upper()} LTD", basis))


def _contract(conn, notice_id, ons, supplier_raw, *, alias_key=None):
    if alias_key:
        conn.execute(
            "INSERT INTO supplier_aliases (alias_raw, supplier_key, "
            " canonical_name) VALUES (%s, %s, %s) "
            "ON CONFLICT (alias_raw) DO NOTHING",
            (supplier_raw, alias_key, alias_key))
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, notice_type, "
        " buyer_name, buyer_ons_code, supplier_name_raw, title, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "(%s, '', %s, 'award', 'B', %s, %s, 'x', 'https://ft/x', "
        " '2026-01-01T00:00:00Z', 200, 'find_tender', 'h')",
        (notice_id, f"ocid-{notice_id}", ons, supplier_raw))


def test_finds_the_shortest_verified_path(conn: sqlite3.Connection) -> None:
    _contract(conn, "c1", "E09000007", "CHANGE GROW LIVE", alias_key="cgl")
    conn.commit()
    out = pathfinder.find_path(conn, from_type="authority", from_id="E09000007",
                                to_type="supplier", to_id="cgl")
    assert out["found"] and out["hops"] == 1
    hop = out["path"][0]
    assert hop["relationship"] == "awarded_contract_to"
    assert hop["basis"] == "alias_matched"
    assert hop["source_url"] == "https://ft/x"
    assert out["verified_only"] is True
    assert "review gate" in out["note"].lower()


def test_unconfirmed_name_match_edges_are_not_followed(conn: sqlite3.Connection) -> None:
    # no supplier_aliases row -> basis is 'supplier_name_unmatched'
    _contract(conn, "c2", "E09000019", "SOME OTHER LTD")
    conn.commit()
    out = pathfinder.find_path(conn, from_type="authority", from_id="E09000019",
                                to_type="supplier", to_id="SOME OTHER LTD")
    assert out["found"] is False
    assert "no verified edges" in out["reason"]


def test_a_two_hop_path_and_the_hop_bound(conn: sqlite3.Connection) -> None:
    # authority --awarded--> supplier:cgl ; provider:cgl --registered_as--> company
    # so authority -> cgl (as supplier) and cgl (as provider) share the id but
    # different node types; build a genuine 2-hop chain instead:
    # authority E09000007 -> supplier cgl ; authority E09000007 also -> supplier acme
    _contract(conn, "c1", "E09000007", "CHANGE GROW LIVE", alias_key="cgl")
    _contract(conn, "c3", "E09000007", "ACME CARE", alias_key="acme")
    conn.commit()
    out = pathfinder.find_path(conn, from_type="supplier", from_id="cgl",
                                to_type="supplier", to_id="acme")
    assert out["found"] and out["hops"] == 2          # cgl -> E09000007 -> acme
    assert out["path"][0]["to"] == "authority:E09000007"
    # the same call twice is byte-identical (deterministic)
    again = pathfinder.find_path(conn, from_type="supplier", from_id="cgl",
                                  to_type="supplier", to_id="acme")
    assert again["path"] == out["path"]
    # cap the search below the true distance
    capped = pathfinder.find_path(conn, from_type="supplier", from_id="cgl",
                                   to_type="supplier", to_id="acme", max_hops=1)
    assert capped["found"] is False and "within 1 hops" in capped["reason"]


def test_same_endpoint_is_zero_hops(conn: sqlite3.Connection) -> None:
    out = pathfinder.find_path(conn, from_type="provider", from_id="cgl",
                                to_type="provider", to_id="cgl")
    assert out["found"] and out["hops"] == 0 and out["path"] == []


def test_a_bad_endpoint_kind_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        pathfinder.find_path(conn, from_type="company", from_id="1",
                              to_type="authority", to_id="E09000007")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/relationship_path" in openapi.document()["paths"]
