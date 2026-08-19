"""Seed the Evidence Graph registry from existing, provenance-bearing tables."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any

BACKFILL_VERSION = "1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def _stable_id(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def _relationship_id(*parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"relationship:{digest}"


def _evidence_id(source_system: str, payload_sha256: str) -> str:
    return _stable_id("evidence", f"{source_system}:{payload_sha256}")


def _upsert_entity(conn: Any, entity_id: str, entity_type: str, name: str, now: str) -> None:
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, canonical_name_normalized, "
        "status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?) "
        "ON CONFLICT(entity_id) DO UPDATE SET entity_type = excluded.entity_type, "
        "canonical_name = excluded.canonical_name, canonical_name_normalized = excluded.canonical_name_normalized, "
        "updated_at = excluded.updated_at",
        (entity_id, entity_type, name, _normalise(name), now, now),
    )


def _identifier(conn: Any, entity_id: str, scheme: str, value: str, now: str) -> None:
    conn.execute(
        "INSERT INTO entity_identifiers (entity_id, identifier_scheme, identifier_value, created_at) "
        "VALUES (?, ?, ?, ?) ON CONFLICT(identifier_scheme, identifier_value) DO NOTHING",
        (entity_id, scheme, value, now),
    )


def _evidence(conn: Any, row: dict, now: str) -> str:
    evidence_id = _evidence_id(row["source_system"], row["payload_sha256"])
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, retrieved_at, http_status, "
        "payload_sha256, raw_object_path, created_at) VALUES (?, ?, ?, ?, ?, ?, NULL, ?) "
        "ON CONFLICT(evidence_id) DO NOTHING",
        (evidence_id, row["source_system"], row["source_url"], row["retrieved_at"],
         row["http_status"], row["payload_sha256"], now),
    )
    return evidence_id


def _relationship(
    conn: Any,
    *,
    subject_id: str,
    predicate: str,
    object_id: str,
    evidence_id: str,
    now: str,
    valid_from: str | None = None,
    valid_to: str | None = None,
    confidence: float = 1.0,
    derivation_type: str = "SOURCE_FACT",
) -> str:
    relationship_id = _relationship_id(subject_id, predicate, object_id, evidence_id)
    conn.execute(
        "INSERT INTO entity_relationships (relationship_id, subject_entity_id, predicate, object_entity_id, "
        "relationship_type, evidence_id, valid_from, valid_to, confidence, derivation_type, "
        "derivation_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(relationship_id) DO UPDATE SET valid_from = excluded.valid_from, "
        "valid_to = excluded.valid_to, confidence = excluded.confidence, updated_at = excluded.updated_at",
        (relationship_id, subject_id, predicate, object_id, predicate, evidence_id, valid_from, valid_to,
         confidence, derivation_type, f"backfill-{BACKFILL_VERSION}", now, now),
    )
    return relationship_id


def _queue(conn: Any, object_type: str, object_id: str, operation: str, now: str) -> None:
    """Replace a pending equivalent operation; repeated backfills stay bounded."""
    conn.execute(
        "DELETE FROM graph_projection_queue WHERE object_type = ? AND object_id = ? "
        "AND operation = ? AND processed_at IS NULL",
        (object_type, object_id, operation),
    )
    conn.execute(
        "INSERT INTO graph_projection_queue (object_type, object_id, operation, created_at) "
        "VALUES (?, ?, ?, ?)",
        (object_type, object_id, operation, now),
    )


def seed_existing_evidence(conn: Any) -> dict[str, int]:
    """Backfill deterministic existing evidence without fetching or name guessing.

    Unmatched procurement supplier names are intentionally excluded: a name is
    useful lead data but is not enough to create a provider identity.  A match
    in the existing deterministic `supplier_aliases` registry is required.
    """
    now = _now()
    counts = {"entities": 0, "evidence": 0, "relationships": 0, "queued": 0}
    queued: set[tuple[str, str, str]] = set()

    def queue_once(object_type: str, object_id: str, operation: str) -> None:
        key = (object_type, object_id, operation)
        if key not in queued:
            _queue(conn, *key, now)
            queued.add(key)
            counts["queued"] += 1

    for row in conn.execute("SELECT ons_code, name FROM authorities"):
        record = dict(row)
        entity_id = _stable_id("authority", record["ons_code"])
        _upsert_entity(conn, entity_id, "LOCAL_AUTHORITY", record["name"], now)
        _identifier(conn, entity_id, "ons_code", record["ons_code"], now)
        counts["entities"] += 1
        queue_once("entity", entity_id, "UPSERT_ENTITY")

    for row in conn.execute("SELECT provider_key, canonical_name FROM providers"):
        record = dict(row)
        entity_id = _stable_id("provider", record["provider_key"])
        _upsert_entity(conn, entity_id, "PROVIDER", record["canonical_name"], now)
        _identifier(conn, entity_id, "sectortrace_provider_key", record["provider_key"], now)
        counts["entities"] += 1
        queue_once("entity", entity_id, "UPSERT_ENTITY")

    contract_rows = conn.execute(
        "SELECT c.notice_id, c.supplier_id, c.buyer_ons_code, c.date_start, c.date_end, "
        "c.source_system, c.source_url, c.retrieved_at, c.http_status, c.payload_sha256, "
        "sa.supplier_key, COALESCE(p.canonical_name, sa.canonical_name) AS provider_name "
        "FROM contracts c JOIN authorities a ON a.ons_code = c.buyer_ons_code "
        "JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw "
        "LEFT JOIN providers p ON p.provider_key = sa.supplier_key "
        "WHERE c.buyer_ons_code IS NOT NULL AND sa.supplier_key IS NOT NULL "
        "AND c.payload_sha256 IS NOT NULL"
    ).fetchall()
    for row in contract_rows:
        record = dict(row)
        authority_id = _stable_id("authority", record["buyer_ons_code"])
        provider_id = _stable_id("provider", record["supplier_key"])
        _upsert_entity(conn, provider_id, "PROVIDER", record["provider_name"], now)
        evidence_id = _evidence(conn, record, now)
        relationship_id = _relationship(
            conn, subject_id=authority_id, predicate="AWARDED_TO", object_id=provider_id,
            evidence_id=evidence_id, valid_from=record["date_start"], valid_to=record["date_end"], now=now)
        counts["entities"] += 1
        counts["evidence"] += 1
        counts["relationships"] += 1
        queue_once("entity", provider_id, "UPSERT_ENTITY")
        queue_once("evidence", evidence_id, "UPSERT_EVIDENCE")
        queue_once("relationship", relationship_id, "UPSERT_RELATIONSHIP")

    company_rows = conn.execute(
        "SELECT c.provider_key, c.company_number, c.company_name, c.match_basis, c.source_system, c.source_url, "
        "c.retrieved_at, c.http_status, c.payload_sha256 FROM companies c "
        "JOIN providers p ON p.provider_key = c.provider_key "
        "WHERE c.company_number IS NOT NULL AND c.payload_sha256 IS NOT NULL"
    ).fetchall()
    for row in company_rows:
        record = dict(row)
        provider_id = _stable_id("provider", record["provider_key"])
        company_id = _stable_id("company", record["company_number"])
        _upsert_entity(conn, company_id, "LEGAL_ENTITY", record["company_name"], now)
        _identifier(conn, company_id, "companies_house_number", record["company_number"], now)
        evidence_id = _evidence(conn, record, now)
        uncertain = record["match_basis"] == "name_only_unconfirmed"
        relationship_id = _relationship(
            conn, subject_id=provider_id, predicate="REGISTERED_AS", object_id=company_id,
            evidence_id=evidence_id, confidence=0.5 if uncertain else 1.0,
            derivation_type="DERIVED_RELATIONSHIP" if uncertain else "SOURCE_FACT", now=now)
        counts["entities"] += 1
        counts["evidence"] += 1
        counts["relationships"] += 1
        queue_once("entity", company_id, "UPSERT_ENTITY")
        queue_once("evidence", evidence_id, "UPSERT_EVIDENCE")
        queue_once("relationship", relationship_id, "UPSERT_RELATIONSHIP")

    conn.commit()
    return counts
