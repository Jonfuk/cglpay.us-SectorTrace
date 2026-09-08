"""PostgreSQL-backed job queue, and the separate process that drains it.

Phase 5 worker cutover (CLAUDE.md settled decision 10): the web server used
to run a module on its own thread and enforce "one run at a time" with a
`threading.Lock` -- fine while PostgreSQL's MVCC still let it get away with
calling that lock a stand-in for a write slot, wrong the day two web
processes (or a web process restarting mid-run) both believe they hold it.
`WorkerQueue` is the durable state a fact about a run needs to survive that;
`PipelineWorker` is the process that actually executes one.

The split:

  * The web process (`pipeline/web/jobs.py`, `pipeline/web/admin.py`) only
    ever enqueues a row here and polls it. It never imports
    `pipeline.runner` to run a module directly once this module is wired in
    -- see `docs/CAVEATS.md`-adjacent settled decision 10's own words:
    "the one-overlapping-run rule moves to a PostgreSQL advisory lock in the
    Phase 5 worker cutover." This is that cutover.
  * `PipelineWorker`, started as `pipeline worker run` (a separate OS
    process, possibly on a separate machine), claims one row with
    `FOR UPDATE SKIP LOCKED`, executes it through the same
    `pipeline.runner.run_waves` the CLI and the old in-process path both
    use, and writes progress back for the web process to poll.

`FOR UPDATE SKIP LOCKED` already stops two worker processes claiming the
*same* row. It does not stop two worker processes claiming two *different*
queued rows at once, which is the case that actually matters here: two
pipeline runs executing concurrently would double up on whichever public
host both happened to touch, which is exactly what the per-host rate limit
(pipeline.http.HOST_CLOCK, enforced per process) cannot see across two
processes. `PIPELINE_RUN_LOCK_KEY` is the PostgreSQL advisory lock that
closes that gap: a worker only claims after it holds the lock, so at most
one worker process is ever inside `run_waves` at a time, deployment-wide,
regardless of how many worker processes are running or how many rows are
queued.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from pipeline import telemetry

log = structlog.get_logger()

# The advisory lock key, hashed from a name rather than a bare integer for
# the same reason pipeline/nlp/embedding_repository.py's compaction lock is:
# a name says what it is for at the call site instead of asking the reader to
# remember what some number means. Session-scoped (`pg_try_advisory_lock`,
# not `..._xact_lock`) because it has to survive the many commits one run
# makes across its lifetime -- `execute_module` commits per module -- and be
# releasable only when this worker is actually done with the row, not when
# whichever statement happens to finish its transaction first.
#
# Must never change once anything is deployed against it: a rolling deploy
# briefly runs an old and a new worker side by side, and if their lock names
# hash differently neither would see the other's lock and the one-run-at-a-
# time guarantee this exists for would be silently gone for the length of
# the rollout.
PIPELINE_RUN_LOCK_NAME = "sectortrace:pipeline-run"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seconds_since(iso: str | None) -> float | None:
    """Elapsed seconds since an ISO-8601 timestamp this module wrote, or None
    for a value that is missing or does not parse -- a benchmarking read must
    never be the reason a claimed job fails. Mirrors
    `pipeline/graph/projector.py`'s `_lag_seconds`, the same shape for the
    same reason (a queued row's own timestamp, compared to now)."""
    if not iso:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso)).total_seconds()
    except (TypeError, ValueError):
        return None


class WorkerQueue:
    """Durable enqueue/claim/checkpoint/event operations.

    Claims use ``FOR UPDATE SKIP LOCKED`` so multiple worker processes can
    safely share the queue without two of them taking the same row; see the
    module docstring for why that alone is not the whole story.

    Every method opens no connection of its own -- it uses the one handed to
    the constructor and never closes it, matching every other piece of this
    codebase that takes a connection as a parameter (pipeline/db.py's own
    convention). Used as a context manager (`with WorkerQueue(conn) as
    queue:`) closes that connection on exit, which is the shape every short-
    lived caller here wants: open one connection, do one thing, close it,
    exactly like every other per-request write in pipeline/web already does.
    """

    def __init__(self, conn, *, lease_seconds: int = 900,
                 event_limit: int = 4000):
        self.conn = conn
        self.lease_seconds = lease_seconds
        self.event_limit = event_limit

    def __enter__(self) -> "WorkerQueue":
        return self

    def __exit__(self, *exc_info) -> bool:
        self.conn.close()
        return False

    def enqueue(self, kind: str, arguments: dict[str, Any], *,
                job_id: str | None = None) -> str:
        job_id = job_id or str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            "INSERT INTO worker_jobs(job_id, kind, arguments_json, state, created_at, updated_at) "
            "VALUES (%s, %s, %s, 'queued', %s, %s)",
            (job_id, kind, json.dumps(arguments, sort_keys=True, default=str), now, now))
        self.conn.commit()
        return job_id

    def claim(self) -> dict[str, Any] | None:
        now = _now()
        lease = (datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds)).isoformat(timespec="seconds")
        # FOR UPDATE SKIP LOCKED is what lets more than one worker claim from
        # the same queue without two of them taking the same job.
        row = self.conn.execute(
            "SELECT job_id, kind, arguments_json, checkpoint_json, attempt_count, created_at "
            "FROM worker_jobs WHERE state = 'queued' OR "
            "(state = 'running' AND lease_until < %s) "
            "ORDER BY created_at, job_id LIMIT 1 FOR UPDATE SKIP LOCKED", (now,)
        ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            "UPDATE worker_jobs SET state = 'running', lease_until = %s, "
            "attempt_count = attempt_count + 1, updated_at = %s WHERE job_id = %s",
            (lease, now, row["job_id"]))
        self.conn.commit()
        return {"job_id": row["job_id"], "kind": row["kind"],
                "arguments": json.loads(row["arguments_json"]),
                "checkpoint": json.loads(row["checkpoint_json"] or "{}"),
                "attempt_count": row["attempt_count"] + 1,
                "lease_until": lease,
                # Queue delay (performance.md:632) is this minus claim time,
                # computed by the caller -- `created_at` is whatever
                # `enqueue()` wrote, never touched again by a re-claim after a
                # lease expiry, so it always answers "how long did this job
                # wait for a worker", not "how long since the last attempt".
                "created_at": row["created_at"]}

    def checkpoint(self, job_id: str, checkpoint: dict[str, Any]) -> None:
        self.conn.execute(
            "UPDATE worker_jobs SET checkpoint_json = %s, updated_at = %s WHERE job_id = %s",
            (json.dumps(checkpoint, sort_keys=True, default=str), _now(), job_id))
        self.conn.commit()

    def renew_lease(self, job_id: str) -> None:
        """Push a claimed job's lease forward. Called periodically while it
        is still genuinely running, from a thread separate to the one
        executing it -- see `PipelineWorker._renew_lease_loop`.

        Without this, a module that outlasts `lease_seconds` looks abandoned
        to `claim()` before it actually is. m10 alone was measured at four
        and a half hours per full run (pipeline/parallel.py); the default
        900-second lease is nowhere near that, and a second worker
        legitimately claiming and re-running a job that is still in progress
        would double the load on whichever host both happened to be reading,
        which is exactly what this pipeline's politeness rules exist to
        prevent.
        """
        self.conn.execute(
            "UPDATE worker_jobs SET lease_until = %s, updated_at = %s "
            "WHERE job_id = %s AND state = 'running'",
            ((datetime.now(timezone.utc) + timedelta(seconds=self.lease_seconds))
             .isoformat(timespec="seconds"), _now(), job_id))
        self.conn.commit()

    def _ensure_data_version_row(self) -> None:
        """`warehouse_data_version` is a singleton counter, not a fact a
        migration can seed once and be done with -- the offline test suite
        truncates every table between tests (see conftest.py), and a
        migration only ever runs once per schema, so nothing would reseed
        this row for test two onward without this. Safe to call before every
        read or write of the row: the `WHERE NOT EXISTS` makes it a no-op
        once the row is there.
        """
        self.conn.execute(
            "INSERT INTO warehouse_data_version(version, updated_at) "
            "SELECT 0, %s WHERE NOT EXISTS (SELECT 1 FROM warehouse_data_version)",
            (_now(),))

    def finish(self, job_id: str, *, success: bool, error: str | None = None,
               summary: Any = None) -> None:
        self.conn.execute(
            "UPDATE worker_jobs SET state = %s, lease_until = NULL, error = %s, "
            "summary_json = %s, updated_at = %s WHERE job_id = %s",
            ("finished" if success else "failed", error,
             json.dumps(summary, default=str) if summary is not None else None,
             _now(), job_id))
        self.conn.commit()
        if error:
            self.event(job_id, "error", error)
        if success:
            self._ensure_data_version_row()
            self.conn.execute(
                "UPDATE warehouse_data_version SET version = version + 1, updated_at = %s",
                (_now(),))
            self.conn.commit()

    def event(self, job_id: str, level: str, message: str) -> None:
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_no), 0) + 1 AS n FROM worker_job_events "
            "WHERE job_id = %s", (job_id,)).fetchone()
        self.conn.execute(
            "INSERT INTO worker_job_events(job_id, sequence_no, level, message, created_at) "
            "VALUES (%s, %s, %s, %s, %s)", (job_id, row["n"], level, message[:4000], _now()))
        self.conn.execute(
            "DELETE FROM worker_job_events WHERE job_id = %s AND sequence_no <= "
            "(SELECT COALESCE(MAX(sequence_no), 0) - %s FROM worker_job_events WHERE job_id = %s)",
            (job_id, self.event_limit, job_id))
        self.conn.commit()

    def data_version(self) -> int:
        self._ensure_data_version_row()
        self.conn.commit()
        return int(self.conn.execute(
            "SELECT version FROM warehouse_data_version").fetchone()["version"])

    def job_row(self, job_id: str) -> dict[str, Any] | None:
        """The current fact of one job, for a poller in a different process
        (or the same process after a restart) than whichever worker is, or
        was, executing it. There is no in-memory copy of this anywhere to
        trust instead -- see pipeline/web/jobs.py's `Job._refresh_from_queue`.
        """
        row = self.conn.execute(
            "SELECT state, error, summary_json, updated_at FROM worker_jobs "
            "WHERE job_id = %s", (job_id,)).fetchone()
        if row is None:
            return None
        return {
            "state": row["state"],
            "finished_at": row["updated_at"] if row["state"] in ("finished", "failed") else None,
            "error": row["error"],
            "summary": json.loads(row["summary_json"]) if row["summary_json"] else None,
        }

    def existing_job_ids(self, job_ids: list[str]) -> set[str]:
        """Which of these ids have a row here at all -- a batch membership
        check, not a batch `job_row`, because the only thing a caller ever
        needs this for (JobRegistry rehydrating its history at startup) is
        "is this one worker-backed", asked once for up to fifty ids rather
        than once per id.
        """
        if not job_ids:
            return set()
        rows = self.conn.execute(
            "SELECT job_id FROM worker_jobs WHERE job_id = ANY(%s)", (job_ids,)).fetchall()
        return {row["job_id"] for row in rows}

    def active(self) -> str | None:
        """The job_id presently queued or running, if any.

        The cross-process source of truth for "is the single pipeline slot
        taken": a live query against this table, not a pointer in any one
        process's memory, because the process answering an admin request is
        very often not the process (if any) executing the job it is asking
        about.
        """
        row = self.conn.execute(
            "SELECT job_id FROM worker_jobs WHERE state IN ('queued', 'running') "
            "ORDER BY created_at LIMIT 1").fetchone()
        return row["job_id"] if row else None

    def events_since(self, job_id: str, after: int) -> tuple[list[dict], int]:
        """The `Job.since()` shape (`{i, at, level, text}` lines, and the next
        index to ask for), read from `worker_job_events` instead of an
        in-memory buffer. `i` is `sequence_no - 1` so the numbering lines up
        with the in-memory path's zero-based indices exactly, including
        `after=-1` meaning "from the start".
        """
        hi = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_no), 0) AS hi FROM worker_job_events "
            "WHERE job_id = %s", (job_id,)).fetchone()["hi"]
        rows = self.conn.execute(
            "SELECT sequence_no, level, message, created_at FROM worker_job_events "
            "WHERE job_id = %s AND sequence_no > %s ORDER BY sequence_no",
            (job_id, after + 1)).fetchall()
        lines = [{"i": row["sequence_no"] - 1, "at": row["created_at"],
                  "level": row["level"], "text": row["message"]} for row in rows]
        return lines, hi - 1

    def event_stats(self, job_id: str) -> tuple[int, int]:
        """(lines ever emitted, lines dropped from the front) for `Job.head()`.

        `sequence_no` is never reused even though `event()` deletes the
        oldest rows past `event_limit`, so the gap between the highest
        number ever issued and how many rows currently exist for this job
        *is* the drop count -- computed without keeping the dropped rows
        around only to count them.
        """
        row = self.conn.execute(
            "SELECT COALESCE(MAX(sequence_no), 0) AS hi, COUNT(*) AS n "
            "FROM worker_job_events WHERE job_id = %s", (job_id,)).fetchone()
        hi, n = int(row["hi"]), int(row["n"])
        return hi, hi - n


class _EventLogHandler(logging.Handler):
    """Root-logger handler that files every record into `worker_job_events`
    while one job is executing.

    Unlike `pipeline/web/jobs.py`'s `_JobLogHandler`, this does not filter by
    thread name. That filter exists there because the web process serves
    other requests -- and other jobs' log lines -- on other threads at the
    same moment. A worker process does not: the advisory lock guarantees
    exactly one job is ever being executed here at a time, so every record
    emitted while this handler is attached belongs to it, whichever thread a
    concurrent wave (`--jobs N`) happened to run it on.

    That last part is exactly why this needs its own lock: `emit()` can be
    called from any of a wave's pool threads, all sharing the one connection
    this handler was built with, and a psycopg connection is not safe for
    concurrent use from more than one thread at a time.
    """

    def __init__(self, queue: WorkerQueue, job_id: str) -> None:
        super().__init__(level=logging.INFO)
        self._queue = queue
        self._job_id = job_id
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        from pipeline.web.jobs import _render

        try:
            with self._lock:
                self._queue.event(self._job_id, record.levelname.lower(), _render(record))
        except Exception:  # pragma: no cover - a log handler must never raise
            pass


class _PhaseReporter:
    """The ProgressReporter shape, logging instead of drawing. Deliberately
    the same shape as `pipeline/web/admin.py`'s: a worker-executed run and an
    admin-executed one should read identically to whoever is watching,
    duplicated rather than imported because a worker process has no reason
    to depend on the web layer -- it is the web layer's peer, not a caller of
    it."""

    def __init__(self, module: str) -> None:
        self._module = module

    def phase(self, text: str) -> None:
        log.info("run.phase", module=self._module, phase=text)

    def track(self, items, description: str, total: int | None = None):
        try:
            count = total if total is not None else len(items)
        except TypeError:
            count = "?"
        log.info("run.phase", module=self._module, phase=description, items=count)
        return iter(items)


class _phase_reporter:  # noqa: N801 - used as a context manager, not a class
    def __init__(self, module: str) -> None:
        self._module = module

    def __enter__(self) -> _PhaseReporter:
        log.info("run.module_starting", module=self._module)
        return _PhaseReporter(self._module)

    def __exit__(self, *exc_info) -> bool:
        return False


class _CheckpointingObserver:
    """Logs a run through structlog exactly as the admin route's own
    observer does, and additionally checkpoints after every module -- the
    granularity `pipeline.runner` actually offers: `execute_module` commits
    or rolls back as a whole, so there is no finer-grained "half a module
    done" to record, and none is invented here. A job resumed after a crash
    re-enters at the next module that had not yet reported in, never partway
    through one.
    """

    def __init__(self, queue: WorkerQueue, job_id: str,
                 completed: set[str], prior_summary: list[dict]):
        self._queue = queue
        self._job_id = job_id
        self._completed = set(completed)
        self.summary: list[dict] = list(prior_summary)
        # When this checkpoint was last durable, for the "checkpoint age"
        # metric (performance.md:632): how long a crash right before the next
        # module finished would have cost, in re-done work. Starts at
        # construction time -- the checkpoint this job resumed from (or, for
        # a fresh job, its start) -- and moves forward every time a new one is
        # written below, never read back from the row itself: `worker_jobs`
        # has no per-checkpoint timestamp finer than `updated_at`, which this
        # process's own clock already stands in for while it is the one
        # writing.
        self._last_checkpoint_at = time.monotonic()

    def run_starting(self, total_modules: int) -> None:
        log.info("run.starting", modules=total_modules)

    def wave_starting(self, names: list[str], width: int) -> None:
        log.info("run.wave", modules=", ".join(names), at_a_time=width)

    def module_progress(self, name: str):
        return _phase_reporter(name)

    def module_finished(self, row: dict) -> None:
        clean = {**row, "error": (f"{type(row['error']).__name__}: {row['error']}"
                                   if row.get("error") is not None else None)}
        if row["status"] == "failed":
            log.warning("run.module_failed", module=row["module"],
                        error=str(row.get("error")), seconds=round(row["elapsed"], 1))
        else:
            log.info("run.module_done", module=row["module"],
                      seconds=round(row["elapsed"], 1), rows=row.get("rows", 0),
                      review=row.get("review", 0), failures=row.get("failures", 0))
        self._completed.add(row["module"])
        self.summary.append(clean)
        # Checkpointed after every module rather than batched: the point of a
        # checkpoint is that it is durable before the next thing that could
        # fail, and the next thing that could fail here is the next module.
        age = time.monotonic() - self._last_checkpoint_at
        telemetry.histogram(
            "worker.checkpoint_age_seconds", unit="s",
            description="Time since the previous durable checkpoint, at each new one.").record(age)
        self._queue.checkpoint(self._job_id, {
            "completed": sorted(self._completed), "summary": self.summary})
        self._last_checkpoint_at = time.monotonic()


class PipelineWorker:
    """Claims and executes queued pipeline-module runs, one at a time,
    deployment-wide -- see the module docstring for why "one at a time" needs
    the advisory lock and not just `FOR UPDATE SKIP LOCKED`.

    A separate OS process from the web server. `run_forever` is what
    `pipeline worker run` calls; `run_once` (used by tests and by
    `--once`) claims and executes at most one job before returning, so the
    offline suite can drive exactly one claim-execute-checkpoint-finish cycle
    without a real background process or a poll loop with a timeout.
    """

    def __init__(self, settings, *, poll_seconds: float = 5.0,
                 lease_seconds: int = 900, worker_id: str | None = None):
        self.settings = settings
        self.poll_seconds = max(0.1, float(poll_seconds))
        self.lease_seconds = max(30, int(lease_seconds))
        self.worker_id = worker_id or f"pipeline-worker-{uuid.uuid4()}"

    def run_forever(self) -> None:
        from pipeline.registry import discover_modules

        discover_modules()
        while True:
            if self.run_once() is None:
                time.sleep(self.poll_seconds)

    def run_once(self) -> dict[str, Any] | None:
        """Try the advisory lock, try a claim, run at most one job.

        Returns None when there was nothing to do this tick -- either the
        lock is held by another worker process, or the queue is empty --
        which is what tells `run_forever` to sleep rather than spin.
        """
        from pipeline import db

        conn = db.get_connection(self.settings)
        try:
            locked = conn.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s)) AS locked",
                (PIPELINE_RUN_LOCK_NAME,)).fetchone()["locked"]
            if not locked:
                log.info("worker.lock_held_elsewhere")
                return None
            try:
                return self._claim_and_run(conn)
            finally:
                conn.execute("SELECT pg_advisory_unlock(hashtext(%s))",
                             (PIPELINE_RUN_LOCK_NAME,))
        finally:
            conn.close()

    def _claim_and_run(self, conn) -> dict[str, Any] | None:
        queue = WorkerQueue(conn, lease_seconds=self.lease_seconds)
        claimed = queue.claim()
        if claimed is None:
            return None

        job_id = claimed["job_id"]
        # Queue delay (performance.md:632): how long this job sat in
        # `worker_jobs` between `enqueue()` and this claim. None rather than
        # 0 for a row with no parseable `created_at` -- never fabricated.
        queue_delay = _seconds_since(claimed.get("created_at"))
        telemetry.histogram(
            "worker.queue_delay_seconds", unit="s",
            description="Time between a job's enqueue and its claim.").record(
            queue_delay if queue_delay is not None else 0.0, {"kind": claimed["kind"]})
        log.info("worker.job_claimed", job_id=job_id, kind=claimed["kind"],
                 attempt=claimed["attempt_count"], worker_id=self.worker_id)

        with telemetry.span("worker.job", job_id=job_id, kind=claimed["kind"],
                            attempt=claimed["attempt_count"],
                            queue_delay_seconds=queue_delay) as job_span:
            stop = threading.Event()
            heartbeat = threading.Thread(
                target=self._renew_lease_loop, args=(job_id, stop),
                name=f"pipeline-worker-lease-{job_id}", daemon=True)
            heartbeat.start()
            try:
                if claimed["kind"] == "pipeline_run":
                    result = self._run_pipeline_job(queue, job_id, claimed)
                    job_span.set_attribute("status", result["status"])
                    return result
                # Nothing else is enqueued by this codebase today, but a row this
                # worker does not understand must still leave the queue rather
                # than being claimed forever and blocking every future run.
                message = f"unknown job kind {claimed['kind']!r}"
                queue.finish(job_id, success=False, error=message)
                self._sync_job_runs(job_id, success=False, error=message, summary=None)
                log.error("worker.unknown_job_kind", job_id=job_id, kind=claimed["kind"])
                job_span.set_attribute("status", "failed")
                return {"job_id": job_id, "status": "failed"}
            finally:
                stop.set()
                heartbeat.join(timeout=5)

    def _renew_lease_loop(self, job_id: str, stop: threading.Event) -> None:
        from pipeline import db

        interval = max(5.0, min(self.lease_seconds / 3, 120.0))
        while not stop.wait(interval):
            conn = db.get_connection(self.settings)
            try:
                WorkerQueue(conn, lease_seconds=self.lease_seconds).renew_lease(job_id)
            except Exception as exc:
                log.warning("worker.lease_renew_failed", job_id=job_id, error=str(exc))
            finally:
                conn.close()

    def _run_pipeline_job(self, queue: WorkerQueue, job_id: str,
                            claimed: dict[str, Any]) -> dict[str, Any]:
        from pipeline import db, runner
        from pipeline.registry import discover_modules

        discover_modules()

        # Migrations first, on their own connection, exactly as `cli.run` and
        # `admin.start_run`'s `work()` both do: a warehouse built before a
        # module's tables arrived would otherwise fail mid-run rather than
        # before it starts.
        migrate_conn = db.get_connection(self.settings)
        try:
            db.apply_migrations(migrate_conn)
        finally:
            migrate_conn.close()

        args = claimed["arguments"]
        waves: list[list[str]] = args["waves"]
        checkpoint = claimed["checkpoint"] or {}
        completed = set(checkpoint.get("completed") or [])
        prior_summary = list(checkpoint.get("summary") or [])
        # Resuming skips whatever the checkpoint already says finished,
        # keeping wave order and dropping any wave that is now empty. This is
        # the only granularity available: `execute_module` has no partial
        # state of its own to resume from mid-module.
        remaining = [[name for name in wave if name not in completed] for wave in waves]
        remaining = [wave for wave in remaining if wave]

        event_conn = db.get_connection(self.settings)
        handler = _EventLogHandler(WorkerQueue(event_conn, event_limit=queue.event_limit), job_id)
        root = logging.getLogger()
        root.addHandler(handler)

        observer = _CheckpointingObserver(queue, job_id, completed, prior_summary)
        error_text: str | None = None
        try:
            if remaining:
                run_summary = runner.run_waves(
                    remaining, int(args.get("jobs") or 1), self.settings,
                    args.get("since"), bool(args.get("dry_run")), args.get("limit"),
                    observer, origin="worker")
                # `run_waves` reports module-level failures in its summary
                # instead of raising. A worker job must mirror that result in
                # the durable queue so the admin UI cannot show a failed run
                # as finished merely because the process stayed alive.
                failed = [row for row in (run_summary or [])
                          if row.get("status") == "failed"]
                if failed:
                    error_text = f"{len(failed)} module(s) failed"
                    success = False
                else:
                    success = True
            else:
                success = True
        except Exception as exc:
            log.exception("worker.job_failed", job_id=job_id)
            error_text = f"{type(exc).__name__}: {exc}"
            success = False
        finally:
            root.removeHandler(handler)
            event_conn.close()

        summary = observer.summary
        queue.finish(job_id, success=success, error=error_text, summary=summary)
        self._sync_job_runs(job_id, success=success, error=error_text, summary=summary)
        log.info("worker.job_finished", job_id=job_id,
                 status="finished" if success else "failed")
        return {"job_id": job_id, "status": "finished" if success else "failed"}

    def _sync_job_runs(self, job_id: str, *, success: bool, error: str | None,
                        summary: list[dict] | None) -> None:
        """Best-effort mirror into `job_runs`, the table `JobStore`
        (pipeline/web/jobs.py) already uses for "the fact of a job outlives
        the process that ran it". `JobRegistry` never needs this -- it reads
        the true state live from `worker_jobs` on every poll, see
        `Job._refresh_from_queue` -- but a direct `SELECT * FROM job_runs`,
        or the next web process's `JobStore.load()` before this job's
        `worker_jobs` row is consulted, should not read 'running' forever for
        a job whose worker finished and exited.

        Swallowed like every other write `JobStore` makes: bookkeeping that
        can raise is worse than bookkeeping that is occasionally missing a
        row, and it must never be the reason a claimed job is left unfinished
        in the eyes of the queue that matters (`worker_jobs`, already updated
        by the time this runs).
        """
        from pipeline import db

        conn = db.get_connection(self.settings)
        try:
            conn.execute(
                "UPDATE job_runs SET state = %s, finished_at = %s, error = %s, "
                "summary_json = %s WHERE id = %s",
                ("finished" if success else "failed", _now(), error,
                 json.dumps(summary, default=str) if summary else None, int(job_id)))
            conn.commit()
        except Exception as exc:  # pragma: no cover - defensive, like JobStore._write
            log.warning("worker.job_runs_sync_failed", job_id=job_id, error=str(exc))
        finally:
            conn.close()
