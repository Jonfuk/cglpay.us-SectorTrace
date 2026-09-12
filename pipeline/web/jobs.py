"""Long jobs started from the browser, and the log they produce while running.

A module run takes minutes to hours. An HTTP request cannot hold that open, so
a job is started, given an id, and polled: `POST /api/admin/run` returns
immediately and `GET /api/admin/jobs/{id}?after=N` hands back whatever lines
have appeared since line N.

Two different things run under that same contract, and only one of them still
runs in this process:

  * **A pipeline-module run is enqueued, not started here.** Phase 5 (CLAUDE.md
    settled decision 10) moved module execution into a separate `pipeline
    worker` process (pipeline/worker.py) so that "one run at a time" could stop
    being a `threading.Lock` this process could lose track of the moment there
    is more than one process, and become a PostgreSQL advisory lock the worker
    holds for as long as it is actually running something. `enqueue_pipeline_run`
    writes a row to `worker_jobs` and returns immediately; nothing about
    executing it happens here, or on any thread of this process, ever again.
    Its state and log live in `worker_jobs`/`worker_job_events`, and `Job`
    reads them live on every poll (`_refresh_from_queue`) rather than trusting
    anything cached in this object, because the process that could tell it
    the truth is frequently not this one.

  * **Everything else** -- the integrity check, an export -- is small enough,
    and reads-not-collects enough, that running it on a thread of this process
    still fits: `ThreadStrategy` runs the work here, on its own thread, exactly
    as before. It cannot be cancelled and a hard interpreter crash would take
    the server down with it, same as always; that was an acceptable trade
    for a read-mostly job and still is.

One thing is deliberately shared between the two: **there is still only one
slot.** A pipeline run and an integrity check both want the whole warehouse
undisturbed while they work, so `JobRegistry` refuses a second job of *either*
kind with a 409 naming whichever job is in the way -- checked against the
in-process pointer first (cheap, and right most of the time) and against
`WorkerQueue.active()` second (the only way to know a job enqueued by a
process that no longer exists, or being executed by a process that is not
this one, is still using the slot). The worker's advisory lock is the version
of this guarantee that cannot be raced past; this 409 is the version a caller
gets to see.

Nothing here authenticates anybody: starting a run is available to whoever can
reach the server, which is every interface by default. See docs/admin-ui-plan.md.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import structlog

log = structlog.get_logger()

# Enough to hold a long module's chatter without letting a runaway job grow the
# server's memory without bound. Older lines are dropped from the front and the
# reader is told how many, so a gap is visible rather than silent.
MAX_LINES = 4_000


class JobError(Exception):
    def __init__(self, message: str, status: int = 400, job_id: int | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.job_id = job_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Job:
    id: int
    kind: str
    label: str
    args: dict[str, Any]
    state: str = "running"          # running | finished | failed
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    error: str | None = None
    summary: list[dict] | None = None

    # Line buffer. `dropped` counts lines trimmed off the front, so an index
    # into this log means the same thing for the whole life of the job. Read
    # by `since()`/`head()` only for a `ThreadStrategy` job -- a worker-backed
    # one (`worker_backed=True`) never has anything appended here; its lines
    # live in `worker_job_events` instead, see `_refresh_from_queue`.
    lines: list[dict] = field(default_factory=list)
    dropped: int = 0

    # True for a job `JobRegistry.enqueue_pipeline_run` handed to the worker
    # queue instead of a thread. `_queue_factory`, set alongside it, is a
    # zero-argument callable returning a fresh, ready-to-close
    # `pipeline.worker.WorkerQueue` -- a factory rather than a live instance
    # because this object is read from whichever web-request thread polls
    # it, and a psycopg connection shared across threads is not safe to use
    # concurrently. Every read opens its own connection and closes it, the
    # same per-request cost every other admin route already pays.
    worker_backed: bool = False
    _queue_factory: Callable[[], Any] | None = field(default=None, repr=False, compare=False)

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def append(self, level: str, text: str) -> None:
        with self._lock:
            index = self.dropped + len(self.lines)
            self.lines.append({"i": index, "at": _now(), "level": level, "text": text})
            if len(self.lines) > MAX_LINES:
                overflow = len(self.lines) - MAX_LINES
                del self.lines[:overflow]
                self.dropped += overflow

    def _apply_queue_row(self, row: dict) -> None:
        """Overwrite whatever this object believed with what `worker_jobs`
        actually says. Called on every poll of a worker-backed job -- this is
        the one place a live-executing job's true state ever reaches this
        object, since nothing in this process ever sets `self.state` for one
        the way `ThreadStrategy.start`'s `body()` does for its own jobs."""
        state = row["state"]
        self.state = "finished" if state == "finished" else "failed" if state == "failed" else "running"
        self.finished_at = row["finished_at"]
        self.error = row["error"]
        self.summary = row["summary"]

    def since(self, after: int) -> tuple[list[dict], int]:
        """Lines with index > `after`, and the next index to ask for."""
        if self._queue_factory is not None:
            with self._queue_factory() as queue:
                row = queue.job_row(str(self.id))
                if row is not None:
                    self._apply_queue_row(row)
                return queue.events_since(str(self.id), after)
        with self._lock:
            start = max(0, after + 1 - self.dropped)
            chunk = self.lines[start:]
            nxt = self.dropped + len(self.lines) - 1
            return [dict(line) for line in chunk], nxt

    def head(self) -> dict:
        """The job without its log, for the list view."""
        if self._queue_factory is not None:
            with self._queue_factory() as queue:
                row = queue.job_row(str(self.id))
                if row is not None:
                    self._apply_queue_row(row)
                lines, dropped = queue.event_stats(str(self.id))
        else:
            with self._lock:
                lines = self.dropped + len(self.lines)
                dropped = self.dropped
        return {
            "id": self.id, "kind": self.kind, "label": self.label, "args": self.args,
            "state": self.state, "started_at": self.started_at,
            "finished_at": self.finished_at, "error": self.error,
            "summary": self.summary, "lines": lines, "dropped": dropped,
            "running": self.state == "running",
        }


class _JobLogHandler(logging.Handler):
    """Root-logger handler that files records into a job's line buffer.

    Filtered by thread name rather than taking everything: the same process is
    serving the browser while the run proceeds, and a review decision made in
    another tab is not part of this job's log. `runner.execute_module` renames
    its thread to the module it is running, which is what makes the filter both
    possible and stable -- serial modules run on the job's own thread and
    rename it, pooled ones are named by the executor and renamed the same way.
    """

    def __init__(self, job: Job, thread_names: set[str]) -> None:
        super().__init__(level=logging.INFO)
        self._job = job
        self._names = thread_names

    def emit(self, record: logging.LogRecord) -> None:
        if record.threadName not in self._names:
            return
        try:
            self._job.append(record.levelname.lower(), _render(record))
        except Exception:  # pragma: no cover - a log handler must never raise
            pass


def _render(record: logging.LogRecord) -> str:
    """structlog renders JSON into the message. Flatten it into one readable
    line, and fall back to the raw message for anything that is not ours."""
    message = record.getMessage()
    try:
        payload = json.loads(message)
        if not isinstance(payload, dict):
            return message
    except (ValueError, TypeError):
        return message

    event = payload.pop("event", "")
    payload.pop("timestamp", None)
    payload.pop("level", None)
    rest = " ".join(f"{k}={v}" for k, v in payload.items())
    prefix = record.threadName if record.threadName != "MainThread" else ""
    return " ".join(part for part in (f"[{prefix}]" if prefix else "", event, rest) if part)


class ThreadStrategy:
    """Run the work in this process, on its own thread.

    The seam: everything above talks to a strategy, so a subprocess-based one
    can replace this without the registry, the routes or the page changing.
    """

    name = "thread"

    def start(self, job: Job, work: Callable[[], Any], done: Callable[[Job], None],
               thread_names: set[str]) -> None:
        handler = _JobLogHandler(job, thread_names | {f"job-{job.id}"})

        def body() -> None:
            root = logging.getLogger()
            root.addHandler(handler)
            started = time.perf_counter()
            try:
                job.summary = work()
                job.state = "finished"
            except Exception as exc:
                job.state = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.append("error", job.error)
                log.exception("web.job_failed", job=job.id, label=job.label)
            finally:
                root.removeHandler(handler)
                job.finished_at = _now()
                job.append("info",
                            f"{job.state} in {time.perf_counter() - started:.1f}s")
                done(job)

        threading.Thread(target=body, name=f"job-{job.id}", daemon=True).start()


class JobStore:
    """Where the fact of a job outlives the process that ran it.

    Only the fact. The log lines stay in memory and in logs/ -- see
    migrations/0029_job_runs.sql for why they are not copied here.

    Every method swallows its own errors. Recording history is bookkeeping
    around running the pipeline, and bookkeeping that can refuse a run is worse
    than bookkeeping that is occasionally missing a row: a warehouse locked by
    something else must not be the reason a module cannot start.
    """

    def __init__(self, settings) -> None:
        self._settings = settings

    def _write(self, sql: str, params: tuple) -> None:
        from pipeline import db

        try:
            conn = db.get_connection(self._settings)
            conn.write_label = "job-store"
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        except Exception as exc:  # pragma: no cover - exercised via load()
            log.warning("web.job_store_write_failed", error=str(exc))

    def create(self, job: Job) -> None:
        # `ON CONFLICT` rather than SQLite's `INSERT OR REPLACE`, which has no
        # PostgreSQL equivalent. Not just a spelling: `INSERT OR REPLACE`
        # deletes the conflicting row and inserts a new one, so a column not
        # named here would be reset to its default. Every column this table
        # has that is not listed — finished_at, error, summary_json — is
        # written later by finish(), and create() is only ever called before
        # that, so the two behave identically for the one caller. Spelling it
        # as an upsert makes that true by construction rather than by
        # coincidence of call order.
        self._write(
            "INSERT INTO job_runs "
            "(id, kind, label, args_json, state, dry_run, started_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "kind = excluded.kind, label = excluded.label, "
            "args_json = excluded.args_json, state = excluded.state, "
            "dry_run = excluded.dry_run, started_at = excluded.started_at",
            (job.id, job.kind, job.label, json.dumps(job.args), job.state,
             1 if job.args.get("dry_run") else 0, job.started_at))

    def finish(self, job: Job) -> None:
        self._write(
            "UPDATE job_runs SET state = %s, finished_at = %s, error = %s, "
            "summary_json = %s WHERE id = %s",
            (job.state, job.finished_at, job.error,
             json.dumps(job.summary, default=str) if job.summary else None,
             job.id))

    def load(self, limit: int = 50) -> list[Job]:
        """Recent jobs, newest first, with anything left running marked.

        A row still saying 'running' cannot be running: this process has only
        just started, and the strategy runs jobs in it. That is the whole value
        of persisting them -- a run killed by a crash or a closed laptop is
        visible as an interrupted run rather than as nothing at all.
        """
        from pipeline import db

        try:
            conn = db.get_connection(self._settings)
            try:
                stale = [r["id"] for r in conn.execute(
                    "SELECT id FROM job_runs WHERE state = 'running'")]
                if stale:
                    conn.execute("UPDATE job_runs SET state = 'interrupted' "
                                  "WHERE state = 'running'")
                    conn.commit()
                    log.info("web.jobs_interrupted", jobs=stale)
                rows = conn.execute(
                    "SELECT id, kind, label, args_json, state, started_at, "
                    "       finished_at, error, summary_json "
                    "FROM job_runs ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
            finally:
                conn.close()
        except Exception as exc:
            log.warning("web.job_store_load_failed", error=str(exc))
            return []

        jobs = []
        for row in rows:
            job = Job(id=row["id"], kind=row["kind"], label=row["label"],
                       args=json.loads(row["args_json"]) if row["args_json"] else {},
                       state=row["state"], started_at=row["started_at"])
            job.finished_at = row["finished_at"]
            job.error = row["error"]
            job.summary = json.loads(row["summary_json"]) if row["summary_json"] else None
            # Its lines are not here and saying so is better than an empty log
            # that reads as a job which printed nothing.
            job.append("info", "log not retained across restart — see logs/")
            jobs.append(job)
        return jobs


class JobRegistry:
    """Every job this process has run, and at most one of them running or
    enqueued.

    The log of a `ThreadStrategy` job lives here and only here: it is a thing
    you watch while it happens, and a server restart is the end of watching.
    A worker-backed job (`enqueue_pipeline_run`) is the opposite of that on
    purpose -- its log lives in `worker_job_events`, precisely so that
    watching it does not depend on this process at all. Either way the *fact*
    of a job is handed to a `JobStore` when one is supplied, so what ran last
    night survives a restart even when its chatter does not.
    """

    def __init__(self, strategy: ThreadStrategy | None = None,
                  store: JobStore | None = None,
                  invalidate: Callable[[], None] | None = None,
                  settings: Any | None = None) -> None:
        self._strategy = strategy or ThreadStrategy()
        self._lock = threading.Lock()
        self._jobs: dict[int, Job] = {}
        self._running: int | None = None
        self._store = store
        # Called when a run finishes, to drop any read cache the warehouse it
        # just wrote has made stale. Optional and decoupled: the registry does
        # not import the cache module, it is handed a callback (bump_version),
        # so a registry built without one -- most tests -- is unaffected.
        self._invalidate = invalidate
        # Present only when this server is configured to enqueue pipeline
        # runs onto the worker queue rather than only ever running
        # ThreadStrategy jobs -- most of the generic JobRegistry tests build
        # one without it, and get exactly today's in-process behaviour.
        self._settings = settings
        self._next_id = 1
        if store is not None:
            loaded = store.load()
            worker_ids: set[str] = set()
            if self._settings is not None and loaded:
                try:
                    with self._open_queue() as queue:
                        worker_ids = queue.existing_job_ids([str(job.id) for job in loaded])
                except Exception as exc:  # pragma: no cover - defensive, like JobStore
                    log.warning("web.job_registry_queue_lookup_failed", error=str(exc))
            for job in loaded:
                if str(job.id) in worker_ids:
                    # JobStore.load() just guessed 'interrupted' for this row
                    # because *this* process never ran it -- true of every
                    # worker-backed job by construction, and wrong exactly
                    # when the worker process is still going. Wiring the live
                    # queue factory in means the very first poll corrects
                    # whatever was guessed to whatever `worker_jobs` actually
                    # says.
                    job.worker_backed = True
                    job._queue_factory = self._open_queue
                self._jobs[job.id] = job
            # Continue the sequence rather than restarting it, so a job id
            # identifies one job for the life of the warehouse. Restarting at 1
            # would make `job 3` mean two different runs in the same logs/.
            self._next_id = max(self._jobs, default=0) + 1

    def _open_queue(self):
        """A fresh, ready-to-close WorkerQueue -- never held onto, because
        its connection must never be shared across the request threads that
        will each call this. See `Job._queue_factory`."""
        from pipeline import db
        from pipeline.worker import WorkerQueue

        return WorkerQueue(db.get_connection(self._settings))

    def _queue_active_id(self) -> str | None:
        """The job_id the worker queue says is queued or running, if this
        server is configured to use one at all. Best-effort: a database
        hiccup here should cost a request its 409, not fail it outright, and
        the worker's advisory lock is the guarantee that cannot be raced past
        regardless of what this check manages to see."""
        if self._settings is None:
            return None
        try:
            with self._open_queue() as queue:
                return queue.active()
        except Exception as exc:
            log.warning("web.queue_busy_check_failed", error=str(exc))
            return None

    def running(self) -> Job | None:
        """The job holding the slot, if one still is.

        Checked two ways because the two kinds of job say so two different
        ways. A `ThreadStrategy` job's state is checked here rather than
        trusting the pointer alone: a job sets its state before the strategy
        releases the slot, so for a moment the pointer outlives the run, and
        "is something running?" should answer about the run, not the
        bookkeeping. A worker-backed job has no pointer to check in the first
        place -- `queue.active()` is the only thing that can answer for it,
        because the process holding the slot is very often not this one.
        """
        with self._lock:
            job = self._jobs.get(self._running) if self._running else None
            in_proc = job if job is not None and job.state == "running" else None
        if in_proc is not None:
            return in_proc
        active_id = self._queue_active_id()
        return self.get(int(active_id)) if active_id is not None else None

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def _refuse_if_busy(self) -> None:
        """Call while already holding `self._lock`. Raises JobError(409) if
        the single slot is taken, by either kind of job -- see the class
        docstring for why both are checked."""
        current = self._jobs.get(self._running) if self._running else None
        busy = current if current is not None and current.state == "running" else None
        active_id = None
        if busy is None:
            active_id = self._queue_active_id()
            if active_id is not None:
                busy = self._jobs.get(int(active_id))
        if busy is not None:
            raise JobError(
                f"{busy.label} is already running (job {busy.id}). "
                "One at a time: two runs against the same public sources at "
                "once is what the per-host rate limit exists to prevent.",
                status=409, job_id=busy.id)
        if active_id is not None:
            # A row this process has never heard of -- enqueued by a process
            # that no longer exists to have told us its label. Still refused;
            # there is simply nothing but the id to name.
            raise JobError(
                f"job {active_id} is already running. One at a time.",
                status=409, job_id=int(active_id))

    def start(self, kind: str, label: str, args: dict, work: Callable[[], Any],
               thread_names: set[str]) -> Job:
        """Claim the single slot and start. Raises JobError(409) if taken.

        The claim happens under the lock together with the id allocation, so
        two requests arriving at once cannot both find the slot free.
        """
        with self._lock:
            self._refuse_if_busy()
            job = Job(id=self._next_id, kind=kind, label=label, args=args)
            self._jobs[job.id] = job
            self._running = job.id
            self._next_id += 1

        if self._store is not None:
            self._store.create(job)

        def done(finished: Job) -> None:
            with self._lock:
                if self._running == finished.id:
                    self._running = None
            if self._store is not None:
                self._store.finish(finished)
            # A finished run may have written rows the public cache now
            # disagrees with. Only on success -- a failed or interrupted run
            # changed nothing worth invalidating for -- and errors are
            # swallowed for the reason the rest of this class swallows them: a
            # cache that cannot be dropped is a stale answer for a few minutes
            # until the TTL lapses, which must never be the reason a job's
            # completion callback raises. Over-invalidation (a dry run, an
            # export job) only costs a repopulate, so the test is deliberately
            # coarse.
            if self._invalidate is not None and finished.state == "finished":
                try:
                    self._invalidate()
                except Exception:  # pragma: no cover - defensive, like _write
                    log.warning("web.cache_invalidate_failed", job=finished.id)

        job.append("info", f"started: {label}")
        log.info("web.job_started", job=job.id, kind=kind, label=label, **args)
        self._strategy.start(job, work, done, thread_names)
        return job

    def enqueue_pipeline_run(self, label: str, args: dict, arguments: dict) -> Job:
        """Claim the single slot and enqueue a pipeline-module run for a
        separate `pipeline worker` process to execute -- the worker-queue
        counterpart of `start()`, for the one kind of job that no longer runs
        in this process at all.

        `args` is what the job list shows (module, since, dry_run, limit,
        jobs -- the same shape `admin.start_run` has always recorded);
        `arguments` is what `pipeline.worker.PipelineWorker` reads back on
        claim to actually run it (resolved `waves` plus those same knobs).
        They are handed separately because the row a browser polls and the
        row a worker executes are different tables with different audiences,
        and conflating them would make either one hostage to changes the
        other needs.
        """
        if self._settings is None:
            raise JobError(
                "This server has no job queue configured -- JobRegistry was "
                "built without `settings`, so there is nowhere to enqueue a "
                "pipeline run.", status=500)

        with self._lock:
            self._refuse_if_busy()
            job = Job(id=self._next_id, kind="run", label=label, args=args,
                       worker_backed=True, _queue_factory=self._open_queue)
            self._jobs[job.id] = job
            self._next_id += 1

        if self._store is not None:
            self._store.create(job)

        with self._open_queue() as queue:
            queue.enqueue("pipeline_run", arguments, job_id=str(job.id))
            queue.event(str(job.id), "info", f"queued: {label}")

        log.info("web.job_enqueued", job=job.id, label=label, **args)
        return job
