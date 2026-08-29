"""Orchestration: raw archive -> inspection -> optional OCR -> canonical parse."""
from __future__ import annotations

import hashlib
import json
import time

from pipeline.archive import get_archive
from pipeline.documents import ocr, repository
from pipeline.documents.artifacts import DerivedArtifactStore
from pipeline.documents.classify import classify
from pipeline.documents.inspect import inspect_bytes, ocr_required, source_filename
from pipeline.documents.models import EvidenceReference
from pipeline.documents.parsers import (
    DOCXParser,
    HTMLParserAdapter,
    MSWordParser,
    ParserUnavailable,
    PPTXParser,
    PyMuPDFParser,
    get_parser,
)
from pipeline.documents.quality import assess

# The formats whose only readers are the optional parsers (PyMuPDF, docling)
# and so the only ones that cannot be handled at all without `uv sync --extra
# documents`. Everything else this service accepts — DOCX, PPTX, HTML — has an
# adapter in pipeline/documents/parsers.py built on the standard library, and
# legacy .doc has its own already-non-fatal path through antiword.
#
# This exists so `process` can tell "this deployment is missing its parser"
# from "nothing here reads this format". They want opposite answers: the first
# must be raised, the second must be skipped and recorded.
NEEDS_OPTIONAL_PARSER = {"application/pdf"}


class DocumentService:
    def __init__(self, conn, settings):
        self.conn, self.settings = conn, settings

    def register(self, reference: EvidenceReference) -> None:
        repository.upsert_evidence(self.conn, reference)

    def process(self, reference: EvidenceReference, title: str | None = None,
                force: bool = False, parser_name: str | None = None) -> dict:
        if not self.settings.document_analysis_enabled:
            raise RuntimeError("Document analysis is disabled; set DOCUMENT_ANALYSIS_ENABLED=true.")
        self.register(reference)
        body = get_archive(self.settings).read(reference.raw_object_path)
        inspection = inspect_bytes(body, source_filename(reference.raw_object_path), reference.mime_type)
        if len(body) > self.settings.document_max_file_size_mb * 1024 * 1024:
            error = f"file exceeds DOCUMENT_MAX_FILE_SIZE_MB ({self.settings.document_max_file_size_mb})"
            repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, "OCR_NOT_REQUIRED", error)
            return {"status": "SKIPPED_LIMIT", "evidence_id": reference.evidence_id, "error": error}
        if inspection.page_count and inspection.page_count > self.settings.document_max_pages:
            error = f"document exceeds DOCUMENT_MAX_PAGES ({self.settings.document_max_pages})"
            repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, "OCR_NOT_REQUIRED", error)
            return {"status": "SKIPPED_LIMIT", "evidence_id": reference.evidence_id, "error": error}
        needs_ocr = ocr_required(inspection, self.settings)
        ocr_status = "OCR_REQUIRED" if needs_ocr else "OCR_NOT_REQUIRED"
        repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, ocr_status)
        document_type, method, confidence = classify(reference.source_system, title,
                                                      source_filename(reference.raw_object_path))
        document_id = repository.upsert_document(
            self.conn, reference, document_type, method, confidence, source_filename(reference.raw_object_path),
            inspection.mime_type, inspection.page_count, title)
        parser_input, source_artifact_id = body, None
        if needs_ocr and self.settings.document_ocr_enabled:
            try:
                ocr_body, tool_version = ocr.create_searchable_pdf(body, self.settings.document_ocr_language)
                storage_path, artifact_hash = DerivedArtifactStore(self.settings).put(
                    reference.source_system, "ocr_pdf", ".pdf", ocr_body)
                source_artifact_id = repository.add_artifact(
                    self.conn, reference, "OCR_PDF", storage_path, artifact_hash, "ocrmypdf", tool_version,
                    {"language": self.settings.document_ocr_language, "input_sha256": reference.payload_sha256,
                     "output_type": "pdf", "skip_text": True})
                parser_input, ocr_status = ocr_body, "OCR_SUCCESS"
            except Exception as exc:
                repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, "OCR_FAILED", str(exc))
                return {"status": "OCR_FAILED", "evidence_id": reference.evidence_id, "error": str(exc)}
        selected = parser_name or self.settings.document_parser
        # The configured parser still gets first refusal, and only the formats
        # it cannot take fall through to the adapters below. That order is
        # deliberate rather than incidental: docling handles DOCX and HTML
        # itself, so choosing an adapter by mime type first would quietly
        # route those away from the parser the deployment asked for.
        #
        # Its being *unavailable* is remembered rather than raised, though,
        # and that is the fix. A document this parser was never going to
        # handle — a legacy .doc with no antiword, a spreadsheet — must be
        # skipped with a recorded reason rather than abort the batch, and
        # that is true whether or not a PDF toolchain happens to be
        # installed. Raising here made the non-fatal skip below depend on a
        # parser it does not use, so an environment without the `documents`
        # extra turned every skippable document into a crash — including in
        # CI, where the two tests covering exactly that skip have been red
        # since the day it was written.
        parser = None
        unavailable: ParserUnavailable | None = None
        try:
            parser = get_parser(selected)
        except ParserUnavailable as exc:
            if selected == "docling":
                try:
                    parser = PyMuPDFParser()
                except ParserUnavailable as fallback:
                    unavailable = fallback
            else:
                unavailable = exc

        if parser is None or not parser.supports(inspection.mime_type):
            if inspection.mime_type == "text/html":
                parser = HTMLParserAdapter()
            elif DOCXParser().supports(inspection.mime_type):
                parser = DOCXParser()
            elif PPTXParser().supports(inspection.mime_type):
                parser = PPTXParser()
            elif inspection.mime_type == "application/msword":
                try:
                    parser = MSWordParser()
                except ParserUnavailable as exc:
                    error = str(exc)
                    repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, ocr_status, error)
                    return {"status": "SKIPPED_UNSUPPORTED_FORMAT", "evidence_id": reference.evidence_id,
                            "error": error}
            elif unavailable is not None and inspection.mime_type in NEEDS_OPTIONAL_PARSER:
                # The document is one only the missing parser could have read,
                # so this is a deployment without its parser rather than a
                # document nothing can parse. Raised, not skipped: a PDF
                # recorded as "unsupported format" reads as a bad document,
                # and a whole batch of them could be written off that way
                # before anyone noticed the install was incomplete.
                raise unavailable
            else:
                # No committed source in this pipeline produces types outside
                # PDF/DOCX/PPTX/HTML/legacy DOC, so this is treated the same
                # as DOCUMENT_MAX_PAGES: a non-fatal skip with a recorded
                # reason, not a raised exception that would abort a batch run.
                error = f"no parser supports {inspection.mime_type}"
                repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, ocr_status, error)
                return {"status": "SKIPPED_UNSUPPORTED_FORMAT", "evidence_id": reference.evidence_id,
                        "error": error}
        config = {"parser": parser.name, "parser_version": parser.version,
                  "schema_version": "1", "ocr": ocr_status,
                  "min_text_chars_per_page": self.settings.document_min_text_chars_per_page,
                  "max_zero_text_page_ratio": self.settings.document_max_zero_text_page_ratio}
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
        if not force and repository.version_exists(self.conn, document_id, parser.name, parser.version, config_hash):
            repository.mark_unchanged(self.conn, reference.evidence_id, ocr_status)
            return {"status": "UNCHANGED", "document_id": document_id, "evidence_id": reference.evidence_id}
        run_id = repository.stable_id("document-parse-run", f"{document_id}|{time.time_ns()}")
        started = repository.utcnow()
        self.conn.execute(
            "INSERT INTO document_parse_runs (document_parse_run_id, document_id, parser_name, parser_version, "
            "config_hash, started_at, status) VALUES (?, ?, ?, ?, ?, ?, 'RUNNING')",
            (run_id, document_id, parser.name, parser.version, config_hash, started))
        tick = time.monotonic()
        try:
            parsed = parser.parse(parser_input, inspection.mime_type)
            quality_status, metrics, warnings = assess(parsed, inspection.page_count)
            version_id = repository.persist_parse(self.conn, document_id, parsed, config_hash, source_artifact_id,
                                                  quality_status, metrics, warnings, self.settings)
            # BETA-062: name the document from the best available signal now
            # that its headings exist. inspection.metadata is {} for non-PDFs,
            # so .get("title") is simply None there.
            repository.refresh_display_title(self.conn, document_id, source_title=title,
                                             pdf_title=inspection.metadata.get("title"))
            self.conn.execute("UPDATE document_processing_states SET ocr_status=? WHERE evidence_id=?",
                              (ocr_status, reference.evidence_id))
            self.conn.execute(
                "UPDATE document_parse_runs SET completed_at=?, status='SUCCESS', elapsed_ms=?, warning_count=? "
                "WHERE document_parse_run_id=?",
                (repository.utcnow(), int((time.monotonic() - tick) * 1000), len(warnings), run_id))
            return {"status": "SUCCESS", "document_id": document_id, "document_version_id": version_id,
                    "evidence_id": reference.evidence_id, "quality_status": quality_status,
                    "parser": parser.name, "ocr_status": ocr_status}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.conn.execute("UPDATE document_parse_runs SET completed_at=?, status='FAILED', error=? "
                              "WHERE document_parse_run_id=?", (repository.utcnow(), error, run_id))
            repository.mark_attempt(self.conn, reference.evidence_id, inspection.status, ocr_status, error)
            raise
