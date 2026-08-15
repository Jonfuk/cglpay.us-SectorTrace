"""Fetching several hosts at once, without giving up anything that matters.

The council-walking modules (m09, m10, m15) are the slow part of this
pipeline, and they are slow for a reason that has nothing to do with
politeness: they visit a few hundred *different* councils one after another,
waiting two seconds between requests to hosts that have never heard of each
other. Measured on 2026-08-11, m10 took ~52 seconds per council; across 315
authorities that is roughly four and a half hours of mostly sleeping.

Running those concurrently is free in politeness terms — a council is not
hit any harder because a different council is being read at the same time —
provided two things hold:

  1. **The rate limit is enforced per host across the whole process.** That is
     `pipeline.http.HOST_CLOCK`, and it is why this module can exist. Two
     workers that land on the same host queue behind each other correctly.

  2. **Only one thread writes evidence.** Workers fetch and parse; they
     return what they found and the caller writes it on the module's own
     connection. This keeps the transaction semantics the CLI already relies
     on — commit per module, roll back the module's partial writes on failure
     — instead of scattering them across threads.

The one piece of database work a worker unavoidably does is the HTTP
conditional-request cache, since `PipelineHTTPClient` reads and writes it on
every fetch. Each thread therefore gets its own client with its own
connection, **opened in that thread**, so no connection object ever crosses a
thread boundary and `check_same_thread` can stay on.

What a worker does with a cache entry depends on the backend, and this is the
one place in the pipeline where that is true:

  * **SQLite** — buffered, and flushed by the caller once the pool has
    finished. A worker writing here would take the single writer slot that
    the main thread is holding while it commits evidence, and block for the
    whole busy_timeout, over and over. That was observed as a hung test
    suite, not predicted.
  * **PostgreSQL** — written and committed by the worker itself, because
    there is no slot to take. Phase 4; the plan named the deferral as
    machinery that PostgreSQL makes unnecessary, and it is.

Either way the cache is a fetch optimisation and not evidence, and it is
consistent with the raw archive on both paths because archiving already
happens regardless of `--dry-run`.

Results come back in submission order, not completion order. Two runs of the
same checkout should do the same work in the same sequence — the same reason
`resolve_run_order` breaks ties alphabetically. A run whose log order depends
on which council answered first is a run you cannot diff against yesterday's.
"""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, TypeVar

import structlog

from pipeline.config import Settings
from pipeline.http import PipelineHTTPClient

log = structlog.get_logger()

Unit = TypeVar("Unit")
Value = TypeVar("Value")

# Enough to turn hours into minutes, small enough that a run does not look
# like a denial of service to anyone watching their own logs. Every worker is
# on a different host by construction; workers that collide on one host
# serialise on HOST_CLOCK rather than doubling its rate.
DEFAULT_MAX_WORKERS = 8


@dataclass(frozen=True)
class Outcome:
    """What one unit of work produced, including the case where it failed."""

    unit: Any
    value: Any = None
    error: BaseException | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class _ClientPool:
    """One PipelineHTTPClient per worker thread, built lazily in that thread.

    Not shared: httpx clients are thread-safe but the SQLite connection behind
    the conditional-request cache is not, and building the client where it
    will be used is simpler to reason about than guarding it.
    """

    def __init__(self, source_system: str, settings: Settings,
                  configure: Callable[[PipelineHTTPClient], None] | None = None) -> None:
        self._source_system = source_system
        self._settings = settings
        self._configure = configure
        self._local = threading.local()
        self._all: list[tuple[PipelineHTTPClient, Any]] = []
        self._lock = threading.Lock()

    def get(self) -> PipelineHTTPClient:
        client = getattr(self._local, "client", None)
        if client is None:
            from pipeline import db

            # check_same_thread=False buys exactly one thing: the ability to
            # close these from the main thread in close(), after the executor
            # has joined every worker. During the run each connection is used
            # by the single thread that created it, and close() happens only
            # once nothing is running — so there is no point at which two
            # threads touch one connection. Without this the pool leaks a
            # connection per thread, because a worker thread has no shutdown
            # hook of its own to close it in.
            conn = db.get_connection(self._settings, check_same_thread=False)
            client = PipelineHTTPClient(self._source_system, settings=self._settings, conn=conn)
            # Deferring is SQLite's answer to SQLite's single writer. On
            # PostgreSQL a worker writes its own cache entries on its own
            # connection, which is what the module docstring above has always
            # wished were true — see `PipelineHTTPClient` for why the commit
            # travels with it.
            if db.backend_of(conn) == "sqlite":
                client.defer_cache_writes = True
            else:
                client.commit_cache_writes = True
            if self._configure is not None:
                self._configure(client)
            self._local.client = client
            self._local.conn = conn
            with self._lock:
                self._all.append((client, conn))
        return client

    def close(self) -> list[dict]:
        """Shut every worker client down and hand back their deferred
        conditional-request cache entries for the caller to write.
        """
        with self._lock:
            pending, self._all = self._all, []
        cache_writes: list[dict] = []
        for client, conn in pending:
            cache_writes.extend(client.pending_cache_writes)
            client.close()
            conn.close()
        return cache_writes


def fetch_in_parallel(
    units: Iterable[Unit],
    worker: Callable[[Unit, PipelineHTTPClient], Value],
    *,
    source_system: str,
    settings: Settings,
    max_workers: int | None = None,
    configure_client: Callable[[PipelineHTTPClient], None] | None = None,
    cache_conn: Any = None,
) -> Iterator[Outcome]:
    """Run `worker(unit, client)` across a thread pool, in submission order.

    `worker` must not touch the module's database connection. It fetches,
    parses, and returns whatever the caller needs in order to write — the
    caller does the writing, single-threaded, on its own connection.

    A worker that raises does not stop the run: the exception comes back on
    that unit's Outcome so the caller can record it and carry on. One council
    with a broken TLS chain should cost one council, not the crawl.

    Pass `cache_conn` (the module's connection) to keep conditional requests
    working across runs on SQLite, where worker threads cannot write the HTTP
    cache themselves — SQLite allows one writer and the main thread holds that
    slot while committing evidence — so their entries are buffered and flushed
    here once the pool has finished and nothing else is running.

    On PostgreSQL the workers have already written and committed their own,
    so there is nothing to flush and `cache_conn` is unused. Still worth
    passing: which backend a module is running against is not a module's
    business, and a call site that dropped the argument would quietly stop
    caching the day someone unset `DATABASE_URL`.
    """
    units = list(units)
    if not units:
        return

    workers = max_workers or DEFAULT_MAX_WORKERS
    workers = max(1, min(workers, len(units)))
    pool = _ClientPool(source_system, settings, configure_client)

    def run_one(unit: Unit) -> Value:
        return worker(unit, pool.get())

    log.info("parallel.start", source_system=source_system,
              units=len(units), workers=workers)
    try:
        with ThreadPoolExecutor(max_workers=workers,
                                 thread_name_prefix=f"fetch-{source_system}") as executor:
            futures = [executor.submit(run_one, unit) for unit in units]
            for unit, future in zip(units, futures):
                try:
                    yield Outcome(unit=unit, value=future.result())
                except BaseException as exc:   # noqa: BLE001 - reported, not swallowed
                    yield Outcome(unit=unit, error=exc)
    finally:
        deferred = pool.close()
        if cache_conn is not None and deferred:
            from pipeline import db

            # The executor has joined every worker by now, so this is the only
            # thread running. Last write wins on a repeated URL, which is the
            # same as the serial behaviour.
            for entry in deferred:
                db.set_http_cache(cache_conn, **entry)
            log.info("parallel.cache_flushed", source_system=source_system,
                      entries=len(deferred))


def worker_count(settings: Settings, limit: int | None = None) -> int:
    """How many workers to use, honouring the setting and any --limit.

    A `--limit 5` smoke run should not open eight connections to fetch five
    things.
    """
    configured = getattr(settings, "max_fetch_workers", DEFAULT_MAX_WORKERS)
    if limit:
        return max(1, min(configured, limit))
    return max(1, configured)
