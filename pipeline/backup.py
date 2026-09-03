"""Copying the warehouse, and knowing what the archive should contain.

This pipeline is slow on purpose. One request per two seconds per host, robots
respected, conditional requests, and a full collection is hours of it. The
warehouse is the only place that work exists in a queryable form, and until
now nothing copied it.

Two artefacts, because the two halves of the evidence base fail differently:

  * **The warehouse** is copied, with `VACUUM INTO`. That is not a file copy:
    SQLite runs it inside a read transaction, so the result is a consistent
    snapshot of a database that is being written to, with no WAL sidecar to
    forget and no risk of catching a half-committed transaction. It also
    compacts, which matters after a module rewrites a large table.

  * **The raw archive** is *not* copied. It is 3.6 GB against a warehouse in
    the hundreds of MB, and duplicating it onto the same disk buys very little.
    What is written instead is a manifest: every file, its source system and
    its size. The archive is content-addressed -- `data/raw/{source}/{sha256}`
    -- so a manifest is enough to say exactly which documents are missing after
    a partial loss, and each surviving file can be checked against its own
    name. Knowing precisely what is gone is most of the value; re-fetching a
    named list is something this pipeline can do politely.

A backup is verified before it is called one. `VACUUM INTO` can fail part-way
and leave a file, and a backup nobody checked is a hope rather than a copy, so
the new database is opened, integrity-checked, and compared table by table
against the source it came from.

Both of those halves are about the warehouse's *contents*, not about SQLite,
and the warehouse now has two backends. When `DATABASE_URL` is set this module
keeps the contract and hands the copying to `pipeline/pgbackup.py`, which takes
a consistent snapshot the way PostgreSQL offers one — see that module for why
it is not `pg_dump`. The manifest, the archive inventory, the retention rule
and the refusal to overwrite are the same either way; they were never about
the file format.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import db
from pipeline.archive import get_archive
from pipeline.config import Settings, get_settings

log = structlog.get_logger()

# `VACUUM INTO` landed in SQLite 3.27. Everything else here would work without
# it; nothing else gives a consistent copy of a live database in one statement.
MIN_SQLITE = (3, 27, 0)

# What a backup of each backend is called on disk. Both are `warehouse-<stamp>`
# so one listing, one retention rule and one set of companion files cover them;
# the suffix is what says which backend took it, and `restore` refuses the
# wrong one rather than trying to read it.
SQLITE_SUFFIX = ".db"
POSTGRES_SUFFIX = ".sql.gz"
# Longest first: `.sql.gz` and `.db` do not collide, but a future `.db.gz`
# would, and stripping the shorter one first would leave `.gz` behind.
BACKUP_SUFFIXES = (POSTGRES_SUFFIX, SQLITE_SUFFIX)


class BackupError(RuntimeError):
    """A backup that cannot be trusted, or a restore that would lose data."""


def companion(backup: Path, suffix: str) -> Path:
    """The manifest or listing beside a backup, whatever its own suffix is.

    `warehouse-….db` and `warehouse-….sql.gz` both answer
    `warehouse-….manifest.json`. Not `with_suffix`, which sees `.sql.gz` as a
    name ending in `.gz` and would file the manifest under
    `warehouse-….sql.manifest.json` — beside the backup, and not where
    anything looks for it.
    """
    name = backup.name
    for known in BACKUP_SUFFIXES:
        if name.endswith(known):
            name = name[: -len(known)]
            break
    else:
        name = backup.stem
    return backup.with_name(name + suffix)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).strftime("%Y%m%dT%H%M%SZ")


def _require_vacuum_into() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE:
        raise BackupError(
            f"SQLite {'.'.join(map(str, MIN_SQLITE))} or newer is needed for a "
            f"consistent backup (VACUUM INTO); this Python has "
            f"{sqlite3.sqlite_version}.")


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """Row counts for every table, which is what a copy has to reproduce."""
    names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return {name: conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
             for name in names}


def archive_inventory(raw_dir: Path) -> tuple[dict, list[str]]:
    """What is in the raw archive, by source system, and the file list.

    Sizes and names only. The names *are* the SHA-256 of the bytes, so this
    does not need to hash anything to be checkable -- which is what keeps it
    seconds rather than minutes over 6,000 files.
    """
    by_source: dict[str, dict[str, int]] = {}
    listing: list[str] = []
    if not raw_dir.is_dir():
        return {"sources": {}, "files": 0, "bytes": 0, "present": False}, listing

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(raw_dir).as_posix()
        source = relative.split("/")[0] if "/" in relative else "(root)"
        entry = by_source.setdefault(source, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += path.stat().st_size
        listing.append(relative)

    return ({"sources": by_source,
              "files": sum(e["files"] for e in by_source.values()),
              "bytes": sum(e["bytes"] for e in by_source.values()),
              "present": True},
             listing)


def verify_copy(source: Path, copy: Path) -> dict:
    """Open the copy and prove it holds what the original does.

    Both counts are taken after the copy is written. A row inserted into the
    live warehouse in between is not a fault in the backup, so a difference is
    reported rather than raised on -- except for a table that is missing
    outright or an integrity failure, which are.
    """
    try:
        with closing(sqlite3.connect(f"file:{copy}?mode=ro", uri=True)) as copied:
            integrity = copied.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise BackupError(f"the copy failed its integrity check: {integrity}")
            copied_counts = table_counts(copied)
            migrations = [row[0] for row in copied.execute(
                "SELECT filename FROM schema_migrations ORDER BY filename")]
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"the copy cannot be read as a database: {exc}") from exc

    with closing(sqlite3.connect(f"file:{source}?mode=ro", uri=True)) as original:
        source_counts = table_counts(original)

    missing = sorted(set(source_counts) - set(copied_counts))
    if missing:
        raise BackupError(f"the copy is missing tables: {', '.join(missing)}")

    drifted = {name: {"source": source_counts[name], "copy": copied_counts[name]}
                for name in source_counts
                if source_counts[name] != copied_counts[name]}
    return {"integrity": integrity, "tables": len(copied_counts),
             "rows": sum(copied_counts.values()), "counts": copied_counts,
             "migrations": migrations, "drifted_while_copying": drifted}


def create(settings: Settings | None = None, destination: Path | None = None,
            label: str | None = None) -> dict:
    """Back up the warehouse, verify it, and write its manifest.

    Returns the manifest. Raises `BackupError` rather than leaving anything
    that looks like a backup and is not.
    """
    settings = settings or get_settings()
    if not settings.database_url:
        raise BackupError(
            "PostgreSQL backup path requires DATABASE_URL; no warehouse "
            "was configured.")
    if settings.database_backend == "postgres":
        from pipeline import pgbackup

        return pgbackup.dump(settings, destination=destination, label=label)

    _require_vacuum_into()

    source = settings.database_path
    if not source.is_file():
        raise BackupError(f"no warehouse at {source} to back up.")

    started = _now()
    name = f"warehouse-{_stamp(started)}" + (f"-{label}" if label else "")
    target = destination or (settings.backup_dir / f"{name}.db")
    target.parent.mkdir(parents=True, exist_ok=True)

    if destination is None:
        # The default name is second-resolution, and two backups inside one
        # second are a thing that happens -- a script taking one before and
        # after a short module, or a test suite. Take the next free suffix
        # rather than refusing: the caller did not choose this name, so a
        # collision in it is not their mistake to be told about.
        attempt = 2
        while target.exists():
            target = settings.backup_dir / f"{name}-{attempt}.db"
            attempt += 1
    elif target.exists():
        # A path someone typed is different: overwriting it silently is how a
        # backup gets replaced by a worse one.
        raise BackupError(f"{target} already exists; refusing to overwrite it.")

    log.info("backup.starting", source=str(source), target=str(target))
    conn = db.get_connection(settings)
    try:
        # Parameters are not allowed in VACUUM INTO, and this path comes from
        # settings or the command line rather than from the warehouse. Quoted
        # as a SQL string literal with the one escape that matters.
        literal = str(target).replace("'", "''")
        conn.execute(f"VACUUM INTO '{literal}'")
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise BackupError(f"VACUUM INTO failed: {exc}") from exc
    finally:
        conn.close()

    verified = verify_copy(source, target)
    if settings.archive_backend == "filesystem":
        archive, listing = archive_inventory(settings.raw_archive_dir)
    else:
        archive = get_archive(settings).inventory()
        listing = [row["key"] for row in archive["objects"]]

    manifest = {
        "created_at": started.isoformat(timespec="seconds"),
        "elapsed_seconds": round((_now() - started).total_seconds(), 1),
        "backend": "sqlite",
        "warehouse": {
            "source": str(source),
            "backup": str(target),
            "source_bytes": source.stat().st_size,
            "backup_bytes": target.stat().st_size,
            **{k: v for k, v in verified.items() if k != "counts"},
            "counts": verified["counts"],
        },
        # Recorded, not copied. See the module docstring.
        "raw_archive": {"path": str(settings.raw_archive_dir), **archive},
        "sqlite_version": sqlite3.sqlite_version,
    }
    companion(target, ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    if listing:
        companion(target, ".archive.txt").write_text(
            "\n".join(listing) + "\n", encoding="utf-8")

    log.info("backup.complete", target=str(target),
              bytes=manifest["warehouse"]["backup_bytes"],
              rows=verified["rows"], archive_files=archive["files"])
    return manifest


def missing_from_archive(manifest_path: Path, raw_dir: Path | None = None) -> list[str]:
    """Files a manifest lists that are no longer on disk.

    The question a manifest exists to answer. Reads the companion listing —
    the manifest itself carries totals, and the listing carries the names.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    listing_path = manifest_path.with_suffix("").with_suffix(".archive.txt")
    if not listing_path.is_file():
        raise BackupError(f"no archive listing beside {manifest_path}.")

    root = raw_dir or Path(manifest["raw_archive"]["path"])
    return [name for name in listing_path.read_text(encoding="utf-8").splitlines()
             if name and not (root / name).is_file()]


def restore(backup: Path, settings: Settings | None = None,
             force: bool = False) -> dict:
    """Put a backup back, keeping whatever it replaces.

    The existing warehouse is moved aside rather than deleted, because the
    common reason to restore is "something went wrong" and the second-commonest
    is "I restored the wrong one". WAL and shm sidecars beside the target are
    removed: they belong to the database being replaced, and a stale WAL next
    to a restored file is how a good backup becomes a corrupt warehouse.
    """
    settings = settings or get_settings()
    if not settings.database_url:
        raise BackupError(
            "PostgreSQL restore path requires DATABASE_URL; no warehouse "
            "was configured.")
    if not backup.is_file():
        raise BackupError(f"no backup file at {backup}.")

    # Which backend restores this is the configured one, not the file's — but
    # a file taken from the other backend cannot be read by it, and finding
    # that out from a parse error is worse than being told. The check is on
    # the name because that is what the operator typed and what they can
    # correct.
    wanted = (POSTGRES_SUFFIX if settings.database_backend == "postgres"
               else SQLITE_SUFFIX)
    if not backup.name.endswith(wanted):
        raise BackupError(
            f"{backup.name} is not a {settings.database_backend} backup "
            f"(those end in {wanted}). DATABASE_URL decides which warehouse "
            "is being restored into; unset it to restore a SQLite file.")

    if settings.database_backend == "postgres":
        from pipeline import pgbackup

        return pgbackup.restore(backup, settings, force=force)

    # A file damaged badly enough does not report a failed check -- it refuses
    # to be read as a database at all, and sqlite3 raises. Both are the same
    # answer to the only question being asked here, so both are refusals
    # rather than one refusal and one traceback.
    try:
        with closing(sqlite3.connect(f"file:{backup}?mode=ro", uri=True)) as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise BackupError(
                    f"{backup} fails its own integrity check ({integrity}); "
                    "it will not be restored.")
            counts = table_counts(conn)
    except sqlite3.DatabaseError as exc:
        raise BackupError(
            f"{backup} cannot be read as a database ({exc}); "
            "it will not be restored.") from exc

    target = settings.database_path
    superseded = None
    if target.exists():
        if not force:
            # Say how much is at stake rather than just refusing. Read on its
            # own read-only connection: this path must not disturb, or hold a
            # handle on, the warehouse it is declining to replace.
            try:
                with closing(sqlite3.connect(f"file:{target}?mode=ro", uri=True)) as existing:
                    at_stake = f"holding {sum(table_counts(existing).values()):,} rows"
            except sqlite3.DatabaseError:
                at_stake = "that cannot be read"
            raise BackupError(
                f"{target} already exists. Restoring would replace a warehouse "
                f"{at_stake}. Re-run with force to move it aside and continue.")
        # Fold the WAL into the database file *before* moving it aside.
        #
        # The sidecars are named after the file, not carried with it: rename
        # `warehouse.db` and `warehouse.db-wal` stays behind, about to be
        # deleted below. Anything committed but not yet checkpointed would go
        # with it, so the file kept "so nothing is thrown away" could be
        # missing the most recent thing it was kept for.
        #
        # Windows hid this. It refuses to rename a file another connection has
        # open, so the failure needed a POSIX filesystem and CI to surface it.
        try:
            with closing(sqlite3.connect(target)) as live:
                live.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.DatabaseError as exc:
            # A warehouse too damaged to checkpoint is exactly one worth
            # keeping a copy of, so this is a note rather than a refusal.
            log.warning("backup.checkpoint_failed", target=str(target), error=str(exc))

        superseded = target.with_name(f"{target.name}.superseded-{_stamp()}")
        target.rename(superseded)

    for sidecar in (target.with_name(target.name + "-wal"),
                     target.with_name(target.name + "-shm")):
        sidecar.unlink(missing_ok=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    log.info("backup.restored", backup=str(backup), target=str(target),
              superseded=str(superseded) if superseded else None)
    return {"restored": str(target), "from": str(backup),
             "rows": sum(counts.values()), "tables": len(counts),
             "superseded": str(superseded) if superseded else None}


def prune(settings: Settings | None = None, keep: int = 7,
           dry_run: bool = False) -> dict:
    """Delete old automatic backups, keeping the newest `keep` of them.

    **A labelled backup is never deleted.** `--label before-m04-rerun` is
    somebody saying "I am about to do something and want this moment back", and
    a retention rule that discards it is worse than no retention rule. Only the
    unlabelled, timestamp-only ones — the sort a schedule produces — are
    candidates.

    Each backup's manifest and archive listing go with it: they describe that
    file and are meaningless without it.
    """
    settings = settings or get_settings()
    if keep < 1:
        raise BackupError("keep must be at least 1 — pruning to nothing is "
                           "deleting every backup, which this will not do.")

    automatic, labelled = [], []
    for entry in listing(settings):
        path = Path(entry["path"])
        # warehouse-20260813T131334Z.db is automatic;
        # warehouse-20260813T131334Z-before-m04-rerun.db is not.
        #
        # Read off the name with the suffix stripped by `companion`, not off
        # `Path.stem`: for `warehouse-….sql.gz` that leaves `warehouse-….sql`,
        # which matches nothing here, and every PostgreSQL snapshot would have
        # been filed as labelled and never pruned — a retention rule that
        # quietly retains everything.
        stem = companion(path, "").name
        (automatic if re.fullmatch(r"warehouse-\d{8}T\d{6}Z(-\d+)?", stem)
          else labelled).append(path)

    doomed = automatic[keep:]          # listing() is newest first
    removed = []
    for path in doomed:
        companions = [path, companion(path, ".manifest.json"),
                       companion(path, ".archive.txt")]
        if not dry_run:
            for beside in companions:
                beside.unlink(missing_ok=True)
        removed.append(path.name)

    if removed and not dry_run:
        log.info("backup.pruned", removed=len(removed), kept=len(automatic) - len(doomed),
                  labelled_kept=len(labelled))
    return {"removed": removed, "kept": len(automatic) - len(doomed),
             "labelled_kept": len(labelled), "dry_run": dry_run}


def listing(settings: Settings | None = None) -> list[dict]:
    """Backups on disk, newest first, with what each one holds.

    Ordered by modification time, not by filename. The names look sortable and
    are not: the uniquifier for two backups inside one second appends `-2`,
    and `warehouse-…Z.db` sorts *after* `warehouse-…Z-5.db` because `.` is
    above `-`. So a filename sort put the oldest of a same-second run first
    and called it newest — which `prune()` would then have kept while deleting
    the four that came after it.
    """
    settings = settings or get_settings()
    if not settings.backup_dir.is_dir():
        return []

    # Both backends' backups, in one list. An operator who has cut over to
    # PostgreSQL still has the SQLite snapshots from before it, and those are
    # the ones that matter most on the day the cutover is being reconsidered —
    # a listing that hid them because of the configured backend would hide
    # them exactly then.
    found = [path for pattern in (f"warehouse-*{suffix}"
                                   for suffix in BACKUP_SUFFIXES)
              for path in settings.backup_dir.glob(pattern)]

    out = []
    for path in sorted(found, key=lambda p: (p.stat().st_mtime_ns, p.name),
                        reverse=True):
        entry = {"path": str(path), "name": path.name,
                  "bytes": path.stat().st_size,
                  "backend": ("postgres" if path.name.endswith(POSTGRES_SUFFIX)
                               else "sqlite"),
                  "modified": datetime.fromtimestamp(
                      path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
        manifest_path = companion(path, ".manifest.json")
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                entry["rows"] = manifest["warehouse"].get("rows")
                entry["created_at"] = manifest.get("created_at")
                entry["archive_files"] = manifest.get("raw_archive", {}).get("files")
            except (ValueError, KeyError):
                entry["manifest"] = "unreadable"
        out.append(entry)
    return out
