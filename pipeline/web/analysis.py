"""Admin-only read model and controls for the analysis control plane."""
from __future__ import annotations

import json
import uuid
from typing import Any

from pipeline.analysis import domains, releases
from pipeline.analysis.operations import utcnow
from pipeline.analysis.store import list_signals


def _limit(value: Any, default: int = 100) -> int:
    try:
        return max(1, min(int(value), 500))
    except (TypeError, ValueError):
        return default


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
    return {"active_release": dict(release) if release else None, "counts": counts,
            "domains": domains_view(conn)["domains"],
            "quality_boundary": "Automated signals are admin-only and human_verified is always false."}


def coverage(conn) -> dict[str, Any]:
    rows = conn.execute("SELECT domain_id, COUNT(*) AS signals, COUNT(DISTINCT subject_id) AS subjects FROM automated_signals GROUP BY domain_id ORDER BY domain_id").fetchall()
    return {"coverage": [dict(row) for row in rows]}


def structured(conn, *, domain_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    where, params = [], []
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


def themes(conn, *, status: str | None = None, limit: int = 100) -> dict[str, Any]:
    where, params = [], []
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
            "proposals": [dict(row) for row in conn.execute("SELECT * FROM adaptation_proposals ORDER BY created_at DESC LIMIT 100")]}


def report(conn, release_id: str) -> dict[str, Any]:
    manifest = releases.load_release(conn, release_id)
    if manifest is None:
        raise KeyError(f"unknown analysis release {release_id!r}")
    return {"release_manifest": manifest, "domains": domains_view(conn),
            "signals": list_signals(conn, release_id=release_id),
            "structured": structured(conn)["structured"],
            "links": {"links": [dict(row) for row in conn.execute("SELECT * FROM cross_source_signal_links WHERE release_id = ?", (release_id,))]},
            "themes": themes(conn)["themes"], "operations": operations(conn)}


def start_run(conn, settings, body: dict[str, Any]) -> dict[str, Any]:
    requested = body.get("domains")
    if requested is not None and (not isinstance(requested, list) or not all(isinstance(x, str) for x in requested)):
        raise ValueError("domains must be a list of domain ids")
    manifest = releases.create_release(conn, settings, domains=requested, config={"cost_ceiling_micros": body.get("cost_ceiling_micros", 0)})
    for domain_id in manifest["domains"]:
        conn.execute("INSERT INTO analysis_domain_runs (domain_run_id, release_id, domain_id, status, started_at) VALUES (?, ?, ?, 'pending', ?)", (f"domain-run-{uuid.uuid4()}", manifest["release_id"], domain_id, utcnow()))
    conn.commit()
    return manifest


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
