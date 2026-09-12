"""Recording that a source was attempted, independent of what it found.

A row in an evidence table answers "what did we get." Nothing answered "did
we even look, and if we looked and got nothing, was that the source having
nothing or the source being unreachable" -- see migration 0103's comment.
Absence collapsing those cases is exactly what docs/CAVEATS.md forbids
concluding from, so this module exists to keep them apart.

Granularity is one attempt per (module, run) today, recorded around
`runner.execute_module`. A module that itself walks many pages/authorities
per run may open finer-grained attempts of its own (see
`pipeline/modules/m01_procurement.py`) by calling `collection_attempt`
directly with a narrower `scope`; nothing here requires every module to.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator


def _now():
    return datetime.now(timezone.utc)


def start_attempt(conn, *, module: str, source_system: str, scope: str,
                   run_id: str | None = None) -> int:
    row = conn.execute(
        "INSERT INTO collection_attempts (module, run_id, source_system, scope, started_at, status) "
        "VALUES (%s, %s, %s, %s, %s, 'running') RETURNING attempt_id",
        (module, run_id, source_system, scope, _now()),
    ).fetchone()
    return row["attempt_id"]


def finish_attempt(conn, attempt_id: int, *, status: str, result_count: int | None = None,
                    failure_class: str | None = None, coverage_state: str | None = None,
                    detail: dict | None = None) -> None:
    import json
    conn.execute(
        "UPDATE collection_attempts SET finished_at=%s, status=%s, result_count=%s, "
        "failure_class=%s, coverage_state=%s, detail_json=%s::jsonb WHERE attempt_id=%s",
        (_now(), status, result_count, failure_class, coverage_state,
         json.dumps(detail or {}, sort_keys=True, default=str), attempt_id),
    )


class Attempt:
    """What a caller fills in inside a `collection_attempt` block.

    `result_count`/`coverage_state`/`detail` default to values a plain
    "the call returned without raising" outcome would report; a caller with
    something more specific to say (zero results vs. genuinely unavailable)
    sets them before the block exits.
    """

    def __init__(self, attempt_id: int):
        self.attempt_id = attempt_id
        self.result_count: int | None = None
        self.coverage_state: str = "covered"
        self.failure_class: str | None = None
        self.detail: dict = {}


@contextmanager
def collection_attempt(conn, *, module: str, source_system: str, scope: str,
                        run_id: str | None = None) -> Iterator[Attempt]:
    """Bracket one collection attempt, recording success or failure either way.

    An exception inside the block is recorded (`status="failed"`) and
    re-raised unchanged -- this brackets bookkeeping, it does not swallow
    failures a caller needs to see.
    """
    attempt_id = start_attempt(conn, module=module, source_system=source_system,
                                scope=scope, run_id=run_id)
    attempt = Attempt(attempt_id)
    try:
        yield attempt
    except BaseException as exc:
        finish_attempt(conn, attempt_id, status="failed",
                        result_count=attempt.result_count,
                        failure_class=type(exc).__name__,
                        coverage_state="failed", detail=attempt.detail)
        raise
    else:
        status = "empty" if attempt.coverage_state == "no_results" else "ok"
        finish_attempt(conn, attempt_id, status=status, result_count=attempt.result_count,
                        failure_class=attempt.failure_class,
                        coverage_state=attempt.coverage_state, detail=attempt.detail)
