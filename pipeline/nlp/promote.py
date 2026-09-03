"""Selecting machine claim candidates for human review.

`document_claim_candidates` is high volume by design; `review_queue` is only
ever things worth a person's time. This is the policy between them, and it is
deliberately narrow:

  * a **primary** slice -- a campaign-relevant predicate, `relation_score`
    over a floor, `AFFIRMED` (not `NEGATED` / `HISTORICAL` / `THIRD_PARTY`),
    and a subject that resolves to a registered entity;
  * a **contradiction** slice -- the same (subject, predicate) asserted one
    way in one place and the opposite in another, kept even below the floor
    because a disagreement across documents is exactly what a person should
    adjudicate;
  * a **novel** slice -- a (subject entity, predicate) pair the Evidence
    Graph has never carried, at a slightly lower floor;
  * a small deterministic **validation** sample, so the precision of the
    unselected majority stays measurable;
  * a bounded **gate_coverage** slice -- for the six predicates the 034G
    readiness gate classifies (`pipeline/nlp/gate.py`), a capped number of
    `AFFIRMED` candidates over the `primary` score floor *without* the
    resolved-entity requirement, plus a smaller cap of non-`AFFIRMED` ones so
    the negative class is not starved. The resolved-entity bar exists so an
    Evidence Graph *claim* has a real subject; a `gate_coverage` item trains a
    *classifier*, is never written to `graph_claims`, and is human-reviewed
    before it counts. The narrowness is relaxed only for this bounded labelled
    quota, only for those six categories. Committee papers name their subject
    generically ("the service", "staff") far more often than they name a
    registered provider, so without this slice five of the six categories can
    never reach the gate's per-class floor no matter how the review goes.

It writes `review_queue` items (`item_type='semantic_claim_candidate'`) with
the sentence, chunk id, offsets, source URL and payload SHA-256 in
`context_json`, and marks the candidate `queued`. It does NOT decide
anything and does NOT write a `graph_claims` draft -- that is a person's
decision, recorded separately (034F, second cut).
"""
from __future__ import annotations

import json

from pipeline import db
from pipeline.nlp import gate as gate_mod
from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp import runs

STAGE = "queue"
MODULE = "nlp"
ITEM_TYPE = "semantic_claim_candidate"

SCORE_FLOOR = 0.55
NOVEL_FLOOR = 0.44
VALIDATION_RATE = 40   # 1 in N candidates, by a stable hash

# The six predicates 034G classifies. The gate needs ~65 decided positive and
# ~65 decided negative per category; these caps queue enough that the expected
# survivors of review clear that floor without flooding the queue. Positives
# are AFFIRMED over SCORE_FLOOR (the `primary` quality bar); negatives are the
# other assertion statuses over the same floor -- a reviewer confirms them as
# "about this category but not affirming it now", which `gate._label_for`
# counts as a negative. Ordered by relation_score, so the cap keeps the
# highest-confidence candidates.
GATE_COVERAGE_PREDICATES = frozenset(gate_mod.GATE_CATEGORIES.values())
GATE_COVERAGE_POS_CAP = 150      # AFFIRMED, per predicate, per run
GATE_COVERAGE_NEG_CAP = 90       # non-AFFIRMED, per predicate, per run
_GATE_NEGATIVE_ASSERTIONS = frozenset(
    {"NEGATED", "HISTORICAL", "HYPOTHETICAL", "THIRD_PARTY", "CONDITIONAL"})


def campaign_predicates(onto: ontology_mod.Ontology) -> frozenset[str]:
    """Every `pressure` predicate plus the commissioning-change ones -- the
    claims a pay campaign actually argues from."""
    extra = {"commissioning.is_recommissioning", "commissioning.awarded_contract",
             "commissioning.delivers_service", "commissioning.extended_contract"}
    return frozenset(
        {r.id for r in onto.relations.values() if r.pressure} | extra)


def _subject_entity(conn, row) -> str | None:
    if not row["subject_mention_id"]:
        return None
    hit = conn.execute(
        "SELECT dem.entity_id FROM document_concept_mentions m "
        "JOIN document_entity_mentions dem ON dem.document_element_id = m.document_element_id "
        "  AND dem.start_offset = m.element_char_start AND dem.end_offset = m.element_char_end "
        "  AND dem.matched_text = m.span_text "
        "WHERE m.document_concept_mention_id = %s", (row["subject_mention_id"],)).fetchone()
    return hit["entity_id"] if hit else None


def _graph_has_pair(conn, entity_id: str, predicate: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM graph_claims WHERE subject_entity_id = %s AND predicate = %s LIMIT 1",
        (entity_id, predicate)).fetchone() is not None


def _validation_pick(candidate_id: str) -> bool:
    return int(candidate_id[-8:], 16) % VALIDATION_RATE == 0


def select(conn, candidates: list, *, campaign: frozenset[str]) -> list[dict]:
    """[{row, reason, subject_entity_id}] for the candidates worth queueing."""
    # contradiction detection needs the whole batch first.
    by_pair: dict[tuple, set[str]] = {}
    subject_entities: dict[str, str | None] = {}
    for row in candidates:
        entity_id = _subject_entity(conn, row)
        subject_entities[row["claim_candidate_id"]] = entity_id
        subject_key = entity_id or row["subject_hint"]
        if subject_key:
            by_pair.setdefault((subject_key, row["predicate"]), set()).add(row["assertion_status"])
    contradicted = {pair for pair, statuses in by_pair.items()
                    if "AFFIRMED" in statuses and "NEGATED" in statuses}

    selected: list[dict] = []
    for row in candidates:
        cid = row["claim_candidate_id"]
        entity_id = subject_entities[cid]
        subject_key = entity_id or row["subject_hint"]
        predicate = row["predicate"]
        score = row["relation_score"] or 0.0
        status = row["assertion_status"]
        reason: str | None = None

        if predicate in campaign and (subject_key, predicate) in contradicted:
            reason = "contradiction"
        elif (predicate in campaign and score >= SCORE_FLOOR and status == "AFFIRMED"
                and entity_id is not None):
            reason = "primary"
        elif (predicate in campaign and score >= NOVEL_FLOOR and status == "AFFIRMED"
                and entity_id is not None and not _graph_has_pair(conn, entity_id, predicate)):
            reason = "novel"
        elif _validation_pick(cid):
            reason = "validation"

        if reason:
            selected.append({"row": row, "reason": reason, "subject_entity_id": entity_id})

    # gate_coverage: a second, bounded pass for the 034G categories only. It
    # deliberately does not require entity_id -- see the module docstring.
    # `candidates` arrives ordered by relation_score DESC, so first-past-the-cap
    # keeps the highest-confidence sentences for each predicate.
    already = {pick["row"]["claim_candidate_id"] for pick in selected}
    pos_seen: dict[str, int] = {}
    neg_seen: dict[str, int] = {}
    for row in candidates:
        cid = row["claim_candidate_id"]
        predicate = row["predicate"]
        if cid in already or predicate not in GATE_COVERAGE_PREDICATES:
            continue
        if (row["relation_score"] or 0.0) < SCORE_FLOOR:
            continue
        status = row["assertion_status"]
        if status == "AFFIRMED" and pos_seen.get(predicate, 0) < GATE_COVERAGE_POS_CAP:
            pos_seen[predicate] = pos_seen.get(predicate, 0) + 1
        elif status in _GATE_NEGATIVE_ASSERTIONS and neg_seen.get(predicate, 0) < GATE_COVERAGE_NEG_CAP:
            neg_seen[predicate] = neg_seen.get(predicate, 0) + 1
        else:
            continue
        selected.append({"row": row, "reason": "gate_coverage",
                         "subject_entity_id": subject_entities[cid]})

    return selected


def _candidates(conn, source_system, limit):
    sql = (
        "SELECT c.*, e.source_url, e.retrieved_at, e.payload_sha256 "
        "FROM document_claim_candidates c "
        "JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE c.status = 'new' AND c.superseded = 0")
    params: list = []
    if source_system:
        sql += " AND e.source_system = %s"
        params.append(source_system)
    sql += " ORDER BY c.relation_score DESC, c.claim_candidate_id"
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def run(conn, *, source_system: str | None = None, limit: int | None = None,
        dry_run: bool = False) -> dict:
    """Queue the selected slice of `new` claim candidates into `review_queue`.
    Idempotent: `record_review_item` upserts, and a candidate already `queued`
    is not re-selected."""
    onto = ontology_mod.default()
    campaign = campaign_predicates(onto)
    config = {"score_floor": SCORE_FLOOR, "novel_floor": NOVEL_FLOOR,
              "validation_rate": VALIDATION_RATE, "source_system": source_system, "limit": limit}
    run_id = runs.start_run(conn, STAGE, config=config, ontology_version=onto.version,
                            input_scope={"source_system": source_system, "limit": limit})
    candidates = _candidates(conn, source_system, limit)
    by_reason: dict[str, int] = {}
    queued = 0
    try:
        for pick in select(conn, candidates, campaign=campaign):
            row = pick["row"]
            context = {
                "candidate_id": row["claim_candidate_id"],
                "predicate": row["predicate"],
                "subject_entity_id": pick["subject_entity_id"],
                "subject_hint": row["subject_hint"],
                "object_concept_id": row["object_concept_id"],
                "object_literal": row["object_literal"],
                "assertion_status": row["assertion_status"],
                "relation_score": row["relation_score"],
                "selection_reason": pick["reason"],
                "sentence": row["evidence_span"],
                "document_chunk_id": row["document_chunk_id"],
                "char_start": row["char_start"],
                "char_end": row["char_end"],
                "source_url": row["source_url"],
                "retrieved_at": row["retrieved_at"],
                "payload_sha256": row["payload_sha256"],
            }
            db.record_review_item(conn, MODULE, ITEM_TYPE, row["claim_candidate_id"],
                                  json.dumps(context, sort_keys=True))
            conn.execute(
                "UPDATE document_claim_candidates SET status = 'queued' "
                "WHERE claim_candidate_id = %s AND status = 'new'",
                (row["claim_candidate_id"],))
            by_reason[pick["reason"]] = by_reason.get(pick["reason"], 0) + 1
            queued += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=len(candidates),
                        rows_written=queued, error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(candidates), rows_written=queued)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"run_id": run_id, "considered": len(candidates), "queued": queued,
            "by_reason": by_reason, "dry_run": dry_run}
