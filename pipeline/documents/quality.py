"""Explicit, deterministic parser-quality metrics."""
from __future__ import annotations

import statistics
from collections import Counter

from pipeline.documents.models import ParsedDocument


def assess(parsed: ParsedDocument, pages_total: int | None = None) -> tuple[str, dict, list[str]]:
    texts = [element.text or "" for element in parsed.elements]
    non_empty = [text for text in texts if text.strip()]
    normalized_lines = [line.strip().lower() for text in non_empty for line in text.splitlines()
                        if line.strip()]
    repeated = sum(count - 1 for count in Counter(normalized_lines).values() if count > 1)
    characters = sum(len(text) for text in non_empty)
    replacement = sum(text.count("\ufffd") for text in non_empty)
    metrics = {
        "pages_total": pages_total,
        "pages_with_text": len({item.page_number for item in parsed.elements if item.text and item.page_number}),
        "pages_without_text": max(0, (pages_total or 0) - len({item.page_number for item in parsed.elements if item.text and item.page_number})),
        "total_characters": characters,
        "median_chars_per_element": statistics.median([len(text) for text in non_empty]) if non_empty else 0,
        "replacement_character_ratio": replacement / max(characters, 1),
        "duplicate_line_ratio": repeated / max(len(normalized_lines), 1),
        "heading_count": sum(item.element_type == "HEADING" for item in parsed.elements),
        "table_count": len(parsed.tables),
        "empty_element_ratio": (len(texts) - len(non_empty)) / max(len(texts), 1),
    }
    warnings = list(parsed.warnings)
    if not non_empty:
        return "FAILED", metrics, warnings + ["parser produced no text elements"]
    if metrics["replacement_character_ratio"] > 0.01 or metrics["empty_element_ratio"] > 0.5:
        return "SUSPECT", metrics, warnings
    if metrics["duplicate_line_ratio"] > 0.25:
        return "ACCEPTABLE", metrics, warnings + ["repeated lines may be headers or footers"]
    return "GOOD", metrics, warnings
