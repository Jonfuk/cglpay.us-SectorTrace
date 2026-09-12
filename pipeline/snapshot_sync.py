"""Additive transfers of verified warehouse snapshot files to and from S3."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from pipeline import backup
from pipeline.config import Settings

SNAPSHOT_PREFIX = "warehouse-"
SNAPSHOT_SUFFIXES = (".sql.gz", ".manifest.json", ".archive.txt")


class SnapshotSyncError(RuntimeError):
    """A snapshot transfer that cannot prove what it copied."""


Progress = Callable[[int, int], None]


def _client(settings: Settings):
    values = (settings.backup_s3_bucket, settings.backup_s3_endpoint,
              settings.backup_s3_region, settings.backup_s3_url_style,
              settings.backup_s3_access_key, settings.backup_s3_secret)
    if not all(values):
        raise SnapshotSyncError(
            "warehouse snapshot sync needs the complete BACKUP_S3_* configuration.")
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise SnapshotSyncError(
            "warehouse snapshot sync requires `uv sync --extra storage`.") from exc
    return boto3.client(
        "s3", region_name=settings.backup_s3_region,
        endpoint_url=settings.backup_s3_endpoint,
        config=boto3.session.Config(
            s3={"addressing_style": settings.backup_s3_url_style}),
        aws_access_key_id=settings.backup_s3_access_key,
        aws_secret_access_key=settings.backup_s3_secret,
    )


def _local_files(settings: Settings) -> dict[str, Path]:
    root = Path(settings.backup_dir)
    if not root.is_dir():
        return {}
    return {
        path.name: path for path in root.iterdir()
        if path.is_file() and path.name.startswith(SNAPSHOT_PREFIX)
        and path.name.endswith(SNAPSHOT_SUFFIXES)
    }


def _remote_files(settings: Settings, client) -> dict[str, dict]:
    prefix = settings.backup_s3_prefix.strip("/")
    prefix = f"{prefix}/" if prefix else ""
    result: dict[str, dict] = {}
    token = None
    while True:
        kwargs = {"Bucket": settings.backup_s3_bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            name = item["Key"][len(prefix):]
            if name.startswith(SNAPSHOT_PREFIX) and name.endswith(SNAPSHOT_SUFFIXES):
                result[name] = item
        if not page.get("IsTruncated"):
            return result
        token = page.get("NextContinuationToken")
        if not token:
            raise SnapshotSyncError(
                "the snapshot listing was truncated without a continuation token")


def _key(settings: Settings, name: str) -> str:
    prefix = settings.backup_s3_prefix.strip("/")
    return f"{prefix}/{name}" if prefix else name


def plan_local_to_s3(settings: Settings) -> dict:
    """Report local verified snapshot files absent from the S3 destination."""
    client = _client(settings)
    local = _local_files(settings)
    remote = _remote_files(settings, client)
    missing = sorted(set(local) - set(remote))
    return {"direction": "local-to-s3", "local": len(local), "remote": len(remote),
            "objects": len(missing), "bytes": sum(local[name].stat().st_size for name in missing)}


def local_to_s3(settings: Settings, *, workers: int = 4,
                on_progress: Progress | None = None) -> dict:
    """Upload snapshot and companion files missing from S3; never delete."""
    client = _client(settings)
    local = _local_files(settings)
    remote = _remote_files(settings, client)
    missing = sorted(set(local) - set(remote))

    def upload(name: str) -> None:
        path = local[name]
        client.upload_file(str(path), settings.backup_s3_bucket, _key(settings, name))
        remote_size = int(client.head_object(
            Bucket=settings.backup_s3_bucket, Key=_key(settings, name))["ContentLength"])
        if remote_size != path.stat().st_size:
            raise SnapshotSyncError(f"{name} uploaded with the wrong size; keeping local only")

    copied = 0
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="snapshot-upload") as pool:
        for _ in pool.map(upload, missing):
            copied += 1
            if on_progress:
                on_progress(copied, len(missing))
    return {"direction": "local-to-s3", "objects": len(missing), "bytes": sum(
        local[name].stat().st_size for name in missing), "copied": copied}


def plan_s3_to_local(settings: Settings) -> dict:
    """Report S3 snapshot files absent from the local backup directory."""
    client = _client(settings)
    local = _local_files(settings)
    remote = _remote_files(settings, client)
    missing = sorted(set(remote) - set(local))
    return {"direction": "s3-to-local", "local": len(local), "remote": len(remote),
            "objects": len(missing), "bytes": sum(remote[name].get("Size", 0)
                                                     for name in missing)}


def s3_to_local(settings: Settings, *, workers: int = 4,
                on_progress: Progress | None = None) -> dict:
    """Download snapshot and companion files missing locally; never delete."""
    client = _client(settings)
    local_root = Path(settings.backup_dir)
    local_root.mkdir(parents=True, exist_ok=True)
    local = _local_files(settings)
    remote = _remote_files(settings, client)
    missing = sorted(set(remote) - set(local))

    def download(name: str) -> None:
        destination = local_root / name
        partial = destination.with_name(destination.name + ".partial")
        with partial.open("wb") as handle:
            client.download_fileobj(settings.backup_s3_bucket, _key(settings, name), handle)
        expected = int(remote[name].get("Size", 0))
        if expected and partial.stat().st_size != expected:
            partial.unlink(missing_ok=True)
            raise SnapshotSyncError(
                f"{name} downloaded with the wrong size; not installing it")
        if name.endswith(".sql.gz"):
            try:
                backup.verify_archive(partial)
            except backup.BackupError as exc:
                partial.unlink(missing_ok=True)
                raise SnapshotSyncError(
                    f"{name} failed PostgreSQL snapshot verification: {exc}") from exc
        os.replace(partial, destination)

    copied = 0
    with ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="snapshot-download") as pool:
        for _ in pool.map(download, missing):
            copied += 1
            if on_progress:
                on_progress(copied, len(missing))
    return {"direction": "s3-to-local", "objects": len(missing), "bytes": sum(
        remote[name].get("Size", 0) for name in missing), "copied": copied}
