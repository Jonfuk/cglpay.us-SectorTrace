from __future__ import annotations

import time

import typer

from pipeline import console as ui
from pipeline import db
from pipeline.config import get_settings
from pipeline.logging_conf import configure_logging
from pipeline.registry import (
    MODULE_REGISTRY,
    DependencyCycleError,
    ModuleContext,
    discover_modules,
    missing_dependencies,
    module_meta,
    resolve_run_order,
    resolve_run_waves,
)

app = typer.Typer(help="England-wide substance misuse sector evidence pipeline")


@app.command("list-modules")
def list_modules() -> None:
    """List every module currently registered with the CLI."""
    discover_modules()
    if not MODULE_REGISTRY:
        typer.echo("No modules registered yet.")
        return
    for name in sorted(MODULE_REGISTRY):
        typer.echo(name)


@app.command()
def export(
    target: str = typer.Argument(..., help="sheets | geojson | echarts | docs | all"),
    output_dir: str = typer.Option("exports/output", help="Where to write export files"),
    push: bool = typer.Option(False, "--push", help="Also push Sheets tabs to Google (needs credentials)"),
) -> None:
    """Generate exports. Every file is written with a companion .provenance.json."""
    from pathlib import Path

    configure_logging(f"export_{target}")
    settings = get_settings()
    conn = db.get_connection(settings)
    db.apply_migrations(conn)

    from pipeline.exports import docs as docs_export
    from pipeline.exports import echarts as echarts_export
    from pipeline.exports import geojson as geojson_export
    from pipeline.exports import sheets as sheets_export

    base = Path(output_dir)
    docs_dir = Path(settings.logs_dir).parent / "docs"
    targets = ["sheets", "geojson", "echarts", "docs"] if target == "all" else [target]

    for name in targets:
        if name == "sheets":
            paths = sheets_export.export_sheets(conn, base / "sheets", push, settings)
            typer.echo(f"sheets: {len(paths)} tabs -> {base / 'sheets'}")
        elif name == "geojson":
            paths = geojson_export.export_all(conn, base / "geojson")
            typer.echo(f"geojson: {len(paths)} layers -> {base / 'geojson'}")
        elif name == "echarts":
            paths = echarts_export.export_all(conn, base / "echarts")
            typer.echo(f"echarts: {len(paths)} charts -> {base / 'echarts'}")
        elif name == "docs":
            path = docs_export.write_data_dictionary(conn, settings.migrations_dir, docs_dir)
            typer.echo(f"docs: wrote {path}")
        else:
            typer.echo(f"Unknown export target {name!r}. "
                        "Use sheets, geojson, echarts, docs or all.", err=True)
            conn.close()
            raise typer.Exit(code=1)

    conn.commit()
    conn.close()


@app.command()
def web(
    port: int = typer.Option(1801, help="Port to listen on"),
    host: str = typer.Option(
        # No em dash: Typer writes help straight to a console that is cp1252
        # on Windows, where it arrives as a replacement character.
        "127.0.0.1", help="Address to bind. Loopback by default; see the warning it prints."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the UI in a browser once it is listening"),
) -> None:
    """Browse the warehouse and decide review-queue items in a browser.

    Reading is done on a read-only connection, so nothing the browser or the
    SQL box does can modify the warehouse. The only writes are review
    decisions, and each one records who made it and when.
    """
    import webbrowser

    from pipeline.web.server import build_server

    configure_logging("web")
    settings = get_settings()

    # Migrations first, on a writable connection: the decisions table arrives
    # in 0026 and the UI would otherwise fail on a warehouse built before it.
    # It also restores the -shm file a read-only connection cannot create for
    # itself, which is what the browsing connections need.
    conn = db.get_connection(settings)
    applied = db.apply_migrations(conn)
    if applied:
        typer.echo(f"Applied migrations: {', '.join(applied)}")
    pending = conn.execute(
        "SELECT COUNT(*) FROM review_queue WHERE status = 'pending'").fetchone()[0]
    conn.close()

    try:
        server = build_server(settings, host, port)
    except OSError as exc:
        ui.error(f"Cannot listen on {host}:{port} — {exc}")
        ui.muted("  Another copy may already be running. Use --port to pick a different one.")
        raise typer.Exit(code=1)

    url = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{server.server_address[1]}"
    ui.heading(f"Review UI on {url}")
    ui.info(f"  warehouse: [pipeline.muted]{settings.database_path}[/]")
    ui.info(f"  {pending:,} item(s) pending review")
    if host not in ("127.0.0.1", "localhost", "::1"):
        # Worth interrupting for. There is no login on this server, and the
        # warehouse holds restricted_ tables of personal data — company
        # officers, CQC contacts, named individuals from PFD reports.
        ui.warn(f"  bound to {host}, which is reachable from other machines. "
                 "There is no authentication, and the warehouse contains "
                 "personal data in restricted_ tables.")
    ui.muted("  Ctrl-C to stop.")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ui.muted("\n  stopped.")
    finally:
        server.server_close()


def _audit_counts(conn, module: str) -> dict[str, int]:
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


def _print_summary(summary: list[dict], dry_run: bool) -> None:
    if not summary:
        return
    from pipeline.meters import DISK, NETWORK, human_bytes

    ui.console().print()
    ui.console().print(ui.run_summary(summary))
    if NETWORK.total or DISK.total:
        # The network figure is worth keeping after the run, not just during
        # it: it is what this pipeline asked of public sources, which is the
        # number to quote if one of them ever asks.
        ui.muted(f"  {human_bytes(NETWORK.total)} downloaded, "
                  f"{human_bytes(DISK.total)} written to data/")
    if dry_run:
        ui.warn("--dry-run: everything above was rolled back, nothing was written.")

    review = sum(row.get("review", 0) for row in summary)
    failures = sum(row.get("failures", 0) for row in summary)
    if review or failures:
        # Not an error. An empty cell with a logged reason is the correct
        # output of this pipeline, so these are surfaced as work to look at
        # rather than as something that went wrong.
        ui.muted(f"  {review:,} new review item(s), {failures:,} new parse failure(s) "
                  "— see docs/CAVEATS.md for how to read them:")
        ui.muted("    sqlite3 data/warehouse.db \"SELECT module, item_type, COUNT(*) "
                  "FROM review_queue WHERE status='pending' GROUP BY 1,2;\"")


def _execute_module(name: str, fn, settings, since, dry_run, limit, bar) -> dict:
    """Run one module on its own connection, and report what it did.

    A connection per module rather than one shared across the run. That is
    required for concurrency — SQLite objects cannot cross threads — but it is
    better serially too: a module that fails now rolls back only its own
    writes, where a shared connection could roll back work belonging to
    whatever else had touched it.

    Never raises. The outcome, including a failure, comes back in the summary
    so one module cannot take the run down with it.
    """
    from pipeline.registry import ModuleContext

    started = time.perf_counter()
    # A task per module, always, with no total. Rich renders that as a pulsing
    # bar, which is the honest display for work whose size is not known up
    # front — and it means the screen is never blank.
    #
    # This was the failure: only m09, m10 and m15 call ctx.track(), so the
    # first wave (m00, m02, m03, m06, m08) added no tasks at all and the
    # display rendered nothing for however long they took. A progress system
    # that shows nothing during the first twenty minutes of a run is not a
    # progress system.
    task = bar.add_task(name, total=None)
    conn = db.get_connection(settings)
    try:
        before = _audit_counts(conn, name)
        changes_before = conn.total_changes
        ctx = ModuleContext(conn=conn, settings=settings, since=since,
                             dry_run=dry_run, limit=limit,
                             progress=ui.ProgressReporter(bar, parent_description=name,
                                                          task_id=task))
        try:
            fn(ctx)
        except Exception as exc:
            conn.rollback()
            return {"module": name, "status": "failed",
                     "elapsed": time.perf_counter() - started, "error": exc}

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

        after = _audit_counts(conn, name)
        return {
            "module": name, "status": "ok",
            "elapsed": time.perf_counter() - started,
            "rows": conn.total_changes - changes_before,
            "review": after["review"] - before["review"],
            "failures": after["failures"] - before["failures"],
        }
    finally:
        conn.close()
        bar.remove_task(task)


def _run_waves(waves: list[list[str]], jobs: int, settings, since, dry_run, limit,
                bar) -> list[dict]:
    """Each wave concurrently, waves in order.

    Every module in a wave has its dependencies satisfied by an earlier wave,
    so within a wave there is nothing to order. Concurrency across modules is
    safe because the per-host rate limit is enforced process-wide: modules on
    different APIs proceed independently, and the four sharing www.gov.uk
    queue behind each other on that host alone.

    A wave is joined before the next begins, so a module never starts before
    the module whose output it reads has finished.
    """
    from concurrent.futures import ThreadPoolExecutor

    total_modules = sum(len(wave) for wave in waves)
    # The one task that outlives every module, so there is always a bar on
    # screen and the request counter and throughput columns always have
    # somewhere to render.
    overall = bar.add_task("all modules", total=total_modules, run_level=True)

    summary: list[dict] = []
    for wave in waves:
        width = max(1, min(jobs, len(wave)))
        if width == 1:
            for name in wave:
                summary.append(_execute_module(
                    name, MODULE_REGISTRY[name], settings, since, dry_run, limit, bar))
                bar.advance(overall)
            continue

        bar.console.print(
            f"[pipeline.muted]  wave of {len(wave)}, {width} at a time: "
            f"{', '.join(wave)}[/]")
        with ThreadPoolExecutor(max_workers=width, thread_name_prefix="module") as pool:
            futures = [pool.submit(_execute_module, name, MODULE_REGISTRY[name],
                                    settings, since, dry_run, limit, bar)
                        for name in wave]
            # Collected in submission order, so the summary reads the same way
            # twice regardless of which API answered first.
            for future in futures:
                summary.append(future.result())
                bar.advance(overall)
    return summary


@app.command()
def run(
    module: str = typer.Argument(..., help="Module name (e.g. m00_geography) or 'all'"),
    since: str = typer.Option(None, help="ISO date; only process records published/updated since this date"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and parse but do not write to the database"),
    limit: int = typer.Option(None, help="Stop after N records (smoke testing)"),
    jobs: int = typer.Option(
        1, "--jobs", "-j", min=1,
        help="Modules to run at once (`run all` only). Different APIs are "
              "independent; the per-host rate limit still holds."),
) -> None:
    if limit is not None and limit < 1:
        # Every module tests `if ctx.limit:`, so 0 is falsy and reads as "no
        # limit at all" — typing --limit 0 to fetch nothing launches a full
        # live crawl instead. Refused rather than reinterpreted: guessing which
        # of the two opposite meanings was intended is not this CLI's call.
        ui.error(f"--limit must be 1 or more; got {limit}. "
                  "Use --dry-run to fetch and parse without writing.")
        raise typer.Exit(code=1)

    configure_logging(module)
    settings = get_settings()
    conn = db.get_connection(settings)

    applied = db.apply_migrations(conn)
    if applied:
        typer.echo(f"Applied migrations: {', '.join(applied)}")

    discover_modules()

    if module == "all":
        # Dependency order, not alphabetical. Alphabetical silently produced a
        # worse run: m04 came before m05 and so missed the company numbers CQC
        # publishes, and m09/m10 came before m15 and so saw one authority
        # website instead of every one.
        try:
            order = resolve_run_order()
        except DependencyCycleError as exc:
            typer.echo(f"error: {exc}", err=True)
            conn.close()
            raise typer.Exit(code=1)
        targets = [(name, MODULE_REGISTRY[name]) for name in order]
        waves = resolve_run_waves(order)
        ui.heading(f"Run order — {len(targets)} modules in {len(waves)} waves")
        for index, wave in enumerate(waves, start=1):
            width = max(1, min(jobs, len(wave)))
            shape = f"{width} at a time" if width > 1 else "one at a time"
            ui.info(f"  [pipeline.muted]wave {index}[/] ({shape}): "
                     f"[pipeline.module]{', '.join(wave)}[/]")
        if jobs == 1 and any(len(wave) > 1 for wave in waves):
            # The waves exist either way — they are what orders the run. Saying
            # so avoids the reasonable reading that printing waves means the
            # run is already using them for concurrency.
            ui.muted("  running serially; --jobs N runs each wave's modules "
                      "at once (different APIs, same per-host rate limit)")
    elif module in MODULE_REGISTRY:
        targets = [(module, MODULE_REGISTRY[module])]
        # A single module still runs, but say what it will be working without.
        for name, absent in missing_dependencies([module]).items():
            meta = module_meta(name)
            typer.echo(
                f"note: {name} normally runs after {', '.join(absent)}. "
                "It will still run, using whatever those modules left behind.", err=True)
            if meta.depends_note:
                typer.echo(f"  {meta.depends_note}", err=True)
    else:
        available = ", ".join(sorted(MODULE_REGISTRY)) or "(none registered yet)"
        typer.echo(f"Unknown module {module!r}. Available: {available}", err=True)
        raise typer.Exit(code=1)

    ctx = ModuleContext(conn=conn, settings=settings, since=since, dry_run=dry_run, limit=limit)

    if since:  # noqa: SIM102 - kept adjacent to the validation it guards
        # Validate once, up front, rather than letting each module discover a
        # bad value part-way through a long crawl.
        try:
            ctx.since_date()
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            conn.close()
            raise typer.Exit(code=1)

        ignoring = [name for name, _ in targets if not module_meta(name).supports_since]
        if ignoring:
            typer.echo(
                f"warning: --since has no effect on {', '.join(ignoring)} — "
                "those modules do not filter by date and will process their full source.",
                err=True)
            for name in ignoring:
                note = module_meta(name).since_note
                if note:
                    typer.echo(f"  {name}: {note}", err=True)

    waves = resolve_run_waves([name for name, _ in targets])

    with ui.progress() as bar:
        summary = _run_waves(waves, jobs, settings, since, dry_run, limit, bar)

    failed = [row for row in summary if row["status"] == "failed"]
    for row in failed:
        exc = row.get("error")
        ui.error(f"{row['module']}: {type(exc).__name__}: {exc}")

    _print_summary(summary, dry_run)
    conn.close()

    if failed:
        # A failing module is a failing run, but the modules that succeeded
        # keep their work and are reported above -- an aborted crawl that
        # discards the sources it already asked is the worst outcome here.
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
