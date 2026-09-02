"""PostgreSQL-backed job queue primitives for the separate worker process."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class WorkerQueue:
    """Durable enqueue/claim/checkpoint operations.

    PostgreSQL claims use ``FOR UPDATE SKIP LOCKED`` so multiple worker
    processes can safely share the queue. SQLite remains usable for local
    development and uses its existing single-writer discipline.
    """

    def __init__(self, conn, *, lease_seconds: int = 900,
                 event_limit: int = 4000):
        self.conn = conn
        self.lease_seconds = lease_seconds
        self.event_limit = event_limit
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS worker_jobs ("
            "job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, arguments_json TEXT NOT NULL, "
            "state TEXT NOT NULL, checkpoint_json TEXT NOT NULL DEFAULT '{}', "
            "lease_until TEXT, attempt_count INTEGER NOT NULL DEFAULT 0, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS worker_job_events ("
            "job_id TEXT NOT NULL, sequence_no INTEGER NOT NULL, level TEXT NOT NULL, "
            "message TEXT NOT NULL, created_at TEXT NOT NULL, "
            "PRIMARY KEY(job_id, sequence_no))"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS warehouse_data_version ("
            "version INTEGER NOT NULL, updated_at TEXT NOT NULL)"
        )
        self.conn.execute(
            "INSERT INTO warehouse_data_version(version, updated_at) "
            "SELECT 0, ? WHERE NOT EXISTS (SELECT 1 FROM warehouse_data_version)", (_now(),)
        )
        self.conn.commit()

    def enqueue(self, kind: str, arguments: dict[str, Any], *,
                job_id: str | None = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            "INSERT INTO worker_jobs(job_id, kind, arguments_json, state, created_at, updated_at) "
            "VALUES (?, ?, ?, 'queued', ?, ?)",
            (job_id, kind, json.dumps(arguments, sort_keys=True, default=str), now, now))
        self.conn.commit()
        return job_id

    def claim(self) -> dict[str, Any] | None:
        now = _now()
        lease = (datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds)).isoformat(timespec="seconds")
        if db.backend_of(self.conn) == "postgres":
            row = self.conn.execute(
                "SELECT job_id, kind, arguments_json, checkpoint_json, attempt_count "
                "FROM worker_jobs WHERE state = 'queued' OR "
                "(state = 'running' AND lease_until < ?) "
                "ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED", (now,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT job_id, kind, arguments_json, checkpoint_json, attempt_count "
                "FROM worker_jobs WHERE state = 'queued' OR "
                "(state = 'running' AND lease_until < ?) "
                "ORDER BY created_at, job_id LIMIT 1", (now,)
            ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE worker_jobs SET state = 'running', lease_until = ?, "
            "attempt_count = attempt_count + 1, updated_at = ? WHERE job_id = ?",
            (lease, now, row["job_id"]))
        self.conn.commit()
        return {"job_id": row["job_id"], "kind": row["kind"],
                "arguments": json.loads(row["arguments_json"]),
                "checkpoint": json.loads(row["checkpoint_json"] or "{}"),
                "attempt_count": row["attempt_count"] + 1,
                "lease_until": lease}

    def checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE worker_jobs SET checkpoint_json = ?, updated_at = ? WHERE job_id = ?",
            (json.dumps(checkpoint, sort_keys=True, default=str), _now(), job_id))
        self.conn.commit()

    def finish(self, job_id: str, *, success: bool, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE worker_jobs SET state = ?, lease_until = NULL, updated_at = ? "
            "WHERE job_id = ?", ("finished" if success else "failed", _now(), job_id))
        if error:
            self.event(job_id, "error", error)
        self.conn.commit()
        if success:
            self.conn.execute(
                "UPDATE warehouse_data_version SET version = version + 1, updated_at = ?",
                (_now(),))
            self.conn.commit()

    def event(self, job_id: str, level: str, message: str) -> None:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS n FROM worker_job_events "
            "WHERE job_id = ?", (job_id,)).fetchone()
        self.conn.execute(
            "INSERT INTO worker_job_events(job_id, sequence_no, level, message, created_at) "
            "VALUES (?, ?, ?, ?, ?)", (job_id, row["n"], level, message[:4000], _now()))
        self.conn.execute(
            "DELETE FROM worker_job_events WHERE job_id = ? AND sequence_no <= "
            "(SELECT COALESCE(MAX(sequence_no), 0) - ? FROM worker_job_events WHERE job_id = ?)",
            (job_id, self.event_limit, job_id))
        self.conn.commit()

    def data_version(self) -> int:
        return int(self.conn.execute(
            "SELECT version FROM warehouse_data_version").fetchone()["version"])

