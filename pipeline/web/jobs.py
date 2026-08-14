"""Long jobs started from the browser, and the log they produce while running.

A module run takes minutes to hours. An HTTP request cannot hold that open, so
a job is started, given an id, and polled: `POST /api/admin/run` returns
immediately and `GET /api/admin/jobs/{id}?after=N` hands back whatever lines
have appeared since line N.

Three things here are deliberate.

  * **One job at a time.** Not a queue -- a refusal, with the running job's id
    in the reply. The warehouse has a single write slot (pipeline/parallel.py),
    so a second concurrent run would spend its life waiting on the first, and
    two runs hitting the same public sources at once is exactly what the
    per-host rate limit exists to prevent. A queue would hide that; a 409 says
    it.

  * **The log is captured, not invented.** Modules already log everything they
    do through structlog. A handler is attached to the root logger for the
    length of the job and filtered to the threads the run is using, so what
    the browser shows is the same audit trail that lands in logs/, not a
    parallel commentary that could disagree with it.

  * **Execution sits behind a seam.** `ThreadStrategy` runs the work in this
    process, which is the simplest thing that reuses pipeline.runner exactly as
    the CLI calls it. It cannot be cancelled and a hard interpreter crash would
    take the server with it; if either turns out to matter, a subprocess
    strategy goes in beside it without the job registry or the UI noticing.

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
    # into this log means the same thing for the whole life of the job.
    lines: list[dict] = field(default_factory=list)
    dropped: int = 0

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def append(self, level: str, text: str) -> None:
        with self._lock:
            index = self.dropped + len(self.lines)
            self.lines.append({"i": index, "at": _now(), "level": level, "text": text})
            if len(self.lines) > MAX_LINES:
                overflow = len(self.lines) - MAX_LINES
                del self.lines[:overflow]
                self.dropped += overflow

    def since(self, after: int) -> tuple[list[dict], int]:
        """Lines with index > `after`, and the next index to ask for."""
        with self._lock:
            start = max(0, after + 1 - self.dropped)
            chunk = self.lines[start:]
            nxt = self.dropped + len(self.lines) - 1
            return [dict(line) for line in chunk], nxt

    def head(self) -> dict:
        """The job without its log, for the list view."""
        with self._lock:
            lines = self.dropped + len(self.lines)
        return {
            "id": self.id, "kind": self.kind, "label": self.label, "args": self.args,
            "state": self.state, "started_at": self.started_at,
            "finished_at": self.finished_at, "error": self.error,
            "summary": self.summary, "lines": lines, "dropped": self.dropped,
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
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (id) DO UPDATE SET "
            "kind = excluded.kind, label = excluded.label, "
            "args_json = excluded.args_json, state = excluded.state, "
            "dry_run = excluded.dry_run, started_at = excluded.started_at",
            (job.id, job.kind, job.label, json.dumps(job.args), job.state,
             1 if job.args.get("dry_run") else 0, job.started_at))

    def finish(self, job: Job) -> None:
        self._write(
            "UPDATE job_runs SET state = ?, finished_at = ?, error = ?, "
            "summary_json = ? WHERE id = ?",
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
                stale = [r[0] for r in conn.execute(
                    "SELECT id FROM job_runs WHERE state = 'running'")]
                if stale:
                    conn.execute("UPDATE job_runs SET state = 'interrupted' "
                                  "WHERE state = 'running'")
                    conn.commit()
                    log.info("web.jobs_interrupted", jobs=stale)
                rows = conn.execute(
                    "SELECT id, kind, label, args_json, state, started_at, "
                    "       finished_at, error, summary_json "
                    "FROM job_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            finally:
                conn.close()
        except Exception as exc:
            log.warning("web.job_store_load_failed", error=str(exc))
            return []

        jobs = []
        for row in rows:
            job = Job(id=row[0], kind=row[1], label=row[2],
                       args=json.loads(row[3]) if row[3] else {},
                       state=row[4], started_at=row[5])
            job.finished_at = row[6]
            job.error = row[7]
            job.summary = json.loads(row[8]) if row[8] else None
            # Its lines are not here and saying so is better than an empty log
            # that reads as a job which printed nothing.
            job.append("info", "log not retained across restart — see logs/")
            jobs.append(job)
        return jobs


class JobRegistry:
    """Every job this process has run, and at most one of them running.

    The log of a job lives here and only here: it is a thing you watch while it
    happens, and a server restart is the end of watching. The *fact* of a job
    is handed to a `JobStore` when one is supplied, so what ran last night
    survives the restart even though its chatter does not.
    """

    def __init__(self, strategy: ThreadStrategy | None = None,
                  store: JobStore | None = None) -> None:
        self._strategy = strategy or ThreadStrategy()
        self._lock = threading.Lock()
        self._jobs: dict[int, Job] = {}
        self._running: int | None = None
        self._store = store
        self._next_id = 1
        if store is not None:
            for job in store.load():
                self._jobs[job.id] = job
            # Continue the sequence rather than restarting it, so a job id
            # identifies one job for the life of the warehouse. Restarting at 1
            # would make `job 3` mean two different runs in the same logs/.
            self._next_id = max(self._jobs, default=0) + 1

    def running(self) -> Job | None:
        """The job holding the slot, if one still is.

        The state is checked as well as the pointer. A job sets its state
        before the strategy releases the slot, so for a moment the pointer
        outlives the run -- and "is something running?" should answer about the
        run, not about the bookkeeping.
        """
        with self._lock:
            job = self._jobs.get(self._running) if self._running else None
            return job if job is not None and job.state == "running" else None

    def get(self, job_id: int) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.id, reverse=True)

    def start(self, kind: str, label: str, args: dict, work: Callable[[], Any],
               thread_names: set[str]) -> Job:
        """Claim the single slot and start. Raises JobError(409) if taken.

        The claim happens under the lock together with the id allocation, so
        two requests arriving at once cannot both find the slot free.
        """
        with self._lock:
            current = self._jobs.get(self._running) if self._running else None
            if current is not None and current.state == "running":
                raise JobError(
                    f"{current.label} is already running (job {current.id}). "
                    "One at a time: the warehouse has a single write slot and "
                    "two runs would queue behind each other anyway.",
                    status=409, job_id=current.id)

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

        job.append("info", f"started: {label}")
        log.info("web.job_started", job=job.id, kind=kind, label=label, **args)
        self._strategy.start(job, work, done, thread_names)
        return job
