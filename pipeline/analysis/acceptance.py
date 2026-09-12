"""Reproducible Phase 2 parity snapshots and instrumented worker runs.

The harness records only measurements it actually observes.  In particular,
it labels Python allocator memory and client-side SQL calls precisely rather
than presenting either as total host memory or PostgreSQL server statements.
"""
from __future__ import annotations

import hashlib
import json
import platform
import threading
import time
import tracemalloc
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pipeline import db
from pipeline.analysis.domains import domain_registry
from pipeline.analysis.releases import code_commit
from pipeline.catalog import quote

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

SNAPSHOT_VERSION = "phase2-acceptance-v1"
CORRECTNESS_SECTIONS = frozenset({"signals", "themes", "topics", "verifiers", "links"})


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _parse_json(value: Any, fallback: Any) -> Any:
    try:
        return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return fallback


def _normalise(rows: Iterable[Any], *, omit: set[str]) -> list[dict[str, Any]]:
    values = []
    for raw in rows:
        row = dict(raw)
        values.append({key: _parse_json(value, value) if key.endswith("_json") else value
                       for key, value in row.items() if key not in omit})
    return values


def _section(rows: list[dict[str, Any]], *, ordered: bool = False) -> dict[str, Any]:
    canonical_rows = [_canonical(row) for row in rows]
    unordered_rows = sorted(canonical_rows)
    result = {"count": len(rows), "digest": _digest(unordered_rows)}
    if ordered:
        result["ordered_digest"] = _digest(canonical_rows)
    return result


def _source_digests(conn, selected_domains: Iterable[str]) -> list[dict[str, Any]]:
    registry = domain_registry()
    tables = sorted({table for domain_id in selected_domains
                     for table in registry[domain_id].source_tables})
    results = []
    for table in tables:
        digest = hashlib.sha256()
        count = 0
        cursor_name = "phase2_acceptance_" + uuid.uuid4().hex
        try:
            with conn.cursor(name=cursor_name) as cursor:
                cursor.execute(
                    f"SELECT to_jsonb(source_row)::text AS row_json FROM {quote(table)} source_row "
                    "ORDER BY to_jsonb(source_row)::text")
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for row in rows:
                        value = row["row_json"] if isinstance(row, dict) else row[0]
                        digest.update(str(value).encode() + b"\n")
                        count += 1
            results.append({"table": table, "status": "captured", "row_count": count,
                            "content_sha256": digest.hexdigest()})
        except Exception as exc:
            conn.rollback()
            results.append({"table": table, "status": "unavailable", "row_count": None,
                            "content_sha256": None,
                            "error": f"{type(exc).__name__}: {exc}"})
    return results


def release_snapshot(conn, release_id: str) -> dict[str, Any]:
    """Capture comparable semantics and exact run diagnostics for one release."""
    release = conn.execute(
        "SELECT r.release_id, r.manifest_json, r.manifest_sha256, r.code_commit, r.created_at, "
        "r.status, (SELECT run.status FROM analysis_runs run WHERE run.release_id = r.release_id "
        "ORDER BY run.updated_at DESC LIMIT 1) AS run_status "
        "FROM analysis_releases r WHERE r.release_id = %s", (release_id,)).fetchone()
    if release is None:
        raise KeyError(release_id)
    if release["run_status"] != "complete":
        raise ValueError("acceptance capture requires a completed release")
    final_manifest = conn.execute(
        "SELECT release_manifest_id, manifest_sha256, output_sha256 FROM release_manifests "
        "WHERE release_id = %s AND release_kind = 'analytical' ORDER BY created_at DESC LIMIT 1",
        (release_id,)).fetchone()
    if final_manifest is None:
        raise ValueError("acceptance capture requires a sealed analytical manifest")

    release_data = dict(release)
    plan = _parse_json(release_data.pop("manifest_json"), {})
    source_digests = _source_digests(conn, plan.get("domains") or [])
    inputs = _normalise(conn.execute(
        "SELECT domain_id, source_tables_json, input_count, ordered_input_sha256, "
        "configuration_sha256, prefilter_version, prefilter_result_sha256, suppression_enabled, "
        "candidate_count, output_sha256, status "
        "FROM analysis_input_manifests WHERE release_id = %s ORDER BY domain_id",
        (release_id,)).fetchall(), omit=set())
    signal_rows = _normalise(conn.execute(
        "SELECT domain_id, taxonomy_namespace, signal_type, subject_type, subject_id, direction, "
        "assertion_status, period_start, period_end, evidence_refs_json, derivation_method, "
        "confidence_contract_json, human_verified FROM automated_signals WHERE release_id = %s "
        "ORDER BY created_at, signal_id", (release_id,)).fetchall(), omit=set())
    # A stable semantic key lets verifier/link parity survive different release
    # IDs while retaining every field that affects a displayed signal.
    signal_key_rows = conn.execute(
        "SELECT signal_id, domain_id, taxonomy_namespace, signal_type, subject_type, subject_id, "
        "direction, assertion_status, period_start, period_end, evidence_refs_json, "
        "derivation_method, confidence_contract_json, human_verified "
        "FROM automated_signals WHERE release_id = %s ORDER BY created_at, signal_id",
        (release_id,)).fetchall()
    signal_keys = {
        row["signal_id"]: _digest(_normalise([row], omit={"signal_id"})[0])
        for row in signal_key_rows
    }
    signal_order = {row["signal_id"]: ordinal
                    for ordinal, row in enumerate(signal_key_rows)}
    theme_rows = _normalise(conn.execute(
        "SELECT domain_id, theme_key, status, passage_count, document_count, subject_count, "
        "novelty_similarity, evidence_json, promotion_reason FROM emerging_themes "
        "WHERE release_id = %s ORDER BY created_at, theme_id", (release_id,)).fetchall(), omit=set())
    topic_rows = _normalise(conn.execute(
        "SELECT domain_id, topic_number, label, novelty_similarity, outlier, representative_json "
        "FROM analysis_topics WHERE release_id = %s ORDER BY domain_id, topic_number, topic_id",
        (release_id,)).fetchall(), omit=set())
    verifier_rows = []
    for raw in conn.execute(
            "SELECT v.signal_id, v.verifier_name, v.passed, v.score, v.reasons_json "
            "FROM analysis_verifier_results v JOIN automated_signals a ON a.signal_id = v.signal_id "
            "WHERE a.release_id = %s ORDER BY a.created_at, a.signal_id, v.verifier_name, "
            "v.verifier_result_id", (release_id,)).fetchall():
        row = _normalise([raw], omit={"signal_id"})[0]
        row["signal_key"] = signal_keys.get(raw["signal_id"])
        row["signal_ordinal"] = signal_order.get(raw["signal_id"])
        verifier_rows.append(row)
    verifier_rows.sort(key=lambda row: (
        row["signal_ordinal"], row["verifier_name"], _canonical(row)))
    link_rows = []
    for raw in conn.execute(
            "SELECT left_signal_id, right_signal_id, relationship_type, subject_type, subject_id, "
            "period_start, period_end, join_reason_json, explanation "
            "FROM cross_source_signal_links WHERE release_id = %s "
            "ORDER BY left_signal_id, right_signal_id, relationship_type", (release_id,)).fetchall():
        row = _normalise([raw], omit={"left_signal_id", "right_signal_id"})[0]
        row["left_signal_key"] = signal_keys.get(raw["left_signal_id"])
        row["right_signal_key"] = signal_keys.get(raw["right_signal_id"])
        row["left_signal_ordinal"] = signal_order.get(raw["left_signal_id"])
        row["right_signal_ordinal"] = signal_order.get(raw["right_signal_id"])
        link_rows.append(row)
    link_rows.sort(key=lambda row: (
        row["left_signal_ordinal"], row["right_signal_ordinal"],
        row["relationship_type"], _canonical(row)))
    audit_rows = _normalise(conn.execute(
        "SELECT domain_id, model_id, provider_id, prompt_sha256, request_sha256, "
        "response_cache_key, cached, cost_micros, retry_count, status_code, status, error_detail "
        "FROM analysis_model_calls WHERE release_id = %s "
        "ORDER BY domain_id, window_id, request_sha256, prompt_sha256, status, model_id, model_call_id",
        (release_id,)).fetchall(), omit={"cost_micros", "cached"})
    cost = conn.execute(
        "SELECT COUNT(*) AS calls, COUNT(*) FILTER (WHERE cached = 1) AS cache_hits, "
        "COUNT(*) FILTER (WHERE cached = 0) AS billed_calls, "
        "COALESCE(SUM(cost_micros) FILTER (WHERE cached = 0), 0) AS cost_micros "
        "FROM analysis_model_calls WHERE release_id = %s", (release_id,)).fetchone()
    indexes = [dict(row) for row in conn.execute(
        "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname IN ('ix_analysis_candidates_pending', "
        "'ix_automated_signals_link_candidates', 'ux_analysis_health_release_source') "
        "ORDER BY indexname").fetchall()]
    sections = {
        "inputs": _section(inputs, ordered=True),
        "signals": _section(signal_rows, ordered=True),
        "themes": _section(theme_rows, ordered=True),
        "topics": _section(topic_rows, ordered=True),
        "verifiers": _section(verifier_rows, ordered=True),
        "links": _section(link_rows, ordered=True),
        "model_audits": _section(audit_rows, ordered=True),
    }
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "release": release_data,
        "source_digests": source_digests,
        "dataset_digest": _digest({
            "source_tables": source_digests,
            "narrative_inputs": [
                {key: row.get(key) for key in (
                    "domain_id", "source_tables_json", "input_count", "ordered_input_sha256")}
                for row in inputs
            ],
        }),
        "sections": sections,
        "diagnostics": {
            "model_calls": int(cost["calls"]), "cache_hits": int(cost["cache_hits"]),
            "billed_calls": int(cost["billed_calls"]), "cost_micros": int(cost["cost_micros"]),
        },
        "required_indexes": indexes,
        "final_manifest": dict(final_manifest) if final_manifest else None,
        "snapshot_digest": _digest(sections),
    }


def compare_snapshots(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compare same-dataset correctness while reporting expected audit reductions."""
    source_lists = [report.get("source_digests", []) for report in (baseline, candidate)]
    source_capture_complete = all(source_lists) and all(
        item.get("status") == "captured"
        for items in source_lists for item in items)
    same_dataset = (source_capture_complete and
                    baseline.get("dataset_digest") == candidate.get("dataset_digest"))
    names = sorted(set(baseline.get("sections", {})) | set(candidate.get("sections", {})))
    sections = {}
    for name in names:
        left = baseline.get("sections", {}).get(name, {})
        right = candidate.get("sections", {}).get(name, {})
        sections[name] = {
            "count_equal": left.get("count") == right.get("count"),
            "set_equal": left.get("digest") == right.get("digest"),
            "order_equal": left.get("ordered_digest") == right.get("ordered_digest"),
            "baseline_count": left.get("count"), "candidate_count": right.get("count"),
        }
    parity = same_dataset and all(
        value["count_equal"] and value["set_equal"] and value["order_equal"]
        for name, value in sections.items() if name in CORRECTNESS_SECTIONS)
    before_diagnostics = baseline.get("diagnostics", {})
    after_diagnostics = candidate.get("diagnostics", {})
    result = {"comparison_version": SNAPSHOT_VERSION,
              "source_capture_complete": source_capture_complete,
              "same_dataset": same_dataset,
              "parity_passed": parity, "sections": sections,
              "correctness_sections": sorted(CORRECTNESS_SECTIONS),
              "diagnostic_deltas": {
                  key: (after_diagnostics.get(key) - before_diagnostics.get(key)
                        if isinstance(after_diagnostics.get(key), (int, float)) and
                        isinstance(before_diagnostics.get(key), (int, float)) else None)
                  for key in sorted(set(before_diagnostics) | set(after_diagnostics))
              },
              "baseline_snapshot_digest": baseline.get("snapshot_digest"),
              "candidate_snapshot_digest": candidate.get("snapshot_digest")}
    result["comparison_digest"] = _digest(result)
    return result


class _SQLCounts:
    def __init__(self) -> None:
        self.execute_calls = 0
        self.executemany_calls = 0
        self.executemany_rows = 0
        self._lock = threading.Lock()

    def add_execute(self) -> None:
        with self._lock:
            self.execute_calls += 1

    def add_many(self, rows: int) -> None:
        with self._lock:
            self.executemany_calls += 1
            self.executemany_rows += rows


class _CountingConnection:
    def __init__(self, connection, counts: _SQLCounts) -> None:
        self._connection = connection
        self._counts = counts

    def execute(self, sql, params=None):
        self._counts.add_execute()
        return self._connection.execute(sql, params)

    def executemany(self, sql, params_seq):
        params = list(params_seq)
        self._counts.add_many(len(params))
        return self._connection.executemany(sql, params)

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


def _rss_bytes() -> int | None:
    if resource is None:
        return None
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (AttributeError, OSError):
        return None
    # Linux reports KiB; macOS reports bytes.
    return int(value if platform.system() == "Darwin" else value * 1024)


def benchmark_once(settings: Any, *, batch_size: int = 100,
                   worker_id: str = "phase2-acceptance") -> dict[str, Any]:
    """Instrument exactly one queued worker run using client-observable metrics."""
    from pipeline.analysis.worker import AnalysisWorker

    counts = _SQLCounts()
    original = db.get_connection

    def measured_connection(current_settings):
        return _CountingConnection(original(current_settings), counts)

    already_tracing = tracemalloc.is_tracing()
    if not already_tracing:
        tracemalloc.start()
    tracemalloc.reset_peak()
    rss_before = _rss_bytes()
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    db.get_connection = measured_connection
    result = None
    failure = None
    try:
        result = AnalysisWorker(
            settings, batch_size=batch_size, worker_id=worker_id).run_once()
    except Exception as exc:
        failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        db.get_connection = original
        wall_seconds = time.perf_counter() - wall_started
        cpu_seconds = time.process_time() - cpu_started
        _current, traced_peak = tracemalloc.get_traced_memory()
        if not already_tracing:
            tracemalloc.stop()
    rss_after = _rss_bytes()
    report = {
        "benchmark_version": SNAPSHOT_VERSION,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": code_commit(), "batch_size": batch_size,
        "worker_result": result or {"status": "idle"},
        "failure": failure,
        "wall_seconds": round(wall_seconds, 6), "cpu_seconds": round(cpu_seconds, 6),
        "python_peak_traced_bytes": int(traced_peak),
        "process_peak_rss_before_bytes": rss_before,
        "process_peak_rss_after_bytes": rss_after,
        "client_sql_execute_calls": counts.execute_calls,
        "client_sql_executemany_calls": counts.executemany_calls,
        "client_sql_executemany_rows": counts.executemany_rows,
        "measurement_notes": {
            "python_peak_traced_bytes": "Python allocator peak during this command only.",
            "process_peak_rss": "Process high-water marks; after-minus-before is not allocated memory.",
            "client_sql": "Client API calls, not PostgreSQL server statement execution counts.",
        },
    }
    if failure:
        report["status"] = "failed"
    else:
        report["status"] = "measured" if result else "idle"
    report["benchmark_digest"] = _digest(report)
    return report


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
