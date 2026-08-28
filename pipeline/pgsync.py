"""Keeping the SQLite warehouse in step with the PostgreSQL one.

`pipeline/pgload.py` moves the warehouse into PostgreSQL. This moves it back —
not as a rollback of that decision, but as the thing that keeps the rollback
real.

The plan (issue #21) says the way back from PostgreSQL is to unset
`DATABASE_URL`, and that this stays true for as long as SQLite is
dual-maintained. Both halves matter, and only the first one is free. Once
collection runs against PostgreSQL, `data/warehouse.db` stops moving: it was
seven migrations and 33,000 rows behind when this module was written, so
"unset the variable" would have landed on a warehouse missing four phases of
work. A rollback path nobody exercises is a rollback path nobody has.

Re-running the collection against SQLite is not the answer. Every row here
came from a polite crawl — one request per two seconds per host — and
collecting the same evidence twice would double what this pipeline asks of
sources that owe it nothing. Settled decision 5 is not suspended because there
are two warehouses now. So the rows come from the warehouse that has them.

What this is not:

  * **Not a merge.** The SQLite file is rebuilt from PostgreSQL and replaced
    wholesale. A row written into SQLite while PostgreSQL was authoritative is
    not preserved, and it is not supposed to be — two warehouses that both
    accept writes are two warehouses that disagree, and this exists precisely
    so that only one of them is written to.
  * **Not incremental.** There is no change log to follow: the warehouse's
    natural-key upserts overwrite in place and nothing records what moved.
    Rebuilding whole takes minutes, which is cheaper than the machinery that
    would make it clever, and is a copy rather than a reconciliation.
  * **Not a write to the source.** The PostgreSQL side is read through a
    read-only, `REPEATABLE READ` connection — one instant of the warehouse,
    so a module committing part way through cannot produce a file holding a
    child row whose parent it did not read.

The new file is built beside the old one and only swapped in **after** it has
been verified against the source with `pipeline/pgverify.py` — the same
row-by-row comparison the Phase 2 migration was accepted on, run the other way
round. What it replaces is renamed, never deleted, for the reason
`pipeline/backup.py` gives: the second-commonest reason to restore is having
restored the wrong thing.
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import catalog, db, pgbackup, pgload, pgverify
from pipeline.config import Settings, get_settings

log = structlog.get_logger()

# Rows per `executemany`. Big enough that the per-statement cost disappears,
# small enough that a 477,199-row table is never held in memory at once — the
# PostgreSQL side is streamed off a server-side cursor for the same reason.
BATCH_ROWS = 5_000

# What SQLite will store, and what PostgreSQL hands back for the three types
# this schema uses (780 text columns, 117 bigint, 51 double precision).
# Anything else — a Decimal from a numeric column, a date from a timestamptz,
# a dict from jsonb — is refused by name rather than converted. The refusal is
# the point: a column whose type changed is a decision about the evidence
# base, and this module is not where it gets made.
_STORABLE = (str, int, float, bytes)


class SyncError(RuntimeError):
    """A refresh that would leave a SQLite warehouse nobody should trust."""


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _open_target(path: Path) -> sqlite3.Connection:
    """A connection to the warehouse being built.

    `foreign_keys = ON` because the load order is the only thing making the
    references hold, and a rebuild that silently produced orphans would pass
    every count. `synchronous = OFF` because this file is not a warehouse
    until it has been verified and moved into place: a crash part way through
    discards the whole attempt, so paying for durability of an intermediate
    state buys nothing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = OFF")
    return conn


def check(settings: Settings | None = None) -> dict:
    """How far apart the two warehouses are, without writing anything.

    The question dual-maintenance needs answered on any given day, and the one
    the operator cannot answer by looking: both files exist, both are
    warehouses, and nothing about either says which one the last collection
    wrote to.
    """
    settings = settings or get_settings()
    if settings.database_backend != "postgres":
        raise SyncError(
            "there is nothing to compare: DATABASE_URL is not set, so the "
            "SQLite warehouse is the only one there is.")

    source = pgbackup.snapshot_connection(settings)
    try:
        pg_tables = set(catalog.table_names(source)) - pgload.SOURCE_ONLY_TABLES
        pg_counts = {t: source.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(t)}").fetchone()[0]
            for t in sorted(pg_tables)}
        pg_ledger = [row[0] for row in source.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename")]
    finally:
        source.close()

    path = settings.database_path
    if not path.is_file():
        absent = f"there is no SQLite warehouse at {path} to compare."
        return {"in_step": False, "rows_in_step": False, "schema_in_step": False,
                 "sqlite_present": False, "sqlite_path": str(path),
                 "postgres": settings.redacted_database_url,
                 "postgres_rows": sum(pg_counts.values()),
                 "problems": [absent], "row_problems": [absent],
                 "schema_problems": [], "checked_at": _utcnow()}

    with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as lite:
        lite.row_factory = sqlite3.Row
        lite_tables = set(catalog.table_names(lite)) - pgload.SOURCE_ONLY_TABLES
        lite_counts = {t: lite.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(t)}").fetchone()[0]
            for t in sorted(lite_tables)}
        lite_ledger = [row[0] for row in lite.execute(
            "SELECT filename FROM schema_migrations ORDER BY filename")]

    # Two answers, not one, because they are two different questions with two
    # different remedies. Rows out of step are fixed by a refresh. Ledgers out
    # of step are a checkout that does not hold every migration the server has
    # had applied — which a refresh cannot fix and should not paper over,
    # since the file it would build has a schema nobody can point at a commit
    # for. The renumbering that happens when two workstreams take the same
    # number shows up here too, as one file "ahead" and another "behind".
    behind = sorted(set(pg_ledger) - set(lite_ledger))
    ahead = sorted(set(lite_ledger) - set(pg_ledger))
    schema_problems = []
    if behind:
        schema_problems.append(
            f"the SQLite warehouse has not had {len(behind)} migration(s) "
            f"applied that PostgreSQL has: {', '.join(behind)}")
    if ahead:
        schema_problems.append(
            f"the SQLite warehouse has migrations PostgreSQL does not: "
            f"{', '.join(ahead)}")

    row_problems = []
    missing = sorted(pg_tables - lite_tables)
    if missing:
        row_problems.append(f"tables only in PostgreSQL: {', '.join(missing)}")
    extra = sorted(lite_tables - pg_tables)
    if extra:
        row_problems.append(f"tables only in SQLite: {', '.join(extra)}")

    drift = {t: {"sqlite": lite_counts[t], "postgres": pg_counts[t]}
              for t in sorted(pg_tables & lite_tables)
              if lite_counts[t] != pg_counts[t]}
    for table, counts in drift.items():
        row_problems.append(
            f"{table}: {counts['sqlite']:,} rows in SQLite, "
            f"{counts['postgres']:,} in PostgreSQL "
            f"({counts['postgres'] - counts['sqlite']:+,})")

    return {"in_step": not (row_problems or schema_problems),
             "rows_in_step": not row_problems,
             "schema_in_step": not schema_problems,
             "sqlite_present": True,
             "sqlite_path": str(path), "postgres": settings.redacted_database_url,
             "sqlite_rows": sum(lite_counts.values()),
             "postgres_rows": sum(pg_counts.values()),
             "migrations_behind": behind, "migrations_ahead": ahead,
             "drifted": drift, "problems": row_problems + schema_problems,
             "row_problems": row_problems, "schema_problems": schema_problems,
             "checked_at": _utcnow()}


def _preflight(source, target: sqlite3.Connection) -> list[str]:
    """That the file just built can hold what PostgreSQL is about to send.

    The two schemas come from two dialect trees with the same filenames, and
    `tests/test_migration_equivalence.py` diffs them on every commit — so this
    should never fire. It is here because "should never" is what the checked
    version of an assumption sounds like before it is checked, and the cost of
    finding out at row 400,000 is the whole rebuild.
    """
    problems = []
    theirs = set(catalog.table_names(source)) - pgload.SOURCE_ONLY_TABLES
    ours = set(catalog.table_names(target)) - pgload.SOURCE_ONLY_TABLES
    missing = sorted(theirs - ours)
    extra = sorted(ours - theirs)
    if missing:
        problems.append(
            "the SQLite migration tree does not build: " + ", ".join(missing)
            + ". The two trees are out of step — see "
            "pipeline/migrations/postgres/README.md.")
    if extra:
        problems.append(
            "the SQLite tree builds tables PostgreSQL does not have: "
            + ", ".join(extra))
    for table in sorted(theirs & ours):
        # portable_columns drops any PostgreSQL-only derived column
        # (authorities.geom) — it has no SQLite counterpart by design.
        here = pgload.portable_columns(target, table)
        there = pgload.portable_columns(source, table)
        if here != there:
            problems.append(
                f"{table}: columns differ. PostgreSQL {there}, SQLite {here}")
    return problems


def _copy_table(source, target: sqlite3.Connection, table: str,
                 columns: list[str]) -> int:
    """One table, streamed out of PostgreSQL and into SQLite. Rows written.

    Server-side cursor on the way out (psycopg downloads the whole result set
    otherwise, which for `la_revenue_budgets` is 477,199 rows held while the
    same number are being written beside it) and `executemany` on the way in.
    """
    column_list = ", ".join(catalog.quote(c) for c in columns)
    placeholders = ", ".join("?" for _ in columns)
    insert = (f"INSERT INTO {catalog.quote(table)} ({column_list}) "
               f"VALUES ({placeholders})")

    written = 0
    batch: list[tuple] = []
    raw = source.raw
    with raw.cursor(name=f"pgsync_{table}") as cursor:
        cursor.itersize = BATCH_ROWS
        cursor.execute(f"SELECT {column_list} FROM {catalog.quote(table)}")
        for row in cursor:
            values = tuple(row)
            for value, column in zip(values, columns):
                if value is not None and not isinstance(value, _STORABLE):
                    raise SyncError(
                        f"{table}.{column}: PostgreSQL returned a "
                        f"{type(value).__name__}, which SQLite has no storage "
                        "class for. Nothing here converts — a column whose "
                        "type changed needs deciding about, not casting.")
            batch.append(values)
            if len(batch) >= BATCH_ROWS:
                target.executemany(insert, batch)
                written += len(batch)
                batch = []
        if batch:
            target.executemany(insert, batch)
            written += len(batch)
    return written


def refresh(settings: Settings | None = None, *, destination: Path | None = None,
             verify: bool = True, deep: bool = True, force: bool = False,
             on_table=None) -> dict:
    """Rebuild the SQLite warehouse from PostgreSQL, verify it, then swap it in.

    Returns the run's summary. Raises `SyncError` rather than leaving a file
    that looks like a warehouse and has not been checked — which is the whole
    reason the build happens beside the target rather than into it.
    """
    settings = settings or get_settings()
    if settings.database_backend != "postgres":
        raise SyncError(
            "there is nothing to sync from: DATABASE_URL is not set.")

    target_path = destination or settings.database_path
    if destination is not None and destination.exists() and not force:
        raise SyncError(f"{destination} already exists; refusing to overwrite it.")

    started = time.monotonic()
    building = target_path.with_name(f"{target_path.name}.rebuilding-{_stamp()}")
    building.unlink(missing_ok=True)

    source = pgbackup.snapshot_connection(settings)
    counts: dict[str, int] = {}
    try:
        new = _open_target(building)
        try:
            # The SQLite tree, named rather than resolved: `migrations_dir_for`
            # answers with the *configured* backend's dialect, which here is
            # PostgreSQL — this is the one place in the codebase building a
            # SQLite schema while pointed at a PostgreSQL warehouse.
            applied = db.apply_migrations(new, settings.migrations_dir)
            new.commit()
            log.info("pgsync.schema_built", migrations=len(applied),
                      path=str(building))

            problems = _preflight(source, new)
            if problems:
                raise SyncError(
                    "the refresh was refused before writing anything:\n  - "
                    + "\n  - ".join(problems))

            for table in pgload.load_order(source):
                # Drops authorities.geom: PostGIS geometry has no SQLite
                # storage class, and geometry_geojson (which is copied) is the
                # source of truth the mirror keeps.
                columns = pgload.portable_columns(source, table)
                if on_table:
                    on_table(table, None)
                written = _copy_table(source, new, table, columns)
                new.commit()
                counts[table] = written
                log.info("pgsync.table", table=table, rows=written)
                if on_table:
                    on_table(table, written)

            # SQLite maintains `sqlite_sequence` itself when an explicit
            # rowid larger than the current maximum is inserted, so there is
            # no `setval` equivalent to run here — but it is the same hazard
            # the loader has, and the one whose failure arrives days later as
            # a duplicate key on somebody's review decision. Asserted rather
            # than assumed.
            problems = _sequence_problems(new)
            if problems:
                raise SyncError(
                    "the rebuilt warehouse would hand out ids that are "
                    "already taken:\n  - " + "\n  - ".join(problems))
            new.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            new.close()

        report = None
        if verify:
            with closing(sqlite3.connect(f"file:{building}?mode=ro",
                                          uri=True)) as reader:
                reader.row_factory = sqlite3.Row
                report = pgverify.verify(reader, source, deep=deep)
            if not report["ok"]:
                raise SyncError(
                    f"{building} does not match the PostgreSQL warehouse and "
                    "has not been installed:\n  - "
                    + "\n  - ".join(report["problems"][:10]))
    except BaseException:
        building.unlink(missing_ok=True)
        for sidecar in ("-wal", "-shm"):
            building.with_name(building.name + sidecar).unlink(missing_ok=True)
        raise
    finally:
        source.close()

    superseded = _install(building, target_path)
    elapsed = round(time.monotonic() - started, 1)
    log.info("pgsync.complete", rows=sum(counts.values()), tables=len(counts),
              seconds=elapsed, target=str(target_path), superseded=superseded)
    return {"target": str(target_path), "rows": sum(counts.values()),
             "tables": len(counts), "counts": counts,
             "superseded": superseded, "verified": bool(verify),
             "deep": deep and bool(verify), "elapsed_seconds": elapsed,
             "source": settings.redacted_database_url,
             "problems": (report or {}).get("problems", [])}


def _sequence_problems(conn: sqlite3.Connection) -> list[str]:
    """`sqlite_sequence` entries that are behind the rows in their table."""
    has_table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='sqlite_sequence'").fetchone()
    if has_table is None:
        return []

    problems = []
    for row in conn.execute("SELECT name, seq FROM sqlite_sequence").fetchall():
        table, seq = row["name"], row["seq"]
        key = catalog.primary_key(conn, table)
        if len(key) != 1:
            continue
        highest = conn.execute(
            f"SELECT MAX({catalog.quote(key[0])}) FROM {catalog.quote(table)}"
        ).fetchone()[0]
        if highest is not None and seq < highest:
            problems.append(
                f"{table}: the next id would be {seq + 1:,} and "
                f"{highest:,} is already in use")
    return problems


def _install(built: Path, target: Path) -> str | None:
    """Move the verified file into place, keeping whatever it replaces.

    The same three steps `backup.restore` takes, and for the same reasons:
    checkpoint the WAL *before* renaming, because the sidecars are named after
    the file rather than carried with it and the most recently committed rows
    would be left behind; delete the sidecars beside the target, because a
    stale WAL next to a replaced database is how a good copy becomes a corrupt
    warehouse; and rename rather than delete, because the file being replaced
    may be the only copy of something.
    """
    superseded = None
    if target.exists():
        try:
            with closing(sqlite3.connect(target)) as live:
                live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError as exc:
            log.warning("pgsync.checkpoint_failed", target=str(target),
                         error=str(exc))
        superseded = target.with_name(f"{target.name}.superseded-{_stamp()}")
        try:
            target.rename(superseded)
        except OSError as exc:
            # Windows refuses to rename a file another process has open, and
            # the web server keeps a connection per request against exactly
            # this file. The rebuild is finished and verified at this point,
            # so the answer is to say what is holding it rather than to fall
            # back on copying over the top — which would destroy the warehouse
            # this step exists to keep.
            raise SyncError(
                f"{target} could not be moved aside ({exc}). Something else "
                "has the warehouse open — the web server is the usual "
                f"answer. Stop it and re-run; the rebuilt warehouse is at "
                f"{built} and is not lost.") from None

    for sidecar in ("-wal", "-shm"):
        target.with_name(target.name + sidecar).unlink(missing_ok=True)
        built.with_name(built.name + sidecar).unlink(missing_ok=True)

    built.replace(target)
    return str(superseded) if superseded else None
