"""Exact projector parity (performance.md:588-589).

`GraphProjector.rebuild()` is only trusted to replay PostgreSQL into Neo4j
if a redesign of it cannot silently drop or misrender a node, an edge, a
relationship's type or properties, an evidence reference, or a count. The
other graph tests either record which store method was called
(`test_graph_projector.py`'s `RecordingStore`, which never builds real
Cypher) or exercise `GraphStore` against hand-built rows
(`test_graph_store.py`). Neither, alone, catches a redesign that changes
what actually reaches Neo4j for real warehouse data. This test runs the real
`GraphStore` (real Cypher, MERGE and all) behind the same `FakeDriver`/
`FakeSession` fake `test_graph_store.py` uses, driven by
`GraphProjector.rebuild()` against a small fixture warehouse -- so every
assertion below reads the exact query text and parameters Neo4j would have
received, and every count is checked against the canonical PostgreSQL rows
directly, not against the projector's own report of itself.
"""
from __future__ import annotations

from pathlib import Path

from pipeline import db
from pipeline.config import Settings
from pipeline.graph.projector import GraphProjector
from pipeline.graph.store import GraphStore


class FakeResult:
    def consume(self):
        return None


class FakeSession:
    def __init__(self, calls):
        self.calls = calls

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def run(self, query, parameters):
        self.calls.append((query, parameters))
        return FakeResult()


class FakeDriver:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def session(self, database):
        return FakeSession(self.calls)


def _conn(tmp_path: Path):
    settings = Settings(contact_email="test@example.com", database_path=tmp_path / "warehouse.db",
                        migrations_dir=Path("pipeline/migrations"), _env_file=None)
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    return conn


def _insert_entity(conn, entity_id: str, entity_type: str, name: str) -> None:
    conn.execute(
        "INSERT INTO entities (entity_id, entity_type, canonical_name, canonical_name_normalized, "
        "status, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (entity_id, entity_type, name, name.casefold(), "active", "now", "now"))


def _seed_fixture_warehouse(conn) -> None:
    """Two authorities, two providers, one evidence record, one claim, and
    one relationship tying an authority to a provider -- small enough to
    check every field by hand, and touching every table the projector reads
    (`entities`, `evidence_records`, `graph_claims`, `entity_relationships`)."""
    _insert_entity(conn, "authority:E00000001", "LOCAL_AUTHORITY", "Example Council")
    _insert_entity(conn, "authority:E00000002", "LOCAL_AUTHORITY", "Second Council")
    _insert_entity(conn, "provider:example-provider", "PROVIDER", "Example Provider")
    _insert_entity(conn, "provider:second-provider", "PROVIDER", "Second Provider")
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, retrieved_at, "
        "http_status, payload_sha256, raw_object_path, created_at) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s)",
        ("evidence:fts:hash-1", "fts", "https://example.test/notice", "now", 200,
         "hash-1", "data/raw/fts/hash-1.json", "now"))
    conn.execute(
        "INSERT INTO graph_claims (claim_id, subject_entity_id, predicate, object_literal, "
        "claim_text, evidence_id, extraction_method, confidence, review_status, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("claim:1", "provider:example-provider", "OPERATES", "true",
         "Example Provider operates services.", "evidence:fts:hash-1", "parser", 0.9, "draft", "now"))
    conn.execute(
        "INSERT INTO entity_relationships (relationship_id, subject_entity_id, predicate, "
        "object_entity_id, relationship_type, evidence_id, claim_id, valid_from, valid_to, "
        "confidence, derivation_type, derivation_version, created_at, updated_at) VALUES "
        "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        ("relationship:1", "authority:E00000001", "AWARDED_TO", "provider:example-provider",
         "AWARDED_TO", "evidence:fts:hash-1", "claim:1", "2024-01-01", "2025-01-01", 1.0,
         "SOURCE_FACT", "1", "now", "now"))
    conn.commit()


def _calls_matching(driver: FakeDriver, needle: str) -> list[tuple[str, dict]]:
    return [call for call in driver.calls if needle in call[0]]


def test_rebuild_reaches_neo4j_with_exact_node_edge_and_reference_parity(tmp_path):
    conn = _conn(tmp_path)
    _seed_fixture_warehouse(conn)

    # The canonical counts this test holds the projector to -- read straight
    # from PostgreSQL, independent of anything `rebuild()` reports about
    # itself, per performance.md:588-589's "matching the canonical source
    # rows exactly".
    canonical_entities = conn.execute("SELECT COUNT(*) AS n FROM entities").fetchone()["n"]
    canonical_authorities = conn.execute(
        "SELECT COUNT(*) AS n FROM entities WHERE entity_type = 'LOCAL_AUTHORITY'").fetchone()["n"]
    canonical_providers = conn.execute(
        "SELECT COUNT(*) AS n FROM entities WHERE entity_type = 'PROVIDER'").fetchone()["n"]
    canonical_evidence = conn.execute("SELECT COUNT(*) AS n FROM evidence_records").fetchone()["n"]
    canonical_claims = conn.execute("SELECT COUNT(*) AS n FROM graph_claims").fetchone()["n"]
    canonical_relationships = conn.execute(
        "SELECT COUNT(*) AS n FROM entity_relationships").fetchone()["n"]
    relationship_row = conn.execute(
        "SELECT * FROM entity_relationships WHERE relationship_id = 'relationship:1'").fetchone()

    driver = FakeDriver()
    store = GraphStore(Settings(contact_email="test@example.com", _env_file=None), driver=driver)
    result = GraphProjector(conn, store, batch_size=500).rebuild(clear=True)

    # The projector's own report agrees with the canonical warehouse counts...
    assert result["entities"] == canonical_entities == 4
    assert result["evidence"] == canonical_evidence == 1
    assert result["claims"] == canonical_claims == 1
    assert result["relationships"] == canonical_relationships == 1

    # ...and so, independently, does what actually reached the fake Neo4j
    # session. Exactly one entity MERGE call, carrying every entity row and
    # no more, no fewer.
    entity_merges = _calls_matching(driver, "MERGE (n:Entity {entity_id: row.entity_id})")
    assert len(entity_merges) == 1
    entity_ids = {row["entity_id"] for row in entity_merges[0][1]["rows"]}
    assert entity_ids == {
        "authority:E00000001", "authority:E00000002",
        "provider:example-provider", "provider:second-provider",
    }

    # Exact label parity: every LocalAuthority row got that label and no
    # other, same for Provider -- not a count that happens to match by
    # coincidence of totals.
    authority_labels = _calls_matching(driver, "SET n:LocalAuthority")
    assert len(authority_labels) == 1
    assert {row["entity_id"] for row in authority_labels[0][1]["rows"]} == {
        "authority:E00000001", "authority:E00000002"}
    assert len(authority_labels[0][1]["rows"]) == canonical_authorities

    provider_labels = _calls_matching(driver, "SET n:Provider")
    assert len(provider_labels) == 1
    assert {row["entity_id"] for row in provider_labels[0][1]["rows"]} == {
        "provider:example-provider", "provider:second-provider"}
    assert len(provider_labels[0][1]["rows"]) == canonical_providers

    # Evidence node: exact reference fields, not just a count.
    evidence_merges = _calls_matching(driver, "MERGE (n:Evidence {evidence_id: row.evidence_id})")
    assert len(evidence_merges) == 1
    assert len(evidence_merges[0][1]["rows"]) == canonical_evidence
    evidence_row = evidence_merges[0][1]["rows"][0]
    assert evidence_row["evidence_id"] == "evidence:fts:hash-1"
    assert evidence_row["source_url"] == "https://example.test/notice"
    assert evidence_row["payload_sha256"] == "hash-1"

    # Claim node plus both its edges: the evidence reference and the subject
    # link a claim carries are exact properties, not summarised away.
    claim_merges = _calls_matching(driver, "MERGE (n:Claim {claim_id: row.claim_id})")
    assert len(claim_merges) == 1
    assert len(claim_merges[0][1]["rows"]) == canonical_claims
    claim_row = claim_merges[0][1]["rows"][0]
    assert claim_row["claim_id"] == "claim:1"
    assert claim_row["evidence_id"] == "evidence:fts:hash-1"

    about_edges = _calls_matching(driver, "MERGE (claim)-[:ABOUT]->(entity)")
    assert len(about_edges) == 1
    assert about_edges[0][1]["rows"] == [{
        "claim_id": "claim:1", "predicate": "OPERATES", "claim_text": "Example Provider operates services.",
        "extraction_method": "parser", "confidence": 0.9, "review_status": "draft",
        "evidence_id": "evidence:fts:hash-1", "subject_entity_id": "provider:example-provider",
    }]

    supported_by_edges = _calls_matching(driver, "MERGE (claim)-[:SUPPORTED_BY]->(evidence)")
    assert len(supported_by_edges) == 1
    assert len(supported_by_edges[0][1]["rows"]) == 1

    # Relationship: exact type, exact endpoints, exact properties -- every
    # field the fixture set, read back from the Cypher call rather than
    # assumed from the count.
    relationship_merges = _calls_matching(driver, "MERGE (a)-[r:AWARDED_TO")
    assert len(relationship_merges) == 1
    assert len(relationship_merges[0][1]["rows"]) == canonical_relationships
    projected = relationship_merges[0][1]["rows"][0]
    assert projected["relationship_id"] == relationship_row["relationship_id"]
    assert projected["subject_entity_id"] == relationship_row["subject_entity_id"]
    assert projected["object_entity_id"] == relationship_row["object_entity_id"]
    assert projected["predicate"] == relationship_row["predicate"]
    assert projected["evidence_id"] == relationship_row["evidence_id"]
    assert projected["claim_id"] == relationship_row["claim_id"]
    assert projected["valid_from"] == relationship_row["valid_from"]
    assert projected["valid_to"] == relationship_row["valid_to"]
    assert projected["confidence"] == relationship_row["confidence"]
    assert projected["derivation_type"] == relationship_row["derivation_type"]
    assert projected["derivation_version"] == relationship_row["derivation_version"]

    # No other relationship type was invented or merged: the fixture has one
    # relationship, `upsert_relationships` groups by type before writing, and
    # there is exactly one such write in total.
    assert len(_calls_matching(driver, "MERGE (a)-[r:")) == 1

    conn.close()
