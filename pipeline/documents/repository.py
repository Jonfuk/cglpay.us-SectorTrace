"""Persistence and retrieval for canonical document representations."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

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
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
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
        "INSERT INTO document_processing_states (evidence_id) VALUES (?) "
        "ON CONFLICT(evidence_id) DO NOTHING", (reference.evidence_id,))


def upsert_document(conn, reference: EvidenceReference, document_type: str, method: str,
                    confidence: float, filename: str, mime_type: str, page_count: int | None,
                    title: str | None = None) -> str:
    document_id = stable_id("document", reference.evidence_id)
    now = utcnow()
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, source_key, document_type, "
        "classification_method, classification_confidence, mime_type, title, filename, page_count, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(evidence_id) DO UPDATE SET document_type=excluded.document_type, "
        "classification_method=excluded.classification_method, classification_confidence=excluded.classification_confidence, "
        "mime_type=excluded.mime_type, title=COALESCE(excluded.title, document_records.title), "
        "filename=excluded.filename, page_count=excluded.page_count, updated_at=excluded.updated_at",
        (document_id, reference.evidence_id, reference.source_table, reference.source_key, document_type,
         method, confidence, mime_type, title, filename, page_count, now, now),
    )
    return document_id


def add_artifact(conn, reference: EvidenceReference, artifact_type: str, storage_path: str,
                 sha256: str, tool_name: str, tool_version: str | None, parameters: dict) -> str:
    artifact_id = stable_id("artifact", f"{reference.evidence_id}|{artifact_type}|{sha256}")
    conn.execute(
        "INSERT INTO derived_artifacts (artifact_id, evidence_id, artifact_type, storage_path, sha256, tool_name, "
        "tool_version, parameters_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(evidence_id, artifact_type, sha256) DO NOTHING",
        (artifact_id, reference.evidence_id, artifact_type, storage_path, sha256, tool_name, tool_version,
         _json(parameters), utcnow()),
    )
    return artifact_id


def version_exists(conn, document_id: str, parser_name: str, parser_version: str, config_hash: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM document_versions WHERE document_id=? AND parser_name=? AND parser_version=? "
        "AND config_hash=?", (document_id, parser_name, parser_version, config_hash)).fetchone() is not None


def persist_parse(conn, document_id: str, parsed: ParsedDocument, config_hash: str,
                  source_artifact_id: str | None, quality_status: str, quality_metrics: dict,
                  quality_warnings: list[str], settings) -> str:
    version_id = stable_id("document-version", f"{document_id}|{parsed.parser_name}|{parsed.parser_version}|{config_hash}")
    now = utcnow()
    text_hash = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()
    conn.execute("UPDATE document_versions SET is_active=0 WHERE document_id=?", (document_id,))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, parser_name, parser_version, "
        "parse_schema_version, source_artifact_id, config_hash, text_sha256, status, is_active, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'SUCCESS', 1, ?) "
        "ON CONFLICT(document_id, parser_name, parser_version, config_hash) DO UPDATE SET "
        "is_active=1, status='SUCCESS', text_sha256=excluded.text_sha256",
        (version_id, document_id, parsed.parser_name, parsed.parser_version, "1", source_artifact_id,
         config_hash, text_hash, now),
    )
    conn.execute("DELETE FROM document_elements WHERE document_version_id=?", (version_id,))
    if settings.database_backend == "sqlite":
        conn.execute("DELETE FROM document_element_search WHERE document_id=?", (document_id,))
    element_ids: dict[int, str] = {}
    for item in parsed.elements:
        element_id = stable_id("document-element", f"{version_id}|{item.sequence}")
        element_ids[item.sequence] = element_id
        text_hash = hashlib.sha256((item.text or "").encode("utf-8")).hexdigest() if item.text else None
        conn.execute(
            "INSERT INTO document_elements (document_element_id, document_version_id, parent_element_id, "
            "element_type, sequence, page_number, heading_level, text, text_sha256, bbox_json, metadata_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (element_id, version_id, None, item.element_type, item.sequence, item.page_number,
             item.heading_level, item.text, text_hash, _json(item.bbox) if item.bbox else None,
             _json(item.metadata)),
        )
        if settings.database_backend == "sqlite" and item.text:
            # Named columns here despite positional being the FTS5 idiom. SQLite refuses
            # ALTER on a virtual table, so this cannot drift the way 0054 drifted
            # evidence_records; what remains reachable is a migration dropping and
            # recreating the table in a different order, which naming survives.
            conn.execute(
                "INSERT INTO document_element_search (document_element_id, document_id, page_number, "
                "element_type, text) VALUES (?, ?, ?, ?, ?)",
                (element_id, document_id, item.page_number, item.element_type, item.text))
        for topic, count in topic_matches(item.text or "").items():
            conn.execute(
                "INSERT INTO document_topics (document_element_id, topic, match_count, match_method) "
                "VALUES (?, ?, ?, 'keyword_v1')",
                (element_id, topic, count))
    for item in parsed.elements:
        if item.parent_sequence is not None:
            conn.execute("UPDATE document_elements SET parent_element_id=? WHERE document_element_id=?",
                         (element_ids.get(item.parent_sequence), element_ids[item.sequence]))
    for table in parsed.tables:
        element_id = element_ids[table.element_sequence]
        conn.execute(
            "INSERT INTO document_tables (document_table_id, document_element_id, row_count, column_count, "
            "table_json, markdown) VALUES (?, ?, ?, ?, ?, ?)",
            (stable_id("document-table", element_id), element_id, len(table.rows),
             max((len(row) for row in table.rows), default=0), _json(table.rows), table.markdown))
    for link in parsed.links:
        element_id = element_ids[link.element_sequence]
        conn.execute(
            "INSERT INTO document_links (document_link_id, document_element_id, href, anchor_text) "
            "VALUES (?, ?, ?, ?)",
            (stable_id("document-link", f"{element_id}|{link.href}"), element_id, link.href,
             link.anchor_text))
    conn.execute(
        "INSERT INTO document_quality (document_version_id, status, metrics_json, warnings_json, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(document_version_id) DO UPDATE SET status=excluded.status, metrics_json=excluded.metrics_json, "
        "warnings_json=excluded.warnings_json",
        (version_id, quality_status, _json(quality_metrics), _json(quality_warnings), now))
    conn.execute(
        "UPDATE document_processing_states SET parse_status='SUCCESS', classification_status='SUCCESS', "
        "quality_status=?, active_document_version_id=?, last_processed_at=?, last_error=NULL "
        "WHERE evidence_id=(SELECT evidence_id FROM document_records WHERE document_id=?)",
        (quality_status, version_id, now, document_id))
    return version_id


def mark_attempt(conn, evidence_id: str, inspection_status: str, ocr_status: str, error: str | None = None) -> None:
    now = utcnow()
    conn.execute(
        "UPDATE document_processing_states SET inspection_status=?, ocr_status=?, "
        "parse_status=?, attempt_count=attempt_count+1, last_error=?, last_attempted_at=? WHERE evidence_id=?",
        (inspection_status, ocr_status, "FAILED" if error else "RUNNING", error, now, evidence_id))


def mark_unchanged(conn, evidence_id: str, ocr_status: str) -> None:
    """Restore the completed state when an existing active version is reused."""
    conn.execute(
        "UPDATE document_processing_states SET parse_status='SUCCESS', ocr_status=?, last_error=NULL "
        "WHERE evidence_id=?", (ocr_status, evidence_id))


def search(conn, settings, query: str, limit: int = 25) -> list[dict]:
    if settings.database_backend == "sqlite":
        rows = conn.execute(
            "SELECT s.document_element_id, s.document_id, s.page_number, s.element_type, s.text, "
            "d.evidence_id, e.source_url FROM document_element_search s JOIN document_records d ON d.document_id=s.document_id "
            "JOIN evidence_records e ON e.evidence_id=d.evidence_id WHERE document_element_search MATCH ? LIMIT ?",
            (query, limit)).fetchall()
    else:
        rows = conn.execute(
            "SELECT de.document_element_id, d.document_id, de.page_number, de.element_type, de.text, d.evidence_id, e.source_url "
            "FROM document_elements de JOIN document_versions dv ON dv.document_version_id=de.document_version_id "
            "JOIN document_records d ON d.document_id=dv.document_id JOIN evidence_records e ON e.evidence_id=d.evidence_id "
            "WHERE dv.is_active=1 AND to_tsvector('simple', COALESCE(de.text, '')) @@ plainto_tsquery('simple', ?) LIMIT ?",
            (query, limit)).fetchall()
    return [dict(row) for row in rows]
