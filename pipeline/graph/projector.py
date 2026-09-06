"""Replayable warehouse-to-Neo4j projection and transactional queue handling."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from pipeline.graph.store import PROJECTOR_VERSION, GraphStore

log = structlog.get_logger()

SCHEMA_VERSION = "0050"

_PROJECTED_COLUMNS = {
    "entities": ("entity_id", "canonical_name", "entity_type", "status"),
    "evidence_records": ("evidence_id", "source_system", "source_url",
                          "retrieved_at", "payload_sha256", "raw_object_path"),
    "graph_claims": ("claim_id", "predicate", "claim_text", "extraction_method",
                      "confidence", "review_status", "evidence_id",
                      "subject_entity_id"),
    "entity_relationships": ("relationship_id", "subject_entity_id",
                              "object_entity_id", "relationship_type", "predicate",
                              "evidence_id", "claim_id", "valid_from", "valid_to",
                              "confidence", "derivation_type", "derivation_version"),
}

# The queue operation a rebuild row falls back to when its own write fails
# outright (performance.md:582). Deliberately the same (object_type,
# operation) vocabulary `_sync_item` already reads: a rebuild-time failure
# and a delta-sync failure are the same fact — "this row is not projected
# yet" — and must retry through the one path, not a second one invented for
# rebuild.
_TABLE_QUEUE_OPERATION = {
    "entities": ("entity", "UPSERT_ENTITY"),
    "evidence_records": ("evidence", "UPSERT_EVIDENCE"),
    "graph_claims": ("claim", "UPSERT_CLAIM"),
    "entity_relationships": ("relationship", "UPSERT_RELATIONSHIP"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lag_seconds(created_at: str | None, now: str) -> float | None:
    """Time between a queued row's own `created_at` and this projection.

    `created_at` is written by whatever enqueued the row (`backfill.py`'s
    `_queue`, or a future writer) with this module's own `_now()`, so it is
    always an ISO-8601 UTC timestamp -- never a guess at a source commit time
    this module was not there to observe. Returns None rather than raising on
    a value that is missing or does not parse, because a benchmarking read
    must never be the reason a queued change fails to project.
    """
    if not created_at:
        return None
    try:
        return (datetime.fromisoformat(now) - datetime.fromisoformat(created_at)).total_seconds()
    except (TypeError, ValueError):
        return None


class GraphProjector:
    """Projects only warehouse records; ingestion modules never dual-write."""

    def __init__(self, conn: Any, store: GraphStore, batch_size: int = 500):
        self.conn = conn
        self.store = store
        self.batch_size = batch_size
        # Set for real at the top of each `rebuild()`; initialised here only
        # so `_write_rows` has something to increment if it is ever reached
        # outside a rebuild.
        self._run_row_failures = 0

    def rebuild(self, clear: bool = False) -> dict[str, int | str]:
        run_id = str(uuid.uuid4())
        started_at = _now()
        clock = time.monotonic()
        # Reset per-run: a bad row bisected down to single-row granularity is
        # queued rather than raised (see `_write_rows`), so the only place
        # left to surface "how many rows this rebuild could not project" is
        # this counter, read back into `graph_projection_runs.error_count`.
        self._run_row_failures = 0
        self.conn.execute(
            "INSERT INTO graph_projection_runs (run_id, started_at, status, schema_version, "
            "projector_version, warehouse_snapshot) VALUES (%s, %s, 'running', %s, %s, %s)",
            (run_id, started_at, SCHEMA_VERSION, PROJECTOR_VERSION, started_at),
        )
        self.conn.commit()
        counts = {"entities": 0, "relationships": 0, "claims": 0, "evidence": 0}
        try:
            self.store.ensure_schema()
            if clear:
                self.store.clear_managed_data()
            counts["entities"] = self._project_table("entities", self.store.upsert_entities, run_id)
            counts["evidence"] = self._project_table(
                "evidence_records", self.store.upsert_evidence, run_id)
            counts["claims"] = self._project_table("graph_claims", self.store.upsert_claims, run_id)
            counts["relationships"] = self._project_table(
                "entity_relationships", self.store.upsert_relationships, run_id)
        except Exception as exc:
            # Reserved for a systemic failure -- schema setup, `clear`, or a
            # warehouse read going wrong -- none of which subdivision can
            # isolate a row from, unlike a single bad row's write (below).
            log.error("graph.rebuild_failed", run_id=run_id, error=str(exc))
            self.conn.execute(
                "UPDATE graph_projection_runs SET completed_at = %s, status = 'failed', "
                "error_count = 1, error_detail = %s WHERE run_id = %s",
                (_now(), str(exc), run_id),
            )
            self.conn.commit()
            raise
        duration_seconds = time.monotonic() - clock
        rows_total = sum(counts.values())
        log.info(
            "graph.rebuild_completed", run_id=run_id, duration_seconds=round(duration_seconds, 3),
            rows_total=rows_total,
            rows_per_second=round(rows_total / duration_seconds, 2) if duration_seconds > 0 else None,
            row_failures=self._run_row_failures, **counts,
        )
        self.conn.execute(
            "UPDATE graph_projection_runs SET completed_at = %s, status = 'completed', "
            "entity_count = %s, relationship_count = %s, claim_count = %s, error_count = %s "
            "WHERE run_id = %s",
            (_now(), counts["entities"], counts["relationships"], counts["claims"],
             self._run_row_failures, run_id),
        )
        self.conn.commit()
        return {"run_id": run_id, **counts, "row_failures": self._run_row_failures}

    def sync_delta(self, limit: int = 500) -> dict[str, int]:
        # No batch subdivision here (performance.md:582's other half): the
        # queue already processes one row per `_sync_item` call, so a bad row
        # was always isolated from its neighbours by construction. Subdivision
        # is `rebuild()`'s problem because `_project_table` reads a whole page
        # at a time and calls the store once per page.
        queue_depth = self.status()["pending"]
        rows = self.conn.execute(
            "SELECT * FROM graph_projection_queue WHERE processed_at IS NULL ORDER BY id LIMIT %s",
            (max(1, limit),),
        ).fetchall()
        processed = 0
        failed = 0
        lag_seconds: list[float] = []
        now = _now()
        for row in rows:
            item = dict(row)
            lag = _lag_seconds(item.get("created_at"), now)
            if lag is not None:
                lag_seconds.append(lag)
            try:
                self._sync_item(item)
                self.conn.execute(
                    "UPDATE graph_projection_queue SET processed_at = %s, attempt_count = attempt_count + 1, "
                    "last_error = NULL WHERE id = %s",
                    (_now(), item["id"]),
                )
                self.conn.commit()
                processed += 1
            except Exception as exc:
                self.conn.execute(
                    "UPDATE graph_projection_queue SET attempt_count = attempt_count + 1, last_error = %s "
                    "WHERE id = %s",
                    (str(exc), item["id"]),
                )
                self.conn.commit()
                failed += 1
        log.info(
            "graph.sync_delta_completed", queue_depth_before=queue_depth, batch_size=len(rows),
            processed=processed, failed=failed,
            lag_seconds_max=round(max(lag_seconds), 3) if lag_seconds else None,
            lag_seconds_avg=round(sum(lag_seconds) / len(lag_seconds), 3) if lag_seconds else None,
        )
        return {"processed": processed, "failed": failed}

    def status(self) -> dict[str, int]:
        pending = self.conn.execute(
            "SELECT COUNT(*) AS n FROM graph_projection_queue WHERE processed_at IS NULL").fetchone()["n"]
        return {"pending": int(pending)}

    def _project_table(self, table: str, upsert: Any, run_id: str) -> int:
        total = 0
        key = _PROJECTED_COLUMNS[table][0]
        columns = ", ".join(_PROJECTED_COLUMNS[table])
        last_key = None
        while True:
            if last_key is None:
                sql = (f"SELECT {columns} FROM {table} "
                       f"ORDER BY {key} LIMIT %s")
                params = (self.batch_size,)
            else:
                sql = (f"SELECT {columns} FROM {table} WHERE {key} > %s "
                       f"ORDER BY {key} LIMIT %s")
                params = (last_key, self.batch_size)
            rows = self.conn.execute(sql, params).fetchall()
            if not rows:
                return total
            total += self._write_rows(table, upsert, [dict(row) for row in rows], run_id)
            last_key = rows[-1][key]

    def _write_rows(self, table: str, upsert: Any, rows: list[dict], run_id: str) -> int:
        """Write one page, subdividing on failure (performance.md:582).

        A page write is one call into `store.py`, which itself may issue
        several Neo4j statements (`upsert_relationships` groups by type,
        `upsert_claims` writes the node then two edge passes) -- so a failure
        partway through can leave part of the page already committed. Bisecting
        blindly by position rather than trying to know which half landed is
        still correct: every write is a Neo4j `MERGE`, so replaying a half that
        already succeeded is a no-op, not a duplicate.

        Recurses to single-row batches before giving up on a row, so one
        malformed row (a bad relationship type, an entity the row references
        that was deleted mid-rebuild) never takes its neighbours down with it.
        A row still failing alone is not dropped: settled decision 1 says
        nothing here gets guessed at or silently skipped, so it is queued back
        onto `graph_projection_queue` with the error attached -- the same
        table and the same retry path `graph sync` already gives a delta
        change that failed once -- and counted in `_run_row_failures` for
        `graph_projection_runs.error_count`.
        """
        if not rows:
            return 0
        try:
            return upsert(rows)
        except Exception as exc:
            if len(rows) == 1:
                row = rows[0]
                key = _PROJECTED_COLUMNS[table][0]
                object_id = row.get(key)
                object_type, operation = _TABLE_QUEUE_OPERATION[table]
                log.warning(
                    "graph.rebuild_row_failed", run_id=run_id, table=table,
                    object_id=object_id, operation=operation, error=str(exc),
                )
                self._queue_retry(object_type, object_id, operation, str(exc))
                self._run_row_failures += 1
                return 0
            midpoint = len(rows) // 2
            return (self._write_rows(table, upsert, rows[:midpoint], run_id)
                    + self._write_rows(table, upsert, rows[midpoint:], run_id))

    def _queue_retry(self, object_type: str, object_id: Any, operation: str, error: str) -> None:
        """Requeue a rebuild row that could not be written, for `graph sync`.

        Mirrors `backfill.py`'s `_queue`: delete any existing pending
        equivalent first. `graph_projection_queue`'s UNIQUE constraint
        includes `processed_at`, and PostgreSQL does not treat two NULLs as
        equal for uniqueness, so an ON CONFLICT upsert would silently pile up
        one row per rebuild for the same object instead of updating one.
        """
        now = _now()
        self.conn.execute(
            "DELETE FROM graph_projection_queue WHERE object_type = %s AND object_id = %s "
            "AND operation = %s AND processed_at IS NULL",
            (object_type, object_id, operation),
        )
        self.conn.execute(
            "INSERT INTO graph_projection_queue (object_type, object_id, operation, created_at, "
            "attempt_count, last_error) VALUES (%s, %s, %s, %s, 1, %s)",
            (object_type, object_id, operation, now, error),
        )
        self.conn.commit()

    def _sync_item(self, item: dict) -> None:
        operation = item["operation"]
        object_type = item["object_type"]
        object_id = item["object_id"]
        if operation == "DELETE_ENTITY":
            self.store.delete_entity(object_id)
            return
        if operation == "DELETE_RELATIONSHIP":
            self.store.delete_relationship(object_id)
            return
        mapping = {
            "UPSERT_ENTITY": ("entities", "entity_id", self.store.upsert_entities),
            "UPSERT_EVIDENCE": ("evidence_records", "evidence_id", self.store.upsert_evidence),
            "UPSERT_CLAIM": ("graph_claims", "claim_id", self.store.upsert_claims),
            "UPSERT_RELATIONSHIP": ("entity_relationships", "relationship_id",
                                    self.store.upsert_relationships),
        }
        try:
            table, key, upsert = mapping[operation]
        except KeyError as exc:
            raise ValueError(f"Unknown graph projection operation {operation!r} for {object_type!r}.") from exc
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key} = %s", (object_id,)).fetchone()
        if row is None:
            raise ValueError(f"Queued {operation} refers to absent {table} record {object_id!r}.")
        upsert([dict(row)])
