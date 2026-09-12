"""Document table extraction viewer (BETA-099).

Tables detected in a parsed document — the grid the parser wrote to
`document_tables`, its page context and extraction status. No cell is
re-detected or reconstructed.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import doc_tables
from pipeline.web.queries import QueryError

_NOW = "2026-08-01T00:00:00Z"


def _doc(conn, *, source_system="committee_paper_promotion"):
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, mime_type, "
        " content_length, source_table, source_key, created_at) VALUES "
        "('ev1', %s, 'https://x/1', %s, 200, 's1', 'r/x.pdf', 'application/pdf', "
        " 10, 'committee_papers', 'k1', %s)", (source_system, _NOW, _NOW))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, "
        " source_key, document_type, mime_type, title, created_at, updated_at) "
        "VALUES ('d1', 'ev1', 'committee_papers', 'k1', 'committee_paper', "
        " 'application/pdf', 'Board pack', %s, %s)", (_NOW, _NOW))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, "
        " parser_name, parser_version, parse_schema_version, config_hash, "
        " text_sha256, status, is_active, created_at) VALUES "
        "('v1', 'd1', 'docling', '1', '1', 'c', 't', 'parsed', 1, %s)", (_NOW,))
    els = [
        ("e0", "HEADING", 0, "Table 3: staff costs by band", None),
        ("e1", "table", 1, "band | headcount", '[["Band","Headcount"],["5","12"],["6","4"]]'),
        ("e2", "table", 2, "| x |\n|---|", "[]"),
    ]
    for eid, etype, seq, text, tjson in els:
        conn.execute(
            "INSERT INTO document_elements (document_element_id, "
            " document_version_id, element_type, sequence, page_number, text, "
            " text_sha256, metadata_json) VALUES (%s, 'v1', %s, %s, 1, %s, 'h', '{}')",
            (eid, etype, seq, text))
        if etype == "table":
            conn.execute(
                "INSERT INTO document_tables (document_table_id, "
                " document_element_id, row_count, column_count, table_json, "
                " markdown) VALUES (%s, %s, %s, %s, %s, %s)",
                (f"dt-{eid}", eid, 3 if eid == "e1" else 0,
                 2 if eid == "e1" else 0, tjson,
                 "| x |\n|---|" if eid == "e2" else None))
    conn.commit()


def test_the_list_reports_page_and_extraction_status(conn: sqlite3.Connection) -> None:
    _doc(conn)
    out = doc_tables.tables(conn, "d1")
    assert out["document"]["title"] == "Board pack"
    statuses = {t["document_table_id"]: t["extraction_status"] for t in out["tables"]}
    assert statuses == {"dt-e1": "structured", "dt-e2": "markdown_only"}
    structured = next(t for t in out["tables"] if t["document_table_id"] == "dt-e1")
    assert structured["page_number"] == 1
    assert structured["preview"] == [["Band", "Headcount"], ["5", "12"], ["6", "4"]]
    assert structured["reading_room_link"] == "#/documents?doc=d1&el=e1"
    assert "no cell is re-detected" in out["note"].lower()


def test_the_detail_returns_the_parser_grid_verbatim(conn: sqlite3.Connection) -> None:
    _doc(conn)
    out = doc_tables.table_detail(conn, "dt-e1")
    assert out["grid"] == [["Band", "Headcount"], ["5", "12"], ["6", "4"]]
    assert out["caption"] == "Table 3: staff costs by band"
    assert out["extraction_status"] == "structured"
    assert out["row_count"] == 3 and out["column_count"] == 2
    assert "parser's own extraction" in out["note"].lower()
    assert out["reading_room_link"] == "#/documents?doc=d1&el=e1"


def test_a_non_allowlisted_source_is_refused(conn: sqlite3.Connection) -> None:
    _doc(conn, source_system="pfd_report")
    with pytest.raises(QueryError):
        doc_tables.tables(conn, "d1")
    with pytest.raises(QueryError):
        doc_tables.table_detail(conn, "dt-e1")


def test_unknown_document_and_table_raise(conn: sqlite3.Connection) -> None:
    with pytest.raises(QueryError):
        doc_tables.tables(conn, "nope")
    with pytest.raises(QueryError):
        doc_tables.table_detail(conn, "nope")


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/document_tables" in openapi.document()["paths"]
