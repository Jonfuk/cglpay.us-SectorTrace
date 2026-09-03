"""Snapshotting the PostgreSQL warehouse, and knowing the snapshot is one.

`pipeline/backup.py` holds the contract this has to keep: a backup is verified
before it is called one, the raw archive is inventoried rather than copied, and
nothing that fails a check is left behind looking like a copy. What changes
under PostgreSQL is only *how* the bytes are taken — `VACUUM INTO` is a
statement SQLite has and PostgreSQL does not.

**Why this is not `pg_dump`.** The plan (issue #21) proposed
`pg_dump --format=custom`, and for most projects that is the right answer. Two
things argued against it here:

  * `pg_dump` must be at least the server's major version to dump it. The
    warehouse is on PostgreSQL 18; the machine that runs the collection has no
    PostgreSQL client installed at all, and a backup tool that cannot run on
    the operator's machine is a backup tool that does not run. Any future
    Railway image would carry the same version-matched dependency.
  * The one thing `pg_dump` does that this cannot — emit the schema — is
    something this project does not need it for. The schema *is*
    `pipeline/migrations/postgres/`, in git, applied in a recorded order. A
    dump that carried its own DDL would be a second copy of the schema, free
    to disagree with the tree.

So the archive holds data and a ledger, and the schema comes from the
migration tree. That is a real constraint and it is written into the header:
restoring needs a checkout whose PostgreSQL tree contains the migrations named
there. `restore()` refuses rather than discovering it half way in.

**The format is a gzipped SQL script.** Every table is a `COPY ... FROM stdin`
block whose bytes are exactly what the server produced for `COPY ... TO
STDOUT` — PostgreSQL writes the text format and PostgreSQL parses it back, so
there is no escaping convention in this file to get wrong. It is restorable by
`psql -f` without this tool, which matters more than it sounds: the reason to
avoid a bespoke container format is the day somebody needs the data and this
repository is not what they have.

**The snapshot is consistent.** Every `COPY` runs inside one `REPEATABLE READ,
READ ONLY` transaction, which is the mechanism `pg_dump` itself uses: all the
tables are read as of one instant, so a module committing between two of them
cannot produce an archive holding a child row whose parent is missing.

**The archive proves itself.** The trailer — written last, after every byte of
data — carries the row count and a SHA-256 of each table's block. Verification
re-reads the whole file, decompresses it (gzip's own CRC covers that), counts
the rows and re-hashes the blocks. A truncated file has no trailer and fails
on that; a corrupted one fails on its table's hash, which names the table
rather than the file.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import catalog, db, pgschema
from pipeline.backup import (
    POSTGRES_SUFFIX as ARCHIVE_SUFFIX,
)
from pipeline.backup import (
    BackupError,
    archive_inventory,
    companion,
)
from pipeline.config import Settings, get_settings

log = structlog.get_logger()

# `ARCHIVE_SUFFIX` is `.sql.gz`, defined in `pipeline/backup.py` because that
# is where the listing and the retention rule read it. Two suffixes rather
# than one so `.gz` still means gzip to every tool on the machine and `.sql`
# still means "you can read this".
#
# Bumped when a reader written against version N could misread version N+1.
# Adding a key to the header or the trailer does not qualify; changing what a
# COPY block means does.
FORMAT_VERSION = 1

_HEADER_MARKER = "-- sectortrace-pgdump "
_TRAILER_MARKER = "-- sectortrace-trailer "
_COPY_LINE = re.compile(rb'^COPY ("(?:[^"]|"")+") \((.*)\) FROM stdin;$')

# How much of a table's block to hand to `COPY FROM STDIN` at a time on the
# way back in. The archive is read a line at a time — the format is
# line-oriented and a 477,199-row table cannot be held in memory as one
# bytes object — and writing each line separately costs a call per row.
_RESTORE_CHUNK_BYTES = 1 << 20

# gzip's default is 9, which on a 500 MB stream spends minutes to save a few
# per cent. 6 is the level the format itself defaults to elsewhere and the
# difference on this data is under 2%; the backup runs on a schedule, and a
# backup that takes long enough to notice is a backup that gets skipped.
_COMPRESSION_LEVEL = 6


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utcnow() -> str:
    return _now().isoformat(timespec="seconds")


def snapshot_connection(settings: Settings) -> _ConnAdapter:
    """A read-only, single-instant view of the warehouse, in this codebase's
    dialect.

    `REPEATABLE READ, READ ONLY` so every table in the dump is read as of one
    instant, whatever the dump's duration.
    """
    return _ConnAdapter(_connect_for_snapshot(settings))


def _connect_for_snapshot(settings: Settings):
    """A connection that reads one instant of the warehouse and cannot write.

    `REPEATABLE READ` fixes the snapshot at the first statement, so the tables
    are read as of one moment however long the dump takes; `READ ONLY` is the
    same argument as `mode=ro` on the SQLite side — this runs against the
    authoritative warehouse, and the guarantee that it cannot write should not
    depend on this module being correct.
    """
    import psycopg

    from pipeline import pg

    # The project's own row factory, because `catalog` addresses rows by name
    # and psycopg's default hands back plain tuples.
    conn = psycopg.connect(settings.database_url,
                            row_factory=pg.row_factory,
                            application_name="sectortrace-backup")
    try:
        conn.read_only = True
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
    except Exception:
        conn.close()
        raise
    return conn


def _server_version(conn) -> str:
    return conn.execute("SELECT version()").fetchone()[0]


def _applied_migrations(conn) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT filename FROM schema_migrations ORDER BY filename")]


def dump(settings: Settings | None = None, destination: Path | None = None,
          label: str | None = None) -> dict:
    """Write a verified snapshot of the PostgreSQL warehouse. Returns the
    manifest.

    The archive is written to a `.partial` file and renamed only once the
    trailer is down and the whole thing has been read back. An interrupted
    dump therefore leaves something that is visibly not a backup, rather than
    a short file with a plausible name — the failure `backup.create` guards
    against by unlinking, taken the other way round because renaming is atomic
    and unlinking is not.
    """
    settings = settings or get_settings()
    if settings.database_backend != "postgres":
        raise BackupError(
            "this is the PostgreSQL backup path and DATABASE_URL is not set.")

    started = _now()
    name = (f"warehouse-{started.strftime('%Y%m%dT%H%M%SZ')}"
             + (f"-{label}" if label else ""))
    target = destination or (settings.backup_dir / f"{name}{ARCHIVE_SUFFIX}")
    target.parent.mkdir(parents=True, exist_ok=True)

    if destination is None:
        # Same reasoning as the SQLite path: a second-resolution name the
        # caller did not choose, colliding, is not their mistake to be told
        # about.
        attempt = 2
        while target.exists():
            target = settings.backup_dir / f"{name}-{attempt}{ARCHIVE_SUFFIX}"
            attempt += 1
    elif target.exists():
        raise BackupError(f"{target} already exists; refusing to overwrite it.")

    partial = target.with_name(target.name + ".partial")
    log.info("backup.starting", source=settings.redacted_database_url,
              target=str(target))

    conn = _connect_for_snapshot(settings)
    try:
        counts, digests, header = _write_archive(conn, partial, settings, started)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    # Read back what was just written, with the writer closed and out of the
    # way. `backup.verify_copy` reopens the copy for the same reason: a file
    # checked by the process that wrote it is agreeing with its own memory of
    # what it meant to write.
    verified = verify_archive(partial)
    if verified["counts"] != counts:
        raise BackupError(
            "the archive does not read back as it was written: "
            f"{_first_difference(counts, verified['counts'])}")

    partial.replace(target)

    archive, listing = archive_inventory(settings.raw_archive_dir)
    manifest = {
        "created_at": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round((_now() - started).total_seconds(), 1),
        "backend": "postgres",
        "warehouse": {
            "source": settings.redacted_database_url,
            "backup": str(target),
            "backup_bytes": target.stat().st_size,
            "tables": len(counts),
            "rows": sum(counts.values()),
            "counts": counts,
            "migrations": header["migrations"],
            "sha256": digests,
        },
        # Recorded, not copied — see pipeline/backup.py's docstring. The
        # archive is on the machine that runs the collection whichever
        # backend holds the rows.
        "raw_archive": {"path": str(settings.raw_archive_dir), **archive},
        "server_version": header["server_version"],
        "format": FORMAT_VERSION,
    }
    companion(target, ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    if listing:
        companion(target, ".archive.txt").write_text(
            "\n".join(listing) + "\n", encoding="utf-8")

    log.info("backup.complete", target=str(target),
              bytes=manifest["warehouse"]["backup_bytes"],
              rows=manifest["warehouse"]["rows"], archive_files=archive["files"])
    return manifest


def _first_difference(expected: dict[str, int], found: dict[str, int]) -> str:
    for table in sorted(set(expected) | set(found)):
        if expected.get(table) != found.get(table):
            return (f"{table}: wrote {expected.get(table)}, "
                     f"read back {found.get(table)}")
    return "no difference found, which should not be possible"


def _write_archive(conn, path: Path, settings: Settings,
                    started: datetime) -> tuple[dict[str, int], dict[str, str], dict]:
    """Stream every table into `path`. Returns counts, digests and the header.

    The table order is the loader's — parents before children, including the
    edges the triggers impose and no foreign key expresses — so that restoring
    the file in the order it was written satisfies every reference and every
    refusal from migrations 0030 and 0033 as it goes. See
    `pipeline/pgschema.py`.
    """
    asked = _ConnAdapter(conn)
    tables = pgschema.load_order(asked)
    header = {
        "format": FORMAT_VERSION,
        "created_at": started.isoformat(timespec="seconds"),
        "source": settings.redacted_database_url,
        "server_version": _server_version(conn),
        "migrations": _applied_migrations(conn),
        "tables": tables,
    }

    counts: dict[str, int] = {}
    digests: dict[str, str] = {}
    with gzip.open(path, "wb", compresslevel=_COMPRESSION_LEVEL) as out:
        out.write(b"-- SectorTrace PostgreSQL warehouse snapshot.\n")
        out.write(b"-- Data and a migration ledger; the schema is "
                   b"pipeline/migrations/postgres/.\n")
        out.write(b"-- Restore with `pipeline restore`, which applies that "
                   b"tree first and checks it\n-- against the ledger below. "
                   b"Or by hand: migrate an empty database, then psql -f.\n")
        out.write((_HEADER_MARKER + json.dumps(header) + "\n").encode("utf-8"))

        for table in tables:
            columns = [c["name"] for c in catalog.columns_of(asked, table)]
            column_list = ", ".join(catalog.quote(c) for c in columns)
            out.write(b"\n")
            out.write(f"COPY {catalog.quote(table)} ({column_list}) "
                       "FROM stdin;\n".encode("utf-8"))

            rows = 0
            digest = hashlib.sha256()
            with conn.cursor() as cursor:
                with cursor.copy(f"COPY {catalog.quote(table)} ({column_list}) "
                                  "TO STDOUT") as copy:
                    for block in copy:
                        # `block` is a memoryview over psycopg's buffer and is
                        # only valid until the next read, so everything that
                        # looks at it happens here.
                        data = bytes(block)
                        rows += data.count(b"\n")
                        digest.update(data)
                        out.write(data)
            out.write(b"\\.\n")

            # Asked inside the same snapshot transaction the COPY ran in, so
            # this is not "the table now" — it is the table the archive holds.
            # A difference here means the stream and the count disagree about
            # one instant, which is a fault in this module and not a race.
            expected = conn.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
            if rows != expected:
                raise BackupError(
                    f"{table}: the snapshot holds {expected:,} rows and "
                    f"{rows:,} were written. The archive is not a copy of "
                    "anything and has not been kept.")
            counts[table] = rows
            digests[table] = digest.hexdigest()
            log.info("backup.table", table=table, rows=rows)

        trailer = {"rows": sum(counts.values()), "counts": counts,
                    "sha256": digests, "finished_at": _utcnow()}
        out.write(b"\n")
        out.write((_TRAILER_MARKER + json.dumps(trailer) + "\n").encode("utf-8"))

    return counts, digests, header


class _ConnAdapter:
    """A raw psycopg connection wearing the methods `catalog` and `pgschema`
    call on a warehouse connection.

    Those helpers dispatch on `db.backend_of`, which asks whether the object is
    a `sqlite3.Connection` — anything else is PostgreSQL — and then execute
    `?`-style SQL. A raw psycopg connection fails on the placeholders, so the
    snapshot connection is wrapped rather than opened through
    `pipeline.pg.connect`: this one needs `read_only` and an isolation level
    set before the first statement, which is not what `pg.connect` builds.
    """

    __slots__ = ("_conn",)

    def __init__(self, conn) -> None:
        self._conn = conn

    def execute(self, sql, parameters=()):
        from pipeline.sqldialect import to_psycopg

        translated, params = to_psycopg(sql, parameters)
        return self._conn.execute(translated, params)

    def close(self) -> None:
        self._conn.close()

    @property
    def raw(self):
        return self._conn


def read_header(path: Path) -> dict:
    """The archive's header, without reading its data.

    Cheap enough to call before deciding anything: gzip decompresses the first
    block and stops.
    """
    try:
        with gzip.open(path, "rb") as archive:
            for line in archive:
                text = line.decode("utf-8", "replace")
                if text.startswith(_HEADER_MARKER):
                    return json.loads(text[len(_HEADER_MARKER):])
                if not text.startswith("--"):
                    break
    except OSError as exc:
        raise BackupError(f"{path} cannot be read as a gzip archive: {exc}") from exc
    except ValueError as exc:
        raise BackupError(f"{path} has an unreadable header: {exc}") from exc
    raise BackupError(
        f"{path} has no SectorTrace header. It is not a warehouse snapshot, "
        "or it is one from before this format.")


def verify_archive(path: Path) -> dict:
    """Read the whole archive and prove it holds what it says it does.

    Every check here is against the file's own trailer rather than against the
    live warehouse, and that is the point: the question a restore needs
    answered is "is this file intact", which has to be answerable with the
    server unreachable and the warehouse gone.
    """
    header = read_header(path)
    if header.get("format") != FORMAT_VERSION:
        raise BackupError(
            f"{path} is format {header.get('format')!r}; this version of the "
            f"pipeline reads {FORMAT_VERSION}.")

    counts: dict[str, int] = {}
    digests: dict[str, str] = {}
    trailer: dict | None = None
    table: str | None = None
    digest = None
    rows = 0

    try:
        with gzip.open(path, "rb") as archive:
            for line in archive:
                if table is None:
                    text = line.decode("utf-8", "replace")
                    if text.startswith(_TRAILER_MARKER):
                        trailer = json.loads(text[len(_TRAILER_MARKER):])
                        continue
                    match = _COPY_LINE.match(line.rstrip(b"\n"))
                    if match:
                        table = _unquote(match.group(1).decode("utf-8"))
                        digest = hashlib.sha256()
                        rows = 0
                    continue
                if line == b"\\.\n":
                    counts[table] = rows
                    digests[table] = digest.hexdigest()
                    table = None
                    continue
                digest.update(line)
                rows += 1
    except (OSError, EOFError) as exc:
        raise BackupError(
            f"{path} did not decompress to the end ({exc}). A gzip stream "
            "carries a checksum of its own contents, so this is a truncated "
            "or damaged file rather than a disagreement about what is in "
            "it.") from exc
    except ValueError as exc:
        raise BackupError(f"{path} has an unreadable trailer: {exc}") from exc

    if table is not None:
        raise BackupError(
            f"{path} ends inside {table}'s rows. The dump did not finish.")
    if trailer is None:
        raise BackupError(
            f"{path} has no trailer, which is written last. The dump did not "
            "finish, or the file has been truncated.")

    problems = []
    for name in sorted(set(trailer["counts"]) | set(counts)):
        if trailer["counts"].get(name) != counts.get(name):
            problems.append(
                f"{name}: the trailer says {trailer['counts'].get(name)} rows, "
                f"the file holds {counts.get(name)}")
        elif trailer["sha256"].get(name) != digests.get(name):
            problems.append(f"{name}: its rows are not the bytes that were hashed")
    if problems:
        raise BackupError(
            f"{path} fails its own checks:\n  - " + "\n  - ".join(problems))

    return {"tables": len(counts), "rows": sum(counts.values()), "counts": counts,
             "sha256": digests, "migrations": header["migrations"],
             "created_at": header["created_at"], "source": header["source"],
             "server_version": header["server_version"]}


def _unquote(identifier: str) -> str:
    if identifier.startswith('"') and identifier.endswith('"'):
        return identifier[1:-1].replace('""', '"')
    return identifier


def restore(archive: Path, settings: Settings | None = None,
             force: bool = False, on_table=None) -> dict:
    """Put a snapshot back into the configured PostgreSQL warehouse.

    Three refusals, in this order, and each of them is a way a restore turns
    into a loss:

      * an archive that fails its own verification is not restored at all;
      * an archive naming migrations this checkout's tree does not have is
        refused, because the schema comes from the tree and a tree that is
        behind cannot hold the columns the file carries;
      * a warehouse holding rows needs `force`, and even then it is snapshotted
        first. `backup.restore` renames the file it replaces for the same
        reason: the second-commonest reason to restore is having restored the
        wrong one.
    """
    settings = settings or get_settings()
    if settings.database_backend != "postgres":
        raise BackupError(
            "this is the PostgreSQL restore path and DATABASE_URL is not set.")
    if not archive.is_file():
        raise BackupError(f"no snapshot at {archive}.")

    verified = verify_archive(archive)

    target = db.get_connection(settings)
    try:
        applied = db.apply_migrations(target, db.migrations_dir_for(settings))
        target.commit()
        if applied:
            log.info("backup.migrated_before_restore", applied=applied)

        ledger = set(_applied_migrations(target))
        missing = sorted(set(verified["migrations"]) - ledger)
        if missing:
            raise BackupError(
                f"{archive} was taken from a warehouse with migrations this "
                f"one does not have: {', '.join(missing)}. The schema comes "
                "from pipeline/migrations/postgres/, so restoring here would "
                "put the rows into a schema that predates them. Check out the "
                "commit that has those files first.")
        ahead = sorted(ledger - set(verified["migrations"]))

        tables = pgschema.load_order(target)
        unknown = sorted(set(verified["counts"]) - set(tables))
        if unknown:
            raise BackupError(
                f"{archive} holds tables this warehouse does not have: "
                f"{', '.join(unknown)}.")

        occupied = {}
        for table in tables:
            count = target.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
            if count:
                occupied[table] = count
        superseded = None
        if occupied:
            if not force:
                raise BackupError(
                    f"{settings.redacted_database_url} already holds "
                    f"{sum(occupied.values()):,} rows across "
                    f"{len(occupied)} table(s). Restoring would replace them. "
                    "Re-run with force, which snapshots them first.")
            superseded = dump(settings, label="superseded-by-restore")["warehouse"]["backup"]
            log.info("backup.superseded_snapshot", path=superseded)
            # Emptied inside the restore's own transaction rather than through
            # `pgschema.truncate_all`, which commits: that is right for a
            # migration, which is a thing you resume, and wrong for a restore,
            # which either replaced the warehouse or did not. Committing the
            # emptying separately would mean a restore that failed half way
            # had already discarded everything.
            target.execute(
                f"TRUNCATE {', '.join(catalog.quote(t) for t in tables)} "
                "RESTART IDENTITY")

        written = _restore_data(archive, target, on_table=on_table)

        drift = {t: (verified["counts"][t], written.get(t, 0))
                  for t in verified["counts"]
                  if verified["counts"][t] != written.get(t, 0)}
        if drift:
            # Nothing is committed at this point, so raising here leaves the
            # warehouse as it was — including the rows this was about to
            # replace them with.
            raise BackupError(
                "the restore did not write what the archive holds: "
                + ", ".join(f"{t}: archive {a:,}, written {b:,}"
                             for t, (a, b) in sorted(drift.items())))

        sequences = pgschema.reset_sequences(target)
        target.commit()
    finally:
        target.close()

    log.info("backup.restored", archive=str(archive),
              target=settings.redacted_database_url,
              rows=sum(written.values()), superseded=superseded)
    return {"restored": settings.redacted_database_url, "from": str(archive),
             "rows": sum(written.values()), "tables": len(written),
             "superseded": superseded, "sequences": sequences,
             "migrations_ahead_of_archive": ahead,
             "empty_tables_not_in_archive": sorted(set(tables) - set(written))}


def _restore_data(archive: Path, target, on_table=None) -> dict[str, int]:
    """Feed every `COPY` block in the archive back through `COPY FROM STDIN`.

    One transaction for the whole file, committed by the caller. That is
    deliberate: a restore is a thing that either replaced the warehouse or did
    not. Half a restore is a warehouse nobody can reason about.
    """
    written: dict[str, int] = {}
    raw = target.raw
    with gzip.open(archive, "rb") as source:
        cursor = raw.cursor()
        for line in source:
            match = _COPY_LINE.match(line.rstrip(b"\n"))
            if not match:
                continue
            table = _unquote(match.group(1).decode("utf-8"))
            if on_table:
                on_table(table, None)

            rows = 0
            buffer = bytearray()
            with cursor.copy(line.rstrip(b"\n").decode("utf-8")) as copy:
                for data in source:
                    if data == b"\\.\n":
                        break
                    buffer += data
                    rows += 1
                    if len(buffer) >= _RESTORE_CHUNK_BYTES:
                        copy.write(bytes(buffer))
                        buffer.clear()
                if buffer:
                    copy.write(bytes(buffer))
            written[table] = rows
            log.info("backup.restored_table", table=table, rows=rows)
            if on_table:
                on_table(table, rows)
    return written
