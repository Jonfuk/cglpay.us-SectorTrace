from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import db
from pipeline.analytics.graph_builder import GraphTooLargeError, build_commissioner_provider_graph
from pipeline.analytics.networks import (
    commissioner_provider_metrics,
    persist_metrics,
    provider_network_metrics,
)
from pipeline.config import Settings


def _conn(tmp_path: Path):
    settings = Settings(contact_email="test@example.com", database_path=tmp_path / "warehouse.db",
                        migrations_dir=Path("pipeline/migrations"), _env_file=None)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    for entity_id, entity_type, name in [
        ("council-a", "LOCAL_AUTHORITY", "Council A"),
        ("council-b", "LOCAL_AUTHORITY", "Council B"),
        ("council-c", "LOCAL_AUTHORITY", "Council C"),
        ("provider-1", "PROVIDER", "Provider 1"),
        ("provider-2", "PROVIDER", "Provider 2"),
    ]:
        conn.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, "
                     "canonical_name_normalized, status, created_at, updated_at) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (entity_id, entity_type, name, name.lower(), "active", "now", "now"))
    for number, authority, provider in [
        (1, "council-a", "provider-1"), (2, "council-b", "provider-1"),
        (3, "council-c", "provider-2"),
    ]:
        conn.execute(
            "INSERT INTO entity_relationships (relationship_id, subject_entity_id, predicate, "
            "object_entity_id, relationship_type, evidence_id, claim_id, valid_from, valid_to, "
            "confidence, derivation_type, derivation_version, created_at, updated_at) "
            "VALUES (?, ?, 'COMMISSIONS', ?, 'COMMISSIONS', "
            "NULL, NULL, NULL, NULL, 1.0, 'SOURCE_FACT', '1', 'now', 'now')",
            (f"relationship-{number}", authority, provider))
    conn.commit()
    return conn


def test_commissioner_provider_metrics_are_deterministic_and_persisted(tmp_path):
    conn = _conn(tmp_path)
    snapshot = build_commissioner_provider_graph(conn)
    metrics = commissioner_provider_metrics(snapshot)
    reach = {(row["entity_id"], row["metric_name"]): row["metric_value"] for row in metrics}
    assert reach[("provider-1", "observed_counterpart_count")] == 2
    assert reach[("provider-2", "observed_counterpart_count")] == 1
    provider_metrics = provider_network_metrics(snapshot)
    assert {row["entity_id"] for row in provider_metrics} == {"provider-1", "provider-2"}
    assert persist_metrics(conn, metrics, analysis_name="test", graph_snapshot="fixture",
                           parameters=snapshot.parameters) == len(metrics)
    assert conn.execute("SELECT COUNT(*) FROM graph_metrics").fetchone()[0] == len(metrics)
    conn.close()


def test_builder_refuses_an_unbounded_selection(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(GraphTooLargeError, match="max_edges=2"):
        build_commissioner_provider_graph(conn, max_edges=2)
    conn.close()
