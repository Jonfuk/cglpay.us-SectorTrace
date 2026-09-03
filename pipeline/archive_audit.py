"""Append-only raw-archive audit snapshots (BETA-060).

`archive-verify` checks the archive is intact right now. This is the trend
view beside it: `pipeline archive-audit` computes a small set of integrity and
size metrics from the `archive_objects` index and inserts one immutable row.
A history of those rows shows drift and growth that a point-in-time scan
cannot.

**Measurement only.** Nothing here deletes an object, compacts the archive,
or chooses a retention policy. `compute()` does not write at all; `record()`
only inserts.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from pipeline import catalog
from pipeline.run_ledger import git_revision

_SAMPLE_SIZE = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute(conn) -> dict:
    """The integrity/size metrics from `archive_objects`. Read-only."""
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
            "SELECT COUNT(DISTINCT e.payload_sha256) FROM evidence_records e "
            "WHERE e.payload_sha256 IS NOT NULL AND e.payload_sha256 NOT IN "
            "(SELECT payload_sha256 FROM archive_objects)").fetchone()[0]

    duplicate_hashes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT payload_sha256 FROM archive_objects "
        "GROUP BY payload_sha256 HAVING COUNT(*) > 1)").fetchone()[0]

    # A deterministic sample — the objects with the lexicographically smallest
    # hashes — so the same warehouse produces the same sample and a value that
    # changes between audits is a real change, not sampling noise.
    sample = [
        {"payload_sha256": row["payload_sha256"],
         "source_system": row["source_system"],
         "size_bytes": row["size_bytes"],
         "logical_path": row["logical_path"]}
        for row in conn.execute(
            "SELECT payload_sha256, source_system, size_bytes, logical_path "
            "FROM archive_objects ORDER BY payload_sha256 LIMIT ?", (_SAMPLE_SIZE,))
    ]

    return {
        "object_count": object_count,
        "total_bytes": total_bytes,
        "by_source": by_source,
        "missing_refs": missing_refs,
        "duplicate_hashes": duplicate_hashes,
        "sample": sample,
    }


def record(conn, settings) -> dict:
    """Compute the metrics and append one immutable row. Returns the row."""
    metrics = compute(conn)
    audit_id = uuid.uuid4().hex
    run_at = _now()
    revision = git_revision(settings)
    conn.execute(
        "INSERT INTO archive_audits (audit_id, run_at, object_count, "
        " total_bytes, by_source_json, missing_refs, duplicate_hashes, "
        " sample_json, git_revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (audit_id, run_at, metrics["object_count"], metrics["total_bytes"],
         json.dumps(metrics["by_source"], sort_keys=True), metrics["missing_refs"],
         metrics["duplicate_hashes"], json.dumps(metrics["sample"]), revision))
    conn.commit()
    return {"audit_id": audit_id, "run_at": run_at, "git_revision": revision,
            **metrics}


def history(conn, limit: int = 30) -> list[dict]:
    """The audit rows, newest first, JSON columns parsed."""
    if not catalog.object_type(conn, "archive_audits"):
        return []
    rows = [dict(r) for r in conn.execute(
        "SELECT audit_id, run_at, object_count, total_bytes, by_source_json, "
        "missing_refs, duplicate_hashes, sample_json, git_revision "
        "FROM archive_audits ORDER BY run_at DESC LIMIT ?", (limit,)).fetchall()]
    for row in rows:
        for raw_key, out_key in (("by_source_json", "by_source"),
                                  ("sample_json", "sample")):
            raw = row.pop(raw_key, None)
            try:
                row[out_key] = json.loads(raw) if raw else ({} if out_key == "by_source" else [])
            except (TypeError, ValueError):
                row[out_key] = {} if out_key == "by_source" else []
    return rows
