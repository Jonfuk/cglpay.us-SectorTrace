from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from structlog.testing import capture_logs

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


class PartiallyFailingStore(RecordingStore):
    """A store whose `upsert_entities` fails whenever a named entity_id is in
    the batch, standing in for one bad row a real Neo4j write would reject
    (an unsafe label, a constraint violation) while its neighbours are fine.
    """

    def __init__(self, bad_ids):
        super().__init__()
        self.bad_ids = set(bad_ids)
        self.attempted_batch_sizes = []

    def upsert_entities(self, rows):
        self.attempted_batch_sizes.append(len(rows))
        if any(row["entity_id"] in self.bad_ids for row in rows):
            raise RuntimeError("simulated Neo4j write failure")
        return super().upsert_entities(rows)


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


def _insert_entity(conn, entity_id: str) -> None:
    conn.execute("INSERT INTO entities (entity_id, entity_type, canonical_name, "
                 "canonical_name_normalized, status, created_at, updated_at) "
                 "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (entity_id, "PROVIDER", entity_id, entity_id, "active", "now", "now"))


def test_rebuild_subdivides_a_failing_batch_and_isolates_the_bad_row(tmp_path):
    """performance.md:582 -- one bad row must not take its neighbours down.

    Three entities in one page (batch_size=10 keeps them together); the
    middle one always fails. Bisection should still project the other two
    and queue only the bad one, rather than the whole page failing dark.
    """
    conn = _conn(tmp_path)
    for entity_id in ("provider-1", "provider-2", "provider-3"):
        _insert_entity(conn, entity_id)
    conn.commit()
    store = PartiallyFailingStore(bad_ids={"provider-2"})
    result = GraphProjector(conn, store, batch_size=10).rebuild()

    assert result["entities"] == 2
    assert result["row_failures"] == 1
    # Bisection reached single-row granularity for the bad half: the last,
    # smallest attempt against a batch containing provider-2 was size 1.
    assert 1 in store.attempted_batch_sizes

    queued = conn.execute(
        "SELECT object_type, operation, attempt_count, last_error FROM graph_projection_queue "
        "WHERE object_id = 'provider-2'"
    ).fetchone()
    assert queued["object_type"] == "entity"
    assert queued["operation"] == "UPSERT_ENTITY"
    assert queued["attempt_count"] == 1
    assert "simulated Neo4j write failure" in queued["last_error"]
    # The two good rows were never queued for retry -- they do not need one.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM graph_projection_queue WHERE object_id IN ('provider-1', 'provider-3')"
    ).fetchone()["n"] == 0

    run_row = conn.execute(
        "SELECT status, entity_count, error_count FROM graph_projection_runs").fetchone()
    assert run_row["status"] == "completed"
    assert run_row["entity_count"] == 2
    assert run_row["error_count"] == 1
    conn.close()


def test_rebuild_row_failure_is_requeued_not_duplicated_on_a_repeat_run(tmp_path):
    """Mirrors backfill.py's `_queue`: a repeat rebuild against the same
    still-bad row must not pile up a second pending queue entry for it."""
    conn = _conn(tmp_path)
    _insert_entity(conn, "provider-2")
    conn.commit()
    store = PartiallyFailingStore(bad_ids={"provider-2"})
    GraphProjector(conn, store, batch_size=10).rebuild()
    GraphProjector(conn, store, batch_size=10).rebuild()

    rows = conn.execute(
        "SELECT COUNT(*) AS n FROM graph_projection_queue WHERE object_id = 'provider-2' "
        "AND processed_at IS NULL"
    ).fetchone()
    assert rows["n"] == 1
    conn.close()


def test_rebuild_logs_throughput_and_row_failures(tmp_path):
    conn = _conn(tmp_path)
    _insert_entity(conn, "provider-1")
    _insert_entity(conn, "provider-2")
    conn.commit()
    store = PartiallyFailingStore(bad_ids={"provider-2"})
    with capture_logs() as events:
        GraphProjector(conn, store, batch_size=10).rebuild()

    completed = [event for event in events if event["event"] == "graph.rebuild_completed"]
    assert len(completed) == 1
    assert completed[0]["row_failures"] == 1
    assert completed[0]["rows_total"] == 1
    assert completed[0]["duration_seconds"] >= 0

    failures = [event for event in events if event["event"] == "graph.rebuild_row_failed"]
    assert len(failures) == 1
    assert failures[0]["object_id"] == "provider-2"
    assert failures[0]["table"] == "entities"
    conn.close()


def test_sync_delta_logs_queue_depth_and_projection_lag(tmp_path):
    conn = _conn(tmp_path)
    _insert_entity(conn, "provider-1")
    queued_at = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    conn.execute("INSERT INTO graph_projection_queue (object_type, object_id, operation, created_at) "
                 "VALUES ('entity', 'provider-1', 'UPSERT_ENTITY', %s)", (queued_at,))
    conn.commit()
    store = RecordingStore()
    with capture_logs() as events:
        result = GraphProjector(conn, store).sync_delta()

    assert result == {"processed": 1, "failed": 0}
    completed = [event for event in events if event["event"] == "graph.sync_delta_completed"]
    assert len(completed) == 1
    assert completed[0]["queue_depth_before"] == 1
    assert completed[0]["processed"] == 1
    # Real time passed between commit and the moment sync_delta ran, so lag
    # must be a positive number, not the None a missing/unparseable
    # created_at (like the other test's literal 'now') falls back to.
    assert completed[0]["lag_seconds_avg"] > 0
    conn.close()
