"""Database-backed executor for admin analysis runs.

The worker is intentionally a separate process from the web server. It polls
the relational warehouse, claims one queued run, and writes progress there so
the admin page can be closed, reopened, or served by another process without
losing the run state.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import queue
import threading
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import structlog

from pipeline import db
from pipeline.analysis import domains
from pipeline.analysis import state as analysis_state
from pipeline.analysis.budget import AnalysisCancelled, CallBudget, CostCeilingExceeded
from pipeline.analysis.graph import project_release, signal_store_from_settings
from pipeline.analysis.lineage import add_document_element_paths, add_edge, add_object
from pipeline.analysis.linking import link_signals, save_links
from pipeline.analysis.models import (
    AUDIT_INSERT_SQL,
    AnalysisModelClient,
    AnalysisModelConfigurationError,
    AnalysisModelInvalidJSON,
    AnalysisModelUnavailable,
)
from pipeline.analysis.narrative import (
    NARRATIVE_PREFILTER_VERSION,
    candidate_from_payload,
    candidate_to_signal,
    extraction_prompt,
    narrative_candidate_prefilter,
)
from pipeline.analysis.operations import (
    HealthSnapshot,
    detect_drift,
    save_proposal,
    save_snapshot,
    utcnow,
)
from pipeline.analysis.prefilter import qualifying_gate
from pipeline.analysis.prevalence import diagnostics, save_diagnostics
from pipeline.analysis.releases import finalise_manifest, load_release
from pipeline.analysis.store import (
    record_theme,
    record_topic,
    save_signals,
    save_structured_signals,
)
from pipeline.analysis.structured import (
    categorical_signal,
    categorical_transitions,
    comparisons_for_domain,
    observations_for_domain,
    structured_signal,
)

log = structlog.get_logger()

_THEME_EVIDENCE_PER_THEME = 25
_THEME_EVIDENCE_TOTAL = 5_000
_THEME_WRITE_BATCH_SIZE = 100


def _retry_at(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(seconds)))).isoformat()


def _stale_before(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=max(0.0, float(seconds)))).isoformat()


def _comparison_partition(observations):
    """Process-pool target for the pure in-memory comparison stage."""
    return comparisons_for_domain(observations)


def _partition_observations(observations, partitions):
    """Keep each subject/metric/unit group together in one process."""
    buckets = [[] for _ in range(max(1, partitions))]
    for observation in observations:
        key = "\x1f".join((observation.subject_type, observation.subject_id,
                            observation.metric, observation.unit))
        slot = int.from_bytes(hashlib.blake2s(key.encode(), digest_size=4).digest(), "big") % len(buckets)
        buckets[slot].append(observation)
    return [bucket for bucket in buckets if bucket]


class AnalysisWorker:
    """Claim and execute queued analysis runs one at a time."""

    def __init__(self, settings, *, poll_seconds: float = 5.0, batch_size: int = 100,
                 worker_id: str | None = None, model_client_factory=None,
                 comparison_workers: int | None = None):
        self.settings = settings
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.batch_size = max(1, int(batch_size))
        self.worker_id = worker_id or f"analysis-worker-{uuid.uuid4()}"
        self.model_client_factory = model_client_factory or AnalysisModelClient
        if comparison_workers is None:
            try:
                available_cpus = len(os.sched_getaffinity(0))
            except AttributeError:
                available_cpus = os.cpu_count() or 1
            comparison_workers = min(max(1, available_cpus), 4)
        self.comparison_workers = max(1, int(comparison_workers))
        self._budget_lock = threading.RLock()

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
            args=(heartbeat_stop, run_id),
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

    def _run_heartbeat_loop(self, stop: threading.Event, run_id: str) -> None:
        """Keep liveness visible while a run is CPU-bound between batches."""
        interval = max(0.5, min(self.poll_seconds, 5.0))
        while not stop.wait(interval):
            try:
                self._heartbeat("running", run_id=run_id)
            except Exception as exc:
                log.exception("analysis_heartbeat_failed",
                              worker_id=self.worker_id, error=str(exc))

    def _heartbeat(self, status: str, *, run_id: str | None = None) -> None:
        conn = db.get_connection(self.settings)
        try:
            try:
                worker_version = version("sub-misuse-evidence-pipeline")
            except PackageNotFoundError:
                worker_version = "source-checkout"
            now = utcnow()
            conn.execute(
                "INSERT INTO analysis_worker_heartbeats (worker_id, last_seen_at, status, version) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT (worker_id) DO UPDATE SET "
                "last_seen_at = excluded.last_seen_at, status = excluded.status, version = excluded.version",
                (self.worker_id, now, status, worker_version))
            if run_id is not None:
                conn.execute(
                    "UPDATE analysis_runs SET updated_at = %s WHERE run_id = %s AND status = 'running'",
                    (now, run_id))
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
                "UPDATE signal_graph_projection_queue SET processed_at = %s, attempt_count = attempt_count + 1, "
                "last_error = NULL WHERE release_id = %s AND processed_at IS NULL",
                (utcnow(), release_id))
            conn.commit()
        except Exception as exc:
            if queue is not None:
                conn.execute(
                    "UPDATE signal_graph_projection_queue SET attempt_count = attempt_count + 1, last_error = %s "
                    "WHERE release_id = %s AND processed_at IS NULL",
                    (str(exc), queue["release_id"]))
                conn.commit()
        finally:
            if store is not None:
                store.driver.close()
            conn.close()

    def _claim(self) -> str | None:
        conn = db.get_connection(self.settings)
        try:
            self._recover_runs(conn)
            analysis_state.purge_failed_detail(
                conn, retention_days=int(getattr(
                    self.settings, "failed_analysis_detail_retention_days", 7)))
            conn.commit()
            row = conn.execute(
                "SELECT run_id FROM analysis_runs WHERE status = 'queued' "
                "ORDER BY updated_at, started_at LIMIT 1").fetchone()
            if row is None:
                return None
            run_id = row["run_id"]
            changed = conn.execute(
                "UPDATE analysis_runs SET status = 'running', current_stage = 'starting', "
                "updated_at = %s WHERE run_id = %s AND status = 'queued'",
                (utcnow(), run_id)).rowcount
            if changed != 1:
                conn.rollback()
                return None
            conn.commit()
            return run_id
        finally:
            conn.close()

    def _recover_runs(self, conn) -> None:
        """Pause dead work and requeue due automatic retries transactionally."""
        now = utcnow()
        retry_at = _retry_at(getattr(self.settings, "analysis_retry_cooldown_seconds", 300.0))
        stale_before = _stale_before(getattr(self.settings, "analysis_stale_worker_seconds", 900.0))
        stale_rows = conn.execute(
            "SELECT run_id FROM analysis_runs WHERE status = 'running' AND updated_at < %s",
            (stale_before,)).fetchall()
        for row in stale_rows:
            run_id = row["run_id"]
            changed = conn.execute(
                "UPDATE analysis_runs SET status = 'paused', current_stage = 'waiting_for_retry', "
                "error_detail = %s, next_retry_at = %s, completed_at = NULL, updated_at = %s "
                "WHERE run_id = %s AND status = 'running'",
                ("worker heartbeat became stale; automatic retry scheduled", retry_at, now, run_id)).rowcount
            if changed:
                conn.execute(
                    "UPDATE analysis_domain_runs SET status = 'paused', completed_at = NULL, "
                    "error_detail = %s, next_retry_at = %s WHERE run_id = %s AND status = 'running'",
                    ("worker heartbeat became stale; automatic retry scheduled", retry_at, run_id))
                log.warning("analysis_run_requeued_after_stale_worker", run_id=run_id,
                            retry_at=retry_at)

        due_rows = conn.execute(
            "SELECT run_id, COALESCE(automatic_retry_count, 0) AS automatic_retry_count "
            "FROM analysis_runs WHERE status = 'paused' AND next_retry_at IS NOT NULL "
            "AND next_retry_at <= %s ORDER BY updated_at",
            (now,)).fetchall()
        max_retries = max(0, int(getattr(self.settings, "analysis_max_automatic_retries", 12)))
        for row in due_rows:
            run_id = row["run_id"]
            retry_count = int(row["automatic_retry_count"] or 0)
            if retry_count >= max_retries:
                conn.execute(
                    "UPDATE analysis_runs SET status = 'failed', current_stage = 'failed', "
                "error_detail = %s, completed_at = %s, next_retry_at = NULL, updated_at = %s "
                    "WHERE run_id = %s AND status = 'paused'",
                    ("automatic retry limit reached", now, now, run_id))
                conn.execute(
                    "UPDATE analysis_domain_runs SET status = 'failed', prerequisite_status = 'failed', "
                "completed_at = COALESCE(completed_at, %s), next_retry_at = NULL, "
                "error_detail = COALESCE(error_detail, %s) "
                    "WHERE run_id = %s AND status = 'paused'",
                    (now, "automatic retry limit reached", run_id))
                log.error("analysis_run_automatic_retry_limit_reached", run_id=run_id,
                          retry_count=retry_count)
                continue
            changed = conn.execute(
                "UPDATE analysis_runs SET status = 'queued', current_stage = 'queued', "
                "current_domain = NULL, automatic_retry_count = automatic_retry_count + 1, "
                "next_retry_at = NULL, error_detail = NULL, updated_at = %s "
                "WHERE run_id = %s AND status = 'paused'",
                (now, run_id)).rowcount
            if changed:
                conn.execute(
                    "UPDATE analysis_domain_runs SET status = 'pending', next_retry_at = NULL, "
                    "error_detail = NULL WHERE run_id = %s AND status = 'paused'",
                    (run_id,))
                log.info("analysis_run_automatically_requeued", run_id=run_id,
                         retry_count=retry_count + 1)
        conn.commit()

    def _execute(self, run_id: str) -> dict[str, Any]:
        conn = db.get_connection(self.settings)
        try:
            run = conn.execute("SELECT * FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
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
            if self._run_status(run_id) == "paused":
                return self._refresh_run(run_id)

        if self._run_status(run_id) == "paused":
            return self._refresh_run(run_id)

        self._link_run(run_id)
        self._record_health(run_id, requested)

        return self._refresh_run(run_id, force_complete=True)

    def _execute_domain(self, run_id: str, domain_id: str) -> None:
        spec = domains.get_domain(domain_id)
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute(
                "SELECT * FROM analysis_domain_runs WHERE run_id = %s AND domain_id = %s",
                (run_id, domain_id)).fetchone()
            if row is None or row["status"] in {"complete", "unavailable"}:
                return
            now = utcnow()
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'running', prerequisite_status = 'checking', "
                "started_at = COALESCE(started_at, %s), error_detail = NULL WHERE run_id = %s AND domain_id = %s",
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
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            self._update_run(conn, run_id, current_domain=domain_id, current_stage="computing")
            conn.commit()
            self._heartbeat("running")
            observations = observations_for_domain(conn, spec.source_tables)
            self._heartbeat("running")
            comparisons = self._comparisons(observations)
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
                batch_items = []
                for comparison in batch:
                    current = comparison["current"]
                    signal = (structured_signal(
                        comparison, release_id=run["release_id"], domain_id=domain_id,
                        signal_type=f"{current['metric']}_change") if current["unit"] != "category" else
                        categorical_signal(comparison, release_id=run["release_id"], domain_id=domain_id,
                                           signal_type=f"{current['metric']}_transition"))
                    if signal is None:
                        continue
                    batch_items.append((signal, comparison))
                written += save_structured_signals(conn, batch_items)
                for signal, comparison in batch_items:
                    output_node = add_object(
                        conn, kind="analysis", canonical_id=signal.signal_id,
                        processor_version="structured-comparison-v1",
                        metadata={"release_id": run["release_id"], "domain_id": domain_id})
                    for observation in (comparison["previous"], comparison["current"]):
                        source_table = str(observation["source_table"])
                        source_row_id = str(observation["source_row_id"])
                        source_node = add_object(
                            conn, kind="source", canonical_id=source_table)
                        retrieval_node = add_object(
                            conn, kind="retrieval",
                            canonical_id=f"{source_table}:{source_row_id}",
                            metadata={"source_table": source_table,
                                      "source_row_id": source_row_id})
                        add_edge(
                            conn, generated_id=retrieval_node, used_id=source_node,
                            activity="structured_row", activity_version="structured-comparison-v1")
                        add_edge(
                            conn, generated_id=output_node, used_id=retrieval_node,
                            activity="deterministic_comparison",
                            activity_version="structured-comparison-v1")
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

    def _comparisons(self, observations):
        """Run CPU-bound comparisons in processes, with one DB writer left."""
        if self.comparison_workers <= 1 or len(observations) < 10_000:
            return comparisons_for_domain(observations)
        partitions = _partition_observations(observations, self.comparison_workers)
        with ProcessPoolExecutor(
                max_workers=min(self.comparison_workers, len(partitions)),
                mp_context=multiprocessing.get_context("spawn")) as pool:
            results = pool.map(_comparison_partition, partitions)
            return [comparison for partition in results for comparison in partition]

    def _link_run(self, run_id: str) -> None:
        """Create only allowlisted, canonical-identity links between signals."""
        conn = db.get_connection(self.settings)
        try:
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
            if run is None:
                return
            relationship = "narrative_structured_alignment"
            registry = domains.domain_registry()
            allowed_pairs = [
                (left, right) for left in sorted(registry) for right in sorted(registry)
                if left < right and relationship in registry[left].cross_source_rules and
                relationship in registry[right].cross_source_rules
            ]
            if not allowed_pairs:
                return
            pair_clause = " OR ".join(
                "(l.domain_id = %s AND r.domain_id = %s)" for _ in allowed_pairs)
            pair_params = [value for pair in allowed_pairs for value in pair]
            self._update_run(conn, run_id, current_stage="connecting")
            last_left = ""
            last_right = ""
            while True:
                rows = conn.execute(
                    "SELECT l.*, r.signal_id AS _right_signal_id, r.domain_id AS _right_domain_id, "
                    "r.taxonomy_namespace AS _right_taxonomy_namespace, r.signal_type AS _right_signal_type, "
                    "r.subject_type AS _right_subject_type, r.subject_id AS _right_subject_id, "
                    "r.direction AS _right_direction, r.assertion_status AS _right_assertion_status, "
                    "r.period_start AS _right_period_start, r.period_end AS _right_period_end, "
                    "r.evidence_refs_json AS _right_evidence_refs_json, "
                    "r.derivation_method AS _right_derivation_method, "
                    "r.confidence_contract_json AS _right_confidence_contract_json "
                    "FROM automated_signals l JOIN automated_signals r ON "
                    "l.release_id = r.release_id AND l.subject_type = r.subject_type "
                    "AND l.subject_id = r.subject_id AND l.domain_id < r.domain_id "
                    "AND l.period_end IS NOT NULL AND r.period_end IS NOT NULL "
                    "AND l.period_end ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' "
                    "AND r.period_end ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' "
                    "AND CASE WHEN to_char(to_date(LEFT(l.period_end, 10), 'YYYY-MM-DD'), "
                    "'YYYY-MM-DD') = LEFT(l.period_end, 10) "
                    "AND to_char(to_date(LEFT(r.period_end, 10), 'YYYY-MM-DD'), "
                    "'YYYY-MM-DD') = LEFT(r.period_end, 10) "
                    "THEN ABS(to_date(LEFT(l.period_end, 10), 'YYYY-MM-DD') "
                    "- to_date(LEFT(r.period_end, 10), 'YYYY-MM-DD')) <= 365 "
                    "ELSE FALSE END "
                    f"AND ({pair_clause}) WHERE l.release_id = %s "
                    "AND (l.signal_id > %s OR (l.signal_id = %s AND r.signal_id > %s)) "
                    "ORDER BY l.signal_id, r.signal_id LIMIT %s",
                    (*pair_params, run["release_id"], last_left, last_left, last_right,
                     self.batch_size)).fetchall()
                if not rows:
                    break
                links = []
                for raw in rows:
                    source = dict(raw)
                    right = {key.removeprefix("_right_"): value for key, value in source.items()
                             if key.startswith("_right_")}
                    left = {key: value for key, value in source.items()
                            if not key.startswith("_right_")}
                    link = link_signals(
                        left, right, left_spec=domains.get_domain(left["domain_id"]),
                        right_spec=domains.get_domain(right["domain_id"]),
                        relationship_type=relationship, window_days=365)
                    if link:
                        links.append(link)
                save_links(conn, links)
                last_left = rows[-1]["signal_id"]
                last_right = rows[-1]["_right_signal_id"]
                conn.commit()
        finally:
            conn.close()

    def _record_health(self, run_id: str, requested: list[str]) -> None:
        """Persist a small, source-local health snapshot after each run."""
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
            if row is None:
                return
            self._update_run(conn, run_id, current_stage="monitoring")
            from pipeline.analysis.inventory import table_snapshot

            tables = sorted({table for domain_id in requested
                             for table in domains.get_domain(domain_id).source_tables})
            for table in tables:
                snapshot = table_snapshot(
                    conn, table, max_age_seconds=int(getattr(
                        self.settings, "operational_snapshot_max_age_seconds", 900)))
                observed_schema = snapshot["observed_schema"]
                exists = bool(snapshot["exists"])
                count = snapshot["row_count"]
                current = {
                        "expected_schema": {"table": table},
                        "observed_schema": observed_schema,
                        "row_count": count,
                        "parse_success": exists,
                        "content_hash": None,
                }
                baseline_row = conn.execute(
                        "SELECT expected_schema_json, observed_schema_json, row_count, parse_success, content_hash "
                        "FROM analysis_health_snapshots WHERE source_table = %s ORDER BY collected_at DESC LIMIT 1",
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
                    release_id=row["release_id"], domain_id=None)
                for proposal in detect_drift(current, baseline):
                    save_proposal(conn, proposal, release_id=row["release_id"], domain_id=None)
            conn.commit()
        finally:
            conn.close()

    def _execute_narrative(self, run_id: str, domain_id: str, spec) -> None:
        conn = db.get_connection(self.settings)
        input_manifest = None
        try:
            run = conn.execute("SELECT release_id FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
            if run is None:
                raise KeyError(run_id)
            release_manifest = load_release(conn, run["release_id"]) or {}
            suppression_requested = bool(getattr(
                self.settings, "analysis_prefilter_suppression_enabled", False))
            gate = qualifying_gate(conn, explicitly_enabled=suppression_requested)
            suppression = gate is not None
            input_manifest = analysis_state.get_or_create_manifest(
                conn, run_id=run_id, release_id=run["release_id"], domain_id=domain_id,
                source_tables=spec.source_tables,
                configuration={"models": release_manifest.get("models", {}),
                               "model_fallbacks": release_manifest.get("model_fallbacks", {}),
                               "theme_evidence_per_theme": _THEME_EVIDENCE_PER_THEME,
                               "theme_evidence_total": _THEME_EVIDENCE_TOTAL,
                               "suppression_requested": suppression_requested,
                               "suppression_enabled": suppression,
                               "prefilter_result_sha256": (
                                   gate["result_sha256"] if gate else None)},
                prefilter_version=NARRATIVE_PREFILTER_VERSION,
                prefilter_result_sha256=gate["result_sha256"] if gate else None,
                suppression_enabled=suppression)
            processed = int(input_manifest["input_count"] or 0)
            source_marks = ", ".join("%s" for _ in spec.source_tables)
            last_document = input_manifest.get("checkpoint_document_id")
            last_sequence = input_manifest.get("checkpoint_sequence")
            last_element = input_manifest.get("checkpoint_element_id")
            while True:
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                where = (
                    "dv.is_active = 1 AND de.text IS NOT NULL AND TRIM(de.text) <> '' "
                    f"AND d.source_table IN ({source_marks})")
                params: list[Any] = list(spec.source_tables)
                if last_document is not None:
                    where += (" AND (d.document_id > %s OR "
                              "(d.document_id = %s AND (de.sequence > %s OR "
                              "(de.sequence = %s AND de.document_element_id > %s))))")
                    params.extend([last_document, last_document, last_sequence,
                                   last_sequence, last_element])
                batch = conn.execute(
                    "SELECT de.document_element_id, d.document_id, d.source_key, "
                    "de.sequence, de.text, de.text_sha256 FROM document_elements de "
                    "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
                    "JOIN document_records d ON d.document_id = dv.document_id "
                    f"WHERE {where} ORDER BY d.document_id, de.sequence, "
                    "de.document_element_id LIMIT %s", (*params, self.batch_size)).fetchall()
                if not batch:
                    break
                accepted = []
                theme_passages = []
                batch_rows = [dict(row) for row in batch]
                for offset, row in enumerate(batch_rows, start=processed + 1):
                    text = str(row["text"] or "").strip()
                    passage = {
                        "text": text, "document_id": row["document_id"],
                        "subject_id": self._document_subject_id(row["source_key"], row["document_id"]),
                        "subject_type": spec.canonical_subject_keys[0],
                        "evidence_ref": row["document_element_id"],
                    }
                    theme_passages.append(passage)
                    matched = narrative_candidate_prefilter(text, enabled=True)
                    if matched or not suppression:
                        accepted.append((offset, row["document_element_id"], matched))
                accumulator_state = analysis_state.accumulate_themes(
                    conn, input_manifest["input_manifest_id"], theme_passages,
                    first_ordinal=processed + 1,
                    max_evidence_per_theme=_THEME_EVIDENCE_PER_THEME,
                    max_evidence_total=_THEME_EVIDENCE_TOTAL)
                input_manifest = analysis_state.checkpoint(
                    conn, input_manifest, rows=batch_rows,
                    accumulator_state=accumulator_state, accepted=accepted)
                processed = int(input_manifest["input_count"])
                self._update_run(conn, run_id, current_domain=domain_id, current_stage="windowing")
                self._update_domain_progress(conn, run_id, domain_id, processed, 0)
                conn.commit()
                self._heartbeat("running")
                tail = batch[-1]
                last_document = tail["document_id"]
                last_sequence = tail["sequence"]
                last_element = tail["document_element_id"]

            self._update_run(conn, run_id, current_domain=domain_id, current_stage="discovering")
            conn.commit()
            themes = analysis_state.accumulated_themes(
                conn, input_manifest["input_manifest_id"])
            written = 0
            for topic_number, theme in enumerate(themes):
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                theme["theme_id"] = "theme-" + hashlib.sha256(
                    f"{run['release_id']}\0{domain_id}\0{theme['theme_key']}".encode()).hexdigest()
                record_theme(conn, release_id=run["release_id"], domain_id=domain_id, theme=theme)
                record_topic(conn, release_id=run["release_id"], domain_id=domain_id,
                             topic_number=topic_number, theme=theme)
                written += 1
                if (topic_number + 1) % _THEME_WRITE_BATCH_SIZE == 0:
                    conn.commit()
                    self._heartbeat("running")
            self._update_run(conn, run_id, current_domain=domain_id, current_stage="extracting")
            conn.commit()
            extraction_complete = self._extract_narrative_signals(
                conn, run_id, domain_id, spec, run["release_id"],
                analysis_state.candidate_batches(
                    conn, input_manifest["input_manifest_id"], batch_size=self.batch_size))
            if not extraction_complete:
                self._pause_for_retry(conn, run_id, domain_id,
                                      "model/provider availability exhausted; automatic retry scheduled")
                conn.commit()
                return
            positive_row = conn.execute(
                "SELECT COUNT(DISTINCT signal_id) AS positives, COUNT(DISTINCT subject_id) AS subjects FROM automated_signals "
                "WHERE release_id = %s AND domain_id = %s", (run["release_id"], domain_id)).fetchone()
            positives, subjects = int(positive_row["positives"]), int(positive_row["subjects"])
            save_diagnostics(
                conn, release_id=run["release_id"], domain_id=domain_id,
                result=diagnostics(positives=positives, negatives=max(0, processed - positives),
                                   subjects=subjects, pacc=None, emq=None))
            self._finish_domain(conn, run_id, domain_id, "complete", processed, written,
                                prerequisite_status="ready", missing_tables=[], error_detail=None)
            digest = analysis_state.output_digest(
                conn, release_id=run["release_id"], domain_id=domain_id)
            analysis_state.complete_and_purge(
                conn, input_manifest["input_manifest_id"], expected_output_sha256=digest)
            conn.commit()
        except AnalysisCancelled:
            conn.rollback()
            self._finalise_cancelled(run_id)
        except Exception:
            conn.rollback()
            if input_manifest is not None:
                analysis_state.mark_failed(conn, input_manifest["input_manifest_id"])
                conn.commit()
            raise
        finally:
            conn.close()

    @staticmethod
    def _document_subject_id(source_key: str | None, document_id: str) -> str:
        """Use the source adapter's canonical key, not its document URL suffix."""
        return str(source_key or document_id).split("|", 1)[0]

    def _extract_narrative_signals(self, conn, run_id: str, domain_id: str, spec,
                                   release_id: str, passage_batches) -> bool:
        manifest = load_release(conn, release_id) or {}
        models = manifest.get("models", {})
        fallback_models = manifest.get("model_fallbacks", {})
        model_unavailable = False
        requested_workers = max(1, min(4, int(getattr(
            self.settings, "analysis_model_concurrency", 4))))
        # A hard cost ceiling cannot account for the cost of concurrent calls
        # until their responses arrive. Keep that guarantee strict.
        if getattr(self, "_budget", CallBudget()).ceiling_micros > 0:
            requested_workers = 1
        if isinstance(passage_batches, list):
            passages = passage_batches
            passage_batches = (passages[start:start + self.batch_size]
                               for start in range(0, len(passages), self.batch_size))
        audit_rows: queue.SimpleQueue = queue.SimpleQueue()
        cache_rows: queue.SimpleQueue = queue.SimpleQueue()
        response_cache: dict[str, dict[str, Any]] = {}
        cache_lock = threading.Lock()
        local = threading.local()

        def cache_lookup(request_sha):
            with cache_lock:
                return response_cache.get(request_sha)

        def cache_sink(row):
            with cache_lock:
                response_cache.setdefault(row["request_sha256"], row)
                while len(response_cache) > 4096:
                    response_cache.pop(next(iter(response_cache)))
            cache_rows.put(row)

        def client_for_thread():
            if not hasattr(local, "client"):
                local.client = self.model_client_factory(
                    self.settings, release_id=release_id, run_id=run_id, models=models,
                    fallback_models=fallback_models, conn=None,
                    audit_sink=audit_rows.put, cache_lookup=cache_lookup, cache_sink=cache_sink)
                with cache_lock:
                    close = getattr(local.client, "close", None)
                    if close:
                        client_stack.callback(close)
            return local.client

        with ExitStack() as client_stack, ThreadPoolExecutor(
                max_workers=requested_workers, thread_name_prefix="analysis-model") as pool:
            for passages in passage_batches:
                if self._cancelled(run_id):
                    raise AnalysisCancelled("analysis run cancelled at a batch boundary")
                for passage in passages:
                    # Candidate batches carry the canonical source key. Keep
                    # accepting already-normalised passages used by callers
                    # and tests without recalculating or weakening identity.
                    if not passage.get("subject_id"):
                        passage["subject_id"] = self._document_subject_id(
                            passage.get("source_key"), passage["document_id"])
                    passage.setdefault("subject_type", spec.canonical_subject_keys[0])
                if self.model_client_factory is AnalysisModelClient:
                    identity_client = AnalysisModelClient(
                        self.settings, release_id=release_id, run_id=run_id,
                        models=models, fallback_models=fallback_models, conn=None,
                        audit_sink=lambda _row: None)
                    request_keys = []
                    for passage in passages:
                        prompt = extraction_prompt(
                            namespace=spec.taxonomy_namespace,
                            subject_type=passage["subject_type"],
                            subject_id=str(passage["subject_id"]), text=passage["text"])
                        request_keys.extend(filter(None, (
                            identity_client.request_sha(prompt, role="scout"),
                            identity_client.request_sha(prompt, role="extractor"))))
                    if request_keys:
                        marks = ", ".join("%s" for _ in request_keys)
                        for row in conn.execute(
                                "SELECT * FROM analysis_model_response_cache "
                                f"WHERE request_sha256 IN ({marks})", request_keys):
                            response_cache[row["request_sha256"]] = dict(row)
                        while len(response_cache) > 4096:
                            response_cache.pop(next(iter(response_cache)))
                futures = [pool.submit(
                    self._extract_narrative_passage, client_for_thread, passage,
                    run_id, domain_id, spec, release_id) for passage in passages]
                signals = []
                completed_candidates = []
                failed_candidates = []
                fatal_error = None
                for passage, future in zip(passages, futures, strict=True):
                    try:
                        extracted = future.result()
                    except (CostCeilingExceeded, AnalysisModelConfigurationError) as exc:
                        fatal_error = fatal_error or exc
                        failed_candidates.append((passage.get("candidate_id"), str(exc)))
                        continue
                    except AnalysisModelUnavailable as exc:
                        log.warning("analysis_model_unavailable", run_id=run_id, domain_id=domain_id,
                                    error=str(exc))
                        model_unavailable = True
                        continue
                    except Exception as exc:
                        fatal_error = fatal_error or exc
                        failed_candidates.append((passage.get("candidate_id"), str(exc)))
                        continue
                    completed_candidates.append(passage.get("candidate_id"))
                    if extracted is None:
                        continue
                    passage, candidate, second_candidate = extracted
                    signal = candidate_to_signal(
                        candidate, release_id=release_id, source_text=passage["text"],
                        second_model=second_candidate)
                    if signal is None:
                        continue
                    signals.append(signal)
                self._flush_model_rows(conn, cache_rows, audit_rows)
                save_signals(conn, signals)
                conn.executemany(
                    "INSERT INTO analysis_verifier_results (verifier_result_id, signal_id, verifier_name, "
                    "passed, score, reasons_json, created_at) VALUES (%s, %s, "
                    "'dual_model_exact_grounding', 1, 1.0, '[]', %s)",
                    [(f"verifier-{uuid.uuid4()}", signal.signal_id, utcnow()) for signal in signals])
                element_lineage = add_document_element_paths(
                    conn, [signal.evidence_refs[0] for signal in signals])
                for signal in signals:
                    output = add_object(conn, kind="analysis", canonical_id=signal.signal_id,
                                        processor_version=NARRATIVE_PREFILTER_VERSION,
                                        metadata={"release_id": release_id,
                                                  "domain_id": domain_id})
                    used = element_lineage.get(signal.evidence_refs[0])
                    if used:
                        add_edge(conn, generated_id=output, used_id=used,
                                 activity="narrative_analysis",
                                 activity_version=NARRATIVE_PREFILTER_VERSION)
                analysis_state.mark_candidates(
                    conn, [value for value in completed_candidates if value], "complete")
                conn.executemany(
                    "UPDATE analysis_candidates SET status = 'failed', error_detail = %s "
                    "WHERE candidate_id = %s",
                    [(error[:2000], candidate_id) for candidate_id, error in failed_candidates
                     if candidate_id])
                conn.execute(
                    "UPDATE analysis_runs SET cost_micros = %s, updated_at = %s WHERE run_id = %s",
                    (self._budget.spent_micros, utcnow(), run_id))
                conn.commit()
                if fatal_error is not None:
                    raise fatal_error
                if model_unavailable:
                    break
        if model_unavailable:
            self._update_run(conn, run_id, current_stage="discovering")
        return not model_unavailable

    def _extract_narrative_passage(self, client_factory, passage, run_id: str,
                                   domain_id: str, spec, release_id: str):
        """Extract one passage; model threads never own database connections."""
        client = client_factory()
        prompt = extraction_prompt(namespace=spec.taxonomy_namespace,
                                   subject_type=passage["subject_type"],
                                   subject_id=str(passage["subject_id"]), text=passage["text"])
        try:
            first = self._model_call_with_json_retry(
                client, prompt, role="scout", domain_id=domain_id,
                window_id=passage["evidence_ref"], run_id=run_id)
            first_candidate = candidate_from_payload(
                first, namespace=spec.taxonomy_namespace,
                subject_type=passage["subject_type"],
                subject_id=str(passage["subject_id"]),
                evidence_ref=passage["evidence_ref"], model_output=first)
            if first_candidate is None and getattr(
                    self.settings, "claim_signal_skip_extractor_on_null", True):
                return None
            second = self._model_call_with_json_retry(
                client, prompt, role="extractor", domain_id=domain_id,
                window_id=passage["evidence_ref"], run_id=run_id)
        except AnalysisModelInvalidJSON as exc:
            log.warning("analysis_model_invalid_json_skipped", run_id=run_id,
                        domain_id=domain_id, window_id=passage["evidence_ref"], error=str(exc))
            return None
        second_candidate = candidate_from_payload(
            second, namespace=spec.taxonomy_namespace, subject_type=passage["subject_type"],
            subject_id=str(passage["subject_id"]), evidence_ref=passage["evidence_ref"],
            model_output=second)
        if first_candidate is None or second_candidate is None:
            return None
        return passage, first_candidate, second_candidate

    @staticmethod
    def _flush_model_rows(conn, cache_rows, audit_rows) -> None:
        caches = []
        while not cache_rows.empty():
            caches.append(cache_rows.get())
        conn.executemany(
            "INSERT INTO analysis_model_response_cache (request_sha256, response_sha256, response_json, "
            "requested_model, actual_model, provider_id, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT DO NOTHING",
            [(row["request_sha256"], row["response_sha256"], row["response_json"],
             row["requested_model"], row["actual_model"], row.get("provider_id"), row["created_at"])
             for row in caches])
        if caches:
            keys = list(dict.fromkeys(row["request_sha256"] for row in caches))
            marks = ", ".join("%s" for _ in keys)
            stored = {row["request_sha256"]: row["response_sha256"] for row in conn.execute(
                "SELECT request_sha256, response_sha256 FROM analysis_model_response_cache "
                f"WHERE request_sha256 IN ({marks})", keys)}
            if any(stored.get(row["request_sha256"]) != row["response_sha256"] for row in caches):
                raise RuntimeError("content-addressed model response conflict")
        audits = []
        while not audit_rows.empty():
            audits.append(audit_rows.get())
        conn.executemany(AUDIT_INSERT_SQL, audits)

    def _model_call_with_json_retry(self, client, prompt: str, *, role: str,
                                    domain_id: str, window_id: str, run_id: str):
        """Retry one malformed JSON response, then let the caller skip it.

        A malformed response is a model-output defect local to one passage;
        turning it into a domain-wide stop discards the rest of a large
        corpus. Other unavailability errors still propagate to the existing
        fail-closed path.
        """
        try:
            return self._model_call(client, prompt, role=role, domain_id=domain_id, window_id=window_id)
        except AnalysisModelInvalidJSON:
            log.warning("analysis_model_invalid_json_retry", run_id=run_id, domain_id=domain_id,
                        role=role, window_id=window_id)
            retry_prompt = (f"{prompt}\n\nIMPORTANT: your previous response was incomplete or invalid JSON. "
                            "Return one complete JSON object only, with no markdown, commentary or trailing text.")
            return self._model_call(client, retry_prompt, role=role, domain_id=domain_id, window_id=window_id)

    def _model_call(self, client, prompt: str, *, role: str, domain_id: str,
                    window_id: str) -> dict[str, Any] | None:
        budget = getattr(self, "_budget", CallBudget())
        with self._budget_lock:
            budget.before_call()
        payload = client.generate_json(prompt, role=role, domain_id=domain_id, window_id=window_id)
        with self._budget_lock:
            budget.record(getattr(client, "last_cost_micros", 0), cached=getattr(client, "last_cached", False))
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
        clause = ", ".join(f"{key} = %s" for key in values)
        conn.execute(f"UPDATE analysis_runs SET {clause} WHERE run_id = %s",
                     (*values.values(), run_id))

    @staticmethod
    def _update_domain_progress(conn, run_id: str, domain_id: str,
                                processed: int, written: int) -> None:
        conn.execute(
            "UPDATE analysis_domain_runs SET rows_processed = %s, rows_written = %s "
            "WHERE run_id = %s AND domain_id = %s", (processed, written, run_id, domain_id))

    def _pause_for_retry(self, conn, run_id: str, domain_id: str, error_detail: str) -> None:
        now = utcnow()
        retry_at = _retry_at(getattr(self.settings, "analysis_retry_cooldown_seconds", 300.0))
        conn.execute(
            "UPDATE analysis_domain_runs SET status = 'paused', completed_at = NULL, "
            "next_retry_at = %s, error_detail = %s WHERE run_id = %s AND domain_id = %s",
            (retry_at, error_detail, run_id, domain_id))
        conn.execute(
            "UPDATE analysis_runs SET status = 'paused', current_stage = 'waiting_for_retry', "
            "next_retry_at = %s, error_detail = %s, completed_at = NULL, updated_at = %s "
            "WHERE run_id = %s AND status = 'running'",
            (retry_at, error_detail, now, run_id))

    @staticmethod
    def _finish_domain(conn, run_id: str, domain_id: str, status: str,
                       processed: int, written: int, *, prerequisite_status: str,
                       missing_tables: list[str], error_detail: str | None) -> None:
        now = utcnow()
        conn.execute(
            "UPDATE analysis_domain_runs SET status = %s, prerequisite_status = %s, "
            "missing_tables_json = %s, rows_processed = %s, rows_written = %s, "
            "completed_at = %s, error_detail = %s WHERE run_id = %s AND domain_id = %s",
            (status, prerequisite_status, json.dumps(missing_tables), processed, written,
             now, error_detail, run_id, domain_id))

    def _refresh_run(self, self_run_id: str, *, force_complete: bool = False) -> dict[str, Any]:
        from pipeline.web.analysis import run as read_run

        conn = db.get_connection(self.settings)
        try:
            rows = conn.execute(
                "SELECT status FROM analysis_domain_runs WHERE run_id = %s", (self_run_id,)).fetchall()
            statuses = [row["status"] for row in rows]
            if self._cancelled_with_conn(conn, self_run_id):
                status, stage = "cancelled", "cancelled"
            elif any(value == "failed" for value in statuses):
                status, stage = "failed", "failed"
            elif any(value == "paused" for value in statuses):
                status, stage = "paused", "waiting_for_retry"
            elif statuses and all(value in {"complete", "unavailable"} for value in statuses):
                status, stage = "complete", "complete"
            else:
                status, stage = "running", "processing"
            now = utcnow()
            self._update_run(conn, self_run_id, status=status, current_stage=stage,
                             completed_at=now if status in {"complete", "failed", "cancelled"} else None)
            if status == "complete":
                release = conn.execute(
                    "SELECT release_id FROM analysis_runs WHERE run_id = %s",
                    (self_run_id,)).fetchone()
                if release:
                    release_digest = analysis_state.output_digest(
                        conn, release_id=release["release_id"])
                    finalise_manifest(
                        conn, release["release_id"], output_sha256=release_digest)
            analysis_state.purge_failed_detail(
                conn, retention_days=int(getattr(
                    self.settings, "failed_analysis_detail_retention_days", 7)))
            conn.commit()
            return read_run(conn, self_run_id)
        finally:
            conn.close()

    def _run_status(self, run_id: str) -> str | None:
        conn = db.get_connection(self.settings)
        try:
            row = conn.execute("SELECT status FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
            return row["status"] if row else None
        finally:
            conn.close()

    def _finalise_cancelled(self, run_id: str) -> dict[str, Any]:
        conn = db.get_connection(self.settings)
        try:
            now = utcnow()
            conn.execute(
                "UPDATE analysis_runs SET status = 'cancelled', current_stage = 'cancelled', "
                "completed_at = COALESCE(completed_at, %s), cancelled_at = COALESCE(cancelled_at, %s), "
                "updated_at = %s WHERE run_id = %s", (now, now, now, run_id))
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'cancelled' "
                "WHERE run_id = %s AND status NOT IN ('complete', 'unavailable')", (run_id,))
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
                "error_detail = %s, completed_at = %s, updated_at = %s WHERE run_id = %s",
                (f"{type(exc).__name__}: {exc}", now, now, run_id))
            conn.execute(
                "UPDATE analysis_domain_runs SET status = 'failed', prerequisite_status = 'failed', "
                "completed_at = COALESCE(completed_at, %s), error_detail = COALESCE(error_detail, %s) "
                "WHERE run_id = %s AND status NOT IN ('complete', 'unavailable', 'failed')",
                (now, f"{type(exc).__name__}: {exc}", run_id))
            conn.execute(
                "UPDATE analysis_input_manifests SET status = 'failed', updated_at = %s "
                "WHERE run_id = %s AND status = 'active'", (now, run_id))
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
        row = conn.execute("SELECT status FROM analysis_runs WHERE run_id = %s", (run_id,)).fetchone()
        return row is None or row["status"] == "cancelled"
