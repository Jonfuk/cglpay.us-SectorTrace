"""pipeline/nlp/promote.py — the candidate -> review_queue selection policy."""
from __future__ import annotations

import json

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import promote, relations, resolve, spans


def _seed_version(conn, settings, elements, *, evidence_id="ev-promote",
                  source_system="committee_paper_promotion"):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-27T00:00:00+00:00", http_status=200,
        payload_sha256=(evidence_id * 64)[:64],
        raw_object_path=f"data/raw/{source_system}/{(evidence_id * 64)[:64]}.pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf",
        "application/pdf", 3, "Paper")
    parsed = ParsedDocument("fixture", "1", elements)
    return repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


def _seed_entity(conn, entity_id, entity_type, name):
    from pipeline.graph.backfill import _normalise
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, canonical_name_normalized, "
        "status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (entity_id, entity_type, name, _normalise(name),
         "2026-08-27T00:00:00+00:00", "2026-08-27T00:00:00+00:00"))


_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Change Grow Live is struggling to recruit recovery "
                  "workers across the drug and alcohol service.", parent_sequence=1, page_number=1),
]


def _run_to_candidates(conn, settings, elements=_ELEMENTS, **kw):
    _seed_version(conn, settings, elements, **kw)
    _seed_entity(conn, "provider:change_grow_live", "PROVIDER", "Change Grow Live")
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)


def test_a_primary_candidate_is_queued_with_full_context(conn, settings):
    _run_to_candidates(conn, settings)
    result = promote.run(conn, source_system="committee_paper_promotion")
    assert result["queued"] >= 1
    assert "primary" in result["by_reason"]

    run_row = conn.execute("SELECT stage, status FROM nlp_runs WHERE run_id=?",
                           (result["run_id"],)).fetchone()
    assert run_row["stage"] == "queue" and run_row["status"] == "ok"

    item = conn.execute(
        "SELECT raw_value, item_type, context_json, status FROM review_queue "
        "WHERE item_type='semantic_claim_candidate'").fetchone()
    assert item["status"] == "pending"
    ctx = json.loads(item["context_json"])
    assert ctx["predicate"] == "workforce.has_recruitment_pressure"
    assert ctx["subject_entity_id"] == "provider:change_grow_live"
    assert ctx["assertion_status"] == "AFFIRMED"
    assert ctx["source_url"] == "https://example.test/ev-promote"
    assert ctx["payload_sha256"] and ctx["sentence"] and ctx["selection_reason"] == "primary"

    # the candidate is marked queued
    assert conn.execute(
        "SELECT status FROM document_claim_candidates WHERE claim_candidate_id=?",
        (ctx["candidate_id"],)).fetchone()["status"] == "queued"


def test_a_candidate_whose_subject_does_not_resolve_is_not_primary(conn, settings):
    # no entity seeded -> the provider span never resolves -> not 'primary'
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)
    result = promote.run(conn)
    assert "primary" not in result.get("by_reason", {})


def test_a_negated_claim_is_not_queued_as_primary(conn, settings):
    elements = [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Change Grow Live reports no recruitment "
                      "difficulties in the drug and alcohol service this year.",
                      parent_sequence=1, page_number=1),
    ]
    _run_to_candidates(conn, settings, elements)
    result = promote.run(conn)
    # a NEGATED recruitment-pressure candidate exists but is not 'primary'
    negated = conn.execute(
        "SELECT COUNT(*) FROM document_claim_candidates WHERE assertion_status='NEGATED'"
    ).fetchone()[0]
    assert negated >= 1
    assert "primary" not in result.get("by_reason", {})


def test_run_is_idempotent(conn, settings):
    _run_to_candidates(conn, settings)
    promote.run(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
    promote.run(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0]
    assert n1 == n2


def test_dry_run_writes_nothing(conn, settings):
    _run_to_candidates(conn, settings)
    result = promote.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM review_queue WHERE item_type='semantic_claim_candidate'"
    ).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='queue'").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM document_claim_candidates WHERE status='queued'").fetchone()[0] == 0
