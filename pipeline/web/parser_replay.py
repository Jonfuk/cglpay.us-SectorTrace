"""Parser replay sandbox (BETA-103).

Replay one parser against one archived object, in memory, and compare its
**non-persisted** proposed output with the stored active version's elements,
tables and warnings. Diagnosing an extraction change should not need CLI
context and must never be confused with a committed warehouse change.

Read-only contract:
  * the archived bytes are read from `data/raw/` and their SHA-256 is
    checked against `evidence_records.payload_sha256`;
  * the parse runs entirely in memory — nothing is written to any table;
  * only the stdlib parsers (`html`, `docx`, `pptx`) can be replayed here.
    A PDF, or a request for `docling` / `pymupdf`, returns
    `available: false` rather than importing a heavy optional dependency
    into a web request.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from pipeline.web.public_queries import _one, _public, _rows
from pipeline.web.queries import QueryError

# mime type -> the stdlib parser name that can replay it offline.
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_REPLAYABLE = {"text/html": "html", _DOCX: "docx", _PPTX: "pptx"}
_ARCHIVE_MAX = 32 * 1024 * 1024


def _stored(conn: sqlite3.Connection, document_id: str) -> dict:
    _public(["document_records", "document_versions", "document_elements",
              "document_tables", "document_quality", "evidence_records"])
    doc = _one(conn, """
        SELECT d.document_id, d.title, v.document_version_id, v.parser_name,
               v.parser_version, e.evidence_id, e.raw_object_path, e.mime_type,
               e.payload_sha256, e.source_system
        FROM document_records d
        JOIN document_versions v ON v.document_id = d.document_id
                                 AND v.is_active = 1
        JOIN evidence_records e ON e.evidence_id = d.evidence_id
        WHERE d.document_id = ?""", (document_id,))
    if not doc:
        raise QueryError(f"No document {document_id!r} with an active version.")
    elements = _rows(conn,
                     "SELECT sequence, element_type, text FROM document_elements "
                     "WHERE document_version_id = ? ORDER BY sequence",
                     (doc["document_version_id"],))
    tables = _rows(conn,
                   "SELECT de.sequence, dt.row_count, dt.column_count "
                   "FROM document_tables dt "
                   "JOIN document_elements de "
                   "  ON de.document_element_id = dt.document_element_id "
                   "WHERE de.document_version_id = ? ORDER BY de.sequence",
                   (doc["document_version_id"],))
    q = _one(conn, "SELECT warnings_json FROM document_quality "
                   "WHERE document_version_id = ?", (doc["document_version_id"],))
    try:
        warnings = json.loads(q["warnings_json"]) if q and q["warnings_json"] else []
    except (TypeError, ValueError):
        warnings = []
    doc["_elements"] = elements
    doc["_tables"] = tables
    doc["_warnings"] = warnings if isinstance(warnings, list) else [warnings]
    return doc


def _read_archive(settings, raw_object_path: str | None, sha256: str | None) -> tuple[bytes | None, bool | None, str]:
    if not raw_object_path:
        return None, None, "no archived object is recorded for this document"
    rel = str(raw_object_path).removeprefix("data/raw/")
    path = Path(getattr(settings, "raw_archive_dir", "data/raw")) / rel
    if not path.is_file():
        return None, None, "the archived object is not on disk"
    if path.stat().st_size > _ARCHIVE_MAX:
        return None, None, "the archived object is too large to replay in a request"
    body = path.read_bytes()
    verified = (hashlib.sha256(body).hexdigest() == sha256) if sha256 else None
    return body, verified, ""


def replay(conn: sqlite3.Connection, settings, document_id: str,
           parser: str | None = None) -> dict:
    doc = _stored(conn, document_id)
    common = {
        "document": {"document_id": document_id, "title": doc["title"]},
        "stored": {
            "parser": f"{doc['parser_name']} {doc['parser_version']}",
            "element_count": len(doc["_elements"]),
            "table_count": len(doc["_tables"]),
            "warnings": doc["_warnings"],
        },
        "note": "This is a test run against the archived bytes. The parse ran "
                "in memory and nothing was written to the warehouse — the "
                "stored version is unchanged.",
    }

    mime = doc["mime_type"] or ""
    want = parser or _REPLAYABLE.get(mime)
    if want not in _REPLAYABLE.values():
        return {**common, "available": False,
                "reason": f"replay covers the stdlib parsers only "
                          f"({', '.join(sorted(set(_REPLAYABLE.values())))}); "
                          f"{mime or 'this document'} is not one of them."}

    body, verified, err = _read_archive(settings, doc["raw_object_path"],
                                         doc["payload_sha256"])
    if body is None:
        return {**common, "available": False, "reason": err}

    from pipeline.documents.parsers import get_parser

    try:
        parsed = get_parser(want).parse(body, mime)
    except Exception as exc:  # a parser that chokes is a diagnostic result
        return {**common, "available": True, "parser": want,
                "archive": {"verified": verified},
                "proposed": {"error": f"{type(exc).__name__}: {exc}"},
                "diff": None}

    proposed_elements = [
        {"sequence": e.sequence, "element_type": e.element_type,
         "text": e.text or ""} for e in parsed.elements]
    by_seq_stored = {e["sequence"]: e for e in doc["_elements"]}
    by_seq_proposed = {e["sequence"]: e for e in proposed_elements}
    seqs = sorted(set(by_seq_stored) | set(by_seq_proposed))

    text_changes = []
    added = removed = changed = 0
    for seq in seqs:
        s, p = by_seq_stored.get(seq), by_seq_proposed.get(seq)
        if s and not p:
            removed += 1
            kind = "removed"
        elif p and not s:
            added += 1
            kind = "added"
        elif (s["text"] or "") == (p["text"] or ""):
            continue
        else:
            changed += 1
            kind = "changed"
        text_changes.append({
            "sequence": seq, "kind": kind,
            "stored": (s or {}).get("text"),
            "proposed": (p or {}).get("text"),
        })

    return {
        **common,
        "available": True,
        "parser": f"{parsed.parser_name} {parsed.parser_version}",
        "archive": {"verified": verified},
        "proposed": {
            "element_count": len(proposed_elements),
            "table_count": len(parsed.tables),
            "warnings": list(getattr(parsed, "warnings", []) or []),
        },
        "diff": {
            "elements": {"added": added, "removed": removed, "changed": changed},
            "text_changes": text_changes[:200],
            "tables": {"stored": len(doc["_tables"]),
                        "proposed": len(parsed.tables)},
            "truncated": len(text_changes) > 200,
        },
    }
