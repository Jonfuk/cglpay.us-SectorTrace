"""Replaceable parser adapters and parser-neutral normalization."""
from __future__ import annotations

import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol

from pipeline.documents.models import ParsedDocument, ParsedElement


class ParserUnavailable(RuntimeError):
    """The selected optional parser is not installed."""


class DocumentParser(Protocol):
    name: str
    version: str

    def supports(self, mime_type: str) -> bool: ...
    def parse(self, body: bytes, mime_type: str) -> ParsedDocument: ...


def _elements_from_pages(pages: list[str]) -> list[ParsedElement]:
    """Conservative lightweight fallback that retains page provenance."""
    out: list[ParsedElement] = []
    sequence = 0
    for page_number, page in enumerate(pages, start=1):
        for paragraph in re.split(r"\n\s*\n", page):
            text = " ".join(paragraph.split())
            if not text:
                continue
            sequence += 1
            is_heading = len(text) < 160 and (text.isupper() or text.endswith(":"))
            out.append(ParsedElement("HEADING" if is_heading else "PARAGRAPH", sequence,
                                     text=text, page_number=page_number,
                                     heading_level=1 if is_heading else None))
    return out


class PyMuPDFParser:
    name = "pymupdf"

    def __init__(self) -> None:
        try:
            import fitz
        except ImportError as exc:  # pragma: no cover - install-specific
            raise ParserUnavailable(
                "PyMuPDF parsing needs `uv sync --extra documents`.") from exc
        self._fitz = fitz
        self.version = getattr(fitz, "VersionBind", "unknown")

    def supports(self, mime_type: str) -> bool:
        return mime_type == "application/pdf"

    def parse(self, body: bytes, mime_type: str) -> ParsedDocument:
        if not self.supports(mime_type):
            raise ValueError(f"{self.name} does not support {mime_type}")
        with self._fitz.open(stream=body, filetype="pdf") as pdf:
            elements = _elements_from_pages([page.get_text("text") for page in pdf])
        return ParsedDocument(self.name, self.version, elements)


class _HTMLTextCollector(HTMLParser):
    """Collect readable HTML blocks without treating markup as source text."""

    _BLOCKS = {"article", "blockquote", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "p", "td", "th"}
    _IGNORED = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[tuple[str | None, str]] = []
        self._tag: str | None = None
        self._parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag in self._IGNORED:
            self._ignored_depth += 1
        if self._ignored_depth == 0 and tag in self._BLOCKS:
            self._flush()
            self._tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        if self._ignored_depth == 0 and tag in self._BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush()

    def _flush(self) -> None:
        text = " ".join("".join(self._parts).split())
        if text:
            self.blocks.append((self._tag, text))
        self._tag, self._parts = None, []


class HTMLParserAdapter:
    """Deterministic stdlib fallback for archived HTML documents."""
    name = "html"
    version = "stdlib-html-parser-1"

    def supports(self, mime_type: str) -> bool:
        return mime_type == "text/html"

    def parse(self, body: bytes, mime_type: str) -> ParsedDocument:
        if not self.supports(mime_type):
            raise ValueError(f"{self.name} does not support {mime_type}")
        collector = _HTMLTextCollector()
        collector.feed(body.decode("utf-8", errors="replace"))
        collector.close()
        elements = []
        for sequence, (tag, text) in enumerate(collector.blocks, start=1):
            level = int(tag[1]) if tag and tag.startswith("h") and tag[1:].isdigit() else None
            elements.append(ParsedElement(
                "HEADING" if level else "PARAGRAPH", sequence, text=text, heading_level=level))
        return ParsedDocument(self.name, self.version, elements)


class DoclingParser:
    """Docling adapter. Its native document remains an input, never our schema."""
    name = "docling"

    def __init__(self) -> None:
        try:
            import docling
            from docling.document_converter import DocumentConverter
        except ImportError as exc:  # pragma: no cover - install-specific
            raise ParserUnavailable("Docling needs `uv sync --extra documents`.") from exc
        self.version = getattr(docling, "__version__", "unknown")
        self._converter_type = DocumentConverter

    def supports(self, mime_type: str) -> bool:
        return mime_type in {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             "text/html"}

    def parse(self, body: bytes, mime_type: str) -> ParsedDocument:
        if not self.supports(mime_type):
            raise ValueError(f"{self.name} does not support {mime_type}")
        suffix = {"application/pdf": ".pdf", "text/html": ".html"}.get(mime_type, ".docx")
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                temporary.write(body)
                path = Path(temporary.name)
            result = self._converter_type().convert(path)
            document = result.document
            # Markdown is used only as a defensive fallback when a Docling
            # release changes its internal item model. The parser name/version
            # makes that observable in quality review and reprocessing.
            markdown = document.export_to_markdown()
            return ParsedDocument(self.name, self.version, _elements_from_pages([markdown]))
        finally:
            if path is not None:
                path.unlink(missing_ok=True)


def get_parser(name: str) -> DocumentParser:
    if name == "docling":
        return DoclingParser()
    if name == "pymupdf":
        return PyMuPDFParser()
    if name == "html":
        return HTMLParserAdapter()
    raise ValueError(f"Unknown document parser {name!r}; supported: docling, pymupdf, html")
