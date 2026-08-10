from __future__ import annotations

import typer

from pipeline import db
from pipeline.config import get_settings
from pipeline.logging_conf import configure_logging
from pipeline.registry import MODULE_REGISTRY, ModuleContext, discover_modules

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
    for name, fn in targets:
        typer.echo(f"--- running {name} ---")
        fn(ctx)

    conn.close()


if __name__ == "__main__":
    app()
