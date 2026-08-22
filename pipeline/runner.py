"""Executing modules, with or without a terminal attached.

This was inside cli.py, which was the right place for it while the CLI was the
only thing that ran a module. The web UI now runs them too, and the one thing
that must not happen is two subtly different ways to run this pipeline: the
dependency waves, the connection per module, the rollback on failure, the
audit-count deltas and the write-slot discipline are not presentation details
that a second caller can reasonably reimplement.

So the execution lives here and knows nothing about how it is being watched.
What differs between callers is only that -- the CLI paints a Rich progress
display, the web UI appends lines to a job log -- and that difference is a
`RunObserver`, whose default implementation does nothing at all. A module
collects exactly the same evidence whether or not anything is looking.

Nothing in this file imports rich, typer or anything under pipeline.web.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Iterator

import structlog

from pipeline import db
from pipeline.registry import MODULE_REGISTRY, ModuleContext

log = structlog.get_logger()


class RunObserver:
    """Where a run reports what it is doing.

    Every method is a no-op here, and that is a complete implementation rather
    than an abstract base to be filled in: `run_waves(..., RunObserver())` is
    the correct way to run modules with nothing watching.
    """

    def run_starting(self, total_modules: int) -> None:
        """Once, before the first wave."""

    def wave_starting(self, names: list[str], width: int) -> None:
        """Only for waves that actually run concurrently -- a wave of one is
        indistinguishable from serial execution and saying so is noise."""

    @contextmanager
    def module_progress(self, name: str) -> Iterator:
        """A progress reporter for one module, for the length of its run.

        A context manager because the display side of this is a task that has
        to be removed again: sixteen modules leaving sixteen dead bars on
        screen was the bug that shaped it.
        """
        from pipeline.console import NULL_REPORTER

        yield NULL_REPORTER

    def module_finished(self, row: dict) -> None:
        """After each module, with the row that will appear in the summary."""


def audit_counts(conn, module: str) -> dict[str, int]:
    """Review items and parse failures already recorded for this module.

    Both deduplicate on a natural key, so a re-run that finds the same
    problems adds nothing — the delta reported in the summary is genuinely
    what this run newly could not resolve.
    """
    def count(table: str) -> int:
        try:
            return conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE module = ?", (module,)).fetchone()[0]
        except Exception:
            return 0

    return {"review": count("review_queue"), "failures": count("parse_failures")}


def execute_module(name: str, fn, settings, since, dry_run, limit,
                    observer: RunObserver, source: str = "all") -> dict:
    """Run one module on its own connection, and report what it did.

    A connection per module rather than one shared across the run. That is
    required for concurrency — SQLite objects cannot cross threads — but it is
    better serially too: a module that fails now rolls back only its own
    writes, where a shared connection could roll back work belonging to
    whatever else had touched it.

    Never raises. The outcome, including a failure, comes back in the summary
    so one module cannot take the run down with it.
    """
    started = time.perf_counter()
    with observer.module_progress(name) as reporter:
        # Name the thread after the module, so the write slot can say who is
        # holding it and every log line from a wave is attributable.
        #
        # Restored afterwards, which matters more than it looks. The serial
        # path runs modules on the caller's own thread, so without this the
        # CLI's main thread stays named after whichever module ran last and
        # every subsequent log line is attributed to a module that finished
        # minutes ago. It also makes "is this thread inside a module right
        # now?" a question the thread's name actually answers, which is what
        # the web job log filters on.
        thread = threading.current_thread()
        previous_name = thread.name
        thread.name = name
        conn = db.get_connection(settings)
        conn.write_label = name
        try:
            # What this run was asked to do, in the module's own log, before it
            # does any of it. A dry run rolls back below and leaves a warehouse
            # identical to the one it started with, so without this line the
            # only record of a run that wrote nothing on purpose is
            # indistinguishable from a parser that silently collected nothing
            # -- which is the most misleading state this pipeline can be in.
            log.info("module.starting", module=name, dry_run=dry_run,
                      since=str(since) if since else None, limit=limit)
            before = audit_counts(conn, name)
            changes_before = conn.total_changes
            ctx = ModuleContext(conn=conn, settings=settings, since=since,
                                 dry_run=dry_run, limit=limit, source=source,
                                 progress=reporter)
            try:
                fn(ctx)
            except Exception as exc:
                conn.rollback()
                log.info("module.finished", module=name, status="failed",
                          dry_run=dry_run, error=f"{type(exc).__name__}: {exc}")
                return {"module": name, "status": "failed", "dry_run": dry_run,
                         "elapsed": time.perf_counter() - started, "error": exc}

            if dry_run:
                conn.rollback()
            else:
                conn.commit()

            after = audit_counts(conn, name)
            row = {
                "module": name, "status": "ok", "dry_run": dry_run,
                "elapsed": time.perf_counter() - started,
                "rows": conn.total_changes - changes_before,
                "review": after["review"] - before["review"],
                "failures": after["failures"] - before["failures"],
            }
            # `rows` counts changes this module made. On a dry run they were
            # made and then rolled back, so the number is what it *would* have
            # written -- worth reporting, and worth never reporting bare.
            log.info("module.finished", **{k: v for k, v in row.items()
                                            if k != "elapsed"},
                      wrote=not dry_run)
            return row
        finally:
            conn.close()
            thread.name = previous_name


def run_waves(waves: list[list[str]], jobs: int, settings, since, dry_run, limit,
               observer: RunObserver | None = None, source: str = "all") -> list[dict]:
    """Each wave concurrently, waves in order.

    Every module in a wave has its dependencies satisfied by an earlier wave,
    so within a wave there is nothing to order. Concurrency across modules is
    safe because the per-host rate limit is enforced process-wide: modules on
    different APIs proceed independently, and the four sharing www.gov.uk
    queue behind each other on that host alone.

    A wave is joined before the next begins, so a module never starts before
    the module whose output it reads has finished.
    """
    observer = observer or RunObserver()
    total_modules = sum(len(wave) for wave in waves)
    observer.run_starting(total_modules)

    summary: list[dict] = []
    for wave in waves:
        width = max(1, min(jobs, len(wave)))
        if width == 1:
            for name in wave:
                row = execute_module(
                    name, MODULE_REGISTRY[name], settings, since, dry_run, limit, observer,
                    source=source)
                summary.append(row)
                observer.module_finished(row)
            continue

        observer.wave_starting(list(wave), width)
        with ThreadPoolExecutor(max_workers=width, thread_name_prefix="module") as pool:
            futures = [pool.submit(execute_module, name, MODULE_REGISTRY[name],
                                    settings, since, dry_run, limit, observer, source=source)
                        for name in wave]
            # Collected in submission order, so the summary reads the same way
            # twice regardless of which API answered first.
            for future in futures:
                row = future.result()
                summary.append(row)
                observer.module_finished(row)
    return summary
