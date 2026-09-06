"""PostgreSQL maintenance telemetry (migration 0113, performance.md
"PostgreSQL maintenance"). Capture and persistence only — this suite must
never assert anything about autovacuum/index/planner *configuration*, only
that the telemetry needed to eventually decide those is recorded correctly.

The dev/test image (deploy/postgres/Dockerfile, deploy/docker-compose.postgres.yml)
does not set `shared_preload_libraries`, so `pg_stat_statements` is genuinely
absent here the same way docs/DEPLOYMENT.md records it for the live server —
the "installed" branch is exercised by monkeypatching the two functions that
would change behaviour if it were present, rather than by installing the
extension in CI.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline import pg_telemetry


def test_pg_stat_statements_is_not_installed_here(conn):
    """Ground truth for every other test in this file: the dev/test
    PostgreSQL image never sets shared_preload_libraries, so `CREATE
    EXTENSION pg_stat_statements` would fail here exactly as it would on the
    unconfigured live server (docs/DEPLOYMENT.md). Feature-detection, not a
    forced enable, is the only correct behaviour against this database.
    """
    assert pg_telemetry.pg_stat_statements_available(conn) is False
    assert pg_telemetry.capture_statement_stats(conn) == []


def test_capture_table_stats_covers_known_application_tables(conn):
    rows = pg_telemetry.capture_table_stats(conn)
    by_name = {row["table_name"]: row for row in rows}
    # parse_failures is one of the core infra tables every schema carries
    # (test_db.py:test_core_infra_tables_exist) — a stable existence check
    # that does not depend on which domain modules' migrations ran.
    assert "parse_failures" in by_name
    row = by_name["parse_failures"]
    assert row["schema_name"]
    # A freshly-migrated, freshly-truncated schema: no autovacuum/analyze has
    # run yet, so the counters are legitimately zero/NULL. The point of this
    # assertion is that the columns exist and are readable at all, not their
    # value on an empty table.
    assert set(row) == {
        "schema_name", "table_name", "n_live_tup", "n_dead_tup",
        "n_mod_since_analyze", "last_autovacuum", "last_analyze",
        "autovacuum_count", "analyze_count",
    }


def test_capture_index_stats_covers_a_known_index(conn):
    rows = pg_telemetry.capture_index_stats(conn)
    by_name = {row["index_name"]: row for row in rows}
    # schema_migrations' own primary key index always exists once migrated.
    assert any(name.startswith("schema_migrations") for name in by_name)
    sample = next(iter(rows))
    assert set(sample) == {
        "schema_name", "table_name", "index_name",
        "idx_scan", "idx_tup_read", "idx_tup_fetch",
    }


def test_snapshot_persists_table_and_index_rows(conn):
    result = pg_telemetry.snapshot(conn, captured_at="2026-01-01T00:00:00+00:00")

    assert result["captured_at"] == "2026-01-01T00:00:00+00:00"
    assert result["tables"] > 0
    assert result["indexes"] > 0
    assert result["statements"] == 0
    assert result["pg_stat_statements_available"] is False

    persisted_tables = conn.execute(
        "SELECT COUNT(*) AS n FROM pg_telemetry_table_stats "
        "WHERE captured_at = %s", ("2026-01-01T00:00:00+00:00",)
    ).fetchone()["n"]
    assert persisted_tables == result["tables"]

    persisted_indexes = conn.execute(
        "SELECT COUNT(*) AS n FROM pg_telemetry_index_stats "
        "WHERE captured_at = %s", ("2026-01-01T00:00:00+00:00",)
    ).fetchone()["n"]
    assert persisted_indexes == result["indexes"]

    persisted_statements = conn.execute(
        "SELECT COUNT(*) AS n FROM pg_telemetry_statement_stats"
    ).fetchone()["n"]
    assert persisted_statements == 0


def test_snapshot_rerun_with_the_same_captured_at_does_not_error(conn):
    """A retried capture (the operator re-runs the CLI after a transient
    failure, or a scheduled timer fires twice) must not raise a conflict —
    it is the same shape of idempotence `db.upsert_many` already gives every
    other bulk-write path in this codebase.
    """
    first = pg_telemetry.snapshot(conn, captured_at="2026-01-01T00:00:00+00:00")
    second = pg_telemetry.snapshot(conn, captured_at="2026-01-01T00:00:00+00:00")
    assert first["tables"] == second["tables"]
    assert first["indexes"] == second["indexes"]


def test_snapshot_persists_statement_stats_when_the_extension_is_present(conn, monkeypatch):
    """Exercises the persistence path for the pg_stat_statements-backed table
    without depending on the extension actually being installed in this
    environment (see the module docstring) — the capture query itself is
    trivial SQL against a real view and is not what this test is checking;
    what matters is that a row pg_stat_statements could plausibly return
    lands correctly in pg_telemetry_statement_stats.
    """
    monkeypatch.setattr(pg_telemetry, "pg_stat_statements_available", lambda _conn: True)
    fake_rows = [{
        "queryid": 123456789,
        "query_text": "SELECT * FROM contracts WHERE value_core > $1",
        "calls": 42,
        "total_exec_time_ms": 1234.5,
        "rows": 76229,
        "shared_blks_hit": 900,
        "shared_blks_read": 12,
    }]
    monkeypatch.setattr(pg_telemetry, "capture_statement_stats", lambda _conn: fake_rows)

    result = pg_telemetry.snapshot(conn, captured_at="2026-02-02T00:00:00+00:00")
    assert result["statements"] == 1
    assert result["pg_stat_statements_available"] is True

    row = conn.execute(
        "SELECT * FROM pg_telemetry_statement_stats WHERE captured_at = %s",
        ("2026-02-02T00:00:00+00:00",)
    ).fetchone()
    assert row["queryid"] == 123456789
    assert row["calls"] == 42
    assert row["total_exec_time_ms"] == 1234.5
    assert row["rows"] == 76229


def test_snapshot_logs_the_unavailable_event_with_no_extension(conn):
    from structlog.testing import capture_logs

    with capture_logs() as captured:
        pg_telemetry.snapshot(conn, captured_at="2026-03-03T00:00:00+00:00")
    events = {entry["event"] for entry in captured}
    assert "pg_telemetry.pg_stat_statements_unavailable" in events
    assert "pg_telemetry.snapshot_captured" in events


def test_cli_reports_a_snapshot(conn, settings, monkeypatch):
    conn.close()  # the CLI opens its own connection
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    result = CliRunner().invoke(cli_module.app, ["pg-telemetry-snapshot"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["tables"] > 0
    assert payload["indexes"] > 0
    assert payload["pg_stat_statements_available"] is False


def test_capture_never_writes_configuration(conn):
    """Regression guard for the explicit non-goal: nothing in this module may
    touch autovacuum thresholds, indexes, or planner/memory settings. Asserts
    the source rather than behaviour, because the wrong behaviour here is
    silence — a config change with no visible symptom in a snapshot's return
    value — and the settled decision is about what the code may attempt at
    all, not just what it happens to do against this test database.
    """
    import inspect

    source = inspect.getsource(pg_telemetry)
    for forbidden in ("ALTER TABLE", "ALTER SYSTEM", "SET (", "CREATE INDEX",
                      "DROP INDEX", "autovacuum_vacuum", "autovacuum_analyze"):
        assert forbidden not in source, f"{forbidden!r} must not appear in pg_telemetry.py"
