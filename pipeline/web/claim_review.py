"""Operator-side workbench for the semantic claim-candidate review (BETA-047).

`pipeline/nlp/` already has the parts a reviewer needs — `decisions.decide`
records one person's judgement (and, for `corrected`, their better predicate /
object / subject, ontology-validated), `decisions.history` is the audit trail,
and `gate.check` reports exactly how far the review corpus is from letting the
034G classifiers be trained. What was missing is a place to *do* the review.

This is the one-way bridge, the same shape as `pipeline/web/semantic.py`: it
turns query-strings and JSON bodies into calls on those functions and their
`ClaimDecisionError` into the `QueryError` the request handler already turns
into a 400. It adds no policy of its own:

  * decisions are recorded one candidate at a time, never a list — there is
    no bulk-approve path here;
  * nothing writes `graph_claims` (that first-writer decision is parked, see
    beta.md's BETA-034 `context_034f_graph`);
  * nothing trains a model or produces public output.

An `/api/admin/*` tool: it reads the parsed archive, holds no `restricted_`
data, and stays behind the operator's network-trust boundary.
"""
from __future__ import annotations

from pipeline.nlp import decisions
from pipeline.nlp import gate as gate_mod
from pipeline.nlp import ontology as ontology_mod
from pipeline.web.queries import QueryError

PAGE = 25

# `document_claim_candidates.status`: 'new' (extracted, not yet queued),
# 'queued' (a review_queue item exists), 'accepted' / 'dismissed' (a person
# decided). A reviewer filters on these.
STATUSES = ("new", "queued", "accepted", "dismissed")

_BASE_JOIN = """
    FROM document_claim_candidates c
    JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id
    JOIN document_versions v ON v.document_version_id = dc.document_version_id
    JOIN document_records d ON d.document_id = v.document_id
    JOIN evidence_records e ON e.evidence_id = d.evidence_id
"""


def _rows(conn, sql, params=()):
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _label_map():
    onto = ontology_mod.default()
    return (
        {rid: rel.label for rid, rel in onto.relations.items()},
        {cid: con.label for cid, con in onto.concepts.items()},
        onto.version,
    )


def _decorate(row, relation_labels, concept_labels):
    row["predicate_label"] = relation_labels.get(row.get("predicate"))
    row["object_concept_label"] = concept_labels.get(row.get("object_concept_id"))
    return row


def listing(conn, *, status: str | None = None, predicate: str | None = None,
            source_system: str | None = None, q: str | None = None,
            offset: int = 0, limit: int = PAGE) -> dict:
    """A page of live claim candidates with their triple, evidence and the
    latest decision on each."""
    if status and status not in STATUSES:
        raise QueryError(f"status must be one of {', '.join(STATUSES)}.")
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))

    where = ["c.superseded = 0"]
    params: list = []
    if status:
        where.append("c.status = %s")
        params.append(status)
    if predicate:
        where.append("c.predicate = %s")
        params.append(predicate)
    if source_system:
        where.append("e.source_system = %s")
        params.append(source_system)
    if q:
        where.append("(c.evidence_span LIKE %s OR c.subject_hint LIKE %s "
                     "OR c.object_literal LIKE %s)")
        params.extend([f"%{q}%"] * 3)
    clause = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) AS count {_BASE_JOIN} WHERE {clause}", params).fetchone()["count"]

    rows = _rows(conn, f"""
        SELECT c.claim_candidate_id, c.predicate, c.object_concept_id,
               c.object_literal, c.assertion_status, c.subject_hint,
               c.relation_score, c.relation_extractor, c.relation_extractor_version,
               c.evidence_span, c.status, c.created_at,
               e.source_system, e.source_url, e.retrieved_at,
               d.title AS document_title, d.document_type,
               (SELECT dd.decision FROM claim_candidate_decisions dd
                WHERE dd.claim_candidate_id = c.claim_candidate_id
                ORDER BY dd.decided_at DESC LIMIT 1) AS last_decision,
               (SELECT dd.decided_by FROM claim_candidate_decisions dd
                WHERE dd.claim_candidate_id = c.claim_candidate_id
                ORDER BY dd.decided_at DESC LIMIT 1) AS last_decided_by,
               (SELECT COUNT(*) FROM claim_candidate_decisions dd
                WHERE dd.claim_candidate_id = c.claim_candidate_id) AS decision_count
        {_BASE_JOIN}
        WHERE {clause}
        ORDER BY c.relation_score DESC, c.claim_candidate_id
        LIMIT %s OFFSET %s""", [*params, limit, offset])

    relation_labels, concept_labels, _ = _label_map()
    for row in rows:
        _decorate(row, relation_labels, concept_labels)

    return {
        "candidates": rows,
        "total": total,
        "page": {"offset": offset, "limit": limit, "returned": len(rows),
                 "status": status, "predicate": predicate,
                 "source_system": source_system, "q": q},
        "caveat": (
            "A candidate is a machine-extracted (subject, predicate, object) "
            "triple from one sentence — a lead for a reviewer, not a claim. "
            "The relevance score ranks for review only. Deciding one records "
            "a named judgement; it does not write a graph claim or train a "
            "model."),
    }


def detail(conn, claim_candidate_id: str) -> dict:
    """One candidate: its triple, the sentence and containing chunk, source
    identity, and every decision recorded against it."""
    row = conn.execute(f"""
        SELECT c.*, dc.text AS chunk_text, dc.page_start, dc.page_end,
               e.source_system, e.source_url, e.retrieved_at, e.payload_sha256,
               d.title AS document_title, d.document_type, d.published_at,
               d.document_id
        {_BASE_JOIN}
        WHERE c.claim_candidate_id = %s AND c.superseded = 0
        """, (claim_candidate_id,)).fetchone()
    if row is None:
        raise QueryError(f"No live claim candidate {claim_candidate_id!r}.")
    row = dict(row)

    relation_labels, concept_labels, ontology_version = _label_map()
    _decorate(row, relation_labels, concept_labels)
    row["ontology_version"] = ontology_version
    row["decisions"] = decisions.history(conn, claim_candidate_id)
    return row


def gate(conn) -> dict:
    """The read-only 034G gate report: per-category decided counts, spread and
    the blocking list. `pipeline/nlp/gate.check` verbatim — no mutation."""
    return gate_mod.check(conn)


def ontology_options(conn=None) -> dict:
    """The controlled vocabularies a `corrected` decision must choose from —
    for the correction form's dropdowns, so a reviewer cannot type a
    predicate or concept the ontology does not have."""
    onto = ontology_mod.default()
    return {
        "ontology_version": onto.version,
        "predicates": [
            {"id": rid, "label": rel.label, "object": rel.object}
            for rid, rel in sorted(onto.relations.items())],
        "concepts": [
            {"id": cid, "label": con.label,
             "categories": sorted(con.categories)}
            for cid, con in sorted(onto.concepts.items())],
        "reason_codes": ["wrong_predicate", "wrong_object", "wrong_subject",
                          "not_a_claim", "out_of_scope", "unclear_sentence"],
    }


def decide(conn, *, claim_candidate_id: str, decision: str, decided_by: str,
           reason_code: str | None = None,
           corrected_predicate: str | None = None,
           corrected_object_concept_id: str | None = None,
           corrected_object_literal: str | None = None,
           corrected_subject_mention_id: str | None = None,
           review_queue_id: int | None = None,
           note: str | None = None) -> dict:
    """One candidate, one named reviewer. Wraps `decisions.decide` and turns
    its `ClaimDecisionError` into the handler's 400."""
    try:
        return decisions.decide(
            conn, claim_candidate_id, decision, decided_by,
            reason_code=reason_code,
            corrected_predicate=corrected_predicate,
            corrected_object_concept_id=corrected_object_concept_id,
            corrected_object_literal=corrected_object_literal,
            corrected_subject_mention_id=corrected_subject_mention_id,
            review_queue_id=review_queue_id, note=note)
    except decisions.ClaimDecisionError as exc:
        raise QueryError(str(exc)) from None
