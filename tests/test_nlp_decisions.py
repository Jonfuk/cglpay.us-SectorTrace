"""pipeline/nlp/decisions.py — recording a person's decision on a claim candidate."""
from __future__ import annotations

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import decisions, relations, spans


def _seed(conn, settings):
    source = EvidenceReference(
        evidence_id="ev-dec", source_system="committee_paper_promotion",
        source_url="https://example.test/ev-dec", retrieved_at="2026-08-27T00:00:00+00:00",
        http_status=200, payload_sha256="d" * 64,
        raw_object_path="data/raw/committee_paper_promotion/" + "d" * 64 + ".pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf", "application/pdf", 3, "Paper")
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Change Grow Live is struggling to recruit recovery "
                      "workers across the drug and alcohol service.", parent_sequence=1, page_number=1),
    ])
    repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    relations.run(conn)
    return conn.execute(
        "SELECT claim_candidate_id, subject_mention_id FROM document_claim_candidates "
        "WHERE predicate='workforce.has_recruitment_pressure' LIMIT 1").fetchone()


def test_approved_marks_the_candidate_accepted_and_records_a_row(conn, settings):
    cand = _seed(conn, settings)
    result = decisions.decide(conn, cand["claim_candidate_id"], "approved", "Reviewer A")
    assert result["status"] == "accepted"

    row = conn.execute(
        "SELECT decision, decided_by, graph_claim_id FROM claim_candidate_decisions "
        "WHERE claim_candidate_id=%s", (cand["claim_candidate_id"],)).fetchone()
    assert row["decision"] == "approved" and row["decided_by"] == "Reviewer A"
    assert row["graph_claim_id"] is None   # no draft written
    assert conn.execute(
        "SELECT status FROM document_claim_candidates WHERE claim_candidate_id=%s",
        (cand["claim_candidate_id"],)).fetchone()["status"] == "accepted"


def test_rejected_dismisses_the_candidate(conn, settings):
    cand = _seed(conn, settings)
    result = decisions.decide(conn, cand["claim_candidate_id"], "rejected", "Reviewer A",
                              reason_code="wrong-provider")
    assert result["status"] == "dismissed"


def test_corrected_needs_a_correction_and_validates_it(conn, settings):
    cand = _seed(conn, settings)
    with pytest.raises(decisions.ClaimDecisionError):
        decisions.decide(conn, cand["claim_candidate_id"], "corrected", "Reviewer A")
    with pytest.raises(decisions.ClaimDecisionError):
        decisions.decide(conn, cand["claim_candidate_id"], "corrected", "Reviewer A",
                         corrected_predicate="workforce.not_a_real_predicate")

    result = decisions.decide(
        conn, cand["claim_candidate_id"], "corrected", "Reviewer A",
        corrected_predicate="workforce.has_retention_pressure", reason_code="predicate-too-broad")
    assert result["status"] == "accepted"
    row = conn.execute(
        "SELECT corrected_predicate, reason_code FROM claim_candidate_decisions "
        "WHERE claim_candidate_id=%s", (cand["claim_candidate_id"],)).fetchone()
    assert row["corrected_predicate"] == "workforce.has_retention_pressure"


def test_corrections_are_rejected_on_a_non_corrected_decision(conn, settings):
    cand = _seed(conn, settings)
    with pytest.raises(decisions.ClaimDecisionError):
        decisions.decide(conn, cand["claim_candidate_id"], "approved", "Reviewer A",
                         corrected_predicate="workforce.has_retention_pressure")


def test_decided_by_is_required(conn, settings):
    cand = _seed(conn, settings)
    with pytest.raises(decisions.ClaimDecisionError):
        decisions.decide(conn, cand["claim_candidate_id"], "approved", "   ")


def test_unknown_candidate_is_refused(conn, settings):
    _seed(conn, settings)
    with pytest.raises(decisions.ClaimDecisionError):
        decisions.decide(conn, "cc-does-not-exist", "approved", "Reviewer A")


def test_training_export_joins_the_verdict_to_the_triple(conn, settings):
    cand = _seed(conn, settings)
    decisions.decide(conn, cand["claim_candidate_id"], "corrected", "Reviewer A",
                     corrected_predicate="workforce.has_retention_pressure")
    export = decisions.training_export(conn)
    assert len(export) == 1
    assert export[0]["predicate"] == "workforce.has_recruitment_pressure"
    assert export[0]["corrected_predicate"] == "workforce.has_retention_pressure"
    assert export[0]["decision"] == "corrected"
