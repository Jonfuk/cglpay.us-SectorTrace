"""Explicit, additive transfers between the local raw archive and S3.

The raw archive is content-addressed, so a sync has no merge semantics: an
object either exists at its hash or it does not. Both directions are additive
and use the archive backend's own hash verification. Deletion and retention
stay separate operator decisions.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from mimetypes import guess_type
from pathlib import Path
from typing import Callable

from pipeline.archive import FilesystemArchive, get_archive
from pipeline.config import Settings


class ArchiveSyncError(RuntimeError):
    """An archive transfer that cannot prove what it copied."""


Progress = Callable[[int, int], None]


def _require_s3(settings: Settings) -> None:
    if settings.archive_backend != "s3":
        raise ArchiveSyncError(
            "raw archive sync needs ARCHIVE_S3_* configured; the active archive "
            "backend is local filesystem storage.")


def _parts(row: dict) -> tuple[str, str, str]:
    filename = row["key"].split("/")[-1]
    source = row["key"].split("/")[2]
    sha = filename.split(".", 1)[0]
    return source, sha, filename


def plan_local_to_s3(settings: Settings) -> dict:
    """Inventory local objects and report which are absent or changed in S3."""
    _require_s3(settings)
    local = FilesystemArchive(Path(settings.raw_archive_dir))
    local_report = local.verify()
    if not local_report["ok"]:
        raise ArchiveSyncError(
            f"local archive is not valid: {local_report['failures'][:5]}")
    inventory = local.inventory(True)
    remote = get_archive(settings)
    remote_keys = {row["key"] for row in remote.inventory()["objects"]}
    candidates = [row for row in inventory["objects"] if row["key"] not in remote_keys]
    return {
        "direction": "local-to-s3", "local": inventory, "remote_keys": len(remote_keys),
        "objects": len(candidates), "bytes": sum(row["bytes"] for row in candidates),
    }


def local_to_s3(settings: Settings, *, workers: int = 8,
                on_progress: Progress | None = None) -> dict:
    """Upload local objects missing from S3; never delete or overwrite an object."""
    plan = plan_local_to_s3(settings)
    if not plan["objects"]:
        return {**plan, "copied": 0, "remote": plan["remote_keys"]}

    local = FilesystemArchive(Path(settings.raw_archive_dir))
    remote = get_archive(settings)
    inventory = plan["local"]
    remote_keys = {row["key"] for row in remote.inventory()["objects"]}
    candidates = [row for row in inventory["objects"] if row["key"] not in remote_keys]

    def upload(row: dict) -> bool:
        source, sha, filename = _parts(row)
        remote.put(source, sha, guess_type(filename)[0], local.read(row["key"]))
        return True

    copied = 0
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="archive-upload") as pool:
        for copied_one in pool.map(upload, candidates):
            copied += int(copied_one)
            if on_progress:
                on_progress(copied, len(candidates))
    return {**plan, "copied": copied, "remote": plan["remote_keys"] + copied}


def plan_s3_to_local(settings: Settings) -> dict:
    """Inventory S3 objects and report which are absent from local disk."""
    _require_s3(settings)
    remote = get_archive(settings)
    local = FilesystemArchive(Path(settings.raw_archive_dir))
    inventory = remote.inventory()
    missing = [row for row in inventory["objects"] if local.lookup(*_parts(row)[:2]) is None]
    return {
        "direction": "s3-to-local", "remote": inventory,
        "objects": len(missing), "bytes": sum(row["bytes"] for row in missing),
    }


def s3_to_local(settings: Settings, *, workers: int = 8,
                on_progress: Progress | None = None) -> dict:
    """Download S3 objects missing locally; never delete local files."""
    plan = plan_s3_to_local(settings)
    if not plan["objects"]:
        return {**plan, "copied": 0, "local": FilesystemArchive(
            Path(settings.raw_archive_dir)).inventory()}

    remote = get_archive(settings)
    local = FilesystemArchive(Path(settings.raw_archive_dir))
    candidates = [row for row in plan["remote"]["objects"]
                  if local.lookup(*_parts(row)[:2]) is None]

    def download(row: dict) -> bool:
        source, sha, filename = _parts(row)
        local.put(source, sha, guess_type(filename)[0], remote.read(row["key"]))
        return True

    copied = 0
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="archive-download") as pool:
        for copied_one in pool.map(download, candidates):
            copied += int(copied_one)
            if on_progress:
                on_progress(copied, len(candidates))
    return {**plan, "copied": copied, "local": local.inventory()}
