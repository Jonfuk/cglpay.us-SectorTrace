"""The assistant run ledger (BETA-108).

One immutable row per single-turn assistant run, in `assistant_runs`
(migration 0079). It records what an analyst needs to reconstruct an answer —
the question and filters, the router and answerer model identities and their
endpoint URLs (the `needle_*` / `lfm_*` columns keep their BETA-108 names;
since BETA-114 the endpoint is OpenRouter's base URL, still credential-free),
each frozen prompt template's SHA-256, the routing confidence and arguments,
the retrieved chunk ids, the answer and its result-local citation ids,
timings, outcome and error class — and nothing an analyst does not: no
secrets, no API keys, no model file paths, no raw model logs.

Append-only, by the same discipline as `alias_decisions` and
`qc_sample_findings`: `record()` only ever INSERTs, a re-run is a new row,
and there is no update or delete path. Like `run_ledger`, a ledger write that
fails is logged and swallowed — losing an audit row must not turn a working
answer into an error.

Nothing here is evidence, a review decision or a claim.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from pipeline.nlp.runs import code_commit

log = structlog.get_logger()

OUTCOMES = ("ok", "abstained", "clarified", "timeout", "failed", "unavailable")

# Keys that must never reach a stored row even if a caller passes them: an
# adapter's api_key, a resolved filesystem path to model weights, anything
# that looks like a credential. Redaction is positive — only the columns
# below are written — but this list is asserted by the tests as the contract.
_REJECTED_KEYS = frozenset({"api_key", "apikey", "token", "secret",
                             "model_path", "weights_path", "authorization"})

_COLUMNS = (
    "run_id", "created_at", "code_commit", "question", "filters_json",
    "needle_model", "needle_endpoint", "lfm_model", "lfm_quant", "lfm_endpoint",
    "router_prompt_sha256", "answer_prompt_sha256", "selected_tool",
    "routing_confidence", "tool_args_json", "retrieved_chunk_ids", "answer",
    "citation_ids_json", "timings_json", "outcome", "error_class",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else None, sort_keys=True,
                      separators=(",", ":"))


def record(conn, *, question: str, filters: dict,
           outcome: str,
           needle_model: str | None = None, needle_endpoint: str | None = None,
           lfm_model: str | None = None, lfm_quant: str | None = None,
           lfm_endpoint: str | None = None,
           router_prompt_sha256: str | None = None,
           answer_prompt_sha256: str | None = None,
           selected_tool: str | None = None,
           routing_confidence: float | None = None,
           tool_args: dict | None = None,
           retrieved_chunk_ids: list | None = None,
           answer: str | None = None,
           citation_ids: list | None = None,
           timings: dict | None = None,
           error_class: str | None = None,
           **rejected: Any) -> str | None:
    """Append one run row. Returns its `run_id`, or None if the row could not
    be written (the run's own result is unaffected).

    `**rejected` catches anything a caller should not be handing the ledger —
    a credential, a model file path. Its presence is a programming error and
    is logged; the named columns above are the entire stored surface.
    """
    if rejected:
        log.warning("assistant_ledger.rejected_fields",
                    fields=sorted(rejected)[:8])
        for key in rejected:
            if key.lower() in _REJECTED_KEYS:
                raise ValueError(
                    f"refusing to record {key!r} in the assistant ledger")
    if outcome not in OUTCOMES:
        outcome = "failed"

    run_id = uuid.uuid4().hex
    row = {
        "run_id": run_id,
        "created_at": _now(),
        "code_commit": code_commit(),
        "question": (question or "").strip(),
        "filters_json": _dumps(filters or {}),
        "needle_model": needle_model,
        "needle_endpoint": needle_endpoint,
        "lfm_model": lfm_model,
        "lfm_quant": lfm_quant,
        "lfm_endpoint": lfm_endpoint,
        "router_prompt_sha256": router_prompt_sha256,
        "answer_prompt_sha256": answer_prompt_sha256,
        "selected_tool": selected_tool,
        "routing_confidence": routing_confidence,
        "tool_args_json": _dumps(tool_args) if tool_args is not None else None,
        "retrieved_chunk_ids": _dumps(list(retrieved_chunk_ids))
        if retrieved_chunk_ids is not None else None,
        "answer": answer,
        "citation_ids_json": _dumps(list(citation_ids))
        if citation_ids is not None else None,
        "timings_json": _dumps(timings) if timings is not None else None,
        "outcome": outcome,
        "error_class": error_class,
    }
    placeholders = ", ".join("%s" for _ in _COLUMNS)
    try:
        conn.execute(
            f"INSERT INTO assistant_runs ({', '.join(_COLUMNS)}) "
            f"VALUES ({placeholders})",
            tuple(row[c] for c in _COLUMNS))
        conn.commit()
    except Exception as exc:  # a lost audit row must not lose a good answer
        log.warning("assistant_ledger.record_failed",
                    error=f"{type(exc).__name__}: {exc}")
        return None
    return run_id


def _hydrate(row: dict) -> dict:
    out = dict(row)
    for key, target in (("filters_json", "filters"),
                        ("tool_args_json", "tool_args"),
                        ("retrieved_chunk_ids", "retrieved_chunk_ids"),
                        ("citation_ids_json", "citation_ids"),
                        ("timings_json", "timings")):
        raw = out.pop(key, None)
        try:
            out[target] = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            out[target] = None
    return out


def one(conn, run_id: str) -> dict | None:
    """One run row by id, JSON columns parsed, or None."""
    row = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM assistant_runs WHERE run_id = %s",
        (run_id,)).fetchone()
    return _hydrate(dict(row)) if row else None


def recent(conn, limit: int = 20) -> list[dict]:
    """The most recent run rows, newest first, JSON columns parsed."""
    limit = max(1, min(int(limit), 200))
    rows = conn.execute(
        f"SELECT {', '.join(_COLUMNS)} FROM assistant_runs "
        "ORDER BY created_at DESC LIMIT %s", (limit,)).fetchall()
    return [_hydrate(dict(r)) for r in rows]
