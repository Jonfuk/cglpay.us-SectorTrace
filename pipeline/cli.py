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
    ui.console().print()
    ui.console().print(ui.run_summary(summary))
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


@app.command()
def run(
    module: str = typer.Argument(..., help="Module name (e.g. m00_geography) or 'all'"),
    since: str = typer.Option(None, help="ISO date; only process records published/updated since this date"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Fetch and parse but do not write to the database"),
    limit: int = typer.Option(None, help="Stop after N records (smoke testing)"),
) -> None:
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
        typer.echo(f"Run order ({len(targets)} modules): {' -> '.join(order)}")
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

    summary: list[dict] = []
    with ui.progress() as bar:
        overall = bar.add_task("overall", total=len(targets)) if len(targets) > 1 else None

        for name, fn in targets:
            ctx.progress = ui.ProgressReporter(bar, parent_description=name)
            before = _audit_counts(conn, name)
            # sqlite3 counts every inserted/updated/deleted row on this
            # connection, which is exactly "what did this module write" without
            # each module having to keep its own tally and get it wrong.
            changes_before = conn.total_changes
            started = time.perf_counter()
            bar.console.print(f"[pipeline.heading]▸[/] [pipeline.module]{name}[/]")

            try:
                fn(ctx)
            except Exception as exc:
                # Roll back this module's partial writes; earlier modules in a
                # `run all` batch already committed and are unaffected.
                conn.rollback()
                summary.append({"module": name, "status": "failed",
                                 "elapsed": time.perf_counter() - started})
                ui.error(f"{name}: {type(exc).__name__}: {exc}")
                _print_summary(summary, dry_run)
                conn.close()
                raise

            if dry_run:
                conn.rollback()
            else:
                conn.commit()

            after = _audit_counts(conn, name)
            summary.append({
                "module": name, "status": "ok",
                "elapsed": time.perf_counter() - started,
                "rows": conn.total_changes - changes_before,
                "review": after["review"] - before["review"],
                "failures": after["failures"] - before["failures"],
            })
            if overall is not None:
                bar.advance(overall)

    _print_summary(summary, dry_run)
    conn.close()


if __name__ == "__main__":
    app()
