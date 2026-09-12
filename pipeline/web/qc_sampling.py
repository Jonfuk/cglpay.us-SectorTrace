"""Quality-control sampling workspace (BETA-106).

Reproducible random or stratified samples of previously decided records, for
append-only second-look findings. A sample is a **deterministic draw**: the
same `seed` + population filter + method always yields the same record ids,
so it can be re-derived and defended after the fact. `qc_samples` stores the
manifest of exactly how it was drawn; `qc_sample_findings` is append-only —
a revised opinion is a new row.

No decision is changed here. A finding records that a person took a second
look; it never rewrites `review_queue` or `alias_decisions`.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone

from pipeline.web.public_queries import _one, _public, _rows
from pipeline.web.queries import QueryError

_MAX_SIZE = 500
_VERDICTS = ("agree", "disagree", "unclear")

# source -> (id column, eligibility clause, {filter param: column})
_SOURCES = {
    "review_queue": {
        "id": "id",
        "eligible": "resolved_at IS NOT NULL",
        "filters": {"module": "module", "item_type": "item_type",
                     "status": "status"},
        "display": ("id", "module", "item_type", "status", "created_at",
                     "resolved_at", "raw_value"),
    },
    "alias_decisions": {
        "id": "decision_id",
        "eligible": "1=1",
        "filters": {"target_scheme": "target_scheme", "status": "status"},
        "display": ("decision_id", "target_scheme", "status", "canonical_name",
                     "reason", "decided_at", "unmatched_name"),
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key(seed: str, rid) -> str:
    return hashlib.sha256(f"{seed}|{rid}".encode("utf-8")).hexdigest()


def _sample_id(seed, source, method, stratify_by, size, filters) -> str:
    payload = json.dumps([seed, source, method, stratify_by, size,
                          sorted((filters or {}).items())], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _population(conn, source: str, filters: dict, stratify_by: str | None):
    spec = _SOURCES[source]
    where = [spec["eligible"]]
    params: list = []
    for name, value in (filters or {}).items():
        col = spec["filters"].get(name)
        if not col:
            raise QueryError(f"{source} cannot be filtered by {name!r}")
        where.append(f"{col} = %s")
        params.append(value)
    strat_col = None
    if stratify_by:
        strat_col = spec["filters"].get(stratify_by) or (
            stratify_by if stratify_by in spec["display"] else None)
        if not strat_col:
            raise QueryError(f"cannot stratify {source} by {stratify_by!r}")
    select = f"{spec['id']} AS rid" + (f", {strat_col} AS stratum" if strat_col else "")
    rows = _rows(conn, f"SELECT {select} FROM {source} WHERE {' AND '.join(where)}",
                 tuple(params))
    return rows, strat_col


def _draw_ids(rows: list[dict], seed: str, size: int, stratified: bool) -> list:
    ordered = sorted(rows, key=lambda r: _key(seed, r["rid"]))
    if not stratified:
        return [r["rid"] for r in ordered[:size]]

    by_stratum: dict = {}
    for r in ordered:
        by_stratum.setdefault(r.get("stratum"), []).append(r["rid"])
    pop = len(ordered)
    picked: list = []
    for stratum, ids in sorted(by_stratum.items(), key=lambda kv: str(kv[0])):
        take = round(size * len(ids) / pop) if pop else 0
        picked.extend(ids[:take])
    # top up (or trim) to exactly `size`, following the global order
    if len(picked) < size:
        chosen = set(picked)
        for r in ordered:
            if r["rid"] not in chosen:
                picked.append(r["rid"])
                if len(picked) >= size:
                    break
    return picked[:size]


def _hydrate(conn, source: str, ids: list) -> list[dict]:
    if not ids:
        return []
    spec = _SOURCES[source]
    cols = ", ".join(spec["display"])
    placeholders = ",".join("%s" for _ in ids)
    rows = {str(r[spec["id"]]): r for r in _rows(
        conn, f"SELECT {cols} FROM {source} WHERE {spec['id']} IN ({placeholders})",
        tuple(ids))}
    # keep the draw order
    return [rows[str(i)] for i in ids if str(i) in rows]


def draw(conn: sqlite3.Connection, *, seed: str, source: str, size: int = 25,
         method: str = "random", stratify_by: str | None = None,
         filters: dict | None = None, created_by: str | None = None) -> dict:
    _public(["qc_samples", "qc_sample_findings", "review_queue",
              "alias_decisions"])
    if source not in _SOURCES:
        raise QueryError(f"source must be one of {sorted(_SOURCES)}")
    if not seed:
        raise QueryError("a seed is required so the draw is reproducible")
    if method not in ("random", "stratified"):
        raise QueryError("method must be 'random' or 'stratified'")
    size = max(1, min(int(size), _MAX_SIZE))
    stratify_by = stratify_by if method == "stratified" else None

    sample_id = _sample_id(seed, source, method, stratify_by, size, filters)
    existing = _one(conn, "SELECT * FROM qc_samples WHERE sample_id = %s",
                    (sample_id,))
    if existing:
        return _manifest(conn, existing)

    rows, _ = _population(conn, source, filters or {}, stratify_by)
    ids = _draw_ids(rows, seed, size, method == "stratified")

    conn.execute(
        "INSERT INTO qc_samples (sample_id, seed, source, method, stratify_by, "
        " population_filter, population_size, sample_size, record_ids, "
        " created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (sample_id, seed, source, method, stratify_by,
         json.dumps(filters or {}, sort_keys=True), len(rows), len(ids),
         json.dumps([str(i) for i in ids]), created_by or None, _now()))
    conn.commit()
    return _manifest(conn,
                     _one(conn, "SELECT * FROM qc_samples WHERE sample_id = %s",
                          (sample_id,)))


def _manifest(conn: sqlite3.Connection, row: dict) -> dict:
    ids = json.loads(row["record_ids"])
    findings = _rows(conn,
                     "SELECT finding_id, record_ref, verdict, note, created_by, "
                     "created_at FROM qc_sample_findings WHERE sample_id = %s "
                     "ORDER BY created_at", (row["sample_id"],))
    verdicts: dict[str, int] = {}
    for f in findings:
        verdicts[f["verdict"]] = verdicts.get(f["verdict"], 0) + 1
    return {
        "sample_id": row["sample_id"], "seed": row["seed"],
        "source": row["source"], "method": row["method"],
        "stratify_by": row["stratify_by"],
        "population_filter": json.loads(row["population_filter"]),
        "population_size": row["population_size"],
        "sample_size": row["sample_size"],
        "record_ids": ids,
        "records": _hydrate(conn, row["source"], ids),
        "findings": findings,
        "finding_counts": verdicts,
        "reviewed": len({f["record_ref"] for f in findings}),
        "created_at": row["created_at"], "created_by": row["created_by"],
        "note": "A deterministic draw: the same seed, source, method and "
                "filter reproduce this exact sample. Findings are append-only "
                "and change no decision.",
    }


def get(conn: sqlite3.Connection, sample_id: str) -> dict:
    _public(["qc_samples", "qc_sample_findings"])
    row = _one(conn, "SELECT * FROM qc_samples WHERE sample_id = %s", (sample_id,))
    if not row:
        raise QueryError(f"No sample {sample_id!r}.")
    return _manifest(conn, row)


def list_samples(conn: sqlite3.Connection, limit: int = 25) -> dict:
    _public(["qc_samples"])
    rows = _rows(conn,
                 "SELECT sample_id, seed, source, method, sample_size, "
                 "population_size, created_at, created_by FROM qc_samples "
                 "ORDER BY created_at DESC LIMIT %s", (max(1, min(int(limit), 100)),))
    return {"samples": rows}


def record_finding(conn: sqlite3.Connection, *, sample_id: str, record_ref: str,
                   verdict: str, note: str | None = None,
                   created_by: str | None = None) -> dict:
    _public(["qc_samples", "qc_sample_findings"])
    sample = _one(conn, "SELECT record_ids FROM qc_samples WHERE sample_id = %s",
                  (sample_id,))
    if not sample:
        raise QueryError(f"No sample {sample_id!r}.")
    if str(record_ref) not in set(json.loads(sample["record_ids"])):
        raise QueryError("that record is not in this sample")
    if verdict not in _VERDICTS:
        raise QueryError(f"verdict must be one of {list(_VERDICTS)}")
    finding_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        "INSERT INTO qc_sample_findings (finding_id, sample_id, record_ref, "
        " verdict, note, created_by, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (finding_id, sample_id, str(record_ref), verdict,
         (note or None), (created_by or None), now))
    conn.commit()
    return {"finding_id": finding_id, "sample_id": sample_id,
            "record_ref": str(record_ref), "verdict": verdict,
            "note": note or None, "created_at": now,
            "appended": True}
