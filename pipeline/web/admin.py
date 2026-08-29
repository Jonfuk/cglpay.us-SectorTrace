"""The operator API behind the Pipeline tab: what can be run, and running it.

Separate from `queries` because the audience is different again. `queries`
reads the warehouse; this reads the *pipeline* -- which modules exist, what
each one depends on, when it last got anywhere -- and is the only place in the
web layer that causes anything to happen to the outside world.

Everything it hands back about a run comes from pipeline/runner.py, so the run
a browser starts is the run the CLI would have started. The planning below is
the one piece deliberately duplicated from `cli.run`, whose own version is
interleaved with the messages it prints to a terminal; the two are held
together by a test that asserts they resolve identical waves rather than by a
shared function that would have to serve both a browser and a console.
"""
from __future__ import annotations

import structlog

from pipeline import db, runner
from pipeline.registry import (
    MODULE_REGISTRY,
    DependencyCycleError,
    discover_modules,
    missing_dependencies,
    module_meta,
    resolve_run_order,
    resolve_run_waves,
)
from pipeline.web.jobs import JobError

log = structlog.get_logger()


def registry() -> dict:
    """The module registry, populated. Discovery is idempotent and cheap after
    the first call, so this is safe to do per request."""
    discover_modules()
    return MODULE_REGISTRY


def modules(conn) -> dict:
    """Every registered module with the state that decides whether to run it.

    One query per fact rather than per module: sixteen modules times four
    lookups is sixty-four round trips to answer a page that opens on every
    visit to the tab.
    """
    names = sorted(registry())
    meta = {name: module_meta(name) for name in names}

    cursors = {row["module"]: row for row in conn.execute(
        "SELECT module, cursor_value, updated_at FROM module_cursors")}
    pending = {row["module"]: row["n"] for row in conn.execute(
        "SELECT module, COUNT(*) AS n FROM review_queue "
        "WHERE status = 'pending' GROUP BY module")}
    failures = {row["module"]: row["n"] for row in conn.execute(
        "SELECT module, COUNT(*) AS n FROM parse_failures GROUP BY module")}

    unmet = missing_dependencies(names)
    waves = {}
    try:
        for index, wave in enumerate(resolve_run_waves(names), start=1):
            for name in wave:
                waves[name] = index
    except DependencyCycleError:
        # A cycle makes `run all` impossible but says nothing about running one
        # module, which is the more useful thing to still be able to do from
        # here. Reported as an unknown wave rather than a failed request.
        waves = {}

    out = []
    for name in names:
        cursor = cursors.get(name)
        out.append({
            "name": name,
            "wave": waves.get(name),
            "supports_since": meta[name].supports_since,
            "since_note": meta[name].since_note,
            "depends_on": list(meta[name].depends_on),
            "depends_note": meta[name].depends_note,
            "missing_dependencies": unmet.get(name, []),
            "cursor_value": cursor["cursor_value"] if cursor else None,
            "cursor_updated_at": cursor["updated_at"] if cursor else None,
            "pending_review": pending.get(name, 0),
            "parse_failures": failures.get(name, 0),
        })
    return {"modules": out, "waves": max(waves.values()) if waves else 0}


def plan(module: str, since: str | None, limit: int | None) -> dict:
    """Validate a run request and work out what it would do.

    Refuses rather than interprets, in the same places `cli.run` refuses:
    an unknown module name, a `--limit` of zero (every module tests `if
    ctx.limit:`, so zero reads as "no limit at all" and would launch a full
    live crawl), and an unparseable `since`.
    """
    known = registry()

    if module == "all":
        try:
            order = resolve_run_order()
        except DependencyCycleError as exc:
            raise JobError(str(exc)) from None
        targets = list(order)
    elif module in known:
        targets = [module]
    else:
        available = ", ".join(sorted(known)) or "(none registered)"
        raise JobError(f"Unknown module {module!r}. Available: {available}", status=404)

    if limit is not None and limit < 1:
        raise JobError(
            f"limit must be 1 or more; got {limit}. Use a dry run to fetch and "
            "parse without writing.")

    ignoring: list[str] = []
    if since:
        from pipeline.registry import ModuleContext

        try:
            ModuleContext(conn=None, settings=None, since=since,
                           dry_run=False, limit=None).since_date()
        except ValueError as exc:
            raise JobError(str(exc)) from None
        ignoring = [name for name in targets if not module_meta(name).supports_since]

    return {
        "targets": targets,
        "waves": resolve_run_waves(targets),
        # Not errors: the run proceeds. They are the things `cli.run` prints to
        # stderr before starting, and leaving them out of the browser would
        # make the same run look cleaner than it is.
        "since_ignored_by": ignoring,
        "missing_dependencies": missing_dependencies(targets),
    }


def _whole(name: str, value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise JobError(f"{name} must be a whole number, got {value!r}.") from None


def start_run(registry_of_jobs, settings, body: dict):
    """Plan a run, claim the single job slot, and start it."""
    module = str(body.get("module") or "").strip()
    if not module:
        raise JobError("Which module? Pass a module name or 'all'.")

    since = (body.get("since") or "").strip() or None
    dry_run = bool(body.get("dry_run"))

    # Written out rather than `body.get("limit") or None`, and not with a
    # membership test either: 0 == False in Python, so `limit in (None, "",
    # False)` swallows a limit of zero and turns the one value `plan` exists to
    # refuse into "no limit at all" -- a full live crawl.
    raw_limit = body.get("limit")
    limit = None if raw_limit is None or raw_limit == "" else _whole("limit", raw_limit)

    raw_jobs = body.get("jobs")
    jobs = 1 if raw_jobs is None or raw_jobs == "" else _whole("jobs", raw_jobs)
    if jobs < 1:
        raise JobError(f"jobs must be 1 or more; got {jobs}.")

    shape = plan(module, since, limit)
    waves = shape["waves"]
    known = registry()

    def work() -> list[dict]:
        # Migrations first, on a writable connection, exactly as `cli.run`
        # does: a warehouse built before a module's tables arrived would
        # otherwise fail part-way through the run rather than before it.
        conn = db.get_connection(settings)
        try:
            db.apply_migrations(conn)
        finally:
            conn.close()

        summary = runner.run_waves(waves, jobs, settings, since, dry_run, limit,
                                    _LoggingObserver(), origin="admin")
        # Exceptions are already inside the rows; surface them as text so the
        # summary survives JSON.
        return [{**row, "error": (f"{type(row['error']).__name__}: {row['error']}"
                                   if row.get("error") is not None else None)}
                 for row in summary]

    label = module if module != "all" else f"all ({len(shape['targets'])} modules)"
    if dry_run:
        label = f"{label} — dry run"

    return registry_of_jobs.start(
        kind="run", label=label,
        args={"module": module, "since": since, "dry_run": dry_run,
               "limit": limit, "jobs": jobs},
        work=work,
        # The threads whose log lines belong to this job. runner.execute_module
        # renames its thread to the module it is running, so these are the
        # names that will appear on the records.
        thread_names=set(shape["targets"]) | {name for name in known},
    )


def start_export(registry_of_jobs, settings, body: dict):
    """Write an export target, as a job.

    Same job slot as a module run, which is right for a different reason than
    the integrity check: an export reads the whole warehouse and writes files
    named after what it found, so running one while a module is rewriting the
    tables underneath it produces an artefact that matches no moment in time.
    """
    from pathlib import Path

    from pipeline.exports import run as export_run
    from pipeline.web import artefacts

    target = str(body.get("target") or "").strip()
    if not target:
        raise JobError(f"Which target? One of {', '.join(export_run.TARGETS)}, or all.")

    try:
        targets = export_run.resolve_targets(target)
    except export_run.ExportError as exc:
        raise JobError(str(exc), status=404) from None

    base = artefacts.export_root(settings)
    docs_dir = Path(settings.logs_dir).parent / "docs"

    def work() -> list[dict]:
        conn = db.get_connection(settings)
        try:
            db.apply_migrations(conn)
            # push=False, always. Sending tabs to a shared Google document
            # needs credentials and someone watching; it stays a CLI flag.
            results = export_run.run_targets(conn, targets, base, docs_dir,
                                              settings, push=False)
            conn.commit()
        finally:
            conn.close()
        return results

    return registry_of_jobs.start(
        kind="export", label=f"export {target}",
        args={"target": target}, work=work, thread_names=set())


class _LoggingObserver(runner.RunObserver):
    """A run reported through structlog, which the job's handler is capturing.

    The CLI's observer paints a progress bar; there is no bar here, and the
    honest equivalent of one over HTTP is a line saying what started and what
    it did. `phase()` calls from inside modules come through the same way, so
    the browser sees "m05_cqc — paging provider index" while it happens.
    """

    def run_starting(self, total_modules: int) -> None:
        log.info("run.starting", modules=total_modules)

    def wave_starting(self, names: list[str], width: int) -> None:
        log.info("run.wave", modules=", ".join(names), at_a_time=width)

    def module_progress(self, name: str):
        return _phase_reporter(name)

    def module_finished(self, row: dict) -> None:
        if row["status"] == "failed":
            log.warning("run.module_failed", module=row["module"],
                         error=str(row.get("error")), seconds=round(row["elapsed"], 1))
        else:
            log.info("run.module_done", module=row["module"],
                      seconds=round(row["elapsed"], 1), rows=row.get("rows", 0),
                      review=row.get("review", 0), failures=row.get("failures", 0))


class _PhaseReporter:
    """The ProgressReporter shape, logging instead of drawing.

    `track` must yield the items unchanged -- it is wrapped around real loops
    inside modules, and anything clever here would change what a run collects.
    """

    def __init__(self, module: str) -> None:
        self._module = module

    def phase(self, text: str) -> None:
        log.info("run.phase", module=self._module, phase=text)

    def track(self, items, description: str, total: int | None = None):
        log.info("run.phase", module=self._module, phase=description,
                  items=(total if total is not None else _length_of(items)))
        return iter(items)


def _length_of(items) -> str:
    try:
        return len(items)
    except TypeError:
        return "?"


class _phase_reporter:  # noqa: N801 - used as a context manager, not a class
    """`module_progress` has to be a context manager; there is nothing to tear
    down on this side, so this is the whole of it."""

    def __init__(self, module: str) -> None:
        self._module = module

    def __enter__(self) -> _PhaseReporter:
        log.info("run.module_starting", module=self._module)
        return _PhaseReporter(self._module)

    def __exit__(self, *exc_info) -> bool:
        return False
