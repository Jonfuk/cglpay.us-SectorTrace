"""Document table extraction viewer (BETA-099).

Tables detected in parsed documents — the grid the parser produced, its page
context, its extraction status, and a structured (CSV) download built from
exactly what was extracted. Important evidence often sits in tables that
paragraph search and plain-text snippets make hard to read accurately.

The structure comes from `document_tables.table_json` (a JSON array of rows
the parser wrote) — nothing here re-detects a table or reconstructs a cell.
A table whose `table_json` is empty is shown with `extraction_status`
`markdown_only` or `empty`, not with an invented grid. Documents are gated by
the same `DOCUMENT_SEARCH_SOURCES` allowlist as `document_search`.
"""
from __future__ import annotations

import json
import sqlite3

from pipeline.web.public_queries import (
    DOCUMENT_SEARCH_SOURCES,
    _one,
    _public,
    _rows,
)
from pipeline.web.queries import QueryError

_PREVIEW_ROWS = 3
_CONTEXT_ELEMENTS = 2


def _grid(table_json: str | None) -> list[list[str]]:
    try:
        data = json.loads(table_json or "[]")
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    out: list[list[str]] = []
    for row in data:
        if isinstance(row, list):
            out.append([("" if c is None else str(c)) for c in row])
    return out


def _status(grid: list[list[str]], markdown: str | None) -> str:
    if grid and any(any(cell.strip() for cell in row) for row in grid):
        return "structured"
    if markdown and markdown.strip():
        return "markdown_only"
    return "empty"


_TABLES = ("document_tables", "document_elements", "document_versions",
           "document_records", "evidence_records")


def _doc_guard(conn: sqlite3.Connection, document_id: str) -> dict:
    _public(list(_TABLES))
    row = _one(conn, """
        SELECT d.document_id, d.title, e.source_system, e.source_url,
               e.retrieved_at
        FROM document_records d
        JOIN evidence_records e ON e.evidence_id = d.evidence_id
        WHERE d.document_id = ?""", (document_id,))
    if not row:
        raise QueryError(f"No document {document_id!r}.")
    if row["source_system"] not in DOCUMENT_SEARCH_SOURCES:
        raise QueryError("That document is not available on the portal.")
    return row


def tables(conn: sqlite3.Connection, document_id: str) -> dict:
    doc = _doc_guard(conn, document_id)
    rows = _rows(conn, """
        SELECT dt.document_table_id, dt.document_element_id, dt.row_count,
               dt.column_count, dt.table_json, dt.markdown,
               de.sequence, de.page_number
        FROM document_tables dt
        JOIN document_elements de ON de.document_element_id = dt.document_element_id
        JOIN document_versions v ON v.document_version_id = de.document_version_id
                                 AND v.is_active = 1
        JOIN document_records d ON d.document_id = v.document_id
        WHERE d.document_id = ?
        ORDER BY de.sequence""", (document_id,))

    out = []
    by_status: dict[str, int] = {}
    for r in rows:
        grid = _grid(r["table_json"])
        status = _status(grid, r["markdown"])
        by_status[status] = by_status.get(status, 0) + 1
        out.append({
            "document_table_id": r["document_table_id"],
            "element_id": r["document_element_id"],
            "sequence": r["sequence"],
            "page_number": r["page_number"],
            "row_count": r["row_count"] if r["row_count"] is not None else len(grid),
            "column_count": r["column_count"] if r["column_count"] is not None
            else max((len(row) for row in grid), default=0),
            "extraction_status": status,
            "preview": grid[:_PREVIEW_ROWS],
            "reading_room_link": (f"#/documents?doc={document_id}"
                                   f"&el={r['document_element_id']}"),
        })

    return {
        "document": {"document_id": document_id, "title": doc["title"],
                      "source_url": doc["source_url"],
                      "retrieved_at": doc["retrieved_at"]},
        "tables": out,
        "counts": {"by_status": by_status},
        "statuses": ["structured", "markdown_only", "empty"],
        "note": "Each grid is exactly what the parser wrote to "
                "document_tables — no cell is re-detected or reconstructed. A "
                "markdown_only or empty status means the parse did not produce "
                "a structured grid for that table.",
    }


def table_detail(conn: sqlite3.Connection, document_table_id: str) -> dict:
    _public(list(_TABLES))
    r = _one(conn, """
        SELECT dt.document_table_id, dt.document_element_id, dt.row_count,
               dt.column_count, dt.table_json, dt.markdown,
               de.sequence, de.page_number, de.document_version_id,
               d.document_id, d.title, e.source_system, e.source_url,
               e.retrieved_at
        FROM document_tables dt
        JOIN document_elements de ON de.document_element_id = dt.document_element_id
        JOIN document_versions v ON v.document_version_id = de.document_version_id
        JOIN document_records d ON d.document_id = v.document_id
        JOIN evidence_records e ON e.evidence_id = d.evidence_id
        WHERE dt.document_table_id = ?""", (document_table_id,))
    if not r:
        raise QueryError(f"No table {document_table_id!r}.")
    if r["source_system"] not in DOCUMENT_SEARCH_SOURCES:
        raise QueryError("That document is not available on the portal.")

    grid = _grid(r["table_json"])
    context = _rows(conn, """
        SELECT sequence, element_type, text FROM document_elements
        WHERE document_version_id = ?
          AND sequence BETWEEN ? AND ?
          AND document_element_id <> ?
        ORDER BY sequence""",
        (r["document_version_id"], r["sequence"] - _CONTEXT_ELEMENTS,
         r["sequence"] + _CONTEXT_ELEMENTS, r["document_element_id"]))
    caption = next((c["text"] for c in reversed(context)
                    if c["sequence"] < r["sequence"]
                    and (c["element_type"] or "").upper() in
                    ("HEADING", "TITLE", "CAPTION")), None)

    return {
        "document_table_id": r["document_table_id"],
        "element_id": r["document_element_id"],
        "document": {"document_id": r["document_id"], "title": r["title"],
                      "source_url": r["source_url"],
                      "retrieved_at": r["retrieved_at"]},
        "page_number": r["page_number"],
        "caption": caption,
        "extraction_status": _status(grid, r["markdown"]),
        "grid": grid,
        "markdown": r["markdown"],
        "row_count": len(grid) or r["row_count"],
        "column_count": max((len(row) for row in grid), default=0)
        or r["column_count"],
        "context": [{"element_type": c["element_type"],
                      "text": (c["text"] or "")[:280]} for c in context],
        "reading_room_link": (f"#/documents?doc={r['document_id']}"
                               f"&el={r['document_element_id']}"),
        "note": "The grid is the parser's own extraction. Download it as CSV "
                "to work with exactly those cells; the source document is the "
                "authority for anything the parse got wrong.",
    }
