"""pipeline/nlp/label.py — deterministic ontology labelling into document_topics."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import label as nlp_label
from pipeline.nlp import ontology as ontology_mod


def _seed_version(conn, settings, elements, *, evidence_id="ev-label",
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
    ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="The service is struggling to recruit recovery workers "
                  "and relies on agency staff, with high caseloads across every team.",
                  parent_sequence=1, page_number=1),
    ParsedElement("PARAGRAPH", 3, text="Methadone and buprenorphine prescribing continues "
                  "despite a further public health grant reduction this year.", page_number=2),
]


# --- label_text: pure --------------------------------------------------------

def test_label_text_emits_concept_and_category_rows():
    onto = ontology_mod.default()
    topics = nlp_label.label_text(
        onto, "struggling to recruit recovery workers with high caseloads")
    assert topics["workforce.recruitment_difficulty"] == 1
    assert topics["role.recovery_worker"] == 1
    assert topics["workforce.caseload"] == 1
    # category rollup: two workforce concepts + one role concept
    assert topics["cat:workforce"] == 2
    assert topics["cat:pressure"] == 2
    assert topics["cat:role"] == 1


def test_label_text_is_empty_when_nothing_matches():
    assert nlp_label.label_text(ontology_mod.default(), "the minutes were agreed") == {}


# --- run(): end to end -----------------------------------------------------

def test_run_writes_ontology_rows_and_leaves_keyword_rows_alone(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    # parse-time keyword_v1 rows exist already
    keyword_before = conn.execute(
        "SELECT document_element_id, topic, match_count FROM document_topics "
        "WHERE match_method='keyword_v1' ORDER BY topic").fetchall()
    assert keyword_before

    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = nlp_label.run(conn, source_system="committee_paper_promotion")
    assert result["versions"] == 1 and result["rows"] >= 3
    assert result["ontology_version"] == ontology_mod.default().version

    run_row = conn.execute("SELECT stage, status, ontology_version, rows_written FROM nlp_runs "
                           "WHERE run_id=?", (result["run_id"],)).fetchone()
    assert run_row["stage"] == "label" and run_row["status"] == "ok"
    assert run_row["ontology_version"] == ontology_mod.default().version
    assert run_row["rows_written"] == result["rows"]

    topics = {(r["topic"]) for r in conn.execute(
        "SELECT topic FROM document_topics WHERE match_method='ontology_v1' "
        "AND document_element_id IN (SELECT document_element_id FROM document_elements "
        "WHERE document_version_id=?)", (version_id,)).fetchall()}
    assert "workforce.recruitment_difficulty" in topics
    assert "role.recovery_worker" in topics
    assert "medication.methadone" in topics
    assert "finance.funding_reduction" in topics
    assert "cat:workforce" in topics and "cat:finance" in topics

    keyword_after = conn.execute(
        "SELECT document_element_id, topic, match_count FROM document_topics "
        "WHERE match_method='keyword_v1' ORDER BY topic").fetchall()
    assert [tuple(r) for r in keyword_after] == [tuple(r) for r in keyword_before]


def test_run_is_idempotent(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    first = nlp_label.run(conn, source_system="committee_paper_promotion")
    count_1 = conn.execute(
        "SELECT COUNT(*) FROM document_topics WHERE match_method='ontology_v1'").fetchone()[0]
    again = nlp_label.run(conn, source_system="committee_paper_promotion")
    count_2 = conn.execute(
        "SELECT COUNT(*) FROM document_topics WHERE match_method='ontology_v1'").fetchone()[0]
    assert first["rows"] == again["rows"]
    assert count_1 == count_2


def test_negated_wording_still_produces_a_provisional_row(conn, settings):
    elements = [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="No recruitment difficulties were identified "
                      "this year.", parent_sequence=1, page_number=1),
    ]
    _seed_version(conn, settings, elements)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    nlp_label.run(conn, source_system="committee_paper_promotion")
    # 034C records the wording; AFFIRMED/NEGATED is 034E's job.
    row = conn.execute(
        "SELECT match_count FROM document_topics WHERE match_method='ontology_v1' "
        "AND topic='workforce.recruitment_difficulty'").fetchone()
    assert row is not None and row["match_count"] == 1


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = nlp_label.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute(
        "SELECT COUNT(*) FROM document_topics WHERE match_method='ontology_v1'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='label'").fetchone()[0] == 0


def test_unchunked_versions_are_not_labelled(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    # no nlp_chunk.run — nothing is chunked
    result = nlp_label.run(conn)
    assert result["versions"] == 0 and result["rows"] == 0


def test_superseded_chunks_are_not_labelled(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    conn.execute("UPDATE document_chunks SET superseded=1 WHERE document_version_id=?", (version_id,))
    result = nlp_label.run(conn)
    assert result["versions"] == 0 and result["rows"] == 0


def test_source_system_filter_scopes_the_run(conn, settings):
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-a",
                  source_system="committee_paper_promotion")
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-b",
                  source_system="cdp_document_promotion")
    nlp_chunk.run(conn)
    result = nlp_label.run(conn, source_system="cdp_document_promotion")
    assert result["versions"] == 1
