"""Append-only raw-archive audit snapshots (BETA-060), with real verification.

`archive-verify` checks the archive is intact right now, against every key
its own inventory can see. This is the trend view beside it, on the
`archive_objects` index the extraction pipeline maintains, and — since
performance.md's Phase 5 archive-audit gap — a genuine read-and-rehash of
what it samples, not only a count of what the database believes is there.

Two schedules, one mechanism. `record()` re-hashes a deterministic 1% sample
(at least 100 objects, or every object under `full=True`) and appends one
immutable row; a mismatch is quarantined (`pipeline.quarantine`), never
deleted — the archive audit alerts on a bad object, it does not act as
though the evidence never existed. `compute()` alone stays what it always
was for a caller with no archive handy: read-only DB metrics, no bytes
fetched, no writes at all.
"""
from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone

from pipeline import catalog, quarantine
from pipeline.archive import get_archive
from pipeline.run_ledger import git_revision

# The daily sample: at least this many objects, or 1% of the archive,
# whichever is larger — performance.md's own numbers for Phase 5's
# archive-audit gap. `_SAMPLE_FRACTION` alone would round to nothing on a
# warehouse with only a few hundred objects, which is exactly the sized
# warehouse where losing track of one object matters most.
_MIN_SAMPLE_SIZE = 100
_SAMPLE_FRACTION = 0.01


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sample_size(object_count: int, full: bool) -> int:
    if full:
        return object_count
    if not object_count:
        return 0
    return max(_MIN_SAMPLE_SIZE, math.ceil(object_count * _SAMPLE_FRACTION))


def _sampled_rows(conn, limit: int | None) -> list[dict]:
    # The lexicographically smallest hashes, exactly as before this module
    # verified anything — a deterministic selection means the same warehouse
    # produces the same sample, so a value that changes between two audits is
    # a real change, not sampling noise landing on a different object.
    sql = ("SELECT payload_sha256, source_system, size_bytes, logical_path "
           "FROM archive_objects ORDER BY payload_sha256")
    params: tuple = ()
    if limit is not None:
        sql += " LIMIT %s"
        params = (limit,)
    return [dict(row) for row in conn.execute(sql, params)]


def _verify_objects(archive, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Read each row's exact bytes back from the archive and confirm the
    stored hash and size still match. Returns `(annotated_rows, failures)` —
    the annotation (`verified_ok`) is what a person reads in the audit
    history; `failures` is in the same shape `Archive.verify()` already
    produces, so `quarantine_failures` handles all three callers (this
    module's daily sample, its quarterly full pass, and `archive-verify`)
    identically.
    """
    annotated, failures = [], []
    for row in rows:
        entry = dict(row)
        try:
            obj = archive.get_by_ref(row["logical_path"])
            if obj is None:
                raise FileNotFoundError(row["logical_path"])
            body = obj.read_bytes()
            actual_sha256 = hashlib.sha256(body).hexdigest()
            ok = actual_sha256 == row["payload_sha256"] and len(body) == row["size_bytes"]
            entry["verified_ok"] = ok
            if not ok:
                failures.append({
                    "key": row["logical_path"], "expected": row["payload_sha256"],
                    "actual": actual_sha256, "expected_bytes": row["size_bytes"],
                    "actual_bytes": len(body)})
        except Exception as exc:  # a missing file, a bad reference, a transport error
            entry["verified_ok"] = False
            failures.append({"key": row["logical_path"], "error": str(exc)})
        annotated.append(entry)
    return annotated, failures


def quarantine_failures(conn, failures: list[dict], *, module: str) -> None:
    """Record each archive integrity failure so it is listable/retryable
    (migration 0103) rather than only living in a point-in-time report or
    this module's own audit row. Shared by `archive-verify`, the daily
    sample and the quarterly full verification — one quarantine call for the
    one failure shape (`Archive.verify()`'s, and this module's sampled/full
    checks produce it identically) means a mismatch is recorded the same way
    regardless of which path found it. Never deletes evidence; quarantine
    only flags it for a person.
    """
    for failure in failures:
        quarantine.quarantine(
            conn, kind="archive_mismatch", module=module,
            item_identity=failure["key"],
            failure_class="invalid_key" if "error" in failure else "sha256_mismatch",
            reason=failure.get("error") or (
                f"expected {failure.get('expected')}, got {failure.get('actual')}"),
            input_sha256=failure.get("expected"), output_sha256=failure.get("actual"),
            payload=failure)


def compute(conn, archive=None, *, full: bool = False) -> dict:
    """The integrity/size metrics from `archive_objects`, plus a verified
    sample (or, under `full=True`, every object). Read-only on the database
    in every case — `archive` is read from, never written to, and a mismatch
    is reported in the return value rather than quarantined here; quarantine
    is `record()`'s job, so a caller measuring only (no `archive` passed)
    gets the original DB-metrics-only behaviour with nothing fetched at all.
    """
    if not catalog.object_type(conn, "archive_objects"):
        raise RuntimeError("archive_objects table does not exist in this warehouse.")

    totals = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS b "
        "FROM archive_objects").fetchone()
    # PostgreSQL returns NUMERIC aggregates as Decimal; the audit contract is
    # JSON and these counters are integral byte/object counts.
    object_count = int(totals["n"])
    total_bytes = int(totals["b"] or 0)

    by_source = {
        row["source_system"]: {"count": int(row["n"]), "bytes": int(row["b"] or 0)}
        for row in conn.execute(
            "SELECT source_system, COUNT(*) AS n, COALESCE(SUM(size_bytes), 0) AS b "
            "FROM archive_objects GROUP BY source_system ORDER BY source_system")
    }

    # Evidence rows whose bytes were never archived. `evidence_records` is the
    # cross-source provenance table; a payload_sha256 there with no
    # archive_objects row is a gap worth trending.
    missing_refs = 0
    if catalog.object_type(conn, "evidence_records"):
        missing_refs = conn.execute(
            "SELECT COUNT(DISTINCT e.payload_sha256) AS count FROM evidence_records e "
            "WHERE e.payload_sha256 IS NOT NULL AND e.payload_sha256 NOT IN "
            "(SELECT payload_sha256 FROM archive_objects)").fetchone()["count"]

    duplicate_hashes = conn.execute(
        "SELECT COUNT(*) AS count FROM (SELECT payload_sha256 FROM archive_objects "
        "GROUP BY payload_sha256 HAVING COUNT(*) > 1) AS duplicate_groups").fetchone()["count"]

    sample_size = _sample_size(object_count, full)
    rows = _sampled_rows(conn, None if full else sample_size)
    if archive is not None:
        sample, failures = _verify_objects(archive, rows)
    else:
        sample, failures = rows, []

    return {
        "object_count": object_count,
        "total_bytes": total_bytes,
        "by_source": by_source,
        "missing_refs": missing_refs,
        "duplicate_hashes": duplicate_hashes,
        "sample": sample,
        "sample_size": sample_size,
        "verified_mismatches": len(failures),
        "failures": failures,
    }


def record(conn, settings, *, full: bool = False) -> dict:
    """Compute the metrics — verifying the sample, or every object under
    `full=True` — and append one immutable row. Quarantines any verification
    failure (never deletes it) so it is listable/retryable rather than only
    living in this row. Returns the row.
    """
    metrics = compute(conn, get_archive(settings), full=full)
    failures = metrics.pop("failures")
    audit_id = uuid.uuid4().hex
    run_at = _now()
    revision = git_revision(settings)
    audit_kind = "quarterly_full" if full else "daily_sample"
    conn.execute(
        "INSERT INTO archive_audits (audit_id, run_at, audit_kind, object_count, "
        " total_bytes, by_source_json, missing_refs, duplicate_hashes, "
        " sample_json, sample_size, verified_mismatches, git_revision) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (audit_id, run_at, audit_kind, metrics["object_count"], metrics["total_bytes"],
         json.dumps(metrics["by_source"], sort_keys=True), metrics["missing_refs"],
         metrics["duplicate_hashes"], json.dumps(metrics["sample"]), metrics["sample_size"],
         metrics["verified_mismatches"], revision))
    if failures:
        quarantine_failures(conn, failures, module="archive_audit_full" if full else "archive_audit_sample")
    conn.commit()
    return {"audit_id": audit_id, "run_at": run_at, "audit_kind": audit_kind,
            "git_revision": revision, **metrics}


def history(conn, limit: int = 30) -> list[dict]:
    """The audit rows, newest first, JSON columns parsed."""
    if not catalog.object_type(conn, "archive_audits"):
        return []
    rows = [dict(r) for r in conn.execute(
        "SELECT audit_id, run_at, audit_kind, object_count, total_bytes, by_source_json, "
        "missing_refs, duplicate_hashes, sample_json, sample_size, verified_mismatches, "
        "git_revision FROM archive_audits ORDER BY run_at DESC LIMIT %s", (limit,)).fetchall()]
    for row in rows:
        for raw_key, out_key in (("by_source_json", "by_source"),
                                  ("sample_json", "sample")):
            raw = row.pop(raw_key, None)
            try:
                row[out_key] = json.loads(raw) if raw else ({} if out_key == "by_source" else [])
            except (TypeError, ValueError):
                row[out_key] = {} if out_key == "by_source" else []
    return rows
