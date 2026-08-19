from __future__ import annotations

from pathlib import Path

from pipeline import db
from pipeline.config import Settings
from pipeline.evidence_graph import claim_provenance, relationship_provenance


def test_provenance_resolves_to_immutable_raw_archive_metadata(tmp_path):
    settings = Settings(contact_email="test@example.com", database_path=tmp_path / "warehouse.db",
                        migrations_dir=Path("pipeline/migrations"), _env_file=None)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.execute("INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)",
                 ("provider-1", "PROVIDER", "Provider", "provider", "active", "now", "now"))
    conn.execute("INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?)",
                 ("service-1", "SERVICE", "Service", "service", "active", "now", "now"))
    conn.execute("INSERT INTO evidence_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 ("evidence-1", "fixture", "https://example.test/source", "now", 200, "abc123",
                  "data/raw/fixture/abc123.json", "application/json", 10, "now"))
    conn.execute(
        "INSERT INTO graph_claims (claim_id, predicate, object_literal, evidence_id, extraction_method, "
        "review_status, created_at) VALUES ('claim-1', 'OPERATED_BY', 'true', 'evidence-1', 'parser', 'draft', 'now')")
    conn.execute(
        "INSERT INTO entity_relationships VALUES ('relationship-1', 'provider-1', 'OPERATES', 'service-1', "
        "'OPERATES', 'evidence-1', 'claim-1', NULL, NULL, 1.0, 'SOURCE_FACT', '1', 'now', 'now')")
    conn.commit()
    provenance = relationship_provenance(conn, "relationship-1")
    assert provenance["payload_sha256"] == "abc123"
    assert provenance["raw_object_path"] == "data/raw/fixture/abc123.json"
    assert claim_provenance(conn, "claim-1")["source_url"] == "https://example.test/source"
    conn.close()
