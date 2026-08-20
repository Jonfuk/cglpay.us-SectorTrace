from __future__ import annotations

import hashlib
import io

from pipeline.archive import FilesystemArchive
from pipeline.cli import _document_candidates
from pipeline.documents import repository
from pipeline.documents.artifacts import DerivedArtifactStore
from pipeline.documents.bridge import register_existing
from pipeline.documents.inspect import ocr_required
from pipeline.documents.models import EvidenceReference, Inspection, ParsedDocument, ParsedElement
from pipeline.documents.parsers import HTMLParserAdapter
from pipeline.documents.quality import assess


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
    assert conn.execute("SELECT match_count FROM document_topics WHERE topic='WORKFORCE'").fetchone()[0] == 1


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


def test_ocr_routing_uses_the_configured_transparent_thresholds(settings):
    low_text = Inspection("application/pdf", 100, "NORMAL", page_count=2,
                          embedded_text_chars=20, pages_with_zero_text=1)
    born_digital = Inspection("application/pdf", 100, "NORMAL", page_count=2,
                              embedded_text_chars=400, pages_with_zero_text=0)
    assert ocr_required(low_text, settings)
    assert not ocr_required(born_digital, settings)


def test_document_candidates_exclude_evidence_without_a_raw_archive_path(conn):
    source = reference()
    repository.upsert_evidence(conn, source)
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, retrieved_at, "
        "payload_sha256, raw_object_path, created_at) VALUES (?, ?, ?, ?, ?, NULL, ?)",
        ("evidence-not-a-document", "find_a_tender", "https://example.test/notice",
         "2026-08-20T00:00:00+00:00", "b" * 64, repository.utcnow()),
    )

    rows = _document_candidates(conn, None, None, None, None, 25, pending_only=True)

    assert [row["evidence_id"] for row in rows] == [source.evidence_id]


def test_quality_marks_empty_parse_as_failed():
    status, metrics, warnings = assess(ParsedDocument("fixture", "1", []), pages_total=2)
    assert status == "FAILED"
    assert metrics["pages_total"] == 2
    assert warnings == ["parser produced no text elements"]


def test_derived_files_are_content_addressed_and_outside_raw_archive(settings):
    path, digest = DerivedArtifactStore(settings).put("fixture", "ocr_pdf", ".pdf", b"derived pdf")
    assert path == f"data/derived/fixture/ocr_pdf/{digest}.pdf"
    assert str(settings.raw_archive_dir) not in path
    assert (settings.derived_archive_dir / "fixture" / "ocr_pdf" / f"{digest}.pdf").read_bytes() == b"derived pdf"


def test_derived_s3_storage_verifies_the_uploaded_hash(settings):
    class FakeS3:
        objects = {}

        def put_object(self, Bucket, Key, Body):
            self.objects[(Bucket, Key)] = Body

        def get_object(self, Bucket, Key):
            return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    configured = settings.model_copy(update={
        "derived_archive_s3_bucket": "derived", "derived_archive_s3_endpoint": "https://s3.example",
        "derived_archive_s3_region": "eu-west-2", "derived_archive_s3_url_style": "path",
        "derived_archive_s3_access_key": "key", "derived_archive_s3_secret": "secret",
    })
    path, digest = DerivedArtifactStore(configured, FakeS3()).put("fixture", "ocr_pdf", ".pdf", b"derived")
    assert path == f"s3://derived/fixture/ocr_pdf/{digest}.pdf"


def test_legacy_bridge_requires_a_real_archived_document(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    body = b"%PDF-legacy"
    digest = hashlib.sha256(body).hexdigest()
    raw_path = archive.put("committee_papers", digest, "application/pdf", body)
    conn.execute(
        "INSERT INTO evidence_promotions (candidate_table, candidate_url, target_table, target_key, promoted_by, "
        "promoted_at, candidate_context_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("committee_paper_candidates", "https://example.test/paper.pdf", "committee_papers",
         "E06000001|https://example.test/paper.pdf", "test", "2026-08-19T00:00:00+00:00", "{}"),
    )
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, last_seen_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("E06000001", "Fixture Council", "unitary", "2020-01-01", "2020", "2020",
         "https://example.test/authority", "2026-08-19T00:00:00+00:00", 200, "fixture", digest),
    )
    conn.execute(
        "INSERT INTO committee_papers (authority_ons_code, document_url, report_title, archived_path, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("E06000001", "https://example.test/paper.pdf", "Agenda report", raw_path,
         "https://example.test/paper.pdf", "2026-08-19T00:00:00+00:00", 200,
         "committee_papers", digest),
    )
    result = register_existing(conn, settings, "committee_papers", 25)
    assert result == {
        "source": "committee_papers",
        "candidates": 1,
        "registered": 1,
        "missing_raw": 0,
        "source_systems": ["committee_papers"],
    }
    row = conn.execute("SELECT source_table, source_key FROM evidence_records").fetchone()
    assert row["source_table"] == "committee_papers"
    assert row["source_key"] == "E06000001|https://example.test/paper.pdf"
    assert register_existing(conn, settings, "committee_papers", 25) == {
        "source": "committee_papers",
        "candidates": 0,
        "registered": 0,
        "missing_raw": 0,
        "source_systems": [],
    }


def test_html_fallback_strips_markup_and_ignores_script_content():
    parsed = HTMLParserAdapter().parse(
        b"<html><body><h2>Committee report</h2><p>Published finding.</p>"
        b"<script>not evidence</script></body></html>", "text/html")
    assert [(element.element_type, element.text) for element in parsed.elements] == [
        ("HEADING", "Committee report"),
        ("PARAGRAPH", "Published finding."),
    ]


def test_unchanged_version_restores_completed_processing_state(conn):
    reference = EvidenceReference(
        "evidence-unchanged", "fixture", "https://example.test/document", "2026-08-19T00:00:00+00:00",
        200, "a" * 64, "data/raw/fixture/" + "a" * 64 + ".pdf")
    repository.upsert_evidence(conn, reference)
    repository.mark_attempt(conn, reference.evidence_id, "NORMAL", "OCR_NOT_REQUIRED")
    repository.mark_unchanged(conn, reference.evidence_id, "OCR_NOT_REQUIRED")
    row = conn.execute(
        "SELECT parse_status, ocr_status, last_error FROM document_processing_states WHERE evidence_id=?",
        (reference.evidence_id,)).fetchone()
    assert tuple(row) == ("SUCCESS", "OCR_NOT_REQUIRED", None)


def test_default_batch_selection_skips_successful_documents(conn):
    source = reference()
    repository.upsert_evidence(conn, source)
    assert len(_document_candidates(conn, None, "fixture", None, None, 25, pending_only=True)) == 1
    conn.execute("UPDATE document_processing_states SET parse_status='SUCCESS' WHERE evidence_id=?",
                 (source.evidence_id,))
    assert _document_candidates(conn, None, "fixture", None, None, 25, pending_only=True) == []
