from __future__ import annotations

import pytest

from pipeline.config import Settings
from pipeline.graph.store import GraphStore, GraphStoreError


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
        self.calls = []
        self.checked = []

    def session(self, database):
        self.checked.append(database)
        return FakeSession(self.calls)

    def verify_connectivity(self, database):
        self.checked.append(database)

    def close(self):
        return None


def _settings():
    return Settings(contact_email="test@example.com", neo4j_enabled=True,
                    neo4j_password="test-password", _env_file=None)


def test_schema_and_entity_upsert_are_idempotent_by_stable_id():
    driver = FakeDriver()
    store = GraphStore(_settings(), driver=driver)
    store.ensure_schema()
    store.upsert_entities([{
        "entity_id": "provider-1", "entity_type": "PROVIDER",
        "canonical_name": "Example Provider", "status": "active",
    }])
    queries = "\n".join(call[0] for call in driver.calls)
    assert "CREATE CONSTRAINT sectortrace_entity_id" in queries
    assert "MERGE (n:Entity {entity_id: row.entity_id})" in queries
    assert "SET n:Provider" in queries


def test_relationship_type_is_validated_before_cypher_is_built():
    store = GraphStore(_settings(), driver=FakeDriver())
    with pytest.raises(GraphStoreError, match="Unsafe graph relationship type"):
        store.upsert_relationships([{
            "relationship_type": "RELATED_TO} DELETE n //",
        }])
