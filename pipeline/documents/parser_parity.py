"""Read-only comparison of parser adapters against the same document bytes.

This is deliberately *not* `pipeline documents benchmark` (see
`pipeline/cli.py`, `documents_app.command("benchmark")`): that command runs
`DocumentService.process` end to end and commits a real `document_versions`
row per (document, parser) — it exercises the full pipeline, including OCR
routing, classification and persistence, and its purpose is to populate the
warehouse with a named parser's output for later review.

What is missing is a *parity* check: does swapping the preferred PDF parser
change what comes out, for the same bytes, without touching the database at
all? `PdfPlumberParser`'s docstring already promises this comparison exists
before the preferred parser is changed (see `pipeline/documents/parsers.py`).
`compare_parsers` below is that comparison — it calls `.parse()` on each
parser adapter directly and never opens a connection or writes anywhere.
"""
from __future__ import annotations

import difflib
import re
from collections import defaultdict
from itertools import combinations
from typing import Sequence

from pipeline.documents.models import ParsedDocument
from pipeline.documents.parsers import DocumentParser

# Bound on how much of a unified diff a report will carry. A real PDF can run
# to thousands of lines of normalized text; an unbounded diff turns a report
# meant to be read by a person into something nobody actually reads.
_DIFF_LINE_LIMIT = 200

_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_whitespace(text: str) -> str:
    """Collapse whitespace runs so a re-wrapped or re-indented page compares
    equal to itself. This is the *only* normalization applied — case,
    punctuation, and word order are left alone, because those differences are
    exactly the kind of thing a parity check exists to surface, not hide.
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def _per_page_text(document: ParsedDocument) -> dict[int, str]:
    """Group element text by `page_number`, when the parser recorded one.

    Elements without a page number (some fallback parsers only know a single
    logical page, see `_elements_from_pages`) are grouped under key `0` rather
    than dropped, so the caller can still see them in a diff.
    """
    pages: dict[int, list[str]] = defaultdict(list)
    for element in document.elements:
        if not element.text:
            continue
        pages[element.page_number or 0].append(element.text)
    return {page: "\n".join(parts) for page, parts in pages.items()}


def _summarize(document: ParsedDocument) -> dict:
    return {
        "parser_name": document.parser_name,
        "parser_version": document.parser_version,
        "element_count": len(document.elements),
        "table_count": len(document.tables),
        "text": document.text,
        "per_page_text": _per_page_text(document),
        "warnings": list(document.warnings),
    }


def _compare_pair(left: dict, right: dict) -> dict:
    """Pairwise comparison for two successfully-parsed summaries.

    Deliberately out of scope, per performance.md's equivalence bar: document
    identifiers, amounts, dates, concepts, spans, assertions and relations.
    Those are produced downstream by the NLP pipeline (`pipeline/nlp/`) from
    parsed elements, not by a `DocumentParser` — there is nothing on
    `ParsedDocument` today to extract them from at this layer, and wiring the
    NLP pipeline into a parser-level harness just to check that box would be
    a separate, much larger piece of work that risks reporting a false sense
    of completeness rather than an honest parity result.
    """
    left_norm = _normalize_whitespace(left["text"])
    right_norm = _normalize_whitespace(right["text"])
    text_equivalent = left_norm == right_norm
    element_delta = right["element_count"] - left["element_count"]
    table_delta = right["table_count"] - left["table_count"]

    diff: list[str] = []
    if not text_equivalent:
        diff = list(difflib.unified_diff(
            left_norm.splitlines(), right_norm.splitlines(),
            fromfile=left["parser_name"], tofile=right["parser_name"],
            lineterm="",
        ))
        truncated = len(diff) > _DIFF_LINE_LIMIT
        diff = diff[:_DIFF_LINE_LIMIT]
        if truncated:
            diff.append(f"... diff truncated at {_DIFF_LINE_LIMIT} lines ...")

    return {
        "left": left["parser_name"],
        "right": right["parser_name"],
        "element_count_delta": element_delta,
        "table_count_delta": table_delta,
        "text_equivalent_after_normalization": text_equivalent,
        "diff": diff,
        "equivalent": text_equivalent and element_delta == 0 and table_delta == 0,
    }


def compare_parsers(body: bytes, mime_type: str, parsers: Sequence[DocumentParser]) -> dict:
    """Parse `body` with each of `parsers` and report per-parser stats plus a
    pairwise comparison for every pair. Never opens a database connection or
    writes anything — the parsers are called directly against the given
    bytes, which is the entire point of this module (contrast with
    `DocumentService.process` / `pipeline documents benchmark`, which persist
    a document_versions row per run).

    A parser that raises while parsing (most commonly `ParserUnavailable`,
    when an optional dependency such as PyMuPDF is not installed) does not
    abort the comparison: that parser's entry becomes
    `{"error": ..., "error_type": ...}` and it is excluded from every pair
    it would have been part of, rather than crashing a batch over one
    document that one parser cannot read.
    """
    parsed: dict[str, dict] = {}
    for parser in parsers:
        try:
            document = parser.parse(body, mime_type)
        except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
            parsed[parser.name] = {"error": str(exc), "error_type": type(exc).__name__}
            continue
        parsed[parser.name] = _summarize(document)

    comparisons = []
    ok_names = [parser.name for parser in parsers if "error" not in parsed[parser.name]]
    for left_name, right_name in combinations(ok_names, 2):
        comparisons.append(_compare_pair(parsed[left_name], parsed[right_name]))

    return {"parsers": parsed, "comparisons": comparisons}
