from __future__ import annotations

from pathlib import Path

from pipeline import db
from pipeline.analytics.graph_builder import build_commissioner_provider_graph
from pipeline.analytics.networks import provider_network_metrics
from pipeline.config import Settings
from pipeline.graph.backfill import seed_existing_evidence


def _conn(tmp_path: Path):
    settings = Settings(contact_email="test@example.com", database_path=tmp_path / "warehouse.db",
                        migrations_dir=Path("pipeline/migrations"), _env_file=None)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.execute("INSERT INTO providers VALUES ('example-provider', 'Example Provider', 0, NULL)")
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, last_seen_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E00000001', 'Example Council', 'unitary', '2020-01-01', '2020', '2020', "
        "'https://example.test/authority', 'now', 200, 'ons', 'authority-hash')")
    conn.execute("INSERT INTO supplier_aliases VALUES ('Example Provider Ltd', 'example-provider', 'Example Provider')")
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, buyer_ons_code, supplier_name_raw, date_start, "
        "date_end, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('notice-1', 'supplier-1', 'ocid-1', 'E00000001', 'Example Provider Ltd', '2024-01-01', "
        "'2025-01-01', 'https://example.test/contract', 'now', 200, 'fts', 'contract-hash')")
    conn.commit()
    return conn


def test_backfill_seeds_evidence_backed_commissioning_graph_and_queue(tmp_path):
    conn = _conn(tmp_path)
    result = seed_existing_evidence(conn)
    assert result["relationships"] == 1
    assert conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 2
    edge = conn.execute("SELECT predicate, evidence_id, valid_from, valid_to FROM entity_relationships").fetchone()
    assert tuple(edge) == ("AWARDED_TO", "evidence:fts:contract-hash", "2024-01-01", "2025-01-01")
    assert conn.execute("SELECT COUNT(*) FROM graph_projection_queue").fetchone()[0] == result["queued"]
    snapshot = build_commissioner_provider_graph(conn)
    assert snapshot.graph.number_of_edges() == 1
    assert provider_network_metrics(snapshot)[0]["metric_value"] == 0.0
    seed_existing_evidence(conn)
    assert conn.execute("SELECT COUNT(*) FROM entity_relationships").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM graph_projection_queue").fetchone()[0] == result["queued"]
    conn.close()


def test_backfill_keeps_historical_authorities_that_share_a_display_name(tmp_path):
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, last_seen_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E00000002', 'Example Council', 'unitary', '2024-01-01', '2024', '2024', "
        "'https://example.test/authority-new', 'now', 200, 'ons', 'authority-hash-new')")
    conn.commit()
    seed_existing_evidence(conn)
    rows = conn.execute(
        "SELECT entity_id FROM entities WHERE entity_type = 'LOCAL_AUTHORITY' "
        "ORDER BY entity_id").fetchall()
    assert [row[0] for row in rows] == ["authority:E00000001", "authority:E00000002"]
    conn.close()


def test_empty_provider_analysis_is_a_valid_zero_result(tmp_path):
    conn = _conn(tmp_path)
    snapshot = build_commissioner_provider_graph(conn)
    assert provider_network_metrics(snapshot) == []
    conn.close()
