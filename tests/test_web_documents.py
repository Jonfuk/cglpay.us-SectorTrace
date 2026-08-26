"""Document search (BETA-022): the public route over the document-analysis
pipeline's already-parsed, already-searchable text (docs/document-analysis.md).

The one thing this file exists to pin down: `document_search()` reads from an
explicit source-system allowlist, not "everything in document_records" —
`_public()` alone would not catch a future source sharing this schema that
does carry restricted personal data (PFD report bodies, tribunal judgment
text), because `document_records`/`document_elements` are not
`restricted_`-prefixed tables. A document from an unlisted source system must
never be returned here, even when its text matches the query exactly.
"""
from __future__ import annotations

import pytest

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.web import public_queries
from pipeline.web.queries import QueryError


def _reference(evidence_id: str, source_system: str) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-19T00:00:00+00:00", http_status=200,
        payload_sha256="a" * 64,
        raw_object_path=f"data/raw/{source_system}/" + "a" * 64 + ".pdf",
        mime_type="application/pdf",
    )


def _seed_document(conn, settings, *, evidence_id: str, source_system: str,
                    document_type: str, text: str, title: str | None = None) -> None:
    reference = _reference(evidence_id, source_system)
    repository.upsert_evidence(conn, reference)
    document_id = repository.upsert_document(
        conn, reference, document_type, "fixture", 1.0, "report.pdf",
        "application/pdf", 1, title)
    parsed = ParsedDocument("fixture", "1", [
        ParsedElement("PARAGRAPH", 1, text=text, page_number=1),
    ])
    repository.persist_parse(
        conn, document_id, parsed, "config", None, "GOOD", {}, [], settings)


def test_document_search_finds_committee_paper_text(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-committee", source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Substance misuse recruitment vacancies rose in Q3.",
        title="Cabinet committee minutes")

    result = public_queries.document_search(conn, query="recruitment")

    assert result["query"] == "recruitment"
    assert result["caveat"]
    assert len(result["results"]) == 1
    row = result["results"][0]
    assert row["document_type"] == "COMMITTEE_PAPER"
    assert row["title"] == "Cabinet committee minutes"
    assert row["page_number"] == 1
    assert "recruitment" in row["text"].lower()
    assert row["source_url"] == "https://example.test/ev-committee"


def test_document_search_finds_cdp_document_text(conn, settings):
    _seed_document(
        conn, settings, evidence_id="ev-cdp", source_system="cdp_document_promotion",
        document_type="UNKNOWN", text="Partnership board reviewed naloxone distribution figures.")

    result = public_queries.document_search(conn, query="naloxone")

    assert len(result["results"]) == 1
    assert result["results"][0]["document_id"]


def test_document_search_excludes_source_systems_outside_the_allowlist(conn, settings):
    """A document from any source not in DOCUMENT_SEARCH_SOURCES must never
    surface here, even on an exact text match. This is the actual safety
    boundary for the route (see public_queries.py's own comment on why
    `_public()` alone is not enough)."""
    _seed_document(
        conn, settings, evidence_id="ev-restricted-shaped", source_system="pfd_report_promotion",
        document_type="PFD_REPORT", text="A very distinctive unique search phrase xyzzyplugh.")
    _seed_document(
        conn, settings, evidence_id="ev-committee-2", source_system="committee_paper_promotion",
        document_type="COMMITTEE_PAPER", text="Nothing to do with the other phrase.")

    result = public_queries.document_search(conn, query="xyzzyplugh")

    assert result["results"] == []


def test_document_search_requires_a_query(conn):
    with pytest.raises(QueryError):
        public_queries.document_search(conn, query="")
    with pytest.raises(QueryError):
        public_queries.document_search(conn, query="   ")


def test_document_search_limit_is_clamped(conn, settings):
    for i in range(3):
        _seed_document(
            conn, settings, evidence_id=f"ev-limit-{i}", source_system="committee_paper_promotion",
            document_type="COMMITTEE_PAPER", text="Budget pressures continue across the service.")

    result = public_queries.document_search(conn, query="budget", limit=1)
    assert len(result["results"]) == 1

    # A limit above the route's own ceiling is clamped, not honoured verbatim —
    # the same discipline as every other public route with a limit parameter.
    result = public_queries.document_search(conn, query="budget", limit=10_000)
    assert len(result["results"]) == 3
