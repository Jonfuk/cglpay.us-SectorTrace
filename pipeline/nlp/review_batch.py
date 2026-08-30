"""Bulk data-entry for the semantic claim-candidate review (BETA-047).

The review is one person's judgement per candidate. `decisions.decide` records
it, `pipeline/web/claim_review.py` is the one-at-a-time surface, and nothing --
here included -- has a "decide everything matching a filter" path, because that
would fabricate the 034G training signal rather than collect it.

What this module removes is the *typing*, not the deciding:

  * `sheet_rows` exports a predicate's queued candidates -- the sentence, the
    triple, the source, a stable `group_id` for word-for-word duplicate
    sentences -- with blank `decision` / `reason_code` / `corrected_*` columns
    for a reviewer to fill in offline;
  * `apply_sheet` reads that filled-in sheet back and calls `decisions.decide`
    once per row, under the name the caller gives, with the same validation the
    one-at-a-time path runs.

The sheet is the artifact: a person fills it in reading each row, and
committing it next to the run makes the batch reproducible. `group_id` lets one
ruling carry to sentences that are identical bar whitespace and case (a
committee paper quoted verbatim in three agenda packs); predicate and assertion
status are part of the key, so a NEGATED sentence never groups with its
AFFIRMED twin.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path

from pipeline.nlp import decisions, runs
from pipeline.nlp import ontology as ontology_mod

STAGE = "review_batch"

# Filled by the export; the reviewer completes the decision half.
CONTEXT_FIELDS = (
    "candidate_id", "group_id", "group_size", "predicate", "predicate_label",
    "assertion_status", "relation_score", "subject_hint", "object",
    "authority", "source_url", "evidence_span",
)
DECISION_FIELDS = (
    "decision", "reason_code", "corrected_predicate",
    "corrected_object_concept_id", "corrected_object_literal",
    "corrected_subject_mention_id", "note",
)
SHEET_FIELDS = (*CONTEXT_FIELDS, *DECISION_FIELDS)

_WS = re.compile(r"\s+")

_SHEET_SQL = """
SELECT c.claim_candidate_id, c.predicate, c.assertion_status, c.relation_score,
       c.subject_hint, c.object_concept_id, c.object_literal, c.evidence_span,
       dr.source_key, e.source_url
FROM document_claim_candidates c
JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id
JOIN document_versions v ON v.document_version_id = dc.document_version_id
JOIN document_records dr ON dr.document_id = v.document_id
JOIN evidence_records e ON e.evidence_id = dr.evidence_id
WHERE c.superseded = 0 AND c.status = ? AND c.predicate = ?
"""


class SheetError(ValueError):
    """A sheet that could not be read or that a caller asked for wrongly."""


def _norm_span(text: str | None) -> str:
    return _WS.sub(" ", (text or "").strip()).casefold()


def group_id(predicate: str, assertion_status: str, span: str | None) -> str:
    """A stable id shared by candidates whose predicate, assertion status and
    sentence (bar whitespace and case) are the same."""
    key = f"{predicate}\x1f{assertion_status}\x1f{_norm_span(span)}"
    return "grp-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _authority(source_key: str | None) -> str:
    # source_key is "<authority_ons_code>|<url>" for committee_papers /
    # cdp_documents; a key with no pipe (other document sources) is used whole.
    return (source_key or "").split("|", 1)[0] or "unknown"


def _labels() -> tuple[dict, dict]:
    onto = ontology_mod.default()
    return ({rid: rel.label for rid, rel in onto.relations.items()},
            {cid: con.label for cid, con in onto.concepts.items()})


def sheet_rows(conn, *, predicate: str, status: str = "queued",
               source_system: str | None = None, groups_only: bool = False,
               limit: int | None = None) -> list[dict]:
    """A decision sheet for one predicate: one row per queued candidate, or --
    with `groups_only` -- one row per word-for-word-identical group, carrying
    `group_members` so `apply_sheet` can fan a ruling out to all of them."""
    sql = _SHEET_SQL
    params: list = [status, predicate]
    if source_system:
        sql += " AND e.source_system = ?"
        params.append(source_system)
    sql += " ORDER BY c.relation_score DESC, c.claim_candidate_id"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    raw = conn.execute(sql, params).fetchall()

    relation_labels, concept_labels = _labels()
    enriched: list[dict] = []
    sizes: dict[str, int] = {}
    for r in raw:
        gid = group_id(r["predicate"], r["assertion_status"], r["evidence_span"])
        sizes[gid] = sizes.get(gid, 0) + 1
        enriched.append({
            "candidate_id": r["claim_candidate_id"],
            "group_id": gid,
            "predicate": r["predicate"],
            "predicate_label": relation_labels.get(r["predicate"], ""),
            "assertion_status": r["assertion_status"],
            "relation_score": r["relation_score"],
            "subject_hint": r["subject_hint"] or "",
            "object": (r["object_literal"]
                       or concept_labels.get(r["object_concept_id"], "")),
            "authority": _authority(r["source_key"]),
            "source_url": r["source_url"],
            "evidence_span": (r["evidence_span"] or "").strip(),
            **{f: "" for f in DECISION_FIELDS},
        })

    for row in enriched:
        row["group_size"] = sizes[row["group_id"]]

    if not groups_only:
        return enriched

    seen: dict[str, dict] = {}
    for row in enriched:  # enriched is already score-ordered, so the first
        gid = row["group_id"]  # member kept is the highest-scoring one
        if gid in seen:
            seen[gid]["group_members"].append(row["candidate_id"])
        else:
            seen[gid] = {**row, "group_members": [row["candidate_id"]]}
    return list(seen.values())


def _resolve_fmt(path: Path, fmt: str) -> str:
    if fmt not in ("auto", "jsonl", "csv"):
        raise SheetError("format must be jsonl, csv or auto")
    if fmt != "auto":
        return fmt
    return "csv" if path.suffix.lower() == ".csv" else "jsonl"


def write_sheet(rows: list[dict], path, *, fmt: str = "auto") -> int:
    """Write a sheet from `sheet_rows`. Returns the number of distinct groups.
    `groups_only` sheets (rows carrying `group_members`) must be JSONL -- a
    list does not belong in a CSV cell."""
    path = Path(path)
    fmt = _resolve_fmt(path, fmt)
    groups_only = any("group_members" in r for r in rows)
    if groups_only and fmt == "csv":
        raise SheetError("a --groups-only sheet must be written as JSONL")

    if fmt == "csv":
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(SHEET_FIELDS),
                                    extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in SHEET_FIELDS})
    else:
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    return len({r["group_id"] for r in rows})


def read_sheet(path, *, fmt: str = "auto") -> list[dict]:
    """Read a sheet written by `write_sheet` (or a spreadsheet saved back over
    one). Parses only -- `apply_sheet` does the validation."""
    path = Path(path)
    fmt = _resolve_fmt(path, fmt)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SheetError(f"cannot read {path}: {exc}") from None

    if fmt == "csv":
        return list(csv.DictReader(text.splitlines()))

    rows: list[dict] = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SheetError(f"{path} line {n}: {exc}") from None
    return rows


def _blank_none(value):
    value = (value or "").strip() if isinstance(value, str) else value
    return value or None


def _targets(row: dict) -> list[str]:
    members = row.get("group_members")
    if isinstance(members, list) and members:
        return [str(m).strip() for m in members if str(m).strip()]
    if isinstance(members, str) and members.strip():
        return [m for m in members.split() if m]
    cid = str(row.get("candidate_id") or "").strip()
    return [cid] if cid else []


def _already_decided_by(conn, candidate_id: str, decided_by: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM claim_candidate_decisions "
        "WHERE claim_candidate_id = ? AND decided_by = ? LIMIT 1",
        (candidate_id, decided_by)).fetchone() is not None


def apply_sheet(conn, rows: list[dict], *, decided_by: str,
                dry_run: bool = False, allow_redecide: bool = False,
                source_label: str | None = None) -> dict:
    """Record one reviewer's decisions from a filled-in sheet -- one
    `decisions.decide` call per (candidate, row), same validation as
    `decide-claim`. Rows with a blank `decision` are skipped. On the first row
    that `decide` refuses the run stops and names it; rows already recorded on
    earlier iterations stay (each `decide` commits its own). A candidate this
    reviewer has already decided is skipped unless `allow_redecide`.
    """
    decided_by = (decided_by or "").strip()
    if not decided_by:
        raise SheetError("decided_by is required and is never defaulted.")

    cfg = {"decided_by": decided_by, "rows": len(rows), "dry_run": dry_run,
           "allow_redecide": allow_redecide, "source": source_label or ""}
    real = not dry_run
    # On the real path the run row is committed up front, so a crash mid-batch
    # leaves a `running` record next to the decisions `decide` has already
    # committed. A dry run records its trace afterwards (D-02: a dry run must
    # still leave one), since its trial writes are about to be rolled back.
    run_id = None
    if real:
        run_id = runs.start_run(conn, STAGE, config=cfg)
        conn.commit()

    summary = {
        "run_id": run_id, "rows": len(rows), "applied": 0,
        "skipped_blank": 0, "skipped_existing": 0,
        "by_decision": {}, "errors": [], "dry_run": dry_run,
    }
    processed = 0
    aborted = False
    for i, row in enumerate(rows, 1):
        decision = str(row.get("decision") or "").strip()
        if not decision:
            summary["skipped_blank"] += 1
            continue
        targets = _targets(row)
        if not targets:
            summary["errors"].append(f"row {i}: no candidate_id")
            aborted = True
            break
        for cid in targets:
            if not allow_redecide and _already_decided_by(conn, cid, decided_by):
                summary["skipped_existing"] += 1
                continue
            try:
                decisions.decide(
                    conn, cid, decision, decided_by,
                    reason_code=_blank_none(row.get("reason_code")),
                    corrected_predicate=_blank_none(row.get("corrected_predicate")),
                    corrected_object_concept_id=_blank_none(row.get("corrected_object_concept_id")),
                    corrected_object_literal=_blank_none(row.get("corrected_object_literal")),
                    corrected_subject_mention_id=_blank_none(row.get("corrected_subject_mention_id")),
                    note=_blank_none(row.get("note")),
                    commit=not dry_run)
            except decisions.ClaimDecisionError as exc:
                summary["errors"].append(f"row {i} ({cid}): {exc}")
                aborted = True
                break
            summary["applied"] += 1
            summary["by_decision"][decision] = summary["by_decision"].get(decision, 0) + 1
        if aborted:
            break
        processed += 1

    if dry_run:
        conn.rollback()
        run_id = runs.start_run(conn, STAGE, config=cfg)
        summary["run_id"] = run_id
    runs.finish_run(
        conn, run_id, status="failed" if aborted else "ok",
        rows_processed=processed,
        rows_written=0 if dry_run else summary["applied"],
        error=summary["errors"][-1] if summary["errors"] else None)
    conn.commit()
    return summary
