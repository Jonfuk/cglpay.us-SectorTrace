"""The durable queue and the process that drains it (Phase 5 worker cutover,
CLAUDE.md settled decision 10).

Three things matter here that `tests/test_web_admin.py`'s end-to-end coverage
does not reach on its own: that a claim genuinely survives a crash (the
checkpoint resume path), that the advisory lock is what stops two workers
from executing at once rather than merely FOR UPDATE SKIP LOCKED, and that
the event log's accounting (`event_stats`/`events_since`) matches what
`Job.head()`/`Job.since()` need.
"""
from __future__ import annotations

from pipeline import db
from pipeline.registry import MODULE_REGISTRY
from pipeline.worker import PIPELINE_RUN_LOCK_NAME, PipelineWorker, WorkerQueue


def _queue(settings) -> WorkerQueue:
    return WorkerQueue(db.get_connection(settings))


def test_enqueue_claim_checkpoint_finish_round_trip(settings):
    with _queue(settings) as queue:
        job_id = queue.enqueue("pipeline_run", {"waves": [["a"]]}, job_id="1")

        claimed = queue.claim()
        assert claimed["job_id"] == job_id
        assert claimed["checkpoint"] == {}
        assert claimed["attempt_count"] == 1

        # A second claim attempt finds nothing: the row is 'running' with a
        # fresh lease, not 'queued', and its lease has not expired.
        assert queue.claim() is None

        queue.checkpoint(job_id, {"completed": ["a"], "summary": [{"module": "a"}]})
        row = queue.job_row(job_id)
        assert row["state"] == "running"

        queue.finish(job_id, success=True, summary=[{"module": "a", "status": "ok"}])
        row = queue.job_row(job_id)
        assert row["state"] == "finished"
        assert row["error"] is None
        assert row["summary"] == [{"module": "a", "status": "ok"}]
        assert row["finished_at"] is not None


def test_finish_with_an_error_records_it_as_a_failed_event_too(settings):
    with _queue(settings) as queue:
        job_id = queue.enqueue("pipeline_run", {}, job_id="1")
        queue.claim()
        queue.finish(job_id, success=False, error="boom")

        row = queue.job_row(job_id)
        assert row["state"] == "failed"
        assert row["error"] == "boom"

        lines, _ = queue.events_since(job_id, -1)
        assert any(line["level"] == "error" and "boom" in line["text"] for line in lines)


def test_active_reports_a_queued_job_before_anything_claims_it(settings):
    with _queue(settings) as queue:
        assert queue.active() is None
        job_id = queue.enqueue("pipeline_run", {}, job_id="1")
        assert queue.active() == job_id

        queue.claim()
        assert queue.active() == job_id, "still the slot, now running rather than queued"

        queue.finish(job_id, success=True)
        assert queue.active() is None


def test_events_since_indexes_from_zero_like_the_in_memory_buffer(settings):
    with _queue(settings) as queue:
        job_id = "1"
        queue.event(job_id, "info", "first")
        queue.event(job_id, "info", "second")
        queue.event(job_id, "info", "third")

        lines, nxt = queue.events_since(job_id, -1)
        assert [line["i"] for line in lines] == [0, 1, 2]
        assert [line["text"] for line in lines] == ["first", "second", "third"]
        assert nxt == 2

        lines, nxt = queue.events_since(job_id, 0)
        assert [line["i"] for line in lines] == [1, 2]
        assert nxt == 2

        # Polling again from the end returns nothing, same as the in-memory path.
        lines, nxt = queue.events_since(job_id, nxt)
        assert lines == []
        assert nxt == 2


def test_event_stats_counts_what_the_trim_deleted(settings):
    with _queue(settings) as queue:
        queue.event_limit = 3
        job_id = "1"
        for n in range(5):
            queue.event(job_id, "info", f"line {n}")

        # sequence_no ran 1..5; the trim keeps only the newest 3 rows, so 2
        # were dropped -- and the dropped count is derivable without keeping
        # them around, purely from the gap between the highest sequence_no
        # ever issued and how many rows survive.
        hi, dropped = queue.event_stats(job_id)
        assert hi == 5
        assert dropped == 2
        lines, _ = queue.events_since(job_id, -1)
        assert [line["text"] for line in lines] == ["line 2", "line 3", "line 4"]


def test_a_resumed_job_skips_modules_the_checkpoint_already_completed(settings, monkeypatch):
    """The granularity `pipeline.runner` actually offers: whole modules, not
    partial ones. A worker that resumes after a crash re-enters at the next
    module the checkpoint had not yet recorded, and never re-runs one it had.
    """
    ran = []
    monkeypatch.setitem(MODULE_REGISTRY, "a_one", lambda ctx: ran.append("a_one"))
    monkeypatch.setitem(MODULE_REGISTRY, "a_two", lambda ctx: ran.append("a_two"))

    with _queue(settings) as queue:
        job_id = queue.enqueue(
            "pipeline_run",
            {"waves": [["a_one", "a_two"]], "since": None, "dry_run": False,
             "limit": None, "jobs": 1},
            job_id="1")
        # Simulate a first attempt that got as far as finishing "a_one" and
        # checkpointing it, then crashed before "a_two" ran.
        queue.claim()
        queue.checkpoint(job_id, {"completed": ["a_one"],
                                    "summary": [{"module": "a_one", "status": "ok"}]})
        # Force the lease into the past so `claim()` will pick this row back
        # up, exactly as it would after a real worker process died mid-run.
        queue.conn.execute(
            "UPDATE worker_jobs SET lease_until = '2000-01-01T00:00:00+00:00' "
            "WHERE job_id = %s", (job_id,))
        queue.conn.commit()

    worker = PipelineWorker(settings, lease_seconds=30)
    result = worker.run_once()

    assert result == {"job_id": job_id, "status": "finished"}
    assert ran == ["a_two"], "a_one must not run twice"

    with _queue(settings) as queue:
        row = queue.job_row(job_id)
        assert row["state"] == "finished"
        assert [r["module"] for r in row["summary"]] == ["a_one", "a_two"]


def test_the_advisory_lock_stops_a_second_worker_running_concurrently(settings):
    """`FOR UPDATE SKIP LOCKED` alone stops two workers claiming the *same*
    row; it does nothing about two workers each claiming a *different* one at
    the same time, which is the case that actually matters for politeness
    (pipeline.http.HOST_CLOCK is enforced per process). The advisory lock is
    what closes that gap -- held here by a raw connection standing in for
    "some other worker process already has it".
    """
    holder = db.get_connection(settings)
    try:
        locked = holder.execute(
            "SELECT pg_try_advisory_lock(hashtext(%s)) AS locked",
            (PIPELINE_RUN_LOCK_NAME,)).fetchone()["locked"]
        assert locked is True

        with _queue(settings) as queue:
            queue.enqueue("pipeline_run", {"waves": [["a"]]}, job_id="1")

        # A second worker cannot even attempt a claim while the lock is held.
        assert PipelineWorker(settings).run_once() is None
        with _queue(settings) as queue:
            assert queue.active() == "1", "left queued, not claimed"
    finally:
        holder.execute("SELECT pg_advisory_unlock(hashtext(%s))", (PIPELINE_RUN_LOCK_NAME,))
        holder.commit()
        holder.close()
