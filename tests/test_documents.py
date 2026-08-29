from __future__ import annotations

import hashlib
import io
import subprocess
import zipfile

import pytest

from pipeline.archive import FilesystemArchive
from pipeline.cli import _document_candidates
from pipeline.documents import repository
from pipeline.documents.artifacts import DerivedArtifactStore
from pipeline.documents.bridge import register_existing
from pipeline.documents.inspect import DOCX_MIME, PPTX_MIME, inspect_bytes, ocr_required
from pipeline.documents.models import EvidenceReference, Inspection, ParsedDocument, ParsedElement
from pipeline.documents.parsers import (
    DOCXParser,
    HTMLParserAdapter,
    MSWordParser,
    ParserUnavailable,
    PPTXParser,
)
from pipeline.documents.quality import assess
from pipeline.documents.service import DocumentService


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


def test_inspection_recovers_html_from_generic_archive_mime():
    inspection = inspect_bytes(
        b"\xef\xbb\xbf<!doctype html><html><body>Report</body></html>",
        "a" * 64 + ".bin",
        "application/octet-stream",
    )
    assert inspection.mime_type == "text/html"
    assert inspection.status == "UNSUPPORTED"


def test_docx_parser_recovers_text_headings_and_tables_from_generic_archive_mime():
    document_xml = """\
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Report title</w:t></w:r></w:p>
    <w:p><w:r><w:t>Published finding.</w:t></w:r></w:p>
    <w:tbl>
      <w:tr><w:tc><w:p><w:r><w:t>Year</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Value</w:t></w:r></w:p></w:tc></w:tr>
      <w:tr><w:tc><w:p><w:r><w:t>2026</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>42</w:t></w:r></w:p></w:tc></w:tr>
    </w:tbl>
  </w:body>
</w:document>"""
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", document_xml)

    inspection = inspect_bytes(body.getvalue(), "report.bin", "application/octet-stream")
    parsed = DOCXParser().parse(body.getvalue(), inspection.mime_type)
    assert inspection.mime_type == DOCX_MIME
    assert [(item.element_type, item.text, item.heading_level) for item in parsed.elements] == [
        ("HEADING", "Report title", 1),
        ("PARAGRAPH", "Published finding.", None),
        ("TABLE", "Year | Value\n2026 | 42", None),
    ]
    assert parsed.tables[0].rows == [["Year", "Value"], ["2026", "42"]]


def test_pptx_parser_recovers_slide_text_from_generic_archive_mime():
    slide_xml = """\
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
        xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld><p:spTree>
    <p:sp><p:nvSpPr><p:nvPr><p:ph type="title"/></p:nvPr></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>Slide title</a:t></a:r></a:p></p:txBody>
    </p:sp>
    <p:sp><p:nvSpPr><p:nvPr/></p:nvSpPr>
      <p:txBody><a:p><a:r><a:t>Finding on slide one.</a:t></a:r></a:p></p:txBody>
    </p:sp>
  </p:spTree></p:cSld>
</p:sld>"""
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("ppt/presentation.xml", "<p:presentation/>")
        package.writestr("ppt/slides/slide1.xml", slide_xml)

    inspection = inspect_bytes(body.getvalue(), "presentation.bin", "application/octet-stream")
    parsed = PPTXParser().parse(body.getvalue(), inspection.mime_type)
    assert inspection.mime_type == PPTX_MIME
    assert [(item.element_type, item.text, item.page_number) for item in parsed.elements] == [
        ("HEADING", "Slide title", 1),
        ("PARAGRAPH", "Finding on slide one.", 1),
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


def test_msword_parser_reports_unavailable_without_antiword(monkeypatch):
    monkeypatch.setattr("pipeline.documents.parsers.shutil.which", lambda name: None)
    with pytest.raises(ParserUnavailable):
        MSWordParser()


def test_msword_parser_extracts_text_via_antiword(monkeypatch):
    monkeypatch.setattr("pipeline.documents.parsers.shutil.which", lambda name: "/usr/bin/antiword")

    def fake_run(args, capture_output=True, text=True, check=False):
        del capture_output, text, check
        if len(args) == 1:
            return subprocess.CompletedProcess(args, 0, stdout="Version: 0.37  (21 Oct 2005)\n", stderr="")
        return subprocess.CompletedProcess(
            args, 0, stdout="REPORT TITLE\n\nA finding about workforce pressure.\n", stderr="")

    monkeypatch.setattr("pipeline.documents.parsers.subprocess.run", fake_run)
    parser = MSWordParser()
    assert parser.version == "Version: 0.37"
    parsed = parser.parse(b"fake legacy doc bytes", "application/msword")
    assert parsed.parser_name == "msword"
    assert [(item.element_type, item.text) for item in parsed.elements] == [
        ("HEADING", "REPORT TITLE"),
        ("PARAGRAPH", "A finding about workforce pressure."),
    ]


def test_msword_document_is_skipped_not_raised_without_antiword(conn, settings, monkeypatch):
    monkeypatch.setattr("pipeline.documents.parsers.shutil.which", lambda name: None)
    archive = FilesystemArchive(settings.raw_archive_dir)
    body = b"\xd0\xcf\x11\xe0legacy word bytes"
    digest = hashlib.sha256(body).hexdigest()
    raw_path = archive.put("committee_papers", digest, "application/msword", body)
    doc_reference = EvidenceReference(
        evidence_id="evidence-msword", source_system="committee_papers",
        source_url="https://example.test/report.doc", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256=digest, raw_object_path=raw_path, mime_type="application/msword")

    result = DocumentService(conn, settings).process(doc_reference)

    assert result["status"] == "SKIPPED_UNSUPPORTED_FORMAT"
    assert "antiword" in result["error"]
    row = conn.execute(
        "SELECT parse_status, last_error FROM document_processing_states WHERE evidence_id=?",
        (doc_reference.evidence_id,)).fetchone()
    assert row["parse_status"] == "FAILED"
    assert "antiword" in row["last_error"]


def test_a_pdf_with_no_parser_installed_raises_rather_than_being_skipped(conn, settings, monkeypatch):
    """The opposite answer to the two tests below, and it has to be.

    Those two say an unreadable *document* must not abort a batch. This says a
    missing *parser* must — it is a deployment that is not finished, not a
    document nothing can read. Recording a PDF as SKIPPED_UNSUPPORTED_FORMAT
    would read as a bad document, and a whole batch of them could be written
    off that way before anyone noticed the install was incomplete.

    Pinned because the change that stopped a missing PDF parser from crashing
    the skip path could just as easily have turned this into a silent skip.
    """
    def unavailable(*args, **kwargs):
        raise ParserUnavailable("PyMuPDF parsing needs `uv sync --extra documents`.")

    # Inspection reads a PDF with PyMuPDF too, so it is stubbed rather than
    # left to fail first and prove nothing about parser selection.
    monkeypatch.setattr(
        "pipeline.documents.service.inspect_bytes",
        lambda *args, **kwargs: Inspection(
            mime_type="application/pdf", file_size=32, status="NORMAL", page_count=1,
            embedded_text_chars=5000, text_chars_per_page=(5000,)))
    monkeypatch.setattr("pipeline.documents.service.get_parser", unavailable)
    monkeypatch.setattr("pipeline.documents.service.PyMuPDFParser", unavailable)

    archive = FilesystemArchive(settings.raw_archive_dir)
    body = b"%PDF-1.7 a report"
    digest = hashlib.sha256(body).hexdigest()
    raw_path = archive.put("committee_papers", digest, "application/pdf", body)
    doc_reference = EvidenceReference(
        evidence_id="evidence-pdf-no-parser", source_system="committee_papers",
        source_url="https://example.test/report.pdf", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256=digest, raw_object_path=raw_path, mime_type="application/pdf")

    with pytest.raises(ParserUnavailable):
        DocumentService(conn, settings).process(doc_reference)


def test_unrecognised_format_is_skipped_not_raised(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    body = b"binary spreadsheet bytes"
    digest = hashlib.sha256(body).hexdigest()
    raw_path = archive.put("committee_papers", digest, "application/vnd.ms-excel", body)
    doc_reference = EvidenceReference(
        evidence_id="evidence-xls", source_system="committee_papers",
        source_url="https://example.test/report.xls", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256=digest, raw_object_path=raw_path, mime_type="application/vnd.ms-excel")

    result = DocumentService(conn, settings).process(doc_reference)

    assert result["status"] == "SKIPPED_UNSUPPORTED_FORMAT"
    assert "application/vnd.ms-excel" in result["error"]


# --- display titles (BETA-062) ----------------------------------------------


def _seed_parsed(conn, settings, *, source_title, headings, paragraph="Body text."):
    source = reference()
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0,
        "a3f91c2b8e4d5f6071829304a5b6c7d8.pdf", "application/pdf", 1, source_title)
    elements, seq = [], 1
    for heading in headings:
        elements.append(ParsedElement("HEADING", seq, text=heading, page_number=1, heading_level=1))
        seq += 1
    elements.append(ParsedElement("PARAGRAPH", seq, text=paragraph, page_number=1))
    repository.persist_parse(conn, document_id, ParsedDocument("fixture", "1", elements),
                             "config", None, "GOOD", {}, [], settings)
    return document_id


def test_refresh_display_title_prefers_the_source_label(conn, settings):
    document_id = _seed_parsed(
        conn, settings, source_title="Kent Substance Misuse JSNA 2024",
        headings=["Contents", "Executive summary"])

    display, basis = repository.refresh_display_title(
        conn, document_id, source_title="Kent Substance Misuse JSNA 2024")

    assert (display, basis) == ("Kent Substance Misuse JSNA 2024", "source_label")
    row = conn.execute("SELECT display_title, title_basis FROM document_records "
                       "WHERE document_id=?", (document_id,)).fetchone()
    assert row["display_title"] == "Kent Substance Misuse JSNA 2024"
    assert row["title_basis"] == "source_label"


def test_refresh_display_title_falls_to_the_first_usable_heading(conn, settings):
    document_id = _seed_parsed(
        conn, settings, source_title=None,
        headings=["Page 1", "Cabinet Report on Treatment Recommissioning"])

    display, basis = repository.refresh_display_title(
        conn, document_id, source_title=None)

    # "Page 1" is a running-header artefact and is skipped.
    assert (display, basis) == ("Cabinet Report on Treatment Recommissioning", "heading")


def test_processing_a_document_names_it_from_its_heading(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    body = b"<html><body><h1>Adult Treatment Plan 2026</h1><p>Recruitment.</p></body></html>"
    digest = hashlib.sha256(body).hexdigest()
    raw_path = archive.put("committee_papers", digest, "text/html", body)
    doc_reference = EvidenceReference(
        evidence_id="evidence-html-title", source_system="committee_papers",
        source_url="https://example.test/plan", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256=digest, raw_object_path=raw_path, mime_type="text/html")

    result = DocumentService(conn, settings).process(doc_reference)
    assert result["status"] == "SUCCESS"

    row = conn.execute(
        "SELECT display_title, title_basis FROM document_records d "
        "JOIN evidence_records e ON e.evidence_id=d.evidence_id WHERE e.evidence_id=?",
        (doc_reference.evidence_id,)).fetchone()
    assert row["display_title"] == "Adult Treatment Plan 2026"
    assert row["title_basis"] == "heading"


def test_backfill_names_rows_without_a_display_title_and_leaves_hashes_unknown(conn, settings):
    good = _seed_parsed(conn, settings, source_title="Overdose Prevention Strategy",
                        headings=["Intro"])
    # No source label, no usable heading, only a hash-like filename.
    source = EvidenceReference(
        evidence_id="evidence-hash", source_system="fixture",
        source_url="https://example.test/x", retrieved_at="2026-08-19T00:00:00+00:00",
        http_status=200, payload_sha256="b" * 64,
        raw_object_path="data/raw/fixture/" + "b" * 64 + ".pdf", mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    bad = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0,
        "b7c1e2c3d4f5a6b7c8d9e0f1a2b3c4d5.pdf", "application/pdf", 1, None)

    result = repository.backfill_display_titles(conn)

    assert result["updated"] == 2
    assert result["by_basis"] == {"source_label": 1, "unknown": 1}
    assert conn.execute("SELECT title_basis FROM document_records WHERE document_id=?",
                        (good,)).fetchone()[0] == "source_label"
    row = conn.execute("SELECT display_title, title_basis FROM document_records "
                       "WHERE document_id=?", (bad,)).fetchone()
    assert row["display_title"] is None and row["title_basis"] == "unknown"

    # Idempotent: a second run without --recompute finds nothing to do.
    assert repository.backfill_display_titles(conn)["updated"] == 0
