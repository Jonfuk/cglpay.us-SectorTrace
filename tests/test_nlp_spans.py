"""pipeline/nlp/spans.py — span-level entity extraction into document_concept_mentions."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import spans


def _seed_version(conn, settings, elements, *, evidence_id="ev-spans",
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


_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Treatment", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Change Grow Live delivers opioid substitution treatment "
                  "and needle exchange for the adult treatment service.",
                  parent_sequence=1, page_number=1),
    ParsedElement("PARAGRAPH", 3, text="Recovery workers report high caseloads; methadone "
                  "prescribing continues.", page_number=2),
]


# --- the stub extractor: pure ------------------------------------------------

def test_stub_extracts_dictionary_backed_labels_with_offsets():
    ex = spans.get_extractor("stub")
    text = "Change Grow Live delivers opioid substitution treatment."
    found = {(s.label, s.text): s for s in ex.extract(text)}
    assert ("PROVIDER", "Change Grow Live") in found
    assert ("TREATMENT", "opioid substitution treatment") in found
    provider = found[("PROVIDER", "Change Grow Live")]
    assert text[provider.char_start:provider.char_end] == "Change Grow Live"
    assert found[("TREATMENT", "opioid substitution treatment")].concept_id == "treatment.ost"
    assert found[("PROVIDER", "Change Grow Live")].concept_id is None


def test_stub_does_not_emit_abstract_or_unmapped_labels():
    ex = spans.get_extractor("stub")
    labels = {s.label for s in ex.extract(
        "recruitment difficulties and funding reduction and high caseloads")}
    assert labels == set()  # those are 034C's job, never a span label


def test_stub_skips_unsafe_bare_provider_variants():
    ex = spans.get_extractor("stub")
    # "Via" and "CGL" and "Inclusion" are on the unsafe list; the spelled-out
    # forms still match.
    hits = {(s.label, s.text.lower()) for s in ex.extract(
        "the report was sent via CGL to Inclusion")}
    assert ("PROVIDER", "cgl") not in hits
    assert ("PROVIDER", "via") not in hits


# --- run(): end to end -----------------------------------------------------

def test_run_writes_concept_mentions_with_element_offsets(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = spans.run(conn, extractor="stub", source_system="committee_paper_promotion")
    assert result["mentions"] >= 4
    assert result["extractor"] == "ontology-stub"

    run_row = conn.execute("SELECT stage, status, rows_written FROM nlp_runs WHERE run_id=?",
                           (result["run_id"],)).fetchone()
    assert run_row["stage"] == "spans" and run_row["status"] == "ok"
    assert run_row["rows_written"] == result["mentions"]

    rows = conn.execute(
        "SELECT label, concept_id, span_text, char_start, char_end, element_char_start, "
        "element_char_end, document_element_id, extraction_score, superseded "
        "FROM document_concept_mentions ORDER BY char_start").fetchall()
    assert rows and all(r["superseded"] == 0 for r in rows)
    assert {r["label"] for r in rows} >= {"PROVIDER", "TREATMENT", "SUBSTANCE", "ROLE"}
    assert all(r["extraction_score"] == 1.0 for r in rows)
    # never carries entity_id — this table has no such column
    assert "entity_id" not in {d[0] for d in conn.execute(
        "SELECT * FROM document_concept_mentions LIMIT 1").description}

    # element offsets land inside the right element's text
    for row in rows:
        element_text = conn.execute(
            "SELECT text FROM document_elements WHERE document_element_id=?",
            (row["document_element_id"],)).fetchone()["text"]
        assert element_text[row["element_char_start"]:row["element_char_end"]] == row["span_text"]


def test_run_is_idempotent(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    first = spans.run(conn, extractor="stub")
    n1 = conn.execute("SELECT COUNT(*) FROM document_concept_mentions").fetchone()[0]
    again = spans.run(conn, extractor="stub")
    n2 = conn.execute("SELECT COUNT(*) FROM document_concept_mentions").fetchone()[0]
    assert first["mentions"] == again["mentions"] and n1 == n2


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = spans.run(conn, extractor="stub", dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_concept_mentions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='spans'").fetchone()[0] == 0


def test_superseded_chunks_are_not_processed(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    conn.execute("UPDATE document_chunks SET superseded=1 WHERE document_version_id=?", (version_id,))
    result = spans.run(conn, extractor="stub")
    assert result["chunks"] == 0 and result["mentions"] == 0
