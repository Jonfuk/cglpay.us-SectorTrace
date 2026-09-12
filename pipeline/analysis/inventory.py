"""Shared operational source snapshots for forecasts and health checks."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Iterable

from pipeline import operational_snapshots
from pipeline.catalog import quote


def _key(table: str) -> str:
    return f"analysis.source.{table}"


def table_snapshot(conn, table: str, *, max_age_seconds: int = 900,
                   refresh: bool = False) -> dict[str, Any]:
    if not refresh:
        existing = operational_snapshots.load(conn, _key(table), max_age_seconds=max_age_seconds)
        if existing and not existing["stale"]:
            return dict(existing["payload"])
    started = time.monotonic()
    conn.execute("SAVEPOINT analysis_inventory_probe")
    try:
        cursor = conn.execute(f"SELECT * FROM {quote(table)} LIMIT 0")
        description = getattr(cursor, "description", None) or []
        schema = {str(item[0]): str(item[1] or "unknown") for item in description}
        count = int(conn.execute(
            f"SELECT COUNT(*) AS count FROM {quote(table)}").fetchone()["count"])
        payload = {"table": table, "exists": True, "row_count": count,
                   "observed_schema": schema}
        conn.execute("RELEASE SAVEPOINT analysis_inventory_probe")
    except Exception as exc:  # missing/unreadable is an operational state, not zero
        conn.execute("ROLLBACK TO SAVEPOINT analysis_inventory_probe")
        conn.execute("RELEASE SAVEPOINT analysis_inventory_probe")
        payload = {"table": table, "exists": False, "row_count": None,
                   "observed_schema": {}, "error": f"{type(exc).__name__}: {exc}"}
    version = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    operational_snapshots.save(
        conn, _key(table), payload, source_version=version,
        duration_ms=(time.monotonic() - started) * 1000)
    return payload


def source_snapshot(conn, tables: Iterable[str], *, max_age_seconds: int = 900,
                    refresh: bool = False) -> dict[str, Any]:
    unique = sorted(set(tables))
    items = [table_snapshot(conn, table, max_age_seconds=max_age_seconds,
                            refresh=refresh) for table in unique]
    digest = hashlib.sha256(json.dumps(
        items, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"tables": items, "sha256": digest,
            "row_count": sum(int(item["row_count"] or 0) for item in items)}
