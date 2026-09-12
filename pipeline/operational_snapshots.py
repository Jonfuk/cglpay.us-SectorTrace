"""Durable latest-value snapshots for expensive operational calculations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_table(conn) -> None:
    """Probe migration 0094 without attempting DDL on reader connections."""
    conn.execute("SELECT 1 FROM operational_snapshots LIMIT 0")


def save(conn, key: str, payload: Any, *, source_version: str | None = None,
         duration_ms: float | None = None, stale: bool = False,
         refresh_error: str | None = None,
         captured_at: str | None = None) -> None:
    """Upsert the latest snapshot without creating a history table per panel."""
    _ensure_table(conn)
    conn.execute(
        "INSERT INTO operational_snapshots "
        "(snapshot_key, payload_json, captured_at, duration_ms, source_version, stale, refresh_error) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (snapshot_key) DO UPDATE SET "
        "payload_json = excluded.payload_json, captured_at = excluded.captured_at, "
        "duration_ms = excluded.duration_ms, source_version = excluded.source_version, "
        "stale = excluded.stale, refresh_error = excluded.refresh_error",
        (key, json.dumps(payload, sort_keys=True, default=str), captured_at or _now(),
         duration_ms, source_version, int(stale), refresh_error),
    )


def record_refresh_failure(conn, key: str, error: str) -> None:
    """Keep the last successful payload while marking its refresh as stale."""
    _ensure_table(conn)
    conn.execute(
        "UPDATE operational_snapshots SET stale = 1, refresh_error = %s "
        "WHERE snapshot_key = %s", (error[:2000], key))


def load(conn, key: str, *, max_age_seconds: int | float | None = None,
         now: datetime | None = None) -> dict[str, Any] | None:
    try:
        _ensure_table(conn)
    except Exception:
        # Portal connections are intentionally query-only. A pre-migration
        # read must remain useful even when it cannot create the optional
        # snapshot table.
        return None
    row = conn.execute(
        "SELECT snapshot_key, payload_json, captured_at, duration_ms, source_version, "
        "stale, refresh_error FROM operational_snapshots WHERE snapshot_key = %s", (key,)
    ).fetchone()
    if row is None:
        return None
    captured = row["captured_at"]
    age = None
    try:
        age = ((now or datetime.now(timezone.utc)) -
               datetime.fromisoformat(captured)).total_seconds()
    except (TypeError, ValueError):
        pass
    stale = bool(row["stale"])
    if max_age_seconds is not None and age is not None and age > max_age_seconds:
        stale = True
    return {
        "key": row["snapshot_key"],
        "payload": json.loads(row["payload_json"]),
        "captured_at": captured,
        "age_seconds": age,
        "duration_ms": row["duration_ms"],
        "source_version": row["source_version"],
        "stale": stale,
        "refresh_error": row["refresh_error"],
    }
