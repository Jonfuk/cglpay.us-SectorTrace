"""Coverage for the parser-parity harness: `compare_parsers` and the
`pipeline documents benchmark-parsers` CLI command.

Deliberately does not touch PyMuPDF, pdfplumber, or a real PDF byte stream —
two small fixture parsers conforming to the `DocumentParser` protocol stand
in, so the delta/diff/equivalence logic is exercised without any optional
dependency or fixture corpus. Real PyMuPDF is not installed in this sandbox
(it is behind the `documents` extra); nothing here should require it.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline.documents.models import ParsedDocument, ParsedElement
from pipeline.documents.parser_parity import compare_parsers
from pipeline.documents.parsers import ParserUnavailable


class FixtureParser:
    """A minimal `DocumentParser` stand-in: returns canned elements/tables,
    or raises a canned exception, regardless of the bytes handed to it.
    """

    def __init__(self, name, version="1", elements=None, tables=None, error=None):
        self.name = name
        self.version = version
        self._elements = elements or []
        self._tables = tables or []
        self._error = error

    def supports(self, mime_type: str) -> bool:
        return True

    def parse(self, body: bytes, mime_type: str) -> ParsedDocument:
        if self._error is not None:
            raise self._error
        return ParsedDocument(self.name, self.version, list(self._elements), tables=list(self._tables))


def _elements(*texts: str) -> list[ParsedElement]:
    return [ParsedElement("PARAGRAPH", i, text=text, page_number=1) for i, text in enumerate(texts, start=1)]


def test_identical_parser_output_is_equivalent_with_an_empty_diff():
    shared = _elements("Alpha beta gamma.", "Delta epsilon.")
    left = FixtureParser("left", elements=shared)
    right = FixtureParser("right", elements=shared)

    result = compare_parsers(b"ignored", "application/pdf", [left, right])

    [comparison] = result["comparisons"]
    assert comparison["equivalent"] is True
    assert comparison["text_equivalent_after_normalization"] is True
    assert comparison["element_count_delta"] == 0
    assert comparison["table_count_delta"] == 0
    assert comparison["diff"] == []


def test_whitespace_only_differences_are_still_equivalent():
    left = FixtureParser("left", elements=_elements("Alpha   beta\ngamma."))
    right = FixtureParser("right", elements=_elements("Alpha beta gamma."))

    result = compare_parsers(b"ignored", "application/pdf", [left, right])

    [comparison] = result["comparisons"]
    assert comparison["equivalent"] is True
    assert comparison["text_equivalent_after_normalization"] is True
    assert comparison["diff"] == []


def test_a_genuine_content_difference_is_not_equivalent_and_has_a_diff():
    left = FixtureParser("left", elements=_elements("Alpha beta gamma."))
    right = FixtureParser("right", elements=_elements("Alpha beta DELTA."))

    result = compare_parsers(b"ignored", "application/pdf", [left, right])

    [comparison] = result["comparisons"]
    assert comparison["equivalent"] is False
    assert comparison["text_equivalent_after_normalization"] is False
    assert comparison["diff"]  # a non-empty unified diff a human can read


def test_a_raising_parser_is_recorded_as_an_error_and_does_not_crash_the_batch():
    left = FixtureParser("left", elements=_elements("Alpha beta gamma."))
    right = FixtureParser("right", error=ParserUnavailable("needs `uv sync --extra documents`"))

    result = compare_parsers(b"ignored", "application/pdf", [left, right])

    assert result["parsers"]["left"]["element_count"] == 1
    assert result["parsers"]["right"]["error_type"] == "ParserUnavailable"
    assert "uv sync" in result["parsers"]["right"]["error"]
    # No pair could be formed once one side failed to parse.
    assert result["comparisons"] == []


def test_element_and_table_count_mismatches_break_equivalence_even_with_matching_text():
    left = FixtureParser("left", elements=_elements("Alpha beta gamma."))
    right = FixtureParser(
        "right",
        elements=_elements("Alpha beta gamma.") + [ParsedElement("PARAGRAPH", 2, text="", page_number=1)],
    )
    # An element with empty text does not change `.text` (joined only from
    # elements with text) but does change `element_count` -- exactly the
    # kind of structural drift a text-only diff would miss.

    result = compare_parsers(b"ignored", "application/pdf", [left, right])

    [comparison] = result["comparisons"]
    assert comparison["text_equivalent_after_normalization"] is True
    assert comparison["element_count_delta"] == 1
    assert comparison["equivalent"] is False


def _fake_get_parser(mapping):
    def get_parser(name: str):
        try:
            return mapping[name]
        except KeyError:
            raise ParserUnavailable(f"no fixture parser named {name!r}") from None

    return get_parser


def test_cli_corpus_mode_runs_end_to_end_without_a_database(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.pdf").write_bytes(b"not a real pdf, the fixture parsers don't care")
    (corpus / "two.pdf").write_bytes(b"also not a real pdf")

    shared_elements = _elements("Alpha beta gamma.")
    mapping = {
        "fake_a": FixtureParser("fake_a", elements=shared_elements),
        "fake_b": FixtureParser("fake_b", elements=shared_elements),
    }
    monkeypatch.setattr("pipeline.documents.parsers.get_parser", _fake_get_parser(mapping))

    out_path = tmp_path / "report.json"
    result = CliRunner().invoke(cli_module.app, [
        "documents", "benchmark-parsers",
        "--corpus", str(corpus),
        "--parsers", "fake_a,fake_b",
        "--out", str(out_path),
    ])

    assert result.exit_code == 0, result.output
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(report) == 2
    for entry in report:
        [comparison] = entry["comparisons"]
        assert comparison["equivalent"] is True
    # stdout carries the same report the file does.
    assert json.loads(result.output) == report


def test_cli_corpus_mode_reports_non_equivalence_via_exit_code(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.pdf").write_bytes(b"irrelevant")

    mapping = {
        "fake_a": FixtureParser("fake_a", elements=_elements("Alpha beta gamma.")),
        "fake_b": FixtureParser("fake_b", elements=_elements("Alpha beta DELTA.")),
    }
    monkeypatch.setattr("pipeline.documents.parsers.get_parser", _fake_get_parser(mapping))

    result = CliRunner().invoke(cli_module.app, [
        "documents", "benchmark-parsers",
        "--corpus", str(corpus),
        "--parsers", "fake_a,fake_b",
    ])

    assert result.exit_code == 1, result.output


def test_cli_requires_exactly_one_of_manifest_or_corpus(tmp_path):
    result = CliRunner().invoke(cli_module.app, ["documents", "benchmark-parsers"])
    assert result.exit_code == 2

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("evidence_id\n", encoding="utf-8")
    result = CliRunner().invoke(cli_module.app, [
        "documents", "benchmark-parsers", "--corpus", str(corpus), "--manifest", str(manifest),
    ])
    assert result.exit_code == 2


def test_cli_corpus_mode_with_zero_pdfs_fails_rather_than_reporting_ok(tmp_path, monkeypatch):
    corpus = tmp_path / "empty_corpus"
    corpus.mkdir()

    mapping = {
        "fake_a": FixtureParser("fake_a", elements=_elements("Alpha.")),
        "fake_b": FixtureParser("fake_b", elements=_elements("Alpha.")),
    }
    monkeypatch.setattr("pipeline.documents.parsers.get_parser", _fake_get_parser(mapping))

    result = CliRunner().invoke(cli_module.app, [
        "documents", "benchmark-parsers", "--corpus", str(corpus), "--parsers", "fake_a,fake_b",
    ])

    assert result.exit_code == 2
    assert "nothing to benchmark" in result.output.lower() or "no documents" in result.output.lower()


def test_cli_fails_clearly_when_a_named_parser_cannot_be_constructed(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.pdf").write_bytes(b"irrelevant")

    def unavailable(name: str):
        raise ParserUnavailable(f"{name} needs `uv sync --extra documents`")

    monkeypatch.setattr("pipeline.documents.parsers.get_parser", unavailable)

    result = CliRunner().invoke(cli_module.app, [
        "documents", "benchmark-parsers", "--corpus", str(corpus), "--parsers", "pymupdf,pdfplumber",
    ])

    assert result.exit_code == 2
    assert "uv sync --extra documents" in result.output
