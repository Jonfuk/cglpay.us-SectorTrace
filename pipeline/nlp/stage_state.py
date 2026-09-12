"""Durable incremental NLP state and committed batch checkpoints.

Output presence alone cannot prove it was produced from the current chunk,
ontology, model, cue rules, or relation rules. Migration 0096 owns this
schema; runtime code never creates it opportunistically.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable

STAGES = ("chunking", "labels", "spans", "context", "relations", "resolution", "embeddings")
DOWNSTREAM = {
    "chunking": ("labels", "spans", "context", "relations", "resolution", "embeddings"),
    "labels": (),
    "spans": ("context", "relations", "resolution"),
    "context": ("relations",),
    "relations": (),
    "resolution": ("context", "relations"),
    "embeddings": (),
}


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, default=str, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


def combined_hash(*values: Any) -> str:
    return content_hash(list(values))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _validate(stage: str) -> None:
    if stage not in STAGES:
        raise ValueError(f"unknown NLP stage {stage!r}")


def needs_processing(conn, stage: str, input_identity: str, input_hash: str, *,
                     processor_version: str, model_or_ontology_version: str | None = None,
                     configuration: Any = None, dependency_hash: str | None = None,
                     force: bool = False) -> bool:
    _validate(stage)
    if force:
        return True
    row = conn.execute(
        "SELECT input_hash,processor_version,model_or_ontology_version,"
        "configuration_hash,dependency_hash,status FROM nlp_stage_state "
        "WHERE stage=%s AND input_identity=%s", (stage, input_identity)).fetchone()
    if row is None:
        return True
    return (row["input_hash"] != input_hash
            or row["processor_version"] != processor_version
            or row["model_or_ontology_version"] != model_or_ontology_version
            or row["configuration_hash"] != content_hash(configuration or {})
            or row["dependency_hash"] != (dependency_hash or input_hash)
            or row["status"] != "complete")


def pending_identities(conn, stage: str, inputs: Iterable[tuple[str, str, str | None]], *,
                       processor_version: str,
                       model_or_ontology_version: str | None = None,
                       configuration: Any = None, force: bool = False) -> set[str]:
    """Return changed inputs with one ledger lookup for a bounded keyset page.

    Each input is ``(identity, input_hash, dependency_hash)``.  Keeping this
    comparison in Python preserves the exact hash/version semantics of
    :func:`needs_processing` without issuing one SELECT per candidate.
    """
    _validate(stage)
    page = list(inputs)
    if force:
        return {identity for identity, _, _ in page}
    if not page:
        return set()
    identities = [identity for identity, _, _ in page]
    rows = conn.execute(
        "SELECT input_identity,input_hash,processor_version,model_or_ontology_version,"
        "configuration_hash,dependency_hash,status FROM nlp_stage_state "
        "WHERE stage=%s AND input_identity=ANY(%s)", (stage, identities)).fetchall()
    existing = {row["input_identity"]: row for row in rows}
    configuration_hash = content_hash(configuration or {})
    pending = set()
    for identity, input_hash, dependency_hash in page:
        row = existing.get(identity)
        if (row is None or row["input_hash"] != input_hash
                or row["processor_version"] != processor_version
                or row["model_or_ontology_version"] != model_or_ontology_version
                or row["configuration_hash"] != configuration_hash
                or row["dependency_hash"] != (dependency_hash or input_hash)
                or row["status"] != "complete"):
            pending.add(identity)
    return pending


def mark_complete(conn, stage: str, input_identity: str, input_hash: str, *,
                  processor_version: str, output: Any,
                  model_or_ontology_version: str | None = None,
                  configuration: Any = None, dependency_hash: str | None = None,
                  run_id: str | None = None) -> None:
    _validate(stage)
    conn.execute(
        "INSERT INTO nlp_stage_state(stage,input_identity,input_hash,processor_version,"
        "model_or_ontology_version,configuration_hash,dependency_hash,output_digest,"
        "status,last_run_id,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'complete',%s,%s) "
        "ON CONFLICT(stage,input_identity) DO UPDATE SET input_hash=excluded.input_hash,"
        "processor_version=excluded.processor_version,"
        "model_or_ontology_version=excluded.model_or_ontology_version,"
        "configuration_hash=excluded.configuration_hash,dependency_hash=excluded.dependency_hash,"
        "output_digest=excluded.output_digest,status='complete',last_run_id=excluded.last_run_id,"
        "updated_at=excluded.updated_at",
        (stage, input_identity, input_hash, processor_version, model_or_ontology_version,
         content_hash(configuration or {}), dependency_hash or input_hash,
         content_hash(output), run_id, _now()))


def mark_failed(conn, stage: str, input_identity: str, input_hash: str, *,
                processor_version: str, error: BaseException, run_id: str | None,
                model_or_ontology_version: str | None = None,
                configuration: Any = None, dependency_hash: str | None = None) -> None:
    """Attribute a failure after the input savepoint has rolled back."""
    _validate(stage)
    detail = f"{type(error).__name__}: {error}"
    conn.execute(
        "INSERT INTO nlp_stage_failures(run_id,stage,input_identity,input_hash,"
        "failure_class,error_detail,failed_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (run_id, stage, input_identity, input_hash, type(error).__name__, detail, _now()))
    conn.execute(
        "INSERT INTO nlp_stage_state(stage,input_identity,input_hash,processor_version,"
        "model_or_ontology_version,configuration_hash,dependency_hash,status,last_run_id,updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,'failed',%s,%s) "
        "ON CONFLICT(stage,input_identity) DO UPDATE SET input_hash=excluded.input_hash,"
        "processor_version=excluded.processor_version,"
        "model_or_ontology_version=excluded.model_or_ontology_version,"
        "configuration_hash=excluded.configuration_hash,dependency_hash=excluded.dependency_hash,"
        "status='failed',last_run_id=excluded.last_run_id,updated_at=excluded.updated_at",
        (stage, input_identity, input_hash, processor_version, model_or_ontology_version,
         content_hash(configuration or {}), dependency_hash or input_hash, run_id, _now()))


def checkpoint(conn, *, run_id: str, stage: str, batch_ordinal: int,
               last_input_identity: str, rows_processed: int, rows_written: int) -> None:
    _validate(stage)
    conn.execute(
        "INSERT INTO nlp_stage_checkpoints(run_id,stage,batch_ordinal,last_input_identity,"
        "rows_processed,rows_written,committed_at) VALUES (%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT(run_id,batch_ordinal) DO UPDATE SET "
        "last_input_identity=excluded.last_input_identity,rows_processed=excluded.rows_processed,"
        "rows_written=excluded.rows_written,committed_at=excluded.committed_at",
        (run_id, stage, batch_ordinal, last_input_identity, rows_processed, rows_written, _now()))


def invalidate_downstream(conn, stage: str, input_identity: str,
                          related_identities: Iterable[str] = ()) -> int:
    """Mark affected downstream identities invalid without deleting audit state."""
    _validate(stage)
    downstream = DOWNSTREAM[stage]
    identities = tuple(dict.fromkeys((input_identity, *related_identities)))
    if not downstream or not identities:
        return 0
    stage_marks = ",".join("%s" for _ in downstream)
    identity_marks = ",".join("%s" for _ in identities)
    cursor = conn.execute(
        f"UPDATE nlp_stage_state SET status='invalidated',updated_at=%s "
        f"WHERE stage IN ({stage_marks}) AND input_identity IN ({identity_marks})",
        (_now(), *downstream, *identities))
    return max(0, int(cursor.rowcount or 0))
