"""Register legacy document rows only when their complete provenance survives."""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.archive import get_archive
from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference
from pipeline.documents.service import DocumentService


@dataclass(frozen=True)
class LegacySource:
    name: str
    query: str


# These are promoted document tables with their own direct document-fetch
# provenance. Candidates are deliberately excluded: their hash belongs to a
# listing/search page, not necessarily to the document URL they mention.
LEGACY_SOURCES = {
    "committee_papers": LegacySource(
        "committee_papers",
        "SELECT source_system, document_url AS source_url, retrieved_at, http_status, payload_sha256, "
        "archived_path AS raw_object_path, report_title AS title, 'committee_papers' AS source_table, "
        "authority_ons_code || '|' || document_url AS source_key "
        "FROM committee_papers WHERE archived_path IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM evidence_records e WHERE e.source_table='committee_papers' "
        "AND e.source_key=(authority_ons_code || '|' || document_url)) ORDER BY retrieved_at DESC",
    ),
    "cdp_documents": LegacySource(
        "cdp_documents",
        "SELECT source_system, document_url AS source_url, retrieved_at, http_status, payload_sha256, "
        "archived_path AS raw_object_path, title, 'cdp_documents' AS source_table, "
        "authority_ons_code || '|' || document_url AS source_key "
        "FROM cdp_documents WHERE archived_path IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM evidence_records e WHERE e.source_table='cdp_documents' "
        "AND e.source_key=(authority_ons_code || '|' || document_url)) ORDER BY retrieved_at DESC",
    ),
    "annual_reports": LegacySource(
        "annual_reports",
        "SELECT source_system, document_url AS source_url, retrieved_at, http_status, payload_sha256, "
        "archived_path AS raw_object_path, NULL AS title, 'provider_annual_reports' AS source_table, "
        "provider_key || '|' || financial_year_end AS source_key "
        "FROM provider_annual_reports WHERE archived_path IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM evidence_records e WHERE e.source_table='provider_annual_reports' "
        "AND e.source_key=(provider_key || '|' || financial_year_end)) ORDER BY retrieved_at DESC",
    ),
}


def sources() -> tuple[str, ...]:
    return tuple(LEGACY_SOURCES)


def register_existing(conn, settings, source: str, limit: int) -> dict:
    """Bridge a bounded, verified set of legacy rows into document states."""
    if source not in LEGACY_SOURCES:
        raise ValueError(f"Unknown legacy source {source!r}; choose one of: {', '.join(sources())}")
    if limit < 1:
        raise ValueError("limit must be at least 1")
    rows = conn.execute(LEGACY_SOURCES[source].query + " LIMIT ?", (limit,)).fetchall()
    archive = get_archive(settings)
    service = DocumentService(conn, settings)
    result = {
        "source": source,
        "candidates": len(rows),
        "registered": 0,
        "missing_raw": 0,
        "source_systems": [],
    }
    for row in rows:
        raw_object = archive.lookup(row["source_system"], row["payload_sha256"])
        if raw_object is None or raw_object.logical_path != row["raw_object_path"]:
            result["missing_raw"] += 1
            continue
        # read() proves the archive still matches the SHA-256 encoded in the
        # legacy provenance row before any canonical record is created.
        body = archive.read(row["raw_object_path"])
        evidence_id = repository.stable_id(
            "evidence", f"{row['source_system']}|{row['source_url']}|{row['payload_sha256']}")
        service.register(EvidenceReference(
            evidence_id=evidence_id, source_system=row["source_system"], source_url=row["source_url"],
            retrieved_at=row["retrieved_at"], http_status=row["http_status"],
            payload_sha256=row["payload_sha256"], raw_object_path=row["raw_object_path"],
            content_length=len(body), source_table=row["source_table"], source_key=row["source_key"],
        ))
        result["registered"] += 1
        if row["source_system"] not in result["source_systems"]:
            result["source_systems"].append(row["source_system"])
    result["source_systems"].sort()
    return result
