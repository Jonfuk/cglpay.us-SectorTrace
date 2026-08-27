"""pipeline/nlp/resolve.py — deterministic PROVIDER/COMMISSIONER resolution."""
from __future__ import annotations

from pipeline.documents import repository
from pipeline.documents.models import EvidenceReference, ParsedDocument, ParsedElement
from pipeline.nlp import chunk as nlp_chunk
from pipeline.nlp import resolve, spans


def _seed_version(conn, settings, elements, *, evidence_id="ev-resolve",
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


def _seed_entity(conn, entity_id, entity_type, name):
    from pipeline.graph.backfill import _normalise
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, canonical_name_normalized, "
        "status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (entity_id, entity_type, name, _normalise(name),
         "2026-08-27T00:00:00+00:00", "2026-08-27T00:00:00+00:00"))


_ELEMENTS = [
    ParsedElement("HEADING", 1, text="Provider", page_number=1, heading_level=1),
    ParsedElement("PARAGRAPH", 2, text="Turning Point holds the contract. Change Grow Live "
                  "was the previous provider. Phoenix Futures was not shortlisted.",
                  parent_sequence=1, page_number=1),
]


def _prepare(conn, settings, **entity_kw):
    _seed_version(conn, settings, _ELEMENTS)
    for entity_id, entity_type, name in entity_kw.get("entities", []):
        _seed_entity(conn, entity_id, entity_type, name)
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    spans.run(conn, extractor="stub", source_system="committee_paper_promotion")


def test_exact_name_match_writes_an_entity_mention(conn, settings):
    _prepare(conn, settings, entities=[
        ("provider:turning_point", "PROVIDER", "Turning Point"),
        ("provider:change_grow_live", "PROVIDER", "Change Grow Live"),
    ])
    result = resolve.run(conn, source_system="committee_paper_promotion")
    assert result["resolved"] == 2

    rows = conn.execute(
        "SELECT entity_id, matched_text, match_method, start_offset, end_offset "
        "FROM document_entity_mentions ORDER BY entity_id").fetchall()
    assert [r["entity_id"] for r in rows] == ["provider:change_grow_live", "provider:turning_point"]
    assert all(r["match_method"] == "ontology-stub+alias" for r in rows)
    # offsets index the element text
    for row in rows:
        element_text = _ELEMENTS[1].text
        assert element_text[row["start_offset"]:row["end_offset"]] == row["matched_text"]

    run_row = conn.execute("SELECT stage, status FROM nlp_runs WHERE run_id=?",
                           (result["run_id"],)).fetchone()
    assert run_row["stage"] == "resolve" and run_row["status"] == "ok"


def test_a_span_with_no_registered_entity_stays_unresolved(conn, settings):
    # Phoenix Futures span is produced by the stub, but no entity row exists.
    _prepare(conn, settings, entities=[("provider:turning_point", "PROVIDER", "Turning Point")])
    result = resolve.run(conn)
    assert result["resolved"] == 1
    entity_ids = {r["entity_id"] for r in conn.execute(
        "SELECT entity_id FROM document_entity_mentions").fetchall()}
    assert entity_ids == {"provider:turning_point"}
    # the unresolved PROVIDER spans are still there as concept mentions
    assert conn.execute(
        "SELECT COUNT(*) FROM document_concept_mentions WHERE label='PROVIDER'").fetchone()[0] >= 2


def test_resolution_is_idempotent(conn, settings):
    _prepare(conn, settings, entities=[("provider:turning_point", "PROVIDER", "Turning Point")])
    resolve.run(conn)
    n1 = conn.execute("SELECT COUNT(*) FROM document_entity_mentions").fetchone()[0]
    resolve.run(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM document_entity_mentions").fetchone()[0]
    assert n1 == n2 == 1


def test_commissioner_span_resolves_to_a_local_authority(conn, settings):
    elements = [
        ParsedElement("HEADING", 1, text="Commissioning", page_number=1, heading_level=1),
        ParsedElement("PARAGRAPH", 2, text="The integrated care board and the combined authority "
                      "attended.", parent_sequence=1, page_number=1),
    ]
    _seed_version(conn, settings, elements)
    # the stub emits COMMISSIONER spans for ontology commissioner concepts;
    # only ones matching a LOCAL_AUTHORITY entity resolve.
    _seed_entity(conn, "authority:E06000001", "LOCAL_AUTHORITY", "integrated care board")
    nlp_chunk.run(conn, source_system="committee_paper_promotion")
    spans.run(conn, extractor="stub")
    result = resolve.run(conn)
    assert result["resolved"] == 1
    row = conn.execute("SELECT entity_id, match_method FROM document_entity_mentions").fetchone()
    assert row["entity_id"] == "authority:E06000001"


def test_dry_run_writes_nothing(conn, settings):
    _prepare(conn, settings, entities=[("provider:turning_point", "PROVIDER", "Turning Point")])
    result = resolve.run(conn, dry_run=True)
    assert result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_entity_mentions").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nlp_runs WHERE stage='resolve'").fetchone()[0] == 0
