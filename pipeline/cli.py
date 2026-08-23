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
graph_app = typer.Typer(help="Manage the derived, rebuildable Evidence Graph.")
documents_app = typer.Typer(help="Inspect, parse, validate, and search archived documents.")
app.add_typer(graph_app, name="graph")
app.add_typer(documents_app, name="documents")


def _document_connection():
    """Open the warehouse with its matching migration dialect applied."""
    settings = get_settings()
    conn = db.get_connection(settings)
    db.apply_migrations(conn, db.migrations_dir_for(settings))
    return conn, settings


def _document_reference(row):
    from pipeline.documents.models import EvidenceReference

    return EvidenceReference(
        evidence_id=row["evidence_id"], source_system=row["source_system"],
        source_url=row["source_url"], retrieved_at=row["retrieved_at"],
        http_status=row["http_status"], payload_sha256=row["payload_sha256"],
        raw_object_path=row["raw_object_path"], mime_type=row["mime_type"],
        content_length=row["content_length"], source_table=row["source_table"], source_key=row["source_key"],
    )


@documents_app.command("inspect")
def documents_inspect(
    raw_object_path: str = typer.Argument(..., help="Immutable data/raw/... object to inspect"),
    mime_type: str = typer.Option(None, help="Override the detected MIME type"),
) -> None:
    """Report deterministic PDF inspection metrics without parsing or writing."""
    from pipeline.archive import get_archive
    from pipeline.documents.inspect import inspect_bytes, source_filename

    settings = get_settings()
    report = inspect_bytes(get_archive(settings).read(raw_object_path), source_filename(raw_object_path), mime_type)
    typer.echo(__import__("json").dumps(report.__dict__, default=list, indent=2, sort_keys=True))


@documents_app.command("register")
def documents_register(
    source_system: str = typer.Option(..., help="Owning source-system/module name"),
    payload_sha256: str = typer.Option(..., help="SHA-256 recorded for the raw bytes"),
    raw_object_path: str = typer.Option(..., help="Immutable data/raw/... path"),
    retrieved_at: str = typer.Option(..., help="ISO retrieval timestamp"),
    source_url: str = typer.Option(None, help="Original publisher URL"),
    http_status: int = typer.Option(None, help="HTTP status recorded at retrieval"),
    mime_type: str = typer.Option(None),
    source_table: str = typer.Option(None, help="Existing module table, if applicable"),
    source_key: str = typer.Option(None, help="Existing module natural key, if applicable"),
) -> None:
    """Register an already-provenanced raw object without re-fetching it."""
    from pipeline.documents import repository
    from pipeline.documents.models import EvidenceReference
    from pipeline.documents.service import DocumentService

    conn, settings = _document_connection()
    try:
        evidence_id = repository.stable_id("evidence", f"{source_system}|{source_url}|{payload_sha256}")
        DocumentService(conn, settings).register(EvidenceReference(
            evidence_id=evidence_id, source_system=source_system, source_url=source_url,
            retrieved_at=retrieved_at, http_status=http_status, payload_sha256=payload_sha256,
            raw_object_path=raw_object_path, mime_type=mime_type, source_table=source_table,
            source_key=source_key))
        conn.commit()
        typer.echo(evidence_id)
    finally:
        conn.close()


@documents_app.command("register-existing")
def documents_register_existing(
    source: str = typer.Option(..., help="committee_papers | cdp_documents | annual_reports"),
    limit: int = typer.Option(25, min=1, help="Maximum provenance-complete legacy rows to register"),
) -> None:
    """Bridge a bounded legacy document table into canonical processing states."""
    from pipeline.documents.bridge import register_existing

    conn, settings = _document_connection()
    try:
        result = register_existing(conn, settings, source, limit)
        conn.commit()
        typer.echo(__import__("json").dumps(result, indent=2, sort_keys=True))
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from None
    finally:
        conn.close()


def _document_candidates(conn, evidence_id, source_system, quality, parser_version, limit, pending_only=False):
    sql = "SELECT e.* FROM evidence_records e LEFT JOIN document_processing_states s ON s.evidence_id=e.evidence_id"
    # Evidence is graph-ready before it is document-ready. A document run must
    # only select rows with an immutable raw archive path; otherwise generic
    # evidence (for example, a contract notice) would be retried as a document.
    terms, values = ["e.raw_object_path IS NOT NULL"], []
    if evidence_id:
        terms.append("e.evidence_id=?")
        values.append(evidence_id)
    if source_system:
        terms.append("e.source_system=?")
        values.append(source_system)
    if quality:
        terms.append("s.quality_status=?")
        values.append(quality)
    if parser_version:
        sql += " LEFT JOIN document_records d ON d.evidence_id=e.evidence_id LEFT JOIN document_versions dv ON dv.document_id=d.document_id"
        terms.append("dv.parser_version=?")
        values.append(parser_version)
    if pending_only:
        terms.append("COALESCE(s.parse_status, 'PENDING') != 'SUCCESS'")
    if terms:
        sql += " WHERE " + " AND ".join(terms)
    sql += " ORDER BY e.created_at LIMIT ?"
    return conn.execute(sql, (*values, limit)).fetchall()


@documents_app.command("process")
def documents_process(
    evidence_id: str = typer.Option(None),
    source_system: str = typer.Option(None),
    limit: int = typer.Option(25, min=1),
    parser: str = typer.Option(None, help="docling, pymupdf, docx, or pptx"),
    force: bool = typer.Option(False, "--force", help="Create a new parse run even if configuration matches"),
) -> None:
    """Parse registered raw objects; collection and raw archive are untouched."""
    from pipeline.documents.service import DocumentService

    conn, settings = _document_connection()
    try:
        results = []
        pending_only = evidence_id is None and not force
        for row in _document_candidates(conn, evidence_id, source_system, None, None, limit, pending_only):
            try:
                result = DocumentService(conn, settings).process(
                    _document_reference(row), force=force, parser_name=parser)
                conn.commit()
            except Exception as exc:
                conn.commit()  # Preserve the retryable failure state.
                result = {"status": "FAILED", "evidence_id": row["evidence_id"], "error": str(exc)}
            results.append(result)
        typer.echo(__import__("json").dumps(results, indent=2, sort_keys=True))
        if any(row["status"] in {"FAILED", "OCR_FAILED"} for row in results):
            raise typer.Exit(code=1)
    finally:
        conn.close()


@documents_app.command("reprocess")
def documents_reprocess(
    parser_version: str = typer.Option(None, help="Only versions matching this parser version"),
    quality: str = typer.Option(None, help="Only documents with this quality status"),
    source_system: str = typer.Option(None),
    document_id: str = typer.Option(None),
    limit: int = typer.Option(25, min=1),
    parser: str = typer.Option(None),
) -> None:
    """Selectively re-run existing registered evidence without destructive replacement."""
    conn, settings = _document_connection()
    try:
        evidence_id = None
        if document_id:
            row = conn.execute("SELECT evidence_id FROM document_records WHERE document_id=?", (document_id,)).fetchone()
            if row is None:
                raise typer.BadParameter(f"unknown document_id {document_id!r}")
            evidence_id = row["evidence_id"]
        rows = _document_candidates(conn, evidence_id, source_system, quality, parser_version, limit)
    finally:
        conn.close()
    # Reuse the same operation so error handling and one-transaction-per-file
    # discipline cannot drift between initial and selective processing.
    for row in rows:
        documents_process(evidence_id=row["evidence_id"], limit=1, parser=parser, force=True)


@documents_app.command("status")
def documents_status() -> None:
    """Summarise registered evidence and each processing stage."""
    conn, _ = _document_connection()
    try:
        rows = conn.execute(
            "SELECT s.parse_status, s.ocr_status, s.quality_status, COUNT(*) AS count "
            "FROM document_processing_states s JOIN evidence_records e ON e.evidence_id=s.evidence_id "
            "WHERE e.raw_object_path IS NOT NULL "
            "GROUP BY s.parse_status, s.ocr_status, s.quality_status").fetchall()
        typer.echo(__import__("json").dumps([dict(row) for row in rows], indent=2, sort_keys=True))
    finally:
        conn.close()


@documents_app.command("stats")
def documents_stats() -> None:
    """Return compact corpus, parser, OCR, and quality counts."""
    conn, _ = _document_connection()
    try:
        result = {
            "registered_evidence": conn.execute(
                "SELECT COUNT(*) FROM document_processing_states s "
                "JOIN evidence_records e ON e.evidence_id=s.evidence_id "
                "WHERE e.raw_object_path IS NOT NULL").fetchone()[0],
            "documents": conn.execute("SELECT COUNT(*) FROM document_records").fetchone()[0],
            "active_versions": conn.execute("SELECT COUNT(*) FROM document_versions WHERE is_active=1").fetchone()[0],
            "parse_runs": conn.execute("SELECT COUNT(*) FROM document_parse_runs").fetchone()[0],
            "derived_artifacts": conn.execute("SELECT COUNT(*) FROM derived_artifacts").fetchone()[0],
        }
        typer.echo(__import__("json").dumps(result, indent=2, sort_keys=True))
    finally:
        conn.close()


@documents_app.command("search")
def documents_search(query: str = typer.Argument(...), limit: int = typer.Option(25, min=1)) -> None:
    """Search active parsed elements and return source/page provenance."""
    from pipeline.documents.repository import search

    conn, settings = _document_connection()
    try:
        typer.echo(__import__("json").dumps(search(conn, settings, query, limit), indent=2, sort_keys=True))
    finally:
        conn.close()


@documents_app.command("validate")
def documents_validate() -> None:
    """Check canonical document integrity and fail non-zero on a broken lineage."""
    conn, _ = _document_connection()
    try:
        checks = {
            "documents_without_evidence": "SELECT COUNT(*) FROM document_records d LEFT JOIN evidence_records e ON e.evidence_id=d.evidence_id WHERE e.evidence_id IS NULL",
            "elements_without_versions": "SELECT COUNT(*) FROM document_elements e LEFT JOIN document_versions v ON v.document_version_id=e.document_version_id WHERE v.document_version_id IS NULL",
            "duplicate_active_versions": "SELECT COUNT(*) FROM (SELECT document_id FROM document_versions WHERE is_active=1 GROUP BY document_id HAVING COUNT(*) > 1)",
            "broken_artifact_lineage": "SELECT COUNT(*) FROM derived_artifacts a LEFT JOIN evidence_records e ON e.evidence_id=a.evidence_id WHERE e.evidence_id IS NULL",
        }
        result = {name: conn.execute(sql).fetchone()[0] for name, sql in checks.items()}
        typer.echo(__import__("json").dumps(result, indent=2, sort_keys=True))
        if any(result.values()):
            raise typer.Exit(code=1)
    finally:
        conn.close()


@documents_app.command("benchmark")
def documents_benchmark(
    manifest: str = typer.Option(..., help="CSV containing an evidence_id column"),
    parsers: str = typer.Option("pymupdf,docling", help="Comma-separated parser names"),
    limit: int = typer.Option(25, min=1),
) -> None:
    """Run a selected representative corpus, never the archive by default."""
    import csv
    from pathlib import Path

    conn, settings = _document_connection()
    try:
        with Path(manifest).open(newline="", encoding="utf-8") as handle:
            evidence_ids = [row["evidence_id"] for row in csv.DictReader(handle) if row.get("evidence_id")][:limit]
        selected = [name.strip() for name in parsers.split(",") if name.strip()]
        rows = []
        from pipeline.documents.service import DocumentService
        for evidence_id in evidence_ids:
            record = conn.execute("SELECT * FROM evidence_records WHERE evidence_id=?", (evidence_id,)).fetchone()
            if record is None:
                rows.append({"evidence_id": evidence_id, "status": "MISSING"})
                continue
            for parser in selected:
                try:
                    result = DocumentService(conn, settings).process(
                        _document_reference(record), parser_name=parser, force=True)
                    conn.commit()
                except Exception as exc:
                    conn.commit()
                    result = {"status": "FAILED", "error": str(exc)}
                rows.append({"evidence_id": evidence_id, "parser": parser, **result})
        typer.echo(__import__("json").dumps(rows, indent=2, sort_keys=True))
        if any(row.get("status") == "FAILED" for row in rows):
            raise typer.Exit(code=1)
    finally:
        conn.close()


def _graph_projector():
    """Open the authoritative warehouse and the optional graph projection."""
    from pipeline.graph.projector import GraphProjector
    from pipeline.graph.store import GraphStore

    settings = get_settings()
    conn = db.get_connection(settings)
    db.apply_migrations(conn, db.migrations_dir_for(settings))
    store = GraphStore(settings)
    store.connect()
    return conn, store, GraphProjector(conn, store, settings.graph_batch_size)


@graph_app.command("rebuild")
def graph_rebuild(
    clear: bool = typer.Option(False, "--clear", help="Remove only SectorTrace-managed Neo4j data first."),
) -> None:
    """Replay the warehouse into Neo4j. No ingestion module writes Neo4j directly."""
    conn = store = None
    try:
        conn, store, projector = _graph_projector()
        result = projector.rebuild(clear=clear)
        typer.echo("graph rebuild {run_id}: {entities} entities, {relationships} relationships, "
                    "{claims} claims, {evidence} evidence records".format(**result))
    except Exception as exc:
        typer.echo(f"graph rebuild failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if store:
            store.close()
        if conn:
            conn.close()


@graph_app.command("sync")
def graph_sync(limit: int = typer.Option(500, min=1, help="Maximum queued changes to process.")) -> None:
    """Process a retryable batch from the relational graph-projection queue."""
    conn = store = None
    try:
        conn, store, projector = _graph_projector()
        result = projector.sync_delta(limit=limit)
        typer.echo("graph sync: {processed} processed, {failed} failed".format(**result))
        if result["failed"]:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"graph sync failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if store:
            store.close()
        if conn:
            conn.close()


@graph_app.command("status")
def graph_status() -> None:
    """Show the number of unprojected relational changes."""
    conn = None
    try:
        settings = get_settings()
        conn = db.get_connection(settings)
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        from pipeline.graph.projector import GraphProjector
        # Status is a warehouse query: it does not need Neo4j to be available.
        projector = GraphProjector(conn, None, settings.graph_batch_size)
        typer.echo(f"graph projection queue: {projector.status()['pending']} pending")
    except Exception as exc:
        typer.echo(f"graph status failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if conn:
            conn.close()


@graph_app.command("analyze")
def graph_analyze(
    as_of: str = typer.Option(None, help="Only relationships valid on this ISO date."),
) -> None:
    """Calculate bounded, neutral NetworkX metrics from warehouse relationships."""
    conn = None
    try:
        from pipeline.analytics.graph_builder import build_commissioner_provider_graph
        from pipeline.analytics.networks import (
            commissioner_provider_metrics,
            persist_metrics,
            provider_network_metrics,
        )

        settings = get_settings()
        conn = db.get_connection(settings)
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        snapshot = build_commissioner_provider_graph(
            conn, as_of=as_of, max_nodes=settings.graph_max_nodes,
            max_edges=settings.graph_max_edges)
        stamp = f"commissioner-provider:{as_of or 'current'}"
        stored = persist_metrics(
            conn, commissioner_provider_metrics(snapshot) + provider_network_metrics(snapshot),
            analysis_name="commissioner_provider_network", graph_snapshot=stamp,
            parameters=snapshot.parameters)
        typer.echo(f"graph analysis: {snapshot.graph.number_of_nodes()} nodes, "
                    f"{snapshot.relationship_count} evidence relationships, {stored} metrics")
    except Exception as exc:
        typer.echo(f"graph analysis failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if conn:
            conn.close()


@graph_app.command("backfill")
def graph_backfill() -> None:
    """Seed the graph registry from existing evidence without fetching or guessing."""
    conn = None
    try:
        from pipeline.graph.backfill import seed_existing_evidence

        settings = get_settings()
        conn = db.get_connection(settings)
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        result = seed_existing_evidence(conn)
        typer.echo("graph backfill: {entities} entity writes, {evidence} evidence writes, "
                    "{relationships} relationships, {queued} queued changes".format(**result))
    except Exception as exc:
        typer.echo(f"graph backfill failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if conn:
            conn.close()


@app.command("backfill-procurement-sightings")
def backfill_procurement_sightings() -> None:
    """One-time repair: populate procurement_channel_sightings for contracts
    rows written before that table existed, so --kag's coverage-gap check
    stops misreporting them. See m01_procurement.backfill_channel_sightings
    for why this is needed and what it deliberately does not backfill.
    """
    conn = None
    try:
        from pipeline.modules.m01_procurement import backfill_channel_sightings

        settings = get_settings()
        conn = db.get_connection(settings)
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        inserted = backfill_channel_sightings(conn)
        conn.commit()
        typer.echo(f"procurement sightings backfill: {inserted} rows added")
    except Exception as exc:
        typer.echo(f"procurement sightings backfill failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        if conn:
            conn.close()


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

    On SQLite this is VACUUM INTO, so the copy is consistent even while a run
    is writing, and is checked against the original before it is called a
    backup. On PostgreSQL it is every table streamed out of one REPEATABLE
    READ snapshot into a gzipped SQL script, checked by reading the whole file
    back — see pipeline/pgbackup.py for why it is not pg_dump. The raw archive
    is inventoried rather than copied either way.
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
    if manifest["backend"] == "postgres":
        typer.echo(f"  {warehouse['rows']:,} rows in {warehouse['tables']} tables, "
                    f"{human_bytes(warehouse['backup_bytes'])} "
                    f"from {warehouse['source']}")
        typer.echo("  re-read after writing: every row counted and every "
                    "table's bytes re-hashed")
        typer.echo(f"  schema: {len(warehouse['migrations'])} migrations, "
                    "applied from pipeline/migrations/postgres/ on restore")
    else:
        typer.echo(f"  {warehouse['rows']:,} rows in {warehouse['tables']} tables, "
                    f"{human_bytes(warehouse['backup_bytes'])} "
                    f"(from {human_bytes(warehouse['source_bytes'])}), "
                    f"integrity {warehouse['integrity']}")
        if warehouse["drifted_while_copying"]:
            # Not a fault: the warehouse is live, and a module may have
            # committed between the copy and the count. Said out loud so it is
            # not mistaken for one later.
            typer.echo(f"  note: {len(warehouse['drifted_while_copying'])} table(s) "
                        "changed in the source while copying; the snapshot is "
                        "consistent, just not the newest state.")
    if archive.get("present"):
        typer.echo(f"raw archive: {archive['files']:,} files, "
                    f"{human_bytes(archive['bytes'])} across "
                    f"{len(archive['sources'])} sources — inventoried, not copied")
    typer.echo("  manifest: "
                f"{backup_module.companion(Path(warehouse['backup']), '.manifest.json')}")

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
    backup_file: str = typer.Argument(
        ..., help="Path to a backup to restore: a .db file for SQLite, a "
                   ".sql.gz snapshot for PostgreSQL"),
    force: bool = typer.Option(
        False, "--force",
        help="Required when a warehouse already exists. It is moved aside, "
              "not deleted."),
) -> None:
    """Put a backup back in place of the warehouse.

    Refuses a backup that fails its own checks, and never throws away what it
    replaces: a SQLite warehouse is renamed with a timestamp, and a PostgreSQL
    one is snapshotted before it is emptied.

    Which warehouse is restored into is decided by DATABASE_URL, not by the
    file — a file from the other backend is refused rather than parsed.
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
    if result.get("migrations_ahead_of_archive"):
        # Not a refusal: those migrations added objects, and objects the
        # snapshot predates are simply empty. Said out loud because "the
        # restore worked and the table is empty" is otherwise a mystery.
        typer.echo("  note: this warehouse has "
                    f"{len(result['migrations_ahead_of_archive'])} migration(s) "
                    "applied since the snapshot was taken; anything they added "
                    "is empty.")


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
        typer.echo(f"{entry['name']}  {human_bytes(entry['bytes'])}  {rows}  "
                    f"{entry['backend']}")


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


def _postgres_source(settings, command: str):
    """Open the explicit source URL used by PostgreSQL mirror commands."""
    if settings.database_backend != "postgres":
        typer.echo(f"{command} needs DATABASE_URL set to the target PostgreSQL warehouse.",
                   err=True)
        raise typer.Exit(code=1)
    if not settings.database_source_url:
        typer.echo(
            f"{command} needs DATABASE_SOURCE_URL for the other PostgreSQL warehouse.",
            err=True)
        raise typer.Exit(code=1)
    from pipeline import pg

    return pg.connect(settings.database_source_url, readonly=True,
                      application_name=f"sectortrace-{command}")


@app.command("migrate-postgres")
def migrate_postgres(
    truncate: bool = typer.Option(
        False, "--truncate", help="Replace all target rows instead of refusing a populated target"),
    verify: bool = typer.Option(
        True, "--verify/--no-verify", help="Compare every value after copying"),
) -> None:
    """Copy DATABASE_SOURCE_URL into the configured PostgreSQL warehouse.

    Use this for the initial local-PostgreSQL -> Railway import. Later, point
    DATABASE_URL at local PostgreSQL and DATABASE_SOURCE_URL at Railway to
    refresh the local mirror from the authoritative warehouse.
    """
    from pipeline import pgmirror

    configure_logging("pgmirror")
    settings = get_settings()
    source = _postgres_source(settings, "migrate-postgres")
    target = _postgres_target(settings, "migrate-postgres")
    try:
        def announce(table: str, rows: int) -> None:
            ui.success(f"  {table}: {rows:,} rows")

        result = pgmirror.transfer(source, target, truncate=truncate,
                                   verify=verify, on_table=announce)
    except pgmirror.MirrorError as exc:
        ui.error(str(exc))
        raise typer.Exit(code=1) from None
    finally:
        source.close()
        target.close()
    ui.heading(f"{result['rows']:,} rows in {result['tables']} tables copied")
    if result["verified"]:
        ui.success("  source and target agree on every value")


@app.command("check-postgres-sync")
def check_postgres_sync() -> None:
    """Compare the two PostgreSQL warehouses without changing either one."""
    from pipeline import pgmirror

    configure_logging("pgmirror_check")
    settings = get_settings()
    source = _postgres_source(settings, "check-postgres-sync")
    target = _postgres_target(settings, "check-postgres-sync")
    try:
        report = pgmirror.compare(source, target)
    finally:
        source.close()
        target.close()
    if "tables" in report:
        _report_verification(report)
    else:
        ui.error("PostgreSQL sync preflight failed:")
        for problem in report["problems"]:
            ui.warn(f"  {problem}")
    if not report["ok"]:
        raise typer.Exit(code=1)


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


@app.command("sync-sqlite")
def sync_sqlite(
    check: bool = typer.Option(
        False, "--check",
        help="Say how far apart the two warehouses are and write nothing"),
    output: str = typer.Option(
        None, "--output", help="Build the warehouse here instead of at "
                                "DATABASE_PATH. For inspecting one without "
                                "replacing what you have."),
    verify: bool = typer.Option(
        True, "--verify/--no-verify",
        help="Compare the rebuilt file against PostgreSQL before installing it"),
    quick: bool = typer.Option(
        False, "--quick",
        help="Verify by counts and per-column aggregates only, not row by row"),
    force: bool = typer.Option(
        False, "--force", help="Overwrite the file named by --output"),
) -> None:
    """Rebuild the SQLite warehouse from PostgreSQL, so rollback stays real.

    PostgreSQL is where collection writes once DATABASE_URL is set, and the
    SQLite file stops moving the moment it is. Unsetting the variable is only
    a rollback while this has been run recently — see pipeline/pgsync.py.

    The new file is built beside the old one, verified against PostgreSQL, and
    only then swapped in. What it replaces is renamed, never deleted.
    """
    from pathlib import Path

    from pipeline import pgsync

    configure_logging("pgsync")
    settings = get_settings()

    try:
        if check:
            report = pgsync.check(settings)
            ui.heading(f"{report['postgres_rows']:,} rows in PostgreSQL, "
                        + (f"{report['sqlite_rows']:,} in {report['sqlite_path']}"
                            if report["sqlite_present"] else "no SQLite warehouse"))
            for problem in report["problems"]:
                ui.warn(f"  {problem}")
            if report["in_step"]:
                ui.success("  the two warehouses hold the same rows and the "
                            "same schema.")
            elif report["rows_in_step"]:
                ui.info("  the rows match; it is the migration ledgers that "
                         "differ. A refresh will not change that — this "
                         "checkout is not at the commit the server was "
                         "migrated from.")
            else:
                ui.muted("  `./start.sh sync-sqlite` rebuilds the SQLite "
                          "warehouse from PostgreSQL.")
            raise typer.Exit(code=0 if report["in_step"] else 1)

        def announce(table: str, rows: int | None) -> None:
            if rows is not None:
                ui.success(f"  {table}: {rows:,} rows")

        result = pgsync.refresh(
            settings, destination=Path(output) if output else None,
            verify=verify, deep=not quick, force=force, on_table=announce)
    except pgsync.SyncError as exc:
        ui.error(str(exc))
        raise typer.Exit(code=1) from None

    ui.heading(f"{result['rows']:,} rows in {result['tables']} tables -> "
                f"{result['target']}")
    if result["verified"]:
        ui.success("  verified against PostgreSQL by "
                    + ("every value" if result["deep"]
                        else "counts and aggregates")
                    + " before it was installed")
    else:
        ui.warn("  not verified — this file has not been compared with the "
                 "warehouse it came from")
    if result["superseded"]:
        ui.muted(f"  previous warehouse kept at {result['superseded']}")


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


@app.command("coverage-report")
def coverage_report(
    output: str = typer.Option(
        None, help="Write the JSON baseline to this path instead of stdout"),
    tier: str = typer.Option("upper", help="upper or all authority tier"),
) -> None:
    """Build a read-only coverage, review, freshness and provenance baseline."""
    import json
    from pathlib import Path

    from pipeline import completeness
    from pipeline.web.queries import readonly_connection

    configure_logging("coverage-report")
    settings = get_settings()
    conn = readonly_connection(settings)
    try:
        report = completeness.baseline(conn, tier=tier)
    finally:
        conn.close()

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        typer.echo(f"coverage baseline written to {output}")
    else:
        typer.echo(payload, nl=False)


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
def migrate() -> None:
    """Apply the schema migrations for the configured warehouse.

    This is intentionally a small, explicit deployment command. Railway can
    run it before starting the web process, while local commands continue to
    apply migrations lazily as they do today.
    """
    configure_logging("migrate")
    settings = get_settings()
    conn = db.get_connection(settings)
    try:
        applied = db.apply_migrations(conn, settings=settings)
        conn.commit()
    finally:
        conn.close()

    backend = settings.database_backend
    if applied:
        typer.echo(f"{backend}: applied {len(applied)} migration(s): {', '.join(applied)}")
    else:
        typer.echo(f"{backend}: schema is current")


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

    from pipeline.web.server import build_server, close_read_pools, reachable_urls

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
    # Whichever warehouse is actually being served. `database_path` is always
    # set and is the SQLite file, so printing it unconditionally told an
    # operator running against PostgreSQL the name of a file this process was
    # not going to open — and the redacted URL is the one line that would have
    # made that obvious.
    ui.info(f"  warehouse: [pipeline.muted]"
             f"{settings.redacted_database_url or settings.database_path}[/]")
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
        close_read_pools()


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


def _execute_module(name: str, fn, settings, since, dry_run, limit, bar, source="all") -> dict:
    """Kept as the CLI's bar-shaped way in. The run is runner.execute_module."""
    return runner.execute_module(name, fn, settings, since, dry_run, limit,
                                  _BarObserver(bar), source=source)


def _run_waves(waves: list[list[str]], jobs: int, settings, since, dry_run, limit,
                bar, source="all") -> list[dict]:
    """Every wave, painted onto `bar`. The ordering rules are in runner.py."""
    return runner.run_waves(waves, jobs, settings, since, dry_run, limit,
                             _BarObserver(bar), source=source)


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
    api: bool = typer.Option(
        False, "--api", help="m01 only: run just the Find a Tender + Contracts "
                              "Finder live-API channels, skip the CSV archive backfill"),
    csv: bool = typer.Option(
        False, "--csv", help="m01 only: run just the Contracts Finder CSV archive "
                              "backfill, skip the live-API channels. The default when "
                              "none of --api/--csv/--kag/--all is given."),
    kag: bool = typer.Option(
        False, "--kag", help="m01 only: run just the Kaggle cross-check archive -- "
                              "compares --api/--csv coverage against a third-party "
                              "re-host of Contracts Finder, writes only to "
                              "procurement_channel_sightings/review_queue, never to "
                              "contracts. Needs KAGGLE_USERNAME/KAGGLE_KEY in .env. "
                              "Never included in --all."),
    all_sources: bool = typer.Option(
        False, "--all", help="m01 only: run every channel that writes contracts "
                              "(live APIs + CSV archive) -- not --kag, see --kag's help"),
) -> None:
    if limit is not None and limit < 1:
        # Every module tests `if ctx.limit:`, so 0 is falsy and reads as "no
        # limit at all" — typing --limit 0 to fetch nothing launches a full
        # live crawl instead. Refused rather than reinterpreted: guessing which
        # of the two opposite meanings was intended is not this CLI's call.
        ui.error(f"--limit must be 1 or more; got {limit}. "
                  "Use --dry-run to fetch and parse without writing.")
        raise typer.Exit(code=1)

    chosen_sources = [name for name, flag in
                      (("api", api), ("csv", csv), ("kag", kag), ("all", all_sources)) if flag]
    if len(chosen_sources) > 1:
        ui.error("--api, --csv, --kag and --all are mutually exclusive; got "
                  + ", ".join(f"--{name}" for name in chosen_sources) + ".")
        raise typer.Exit(code=1)
    # csv is the default: m01's live-API channels are only walked on request.
    source = chosen_sources[0] if chosen_sources else "csv"

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

    ctx = ModuleContext(conn=conn, settings=settings, since=since, dry_run=dry_run,
                         limit=limit, source=source)

    if chosen_sources:
        # Only warn when a flag was actually given -- "csv" is also the
        # silent default for every module that ignores ctx.source entirely.
        ignoring = [name for name, _ in targets if not module_meta(name).supports_source]
        if ignoring:
            typer.echo(
                f"warning: --{chosen_sources[0]} has no effect on {', '.join(ignoring)} — "
                "those modules do not scope themselves by source and will run as normal.",
                err=True)
            for name in ignoring:
                note = module_meta(name).source_note
                if note:
                    typer.echo(f"  {name}: {note}", err=True)

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
        summary = _run_waves(waves, jobs, settings, since, dry_run, limit, bar, source=source)

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


@app.command("archive-migrate")
def archive_migrate(
    dry_run: bool = typer.Option(False, "--dry-run"),
    workers: int = typer.Option(8, "--workers", min=1, max=64,
                                help="Concurrent remote archive workers."),
) -> None:
    """Inventory the local mirror, then resumably upload it to the active archive."""
    from pathlib import Path

    from pipeline.archive import ArchiveError, FilesystemArchive, get_archive

    settings = get_settings()
    local = FilesystemArchive(Path(settings.raw_archive_dir))
    inventory = local.inventory(True)
    report = local.verify()
    if not report["ok"]:
        typer.echo(f"local archive is not valid: {report['failures']}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"local: {inventory['files']:,} objects, {inventory['bytes']:,} bytes")
    if dry_run:
        return
    remote = get_archive(settings)
    remote_keys = {row["key"] for row in remote.inventory()["objects"]}

    def migrate_one(row: dict) -> bool:
        source, filename = row["key"].split("/")[2:4]
        sha = filename.split(".", 1)[0]
        body = local.read(row["key"])
        if row["key"] in remote_keys:
            try:
                if remote.read(row["key"]) == body:
                    return False
            except (FileNotFoundError, ArchiveError):
                pass
        from mimetypes import guess_type
        remote.put(source, sha, guess_type(filename)[0], body)
        return True

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="archive-migrate") as pool:
        uploaded = sum(pool.map(migrate_one, inventory["objects"]))

    # Migration records the post-upload inventory. The required complete
    # byte/hash proof remains an explicit `archive-verify` step, so interrupted
    # migrations do not download the whole archive twice before resuming.
    manifest = remote.inventory()
    manifest["verification_required"] = True
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    (Path(settings.backup_dir) / "archive-manifest.json").write_text(
        __import__("json").dumps(manifest, indent=2), encoding="utf-8")
    typer.echo(f"uploaded: {uploaded:,}; inventoried: {manifest['files']:,} objects")
    typer.echo("run archive-verify for complete byte-count and SHA-256 verification")


@app.command("archive-process")
def archive_process(
    source_system: str | None = typer.Option(None, "--source-system", help="Process one archive source directory."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Process at most this many objects."),
    force: bool = typer.Option(False, "--force", help="Re-run objects already processed by this extractor version."),
    extractor_version: str = typer.Option("1", "--extractor-version", help="Version recorded for derived output."),
) -> None:
    """Extract deterministic text/metadata from raw objects; never create claims."""
    from pipeline.archive import get_archive
    from pipeline.archive_process import process_archive

    settings = get_settings()
    conn = db.get_connection(settings)
    try:
        db.apply_migrations(conn, db.migrations_dir_for(settings))
        result = process_archive(
            conn, settings, get_archive(settings), source_system=source_system,
            limit=limit, force=force, extractor_version=extractor_version,
        )
    except Exception as exc:
        typer.echo(f"archive process failed: {exc}", err=True)
        raise typer.Exit(code=1) from None
    finally:
        conn.close()
    typer.echo(
        "archive process {run_id}: {objects} objects, {processed} processed, "
        "{skipped} skipped, {failed} failed".format(**result)
    )


@app.command("archive-verify")
def archive_verify() -> None:
    """Perform a complete key, byte-count and SHA-256 verification."""
    from pipeline.archive import get_archive
    settings = get_settings()
    report = get_archive(settings).verify()
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    (settings.backup_dir / "archive-manifest.json").write_text(
        __import__("json").dumps(report, indent=2), encoding="utf-8")
    typer.echo(__import__("json").dumps(report, indent=2))
    if not report["ok"]:
        raise typer.Exit(code=1)


@app.command("archive-mirror")
def archive_mirror() -> None:
    """Download bucket objects missing from the local recovery mirror."""
    from pipeline.archive import FilesystemArchive, get_archive
    settings = get_settings()
    remote, local = get_archive(settings), FilesystemArchive(settings.raw_archive_dir)
    copied = 0
    for row in remote.inventory()["objects"]:
        source, filename = row["key"].split("/")[2:4]
        sha = filename.split(".", 1)[0]
        if local.lookup(source, sha) is None:
            from mimetypes import guess_type
            local.put(source, sha, guess_type(filename)[0], remote.read(row["key"]))
            copied += 1
    typer.echo(f"mirrored: {copied:,} objects; local files are never deleted")


@app.command("archive-reconcile")
def archive_reconcile(repair_from_local: bool = typer.Option(False, "--repair-from-local")) -> None:
    """Report bucket/local differences; repair only with explicit opt-in."""
    from pipeline.archive import FilesystemArchive, get_archive
    settings = get_settings()
    remote, local = get_archive(settings), FilesystemArchive(settings.raw_archive_dir)
    repaired = 0
    if repair_from_local:
        for row in local.inventory(True)["objects"]:
            source, filename = row["key"].split("/")[2:4]
            sha = filename.split(".", 1)[0]
            if remote.lookup(source, sha) is None or remote.lookup(source, sha).read_bytes() != local.read(row["key"]):
                from mimetypes import guess_type
                remote.put(source, sha, guess_type(filename)[0], local.read(row["key"]))
                repaired += 1
    report = remote.verify()
    typer.echo(f"remote: {report['files']:,} objects, {report['bytes']:,} bytes; repaired {repaired:,}")
    if not report["ok"]:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
