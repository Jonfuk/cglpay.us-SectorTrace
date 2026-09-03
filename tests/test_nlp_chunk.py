"""pipeline/nlp/chunk.py — paragraph chunking of document_elements."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk


def _seed_version(conn, settings, elements, *, evidence_id="evidence-nlp", source_system="committee_papers"):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}", retrieved_at="2026-08-27T00:00:00+00:00",
        http_status=200, payload_sha256="b" * 64,
        raw_object_path=f"data/raw/{source_system}/" + "b" * 64 + ".pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf", "application/pdf", 3, "Paper")
    parsed = ParsedDocument("fixture", "1", elements)
    return repository.persist_parse(
        conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


# --- build_chunks: pure, no DB -------------------------------------------------

def _rows(*specs):
    """(element_type, heading_level, page, text) -> the row-shape build_chunks reads."""
    out = []
    for i, (etype, level, page, text) in enumerate(specs):
        out.append({
            "document_element_id": f"el-{i}", "element_type": etype,
            "heading_level": level, "page_number": page, "text": text,
        })
    return out


def test_heading_flushes_and_becomes_section_context():
    words = "word " * 200
    elements = _rows(
        ("section_header", 1, 1, "Workforce"),
        ("paragraph", None, 1, words.strip()),
        ("section_header", 1, 2, "Finance"),
        ("paragraph", None, 2, "Budget pressure continues this year."),
    )
    chunks = nlp_chunk.build_chunks(elements)
    assert [c["chunk_index"] for c in chunks] == [0, 1]
    assert chunks[0]["preceding_heading_element_id"] == "el-0"
    assert chunks[1]["preceding_heading_element_id"] == "el-2"
    assert chunks[0]["element_start_id"] == chunks[0]["element_end_id"] == "el-1"
    assert chunks[1]["text"] == "Budget pressure continues this year."


def test_char_offsets_map_back_into_the_version_text():
    elements = _rows(
        ("paragraph", None, 1, "First paragraph here."),
        ("paragraph", None, 1, "Second paragraph here."),
    )
    version_text = "\n".join(e["text"] for e in elements)
    chunks = nlp_chunk.build_chunks(elements)
    assert len(chunks) == 1
    chunk = chunks[0]
    assert version_text[chunk["char_start"]:chunk["char_end"]] == chunk["text"]
    assert chunk["page_start"] == chunk["page_end"] == 1


def test_blank_elements_are_skipped():
    elements = _rows(
        ("paragraph", None, 1, "   "),
        ("paragraph", None, 1, "Real content."),
    )
    chunks = nlp_chunk.build_chunks(elements)
    assert len(chunks) == 1
    assert chunks[0]["element_start_id"] == "el-1"


# --- run(): end to end -------------------------------------------------------

_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Recruitment vacancies are increasing across teams.",
                  parent_sequence=1, page_number=1),
    ParsedElement("PARAGRAPH", 3, text="Agency spend has risen to cover unfilled posts.",
                  page_number=2),
]


def test_run_writes_chunks_a_run_row_and_is_idempotent(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)

    result = nlp_chunk.run(conn, source_system="committee_papers")
    assert result["versions"] == 1 and result["chunks"] >= 1

    run_row = conn.execute("SELECT status, rows_written FROM nlp_runs WHERE run_id=%s",
                           (result["run_id"],)).fetchone()
    assert run_row["status"] == "ok"
    assert run_row["rows_written"] == result["chunks"]

    rows = conn.execute(
        "SELECT document_chunk_id, chunk_index, element_start_id, element_end_id, "
        "page_start, page_end, char_start, char_end, superseded FROM document_chunks "
        "WHERE document_version_id=%s ORDER BY chunk_index", (version_id,)).fetchall()
    assert rows and all(r["superseded"] == 0 for r in rows)
    assert all(r["document_chunk_id"].startswith("dc-") for r in rows)
    # every element id referenced actually exists
    for row in rows:
        for col in ("element_start_id", "element_end_id"):
            assert conn.execute("SELECT 1 FROM document_elements WHERE document_element_id=%s",
                                (row[col],)).fetchone()

    first_ids = [r["document_chunk_id"] for r in rows]
    again = nlp_chunk.run(conn, source_system="committee_papers")
    assert again["chunks"] == result["chunks"]
    second_ids = [r["document_chunk_id"] for r in conn.execute(
        "SELECT document_chunk_id FROM document_chunks WHERE document_version_id=%s ORDER BY chunk_index",
        (version_id,)).fetchall()]
    assert first_ids == second_ids  # content-derived id is stable across runs
    assert conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone().values().__iter__().__next__() == len(first_ids)


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    result = nlp_chunk.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone().values().__iter__().__next__() == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs").fetchone().values().__iter__().__next__() == 0


def test_source_system_filter_scopes_the_run(conn, settings):
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-a", source_system="committee_papers")
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-b", source_system="cdp_documents")
    result = nlp_chunk.run(conn, source_system="cdp_documents")
    assert result["versions"] == 1
