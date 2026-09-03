from __future__ import annotations

from pathlib import Path

from pipeline import db
from pipeline.config import Settings
from pipeline.graph.projector import GraphProjector


class RecordingStore:
    def __init__(self):
        self.calls = []

    def ensure_schema(self):
        self.calls.append(("schema", []))

    def clear_managed_data(self):
        self.calls.append(("clear", []))

    def upsert_entities(self, rows):
        self.calls.append(("entities", rows))
        return len(rows)

    def upsert_evidence(self, rows):
        self.calls.append(("evidence", rows))
        return len(rows)

    def upsert_claims(self, rows):
        self.calls.append(("claims", rows))
        return len(rows)

    def upsert_relationships(self, rows):
        self.calls.append(("relationships", rows))
        return len(rows)

    def delete_entity(self, entity_id):
        self.calls.append(("delete_entity", entity_id))

    def delete_relationship(self, relationship_id):
        self.calls.append(("delete_relationship", relationship_id))


def _conn(tmp_path: Path):
    settings = Settings(contact_email="test@example.com", database_path=tmp_path / "warehouse.db",
                        migrations_dir=Path("pipeline/migrations"), _env_file=None)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    return conn


def test_rebuild_projects_only_relational_records(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, "
                 "canonical_name_normalized, status, created_at, updated_at) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 ("provider-1", "PROVIDER", "Example Provider", "example provider", "active", "now", "now"))
    conn.commit()
    store = RecordingStore()
    result = GraphProjector(conn, store, batch_size=10).rebuild(clear=True)
    assert result["entities"] == 1
    assert ("clear", []) in store.calls
    assert store.calls[1][0] == "clear"
    assert store.calls[2][0] == "entities"
    assert conn.execute("SELECT status FROM graph_projection_runs").fetchone().values().__iter__().__next__() == "completed"
    conn.close()


def test_delta_sync_is_retryable_and_marks_a_success(tmp_path):
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, "
                 "canonical_name_normalized, status, created_at, updated_at) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 ("provider-1", "PROVIDER", "Example Provider", "example provider", "active", "now", "now"))
    conn.execute("INSERT INTO graph_projection_queue (object_type, object_id, operation, created_at) "
                 "VALUES ('entity', 'provider-1', 'UPSERT_ENTITY', 'now')")
    conn.commit()
    store = RecordingStore()
    result = GraphProjector(conn, store).sync_delta()
    assert result == {"processed": 1, "failed": 0}
    assert conn.execute("SELECT processed_at, attempt_count FROM graph_projection_queue").fetchone().values().__iter__().__next__()
    assert store.calls[0][0] == "entities"
    assert store.calls[0][1][0]["entity_id"] == "provider-1"
    conn.close()
