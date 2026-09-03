"""Persistence and retrieval for canonical document representations."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from pipeline.documents import titles
from pipeline.documents.classify import topic_matches
from pipeline.documents.models import EvidenceReference, ParsedDocument


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_id(kind: str, value: str) -> str:
    return f"{kind}-{uuid.uuid5(uuid.NAMESPACE_URL, value)}"


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def upsert_evidence(conn, reference: EvidenceReference) -> None:
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, retrieved_at, http_status, "
        "payload_sha256, raw_object_path, mime_type, content_length, source_table, source_key, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT(evidence_id) DO UPDATE SET source_url=excluded.source_url, "
        "retrieved_at=excluded.retrieved_at, http_status=excluded.http_status, "
        "raw_object_path=excluded.raw_object_path, mime_type=excluded.mime_type, "
        "content_length=excluded.content_length, source_table=COALESCE(excluded.source_table, evidence_records.source_table), "
        "source_key=COALESCE(excluded.source_key, evidence_records.source_key)",
        (reference.evidence_id, reference.source_system, reference.source_url, reference.retrieved_at,
         reference.http_status, reference.payload_sha256, reference.raw_object_path, reference.mime_type,
         reference.content_length, reference.source_table, reference.source_key, utcnow()),
    )
    conn.execute(
        "INSERT INTO document_processing_states (evidence_id) VALUES (%s) "
        "ON CONFLICT(evidence_id) DO NOTHING", (reference.evidence_id,))


def upsert_document(conn, reference: EvidenceReference, document_type: str, method: str,
                    confidence: float, filename: str, mime_type: str, page_count: int | None,
                    title: str | None = None) -> str:
    document_id = stable_id("document", reference.evidence_id)
    now = utcnow()
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, source_key, document_type, "
        "classification_method, classification_confidence, mime_type, title, filename, page_count, created_at, updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT(evidence_id) DO UPDATE SET document_type=excluded.document_type, "
        "classification_method=excluded.classification_method, classification_confidence=excluded.classification_confidence, "
        "mime_type=excluded.mime_type, title=COALESCE(excluded.title, document_records.title), "
        "filename=excluded.filename, page_count=excluded.page_count, updated_at=excluded.updated_at",
        (document_id, reference.evidence_id, reference.source_table, reference.source_key, document_type,
         method, confidence, mime_type, title, filename, page_count, now, now),
    )
    return document_id


def _active_headings(conn, document_id: str, limit: int = 8) -> list[str]:
    """The first few heading texts of the active parsed version, in order.

    `titles.derive` takes the first that reads as a real name, so a short head
    is enough — and a document with hundreds of headings should not scan them
    all to name itself."""
    rows = conn.execute(
        "SELECT de.text FROM document_elements de "
        "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
        "WHERE dv.document_id = %s AND dv.is_active = 1 "
        "AND (de.heading_level IS NOT NULL OR de.element_type IN ('HEADING', 'TITLE')) "
        "ORDER BY de.sequence LIMIT %s", (document_id, limit))
    return [row["text"] for row in rows if row["text"]]


def refresh_display_title(conn, document_id: str, *, source_title: str | None,
                          pdf_title: str | None = None) -> tuple[str | None, str]:
    """Recompute `document_records.display_title` / `title_basis` from the
    source label, the PDF /Title, the active version's headings and the
    filename. Deterministic and safe to re-run; caller commits."""
    row = conn.execute(
        "SELECT filename FROM document_records WHERE document_id = %s",
        (document_id,)).fetchone()
    filename = row["filename"] if row else None
    display, basis = titles.derive(
        source_title=source_title, pdf_title=pdf_title,
        headings=_active_headings(conn, document_id), filename=filename)
    conn.execute(
        "UPDATE document_records SET display_title = %s, title_basis = %s, updated_at = %s "
        "WHERE document_id = %s", (display, basis, utcnow(), document_id))
    return display, basis


def backfill_display_titles(conn, *, recompute: bool = False) -> dict:
    """Fill `display_title` / `title_basis` for existing rows (BETA-062).

    Without `recompute`, only rows that have neither set. No `pdf_title` is
    available here — that rung is only reachable on a reparse — so a row whose
    only signal is a hash-like filename resolves to `title_basis='unknown'`
    and the portal keeps showing its raw fallback. Commits per row, the way
    the rest of this pipeline does."""
    clause = "" if recompute else "WHERE display_title IS NULL AND title_basis IS NULL"
    ids = [r["document_id"] for r in conn.execute(
        f"SELECT document_id FROM document_records {clause} ORDER BY document_id")]
    by_basis: dict[str, int] = {}
    for document_id in ids:
        source_title = conn.execute(
            "SELECT title FROM document_records WHERE document_id = %s",
            (document_id,)).fetchone()["title"]
        _, basis = refresh_display_title(conn, document_id, source_title=source_title)
        by_basis[basis] = by_basis.get(basis, 0) + 1
        conn.commit()
    return {"updated": len(ids), "by_basis": by_basis}


def add_artifact(conn, reference: EvidenceReference, artifact_type: str, storage_path: str,
                 sha256: str, tool_name: str, tool_version: str | None, parameters: dict) -> str:
    artifact_id = stable_id("artifact", f"{reference.evidence_id}|{artifact_type}|{sha256}")
    conn.execute(
        "INSERT INTO derived_artifacts (artifact_id, evidence_id, artifact_type, storage_path, sha256, tool_name, "
        "tool_version, parameters_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT(evidence_id, artifact_type, sha256) DO NOTHING",
        (artifact_id, reference.evidence_id, artifact_type, storage_path, sha256, tool_name, tool_version,
         _json(parameters), utcnow()),
    )
    return artifact_id


def version_exists(conn, document_id: str, parser_name: str, parser_version: str, config_hash: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM document_versions WHERE document_id=%s AND parser_name=%s AND parser_version=%s "
        "AND config_hash=%s", (document_id, parser_name, parser_version, config_hash)).fetchone() is not None


def persist_parse(conn, document_id: str, parsed: ParsedDocument, config_hash: str,
                  source_artifact_id: str | None, quality_status: str, quality_metrics: dict,
                  quality_warnings: list[str], settings) -> str:
    version_id = stable_id("document-version", f"{document_id}|{parsed.parser_name}|{parsed.parser_version}|{config_hash}")
    now = utcnow()
    text_hash = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()
    conn.execute("UPDATE document_versions SET is_active=0 WHERE document_id=%s", (document_id,))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, parser_name, parser_version, "
        "parse_schema_version, source_artifact_id, config_hash, text_sha256, status, is_active, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'SUCCESS', 1, %s) "
        "ON CONFLICT(document_id, parser_name, parser_version, config_hash) DO UPDATE SET "
        "is_active=1, status='SUCCESS', text_sha256=excluded.text_sha256",
        (version_id, document_id, parsed.parser_name, parsed.parser_version, "1", source_artifact_id,
         config_hash, text_hash, now),
    )
    conn.execute("DELETE FROM document_elements WHERE document_version_id=%s", (version_id,))
    element_ids: dict[int, str] = {}
    for item in parsed.elements:
        element_id = stable_id("document-element", f"{version_id}|{item.sequence}")
        element_ids[item.sequence] = element_id
        text_hash = hashlib.sha256((item.text or "").encode("utf-8")).hexdigest() if item.text else None
        conn.execute(
            "INSERT INTO document_elements (document_element_id, document_version_id, parent_element_id, "
            "element_type, sequence, page_number, heading_level, text, text_sha256, bbox_json, metadata_json) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (element_id, version_id, None, item.element_type, item.sequence, item.page_number,
             item.heading_level, item.text, text_hash, _json(item.bbox) if item.bbox else None,
             _json(item.metadata)),
        )
        # No FTS5 index to maintain here any more: PostgreSQL search is a
        # `tsvector` computed over document_elements.text at query time
        # (see `search` below and semantic_search), so the element row is the
        # whole write.
        for topic, count in topic_matches(item.text or "").items():
            conn.execute(
                "INSERT INTO document_topics (document_element_id, topic, match_count, match_method) "
                "VALUES (%s, %s, %s, 'keyword_v1')",
                (element_id, topic, count))
    for item in parsed.elements:
        if item.parent_sequence is not None:
            conn.execute("UPDATE document_elements SET parent_element_id=%s WHERE document_element_id=%s",
                         (element_ids.get(item.parent_sequence), element_ids[item.sequence]))
    for table in parsed.tables:
        element_id = element_ids[table.element_sequence]
        conn.execute(
            "INSERT INTO document_tables (document_table_id, document_element_id, row_count, column_count, "
            "table_json, markdown) VALUES (%s, %s, %s, %s, %s, %s)",
            (stable_id("document-table", element_id), element_id, len(table.rows),
             max((len(row) for row in table.rows), default=0), _json(table.rows), table.markdown))
    for link in parsed.links:
        element_id = element_ids[link.element_sequence]
        conn.execute(
            "INSERT INTO document_links (document_link_id, document_element_id, href, anchor_text) "
            "VALUES (%s, %s, %s, %s)",
            (stable_id("document-link", f"{element_id}|{link.href}"), element_id, link.href,
             link.anchor_text))
    conn.execute(
        "INSERT INTO document_quality (document_version_id, status, metrics_json, warnings_json, created_at) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT(document_version_id) DO UPDATE SET status=excluded.status, metrics_json=excluded.metrics_json, "
        "warnings_json=excluded.warnings_json",
        (version_id, quality_status, _json(quality_metrics), _json(quality_warnings), now))
    conn.execute(
        "UPDATE document_processing_states SET parse_status='SUCCESS', classification_status='SUCCESS', "
        "quality_status=%s, active_document_version_id=%s, last_processed_at=%s, last_error=NULL "
        "WHERE evidence_id=(SELECT evidence_id FROM document_records WHERE document_id=%s)",
        (quality_status, version_id, now, document_id))
    return version_id


def mark_attempt(conn, evidence_id: str, inspection_status: str, ocr_status: str, error: str | None = None) -> None:
    now = utcnow()
    conn.execute(
        "UPDATE document_processing_states SET inspection_status=%s, ocr_status=%s, "
        "parse_status=%s, attempt_count=attempt_count+1, last_error=%s, last_attempted_at=%s WHERE evidence_id=%s",
        (inspection_status, ocr_status, "FAILED" if error else "RUNNING", error, now, evidence_id))


def mark_unchanged(conn, evidence_id: str, ocr_status: str) -> None:
    """Restore the completed state when an existing active version is reused."""
    conn.execute(
        "UPDATE document_processing_states SET parse_status='SUCCESS', ocr_status=%s, last_error=NULL "
        "WHERE evidence_id=%s", (ocr_status, evidence_id))


def search(conn, settings, query: str, limit: int = 25) -> list[dict]:
    rows = conn.execute(
        "SELECT de.document_element_id, d.document_id, de.page_number, de.element_type, de.text, d.evidence_id, e.source_url "
        "FROM document_elements de JOIN document_versions dv ON dv.document_version_id=de.document_version_id "
        "JOIN document_records d ON d.document_id=dv.document_id JOIN evidence_records e ON e.evidence_id=d.evidence_id "
        "WHERE dv.is_active=1 AND to_tsvector('simple', COALESCE(de.text, '')) @@ plainto_tsquery('simple', %s) LIMIT %s",
        (query, limit)).fetchall()
    return [dict(row) for row in rows]
