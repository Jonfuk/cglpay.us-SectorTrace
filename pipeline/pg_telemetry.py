"""PostgreSQL maintenance telemetry (performance.md "PostgreSQL maintenance").

That section is explicit that it wants *evidence before action*: table-specific
autovacuum/analyze thresholds only "after telemetry establishes update rates",
index changes only "after the telemetry observation period", and no global
memory or planner change "solely from configuration heuristics". Nothing in
this codebase captured that telemetry durably before this module — a live
`pg_stat_user_tables` query answers "what does it look like right now", not
"how did it change over the observation period", and the tables never persist
because they are dropped and rebuilt from autovacuum counters, not archived.

This module is capture only. It snapshots the three catalog views the
performance-review paragraph names — `pg_stat_user_tables`,
`pg_stat_user_indexes`, and, where installed, `pg_stat_statements` — into the
`pg_telemetry_*` tables (migration 0107), one row per object per snapshot, so
the update-rate and index-usage history the review depends on actually exists
when the observation period ends. It does not read its own output, does not
compute a threshold, and does not touch autovacuum settings, indexes, or
planner/memory configuration — that is deliberately future work, gated on
what the accumulated snapshots show.

`pg_stat_statements` needs `shared_preload_libraries` set at server start,
which is a restart the application cannot perform on itself (unlike pgvector/
pg_trgm/PostGIS, which `db.ensure_extensions` can `CREATE EXTENSION` on a live
server). docs/DEPLOYMENT.md already records it as "available and not
installed" on the live server. So that half of the capture feature-detects
via `db.has_extension` and is skipped with a structured log event rather than
attempted or treated as an error — see the module docstring on
`deploy/ansible/README.md`'s backup timer for the operational precondition an
operator needs to clear first: add `pg_stat_statements` to
`shared_preload_libraries`, restart PostgreSQL, then
`CREATE EXTENSION pg_stat_statements`.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog

from pipeline import db

log = structlog.get_logger()

# Bounds how many query fingerprints one snapshot writes when
# pg_stat_statements is installed. Not a tuning decision — this only bounds
# the *capture's own* storage growth, ranked by the metric the eventual index/
# query review actually cares about (performance.md: "execution counts, total
# time, I/O"). A warehouse running for months can accumulate far more distinct
# fingerprints than are useful to keep every snapshot; the top N by total
# execution time is what the review would look at first anyway.
STATEMENT_STATS_LIMIT = 500


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def capture_table_stats(conn: db.Connection) -> list[dict]:
    """One row per application table: the autovacuum/analyze counters a
    table-specific threshold decision needs, once enough snapshots exist to
    show an update rate.

    `current_schema()` scopes this to the application's own tables, the same
    boundary `catalog.list_objects` and `pg_capabilities` already use — never
    `pg_catalog`/`information_schema` themselves.
    """
    rows = conn.execute(
        "SELECT schemaname AS schema_name, relname AS table_name, "
        "       n_live_tup, n_dead_tup, n_mod_since_analyze, "
        "       last_autovacuum::text AS last_autovacuum, "
        "       last_analyze::text AS last_analyze, "
        "       autovacuum_count, analyze_count "
        "FROM pg_stat_user_tables "
        "WHERE schemaname = current_schema() "
        "ORDER BY relname"
    ).fetchall()
    return [dict(row) for row in rows]


def capture_index_stats(conn: db.Connection) -> list[dict]:
    """One row per application index: the usage counters an eventual index
    review reads (performance.md: "based on execution counts, ... rare
    operational jobs" — `idx_scan` at zero is what that already found once,
    in Phase 4's `docs/benchmarks/README.md`, without this table existing to
    remember it across a restart).
    """
    rows = conn.execute(
        "SELECT schemaname AS schema_name, relname AS table_name, "
        "       indexrelname AS index_name, "
        "       idx_scan, idx_tup_read, idx_tup_fetch "
        "FROM pg_stat_user_indexes "
        "WHERE schemaname = current_schema() "
        "ORDER BY relname, indexrelname"
    ).fetchall()
    return [dict(row) for row in rows]


def pg_stat_statements_available(conn: db.Connection) -> bool:
    """True when the extension is installed and its view can be queried.

    `pg_stat_statements` cannot be installed by `CREATE EXTENSION` alone the
    way pgvector/pg_trgm/PostGIS can — it needs
    `shared_preload_libraries='pg_stat_statements'` set before the server
    starts, an operational precondition this process cannot arrange for
    itself. `db.has_extension` is the same `pg_extension` lookup
    `ensure_extensions` uses for the mandatory three; here absence is
    expected and not fatal.
    """
    return db.has_extension(conn, "pg_stat_statements")


def capture_statement_stats(conn: db.Connection, limit: int = STATEMENT_STATS_LIMIT) -> list[dict]:
    """Top `limit` query fingerprints by total execution time, or `[]` if
    `pg_stat_statements` is not installed. Callers should check
    :func:`pg_stat_statements_available` first if they want to distinguish
    "not installed" from "installed but empty" for logging purposes; this
    function itself treats both the same way (returns `[]`) since either way
    there is nothing to persist.

    Query text is truncated defensively — pg_stat_statements normalises
    literals out under `pg_stat_statements.track=top` (performance.md Phase 0)
    but this capture makes no assumption about how the server is configured,
    and a snapshot table is not the place for an unbounded copy of SQL text.
    """
    if not pg_stat_statements_available(conn):
        return []
    rows = conn.execute(
        "SELECT queryid, "
        "       left(query, 4000) AS query_text, "
        "       calls, total_exec_time AS total_exec_time_ms, "
        "       rows, shared_blks_hit, shared_blks_read "
        "FROM pg_stat_statements "
        "WHERE queryid IS NOT NULL "
        "ORDER BY total_exec_time DESC "
        "LIMIT %s", (limit,)
    ).fetchall()
    return [dict(row) for row in rows]


def _persist_table_stats(conn: db.Connection, captured_at: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**row, "captured_at": captured_at} for row in rows]
    return db.upsert_many(
        conn, "pg_telemetry_table_stats", payload,
        natural_key=("captured_at", "schema_name", "table_name"))


def _persist_index_stats(conn: db.Connection, captured_at: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**row, "captured_at": captured_at} for row in rows]
    return db.upsert_many(
        conn, "pg_telemetry_index_stats", payload,
        natural_key=("captured_at", "schema_name", "table_name", "index_name"))


def _persist_statement_stats(conn: db.Connection, captured_at: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    payload = [{**row, "captured_at": captured_at} for row in rows]
    return db.upsert_many(
        conn, "pg_telemetry_statement_stats", payload,
        natural_key=("captured_at", "queryid"))


def snapshot(conn: db.Connection, *, captured_at: str | None = None) -> dict:
    """Capture and persist one telemetry snapshot. Returns row counts per
    table plus whether `pg_stat_statements` was available for this run.

    One `captured_at` timestamp ties all rows in the batch together, so a
    later query can ask "what did every table/index/statement look like at
    time T" rather than reconstructing a batch from independently-timed rows.
    Commits once, as one unit of work (settled decision 10) — a snapshot is
    either recorded whole or not at all; a half-written batch would misreport
    which objects were captured at that instant.
    """
    captured_at = captured_at or _utcnow()

    table_rows = capture_table_stats(conn)
    index_rows = capture_index_stats(conn)
    statements_available = pg_stat_statements_available(conn)
    statement_rows = capture_statement_stats(conn) if statements_available else []

    if not statements_available:
        log.info("pg_telemetry.pg_stat_statements_unavailable",
                  note="pg_stat_statements is not installed on this server; "
                       "table/index telemetry was still captured. Add "
                       "pg_stat_statements to shared_preload_libraries, "
                       "restart PostgreSQL, then run "
                       "CREATE EXTENSION pg_stat_statements to enable "
                       "statement-level telemetry (see docs/DEPLOYMENT.md).")

    tables_written = _persist_table_stats(conn, captured_at, table_rows)
    indexes_written = _persist_index_stats(conn, captured_at, index_rows)
    statements_written = _persist_statement_stats(conn, captured_at, statement_rows)
    conn.commit()

    log.info("pg_telemetry.snapshot_captured", captured_at=captured_at,
              tables=tables_written, indexes=indexes_written,
              statements=statements_written,
              pg_stat_statements_available=statements_available)

    return {
        "captured_at": captured_at,
        "tables": tables_written,
        "indexes": indexes_written,
        "statements": statements_written,
        "pg_stat_statements_available": statements_available,
    }
