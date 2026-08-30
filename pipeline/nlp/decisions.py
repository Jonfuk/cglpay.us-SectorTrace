"""Recording a person's decision on a machine claim candidate.

The plan for 034F ends with an approved candidate becoming a `graph_claims`
draft. That step is held: `graph_claims` has no writer anywhere in the code
yet and no draft -> `entity_relationships` lifecycle, so wiring it is a
separate decision, not something to slip in here.

What this module does is the half that is unambiguous and that 034G needs: it
records the reviewer's judgement in `claim_candidate_decisions`, and -- when
they disagree with the machine -- their CORRECTION (a better predicate, a
better object, a reason code). A corrected candidate is far stronger training
data than a binary reject.

The reviewer's name is recorded as given and never defaulted. Nothing here is
promoted, so there is no `promoted_by` column to protect (the
`pipeline/ai_promotion.py` rule) -- but the same spirit holds: the machine's
detector already sits on the candidate row, and a human decision is stored
against a human name, separately.
"""
from __future__ import annotations

from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp.runs import utcnow

# `document_claim_candidates.status` values. 'accepted' = a person said yes;
# it does NOT mean a graph_claims draft exists (that writer is a later step).
DECISIONS = ("approved", "rejected", "corrected")
_STATUS_AFTER = {"approved": "accepted", "corrected": "accepted", "rejected": "dismissed"}


class ClaimDecisionError(ValueError):
    """A decision that was refused, with a message for the reviewer."""


def _relation_ids() -> frozenset[str]:
    return frozenset(ontology_mod.default().relations)


def _concept_ids() -> frozenset[str]:
    return frozenset(ontology_mod.default().concepts)


def decide(conn, claim_candidate_id: str, decision: str, decided_by: str, *,
           reason_code: str | None = None,
           corrected_predicate: str | None = None,
           corrected_object_concept_id: str | None = None,
           corrected_object_literal: str | None = None,
           corrected_subject_mention_id: str | None = None,
           review_queue_id: int | None = None,
           note: str | None = None, commit: bool = True) -> dict:
    """Record one decision on `claim_candidate_id`. Returns the decision row's
    id and the candidate's new status.

    `decision`:
      * ``approved``  -- the triple is right as extracted.
      * ``rejected``  -- the triple is wrong and not salvageable.
      * ``corrected`` -- the triple is about something real but the machine
        got the predicate / object / subject wrong; at least one
        ``corrected_*`` field must be supplied.

    `commit` defaults to True -- one decision, one transaction, as the CLI and
    web callers want. `review_batch.apply_sheet` passes ``commit=False`` for a
    ``--dry-run``, running every row's validation and writes in one transaction
    it then rolls back.
    """
    decided_by = (decided_by or "").strip()
    if not decided_by:
        raise ClaimDecisionError("decided_by is required and is never defaulted.")
    if decision not in DECISIONS:
        raise ClaimDecisionError(f"decision must be one of {', '.join(DECISIONS)}.")

    candidate = conn.execute(
        "SELECT claim_candidate_id, status FROM document_claim_candidates "
        "WHERE claim_candidate_id = ? AND superseded = 0", (claim_candidate_id,)).fetchone()
    if candidate is None:
        raise ClaimDecisionError(f"no live claim candidate {claim_candidate_id!r}.")

    corrections = {
        "corrected_predicate": corrected_predicate,
        "corrected_object_concept_id": corrected_object_concept_id,
        "corrected_object_literal": corrected_object_literal,
        "corrected_subject_mention_id": corrected_subject_mention_id,
    }
    supplied = {k: v for k, v in corrections.items() if v}
    if decision == "corrected" and not supplied:
        raise ClaimDecisionError(
            "a 'corrected' decision needs at least one corrected_* value.")
    if decision != "corrected" and supplied:
        raise ClaimDecisionError(
            "corrected_* values only make sense with decision='corrected'.")
    if corrected_predicate and corrected_predicate not in _relation_ids():
        raise ClaimDecisionError(
            f"corrected_predicate {corrected_predicate!r} is not a relations.yml id.")
    if corrected_object_concept_id and corrected_object_concept_id not in _concept_ids():
        raise ClaimDecisionError(
            f"corrected_object_concept_id {corrected_object_concept_id!r} is not a concept id.")
    if corrected_subject_mention_id and conn.execute(
            "SELECT 1 FROM document_concept_mentions WHERE document_concept_mention_id = ?",
            (corrected_subject_mention_id,)).fetchone() is None:
        raise ClaimDecisionError(
            f"corrected_subject_mention_id {corrected_subject_mention_id!r} does not exist.")

    now = utcnow()
    # RETURNING, not cursor.lastrowid -- the latter is a sqlite3-ism and is
    # absent on the psycopg cursor the PostgreSQL wrapper hands back.
    decision_id = conn.execute(
        "INSERT INTO claim_candidate_decisions (claim_candidate_id, review_queue_id, decision, "
        "decided_by, reason_code, corrected_subject_mention_id, corrected_predicate, "
        "corrected_object_concept_id, corrected_object_literal, graph_claim_id, note, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?) RETURNING id",
        (claim_candidate_id, review_queue_id, decision, decided_by, reason_code,
         corrected_subject_mention_id, corrected_predicate, corrected_object_concept_id,
         corrected_object_literal, note, now)).fetchone()[0]
    new_status = _STATUS_AFTER[decision]
    conn.execute(
        "UPDATE document_claim_candidates SET status = ? WHERE claim_candidate_id = ?",
        (new_status, claim_candidate_id))
    if commit:
        conn.commit()
    return {"decision_id": decision_id, "claim_candidate_id": claim_candidate_id,
            "decision": decision, "status": new_status, "decided_at": now}


def history(conn, claim_candidate_id: str) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM claim_candidate_decisions WHERE claim_candidate_id = ? "
        "ORDER BY decided_at", (claim_candidate_id,)).fetchall()]


def training_export(conn) -> list[dict]:
    """Every decided candidate with the reviewer's verdict and correction,
    joined to its triple -- the shape 034G reads. Read-only."""
    rows = conn.execute(
        "SELECT c.claim_candidate_id, c.predicate, c.object_concept_id, c.object_literal, "
        "c.assertion_status, c.relation_score, c.evidence_span, c.subject_mention_id, "
        "d.decision, d.reason_code, d.corrected_predicate, d.corrected_object_concept_id, "
        "d.corrected_object_literal, d.corrected_subject_mention_id, d.decided_at "
        "FROM document_claim_candidates c "
        "JOIN claim_candidate_decisions d ON d.claim_candidate_id = c.claim_candidate_id "
        "ORDER BY d.decided_at").fetchall()
    return [dict(row) for row in rows]
