"""Incremental NLP stage ledger with explicit invalidation semantics."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

STAGES = ("chunking", "labels", "spans", "context", "relations", "resolution")
DOWNSTREAM = {
    "chunking": ("labels", "spans", "context", "relations", "resolution"),
    "labels": ("context", "relations", "resolution"),
    "spans": ("context", "relations", "resolution"),
    "context": ("relations", "resolution"),
    "relations": ("resolution",),
    "resolution": (),
}


def content_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _ensure(conn) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS nlp_stage_state ("
        "stage TEXT NOT NULL, input_identity TEXT NOT NULL, input_hash TEXT NOT NULL, "
        "processor_version TEXT NOT NULL, model_or_ontology_version TEXT, "
        "configuration_hash TEXT NOT NULL, output_digest TEXT, status TEXT NOT NULL DEFAULT 'pending', "
        "updated_at TEXT NOT NULL, PRIMARY KEY(stage, input_identity))"
    )


def needs_processing(conn, stage: str, input_identity: str, input_hash: str, *,
                     processor_version: str, model_or_ontology_version: str | None = None,
                     configuration: Any = None, force: bool = False) -> bool:
    if stage not in STAGES:
        raise ValueError(f"unknown NLP stage {stage!r}")
    _ensure(conn)
    if force:
        return True
    row = conn.execute(
        "SELECT input_hash, processor_version, model_or_ontology_version, configuration_hash, status "
        "FROM nlp_stage_state WHERE stage = ? AND input_identity = ?",
        (stage, input_identity)).fetchone()
    if row is None:
        return True
    return (row["input_hash"] != input_hash or
            row["processor_version"] != processor_version or
            row["model_or_ontology_version"] != model_or_ontology_version or
            row["configuration_hash"] != content_hash(configuration or {}) or
            row["status"] != "complete")


def mark_complete(conn, stage: str, input_identity: str, input_hash: str, *,
                  processor_version: str, output: Any, model_or_ontology_version: str | None = None,
                  configuration: Any = None) -> None:
    _ensure(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO nlp_stage_state(stage, input_identity, input_hash, processor_version, "
        "model_or_ontology_version, configuration_hash, output_digest, status, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'complete', ?) "
        "ON CONFLICT(stage, input_identity) DO UPDATE SET input_hash = excluded.input_hash, "
        "processor_version = excluded.processor_version, model_or_ontology_version = excluded.model_or_ontology_version, "
        "configuration_hash = excluded.configuration_hash, output_digest = excluded.output_digest, "
        "status = 'complete', updated_at = excluded.updated_at",
        (stage, input_identity, input_hash, processor_version, model_or_ontology_version,
         content_hash(configuration or {}), content_hash(output), now))


def invalidate_downstream(conn, stage: str, input_identity: str) -> int:
    """Invalidate only stages that depend on the changed input."""
    _ensure(conn)
    downstream = DOWNSTREAM.get(stage)
    if downstream is None:
        raise ValueError(f"unknown NLP stage {stage!r}")
    if not downstream:
        return 0
    marks = ", ".join("?" for _ in downstream)
    cursor = conn.execute(
        f"DELETE FROM nlp_stage_state WHERE input_identity = ? AND stage IN ({marks})",
        (input_identity, *downstream))
    return max(0, int(cursor.rowcount or 0))

