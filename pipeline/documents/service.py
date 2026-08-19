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
from pipeline.documents.parsers import ParserUnavailable, PyMuPDFParser, get_parser
from pipeline.documents.quality import assess


class DocumentService:
    def __init__(self, conn, settings):
        self.conn, self.settings = conn, settings

    def register(self, reference: EvidenceReference) -> None:
        repository.upsert_evidence(self.conn, reference)

    def process(self, reference: EvidenceReference, title: str | None = None,
                force: bool = False, parser_name: str | None = None) -> dict:
        self.register(reference)
        body = get_archive(self.settings).read(reference.raw_object_path)
        inspection = inspect_bytes(body, source_filename(reference.raw_object_path), reference.mime_type)
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
                storage_path, artifact_hash = DerivedArtifactStore(self.settings.derived_archive_dir).put(
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
        try:
            parser = get_parser(selected)
        except ParserUnavailable:
            if selected != "docling":
                raise
            parser = PyMuPDFParser()
        config = {"parser": parser.name, "parser_version": parser.version,
                  "schema_version": "1", "ocr": ocr_status,
                  "min_text_chars_per_page": self.settings.document_min_text_chars_per_page,
                  "max_zero_text_page_ratio": self.settings.document_max_zero_text_page_ratio}
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()
        if not force and repository.version_exists(self.conn, document_id, parser.name, parser.version, config_hash):
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
