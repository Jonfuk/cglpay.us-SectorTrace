"""Bulk data-entry for the semantic claim-candidate review (BETA-047).

The review is one person's judgement per candidate. `decisions.decide` records
it, `pipeline/web/claim_review.py` is the one-at-a-time surface, and nothing --
here included -- has a "decide everything matching a filter" path, because that
would fabricate the 034G training signal rather than collect it.

What this module removes is the *typing*, not the deciding:

  * `sheet_rows` exports a predicate's queued candidates -- the sentence, the
    triple, the source -- with blank `decision` / `reason_code` / `corrected_*`
    columns for a reviewer to fill in offline. It also does the work that
    shrinks how many rows a person must actually read:
      - `group_id` -- sentences identical bar whitespace and case;
      - `template_id` -- sentences identical once numbers, money, and the
        extracted subject / object literal are blanked (the "no agency staff
        at <council>" family), so `group_by='template'` collapses them and a
        ruling fans out to all;
      - `screen_reason` -- a deterministic, inspectable flag for structurally
        broken extractions (empty / runaway spans, an object that is a bare
        number). A screened row is exported with `suggested_decision='rejected'`
        pre-filled -- a *suggestion*, never a decision;
      - `stratum` + `sample` -- keep the high-confidence positive and negative
        bands whole and take a deterministic 1-in-N of the mushy middle, so a
        category can be brought to the 034G floor without reading all of it
        and the unread majority's precision stays estimable.
  * `apply_sheet` reads the filled-in sheet back and calls `decisions.decide`
    once per row, under the name the caller gives, same validation as the
    one-at-a-time path. `accept_suggested='rejected'` lets the reviewer take a
    screened batch in one explicit move -- each row still records
    `note='via <suggester>'`, and only `rejected` is ever accepted this way
    (a wrong reject costs recall; a wrong approve poisons precision, which the
    gate favours).

The sheet is the artifact: a person fills it in reading each row, and
committing it next to the run makes the batch reproducible. Predicate and
assertion status are part of every group key, so a NEGATED sentence never
groups with its AFFIRMED twin.

A model may fill `suggested_decision` instead of the deterministic screen --
see `docs/CAVEATS.md`, "Model-assisted review triage". Same rule: it writes
`suggested_*`, never `decision`; only `rejected` is acceptable in bulk; the
reviewer's confirmation is the record.
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
    "candidate_id", "group_id", "group_size", "template_id", "template_size",
    "predicate", "predicate_label", "assertion_status", "relation_score",
    "subject_hint", "object", "authority", "source_url", "screen_reason",
    "stratum", "evidence_span",
)
# A suggester (the deterministic screen, or a model) may fill these. They are
# never a decision; `apply_sheet` reads `decision`, and only lifts a
# `suggested_decision` of 'rejected' into one, and only when asked.
SUGGESTION_FIELDS = ("suggested_decision", "suggested_reason", "suggested_by")
DECISION_FIELDS = (
    "decision", "reason_code", "corrected_predicate",
    "corrected_object_concept_id", "corrected_object_literal",
    "corrected_subject_mention_id", "note",
)
SHEET_FIELDS = (*CONTEXT_FIELDS, *SUGGESTION_FIELDS, *DECISION_FIELDS)

GROUP_BY = ("none", "exact", "template")
SAMPLE_BAND_SCORE = 0.80   # a candidate at/above this is in its confidence band
SAMPLE_TAIL_RATE = 10      # 1-in-N of everything outside the two bands
SCREEN_MIN_SPAN = 25       # chars; shorter is a broken extraction
SCREEN_MAX_SPAN = 800      # chars; a whole slide dumped as one "sentence"

_WS = re.compile(r"\s+")
_NUMBERISH = re.compile(
    r"£\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:million|billion|bn|m|k)\b)?"
    r"|\b\d[\d,]*(?:\.\d+)?\s?(?:per cent|%)"
    r"|\b\d[\d,]*(?:\.\d+)?\b")

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


def _template_text(span: str | None, subject_hint: str | None,
                   object_literal: str | None) -> str:
    """The sentence with numbers, money and the extracted subject / object
    literal blanked. Deliberately does NOT blank proper nouns -- there is no
    parser here -- so "no agency staff at Kent CC" and "...at Hull CC" collapse
    but two genuinely different claims about one council do not. Predicate and
    assertion status are in the key alongside, which bounds what the residue
    can merge."""
    text = _norm_span(span)
    for literal in (object_literal, subject_hint):
        literal = _norm_span(literal)
        if len(literal) >= 3:
            text = text.replace(literal, " \x1fx\x1f ")
    text = _NUMBERISH.sub(" \x1fn\x1f ", text)
    return _WS.sub(" ", text).strip()


def template_id(predicate: str, assertion_status: str, span: str | None,
                subject_hint: str | None, object_literal: str | None) -> str:
    """`group_id`'s looser cousin: the same predicate and assertion over the
    same sentence *shape*. A ruling on a template group fans out to every
    member, so the reviewer is shown the distinct variants before deciding."""
    key = (f"{predicate}\x1f{assertion_status}\x1f"
           f"{_template_text(span, subject_hint, object_literal)}")
    return "tpl-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def screen_reason(span: str | None, object_literal: str | None,
                  object_concept_id: str | None) -> str | None:
    """A deterministic, inspectable flag for an extraction that is structurally
    broken -- not a judgement about the claim. A flagged row is exported with
    `suggested_decision='rejected'`; a person still confirms the batch.

      * `span_too_short`   -- under SCREEN_MIN_SPAN chars: no sentence to read.
      * `span_too_long`    -- over SCREEN_MAX_SPAN chars: a whole slide or
        section captured as one unit; the trigger and subject are not in the
        same breath.
      * `object_is_bare_number` -- the object is a 1-3 digit literal with no
        resolved concept: an "of £15k" / "below 15" artifact, not a value the
        predicate is about.
    """
    text = (span or "").strip()
    if len(text) < SCREEN_MIN_SPAN:
        return "span_too_short"
    if len(text) > SCREEN_MAX_SPAN:
        return "span_too_long"
    literal = (object_literal or "").strip()
    if (literal and not object_concept_id
            and literal.replace(",", "").replace(".", "").isdigit()
            and len(literal) <= 3):
        return "object_is_bare_number"
    return None


def _stratum(row: dict) -> str:
    score = row["relation_score"] or 0.0
    if score >= SAMPLE_BAND_SCORE:
        return "positive_band" if row["assertion_status"] == "AFFIRMED" else "negative_band"
    return "tail"


def _sampled(rows: list[dict], target: int, tail_rate: int) -> list[dict]:
    """Keep both high-confidence bands whole (capped at `target`), plus a
    deterministic 1-in-`tail_rate` of the rest, so the category can reach the
    034G floor without the whole queue and the unread majority stays
    measurable. Order within `rows` is score-descending already."""
    kept: list[dict] = []
    band_count = {"positive_band": 0, "negative_band": 0}
    for row in rows:
        stratum = row["stratum"]
        if stratum in band_count:
            if band_count[stratum] < target:
                band_count[stratum] += 1
                kept.append(row)
        elif int(row["candidate_id"][-8:], 16) % max(1, tail_rate) == 0:
            kept.append(row)
    return kept


def _authority(source_key: str | None) -> str:
    # source_key is "<authority_ons_code>|<url>" for committee_papers /
    # cdp_documents; a key with no pipe (other document sources) is used whole.
    return (source_key or "").split("|", 1)[0] or "unknown"


def _labels() -> tuple[dict, dict]:
    onto = ontology_mod.default()
    return ({rid: rel.label for rid, rel in onto.relations.items()},
            {cid: con.label for cid, con in onto.concepts.items()})


def sheet_rows(conn, *, predicate: str, status: str = "queued",
               source_system: str | None = None, group_by: str = "none",
               sample: bool = False, sample_target: int = 130,
               tail_rate: int = SAMPLE_TAIL_RATE,
               limit: int | None = None) -> list[dict]:
    """A decision sheet for one predicate.

    `group_by`:
      * ``none``     -- one row per queued candidate;
      * ``exact``    -- one row per word-for-word-identical `group_id`;
      * ``template`` -- one row per `template_id` (same shape once numbers and
        the subject / object literal are blanked), carrying `group_variants`
        so the reviewer sees what a single ruling would cover.
    A collapsed row carries `group_members` for `apply_sheet` to fan out to.

    `sample` keeps the two high-confidence bands (capped at `sample_target`
    each) plus a deterministic 1-in-`tail_rate` of the rest.
    """
    if group_by not in GROUP_BY:
        raise SheetError(f"group_by must be one of {', '.join(GROUP_BY)}")

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
    rows: list[dict] = []
    for r in raw:
        screen = screen_reason(r["evidence_span"], r["object_literal"],
                               r["object_concept_id"])
        row = {
            "candidate_id": r["claim_candidate_id"],
            "group_id": group_id(r["predicate"], r["assertion_status"],
                                 r["evidence_span"]),
            "template_id": template_id(r["predicate"], r["assertion_status"],
                                       r["evidence_span"], r["subject_hint"],
                                       r["object_literal"]),
            "predicate": r["predicate"],
            "predicate_label": relation_labels.get(r["predicate"], ""),
            "assertion_status": r["assertion_status"],
            "relation_score": r["relation_score"],
            "subject_hint": r["subject_hint"] or "",
            "object": (r["object_literal"]
                       or concept_labels.get(r["object_concept_id"], "")),
            "authority": _authority(r["source_key"]),
            "source_url": r["source_url"],
            "screen_reason": screen or "",
            "evidence_span": (r["evidence_span"] or "").strip(),
            "suggested_decision": "rejected" if screen else "",
            "suggested_reason": screen or "",
            "suggested_by": f"screen:{screen}" if screen else "",
            **{f: "" for f in DECISION_FIELDS},
        }
        row["stratum"] = _stratum(row)
        rows.append(row)

    for key in ("group_id", "template_id"):
        sizes: dict[str, int] = {}
        for row in rows:
            sizes[row[key]] = sizes.get(row[key], 0) + 1
        field = "group_size" if key == "group_id" else "template_size"
        for row in rows:
            row[field] = sizes[row[key]]

    if sample:
        rows = _sampled(rows, sample_target, tail_rate)

    if group_by == "none":
        return rows

    key = "group_id" if group_by == "exact" else "template_id"
    collapsed: dict[str, dict] = {}
    for row in rows:  # score-ordered, so the representative kept is the best
        head = collapsed.get(row[key])
        if head is None:
            collapsed[row[key]] = {**row, "group_members": [row["candidate_id"]],
                                   "group_variants": [row["evidence_span"]]}
        else:
            head["group_members"].append(row["candidate_id"])
            if row["evidence_span"] not in head["group_variants"]:
                head["group_variants"].append(row["evidence_span"])
    return list(collapsed.values())


def _resolve_fmt(path: Path, fmt: str) -> str:
    if fmt not in ("auto", "jsonl", "csv"):
        raise SheetError("format must be jsonl, csv or auto")
    if fmt != "auto":
        return fmt
    return "csv" if path.suffix.lower() == ".csv" else "jsonl"


def write_sheet(rows: list[dict], path, *, fmt: str = "auto") -> int:
    """Write a sheet from `sheet_rows`. Returns the row count. A collapsed sheet
    (rows carrying `group_members` / `group_variants`) must be JSONL -- a list
    does not belong in a CSV cell."""
    path = Path(path)
    fmt = _resolve_fmt(path, fmt)
    collapsed = any("group_members" in r for r in rows)
    if collapsed and fmt == "csv":
        raise SheetError("a collapsed sheet (group_by exact/template) must be JSONL")

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
    return len(rows)


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


def _resolve_decision(row: dict, accept_suggested: str | None) -> tuple[str, dict]:
    """The decision to record for a row, and any fields it carries with it. A
    filled-in `decision` always wins. Otherwise, if `accept_suggested` is set
    and this row's `suggested_decision` matches, lift the suggestion -- with
    its `suggested_reason` as the reason_code and a `note` naming the
    suggester, so the record says the call was reached from a suggestion.
    """
    decision = str(row.get("decision") or "").strip()
    if decision:
        return decision, {
            "reason_code": _blank_none(row.get("reason_code")),
            "corrected_predicate": _blank_none(row.get("corrected_predicate")),
            "corrected_object_concept_id": _blank_none(row.get("corrected_object_concept_id")),
            "corrected_object_literal": _blank_none(row.get("corrected_object_literal")),
            "corrected_subject_mention_id": _blank_none(row.get("corrected_subject_mention_id")),
            "note": _blank_none(row.get("note")),
        }
    suggested = str(row.get("suggested_decision") or "").strip()
    if accept_suggested and suggested == accept_suggested:
        by = str(row.get("suggested_by") or "suggestion").strip()
        own = _blank_none(row.get("note"))
        return suggested, {
            "reason_code": _blank_none(row.get("suggested_reason")),
            "note": f"via {by}" + (f"; {own}" if own else ""),
        }
    return "", {}


def apply_sheet(conn, rows: list[dict], *, decided_by: str,
                dry_run: bool = False, allow_redecide: bool = False,
                accept_suggested: str | None = None,
                source_label: str | None = None) -> dict:
    """Record one reviewer's decisions from a filled-in sheet -- one
    `decisions.decide` call per (candidate, row), same validation as
    `decide-claim`. Rows with no decision are skipped. On the first row that
    `decide` refuses the run stops and names it; rows already recorded on
    earlier iterations stay (each `decide` commits its own). A candidate this
    reviewer has already decided is skipped unless `allow_redecide`.

    `accept_suggested` (only ``'rejected'``) lifts a screened / model-suggested
    `rejected` into a real decision on rows the reviewer left blank -- one
    explicit move over a batch the reviewer has looked at. Never `approved` or
    `corrected`: a wrong reject costs recall, a wrong approve poisons the
    precision the gate favours.
    """
    decided_by = (decided_by or "").strip()
    if not decided_by:
        raise SheetError("decided_by is required and is never defaulted.")
    if accept_suggested not in (None, "rejected"):
        raise SheetError("accept_suggested may only be 'rejected'.")

    cfg = {"decided_by": decided_by, "rows": len(rows), "dry_run": dry_run,
           "allow_redecide": allow_redecide,
           "accept_suggested": accept_suggested or "", "source": source_label or ""}
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
        "skipped_blank": 0, "skipped_existing": 0, "from_suggestion": 0,
        "by_decision": {}, "errors": [], "dry_run": dry_run,
    }
    processed = 0
    aborted = False
    for i, row in enumerate(rows, 1):
        decision, fields = _resolve_decision(row, accept_suggested)
        if not decision:
            summary["skipped_blank"] += 1
            continue
        from_suggestion = not str(row.get("decision") or "").strip()
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
                decisions.decide(conn, cid, decision, decided_by,
                                 commit=not dry_run, **fields)
            except decisions.ClaimDecisionError as exc:
                summary["errors"].append(f"row {i} ({cid}): {exc}")
                aborted = True
                break
            summary["applied"] += 1
            if from_suggestion:
                summary["from_suggestion"] += 1
            summary["by_decision"][decision] = summary["by_decision"].get(decision, 0) + 1
        if aborted:
            break
        processed += 1

    # CAVEATS "Model-assisted review triage": watch how often the reviewer's
    # call just matched the suggestion. Near-total agreement over a real number
    # of rows is the signal the review has gone through the motions.
    paired = [(str(r.get("suggested_decision") or "").strip(),
               str(r.get("decision") or "").strip()) for r in rows]
    paired = [(s, d) for s, d in paired if s and d]
    if paired:
        agree = sum(1 for s, d in paired if s == d) / len(paired)
        summary["suggestion_agreement"] = {
            "n": len(paired), "agree": round(agree, 3),
            "flag": len(paired) >= 20 and agree >= 0.98}

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
