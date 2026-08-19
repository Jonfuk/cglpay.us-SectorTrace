"""Canonical in-memory representation, independent of parser vendors."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CANONICAL_SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class EvidenceReference:
    evidence_id: str
    source_system: str
    source_url: str | None
    retrieved_at: str
    http_status: int | None
    payload_sha256: str
    raw_object_path: str
    mime_type: str | None = None
    content_length: int | None = None
    source_table: str | None = None
    source_key: str | None = None


@dataclass(frozen=True)
class Inspection:
    mime_type: str
    file_size: int
    status: str
    page_count: int | None = None
    embedded_text_chars: int = 0
    text_chars_per_page: tuple[int, ...] = ()
    pages_with_zero_text: int = 0
    image_count: int = 0
    encrypted: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedElement:
    element_type: str
    sequence: int
    text: str | None = None
    parent_sequence: int | None = None
    page_number: int | None = None
    heading_level: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedTable:
    element_sequence: int
    rows: list[list[str]]
    markdown: str | None = None


@dataclass(frozen=True)
class ParsedLink:
    element_sequence: int
    href: str
    anchor_text: str | None = None


@dataclass(frozen=True)
class ParsedDocument:
    parser_name: str
    parser_version: str
    elements: list[ParsedElement]
    tables: list[ParsedTable] = field(default_factory=list)
    links: list[ParsedLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(item.text for item in self.elements if item.text)
