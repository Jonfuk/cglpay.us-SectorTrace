"""The unified home for irreducible bad items with nowhere else to live.

`review_queue` (a link needing a human judgement call) and `parse_failures`
(a field that would not parse) already work and stay exactly as they are --
this is not a migration of either. It closes the gap performance.md named
for three categories that had no durable, listable, retryable table at all:
a candidate a person rejected, an input a pipeline stage could not process,
and an archive object whose stored hash no longer matches its bytes.

Bounded retry only. Nothing here auto-promotes a quarantined item back into
evidence -- see CLAUDE.md's "nothing is promoted without a person" and
`pipeline/promote.py`, whose trigger-enforced rule this does not touch.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pipeline import telemetry

_KINDS = {"rejected_candidate", "failed_stage_input", "archive_mismatch"}


def _now():
    return datetime.now(timezone.utc)


def quarantine(conn, *, kind: str, module: str, item_identity: str, failure_class: str,
               reason: str, run_id: str | None = None, stage: str | None = None,
               input_sha256: str | None = None, output_sha256: str | None = None,
               payload: dict | None = None) -> int:
    """Idempotent: re-observing the same (kind, module, item_identity) updates
    last_seen_at/reason/run_id rather than appending another copy, matching
    `db.record_parse_failure`'s idiom (migration 0007) -- see 0103's index.
    A row already marked resolved is left alone, the same protection
    `record_review_item` gives a decided review item.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown quarantine kind {kind!r}; expected one of {sorted(_KINDS)}")
    now = _now()
    # A span correlated by `run_id` (performance.md:632's "quarantine
    # identifiers") -- `item_identity`, `reason` and `payload` never become
    # attributes here even though they are already in `conn`'s query
    # parameters above: they carry whatever the caller is quarantining (a
    # candidate's name, a rejected value, a URL), which is exactly the
    # source-shaped content this pipeline's telemetry must never export.
    with telemetry.span("quarantine.record", kind=kind, module=module,
                        failure_class=failure_class, run_id=run_id, stage=stage) as record_span:
        row = conn.execute(
            "INSERT INTO quarantine_items (kind, module, run_id, stage, item_identity, failure_class, "
            "reason, input_sha256, output_sha256, payload_json, first_seen_at, last_seen_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s) "
            "ON CONFLICT (kind, module, item_identity) DO UPDATE SET "
            "run_id=excluded.run_id, stage=excluded.stage, failure_class=excluded.failure_class, "
            "reason=excluded.reason, input_sha256=excluded.input_sha256, "
            "output_sha256=excluded.output_sha256, payload_json=excluded.payload_json, "
            "last_seen_at=excluded.last_seen_at "
            "WHERE quarantine_items.retry_state <> 'resolved' "
            "RETURNING item_id",
            (kind, module, run_id, stage, item_identity, failure_class, reason,
             input_sha256, output_sha256, json.dumps(payload or {}, sort_keys=True, default=str),
             now, now),
        ).fetchone()
        if row is not None:
            telemetry.counter(
                "quarantine.items",
                description="Items newly quarantined or re-observed, by kind.").add(1, {"kind": kind})
            record_span.set_attribute("item_id", row["item_id"])
            return row["item_id"]
        # Already resolved: return its existing id without touching it.
        existing = conn.execute(
            "SELECT item_id FROM quarantine_items WHERE kind=%s AND module=%s AND item_identity=%s",
            (kind, module, item_identity),
        ).fetchone()
        record_span.set_attribute("item_id", existing["item_id"])
        record_span.set_attribute("already_resolved", True)
        return existing["item_id"]


def list_items(conn, *, kind: str | None = None, module: str | None = None,
               retry_state: str | None = None, limit: int = 100, cursor: int = 0) -> list[dict]:
    """Bounded listing, newest-identity-first id order. `cursor` is the last
    `item_id` seen; pass it back to page without re-listing what's already
    been looked at."""
    clauses, params = ["item_id > %s"], [cursor]
    if kind is not None:
        clauses.append("kind = %s")
        params.append(kind)
    if module is not None:
        clauses.append("module = %s")
        params.append(module)
    if retry_state is not None:
        clauses.append("retry_state = %s")
        params.append(retry_state)
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM quarantine_items WHERE {' AND '.join(clauses)} "
        f"ORDER BY item_id LIMIT %s", params,
    ).fetchall()
    return [dict(row) for row in rows]


def get_item(conn, item_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM quarantine_items WHERE item_id = %s", (item_id,)).fetchone()
    return dict(row) if row else None


def mark_retried(conn, item_id: int, *, outcome: str, resolved: bool = False) -> None:
    """Record one retry attempt. `outcome` is a short free-text note (the
    failure_class of the retry failure, or "ok"); it does not itself resolve
    the item -- pass `resolved=True` once the underlying cause is actually
    fixed, never as a side effect of merely trying again."""
    conn.execute(
        "UPDATE quarantine_items SET retry_count = retry_count + 1, "
        "retry_state = %s, resolved_at = %s, reason = reason || ' (retry: ' || %s || ')' "
        "WHERE item_id = %s",
        ("resolved" if resolved else "retrying", _now() if resolved else None,
         outcome, item_id),
    )
