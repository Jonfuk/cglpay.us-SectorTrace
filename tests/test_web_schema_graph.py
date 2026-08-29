"""Schema-aware data explorer read model (BETA-083).

A read-only schema graph — tables, columns, foreign-key edges and short
descriptions — composed from the existing catalogue helpers. No new SQL
surface, no row reads; the table browser's restricted-table gate, timeout and
row caps are untouched.
"""
from __future__ import annotations

import sqlite3

from pipeline import catalog
from pipeline.web import queries


def test_the_graph_describes_tables_columns_and_keys(conn: sqlite3.Connection) -> None:
    graph = queries.schema_graph(conn)
    by_name = {t["name"]: t for t in graph["tables"]}

    assert "document_records" in by_name
    doc = by_name["document_records"]
    assert doc["description"]                       # registered description
    col_names = {c["name"] for c in doc["columns"]}
    assert "evidence_id" in col_names

    ev_col = next(c for c in doc["columns"] if c["name"] == "evidence_id")
    assert ev_col["fk"] == {"table": "evidence_records", "column": "evidence_id"}

    # table-level edges are present too
    assert ["document_records", "evidence_records"] in graph["edges"]


def test_it_reads_no_rows_and_keeps_the_restricted_flag(conn: sqlite3.Connection) -> None:
    graph = queries.schema_graph(conn)
    restricted = [t["name"] for t in graph["tables"] if t["restricted"]]
    assert restricted, "no restricted tables flagged"
    assert all(t["name"].startswith("restricted_") for t in graph["tables"]
               if t["restricted"])
    # `rows` is a count for a table and None for a view — the same shape the
    # sidebar already uses.
    assert any(t["rows"] is not None for t in graph["tables"] if t["type"] == "table")


def test_foreign_key_columns_helper_gives_column_level_edges(conn: sqlite3.Connection) -> None:
    edges = catalog.foreign_key_columns(conn)
    assert edges
    for edge in edges:
        assert set(edge) == {"child", "from_col", "parent", "to_col"}
        assert edge["child"] != edge["parent"]     # self-references dropped
    doc_edge = next(e for e in edges if e["child"] == "document_records"
                    and e["from_col"] == "evidence_id")
    assert doc_edge["parent"] == "evidence_records"
    assert doc_edge["to_col"] == "evidence_id"


def test_the_route_serves_it(conn: sqlite3.Connection, settings) -> None:
    import threading

    import httpx

    from pipeline.web.server import build_server

    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=30.0
        ) as http:
            got = http.get("/api/admin/schema-graph")
            assert got.status_code == 200
            body = got.json()
            assert "tables" in body and "edges" in body and "described" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
