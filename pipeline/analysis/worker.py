"""Database-backed executor for admin analysis runs.

The worker is intentionally a separate process from the web server. It polls
the relational warehouse, claims one queued run, and writes progress there so
the admin page can be closed, reopened, or served by another process without
losing the run state.
"""
from __future__ import annotations

import json
import structlog
import threading
import time
import uuid
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from pipeline import db
from pipeline.analysis import domains
from pipeline.analysis.budget import AnalysisCancelled, CallBudget, CostCeilingExceeded
from pipeline.analysis.graph import project_release, signal_store_from_settings
from pipeline.analysis.linking import link_signals, save_link
from pipeline.analysis.models import AnalysisModelClient, AnalysisModelUnavailable
from pipeline.analysis.narrative import (
    candidate_from_payload,
    candidate_to_signal,
    discover_themes,
    extraction_prompt,
)
from pipeline.analysis.operations import (
    HealthSnapshot,
    detect_drift,
    save_proposal,
    save_snapshot,
    utcnow,
)
from pipeline.analysis.prevalence import diagnostics, save_diagnostics
from pipeline.analysis.releases import load_release
from pipeline.analysis.store import record_theme, record_topic, save_structured_signal
from pipeline.analysis.structured import (
    categorical_signal,
    categorical_transitions,
    comparisons_for_domain,
    observations_for_domain,
    structured_signal,
)


log = structlog.get_logger()


class AnalysisWorker:
    """Claim and execute queued analysis runs one at a time."""

    def __init__(self, settings, *, poll_seconds: float = 5.0, batch_size: int = 100,
                 worker_id: str | None = None, model_client_factory=None):
        self.settings = settings
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.batch_size = max(1, int(batch_size))
        self.worker_id = worker_id or f"analysis-worker-{uuid.uuid4()}"
        self.model_client_factory = model_client_factory or AnalysisModelClient

    def run_forever(self) -> None:
        """Poll until interrupted, allowing the container to restart safely."""
        while True:
            self._heartbeat("polling")
            if self.run_once() is None:
                self._process_graph_queue()
                time.sleep(self.poll_seconds)

    def run_once(self) -> dict[str, Any] | None:
        """Claim at most one queued run and return its final summary."""
        self._heartbeat("polling")
        run_id = self._claim()
        if run_id is None:
            self._heartbeat("idle")
            return None
        self._heartbeat("running")
        heartbeat_stop = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._run_heartbeat_loop,
            args=(heartbeat_stop,),
            name=f"{self.worker_id}-heartbeat",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            result = self._execute(run_id)
        except Exception as exc:  # worker must leave a durable failure, not hang
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=2)
            log.exception("analysis_run_failed", run_id=run_id,
                          error_type=type(exc).__name__, error=str(exc))
            self._fail(run_id, exc)
            self._heartbeat("failed")
            return {"run_id": run_id, "status": "failed", "error": str(exc)}
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2)
        self._heartbeat("idle")
        return result

    def _run_heartbeat_loop(self, stop: threading.Event) -> None:
        """Keep liveness visible while a run is CPU-bound between batches."""
        interval = max(0.5, min(self.poll_seconds, 5.0))
        while not stop.wait(interval):
            try:
                self._heartbeat("running")
            except Exception as exc:
                log.exception("analysis_heartbeat_failed",
                              worker_id=self.worker_id, error=str(exc))

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

    def _process_graph_queue(self) -> None:
        """Project one queued release when the deployment explicitly enables Neo4j."""
        conn = db.get_connection(self.settings)
        store = None
        try:
            queue = conn.execute(
                "SELECT release_id FROM signal_graph_projection_queue WHERE processed_at IS NULL "
                "ORDER BY created_at LIMIT 1").fetchone()
            if queue is None:
                return
            try:
                store = signal_store_from_settings(self.settings)
            except Exception:
                return
            self._heartbeat("projecting")
            release_id = queue["release_id"]
            project_release(conn, store, release_id)
            conn.execute(
                "UPDATE signal_graph_projection_queue SET processed_at = ?, attempt_count = attempt_count + 1, "
                "last_error = NULL WHERE release_id = ? AND processed_at IS NULL",
                (utcnow(), release_id))
            conn.commit()
        except Exception as exc:
            if queue is not None:
                conn.execute(
                    "UPDATE signal_graph_projection_queue SET attempt_count = attempt_count + 1, last_error = ? "
                    "WHERE release_id = ? AND processed_at IS NULL",
                    (str(exc), queue["release_id"]))
                conn.commit()
        finally:
            if store is not None:
                store.driver.close()
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
            self._budget = CallBudget(ceiling_micros=int(run["cost_ceiling_micros"] or 0))
            self._current_run_id = run_id
        finally:
            conn.close()

        for domain_id in requested:
            if self._cancelled(run_id):
                return self._finalise_cancelled(run_id)
            self._execute_domain(run_id, domain_id)

        self._link_run(run_id)
        self._record_health(run_id, requested)

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
            conn.commit()
            self._execute_structured(run_id, domain_id, spec)
        finally:
            conn.close()

    def _execute_structured(self, run_id: str, domain_id: str, spec) -> None:
        """Compute exact comparisons from the source tables named by a domain.

        This path never asks a model to calculate a number.  It reads the
        canonical source rows, retains both row references, and makes the
        resulting signal idempotent so a cancelled run can resume safely.
        """
        conn = db.get_connection(self.settings)
        try:
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            self._update_run(conn, run_id, current_domain=domain_id, current_stage="computing")
            conn.commit()
            self._heartbeat("running")
            observations = observations_for_domain(conn, spec.source_tables)
            self._heartbeat("running")
            comparisons = comparisons_for_domain(observations)
            self._heartbeat("running")
            if domain_id == "regulation_enforcement":
                try:
                    cqc_rows = [dict(row) for row in conn.execute(
                        "SELECT location_id, COALESCE(provider_key, location_id) AS provider_key, "
                        "overall_rating, overall_rating_date FROM cqc_locations "
                        "WHERE overall_rating IS NOT NULL AND overall_rating_date IS NOT NULL").fetchall()]
                except Exception:
                    cqc_rows = []
                comparisons.extend(categorical_transitions(
                    cqc_rows, subject_key="provider_key", metric="overall_rating",
                    period_key="overall_rating_date", source_table="cqc_locations",
                    source_id_key="location_id", subject_type="provider_id"))
            written = 0
            for start in range(0, len(comparisons), self.batch_size):
                if self._cancelled(run_id):
                    return self._finalise_cancelled(run_id)
                batch = comparisons[start:start + self.batch_size]
                for comparison in batch:
                    current = comparison["current"]
                    signal = (structured_signal(
                        comparison, release_id=run["release_id"], domain_id=domain_id,
                        signal_type=f"{current['metric']}_change") if current["unit"] != "category" else
                        categorical_signal(comparison, release_id=run["release_id"], domain_id=domain_id,
                                           signal_type=f"{current['metric']}_transition"))
                    if signal is None:
                        continue
                    save_structured_signal(conn, signal, comparison)
                    written += 1
                self._update_run(conn, run_id, current_domain=domain_id, current_stage="computing")
                self._update_domain_progress(conn, run_id, domain_id,
                                              min(start + len(batch), len(observations)), written)
                conn.commit()
                self._heartbeat("running")
            self._finish_domain(conn, run_id, domain_id, "complete", len(observations), written,
                                prerequisite_status="ready", missing_tables=[], error_detail=None)
            conn.commit()
        finally:
            conn.close()

    def _link_run(self, run_id: str) -> None:
        """Create only allowlisted, canonical-identity links between signals."""
        conn = db.get_connection(self.settings)
        try:
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            if run is None:
                return
            rows = [dict(row) for row in conn.execute(
                "SELECT * FROM automated_signals WHERE release_id = ? ORDER BY created_at",
                (run["release_id"],)).fetchall()]
            self._update_run(conn, run_id, current_stage="connecting")
            for index, left in enumerate(rows):
                for right in rows[index + 1:]:
                    if left["domain_id"] == right["domain_id"]:
                        continue
                    link = link_signals(
                        left, right, left_spec=domains.get_domain(left["domain_id"]),
                        right_spec=domains.get_domain(right["domain_id"]),
                        relationship_type="narrative_structured_alignment", window_days=365)
                    if link:
                        save_link(conn, link)
            conn.commit()
        finally:
            conn.close()

    def _record_health(self, run_id: str, requested: list[str]) -> None:
        """Persist a small, source-local health snapshot after each run."""
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                return
            self._update_run(conn, run_id, current_stage="monitoring")
            for domain_id in requested:
                spec = domains.get_domain(domain_id)
                for table in spec.source_tables:
                    observed_schema: dict[str, Any] = {}
                    exists = True
                    try:
                        cursor = conn.execute(f"SELECT * FROM {table} LIMIT 0")
                        description = getattr(cursor, "description", None) or []
                        observed_schema = {str(item[0]): str(item[1] or "unknown") for item in description}
                        count = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                    except Exception:
                        exists, count = False, None
                    current = {
                        "expected_schema": {"table": table},
                        "observed_schema": observed_schema,
                        "row_count": count,
                        "parse_success": exists,
                        "content_hash": None,
                    }
                    baseline_row = conn.execute(
                        "SELECT expected_schema_json, observed_schema_json, row_count, parse_success, content_hash "
                        "FROM analysis_health_snapshots WHERE source_table = ? ORDER BY collected_at DESC LIMIT 1",
                        (table,)).fetchone()
                    baseline = {}
                    if baseline_row:
                        baseline = {"expected_schema": json.loads(baseline_row["expected_schema_json"] or "{}"),
                                    "observed_schema": json.loads(baseline_row["observed_schema_json"] or "{}"),
                                    "row_count": baseline_row["row_count"],
                                    "parse_success": bool(baseline_row["parse_success"]),
                                    "content_hash": baseline_row["content_hash"]}
                    save_snapshot(conn, HealthSnapshot(
                        source_table=table, collected_at=utcnow(), collection_success=exists,
                        parse_success=exists, expected_schema={"table": table},
                        observed_schema=observed_schema, row_count=count),
                        release_id=row["release_id"], domain_id=domain_id)
                    for proposal in detect_drift(current, baseline):
                        save_proposal(conn, proposal, release_id=row["release_id"], domain_id=domain_id)
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
                "SELECT de.document_element_id, d.document_id, d.source_key, de.text "
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
                                     "subject_id": self._document_subject_id(row["source_key"], row["document_id"]),
                                     "subject_type": spec.canonical_subject_keys[0],
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
                self._heartbeat("running")

            self._update_run(conn, run_id, current_domain=domain_id, current_stage="discovering")
            themes = discover_themes(passages)
            written = 0
            for theme in themes:
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                theme["passages"] = theme.get("passages", [])[:25]
                record_theme(conn, release_id=run["release_id"], domain_id=domain_id, theme=theme)
                record_topic(conn, release_id=run["release_id"], domain_id=domain_id,
                             topic_number=themes.index(theme), theme=theme)
                written += 1
            self._update_run(conn, run_id, current_domain=domain_id, current_stage="extracting")
            self._extract_narrative_signals(conn, run_id, domain_id, spec, run["release_id"], passages)
            positive_row = conn.execute(
                "SELECT COUNT(DISTINCT signal_id), COUNT(DISTINCT subject_id) FROM automated_signals "
                "WHERE release_id = ? AND domain_id = ?", (run["release_id"], domain_id)).fetchone()
            positives, subjects = int(positive_row[0]), int(positive_row[1])
            save_diagnostics(
                conn, release_id=run["release_id"], domain_id=domain_id,
                result=diagnostics(positives=positives, negatives=max(0, processed - positives),
                                   subjects=subjects, pacc=None, emq=None))
            self._finish_domain(conn, run_id, domain_id, "complete", processed, written,
                                prerequisite_status="ready", missing_tables=[], error_detail=None)
            conn.commit()
        except AnalysisCancelled:
            conn.rollback()
            self._finalise_cancelled(run_id)
        finally:
            conn.close()

    @staticmethod
    def _document_subject_id(source_key: str | None, document_id: str) -> str:
        """Use the source adapter's canonical key, not its document URL suffix."""
        return str(source_key or document_id).split("|", 1)[0]

    def _extract_narrative_signals(self, conn, run_id: str, domain_id: str, spec,
                                   release_id: str, passages: list[dict[str, Any]]) -> None:
        manifest = load_release(conn, release_id) or {}
        models = manifest.get("models", {})
        client = self.model_client_factory(
            self.settings, release_id=release_id, run_id=run_id, models=models, conn=conn)
        model_unavailable = False
        for passage in passages:
            if self._cancelled(run_id):
                raise AnalysisCancelled("analysis run cancelled at a batch boundary")
            prompt = extraction_prompt(namespace=spec.taxonomy_namespace,
                                       subject_type=passage["subject_type"],
                                       subject_id=str(passage["subject_id"]), text=passage["text"])
            try:
                first = self._model_call(client, prompt, role="scout", domain_id=domain_id,
                                         window_id=passage["evidence_ref"])
                second = self._model_call(client, prompt, role="extractor", domain_id=domain_id,
                                          window_id=passage["evidence_ref"])
            except CostCeilingExceeded:
                raise
            except AnalysisModelUnavailable:
                model_unavailable = True
                break
            candidate = candidate_from_payload(
                first, namespace=spec.taxonomy_namespace, subject_type=passage["subject_type"],
                subject_id=str(passage["subject_id"]), evidence_ref=passage["evidence_ref"],
                model_output=first)
            second_candidate = candidate_from_payload(
                second, namespace=spec.taxonomy_namespace, subject_type=passage["subject_type"],
                subject_id=str(passage["subject_id"]), evidence_ref=passage["evidence_ref"],
                model_output=second)
            if candidate is None or second_candidate is None:
                continue
            signal = candidate_to_signal(candidate, release_id=release_id, source_text=passage["text"],
                                         second_model=second_candidate)
            if signal is None:
                continue
            from pipeline.analysis.store import save_signal
            save_signal(conn, signal)
            conn.execute(
                "INSERT INTO analysis_verifier_results (verifier_result_id, signal_id, verifier_name, passed, score, reasons_json, created_at) "
                "VALUES (?, ?, 'dual_model_exact_grounding', 1, 1.0, '[]', ?)",
                (f"verifier-{uuid.uuid4()}", signal.signal_id, utcnow()))
            conn.commit()
        if model_unavailable:
            self._update_run(conn, run_id, current_stage="discovering")

    def _model_call(self, client, prompt: str, *, role: str, domain_id: str,
                    window_id: str) -> dict[str, Any] | None:
        budget = getattr(self, "_budget", CallBudget())
        budget.before_call()
        payload = client.generate_json(prompt, role=role, domain_id=domain_id, window_id=window_id)
        budget.record(getattr(client, "last_cost_micros", 0), cached=getattr(client, "last_cached", False))
        conn = client.conn
        conn.execute("UPDATE analysis_runs SET cost_micros = ?, updated_at = ? WHERE run_id = ?",
                     (budget.spent_micros, utcnow(), self._current_run_id))
        conn.commit()
        return payload

    @staticmethod
    def _missing_tables(conn, tables: tuple[str, ...]) -> list[str]:
        missing = []
        for table in tables:
            try:
                conn.execute(f"SELECT 1 FROM {table} LIMIT 1")
            except Exception:
                # A missing table aborts a PostgreSQL transaction. The caller
                # still needs to write the domain's unavailable status.
                conn.rollback()
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
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'failed', prerequisite_status = 'failed', "
                "completed_at = COALESCE(completed_at, ?), error_detail = COALESCE(error_detail, ?) "
                "WHERE run_id = ? AND status NOT IN ('complete', 'unavailable', 'failed')",
                (now, f"{type(exc).__name__}: {exc}", run_id))
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
