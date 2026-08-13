"""What ran, after the process that ran it has gone.

The job registry is in memory because a job is something you watch. That left
the registry as the only record that a run had happened at all: close the
server and the fact that a four-hour crawl ran last night — with what
arguments, and whether it finished — went with it.

So the fact of a job is persisted and its log is not, and the interesting
cases are the ones around the edges: a job still marked running by a process
that has died, ids that must not be handed out twice, and a store that fails
without taking the pipeline down with it.
"""
from __future__ import annotations

import json

import pytest

from pipeline import db
from pipeline.web.jobs import JobRegistry, JobStore


def wait_until_finished(registry, job_id, settings=None, timeout=5.0):
    """Until the job has ended — and, when a store is involved, until the row
    that outlives it has been written.

    The job sets its own state before the strategy runs the callback that
    persists it, so polling the in-memory state alone races the write. A
    reader of the API sees the same tiny window; the interrupted-on-load path
    is what covers it in production.
    """
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = registry.get(job_id)
        if job is not None and job.state != "running":
            if settings is None or _persisted_state(settings, job_id) not in (None, "running"):
                return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} never finished")


def _persisted_state(settings, job_id):
    conn = db.get_connection(settings)
    try:
        row = conn.execute("SELECT state FROM job_runs WHERE id = ?", (job_id,)).fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        conn.close()


def start_and_wait(registry, settings=None, label="a job", args=None, work=None):
    job = registry.start(kind="run", label=label, args=args or {},
                          work=work or (lambda: [{"module": "a_fake", "status": "ok"}]),
                          thread_names=set())
    return wait_until_finished(registry, job.id, settings)


def rows(conn):
    return conn.execute(
        "SELECT id, kind, label, state, dry_run, finished_at, summary_json "
        "FROM job_runs ORDER BY id").fetchall()


def test_a_finished_job_is_still_there_after_a_restart(conn, settings):
    first = JobRegistry(store=JobStore(settings))
    start_and_wait(first, settings, label="m00_geography")

    # A new registry is what a restarted server has: nothing in memory.
    second = JobRegistry(store=JobStore(settings))
    recovered = second.all()

    assert [job.label for job in recovered] == ["m00_geography"]
    assert recovered[0].state == "finished"
    assert recovered[0].summary == [{"module": "a_fake", "status": "ok"}]


def test_a_job_that_never_finished_reappears_as_interrupted(conn, settings):
    conn.execute(
        "INSERT INTO job_runs (id, kind, label, args_json, state, dry_run, started_at) "
        "VALUES (7, 'run', 'm05_cqc', '{}', 'running', 0, '2026-08-13T01:00:00+00:00')")
    conn.commit()

    registry = JobRegistry(store=JobStore(settings))

    assert registry.get(7).state == "interrupted"
    # And it is not holding the slot — a dead job must not refuse a live one.
    assert registry.running() is None
    assert rows(conn)[0][3] == "interrupted", "the correction is written back"


def test_ids_continue_rather_than_restarting(conn, settings):
    first = JobRegistry(store=JobStore(settings))
    start_and_wait(first, settings)
    start_and_wait(first, settings)

    second = JobRegistry(store=JobStore(settings))
    fresh = start_and_wait(second, settings)

    assert fresh.id == 3, "a job id must mean one job across the whole warehouse"
    assert sorted(row[0] for row in rows(conn)) == [1, 2, 3]


def test_a_dry_run_is_a_column_not_a_json_field(conn, settings):
    registry = JobRegistry(store=JobStore(settings))
    start_and_wait(registry, settings, label="m13 — dry run", args={"dry_run": True})
    start_and_wait(registry, settings, label="m13", args={"dry_run": False})

    assert [row[4] for row in rows(conn)] == [1, 0]


def test_a_failing_job_records_why(conn, settings):
    def explodes():
        raise RuntimeError("the source changed shape")

    registry = JobRegistry(store=JobStore(settings))
    job = registry.start(kind="run", label="m01", args={}, work=explodes,
                          thread_names=set())
    wait_until_finished(registry, job.id, settings)

    stored = rows(conn)[0]
    assert stored[3] == "failed"
    assert stored[5] is not None, "a failed job still finished at a time"
    reloaded = JobRegistry(store=JobStore(settings)).get(job.id)
    assert "the source changed shape" in reloaded.error


def test_the_log_is_not_persisted_and_says_so(conn, settings):
    first = JobRegistry(store=JobStore(settings))
    job = start_and_wait(first, settings)
    assert len(job.lines) > 1, "a live job has its own log"

    recovered = JobRegistry(store=JobStore(settings)).get(job.id)
    lines, _ = recovered.since(-1)
    assert len(lines) == 1
    assert "logs/" in lines[0]["text"], (
        "an empty log would read as a job that printed nothing")


def test_a_store_that_cannot_write_does_not_stop_the_run(settings, tmp_path):
    """The warehouse here has no schema at all, so every store call fails.

    Recording history is bookkeeping around running the pipeline. Bookkeeping
    that can refuse a run is worse than bookkeeping that is missing a row.
    """
    settings.database_path = tmp_path / "no-schema.db"
    registry = JobRegistry(store=JobStore(settings))

    job = start_and_wait(registry)

    assert job.state == "finished"
    assert registry.all() == [job]


def test_history_is_capped(conn, settings):
    store = JobStore(settings)
    for i in range(1, 8):
        conn.execute(
            "INSERT INTO job_runs (id, kind, label, args_json, state, dry_run, started_at) "
            "VALUES (?, 'run', ?, '{}', 'finished', 0, '2026-08-13T01:00:00+00:00')",
            (i, f"job {i}"))
    conn.commit()

    assert [job.id for job in store.load(limit=3)] == [7, 6, 5]
