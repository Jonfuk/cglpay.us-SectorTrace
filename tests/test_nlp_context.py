"""pipeline/nlp/context.py — assertion / context detection."""
from __future__ import annotations

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import context as nlp_context
from pipeline.nlp import context_eval, spans


def _seed_version(conn, settings, elements, *, evidence_id="ev-context",
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


# --- the cue tagger: pure -------------------------------------------------

@pytest.mark.parametrize("sentence,target,expected", [
    ("No staffing concerns were identified.", "staffing concerns", "NEGATED"),
    ("Recruitment difficulties had resolved.", "Recruitment difficulties", "HISTORICAL"),
    ("The report does not relate to the commissioned provider.", "commissioned provider", "NEGATED"),
    ("Other authorities experienced vacancy pressure.", "vacancy pressure", "THIRD_PARTY"),
    ("The council considered, but did not implement, a funding reduction.", "funding reduction", "NEGATED"),
    ("Recruitment difficulties remain a significant challenge.", "Recruitment difficulties", "AFFIRMED"),
    ("If the grant is reduced, waiting times will rise.", "waiting times", "CONDITIONAL"),
    ("The provider proposed a residential rehabilitation unit.", "residential rehabilitation", "HYPOTHETICAL"),
])
def test_cue_tagger_classifies(sentence, target, expected):
    tagger = nlp_context.CueTagger()
    i = sentence.lower().index(target.lower())
    assert tagger.tag(sentence, i, i + len(target)).status == expected


def test_termination_word_breaks_a_far_cue():
    tagger = nlp_context.CueTagger()
    # "no" is negation, but "; recruitment difficulties" is a fresh clause.
    s = "There were no issues with finance; recruitment difficulties remain acute."
    i = s.index("recruitment difficulties")
    assert tagger.tag(s, i, i + len("recruitment difficulties")).status == "AFFIRMED"


def test_affirmed_has_a_modest_confidence_and_no_cue():
    tagger = nlp_context.CueTagger()
    s = "The team carries high caseloads."
    i = s.index("high caseloads")
    result = tagger.tag(s, i, i + len("high caseloads"))
    assert result.status == "AFFIRMED"
    assert result.cue_text is None
    assert 0.0 < result.confidence < 0.75


def test_sentence_for_locates_the_right_sentence():
    text = "Finance is fine. Recruitment difficulties remain. Estates were discussed."
    located = nlp_context.sentence_for(text, text.index("Recruitment"),
                                       text.index("Recruitment") + len("Recruitment difficulties"))
    assert located is not None
    sentence, start, end = located
    assert sentence.startswith("Recruitment difficulties")
    assert sentence[start:end] == "Recruitment difficulties"


# --- the stage: end to end --------------------------------------------

_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Treatment", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="The service does not provide opioid substitution "
                  "treatment. Change Grow Live runs the needle exchange.",
                  parent_sequence=1, page_number=1),
    ParsedElement("PARAGRAPH", 3, text="Other authorities reported that their recovery workers "
                  "were under pressure.", page_number=2),
]


def test_run_writes_one_assertion_per_span(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    spans.run(conn, extractor="stub", source_system="committee_paper_promotion")
    result = nlp_context.run(conn, source_system="committee_paper_promotion")

    n_spans = conn.execute(
        "SELECT COUNT(*) FROM document_concept_mentions WHERE superseded=0").fetchone().values().__iter__().__next__()
    assert result["assertions"] == n_spans >= 3

    run_row = conn.execute("SELECT stage, status FROM nlp_runs WHERE run_id=%s",
                           (result["run_id"],)).fetchone()
    assert run_row["stage"] == "context" and run_row["status"] == "ok"

    rows = {r["span_text"]: r for r in conn.execute(
        "SELECT m.span_text, a.assertion_status, a.cue_text, a.sentence_sha256 "
        "FROM document_assertions a "
        "JOIN document_concept_mentions m ON m.document_concept_mention_id = a.concept_mention_id")}
    # "opioid substitution treatment" sits in "does not provide ..."
    assert rows["opioid substitution treatment"]["assertion_status"] == "NEGATED"
    # "needle exchange" is in the next, plain sentence
    assert rows["needle exchange"]["assertion_status"] == "AFFIRMED"
    # the recovery workers span is in the "Other authorities ..." sentence
    assert rows["recovery workers"]["assertion_status"] == "THIRD_PARTY"
    assert all(r["sentence_sha256"] for r in rows.values())


def test_run_is_idempotent(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    spans.run(conn, extractor="stub")
    first = nlp_context.run(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM document_assertions").fetchone().values().__iter__().__next__()
    again = nlp_context.run(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM document_assertions").fetchone().values().__iter__().__next__()
    assert first["assertions"] == again["assertions"] and n1 == n2


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    spans.run(conn, extractor="stub")
    result = nlp_context.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_assertions").fetchone().values().__iter__().__next__() == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='context'").fetchone().values().__iter__().__next__() == 0


def test_a_chunk_with_no_spans_is_skipped(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    # no spans.run — nothing to classify
    result = nlp_context.run(conn)
    assert result["chunks"] == 0 and result["assertions"] == 0


# --- the eval harness ------------------------------------------------

def test_committed_case_set_passes_and_covers_the_hard_negatives():
    report = context_eval.run()
    assert report["n_cases"] >= 10
    assert report["hard_negatives"]["total"] == 5
    assert report["hard_negatives"]["failed"] == []
    assert report["accuracy"] >= 0.9


def test_eval_flags_a_wrong_expectation(tmp_path):
    import json
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [
        {"id": "wrong", "text": "The team carries high caseloads.",
         "target": "high caseloads", "expected": "NEGATED"},
    ]}), encoding="utf-8")
    report = context_eval.run(cases_path=path)
    assert report["accuracy"] == 0.0
    assert report["per_case"][0]["predicted"] == "AFFIRMED"
