"""Verified PostgreSQL-to-PostgreSQL transfer through the backup contract.

There is no safe merge between two writable evidence warehouses. A sync is a
one-way replacement: snapshot the source with the existing repeatable-read
backup implementation, then restore that verified snapshot into the target.
The restore path snapshots a populated target before replacing it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from pipeline import backup, catalog, pg
from pipeline.config import Settings


class PostgresSyncError(RuntimeError):
    """A transfer that would leave either PostgreSQL warehouse uncertain."""


Progress = Callable[[str], None]


def _identity(connection) -> tuple:
    row = connection.execute(
        "SELECT current_database(), current_schema(), "
        "inet_server_addr()::text, inet_server_port()"
    ).fetchone()
    return tuple(row)


def _open(url: str, label: str):
    try:
        return pg.connect(url, readonly=True, application_name=f"sectortrace-{label}")
    except Exception as exc:  # noqa: BLE001 - add the endpoint role to the error
        raise PostgresSyncError(f"could not connect to {label} PostgreSQL: {exc}") from exc


def preflight(source_url: str, target_url: str) -> dict:
    """Check endpoint identity and schema without changing either warehouse."""
    if not source_url or not target_url:
        raise PostgresSyncError(
            "both DATABASE_URL and DATABASE_SOURCE_URL are required for PostgreSQL sync.")

    source = _open(source_url, "source")
    try:
        target = _open(target_url, "target")
    except Exception:
        source.close()
        raise
    try:
        source_identity = _identity(source)
        target_identity = _identity(target)
        problems: list[str] = []
        if source_identity == target_identity:
            problems.append("source and target resolve to the same PostgreSQL database")

        source_tables = set(catalog.table_names(source))
        target_tables = set(catalog.table_names(target))
        missing = sorted(source_tables - target_tables)
        if missing:
            problems.append(f"target is missing table(s): {', '.join(missing)}")
        extra = sorted(target_tables - source_tables)
        if extra:
            counts = catalog.row_counts(target, extra)
            populated = [f"{table} ({counts[table]:,} rows)"
                         for table in extra if counts[table]]
            if populated:
                problems.append(
                    "target has unexpected populated table(s): " + ", ".join(populated))

        for table in sorted(source_tables & target_tables):
            source_columns = [column["name"] for column in catalog.columns_of(source, table)]
            target_columns = [column["name"] for column in catalog.columns_of(target, table)]
            if source_columns != target_columns:
                problems.append(
                    f"{table}: columns differ — source {source_columns}, "
                    f"target {target_columns}")
        if set(catalog.foreign_keys(source)) != set(catalog.foreign_keys(target)):
            problems.append("the PostgreSQL foreign-key graphs differ")

        return {
            "ok": not problems, "problems": problems,
            "source": source_identity, "target": target_identity,
            "source_tables": len(source_tables), "target_tables": len(target_tables),
        }
    finally:
        source.close()
        target.close()


def transfer(settings: Settings, *, source_url: str, target_url: str,
             replace: bool = False, on_step: Progress | None = None) -> dict:
    """Snapshot source and restore it into target with full verification."""
    report = preflight(source_url, target_url)
    if not report["ok"]:
        raise PostgresSyncError("preflight failed:\n- " + "\n- ".join(report["problems"]))

    source_settings = settings.model_copy(update={
        "database_url": source_url, "database_ro_url": None,
    })
    target_settings = settings.model_copy(update={
        "database_url": target_url, "database_ro_url": None,
    })

    with tempfile.TemporaryDirectory(prefix="sectortrace-pg-sync-") as directory:
        archive_path = Path(directory) / "source.sql.gz"
        if on_step:
            on_step("taking a verified snapshot of the source")
        manifest = backup.create(source_settings, destination=archive_path)
        if on_step:
            on_step(
                f"restoring {manifest['warehouse']['rows']:,} rows into the target")
        try:
            restored = backup.restore(archive_path, target_settings, force=replace)
        except backup.BackupError as exc:
            raise PostgresSyncError(str(exc)) from exc

    return {
        "source": settings._redact(source_url), "target": settings._redact(target_url),
        "rows": restored["rows"], "tables": restored["tables"],
        "verified": True, "superseded": restored.get("superseded"),
    }
