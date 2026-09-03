"""The PostgreSQL warehouse backup contract.

The warehouse is PostgreSQL-only. The implementation lives in
``pipeline.pgbackup`` because the snapshot format uses PostgreSQL ``COPY``;
this module keeps the stable operator-facing facade and raw-archive helpers.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.config import Settings, get_settings

log = structlog.get_logger()

POSTGRES_SUFFIX = ".sql.gz"
BACKUP_SUFFIXES = (POSTGRES_SUFFIX,)


class BackupError(RuntimeError):
    """A backup that cannot be trusted, or a restore that would lose data."""


def companion(backup: Path, suffix: str) -> Path:
    """Return the manifest/listing path beside a PostgreSQL snapshot."""
    name = backup.name
    if name.endswith(POSTGRES_SUFFIX):
        name = name[:-len(POSTGRES_SUFFIX)]
    else:
        name = backup.stem
    return backup.with_name(name + suffix)


def archive_inventory(raw_dir: Path) -> tuple[dict, list[str]]:
    """Inventory archived source bytes without copying or hashing them again."""
    by_source: dict[str, dict[str, int]] = {}
    listing: list[str] = []
    if not raw_dir.is_dir():
        return {"sources": {}, "files": 0, "bytes": 0, "present": False}, listing

    for path in sorted(raw_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(raw_dir).as_posix()
        source = relative.split("/", 1)[0] if "/" in relative else "(root)"
        entry = by_source.setdefault(source, {"files": 0, "bytes": 0})
        entry["files"] += 1
        entry["bytes"] += path.stat().st_size
        listing.append(relative)

    return ({"sources": by_source,
             "files": sum(e["files"] for e in by_source.values()),
             "bytes": sum(e["bytes"] for e in by_source.values()),
             "present": True}, listing)


def create(settings: Settings | None = None, destination: Path | None = None,
           label: str | None = None) -> dict:
    """Create and verify a PostgreSQL snapshot."""
    settings = settings or get_settings()
    if not settings.database_url:
        raise BackupError(
            "PostgreSQL backup path requires DATABASE_URL; no warehouse "
            "was configured.")
    from pipeline import pgbackup

    return pgbackup.dump(settings, destination=destination, label=label)


def missing_from_archive(manifest_path: Path, raw_dir: Path | None = None) -> list[str]:
    """Return archive files listed by a manifest that are no longer present."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest_path.with_name(
        manifest_path.name.removesuffix(".manifest.json") + POSTGRES_SUFFIX)
    listing_path = companion(snapshot, ".archive.txt")
    if not listing_path.is_file():
        raise BackupError(f"no archive listing beside {manifest_path}.")

    root = raw_dir or Path(manifest["raw_archive"]["path"])
    return [name for name in listing_path.read_text(encoding="utf-8").splitlines()
            if name and not (root / name).is_file()]


def restore(backup: Path, settings: Settings | None = None,
            force: bool = False) -> dict:
    """Restore a PostgreSQL snapshot through the verified restore path."""
    settings = settings or get_settings()
    if not settings.database_url:
        raise BackupError(
            "PostgreSQL restore path requires DATABASE_URL; no warehouse "
            "was configured.")
    if not backup.is_file():
        raise BackupError(f"no backup file at {backup}.")
    if not backup.name.endswith(POSTGRES_SUFFIX):
        raise BackupError(
            f"{backup.name} is not a PostgreSQL backup (those end in "
            f"{POSTGRES_SUFFIX}).")

    from pipeline import pgbackup

    return pgbackup.restore(backup, settings, force=force)


def prune(settings: Settings | None = None, keep: int = 7,
          dry_run: bool = False) -> dict:
    """Delete old automatic snapshots while retaining labelled snapshots."""
    settings = settings or get_settings()
    if keep < 1:
        raise BackupError("keep must be at least 1 — pruning to nothing is "
                          "deleting every backup, which this will not do.")

    automatic, labelled = [], []
    for entry in listing(settings):
        path = Path(entry["path"])
        stem = companion(path, "").name
        (automatic if re.fullmatch(r"warehouse-\d{8}T\d{6}Z(-\d+)?", stem)
          else labelled).append(path)

    doomed = automatic[keep:]
    removed = []
    for path in doomed:
        companions = [path, companion(path, ".manifest.json"),
                      companion(path, ".archive.txt")]
        if not dry_run:
            for beside in companions:
                beside.unlink(missing_ok=True)
        removed.append(path.name)

    if removed and not dry_run:
        log.info("backup.pruned", removed=len(removed),
                  kept=len(automatic) - len(doomed), labelled_kept=len(labelled))
    return {"removed": removed, "kept": len(automatic) - len(doomed),
            "labelled_kept": len(labelled), "dry_run": dry_run}


def listing(settings: Settings | None = None) -> list[dict]:
    """List PostgreSQL snapshots newest first, including manifest metadata."""
    settings = settings or get_settings()
    if not settings.backup_dir.is_dir():
        return []

    found = list(settings.backup_dir.glob(f"warehouse-*{POSTGRES_SUFFIX}"))
    out = []
    for path in sorted(found, key=lambda p: (p.stat().st_mtime_ns, p.name),
                       reverse=True):
        entry = {"path": str(path), "name": path.name,
                 "bytes": path.stat().st_size, "backend": "postgres",
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
