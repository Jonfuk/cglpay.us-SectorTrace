from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement


def reference() -> EvidenceReference:
    return EvidenceReference(
        evidence_id="evidence-test", source_system="fixture", source_url="https://example.test/document",
        retrieved_at="2026-08-19T00:00:00+00:00", http_status=200, payload_sha256="a" * 64,
        raw_object_path="data/raw/fixture/" + "a" * 64 + ".pdf", mime_type="application/pdf",
    )


def test_canonical_parse_keeps_page_provenance_and_is_searchable(conn, settings):
    source = reference()
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "report.pdf", "application/pdf", 2, "Report")
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="Recruitment vacancies are increasing.", parent_sequence=1,
                      page_number=1),
        ParsedElement("PARAGRAPH", 3, text="Budget pressure continues.", page_number=2),
    ])
    version_id = repository.persist_parse(
        conn, document_id, parsed, "config", None, "GOOD", {"total_characters": 72}, [], settings)

    element = conn.execute(
        "SELECT parent_element_id, page_number FROM document_elements WHERE document_version_id=? AND sequence=2",
        (version_id,)).fetchone()
    assert element["parent_element_id"]
    assert element["page_number"] == 1
    assert repository.search(conn, settings, "recruitment") == [
        {
            "document_element_id": repository.stable_id("document-element", f"{version_id}|2"),
            "document_id": document_id,
            "page_number": 1,
            "element_type": "PARAGRAPH",
            "text": "Recruitment vacancies are increasing.",
            "evidence_id": "evidence-test",
            "source_url": "https://example.test/document",
        }
    ]
    assert conn.execute("SELECT match_count FROM document_topics WHERE topic='WORKFORCE'").fetchone()[0] == 2


def test_same_parser_configuration_is_idempotent(conn, settings):
    source = reference()
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "UNKNOWN", "fixture", 0.0, "report.pdf", "application/pdf", 1)
    parsed = ParsedDocument("fixture", "1", [ParsedElement("PARAGRAPH", 1, text="one", page_number=1)])
    first = repository.persist_parse(conn, document_id, parsed, "config", None, "GOOD", {}, [], settings)
    second = repository.persist_parse(conn, document_id, parsed, "config", None, "GOOD", {}, [], settings)
    assert first == second
    assert conn.execute("SELECT COUNT(*) FROM document_versions").fetchone()[0] == 1
