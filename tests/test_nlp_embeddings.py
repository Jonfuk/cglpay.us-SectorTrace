"""pipeline/nlp/embeddings.py — the stub embedder, the blob codec, the stage."""
from __future__ import annotations

import math
import re
from pathlib import Path

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import embeddings
from pipeline.nlp.embedding_repository import (
    PostgresEmbeddingRepository,
    compact_legacy_table,
    validate_restore_receipt,
    vector_values,
)


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


def test_backfill_vectors_uses_the_postgres_backend(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    embeddings.run(conn, model="stub")
    result = embeddings.backfill_vectors(conn)
    assert result["backend"] == "postgres"
    assert result["written"] == 0


def test_stub_run_writes_only_canonical_embedding_vec(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = embeddings.run(conn, model="stub")
    assert result["embedded"] > 0
    row = conn.execute(
        "SELECT embedding,embedding_vec FROM document_embeddings LIMIT 1").fetchone()
    assert row["embedding"] is None
    assert len(vector_values(row["embedding_vec"])) == embeddings.VECTOR_COLUMN_DIM


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


def test_get_embedder_caches_one_instance_per_name():
    # The sentence-transformers model costs a load on first encode; the
    # assistant's retrieval tool calls get_embedder once per turn, so the
    # instance must be reused rather than rebuilt (BETA-116).
    a = embeddings.get_embedder("stub")
    b = embeddings.get_embedder(None)
    c = embeddings.get_embedder("sentence-transformers/all-MiniLM-L6-v2")
    d = embeddings.get_embedder("sentence-transformers/all-MiniLM-L6-v2")
    assert a is b            # None and "stub" resolve to the same cached stub
    assert c is d            # same name -> same instance (no reload)
    assert c is not a


# --- the stage --------------------------------------------------------------

def test_run_embeds_live_chunks_and_registers_the_model(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")

    result = embeddings.run(conn, model="stub")
    assert result["embedded"] == result["pending"] >= 1
    assert result["model_key"] == "embed:stub"

    run_row = conn.execute("SELECT stage, status, model_key, rows_written FROM nlp_runs "
                           "WHERE run_id=%s", (result["run_id"],)).fetchone()
    assert run_row["stage"] == "embed" and run_row["status"] == "ok"
    assert run_row["model_key"] == "embed:stub"
    assert run_row["rows_written"] == result["embedded"]

    model = conn.execute("SELECT * FROM nlp_model_registry WHERE model_key='embed:stub'").fetchone()
    assert model["model_provider"] == "hash-stub"
    assert model["revision_sha"] is None
    assert model["dimension"] == embeddings.STUB_DIMENSION

    rows = conn.execute(
        "SELECT e.dimension, e.embedding_vec, e.nlp_run_id FROM document_embeddings e "
        "JOIN document_chunks c ON c.document_chunk_id = e.document_chunk_id "
        "WHERE c.superseded = 0").fetchall()
    assert rows
    for row in rows:
        assert row["dimension"] == embeddings.STUB_DIMENSION
        assert len(vector_values(row["embedding_vec"])) == embeddings.STUB_DIMENSION
        assert row["nlp_run_id"] == result["run_id"]


def test_second_run_is_a_no_op(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    first = embeddings.run(conn, model="stub")
    again = embeddings.run(conn, model="stub")
    assert first["embedded"] >= 1
    assert again["pending"] == 0 and again["embedded"] == 0
    total = conn.execute("SELECT COUNT(*) FROM document_embeddings").fetchone().values().__iter__().__next__()
    assert total == first["embedded"]


def test_superseded_chunks_are_not_embedded(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    conn.execute("UPDATE document_chunks SET superseded = 1 WHERE document_version_id = %s",
                 (version_id,))
    result = embeddings.run(conn, model="stub")
    assert result["pending"] == 0 and result["embedded"] == 0


def test_dry_run_writes_nothing(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    result = embeddings.run(conn, model="stub", dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_embeddings").fetchone().values().__iter__().__next__() == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='embed'").fetchone().values().__iter__().__next__() == 0
    # register() also rolls back with the run.
    assert conn.execute(
        "SELECT COUNT(*) FROM nlp_model_registry WHERE model_key='embed:stub'").fetchone().values().__iter__().__next__() == 0


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


def test_repository_population_is_keyset_paged(conn, settings):
    for suffix in ("a", "b", "c"):
        _seed_version(conn, settings, _ELEMENTS, evidence_id=f"ev-page-{suffix}")
    nlp_chunk.run(conn)
    embeddings.run(conn, model="stub")
    pages = list(PostgresEmbeddingRepository(conn).iter_population("embed:stub", page_size=2))
    ids = [chunk_id for page in pages for chunk_id, _, _ in page]
    assert pages and all(len(page) <= 2 for page in pages)
    assert ids == sorted(ids) and len(ids) == len(set(ids))


def test_repository_population_excludes_inactive_document_versions(conn, settings):
    version_id = _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn)
    embeddings.run(conn, model="stub")
    conn.execute("UPDATE document_versions SET is_active=0 WHERE document_version_id=%s",
                 (version_id,))
    conn.commit()
    assert list(PostgresEmbeddingRepository(conn).iter_population("embed:stub")) == []


def test_active_nlp_consumers_do_not_query_vector_storage_directly():
    root = Path(__file__).resolve().parent.parent / "pipeline" / "nlp"
    allowed = {"embedding_repository.py", "embeddings.py"}
    offenders = []
    for path in root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        direct_sql = re.search(
            r"(?:FROM|JOIN|INSERT\s+INTO|UPDATE)\s+document_embeddings\b", source, re.I)
        if path.name not in allowed and direct_sql:
            offenders.append(path.name)
    assert offenders == []


def test_embedding_compaction_dry_run_rolls_back_every_change(conn, settings):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn)
    embeddings.run(conn, model="stub")
    before = conn.execute("SELECT COUNT(*) AS count FROM document_embeddings").fetchone()["count"]
    result = compact_legacy_table(conn, dry_run=True)
    assert result["status"] == "dry_run" and result["rows"] == before
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM document_embeddings").fetchone()["count"] == before
    assert conn.execute(
        "SELECT to_regclass(current_schema() || '.document_embeddings_compact') AS name"
    ).fetchone()["name"] is None


def test_embedding_compaction_applies_after_verified_restore(conn, settings, tmp_path, monkeypatch):
    _seed_version(conn, settings, _ELEMENTS)
    nlp_chunk.run(conn)
    embeddings.run(conn, model="stub")
    source_rows = conn.execute(
        "SELECT document_chunk_id, model_key, embedding_vec FROM document_embeddings"
    ).fetchall()
    for row in source_rows:
        conn.execute(
            "UPDATE document_embeddings SET embedding=%s WHERE document_chunk_id=%s AND model_key=%s",
            (embeddings.pack(vector_values(row["embedding_vec"])),
             row["document_chunk_id"], row["model_key"]),
        )
    conn.commit()

    archive = tmp_path / "warehouse.sql.gz"
    archive.write_bytes(b"verified backup fixture")
    receipt = tmp_path / "restore-receipt.json"
    import hashlib
    import json
    receipt.write_text(json.dumps({
        "from": str(archive.resolve()),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "rows": len(source_rows), "tables": 1,
        "restored": "postgresql://redacted",
        "restored_at": "2026-09-04T00:00:00+00:00",
    }))
    monkeypatch.setattr(
        "pipeline.pgbackup.verify_archive",
        lambda _path: {"rows": len(source_rows), "tables": 1},
    )

    result = compact_legacy_table(conn, backup_archive=archive, restore_receipt=receipt)

    assert result["status"] == "complete"
    columns = {
        row["column_name"] for row in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name='document_embeddings'")
    }
    assert "embedding" not in columns
    assert conn.execute("SELECT COUNT(*) AS count FROM document_embeddings").fetchone()["count"] == len(source_rows)
    assert conn.execute(
        "SELECT status FROM embedding_migration_audits WHERE migration_id=%s",
        (result["migration_id"],),
    ).fetchone()["status"] == "complete"


def test_embedding_compaction_apply_requires_restore_evidence(conn):
    try:
        compact_legacy_table(conn)
    except RuntimeError as exc:
        assert "isolated-restore receipt" in str(exc)
    else:
        raise AssertionError("unguarded embedding table swap was accepted")


def test_restore_receipt_is_bound_to_exact_archive_bytes(tmp_path, monkeypatch):
    import hashlib
    import json

    from pipeline import pgbackup

    archive = tmp_path / "warehouse.sql.gz"
    archive.write_bytes(b"fixture archive bytes")
    monkeypatch.setattr(pgbackup, "verify_archive",
                        lambda path: {"rows": 12, "tables": 3})
    receipt = tmp_path / "restore-receipt.json"
    receipt.write_text(json.dumps({
        "from": str(archive.resolve()),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "rows": 12, "tables": 3, "restored": "postgresql://redacted",
        "restored_at": "2026-09-03T12:00:00+00:00",
    }))
    verified = validate_restore_receipt(archive, receipt)
    assert verified["rows"] == 12 and verified["tables"] == 3
    archive.write_bytes(b"changed")
    try:
        validate_restore_receipt(archive, receipt)
    except RuntimeError as exc:
        assert "backup bytes" in str(exc)
    else:
        raise AssertionError("receipt accepted different backup bytes")
