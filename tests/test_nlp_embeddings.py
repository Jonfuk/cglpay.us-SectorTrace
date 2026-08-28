"""pipeline/nlp/embeddings.py — the stub embedder, the blob codec, the stage."""
from __future__ import annotations

import math

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import embeddings


def _seed_version(conn, settings, elements, *, evidence_id="ev-embed",
                  source_system="committee_paper_promotion"):
    source = EvidenceReference(
        evidence_id=evidence_id, source_system=source_system,
        source_url=f"https://example.test/{evidence_id}",
        retrieved_at="2026-08-27T00:00:00+00:00", http_status=200,
        payload_sha256=(evidence_id * 64)[:64],
        raw_object_path=f"data/raw/{source_system}/{(evidence_id * 64)[:64]}.pdf",
        mime_type="application/pdf")
    repository.upsert_evidence(conn, source)
    document_id = repository.upsert_document(
        conn, source, "COMMITTEE_PAPER", "fixture", 1.0, "paper.pdf",
        "application/pdf", 3, "Paper")
    parsed = ParsedDocument("fixture", "1", elements)
    return repository.persist_parse(conn, document_id, parsed, "cfg", None, "GOOD", {}, [], settings)


_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Workforce", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Recruitment and retention of drug and alcohol "
                  "key workers is the single biggest risk to the service this year.",
                  parent_sequence=1, page_number=1),
    ParsedElement("PARAGRAPH", 3, text="Agency spend has risen sharply to cover unfilled "
                  "substance misuse posts across every team.", page_number=2),
]


# --- the blob codec and cosine ------------------------------------------------

def test_pack_unpack_round_trips_little_endian_float32():
    vector = [0.0, 1.0, -0.5, 0.25, 3.14159]
    blob = embeddings.pack(vector)
    assert isinstance(blob, bytes) and len(blob) == 4 * len(vector)
    back = embeddings.unpack(blob)
    assert len(back) == len(vector)
    for a, b in zip(vector, back):
        assert math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)


def test_vec_literal_is_pgvector_text_form():
    assert embeddings.vec_literal([0.0, 1.0, -0.5]) == "[0.0,1.0,-0.5]"
    # Whatever the bytea holds is what the literal must carry — same float32
    # values, exactly, so the derived column cannot disagree with its source.
    stored = embeddings.unpack(embeddings.pack([0.1, -0.2, 0.333333]))
    literal = embeddings.vec_literal(stored)
    assert literal.startswith("[") and literal.endswith("]")
    assert [float(x) for x in literal[1:-1].split(",")] == stored


def test_backfill_vectors_is_a_noop_without_pgvector(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    embeddings.run(conn, model="stub")
    result = embeddings.backfill_vectors(conn)
    assert result["backend"] == "sqlite"
    assert result["written"] == 0


def test_stub_run_does_not_write_embedding_vec(conn, settings):
    # The column does not exist on SQLite, and the stub is 256-wide anyway —
    # `run` must not reference embedding_vec on this path.
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = embeddings.run(conn, model="stub")
    assert result["embedded"] > 0


def test_cosine_is_one_for_identical_and_near_zero_for_disjoint():
    a = embeddings.StubEmbedder().encode(["recruitment and retention pressure"])[0]
    b = embeddings.StubEmbedder().encode(["recruitment and retention pressure"])[0]
    c = embeddings.StubEmbedder().encode(["seaside promenade weather forecast"])[0]
    assert math.isclose(embeddings.cosine(a, b), 1.0, abs_tol=1e-6)
    assert abs(embeddings.cosine(a, c)) < 0.3


def test_stub_is_deterministic_across_instances():
    one = embeddings.StubEmbedder().encode(["the same words in the same order"])[0]
    two = embeddings.StubEmbedder().encode(["the same words in the same order"])[0]
    assert one == two
    assert len(one) == embeddings.STUB_DIMENSION


# --- the stage --------------------------------------------------------------

def test_run_embeds_live_chunks_and_registers_the_model(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")

    result = embeddings.run(conn, model="stub")
    assert result["embedded"] == result["pending"] >= 1
    assert result["model_key"] == "embed:stub"

    run_row = conn.execute("SELECT stage, status, model_key, rows_written FROM nlp_runs "
                           "WHERE run_id=?", (result["run_id"],)).fetchone()
    assert run_row["stage"] == "embed" and run_row["status"] == "ok"
    assert run_row["model_key"] == "embed:stub"
    assert run_row["rows_written"] == result["embedded"]

    model = conn.execute("SELECT * FROM nlp_model_registry WHERE model_key='embed:stub'").fetchone()
    assert model["model_provider"] == "hash-stub"
    assert model["revision_sha"] is None
    assert model["dimension"] == embeddings.STUB_DIMENSION

    rows = conn.execute(
        "SELECT e.dimension, e.embedding, e.nlp_run_id FROM document_embeddings e "
        "JOIN document_chunks c ON c.document_chunk_id = e.document_chunk_id "
        "WHERE c.superseded = 0").fetchall()
    assert rows
    for row in rows:
        assert row["dimension"] == embeddings.STUB_DIMENSION
        assert len(embeddings.unpack(row["embedding"])) == embeddings.STUB_DIMENSION
        assert row["nlp_run_id"] == result["run_id"]


def test_second_run_is_a_no_op(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    first = embeddings.run(conn, model="stub")
    again = embeddings.run(conn, model="stub")
    assert first["embedded"] >= 1
    assert again["pending"] == 0 and again["embedded"] == 0
    total = conn.execute("SELECT COUNT(*) FROM document_embeddings").fetchone()[0]
    assert total == first["embedded"]


def test_superseded_chunks_are_not_embedded(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    conn.execute("UPDATE document_chunks SET superseded = 1 WHERE document_version_id = ?",
                 (version_id,))
    result = embeddings.run(conn, model="stub")
    assert result["pending"] == 0 and result["embedded"] == 0


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = embeddings.run(conn, model="stub", dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_embeddings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='embed'").fetchone()[0] == 0
    # register() also rolls back with the run.
    assert conn.execute(
        "SELECT COUNT(*) FROM nlp_model_registry WHERE model_key='embed:stub'").fetchone()[0] == 0


def test_source_system_filter_scopes_the_run(conn, settings):
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-a",
                  source_system="committee_paper_promotion")
    _seed_version(conn, settings, _ELEMENTS, evidence_id="ev-b",
                  source_system="cdp_document_promotion")
    nlp_chunk.run(conn)
    result = embeddings.run(conn, model="stub", source_system="cdp_document_promotion")
    assert result["embedded"] >= 1
    embedded_versions = conn.execute(
        "SELECT DISTINCT c.document_version_id FROM document_embeddings e "
        "JOIN document_chunks c ON c.document_chunk_id = e.document_chunk_id").fetchall()
    assert len(embedded_versions) == 1
