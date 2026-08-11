from __future__ import annotations

import typer

from pipeline import db
from pipeline.config import get_settings
from pipeline.logging_conf import configure_logging
from pipeline.registry import MODULE_REGISTRY, ModuleContext, discover_modules, module_meta

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
        targets = list(MODULE_REGISTRY.items())
    elif module in MODULE_REGISTRY:
        targets = [(module, MODULE_REGISTRY[module])]
    else:
        available = ", ".join(sorted(MODULE_REGISTRY)) or "(none registered yet)"
        typer.echo(f"Unknown module {module!r}. Available: {available}", err=True)
        raise typer.Exit(code=1)

    ctx = ModuleContext(conn=conn, settings=settings, since=since, dry_run=dry_run, limit=limit)

    if since:
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

    for name, fn in targets:
        typer.echo(f"--- running {name} ---")
        try:
            fn(ctx)
        except Exception:
            # Roll back this module's partial writes; earlier modules in a
            # `run all` batch already committed and are unaffected.
            conn.rollback()
            conn.close()
            raise
        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    conn.close()


if __name__ == "__main__":
    app()
