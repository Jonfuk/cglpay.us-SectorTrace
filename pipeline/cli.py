from __future__ import annotations

from contextlib import contextmanager

import typer

from pipeline import console as ui
from pipeline import db, runner
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
    target: str = typer.Argument(
        ..., help="sheets | geojson | echarts | docs | bundle | all"),
    output_dir: str = typer.Option(
        None, help="Where to write export files. Defaults to the configured "
                    "export_output_dir, which is also the only directory the "
                    "web UI will serve a download from."),
    push: bool = typer.Option(False, "--push", help="Also push Sheets tabs to Google (needs credentials)"),
) -> None:
    """Generate exports. Every file is written with a companion .provenance.json."""
    from pathlib import Path

    configure_logging(f"export_{target}")
    settings = get_settings()
    conn = db.get_connection(settings)
    db.apply_migrations(conn)

    from pipeline.exports import run as export_run

    base = Path(output_dir) if output_dir else Path(settings.export_output_dir)
    docs_dir = Path(settings.logs_dir).parent / "docs"

    try:
        targets = export_run.resolve_targets(target)
        results = export_run.run_targets(conn, targets, base, docs_dir, settings, push)
    except export_run.ExportError as exc:
        typer.echo(str(exc), err=True)
        conn.close()
        raise typer.Exit(code=1) from None

    for result in results:
        if result["target"] == "docs":
            typer.echo(f"docs: wrote {result['paths'][0]}")
        else:
            typer.echo(f"{result['target']}: {result['count']} {result['noun']} "
                        f"-> {base / result['target']}")

    conn.commit()
    conn.close()


@app.command("resolve-answered")
def resolve_answered(
    rule: str = typer.Option(None, help="Only this rule; default is all of them"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what would close, close nothing"),
    reopen: bool = typer.Option(
        False, "--reopen", help="Undo a rule's closures (requires --rule)"),
) -> None:
    """Close review items the pipeline has since answered for itself.

    Fetches nothing: it is a query over the warehouse as it stands. Only
    pending items are touched, every closure is recorded with its evidence in
    `review_resolutions`, and `--reopen` undoes a rule in one operation.
    """
    from pipeline import review_sweep

    configure_logging("review_sweep")
    settings = get_settings()
    conn = db.get_connection(settings)
    # migrations_dir_for, not settings.migrations_dir: the latter is always
    # the SQLite tree, so naming it here would apply SQLite DDL to a
    # PostgreSQL warehouse. The other four call sites pass nothing and get the
    # right tree by default; these two were explicit and had to be corrected.
    db.apply_migrations(conn, db.migrations_dir_for(settings))
    conn.commit()
    try:
        if reopen:
            if not rule:
                typer.echo("--reopen needs --rule: it undoes one rule's "
                            "closures, not everything.", err=True)
                raise typer.Exit(code=1)
            count = review_sweep.reopen(conn, rule)
            typer.echo(f"reopened {count:,} item(s) closed by {rule}")
            return

        result = review_sweep.sweep(conn, rule=rule, dry_run=dry_run)
        for name, count in result["closed"].items():
            verb = "would close" if dry_run else "closed"
            typer.echo(f"{name}: {verb} {count:,}")
        if not result["total"]:
            typer.echo("Nothing to close — the queue is all questions that "
                        "still need a person.")
        elif dry_run:
            ui.warn("--dry-run: nothing was changed.")
    except KeyError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()


@app.command("restore-promotion-flags")
def restore_promotion_flags(
    kind: str = typer.Option(None, help="Only this candidate kind; default is all"),
    apply: bool = typer.Option(
        False, "--apply", help="Write the flags back. Without it, only reports."),
) -> None:
    """Re-mark candidates that were promoted but read as unverified.

    Module runs used to overwrite the decision columns, so a link re-found
    after somebody promoted it lost its `verified` flag and came back round
    the review worklist. Fixed at the source in `db.upsert`; this puts right
    the rows a run had already reached.

    Reports by default, because a candidate somebody reset on purpose looks
    identical from here — a reset deliberately leaves the promotion record
    standing. Read the list before passing `--apply`.
    """
    from pipeline import promote

    configure_logging("promote")
    settings = get_settings()
    conn = db.get_connection(settings)
    # migrations_dir_for, not settings.migrations_dir: the latter is always
    # the SQLite tree, so naming it here would apply SQLite DDL to a
    # PostgreSQL warehouse. The other four call sites pass nothing and get the
    # right tree by default; these two were explicit and had to be corrected.
    db.apply_migrations(conn, db.migrations_dir_for(settings))
    conn.commit()
    try:
        rows = promote.restore_flags(conn, kind=kind, dry_run=not apply)
        if not rows:
            typer.echo("Nothing to restore — every promotion on record has "
                        "its candidate flag.")
            return
        for row in rows:
            typer.echo(f"{row['kind']}: {row['url']} "
                        f"(promoted {row['promoted_at']})")
        if apply:
            typer.echo(f"restored {len(rows):,} flag(s)")
        else:
            ui.warn(f"{len(rows):,} candidate(s) would be re-marked verified. "
                     "Nothing was changed; pass --apply once you have read the "
                     "list, and re-reset anything you reset on purpose.")
    finally:
        conn.close()


@app.command()
def backup(
    output: str = typer.Option(
        None, help="Where to write the backup. Defaults to a timestamped file "
                    "in the configured backup_dir."),
    label: str = typer.Option(
        None, help="Appended to the filename, e.g. --label before-m04-rerun"),
    keep: int = typer.Option(
        None, help="After backing up, delete all but the newest N automatic "
                    "backups. A labelled backup is never deleted."),
) -> None:
    """Copy the warehouse to a verified snapshot, and inventory the raw archive.

    Uses VACUUM INTO, so the copy is consistent even while a run is writing,
    and is checked against the original before it is called a backup. The raw
    archive is inventoried rather than copied — see pipeline/backup.py.
    """
    from pathlib import Path

    from pipeline import backup as backup_module

    configure_logging("backup")
    settings = get_settings()
    try:
        manifest = backup_module.create(
            settings, destination=Path(output) if output else None, label=label)
    except backup_module.BackupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    from pipeline.meters import human_bytes

    warehouse = manifest["warehouse"]
    archive = manifest["raw_archive"]
    typer.echo(f"warehouse -> {warehouse['backup']}")
    typer.echo(f"  {warehouse['rows']:,} rows in {warehouse['tables']} tables, "
                f"{human_bytes(warehouse['backup_bytes'])} "
                f"(from {human_bytes(warehouse['source_bytes'])}), "
                f"integrity {warehouse['integrity']}")
    if warehouse["drifted_while_copying"]:
        # Not a fault: the warehouse is live, and a module may have committed
        # between the copy and the count. Said out loud so it is not mistaken
        # for one later.
        typer.echo(f"  note: {len(warehouse['drifted_while_copying'])} table(s) "
                    "changed in the source while copying; the snapshot is "
                    "consistent, just not the newest state.")
    if archive.get("present"):
        typer.echo(f"raw archive: {archive['files']:,} files, "
                    f"{human_bytes(archive['bytes'])} across "
                    f"{len(archive['sources'])} sources — inventoried, not copied")
    typer.echo(f"  manifest: {Path(warehouse['backup']).with_suffix('.manifest.json')}")

    if keep is not None:
        try:
            pruned = backup_module.prune(settings, keep=keep)
        except backup_module.BackupError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from None
        if pruned["removed"]:
            typer.echo(f"pruned {len(pruned['removed'])} older backup(s); kept "
                        f"{pruned['kept']} automatic and {pruned['labelled_kept']} labelled")


@app.command()
def restore(
    backup_file: str = typer.Argument(..., help="Path to a backup .db to restore"),
    force: bool = typer.Option(
        False, "--force",
        help="Required when a warehouse already exists. It is moved aside, "
              "not deleted."),
) -> None:
    """Put a backup back in place of the warehouse.

    Refuses a backup that fails its own integrity check, and never deletes the
    warehouse it replaces — that one is renamed with a timestamp.
    """
    from pathlib import Path

    from pipeline import backup as backup_module

    configure_logging("backup")
    try:
        result = backup_module.restore(Path(backup_file), get_settings(), force=force)
    except backup_module.BackupError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from None

    typer.echo(f"restored {result['from']} -> {result['restored']}")
    typer.echo(f"  {result['rows']:,} rows in {result['tables']} tables")
    if result["superseded"]:
        typer.echo(f"  previous warehouse kept at {result['superseded']}")


@app.command("list-backups")
def list_backups() -> None:
    """Backups on disk, newest first."""
    from pipeline import backup as backup_module
    from pipeline.meters import human_bytes

    entries = backup_module.listing(get_settings())
    if not entries:
        typer.echo("No backups yet. `pipeline backup` makes one.")
        return
    for entry in entries:
        rows = f"{entry['rows']:,} rows" if entry.get("rows") else "no manifest"
        typer.echo(f"{entry['name']}  {human_bytes(entry['bytes'])}  {rows}")


def _postgres_target(settings, what: str):
    """The configured PostgreSQL warehouse, with its migrations applied.

    Refuses rather than falling back. Both commands below exist to move data
    between two named databases, and "there is no URL set, so I used the file
    for both" is a sentence with no useful ending.
    """
    if settings.database_backend != "postgres":
        ui.error(f"{what} needs a PostgreSQL warehouse to talk to, and "
                  "DATABASE_URL is not set.")
        ui.muted("  Set it in .env — see pipeline/migrations/postgres/README.md "
                  "for creating the database and its two roles.")
        raise typer.Exit(code=1)
    target = db.get_connection(settings)
    applied = db.apply_migrations(target, db.migrations_dir_for(settings))
    if applied:
        typer.echo(f"Applied migrations: {', '.join(applied)}")
    target.commit()
    return target


@app.command("migrate-data")
def migrate_data(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Say what would be loaded, in what order, "
                                  "and write nothing"),
    resume: bool = typer.Option(
        False, "--resume", help="Carry on from an interrupted migration, "
                                 "skipping the tables it finished"),
    truncate: bool = typer.Option(
        False, "--truncate",
        help="Empty the target's tables first. This discards whatever is in "
              "them; the SQLite warehouse is never touched."),
    table: list[str] = typer.Option(
        None, "--table", help="Load only these tables. For recovering a load, "
                               "not for performing one."),
    verify: bool = typer.Option(
        True, "--verify/--no-verify",
        help="Run the full row-by-row verification afterwards"),
) -> None:
    """Copy the SQLite warehouse into PostgreSQL, and prove it arrived.

    The source is opened read-only and stays authoritative: nothing here can
    write to it, and the way back from a bad migration is to unset
    DATABASE_URL rather than to restore anything.

    Refuses a target that already holds rows unless --truncate says otherwise,
    checks the schemas and the source's storage types before writing anything,
    and records each table in a state file so an interrupted run resumes.
    """
    from pipeline import pgload, pgverify

    configure_logging("pgload")
    settings = get_settings()
    target = _postgres_target(settings, "migrate-data")
    source = pgload.open_source(settings.database_path)

    try:
        if dry_run:
            rows = pgload.plan(source, target)
            problems = pgload.preflight(source, target)
            ui.heading(f"{len(rows)} tables, "
                        f"{sum(r['rows'] for r in rows):,} rows, in this order")
            for entry in rows:
                ui.info(f"  {entry['rows']:>9,}  {entry['table']}")
            if problems:
                ui.error("preflight found problems:")
                for problem in problems:
                    ui.warn(f"  {problem}")
                raise typer.Exit(code=1)
            ui.success("preflight is clean; nothing was written.")
            return

        def announce(name: str, expected: int, written: int | None) -> None:
            if written is None:
                ui.info(f"  {name} ({expected:,} rows)…")
            else:
                ui.success(f"  {name}: {written:,} rows")

        summary = pgload.migrate(
            source, target, settings=settings, resume=resume,
            truncate=truncate, only=list(table) if table else None,
            on_table=announce)
    except pgload.LoadError as exc:
        ui.error(str(exc))
        raise typer.Exit(code=1) from None
    else:
        ui.heading(f"{summary['rows']:,} rows in {summary['tables']} tables, "
                    f"{summary['elapsed_seconds']:,}s")
        ui.muted(f"  state: {summary['state_path']}")
        moved = [s for s in summary["sequences"] if s["next_value"] > 1]
        if moved:
            ui.muted(f"  {len(moved)} identity sequence(s) moved past the "
                      "loaded ids")

        if verify:
            ui.heading("Verifying")
            report = pgverify.verify(source, target)
            _report_verification(report)
            if not report["ok"]:
                raise typer.Exit(code=1)
    finally:
        source.close()
        target.close()


@app.command("verify-migration")
def verify_migration(
    quick: bool = typer.Option(
        False, "--quick",
        help="Counts, NULL counts and per-column minima and maxima only — "
              "skip the row-by-row comparison"),
    table: list[str] = typer.Option(
        None, "--table", help="Only these tables"),
) -> None:
    """Check the PostgreSQL warehouse against the SQLite one.

    Reads both and changes neither. Every check that can run does, so the
    output is the complete list of what is wrong rather than the first thing.
    """
    from pipeline import pgverify

    configure_logging("pgverify")
    settings = get_settings()
    target = _postgres_target(settings, "verify-migration")

    from pipeline import pgload

    source = pgload.open_source(settings.database_path)
    try:
        report = pgverify.verify(source, target, deep=not quick,
                                  tables=list(table) if table else None)
    finally:
        source.close()
        target.close()

    _report_verification(report)
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command()
def benchmark(
    output_dir: str = typer.Option(
        "docs/benchmarks", help="Where the JSON report is written"),
    reads: bool = typer.Option(True, "--reads/--no-reads"),
    writes: bool = typer.Option(True, "--writes/--no-writes"),
    compare_to: str = typer.Option(
        None, "--compare-to", help="An earlier report to diff this one "
                                    "against, case by case"),
) -> None:
    """Measure the configured backend, and record it so Phase 4 has a baseline.

    Reads run against the working warehouse, because the point is the real
    data. Writes go to a scratch warehouse — a temporary file on SQLite, a
    temporary schema on PostgreSQL — so nothing here changes what it measures.

    Changes nothing else either: this is a measurement, and the phase it
    belongs to exists so that a later "this is faster" can be checked.
    """
    import json
    from pathlib import Path

    from pipeline import benchmark as benchmark_module

    configure_logging("benchmark")
    settings = get_settings()
    report = benchmark_module.benchmark(
        settings, reads=reads, writes=writes,
        output_dir=Path(output_dir) if output_dir else None)

    environment = report["environment"]
    ui.heading(f"{environment['backend']} — {environment['server']}")
    ui.muted(f"  {sum(report['tables'].values()):,} rows across the measured tables")

    for case in report.get("reads", []):
        if "error" in case:
            ui.warn(f"  {case['name']}: {case['error']}")
        else:
            ui.info(f"  {case['name']:<34} p50 {case['p50_ms']:>9,.1f} ms   "
                     f"p95 {case['p95_ms']:>9,.1f} ms")
    if "write_throughput" in report:
        throughput = report["write_throughput"]
        ui.info(f"  {'writes (upsert + commit)':<34} "
                 f"{throughput['rows_per_second']:,.0f} rows/s   "
                 f"commit p50 {throughput['commit']['p50_ms']:.2f} ms")
        for entry in report["write_contention"]["by_writers"]:
            label = f"{entry['writers']} concurrent writer(s)"
            ui.info(f"  {label:<34} {entry['rows_per_second']:>9,.0f} rows/s   "
                     f"x{entry['scaling_vs_one_writer']} vs one")

    if report.get("written_to"):
        ui.success(f"recorded to {report['written_to']}")

    if compare_to:
        earlier = json.loads(Path(compare_to).read_text(encoding="utf-8"))
        ui.heading(f"against {earlier['environment']['backend']} "
                    f"({earlier['environment']['measured_at']})")
        for row in benchmark_module.compare(earlier, report):
            if "p50_ratio" not in row:
                ui.warn(f"  {row['name']}: {row['note']}")
                continue
            ui.info(f"  {row['name']:<34} "
                     f"{row['left_p50_ms']:>9,.1f} -> {row['right_p50_ms']:>9,.1f} ms   "
                     f"x{row['p50_ratio']}")


def _report_verification(report: dict) -> None:
    depth = "every value" if report["checks"].get("rows") else "counts and aggregates"
    if report["ok"]:
        ui.success(f"{report['rows']:,} rows across {report['tables']} tables "
                    f"agree, compared by {depth}.")
        return
    ui.error(f"{len(report['problems'])} problem(s) across "
              f"{report['tables']} tables:")
    for problem in report["problems"]:
        ui.warn(f"  {problem}")


@app.command()
def web(
    port: int = typer.Option(1801, help="Port to listen on"),
    host: str = typer.Option(
        # No em dash: Typer writes help straight to a console that is cp1252
        # on Windows, where it arrives as a replacement character.
        "0.0.0.0", help="Address to bind. Every interface by default; "
                         "pass 127.0.0.1 for this machine only."),
    open_browser: bool = typer.Option(
        True, "--open/--no-open", help="Open the UI in a browser once it is listening"),
) -> None:
    """Browse the warehouse and decide review-queue items in a browser.

    Reading is done on a read-only connection, so nothing the browser or the
    SQL box does can modify the warehouse. The only writes are review
    decisions, and each one records who made it and when.

    Binds every interface, so other machines on the network can reach it.
    There is no authentication and the warehouse holds personal data in
    restricted_ tables: --host 127.0.0.1 restricts it to this machine.
    """
    import webbrowser

    from pipeline.web.server import build_server, reachable_urls

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

    urls = reachable_urls(host, server.server_address[1])
    ui.heading(f"Review UI on {urls[0]}")
    for other in urls[1:]:
        # The addresses another device on the network can actually type.
        # "listening on 0.0.0.0" is true and useless from a phone.
        ui.info(f"  also on [pipeline.module]{other}[/]")
    ui.info(f"  warehouse: [pipeline.muted]{settings.database_path}[/]")
    ui.info(f"  {pending:,} item(s) pending review")
    if host not in ("127.0.0.1", "localhost", "::1"):
        # Stated every time, not once in a doc. There is no login on this
        # server, and the warehouse holds restricted_ tables of personal data
        # — company officers, CQC contacts, named individuals from PFD
        # reports. Anyone who can reach the port can read all of it and can
        # decide review items.
        ui.warn(f"  bound to {host}: anyone who can reach this machine can "
                 "read the warehouse and decide review items. There is no "
                 "authentication. Use --host 127.0.0.1 for this machine only.")
    ui.muted("  Ctrl-C to stop.")

    if open_browser:
        # Loopback for the local browser regardless of bind: it is the address
        # that always resolves on the machine actually running the server.
        webbrowser.open(f"http://127.0.0.1:{server.server_address[1]}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ui.muted("\n  stopped.")
    finally:
        server.server_close()


_audit_counts = runner.audit_counts


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


class _BarObserver(runner.RunObserver):
    """The Rich progress display, as something a run can report to.

    Everything terminal-shaped about a run lives here: the pulsing task per
    module, the overall counter, and the line announcing a concurrent wave.
    The run itself is in pipeline/runner.py and does not know any of it.
    """

    def __init__(self, bar) -> None:
        self._bar = bar
        self._overall = None

    def run_starting(self, total_modules: int) -> None:
        # The one task that outlives every module, so there is always a bar on
        # screen and the request counter and throughput columns always have
        # somewhere to render.
        self._overall = self._bar.add_task("all modules", total=total_modules,
                                            run_level=True)

    def wave_starting(self, names: list[str], width: int) -> None:
        self._bar.console.print(
            f"[pipeline.muted]  wave of {len(names)}, {width} at a time: "
            f"{', '.join(names)}[/]")

    @contextmanager
    def module_progress(self, name: str):
        # A task per module, always, with no total. Rich renders that as a
        # pulsing bar, which is the honest display for work whose size is not
        # known up front — and it means the screen is never blank.
        #
        # This was the failure: only m09, m10 and m15 call ctx.track(), so the
        # first wave (m00, m02, m03, m06, m08) added no tasks at all and the
        # display rendered nothing for however long they took. A progress
        # system that shows nothing during the first twenty minutes of a run is
        # not a progress system.
        task = self._bar.add_task(name, total=None)
        try:
            yield ui.ProgressReporter(self._bar, parent_description=name, task_id=task)
        finally:
            self._bar.remove_task(task)

    def module_finished(self, row: dict) -> None:
        if self._overall is not None:
            self._bar.advance(self._overall)


def _execute_module(name: str, fn, settings, since, dry_run, limit, bar) -> dict:
    """Kept as the CLI's bar-shaped way in. The run is runner.execute_module."""
    return runner.execute_module(name, fn, settings, since, dry_run, limit,
                                  _BarObserver(bar))


def _run_waves(waves: list[list[str]], jobs: int, settings, since, dry_run, limit,
                bar) -> list[dict]:
    """Every wave, painted onto `bar`. The ordering rules are in runner.py."""
    return runner.run_waves(waves, jobs, settings, since, dry_run, limit,
                             _BarObserver(bar))


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
