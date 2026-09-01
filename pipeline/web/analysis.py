"""Admin-only read model and controls for the analysis control plane."""
from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from pipeline.analysis import domains, releases
from pipeline.analysis.operations import utcnow
from pipeline.analysis.store import list_signals


def _limit(value: Any, default: int = 100) -> int:
    try:
        return max(1, min(int(value), 500))
    except (TypeError, ValueError):
        return default


_ACTIVE_RUN_STATUSES = {"queued", "running", "paused", "cancelling"}
_TERMINAL_RUN_STATUSES = {"cancelled", "complete", "failed", "interrupted"}
_RUN_KINDS = {"discovery", "optimization", "pilot", "complete"}


def worker_status(conn, *, max_age_seconds: int = 30) -> dict[str, Any]:
    row = conn.execute(
        "SELECT worker_id, last_seen_at, status, version FROM analysis_worker_heartbeats "
        "ORDER BY last_seen_at DESC LIMIT 1").fetchone()
    if row is None:
        return {"online": False, "worker_id": None, "last_seen_at": None,
                "status": "not_seen", "version": None}
    try:
        seen = datetime.fromisoformat(row["last_seen_at"])
        age = (datetime.now(timezone.utc) - seen).total_seconds()
    except (TypeError, ValueError):
        age = max_age_seconds + 1
    return {"online": age <= max_age_seconds, "worker_id": row["worker_id"],
            "last_seen_at": row["last_seen_at"], "status": row["status"],
            "version": row["version"], "age_seconds": round(max(0, age), 1)}


def _cost_snapshot(conn, release_id: str, run_id: str | None = None) -> dict[str, int]:
    clause = "release_id = ?"
    params: list[Any] = [release_id]
    if run_id:
        clause += " AND run_id = ?"
        params.append(run_id)
    row = conn.execute(
        "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_micros), 0) AS cost_micros "
        f"FROM analysis_model_calls WHERE {clause}", params).fetchone()
    if run_id:
        run = conn.execute("SELECT cost_micros FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
        return {"model_calls": int(row["calls"]),
                "cost_micros": int(run["cost_micros"] if run else row["cost_micros"] or 0)}
    return {"model_calls": int(row["calls"]), "cost_micros": int(row["cost_micros"] or 0)}


def _estimate_run(conn, selected: list[str]) -> tuple[int | None, int | None]:
    """Forecast two model calls per available source row.

    This is deliberately a forecast, not a claim about work completed. A
    missing source table contributes nothing, and cost is only projected when
    the warehouse has a historical model-call rate to use.
    """
    source_rows = 0
    for domain_id in selected:
        spec = domains.get_domain(domain_id)
        for table in spec.source_tables:
            try:
                source_rows += int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except Exception:
                continue
    if not source_rows:
        return None, None
    calls = source_rows * 2
    average = conn.execute(
        "SELECT AVG(cost_micros) FROM analysis_model_calls WHERE cost_micros IS NOT NULL"
    ).fetchone()[0]
    return calls, round(calls * float(average)) if average is not None else None


def _run_summary(conn, run_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM analysis_runs WHERE run_id = ?", (run_id,)).fetchone()
    if row is None:
        raise KeyError(run_id)
    item = dict(row)
    item["requested_domains"] = json.loads(item.pop("requested_domains_json") or "[]")
    domains_rows = conn.execute(
        "SELECT domain_run_id, domain_id, status, prerequisite_status, "
        "missing_tables_json, rows_processed, rows_written, started_at, "
        "completed_at, error_detail FROM analysis_domain_runs "
        "WHERE run_id = ? ORDER BY domain_id", (run_id,)).fetchall()
    domain_items = []
    for domain_row in domains_rows:
        domain = dict(domain_row)
        domain["missing_tables"] = json.loads(domain.pop("missing_tables_json") or "[]")
        domain_items.append(domain)
    counts = Counter(domain["status"] for domain in domain_items)
    item["domains"] = domain_items
    item["domain_counts"] = dict(counts)
    item["completed_domains"] = sum(counts.get(status, 0) for status in ("complete", "unavailable"))
    item.update(_cost_snapshot(conn, item["release_id"], item["run_id"]))
    item["progress_percent"] = round(
        100 * item["completed_domains"] / item["total_domains"], 1
    ) if item["total_domains"] else 0
    item["worker"] = worker_status(conn)
    item["control_plane_only"] = not item["worker"]["online"]
    return item


def runs(conn, *, limit: int = 20) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT run_id FROM analysis_runs ORDER BY updated_at DESC LIMIT ?", (_limit(limit, 20),)
    ).fetchall()
    return {"runs": [_run_summary(conn, row["run_id"]) for row in rows]}


def run(conn, run_id: str) -> dict[str, Any]:
    return _run_summary(conn, run_id)


def domains_view(conn) -> dict[str, Any]:
    runs = {row["domain_id"]: dict(row) for row in conn.execute(
        "SELECT domain_id, status, prerequisite_status, missing_tables_json, rows_processed, rows_written "
        "FROM analysis_domain_runs WHERE domain_run_id IN (SELECT MAX(domain_run_id) FROM analysis_domain_runs GROUP BY domain_id)")}
    result = []
    for domain_id, spec in domains.domain_registry().items():
        row = runs.get(domain_id, {})
        result.append({"domain_id": domain_id, "taxonomy_namespace": spec.taxonomy_namespace,
                       "source_tables": list(spec.source_tables), "analysis_unit": spec.analysis_unit,
                       "status": row.get("status", "not_started"),
                       "prerequisite_status": row.get("prerequisite_status", "ready"),
                       "missing_tables": json.loads(row.get("missing_tables_json", "[]")),
                       "rows_processed": row.get("rows_processed", 0), "rows_written": row.get("rows_written", 0)})
    return {"domains": result}


def overview(conn) -> dict[str, Any]:
    release = conn.execute("SELECT release_id, status, created_at, activated_at FROM analysis_releases ORDER BY created_at DESC LIMIT 1").fetchone()
    counts = {}
    for table in ("automated_signals", "structured_signals", "emerging_themes", "cross_source_signal_links", "adaptation_proposals"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    latest_run = conn.execute("SELECT run_id FROM analysis_runs ORDER BY updated_at DESC LIMIT 1").fetchone()
    worker = worker_status(conn)
    return {"active_release": dict(release) if release else None, "counts": counts,
            "domains": domains_view(conn)["domains"],
            "latest_run": _run_summary(conn, latest_run["run_id"]) if latest_run else None,
            "executor": "worker_online" if worker["online"] else
            ("worker_offline" if worker["worker_id"] else "control_plane_only"),
            "worker": worker,
            "quality_boundary": "Automated signals are admin-only and human_verified is always false."}


def coverage(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT domain_id, COUNT(*) AS signals, COUNT(DISTINCT subject_id) AS subjects FROM automated_signals GROUP BY domain_id ORDER BY domain_id").fetchall()
    return {"coverage": [dict(row) for row in rows]}


def structured(conn, *, release_id: str | None = None, domain_id: str | None = None,
               limit: int = 100) -> dict[str, Any]:
    where, params = [], []
    if release_id:
        where.append("a.release_id = ?")
        params.append(release_id)
    if domain_id:
        where.append("s.domain_id = ?")
        params.append(domain_id)
    params.append(_limit(limit))
    sql = "SELECT s.*, a.domain_id, a.subject_id, a.direction FROM structured_signals s JOIN automated_signals a ON a.signal_id = s.signal_id"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.created_at DESC LIMIT ?"
    return {"structured": [dict(row) for row in conn.execute(sql, params)]}


def topics(conn, *, release_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    where, params = [], []
    if release_id:
        where.append("release_id = ?")
        params.append(release_id)
    params.append(_limit(limit))
    sql = "SELECT * FROM analysis_topics" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY created_at DESC LIMIT ?"
    return {"topics": [dict(row) for row in conn.execute(sql, params)]}


def themes(conn, *, release_id: str | None = None, status: str | None = None,
           limit: int = 100) -> dict[str, Any]:
    where, params = [], []
    if release_id:
        where.append("release_id = ?")
        params.append(release_id)
    if status:
        where.append("status = ?")
        params.append(status)
    params.append(_limit(limit))
    sql = "SELECT * FROM emerging_themes" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY created_at DESC LIMIT ?"
    return {"themes": [dict(row) for row in conn.execute(sql, params)]}


def entities(conn, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
    where, params = [], []
    if status:
        where.append("status = ?")
        params.append(status)
    params.append(_limit(limit))
    sql = "SELECT * FROM entity_link_suggestions" + ((" WHERE " + " AND ".join(where)) if where else "") + " ORDER BY created_at DESC LIMIT ?"
    return {"entities": [dict(row) for row in conn.execute(sql, params)]}


def graph(conn) -> dict[str, Any]:
    run = conn.execute("SELECT * FROM signal_graph_projection_runs ORDER BY started_at DESC LIMIT 1").fetchone()
    pending = conn.execute("SELECT COUNT(*) FROM signal_graph_projection_queue WHERE processed_at IS NULL").fetchone()[0]
    return {"projection": dict(run) if run else None, "pending": pending,
            "labels": ["AutomatedSignal", "StructuredSignal", "EmergingTheme", "AnalysisRelease"],
            "canonical_claim_isolation": True}


def models(conn) -> dict[str, Any]:
    return {"releases": [dict(row) for row in conn.execute("SELECT release_id, manifest_sha256, code_commit, created_at, status FROM analysis_releases ORDER BY created_at DESC LIMIT 20")],
            "programs": [dict(row) for row in conn.execute("SELECT * FROM analysis_program_versions ORDER BY created_at DESC LIMIT 100")]}


def operations(conn) -> dict[str, Any]:
    return {"health": [dict(row) for row in conn.execute("SELECT * FROM analysis_health_snapshots ORDER BY collected_at DESC LIMIT 100")],
            "proposals": [dict(row) for row in conn.execute("SELECT * FROM adaptation_proposals ORDER BY created_at DESC LIMIT 100")],
            **runs(conn)}


def report(conn, release_id: str) -> dict[str, Any]:
    manifest = releases.load_release(conn, release_id)
    if manifest is None:
        raise KeyError(f"unknown analysis release {release_id!r}")
    return {"release_manifest": manifest, "domains": domains_view(conn),
            "signals": list_signals(conn, release_id=release_id),
            "structured": structured(conn, release_id=release_id)["structured"],
            "links": {"links": [dict(row) for row in conn.execute("SELECT * FROM cross_source_signal_links WHERE release_id = ?", (release_id,))]},
            "themes": themes(conn, release_id=release_id)["themes"], "operations": operations(conn)}


def start_run(conn, settings, body: dict[str, Any]) -> dict[str, Any]:
    requested = body.get("domains")
    if requested is not None and (not isinstance(requested, list) or not all(isinstance(x, str) for x in requested)):
        raise ValueError("domains must be a list of domain ids")
    if requested == []:
        raise ValueError("select at least one analysis domain")
    run_kind = str(body.get("run_kind") or "complete")
    if run_kind not in _RUN_KINDS:
        raise ValueError(f"run_kind must be one of {sorted(_RUN_KINDS)}")
    try:
        ceiling = max(0, int(body.get("cost_ceiling_micros") or 0))
    except (TypeError, ValueError):
        raise ValueError("cost_ceiling_micros must be a non-negative integer") from None
    active = conn.execute(
        "SELECT run_id FROM analysis_runs WHERE status IN (?, ?, ?, ?) "
        "ORDER BY updated_at DESC LIMIT 1", tuple(_ACTIVE_RUN_STATUSES)
    ).fetchone()
    if active:
        raise ValueError(f"analysis run {active['run_id']} is already active")
    selected = requested or sorted(domains.domain_registry())
    run_id = f"analysis-run-{uuid.uuid4()}"
    now = utcnow()
    estimated_calls = body.get("estimated_calls")
    estimated_cost = body.get("estimated_cost_micros")
    if estimated_calls is None or estimated_cost is None:
        forecast_calls, forecast_cost = _estimate_run(conn, selected)
        estimated_calls = estimated_calls if estimated_calls is not None else forecast_calls
        estimated_cost = estimated_cost if estimated_cost is not None else forecast_cost
    manifest = releases.create_release(
        conn, settings, domains=selected,
        config={"run_kind": run_kind, "cost_ceiling_micros": ceiling,
                "estimated_calls": estimated_calls, "estimated_cost_micros": estimated_cost})
    conn.execute(
        "INSERT INTO analysis_runs (run_id, release_id, run_kind, status, "
        "requested_domains_json, total_domains, estimated_calls, estimated_cost_micros, "
        "cost_ceiling_micros, started_at, updated_at) VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)",
        (run_id, manifest["release_id"], run_kind, json.dumps(selected), len(selected),
         estimated_calls, estimated_cost, ceiling, now, now))
    for domain_id in manifest["domains"]:
        conn.execute(
            "INSERT INTO analysis_domain_runs (domain_run_id, run_id, release_id, domain_id, status, started_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?)",
            (f"domain-run-{uuid.uuid4()}", run_id, manifest["release_id"], domain_id, now))
    conn.commit()
    return {**_run_summary(conn, run_id), "release_manifest": manifest}


def cancel_run(conn, run_id: str) -> dict[str, Any]:
    item = _run_summary(conn, run_id)
    if item["status"] in _TERMINAL_RUN_STATUSES:
        raise ValueError(f"analysis run {run_id} is already {item['status']}")
    now = utcnow()
    conn.execute(
        "UPDATE analysis_runs SET status = 'cancelled', current_stage = 'cancelled', "
        "cancelled_at = ?, completed_at = ?, updated_at = ? WHERE run_id = ?",
        (now, now, now, run_id))
    conn.execute(
        "UPDATE analysis_domain_runs SET status = 'cancelled' "
        "WHERE run_id = ? AND status NOT IN ('complete', 'unavailable')", (run_id,))
    conn.commit()
    return _run_summary(conn, run_id)


def resume_run(conn, run_id: str) -> dict[str, Any]:
    item = _run_summary(conn, run_id)
    if item["status"] not in {"cancelled", "paused", "failed", "interrupted"}:
        raise ValueError(f"analysis run {run_id} cannot resume from {item['status']}")
    now = utcnow()
    conn.execute(
        "UPDATE analysis_runs SET status = 'queued', current_stage = 'queued', "
        "cancelled_at = NULL, completed_at = NULL, error_detail = NULL, updated_at = ? "
        "WHERE run_id = ?", (now, run_id))
    conn.execute(
        "UPDATE analysis_domain_runs SET status = 'pending', error_detail = NULL "
        "WHERE run_id = ? AND status NOT IN ('complete', 'unavailable')", (run_id,))
    conn.commit()
    return _run_summary(conn, run_id)


def activate(conn, release_id: str) -> dict[str, Any]:
    manifest = releases.load_release(conn, release_id)
    if manifest is None:
        raise KeyError(release_id)
    if set(manifest.get("domains", [])) != set(domains.domain_registry()):
        raise ValueError("only a complete all-domain release can be activated")
    incomplete = conn.execute("SELECT COUNT(*) FROM analysis_domain_runs WHERE release_id = ? AND status NOT IN ('complete', 'unavailable')", (release_id,)).fetchone()[0]
    if incomplete:
        raise ValueError("a release may activate only when every registered domain is complete or unavailable")
    conn.execute("UPDATE analysis_releases SET status = 'inactive' WHERE status = 'active'")
    conn.execute("UPDATE analysis_releases SET status = 'active', activated_at = ? WHERE release_id = ?", (utcnow(), release_id))
    conn.commit()
    return {"release_id": release_id, "status": "active"}


def rollback(conn, release_id: str, reason: str | None = None) -> dict[str, Any]:
    if releases.load_release(conn, release_id) is None:
        raise KeyError(release_id)
    conn.execute("UPDATE analysis_releases SET status = 'rolled_back', rolled_back_at = ?, rollback_reason = ? WHERE release_id = ?", (utcnow(), reason, release_id))
    conn.commit()
    return {"release_id": release_id, "status": "rolled_back"}


def promote_theme(conn, theme_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT status FROM emerging_themes WHERE theme_id = ?", (theme_id,)).fetchone()
    if row is None:
        raise KeyError(theme_id)
    if row["status"] != "promotion_ready":
        raise ValueError("theme is not promotion_ready")
    conn.execute("UPDATE emerging_themes SET status = 'promoted', promoted_at = ? WHERE theme_id = ?", (utcnow(), theme_id))
    conn.commit()
    return {"theme_id": theme_id, "status": "promoted"}
