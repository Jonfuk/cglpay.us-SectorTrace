from __future__ import annotations

import pytest
from structlog.testing import capture_logs

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


def test_an_unwind_batch_logs_rows_bytes_and_transaction_time():
    """performance.md:586 -- rows/bytes per UNWIND batch and transaction time,
    benchmarking only. Structured event, not a warehouse row: nothing here
    reaches `graph_*` or the portal, so it cannot become the cross-layer
    arithmetic docs/CAVEATS.md forbids.

    `entity_type` is deliberately one `_LABELS` does not recognise, so this
    entity triggers exactly the one MERGE `_write` -- an entity type that
    matched a label would add a second, separately-logged `SET n:Label`
    UNWIND, which is a real batch but not what this assertion is about.
    """
    store = GraphStore(_settings(), driver=FakeDriver())
    with capture_logs() as events:
        store.upsert_entities([{
            "entity_id": "provider-1", "entity_type": "UNLABELLED_TYPE",
            "canonical_name": "Example Provider", "status": "active",
        }])
    batches = [event for event in events if event["event"] == "graph.store_unwind_batch"]
    assert len(batches) == 1
    assert batches[0]["rows"] == 1
    assert batches[0]["bytes"] > 0
    assert batches[0]["duration_seconds"] >= 0


def test_an_unwind_batch_is_logged_once_per_statement_including_label_writes():
    """A PROVIDER row triggers two Neo4j statements -- the entity MERGE and
    the label SET `upsert_entities` issues per matching `_LABELS` group -- and
    performance.md:586 wants a transaction-time reading for each, not one
    number averaged across a call that is not one transaction."""
    store = GraphStore(_settings(), driver=FakeDriver())
    with capture_logs() as events:
        store.upsert_entities([{
            "entity_id": "provider-1", "entity_type": "PROVIDER",
            "canonical_name": "Example Provider", "status": "active",
        }])
    batches = [event for event in events if event["event"] == "graph.store_unwind_batch"]
    assert len(batches) == 2
    assert all(batch["rows"] == 1 for batch in batches)


def test_schema_ddl_is_not_logged_as_an_unwind_batch():
    """`ensure_schema`'s CREATE CONSTRAINT/INDEX statements carry no `rows`
    parameter -- they are not the per-batch throughput this benchmarking
    exists to watch, and must not be counted as though they were."""
    store = GraphStore(_settings(), driver=FakeDriver())
    with capture_logs() as events:
        store.ensure_schema()
    assert not [event for event in events if event["event"] == "graph.store_unwind_batch"]


class _JmxSession:
    def __init__(self, outcome):
        self._outcome = outcome

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def run(self, query, parameters=None):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return _JmxResult(self._outcome)


class _JmxResult:
    def __init__(self, record):
        self._record = record

    def single(self):
        return self._record


class _JmxDriver:
    """Stands in for a real Bolt driver's one relevant behaviour for
    `jvm_metrics`: whether `CALL dbms.queryJmx(...)` answers or the server
    does not have the procedure at all, which is the expected case on a
    modern Neo4j 5 server (see the docstring on `jvm_metrics`)."""

    def __init__(self, outcome):
        self._outcome = outcome

    def session(self, database):
        return _JmxSession(self._outcome)


def test_jvm_metrics_is_best_effort_and_never_raises_when_unavailable():
    store = GraphStore(_settings(), driver=_JmxDriver(
        RuntimeError("Unknown procedure `dbms.queryJmx`")))
    with capture_logs() as events:
        result = store.jvm_metrics()
    assert result is None
    unavailable = [event for event in events if event["event"] == "graph.jvm_metrics_unavailable"]
    assert len(unavailable) == 1
    assert "dbms.queryJmx" in unavailable[0]["reason"]


def test_jvm_metrics_reads_attributes_when_the_procedure_answers():
    record = {"attributes": {"HeapMemoryUsage": {"used": 123456}}}
    store = GraphStore(_settings(), driver=_JmxDriver(record))
    with capture_logs() as events:
        result = store.jvm_metrics()
    assert result == record["attributes"]
    available = [event for event in events if event["event"] == "graph.jvm_metrics"]
    assert available[0]["available"] is True
