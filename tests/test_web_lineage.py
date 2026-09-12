"""Pipeline and data-lineage graph (BETA-102).

One typed graph composed from the machine-owned registries and the live
schema: source -> module -> table -> table -> export. Every edge is derived;
none is hand-maintained. The endpoint writes nothing.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline import catalog
from pipeline.registry import discover_modules
from pipeline.web import lineage
from pipeline.web.server import build_server


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    discover_modules()


def _ids(graph):
    return {n["id"] for n in graph["nodes"]}


def test_graph_is_typed_and_every_edge_lands_on_a_node(conn: sqlite3.Connection) -> None:
    g = lineage.graph(conn)
    assert g["node_kinds"] == ["source", "module", "table", "export"]
    assert set(g["counts"]["by_kind"]) <= set(g["node_kinds"])
    assert set(g["counts"]["by_rel"]) <= set(g["edge_kinds"])
    ids = _ids(g)
    for e in g["edges"]:
        assert e["source"] in ids and e["target"] in ids
        assert e["rel"] in g["edge_kinds"]
    assert "none is hand-maintained" in g["note"].lower()
    assert any("route" in reason.lower() for reason in g["omitted"])


def test_source_module_table_chain_is_present(conn: sqlite3.Connection) -> None:
    g = lineage.graph(conn)
    edges = {(e["source"], e["rel"], e["target"]) for e in g["edges"]}
    assert ("source:public-health-grant", "collected_by",
            "module:m11_public_health_grant") in edges
    assert ("module:m11_public_health_grant", "writes",
            "table:public_health_grants") in edges
    # the module carries its wave and review/parse debt from the registry
    mod = next(n for n in g["nodes"] if n["id"] == "module:m11_public_health_grant")
    assert "wave" in mod and "pending_review" in mod and "consumer_count" in mod


def test_foreign_keys_become_reference_edges(conn: sqlite3.Connection) -> None:
    g = lineage.graph(conn)
    ref_edges = {(e["source"], e["target"]) for e in g["edges"]
                 if e["rel"] == "references"}
    assert ref_edges, "no foreign-key edges derived from the live schema"
    for fk in catalog.foreign_key_columns(conn):
        assert (f"table:{fk['child']}", f"table:{fk['parent']}") in ref_edges
    for src, tgt in ref_edges:
        assert src.startswith("table:") and tgt.startswith("table:")


def test_exports_read_tables_from_the_tab_registry(conn: sqlite3.Connection) -> None:
    from pipeline.exports.schema import TABS

    g = lineage.graph(conn)
    export_ids = {f"export:{t.name}" for t in TABS}
    exported = [e for e in g["edges"] if e["rel"] == "exported_by"]
    assert exported
    for e in exported:
        assert e["source"].startswith("table:")
        assert e["target"] in export_ids
    # 01_Authorities reads `authorities`
    assert ("table:authorities", "exported_by", "export:01_Authorities") in {
        (e["source"], e["rel"], e["target"]) for e in exported}


def test_the_graph_writes_nothing(conn: sqlite3.Connection) -> None:
    before = catalog.list_objects(conn)
    lineage.graph(conn)
    lineage.graph(conn)
    assert catalog.list_objects(conn) == before


def test_the_route_serves_the_graph(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            out = http.get("/api/admin/lineage").json()
            assert out["counts"]["by_kind"]["module"] > 0
            assert out["counts"]["by_rel"]["references"] > 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
