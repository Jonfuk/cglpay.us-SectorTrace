"""Fast, deterministic PDF inspection before expensive document parsing."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from pipeline.documents.models import Inspection


class InspectionUnavailable(RuntimeError):
    """PyMuPDF is not installed with the optional documents dependencies."""


def load_pymupdf():
    """Use PyMuPDF's supported import name, retaining old pinned environments."""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError as exc:  # pragma: no cover - install-specific
            raise InspectionUnavailable(
                "PDF inspection needs `uv sync --extra documents` (PyMuPDF).") from exc
    return pymupdf


def inspect_bytes(body: bytes, filename: str | None = None,
                  mime_type: str | None = None) -> Inspection:
    """Inspect a supported document without interpreting it as evidence text."""
    mime = (mime_type or mimetypes.guess_type(filename or "")[0]
            or "application/octet-stream").split(";", 1)[0].lower()
    if mime != "application/pdf" and not body.startswith(b"%PDF-"):
        return Inspection(mime_type=mime, file_size=len(body), status="UNSUPPORTED")
    pymupdf = load_pymupdf()
    try:
        with pymupdf.open(stream=body, filetype="pdf") as pdf:
            page_text = tuple(len(page.get_text("text").strip()) for page in pdf)
            image_count = sum(len(page.get_images(full=True)) for page in pdf)
            metadata = {str(key): str(value) for key, value in (pdf.metadata or {}).items()
                        if value is not None}
            return Inspection(
                mime_type="application/pdf", file_size=len(body), status="NORMAL",
                page_count=len(pdf), embedded_text_chars=sum(page_text),
                text_chars_per_page=page_text,
                pages_with_zero_text=sum(chars == 0 for chars in page_text),
                image_count=image_count, encrypted=bool(pdf.needs_pass), metadata=metadata,
            )
    except Exception as exc:
        return Inspection(mime_type="application/pdf", file_size=len(body), status="CORRUPT",
                          metadata={"error": type(exc).__name__})


def ocr_required(inspection: Inspection, settings) -> bool:
    """A deliberately transparent routing rule; it never changes raw bytes."""
    if inspection.status != "NORMAL" or inspection.page_count in (None, 0):
        return False
    chars_per_page = inspection.embedded_text_chars / inspection.page_count
    zero_ratio = inspection.pages_with_zero_text / inspection.page_count
    return (chars_per_page < settings.document_min_text_chars_per_page
            or zero_ratio > settings.document_max_zero_text_page_ratio)


def source_filename(raw_object_path: str) -> str:
    return Path(raw_object_path).name
