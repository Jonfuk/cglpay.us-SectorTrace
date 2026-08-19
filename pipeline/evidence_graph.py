"""Resolve derived graph records back to the authoritative evidence trail."""
from __future__ import annotations

from typing import Any


def relationship_provenance(conn: Any, relationship_id: str) -> dict | None:
    """Return a relationship with its claim/evidence/raw-archive identifiers."""
    row = conn.execute(
        "SELECT r.relationship_id, r.predicate, r.derivation_type, r.confidence, "
        "r.claim_id, r.evidence_id, e.source_system, e.source_url, e.retrieved_at, "
        "e.http_status, e.payload_sha256, e.raw_object_path "
        "FROM entity_relationships r LEFT JOIN evidence_records e ON e.evidence_id = r.evidence_id "
        "WHERE r.relationship_id = ?",
        (relationship_id,),
    ).fetchone()
    return dict(row) if row else None


def claim_provenance(conn: Any, claim_id: str) -> dict | None:
    """Return a graph claim with the evidence record that supports it."""
    row = conn.execute(
        "SELECT c.claim_id, c.source_claim_id, c.predicate, c.extraction_method, "
        "c.extractor_name, c.extractor_version, c.confidence, c.review_status, "
        "c.evidence_span, c.evidence_id, e.source_system, e.source_url, e.retrieved_at, "
        "e.payload_sha256, e.raw_object_path "
        "FROM graph_claims c LEFT JOIN evidence_records e ON e.evidence_id = c.evidence_id "
        "WHERE c.claim_id = ?",
        (claim_id,),
    ).fetchone()
    return dict(row) if row else None
