"""pipeline/nlp/gate.py — the 034G readiness report."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import decisions, gate, relations, resolve, spans


def _seed_entity(conn, entity_id, name):
    from pipeline.graph.backfill import _normalise
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, canonical_name_normalized, "
        "status, created_at, updated_at) VALUES (?, 'PROVIDER', ?, ?, 'active', ?, ?) "
        "ON CONFLICT(entity_id) DO NOTHING",
        (entity_id, name, _normalise(name), "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"))


def _doc(conn, settings, evidence_id, source_system, provider_name, published_year):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-27T00:00:00+00:00", http_status=200,
        payload_sha256=(evidence_id * 64)[:64],
        raw_object_path=f"data/raw/{source_system}/{(evidence_id * 64)[:64]}.pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf", "application/pdf", 3, "Paper")
    conn.execute("UPDATE document_records SET published_at = ? WHERE document_id = ?",
                 (f"{published_year}-06-01", document_id))
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Finance", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text=f"{provider_name} had a public health grant "
                      "reduction of £900,000 this year.",
                      parent_sequence=1, page_number=1),
    ])
    repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


def _funding_candidate(conn, evidence_id):
    return conn.execute(
        "SELECT c.claim_candidate_id FROM document_claim_candidates c "
        "JOIN document_chunks dc ON dc.document_chunk_id = c.document_chunk_id "
        "JOIN document_versions v ON v.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE c.predicate = 'finance.has_funding_reduction' AND e.evidence_id = ?",
        (evidence_id,)).fetchone()


def test_empty_warehouse_reports_not_ready_with_no_examples(conn, settings):
    report = gate.check(conn)
    assert report["ready"] is False
    assert report["n_decisions"] == 0
    rec = report["categories"]["funding_reduction"]
    assert rec["positive"] == 0 and rec["negative"] == 0
    assert any("positives 0" in s for s in rec["shortfalls"])


def test_counts_positives_negatives_and_diversity(conn, settings):
    _seed_entity(conn, "provider:change_grow_live", "Change Grow Live")
    _seed_entity(conn, "provider:turning_point", "Turning Point")
    specs = [
        ("eva", "committee_paper_promotion", "Change Grow Live", 2021),
        ("evb", "committee_paper_promotion", "Turning Point", 2022),
        ("evc", "cdp_document_promotion", "Change Grow Live", 2023),
    ]
    for evidence_id, system, provider, year in specs:
        _doc(conn, settings, evidence_id, system, provider, year)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)

    ca = _funding_candidate(conn, "eva")
    cb = _funding_candidate(conn, "evb")
    cc = _funding_candidate(conn, "evc")
    assert ca and cb and cc
    decisions.decide(conn, ca["claim_candidate_id"], "approved", "Reviewer A")
    decisions.decide(conn, cb["claim_candidate_id"], "approved", "Reviewer A")
    decisions.decide(conn, cc["claim_candidate_id"], "rejected", "Reviewer A",
                     reason_code="not-this-provider")

    report = gate.check(conn, min_per_class=1, heldout_per_class=0,
                        min_authorities=1, min_subjects=1, min_years=1,
                        min_double_reviewed=1)
    rec = report["categories"]["funding_reduction"]
    assert rec["positive"] == 2 and rec["negative"] == 1
    # source_systems stays in the report (informational); the blocking spread
    # check is now distinct authorities.
    assert set(rec["source_systems"]) == {"committee_paper_promotion", "cdp_document_promotion"}
    assert "distinct_authorities" in rec
    assert rec["distinct_subjects"] == 2
    assert set(rec["years"]) == {"2021", "2022", "2023"}
    # still not ready: the other five categories have no examples, and no
    # double-reviewed items.
    assert report["ready"] is False
    assert any("cost_pressure" in b for b in report["blocking"])
    assert report["inter_reviewer"]["double_reviewed"] == 0


def test_corrected_decision_moves_the_example_between_categories(conn, settings):
    _seed_entity(conn, "provider:change_grow_live", "Change Grow Live")
    _doc(conn, settings, "evx", "committee_paper_promotion", "Change Grow Live", 2022)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)
    cand = _funding_candidate(conn, "evx")
    decisions.decide(conn, cand["claim_candidate_id"], "corrected", "Reviewer A",
                     corrected_predicate="finance.has_savings_target")

    report = gate.check(conn, min_per_class=1, heldout_per_class=0)
    # negative for funding_reduction (corrected away)…
    assert report["categories"]["funding_reduction"]["negative"] == 1
    assert report["categories"]["funding_reduction"]["positive"] == 0
    # savings_target is not one of the gate categories, so it does not
    # appear — the correction still counts as a funding_reduction negative.
    assert "savings_target" not in report["categories"]


def test_quorum_lets_ready_categories_through_with_laggards_advisory(conn, settings):
    _seed_entity(conn, "provider:change_grow_live", "Change Grow Live")
    _seed_entity(conn, "provider:turning_point", "Turning Point")
    for eid, sysname, prov, yr in [
        ("qa", "committee_paper_promotion", "Change Grow Live", 2021),
        ("qb", "cdp_document_promotion", "Turning Point", 2022),
    ]:
        _doc(conn, settings, eid, sysname, prov, yr)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)
    pos = _funding_candidate(conn, "qa")["claim_candidate_id"]
    neg = _funding_candidate(conn, "qb")["claim_candidate_id"]
    decisions.decide(conn, pos, "approved", "Reviewer A")
    decisions.decide(conn, pos, "approved", "Reviewer B")   # double-reviewed, agree
    decisions.decide(conn, neg, "rejected", "Reviewer A", reason_code="wrong-provider")

    report = gate.check(conn, min_per_class=1, heldout_per_class=0,
                        min_authorities=1, min_subjects=1, min_years=1,
                        min_double_reviewed=1, min_categories_ready=1)
    assert report["categories"]["funding_reduction"]["ready"] is True
    assert report["categories_ready"] == 1
    assert report["ready"] is True                 # quorum of 1 met, reviewers agree
    # the five empty categories are corpus-limited, not blocking
    assert report["blocking"] == []
    assert any("cost_pressure" in a for a in report["advisory"])
    assert any("1/6 categories ready" in a for a in report["advisory"])


def test_inter_reviewer_agreement_is_reported(conn, settings):
    _seed_entity(conn, "provider:change_grow_live", "Change Grow Live")
    _doc(conn, settings, "evy", "committee_paper_promotion", "Change Grow Live", 2022)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)
    cand = _funding_candidate(conn, "evy")["claim_candidate_id"]
    decisions.decide(conn, cand, "approved", "Reviewer A")
    decisions.decide(conn, cand, "rejected", "Reviewer B")

    report = gate.check(conn, min_double_reviewed=1)
    assert report["inter_reviewer"]["double_reviewed"] == 1
    assert report["inter_reviewer"]["agreement"] == 0.0
    assert report["inter_reviewer"]["assessed"] is True
    assert any("agreement 0.0" in b for b in report["blocking"])


def test_min_double_reviewed_zero_makes_the_reviewer_check_advisory(conn, settings):
    _seed_entity(conn, "provider:change_grow_live", "Change Grow Live")
    _seed_entity(conn, "provider:turning_point", "Turning Point")
    for eid, sysname, prov, yr in [
        ("za", "committee_paper_promotion", "Change Grow Live", 2021),
        ("zb", "cdp_document_promotion", "Turning Point", 2022),
    ]:
        _doc(conn, settings, eid, sysname, prov, yr)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)
    resolve.run(conn)
    relations.run(conn)
    pos = _funding_candidate(conn, "za")["claim_candidate_id"]
    neg = _funding_candidate(conn, "zb")["claim_candidate_id"]
    decisions.decide(conn, pos, "approved", "Sole Reviewer")     # one person only
    decisions.decide(conn, neg, "rejected", "Sole Reviewer", reason_code="x")

    report = gate.check(conn, min_per_class=1, heldout_per_class=0,
                        min_authorities=1, min_subjects=1, min_years=1,
                        min_double_reviewed=0, min_categories_ready=1)
    assert report["ready"] is True                              # not gated on a 2nd reviewer
    assert not any("inter-reviewer" in b for b in report["blocking"])
    assert any("single-reviewer corpus (accepted)" in a for a in report["advisory"])
