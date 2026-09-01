"""Database-backed executor for admin analysis runs.

The worker is intentionally a separate process from the web server. It polls
the relational warehouse, claims one queued run, and writes progress there so
the admin page can be closed, reopened, or served by another process without
losing the run state.
"""
from __future__ import annotations

import json
import time
import uuid
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pipeline import db
from pipeline.analysis import domains
from pipeline.analysis.budget import AnalysisCancelled
from pipeline.analysis.narrative import discover_themes
from pipeline.analysis.operations import utcnow
from pipeline.analysis.store import record_theme


class AnalysisWorker:
    """Claim and execute queued analysis runs one at a time."""

    def __init__(self, settings, *, poll_seconds: float = 5.0, batch_size: int = 100,
                 worker_id: str | None = None):
        self.settings = settings
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.batch_size = max(1, int(batch_size))
        self.worker_id = worker_id or f"analysis-worker-{uuid.uuid4()}"

    def run_forever(self) -> None:
        """Poll until interrupted, allowing the container to restart safely."""
        while True:
            self._heartbeat("polling")
            if self.run_once() is None:
                time.sleep(self.poll_seconds)

    def run_once(self) -> dict[str, Any] | None:
        """Claim at most one queued run and return its final summary."""
        self._heartbeat("polling")
        run_id = self._claim()
        if run_id is None:
            self._heartbeat("idle")
            return None
        self._heartbeat("running")
        try:
            result = self._execute(run_id)
            self._heartbeat("idle")
            return result
        except Exception as exc:  # worker must leave a durable failure, not hang
            self._fail(run_id, exc)
            self._heartbeat("failed")
            return {"run_id": run_id, "status": "failed", "error": str(exc)}

    def _heartbeat(self, status: str) -> None:
        conn = db.get_connection(self.settings)
        try:
            try:
                worker_version = version("sub-misuse-evidence-pipeline")
            except PackageNotFoundError:
                worker_version = "source-checkout"
            now = utcnow()
            conn.execute(
                "INSERT INTO analysis_worker_heartbeats (worker_id, last_seen_at, status, version) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (worker_id) DO UPDATE SET "
                "last_seen_at = excluded.last_seen_at, status = excluded.status, version = excluded.version",
                (self.worker_id, now, status, worker_version))
            conn.commit()
        finally:
            conn.close()

    def _claim(self) -> str | None:
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute(
                "SELECT run_id FROM analysis_runs WHERE status = 'queued' "
                "ORDER BY updated_at, started_at LIMIT 1").fetchone()
            if row is None:
                return None
            run_id = row["run_id"]
            changed = conn.execute(
                "UPDATE analysis_runs SET status = 'running', current_stage = 'starting', "
                "updated_at = ? WHERE run_id = ? AND status = 'queued'",
                (utcnow(), run_id)).rowcount
            if changed != 1:
                conn.rollback()
                return None
            conn.commit()
            return run_id
        finally:
            conn.close()

    def _execute(self, run_id: str) -> dict[str, Any]:
        conn = db.get_connection(self.settings)
        try:
            run = conn.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            requested = json.loads(run["requested_domains_json"] or "[]")
        finally:
            conn.close()

        for domain_id in requested:
            if self._cancelled(run_id):
                return self._finalise_cancelled(run_id)
            self._execute_domain(run_id, domain_id)

        return self._refresh_run(run_id, force_complete=True)

    def _execute_domain(self, run_id: str, domain_id: str) -> None:
        spec = domains.get_domain(domain_id)
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute(
                "SELECT * FROM analysis_domain_runs WHERE run_id = ? AND domain_id = ?",
                (run_id, domain_id)).fetchone()
            if row is None or row["status"] in {"complete", "unavailable"}:
                return
            now = utcnow()
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'running', prerequisite_status = 'checking', "
                "started_at = COALESCE(started_at, ?), error_detail = NULL WHERE run_id = ? AND domain_id = ?",
                (now, run_id, domain_id))
            self._update_run(conn, run_id, current_domain=domain_id, current_stage="preflight")
            missing = self._missing_tables(conn, spec.source_tables)
            if missing:
                self._finish_domain(conn, run_id, domain_id, "unavailable", 0, 0,
                                    prerequisite_status="missing", missing_tables=missing,
                                    error_detail="source prerequisite unavailable")
                conn.commit()
                return
            if spec.analysis_unit == "document_window":
                conn.commit()
                self._execute_narrative(run_id, domain_id, spec)
                return
            self._finish_domain(
                conn, run_id, domain_id, "unavailable", 0, 0,
                prerequisite_status="ready", missing_tables=[],
                error_detail="no structured feature builder is configured for this domain")
            conn.commit()
        finally:
            conn.close()

    def _execute_narrative(self, run_id: str, domain_id: str, spec) -> None:
        conn = db.get_connection(self.settings)
        passages: list[dict[str, Any]] = []
        processed = 0
        try:
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            source_marks = ", ".join("?" for _ in spec.source_tables)
            rows = conn.execute(
                "SELECT de.document_element_id, d.document_id, de.text "
                "FROM document_elements de "
                "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
                "JOIN document_records d ON d.document_id = dv.document_id "
                f"WHERE dv.is_active = 1 AND de.text IS NOT NULL AND TRIM(de.text) <> '' "
                f"AND d.source_table IN ({source_marks}) ORDER BY d.document_id, de.sequence",
                tuple(spec.source_tables)).fetchall()
            for start in range(0, len(rows), self.batch_size):
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                batch = rows[start:start + self.batch_size]
                for row in batch:
                    text = str(row["text"] or "").strip()
                    passages.append({"text": text, "document_id": row["document_id"],
                                     "subject_id": row["document_id"],
                                     "evidence_ref": row["document_element_id"]})
                    conn.execute(
                        "INSERT INTO analysis_windows (window_id, domain_run_id, domain_id, "
                        "source_table, source_record_id, subject_type, subject_id, feature_json, status) "
                        "SELECT ?, domain_run_id, ?, 'document_elements', ?, 'document', ?, ?, 'processed' "
                        "FROM analysis_domain_runs WHERE run_id = ? AND domain_id = ? "
                        "ON CONFLICT (domain_run_id, source_table, source_record_id) DO UPDATE SET "
                        "feature_json = excluded.feature_json, status = excluded.status",
                        (f"window-{uuid.uuid4()}", domain_id, row["document_element_id"],
                         row["document_id"], json.dumps({"text_length": len(text)}), run_id, domain_id))
                processed += len(batch)
                self._update_run(conn, run_id, current_domain=domain_id, current_stage="windowing")
                self._update_domain_progress(conn, run_id, domain_id, processed, 0)
                conn.commit()

            self._update_run(conn, run_id, current_domain=domain_id, current_stage="discovering")
            themes = discover_themes(passages)
            written = 0
            for theme in themes:
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                theme["passages"] = theme.get("passages", [])[:25]
                record_theme(conn, release_id=run["release_id"], domain_id=domain_id, theme=theme)
                written += 1
            self._finish_domain(conn, run_id, domain_id, "complete", processed, written,
                                prerequisite_status="ready", missing_tables=[], error_detail=None)
            conn.commit()
        except AnalysisCancelled:
            conn.rollback()
            self._finalise_cancelled(run_id)
        finally:
            conn.close()

    @staticmethod
    def _missing_tables(conn, tables: tuple[str, ...]) -> list[str]:
        missing = []
        for table in tables:
            try:
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
            except Exception:
                missing.append(table)
        return missing

    @staticmethod
    def _update_run(conn, run_id: str, **values: Any) -> None:
        values["updated_at"] = utcnow()
        clause = ", ".join(f"{key} = ?" for key in values)
        conn.execute(f"UPDATE analysis_runs SET {clause} WHERE run_id = ?",
                     (*values.values(), run_id))

    @staticmethod
    def _update_domain_progress(conn, run_id: str, domain_id: str,
                                processed: int, written: int) -> None:
        conn.execute(
            "UPDATE analysis_domain_runs SET rows_processed = ?, rows_written = ? "
            "WHERE run_id = ? AND domain_id = ?", (processed, written, run_id, domain_id))

    @staticmethod
    def _finish_domain(conn, run_id: str, domain_id: str, status: str,
                       processed: int, written: int, *, prerequisite_status: str,
                       missing_tables: list[str], error_detail: str | None) -> None:
        now = utcnow()
        conn.execute(
            "UPDATE analysis_domain_runs SET status = ?, prerequisite_status = ?, "
            "missing_tables_json = ?, rows_processed = ?, rows_written = ?, "
            "completed_at = ?, error_detail = ? WHERE run_id = ? AND domain_id = ?",
            (status, prerequisite_status, json.dumps(missing_tables), processed, written,
             now, error_detail, run_id, domain_id))

    def _refresh_run(self, self_run_id: str, *, force_complete: bool = False) -> dict[str, Any]:
        from pipeline.web.analysis import run as read_run

        conn = db.get_connection(self.settings)
        try:
            rows = conn.execute(
                "SELECT status FROM analysis_domain_runs WHERE run_id = ?", (self_run_id,)).fetchall()
            statuses = [row["status"] for row in rows]
            if self._cancelled_with_conn(conn, self_run_id):
                status, stage = "cancelled", "cancelled"
            elif any(value == "failed" for value in statuses):
                status, stage = "failed", "failed"
            elif force_complete or statuses and all(value in {"complete", "unavailable"} for value in statuses):
                status, stage = "complete", "complete"
            else:
                status, stage = "running", "processing"
            now = utcnow()
            self._update_run(conn, self_run_id, status=status, current_stage=stage,
                             completed_at=now if status in {"complete", "failed", "cancelled"} else None)
            conn.commit()
            return read_run(conn, self_run_id)
        finally:
            conn.close()

    def _finalise_cancelled(self, run_id: str) -> dict[str, Any]:
        conn = db.get_connection(self.settings)
        try:
            now = utcnow()
            conn.execute(
                "UPDATE analysis_runs SET status = 'cancelled', current_stage = 'cancelled', "
                "completed_at = COALESCE(completed_at, ?), cancelled_at = COALESCE(cancelled_at, ?), "
                "updated_at = ? WHERE run_id = ?", (now, now, now, run_id))
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'cancelled' "
                "WHERE run_id = ? AND status NOT IN ('complete', 'unavailable')", (run_id,))
            conn.commit()
            from pipeline.web.analysis import run as read_run
            return read_run(conn, run_id)
        finally:
            conn.close()

    def _fail(self, run_id: str, exc: Exception) -> None:
        conn = db.get_connection(self.settings)
        try:
            now = utcnow()
            conn.execute(
                "UPDATE analysis_runs SET status = 'failed', current_stage = 'failed', "
                "error_detail = ?, completed_at = ?, updated_at = ? WHERE run_id = ?",
                (f"{type(exc).__name__}: {exc}", now, now, run_id))
            conn.commit()
        finally:
            conn.close()

    def _cancelled(self, run_id: str) -> bool:
        conn = db.get_connection(self.settings)
        try:
            return self._cancelled_with_conn(conn, run_id)
        finally:
            conn.close()

    @staticmethod
    def _cancelled_with_conn(conn, run_id: str) -> bool:
        row = conn.execute("SELECT status FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
        return row is None or row["status"] == "cancelled"
