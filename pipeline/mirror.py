"""Keeping a mirror in step with the deployment it copies.

A mirror is a second deployment that collects nothing. Its warehouse arrives
whole from the deployment it copies, and its raw archive is pulled out of that
deployment's S3 bucket onto local disk. `deploy/ansible-mirror/` provisions
one; this is the part of it that makes decisions.

Those decisions used to live in the deployment's shell script, and the reason
they are here instead is the reason most things in this project are testable:
choosing *which* snapshot is current, working out how old it is, and deciding
whether it has already been restored are exactly the steps that are subtly
wrong for a month before anyone notices. In bash they were unreachable by the
offline suite. Here they are fixture-backed, and the shell script is left with
what only it can do — stopping a container, taking a lock, starting it again.

What this is not:

  * **Not a merge.** `pipeline/pgmirror.py` says why there is no safe meaning
    for two independently changed evidence warehouses to reconcile. A sync
    replaces this box's warehouse; anything written here between syncs is
    discarded, and that is the deal a mirror makes.
  * **Not a second backup.** The snapshots it reads belong to the source and
    are already verified there. This copies one in; it never writes to the
    source's bucket, and the credentials it is given should not let it.
  * **Not a collector.** Nothing here fetches from a source of evidence. The
    politeness rules (settled decision 5) are not relaxed on a mirror — they
    simply never come up, because every row arrived from a warehouse that had
    already asked.

The staleness check is the part worth reading twice. A source whose backup
timer has quietly stopped does not produce an error here: the mirror finds
the same snapshot it restored last week, recognises it, and reports "nothing
to do" — which is precisely what being up to date also looks like. Silence is
not success. `plan()` therefore reports the newest snapshot's age whether or
not there is anything to restore, and `--fail-if-stale` turns that into a
non-zero exit, which is what makes the unit fail, which is what makes the
alert fire.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline.config import Settings, get_settings

log = structlog.get_logger()

# Automatic snapshots only. `pipeline/backup.py` names them
# `warehouse-<stamp>[-<n>].sql.gz`, where the `-<n>` is what it appends when
# two land in the same second; a *labelled* one
# (`warehouse-<stamp>-before-m04-rerun.sql.gz`) is a moment somebody
# deliberately kept on the source, not necessarily the state the source is in
# now. A mirror wants the latter, so labelled snapshots are skipped here and
# restored by hand if anyone wants one.
SNAPSHOT_NAME = re.compile(r"^warehouse-(\d{8}T\d{6}Z)(?:-(\d+))?\.sql\.gz$")
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"

STATE_FILE = "state.json"


class MirrorError(RuntimeError):
    """A mirror operation that would leave this box in an unknown state."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_mirror(settings: Settings, what: str) -> None:
    """Refuse on a box that has not said it is a mirror.

    MIRROR_ENABLED is not a convenience flag. Every command that reads it
    behaves differently for having it set — this one replaces the warehouse
    without asking twice — and "a variable happened to be set" is not a
    reason for a collecting deployment to do that.
    """
    if not settings.mirror_enabled:
        raise MirrorError(
            f"{what} only runs on a mirror, and MIRROR_ENABLED is not set. "
            "If this box really is one, set it in .env; if it is the "
            "deployment being mirrored, you are on the wrong box.")


def snapshot_stamp(name: str) -> datetime | None:
    """When the snapshot named `name` was taken, or None if it is not one."""
    match = SNAPSHOT_NAME.fullmatch(name)
    if not match:
        return None
    return datetime.strptime(match.group(1), STAMP_FORMAT).replace(tzinfo=timezone.utc)


def manifest_name(snapshot: str) -> str:
    """The manifest beside a snapshot. See `backup.companion` for the shape."""
    return snapshot[: -len(".sql.gz")] + ".manifest.json"


def _client(settings: Settings, client=None):
    """A client for the SOURCE's snapshot bucket.

    Deliberately not `archive.S3Archive`'s: that one is built from the
    ARCHIVE_S3_* group and addresses content by hash under `data/raw/`, and
    this bucket holds neither of those things. Same injection point though —
    pass `client` and the whole module is exercised offline.
    """
    if client is not None:
        return client
    if not settings.mirror_backup_s3_bucket:
        raise MirrorError(
            "no snapshot bucket configured. Set the MIRROR_BACKUP_S3_* group "
            "(bucket, endpoint, region, url style, access key, secret) — "
            "read-only credentials are enough and are what to use.")
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - depends on the extra
        raise MirrorError("reading the snapshot bucket needs `uv sync --extra storage`") from exc
    return boto3.client(
        "s3",
        region_name=settings.mirror_backup_s3_region,
        endpoint_url=settings.mirror_backup_s3_endpoint,
        config=boto3.session.Config(
            s3={"addressing_style": settings.mirror_backup_s3_url_style}),
        aws_access_key_id=settings.mirror_backup_s3_access_key,
        aws_secret_access_key=settings.mirror_backup_s3_secret,
    )


def available(settings: Settings, client=None, now: datetime | None = None) -> list[dict]:
    """Every automatic snapshot in the source's bucket, newest first.

    Sorted on the timestamp parsed out of the name rather than on the name
    itself or on S3's LastModified. The name is what the source's `pipeline
    backup` stamped when it *took* the snapshot; LastModified is when the
    offsite copy happened to upload it, which is a different question and
    reorders on a re-upload.
    """
    now = now or _now()
    prefix = settings.mirror_backup_s3_prefix.strip("/")
    prefix = f"{prefix}/" if prefix else ""
    rows: list[dict] = []
    token = None
    while True:
        kwargs = {"Bucket": settings.mirror_backup_s3_bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = _client(settings, client).list_objects_v2(**kwargs)
        for item in page.get("Contents", []):
            name = item["Key"].rsplit("/", 1)[-1]
            taken = snapshot_stamp(name)
            if taken is None:
                continue
            rows.append({
                "name": name,
                "key": item["Key"],
                "bytes": int(item.get("Size", 0)),
                "taken_at": taken.isoformat(timespec="seconds"),
                "age_hours": round((now - taken).total_seconds() / 3600, 1),
            })
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
        if not token:
            raise MirrorError("the snapshot listing was truncated without a continuation token")
    return sorted(rows, key=lambda r: r["taken_at"], reverse=True)


# --- What this box currently holds -------------------------------------------

def state(settings: Settings) -> dict:
    """What the last sync left behind. Never raises on a missing or bad file.

    A status command that cannot run because the file it reports on is
    corrupt is a status command that fails exactly when it is needed. A
    damaged state file is reported as damaged and the sync carries on: it is
    a record of what happened, not the thing that happened.
    """
    path = Path(settings.mirror_state_dir) / STATE_FILE
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        log.warning("mirror.state_unreadable", path=str(path), error=str(exc))
        return {"unreadable": str(exc)}
    return loaded if isinstance(loaded, dict) else {"unreadable": "not an object"}


def record(settings: Settings, **fields) -> dict:
    """Merge `fields` into the state file, atomically.

    Written to a temporary file and renamed over the original. A sync that is
    interrupted while writing this must not leave a half-written file behind:
    the next run would read it, fail to parse it, and lose track of which
    snapshot is in place — which would make it restore one it already had.
    """
    directory = Path(settings.mirror_state_dir)
    directory.mkdir(parents=True, exist_ok=True)
    merged = {k: v for k, v in state(settings).items() if k != "unreadable"}
    merged.update(fields)
    path = directory / STATE_FILE
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return merged


# --- Deciding what to do ------------------------------------------------------

def plan(settings: Settings, *, client=None, force: bool = False,
         now: datetime | None = None) -> dict:
    """What a sync would do, without doing any of it.

    This is both the dry run and the first half of `pull`, which is why it is
    one function: a dry run that answers a different question from the real
    one is a dry run nobody should trust.
    """
    _require_mirror(settings, "mirror plan")
    now = now or _now()
    snapshots = available(settings, client=client, now=now)
    holding = state(settings).get("snapshot")

    if not snapshots:
        return {
            "action": "none-available",
            "snapshot": None, "holding": holding, "stale": True,
            "reason": (
                f"no automatic warehouse snapshot under "
                f"s3://{settings.mirror_backup_s3_bucket}/"
                f"{settings.mirror_backup_s3_prefix}/. Has the source's backup "
                "timer run, and is backup_offsite_enabled set there?"),
            "checked_at": now.isoformat(timespec="seconds"),
        }

    newest = snapshots[0]
    stale = newest["age_hours"] > settings.mirror_max_snapshot_age_hours
    if newest["name"] == holding and not force:
        action, reason = "up-to-date", (
            f"{newest['name']} is already in place; nothing newer in the bucket")
    else:
        action = "restore"
        reason = (f"{newest['name']} was taken {newest['age_hours']}h ago; "
                  f"this box holds {holding or 'nothing'}")
    if stale:
        # Said whether or not there is anything to restore, and said the same
        # way both times. The failure this catches is a source that stopped
        # producing snapshots, and in that case there is nothing to restore —
        # so a staleness note that only appeared alongside work would never
        # appear at all.
        reason += (f". The newest snapshot in the bucket is "
                   f"{newest['age_hours']}h old, past the "
                   f"{settings.mirror_max_snapshot_age_hours}h limit — the "
                   "source's backup timer may have stopped")
    return {
        "action": action, "snapshot": newest, "holding": holding,
        "stale": stale, "reason": reason,
        "available": len(snapshots),
        "checked_at": now.isoformat(timespec="seconds"),
    }


def _download(settings: Settings, snapshot: dict, client=None) -> Path:
    directory = Path(settings.mirror_inbox_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / snapshot["name"]
    partial = destination.with_name(destination.name + ".partial")
    handle = _client(settings, client)
    with partial.open("wb") as fh:
        handle.download_fileobj(settings.mirror_backup_s3_bucket, snapshot["key"], fh)
    size = partial.stat().st_size
    if snapshot["bytes"] and size != snapshot["bytes"]:
        partial.unlink(missing_ok=True)
        raise MirrorError(
            f"{snapshot['name']} downloaded as {size:,} bytes; the bucket "
            f"lists it as {snapshot['bytes']:,}. Not restoring a truncated "
            "snapshot.")
    # Renamed only once it is whole, so an interrupted download cannot be
    # picked up as a snapshot by anything that lists this directory.
    os.replace(partial, destination)

    # Best effort, and not on the restore path: the snapshot carries its own
    # checksums and `restore` refuses one that fails them. The manifest is
    # what says how many rows and which migrations, and an operator asking
    # "what did last night bring" should not have to go back to the bucket.
    manifest = manifest_name(snapshot["name"])
    prefix = snapshot["key"][: -len(snapshot["name"])]
    try:
        handle.download_file(settings.mirror_backup_s3_bucket, prefix + manifest,
                             str(directory / manifest))
    except Exception as exc:  # noqa: BLE001 - any failure here is a note
        log.info("mirror.manifest_absent", snapshot=snapshot["name"], error=str(exc))
    return destination


def _prune_inbox(settings: Settings, keep: str) -> list[str]:
    """Everything in the inbox but the snapshot now in place.

    The older ones are still in the source's bucket, which is where they
    belong. Keeping them here is how a mirror fills its disk with copies of
    a file it can fetch again.
    """
    directory = Path(settings.mirror_inbox_dir)
    if not directory.is_dir():
        return []
    keepers = {keep, manifest_name(keep)}
    removed = []
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.name.startswith("warehouse-") and path.name not in keepers:
            path.unlink()
            removed.append(path.name)
    return removed


SUPERSEDED_LABEL = "superseded-by-restore"


def prune_superseded(settings: Settings, keep: int) -> list[str]:
    """Delete all but the newest `keep` snapshots that a restore set aside.

    A deliberate departure from `backup.prune`, which never deletes a
    labelled backup automatically — and is right not to, because on a
    collecting deployment the second-commonest reason to restore is having
    restored the wrong thing, and the labelled copy is the way back.

    On a mirror that argument is weaker in one specific way and stronger in
    none: what a restore replaces here is itself a copy of the source, and
    the source still has the original. Keeping every night's is how a mirror
    fills its disk with copies of a warehouse nobody wrote to. `keep` of 0
    disables this and keeps them all.

    Only files carrying this exact label are considered. A snapshot somebody
    labelled by hand on this box is theirs, and is not swept up by a
    retention rule they did not ask for.
    """
    if keep < 0:
        raise MirrorError("mirror_superseded_keep cannot be negative")
    directory = Path(settings.backup_dir)
    if keep == 0 or not directory.is_dir():
        return []
    found = sorted(directory.glob(f"warehouse-*-{SUPERSEDED_LABEL}.sql.gz"),
                   key=lambda p: p.name, reverse=True)
    removed = []
    for path in found[keep:]:
        path.unlink()
        # The manifest is named for the backup, not suffixed onto it — see
        # backup.companion. Leaving it behind would accumulate the very
        # clutter this removes.
        manifest = path.with_name(manifest_name(path.name))
        manifest.unlink(missing_ok=True)
        removed.append(path.name)
    return removed


def pull(settings: Settings | None = None, *, client=None, force: bool = False,
         dry_run: bool = False, superseded_keep: int = 2,
         now: datetime | None = None, on_step=None) -> dict:
    """Bring this box's warehouse up to the source's newest snapshot.

    The restore is `pipeline.backup.restore`, unchanged and for good reason:
    it refuses a snapshot that fails its own verification, it re-checks every
    table's row count against the archive and rolls back on any disagreement,
    and it sets aside what it replaces. A mirror-specific restore path would
    be a second implementation of the careful one.
    """
    settings = settings or get_settings()
    _require_mirror(settings, "mirror pull")
    refuse_if_promoted(settings)
    now = now or _now()
    decision = plan(settings, client=client, force=force, now=now)

    def step(message: str) -> None:
        if on_step:
            on_step(message)

    if decision["action"] != "restore" or dry_run:
        if dry_run and decision["action"] == "restore":
            decision["would_download_bytes"] = decision["snapshot"]["bytes"]
        return decision

    snapshot = decision["snapshot"]
    step(f"downloading {snapshot['name']} ({snapshot['bytes']:,} bytes)")
    path = _download(settings, snapshot, client=client)

    step(f"restoring {snapshot['name']}")
    from pipeline import backup as backup_module

    try:
        # force is unavoidable after the first sync — the target holds the
        # previous one — and it is not a shortcut past any of the checks
        # above it. What it turns off is the refusal to overwrite, which on
        # this box is the whole job.
        result = backup_module.restore(path, settings, force=True)
    except backup_module.BackupError as exc:
        record(settings, last_failure=str(exc),
               last_failure_at=now.isoformat(timespec="seconds"))
        raise MirrorError(
            f"restoring {snapshot['name']} failed: {exc}. This box still "
            f"holds {decision['holding'] or 'nothing'} — the restore is one "
            "transaction, so a failed one changes nothing.") from None

    pruned = _prune_inbox(settings, snapshot["name"])
    # After the restore, not before: what it prunes is the copy this restore
    # just set aside plus its predecessors, and the newest of those is the
    # way back from the restore that has only this moment succeeded.
    superseded = prune_superseded(settings, superseded_keep)
    record(settings,
           snapshot=snapshot["name"],
           snapshot_taken_at=snapshot["taken_at"],
           snapshot_bytes=snapshot["bytes"],
           warehouse_rows=result["rows"],
           warehouse_tables=result["tables"],
           restored_at=now.isoformat(timespec="seconds"),
           last_failure=None, last_failure_at=None)
    log.info("mirror.restored", snapshot=snapshot["name"], rows=result["rows"],
             tables=result["tables"], source=settings.mirror_source_label)
    return {**decision, "action": "restored", "restore": result,
            "pruned": pruned, "pruned_superseded": superseded}


# --- Reporting ------------------------------------------------------------------

def data_as_of(current: dict) -> str | None:
    """When the evidence this box is serving was true on the source.

    Two modes answer this with different facts, and the difference matters:

      * snapshot mode holds a file, and the file is stamped with the moment
        the source took it. The data is as of then, however recently this box
        downloaded it — a mirror that syncs faithfully every night from a
        source that stopped taking backups a month ago is serving month-old
        evidence, and its own diligence must not be allowed to say otherwise.
      * tunnel mode copies the live warehouse and verifies the copy against
        it value by value, so the data is as of the moment that succeeded.
        There is no file and no stamp; the successful copy is the fact.

    Hence the fallback rather than two code paths: the snapshot's own stamp
    when there is one, and otherwise the last verified copy.
    """
    return current.get("snapshot_taken_at") or current.get("last_success_at")


def status(settings: Settings | None = None, *, client=None,
           check_bucket: bool = False, now: datetime | None = None) -> dict:
    """What this box holds, and how far behind that is.

    `check_bucket` is off by default so the common case — an operator asking
    what is in place — needs no credentials, no network and no wait.
    """
    settings = settings or get_settings()
    now = now or _now()
    current = state(settings)
    report = {
        "source": settings.mirror_source_label,
        "snapshot": current.get("snapshot"),
        "snapshot_taken_at": current.get("snapshot_taken_at"),
        "warehouse_rows": current.get("warehouse_rows"),
        "warehouse_tables": current.get("warehouse_tables"),
        "archive_objects": current.get("archive_objects"),
        "archive_bytes": current.get("archive_bytes"),
        "archive_checked_at": current.get("archive_checked_at"),
        "last_sync_started_at": current.get("last_sync_started_at"),
        "last_sync_finished_at": current.get("last_sync_finished_at"),
        "last_sync_status": current.get("last_sync_status"),
        "last_failure": current.get("last_failure"),
        "last_failure_at": current.get("last_failure_at"),
        "promoted": bool(current.get("promoted_at")),
        "promoted_at": current.get("promoted_at"),
        "checked_at": now.isoformat(timespec="seconds"),
    }
    as_of = data_as_of(current)
    report["data_as_of"] = as_of
    if as_of:
        age = (now - datetime.fromisoformat(as_of)).total_seconds() / 3600
        report["data_age_hours"] = round(age, 1)
        report["stale"] = age > settings.mirror_max_snapshot_age_hours
    else:
        # Never synced. Reported as stale rather than as unknown: a mirror
        # that has never worked and one that stopped working a month ago are
        # the same problem for anyone reading a figure off it.
        report["data_age_hours"] = None
        report["stale"] = True
    if check_bucket:
        snapshots = available(settings, client=client, now=now)
        report["bucket_newest"] = snapshots[0] if snapshots else None
        report["bucket_snapshots"] = len(snapshots)
    return report


def _metric(name: str, value, help_text: str, kind: str = "gauge") -> list[str]:
    if value is None:
        return []
    return [f"# HELP {name} {help_text}", f"# TYPE {name} {kind}",
            f"{name} {value}"]


def metrics(settings: Settings | None = None, *, now: datetime | None = None) -> str:
    """Prometheus textfile-collector output for the last sync.

    Deliberately reports what the state file recorded rather than measuring
    anything: counting the archive means walking millions of files, and a
    metrics scrape that does that is a metrics scrape that takes the box out.
    The numbers here were measured when the work was done.

    A mirror that has never synced emits the info metric and the success
    gauge and nothing else — `sectortrace_mirror_last_success_timestamp_seconds`
    being absent is what an alert should key on, since a mirror that has never
    worked and one that stopped working a month ago are the same problem.
    """
    settings = settings or get_settings()
    now = now or _now()
    current = state(settings)
    source = (settings.mirror_source_label or "unknown").replace('"', "'")
    snapshot = (current.get("snapshot") or "none").replace('"', "'")

    lines = [
        "# HELP sectortrace_mirror_info Which deployment this box mirrors, and what it holds.",
        "# TYPE sectortrace_mirror_info gauge",
        f'sectortrace_mirror_info{{source="{source}",snapshot="{snapshot}"}} 1',
    ]

    def epoch(value):
        return None if not value else int(datetime.fromisoformat(value).timestamp())

    lines += _metric("sectortrace_mirror_last_sync_timestamp_seconds",
                     epoch(current.get("last_sync_finished_at")),
                     "When the last sync finished, successfully or not.")
    lines += _metric("sectortrace_mirror_last_success_timestamp_seconds",
                     epoch(current.get("last_success_at")),
                     "When a sync last completed without failing a step.")
    # The one that matters. The others say when this box last did some work;
    # this says how old the evidence it is serving actually is, which is the
    # question anyone quoting a figure from a mirror is really asking.
    lines += _metric("sectortrace_mirror_snapshot_timestamp_seconds",
                     epoch(data_as_of(current)),
                     "When the evidence now being served was true on the source.")
    lines += _metric("sectortrace_mirror_last_sync_success",
                     1 if current.get("last_sync_status") == "ok" else 0,
                     "1 if the last sync finished cleanly, 0 otherwise.")
    lines += _metric("sectortrace_mirror_warehouse_rows",
                     current.get("warehouse_rows"),
                     "Rows restored into the warehouse by the last sync.")
    lines += _metric("sectortrace_mirror_archive_objects",
                     current.get("archive_objects"),
                     "Objects in this box's local copy of the source's raw archive.")
    lines += _metric("sectortrace_mirror_archive_bytes",
                     current.get("archive_bytes"),
                     "Bytes in this box's local copy of the source's raw archive.")
    lines += _metric("sectortrace_mirror_promoted",
                     1 if current.get("promoted_at") else 0,
                     "1 if this box has been promoted out of mirroring.")
    lines += _metric("sectortrace_mirror_scrape_timestamp_seconds",
                     int(now.timestamp()),
                     "When this file was written.")
    return "\n".join(lines) + "\n"


def write_metrics(settings: Settings, destination: Path,
                  now: datetime | None = None) -> Path:
    """Write the metrics file atomically.

    node_exporter reads whatever is in the directory whenever it likes, and a
    half-written file is a parse error that takes the whole textfile
    collector's output with it — not just this mirror's.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial")
    temporary.write_text(metrics(settings, now=now), encoding="utf-8")
    os.replace(temporary, destination)
    return destination


# --- Promotion -------------------------------------------------------------------

def promote(settings: Settings, *, undo: bool = False,
            now: datetime | None = None) -> dict:
    """Record that this box is no longer being replaced from a source.

    The stopping of timers and tunnels is the deployment's job — this is the
    interlock underneath it. `pull` refuses once the marker is set, so a
    timer that somebody re-enables by hand, or a unit that was already
    queued, cannot overwrite a warehouse that has since been written to.

    Reversible, deliberately: the commonest reason to promote is an
    emergency, and the second commonest is a rehearsal of one.
    """
    now = now or _now()
    if undo:
        record(settings, promoted_at=None, promoted_note=None)
        return {"promoted": False, "at": None}
    record(settings, promoted_at=now.isoformat(timespec="seconds"),
           promoted_note=(
               "Promoted out of mirroring. `mirror pull` refuses while this "
               "is set; `mirror promote --undo` clears it, and the next sync "
               "will then replace this warehouse from the source."))
    log.info("mirror.promoted", source=settings.mirror_source_label)
    return {"promoted": True, "at": now.isoformat(timespec="seconds")}


def refuse_if_promoted(settings: Settings) -> None:
    promoted = state(settings).get("promoted_at")
    if promoted:
        raise MirrorError(
            f"this box was promoted out of mirroring at {promoted}, so its "
            "warehouse is no longer a copy of anything and replacing it would "
            "destroy whatever has been written since. `mirror promote --undo` "
            "if you mean to go back to mirroring.")
