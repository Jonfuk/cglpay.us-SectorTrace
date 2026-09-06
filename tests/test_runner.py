"""One collection_attempts row per (module, run) — see pipeline/collection.py.

Committed independently of the module's own writes, so the attempt is
durable even when the module fails and rolls back: the point of the record
is that the attempt happened, not what it found (migration 0103).
"""
from __future__ import annotations

from pipeline import runner


def a_writing_module(ctx):
    ctx.conn.execute(
        "INSERT INTO module_cursors (module, cursor_value, updated_at) "
        "VALUES ('a_fake', '2026-01-01', '2026-01-01T00:00:00Z') "
        "ON CONFLICT (module) DO UPDATE SET cursor_value = EXCLUDED.cursor_value, "
        "updated_at = EXCLUDED.updated_at")


def test_a_successful_module_records_a_covered_attempt(conn, settings):
    row = runner.execute_module("a_fake", a_writing_module, settings, since=None,
                                 dry_run=False, limit=None, observer=runner.RunObserver())

    attempt = conn.execute(
        "SELECT module, source_system, status, coverage_state, result_count "
        "FROM collection_attempts WHERE module = %s ORDER BY attempt_id DESC LIMIT 1",
        ("a_fake",)).fetchone()
    assert attempt["status"] == "ok"
    assert attempt["coverage_state"] == "covered"
    assert attempt["result_count"] == row["rows"]


def test_the_bookkeeping_write_does_not_inflate_the_reported_row_count(conn, settings):
    """A regression guard: the attempt row's own INSERT/UPDATE must not be
    counted as part of what the module wrote."""
    row = runner.execute_module("a_fake", a_writing_module, settings, since=None,
                                 dry_run=False, limit=None, observer=runner.RunObserver())
    assert row["rows"] == 1


def test_a_failing_module_still_records_its_attempt(conn, settings):
    def explodes(ctx):
        raise RuntimeError("the source changed shape")

    runner.execute_module("a_fake", explodes, settings, since=None,
                           dry_run=False, limit=None, observer=runner.RunObserver())

    attempt = conn.execute(
        "SELECT status, failure_class, coverage_state FROM collection_attempts "
        "WHERE module = %s ORDER BY attempt_id DESC LIMIT 1", ("a_fake",)).fetchone()
    assert attempt["status"] == "failed"
    assert attempt["failure_class"] == "RuntimeError"
    assert attempt["coverage_state"] == "failed"


def test_a_module_that_writes_nothing_is_recorded_as_no_results_not_absent(conn, settings):
    def writes_nothing(ctx):
        pass

    runner.execute_module("a_fake", writes_nothing, settings, since=None,
                           dry_run=False, limit=None, observer=runner.RunObserver())

    attempt = conn.execute(
        "SELECT status, coverage_state, result_count FROM collection_attempts "
        "WHERE module = %s ORDER BY attempt_id DESC LIMIT 1", ("a_fake",)).fetchone()
    assert attempt["status"] == "empty"
    assert attempt["coverage_state"] == "no_results"
    assert attempt["result_count"] == 0
