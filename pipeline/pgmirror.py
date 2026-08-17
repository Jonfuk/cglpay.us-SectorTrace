"""Verified PostgreSQL-to-PostgreSQL warehouse transfers.

The normal application has one writer. These commands are for an explicit
initial import into an empty Railway database and for refreshing a local
mirror from the Railway authority. They are intentionally one-way per run:
there is no safe meaning for two independently changed evidence warehouses to
"merge" without a conflict policy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline import catalog, db, pgload, pgverify


class MirrorError(RuntimeError):
    """A PostgreSQL mirror operation that would leave an untrusted target."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _tables(conn) -> set[str]:
    return set(catalog.table_names(conn)) - pgload.SOURCE_ONLY_TABLES


def _server_identity(conn) -> tuple:
    row = conn.execute(
        "SELECT current_database(), current_schema(), "
        "inet_server_addr()::text, inet_server_port()"
    ).fetchone()
    return tuple(row)


def preflight(source, target) -> list[str]:
    """Return schema differences before any target rows are written."""
    problems: list[str] = []
    source_tables = _tables(source)
    target_tables = _tables(target)
    if missing := sorted(source_tables - target_tables):
        problems.append(f"target is missing table(s): {', '.join(missing)}")
    if extra := sorted(target_tables - source_tables):
        problems.append(f"target has unexpected table(s): {', '.join(extra)}")

    for table in sorted(source_tables & target_tables):
        source_columns = [c["name"] for c in catalog.columns_of(source, table)]
        target_columns = [c["name"] for c in catalog.columns_of(target, table)]
        if source_columns != target_columns:
            problems.append(
                f"{table}: columns differ — source {source_columns}, "
                f"target {target_columns}")

    if set(catalog.foreign_keys(source)) != set(catalog.foreign_keys(target)):
        problems.append("the PostgreSQL foreign-key graphs differ")
    if _server_identity(source) == _server_identity(target):
        problems.append("source and target resolve to the same PostgreSQL database")
    return problems


def _target_counts(target, tables: set[str]) -> dict[str, int]:
    return {table: target.execute(
        f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
        for table in sorted(tables)}


def _truncate(target, tables: set[str]) -> None:
    names = ", ".join(catalog.quote(table) for table in sorted(tables))
    with target:
        target.execute(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")


def transfer(source, target, *, truncate: bool = False, verify: bool = True,
             on_table=None) -> dict:
    """Copy all data from source to target, then verify it."""
    problems = preflight(source, target)
    if problems:
        raise MirrorError("preflight failed:\n" + "\n".join(f"- {p}" for p in problems))

    tables = _tables(source)
    counts = _target_counts(target, tables)
    if any(counts.values()) and not truncate:
        populated = [f"{table} ({count:,})" for table, count in counts.items() if count]
        raise MirrorError(
            "target already contains rows: " + ", ".join(populated) +
            ". Refusing to merge; pass --truncate for a full replacement.")
    if truncate:
        _truncate(target, tables)

    written: dict[str, int] = {}
    for table in pgload.load_order(source):
        with target:
            written[table] = pgload.copy_table(source, target, table)
        if on_table:
            on_table(table, written[table])
    pgload.reset_sequences(target)
    target.commit()

    report = None
    if verify:
        report = pgverify.verify(source, target)
        if not report["ok"]:
            raise MirrorError(
                f"verification failed with {len(report['problems'])} problem(s): "
                + "; ".join(report["problems"][:5]))
    return {
        "tables": len(written), "rows": sum(written.values()),
        "written": written, "verified": bool(report and report["ok"]),
        "checked_at": _utcnow(),
    }


def compare(source, target) -> dict:
    """Compare two PostgreSQL warehouses without changing either one."""
    problems = preflight(source, target)
    if problems:
        return {"ok": False, "problems": problems, "checked_at": _utcnow()}
    report = pgverify.verify(source, target)
    report["checked_at"] = _utcnow()
    return report
