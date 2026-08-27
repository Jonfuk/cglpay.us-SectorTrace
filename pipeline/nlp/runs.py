"""`nlp_runs` — one row per invocation of an nlp stage.

The provenance philosophy the warehouse applies to a collected row, applied
to a model run: the software commit, the chunker/model/ontology versions and
a hash of the full config are recorded when the run starts, so "why does this
annotation exist, and under what software state?" is a query rather than a
guess. Every derived row (`document_chunks`, `document_embeddings`, and the
later mention/assertion/candidate tables) carries `nlp_run_id`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from datetime import datetime, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_sha256(config: dict) -> str:
    return hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def code_commit() -> str | None:
    """The current git commit, or None outside a checkout. Recorded, never
    required — a run from a tarball is still a valid run."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def start_run(conn, stage: str, *, config: dict, chunker_version: str | None = None,
              model_key: str | None = None, model_revision: str | None = None,
              ontology_version: str | None = None, input_scope: dict | None = None) -> str:
    """Insert a `running` row and return its id. The caller commits."""
    run_id = f"nlprun-{uuid.uuid4()}"
    conn.execute(
        "INSERT INTO nlp_runs (run_id, stage, status, started_at, code_commit, "
        "chunker_version, model_key, model_revision, ontology_version, config_sha256, "
        "input_scope_json) VALUES (?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, stage, utcnow(), code_commit(), chunker_version, model_key,
         model_revision, ontology_version, config_sha256(config),
         json.dumps(input_scope or {}, sort_keys=True)))
    return run_id


def finish_run(conn, run_id: str, *, status: str, rows_processed: int = 0,
               rows_written: int = 0, error: str | None = None) -> None:
    conn.execute(
        "UPDATE nlp_runs SET status=?, completed_at=?, rows_processed=?, rows_written=?, "
        "error=? WHERE run_id=?",
        (status, utcnow(), rows_processed, rows_written, error, run_id))
