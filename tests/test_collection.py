"""Collection attempts: recording that a source was searched, independent of
what it found (migration 0103) — the gap performance.md named: absence from
an evidence table collapses "searched, nothing there" with "never searched"
and "failed," which docs/CAVEATS.md forbids concluding from.
"""
from __future__ import annotations

import pytest

from pipeline import collection


def test_an_attempt_records_start_and_finish(conn):
    attempt_id = collection.start_attempt(
        conn, module="m01_procurement", source_system="find_a_tender",
        scope="page 1")
    conn.commit()
    collection.finish_attempt(
        conn, attempt_id, status="ok", result_count=42, coverage_state="covered")
    conn.commit()

    row = conn.execute(
        "SELECT * FROM collection_attempts WHERE attempt_id = %s", (attempt_id,)
    ).fetchone()
    assert row["module"] == "m01_procurement"
    assert row["status"] == "ok"
    assert row["result_count"] == 42
    assert row["coverage_state"] == "covered"
    assert row["started_at"] is not None
    assert row["finished_at"] is not None


def test_zero_results_is_distinguishable_from_never_searched(conn):
    """The exact distinction the table exists for: a covered-but-empty source
    and a source with no attempt row at all must not read the same."""
    attempt_id = collection.start_attempt(
        conn, module="m24_council_spend", source_system="wiltshire",
        scope="2026-Q1")
    conn.commit()
    collection.finish_attempt(
        conn, attempt_id, status="empty", result_count=0, coverage_state="no_results")
    conn.commit()

    searched = conn.execute(
        "SELECT coverage_state FROM collection_attempts WHERE source_system = %s",
        ("wiltshire",)).fetchone()
    never_searched = conn.execute(
        "SELECT coverage_state FROM collection_attempts WHERE source_system = %s",
        ("a-source-nobody-tried",)).fetchone()
    assert searched["coverage_state"] == "no_results"
    assert never_searched is None


def test_collection_attempt_context_manager_records_success(conn):
    with collection.collection_attempt(
            conn, module="m01_procurement", source_system="find_a_tender",
            scope="page 2") as attempt:
        attempt.result_count = 7
        conn.commit()

    row = conn.execute(
        "SELECT status, result_count, coverage_state FROM collection_attempts "
        "WHERE attempt_id = %s", (attempt.attempt_id,)).fetchone()
    assert row["status"] == "ok"
    assert row["result_count"] == 7
    assert row["coverage_state"] == "covered"


def test_collection_attempt_context_manager_records_failure_and_reraises(conn):
    with pytest.raises(ValueError, match="boom"):
        with collection.collection_attempt(
                conn, module="m01_procurement", source_system="find_a_tender",
                scope="page 3") as attempt:
            raise ValueError("boom")

    row = conn.execute(
        "SELECT status, failure_class, coverage_state FROM collection_attempts "
        "WHERE attempt_id = %s", (attempt.attempt_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["failure_class"] == "ValueError"
    assert row["coverage_state"] == "failed"


def test_no_results_reports_status_empty_not_ok(conn):
    with collection.collection_attempt(
            conn, module="m24_council_spend", source_system="rutland",
            scope="2026-Q1") as attempt:
        attempt.result_count = 0
        attempt.coverage_state = "no_results"

    row = conn.execute(
        "SELECT status FROM collection_attempts WHERE attempt_id = %s",
        (attempt.attempt_id,)).fetchone()
    assert row["status"] == "empty"
