"""pipeline/nlp/relations.py — machine claim-candidate assembly."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import ontology as ontology_mod
from pipeline.nlp import relations, spans
from pipeline.nlp.relations import _SentenceSpan, assemble


def _seed_version(conn, settings, elements, *, evidence_id="ev-rel",
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


def _pipeline(conn, settings, elements, **kw):
    _seed_version(conn, settings, elements, **kw)
    nlp_chunk.run(conn)
    spans.run(conn, extractor="stub")
    nlp_context.run(conn)


# --- assemble(): pure ---------------------------------------------------

def test_concept_to_predicate_needs_a_subject_and_the_phrase():
    onto = ontology_mod.default()
    s = "Change Grow Live is struggling to recruit recovery workers this year."
    i = s.index("Change Grow Live")
    spans_in = [
        _SentenceSpan("m-prov", "PROVIDER", None, i, i + 16, "AFFIRMED", 0.6),
        _SentenceSpan("m-role", "ROLE", "role.recovery_worker",
                      s.index("recovery workers"), s.index("recovery workers") + 16, "AFFIRMED", 0.6),
    ]
    triples = assemble(onto, s, spans_in)
    # the subject entity for a workforce claim is the ORGANISATION (the
    # provider span), not the ROLE span.
    assert any(t.predicate == "workforce.has_recruitment_pressure"
               and t.subject_mention_id == "m-prov" and t.assertion_status == "AFFIRMED"
               for t in triples)


def test_co_occurrence_without_a_trigger_yields_nothing():
    onto = ontology_mod.default()
    # a provider and a treatment in one sentence, but no pressure concept or
    # predicate pattern -> not a claim.
    s = "Change Grow Live provides opioid substitution treatment."
    i = s.index("Change Grow Live")
    spans_in = [
        _SentenceSpan("m1", "PROVIDER", None, i, i + 16, "AFFIRMED", 0.6),
        _SentenceSpan("m2", "TREATMENT", "treatment.ost",
                      s.index("opioid substitution treatment"),
                      s.index("opioid substitution treatment") + 29, "AFFIRMED", 0.6),
    ]
    assert assemble(onto, s, spans_in) == []


def test_negated_funding_reduction_is_kept_without_a_figure():
    onto = ontology_mod.default()
    s = "No funding reduction was applied to the service this year."
    spans_in = [_SentenceSpan("m-svc", "SERVICE", "service.adult_treatment",
                              s.index("the service") + 4, s.index("the service") + 11,
                              "NEGATED", 0.85)]
    triples = assemble(onto, s, spans_in)
    funding = [t for t in triples if t.predicate == "finance.has_funding_reduction"]
    assert funding and funding[0].assertion_status == "NEGATED"
    assert funding[0].object_literal is None


def test_anaphor_stands_in_for_a_missing_subject_span():
    onto = ontology_mod.default()
    s = "The service is struggling to recruit and retain drug and alcohol workers."
    assert any(t.subject_hint and t.predicate == "workforce.has_recruitment_pressure"
               for t in assemble(onto, s, []))


def _preds(s):
    onto = ontology_mod.default()
    return {t.predicate for t in assemble(onto, s, [])}


def test_gate_predicates_fire_only_on_an_affirming_construction():
    # D-08: the five removed from CONCEPT_PREDICATE now need a real predication.
    # Sentences carry an anaphor ("the service" / "staff") so assemble() finds
    # a subject.
    assert "workforce.relies_on_agency" in _preds(
        "The service is heavily reliant on locum staff to cover shifts.")
    assert "workforce.relies_on_agency" in _preds(
        "Agency staff were relied upon by the team to fill rota gaps overnight.")
    assert "workforce.has_vacancy_pressure" in _preds(
        "The service has a high vacancy rate across the establishment.")
    assert "workforce.undergoes_tupe" in _preds(
        "Staff will transfer under TUPE to the new provider.")
    assert "finance.has_cost_pressure" in _preds(
        "The service is facing significant cost pressures this year.")
    assert "service.reports_waiting_time" in _preds(
        "The service reports that the waiting time is now 8 weeks for treatment.")


def test_gate_predicates_do_not_fire_on_topic_mentions():
    for s in (
        "There was no plan in place to reduce the number of agency staff.",
        "Progress was being made to reduce the level of agency staff.",
        "The committee noted a statement from UNISON regarding agency staff.",
        "Scrutiny proposal: a review of the council's spend on temporary and agency staff.",
        "How would agency staff performance and value for money be evaluated?",
        "The data included a three-year profile around agency staff and vacancy rates.",
    ):
        assert _preds(s) == set() or "workforce.relies_on_agency" not in _preds(s), s


# --- run(): end to end -----------------------------------------------

_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Change Grow Live is struggling to recruit recovery "
                  "workers, and there was a public health grant reduction of £900,000.",
                  parent_sequence=1, page_number=1),
]


def test_run_writes_candidates_with_a_run_row(conn, settings):
    _pipeline(conn, settings, _ELEMENTS)
    result = relations.run(conn, source_system="committee_paper_promotion")
    assert result["candidates"] >= 1

    run_row = conn.execute("SELECT stage, status, ontology_version FROM nlp_runs WHERE run_id=?",
                           (result["run_id"],)).fetchone()
    assert run_row["stage"] == "relations" and run_row["status"] == "ok"
    assert run_row["ontology_version"] == ontology_mod.default().version

    rows = conn.execute(
        "SELECT predicate, assertion_status, relation_score, object_literal, status, evidence_span "
        "FROM document_claim_candidates ORDER BY predicate").fetchall()
    preds = {r["predicate"] for r in rows}
    assert "workforce.has_recruitment_pressure" in preds
    assert "finance.has_funding_reduction" in preds
    assert all(r["status"] == "new" for r in rows)
    assert all(0.0 <= r["relation_score"] <= 1.0 for r in rows)
    funding = next(r for r in rows if r["predicate"] == "finance.has_funding_reduction")
    assert "900,000" in (funding["object_literal"] or "")


def test_run_is_idempotent(conn, settings):
    _pipeline(conn, settings, _ELEMENTS)
    first = relations.run(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM document_claim_candidates").fetchone()[0]
    again = relations.run(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM document_claim_candidates").fetchone()[0]
    assert first["candidates"] == again["candidates"] and n1 == n2


def test_dry_run_writes_nothing(conn, settings):
    _pipeline(conn, settings, _ELEMENTS)
    result = relations.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_claim_candidates").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='relations'").fetchone()[0] == 0
