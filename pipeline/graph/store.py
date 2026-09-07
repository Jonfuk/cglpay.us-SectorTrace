"""Small, lifecycle-owning wrapper around the official Neo4j driver."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from typing import Any

import structlog

from pipeline.config import Settings

log = structlog.get_logger()

PROJECTOR_VERSION = "1"
_RELATIONSHIP_TYPE = re.compile(r"^[A-Z][A-Z0-9_]{0,62}$")
_LABELS = {
    "LOCAL_AUTHORITY": "LocalAuthority",
    "COMMISSIONING_AREA": "CommissioningArea",
    "PROVIDER": "Provider",
    "LEGAL_ENTITY": "LegalEntity",
    "SERVICE": "Service",
    "CONTRACT": "Contract",
    "DOCUMENT": "Document",
    "CQC_LOCATION": "CQCLocation",
    "GEOGRAPHY": "Geography",
}


class GraphStoreError(RuntimeError):
    """A graph-specific operational failure with no effect on the warehouse."""


class GraphStore:
    """The only component that owns Neo4j driver lifecycle and Cypher.

    The import is intentionally delayed.  A SQLite-only checkout can import
    every pipeline command without installing the optional graph extra.
    """

    def __init__(self, settings: Settings, driver: Any | None = None):
        self.settings = settings
        self._driver = driver

    def connect(self) -> None:
        if not self.settings.neo4j_enabled:
            raise GraphStoreError("Neo4j is disabled; set NEO4J_ENABLED=true for graph commands.")
        if self._driver is not None:
            return
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - depends on install choice
            raise GraphStoreError("Install graph support with `uv sync --extra graph`.") from exc
        self._driver = GraphDatabase.driver(
            self.settings.neo4j_uri,
            auth=(self.settings.neo4j_user, self.settings.neo4j_password),
        )
        if self.settings.neo4j_verify_connectivity:
            self.healthcheck()

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def healthcheck(self) -> None:
        # The driver's database keyword on verify_connectivity() is currently
        # a preview API. A trivial query checks the configured database just as
        # thoroughly without surfacing that warning to every graph command.
        driver = self._require_driver()
        with driver.session(database=self.settings.neo4j_database) as session:
            session.run("RETURN 1").consume()

    def ensure_schema(self) -> None:
        statements = (
            "CREATE CONSTRAINT sectortrace_entity_id IF NOT EXISTS "
            "FOR (n:Entity) REQUIRE n.entity_id IS UNIQUE",
            "CREATE CONSTRAINT sectortrace_claim_id IF NOT EXISTS "
            "FOR (n:Claim) REQUIRE n.claim_id IS UNIQUE",
            "CREATE CONSTRAINT sectortrace_evidence_id IF NOT EXISTS "
            "FOR (n:Evidence) REQUIRE n.evidence_id IS UNIQUE",
            "CREATE INDEX sectortrace_entity_name IF NOT EXISTS "
            "FOR (n:Entity) ON (n.canonical_name)",
        )
        self._write_many(statements)

    def clear_managed_data(self) -> None:
        self._write(
            "MATCH (n {sectortrace_managed: true}) DETACH DELETE n",
            {},
        )

    def upsert_entities(self, rows: Iterable[dict]) -> int:
        items = list(rows)
        if not items:
            return 0
        self._write(
            "UNWIND $rows AS row "
            "MERGE (n:Entity {entity_id: row.entity_id}) "
            "SET n.canonical_name = row.canonical_name, n.entity_type = row.entity_type, "
            "n.status = row.status, n.sectortrace_managed = true",
            {"rows": items},
        )
        for entity_type, label in _LABELS.items():
            matching = [row for row in items if row["entity_type"] == entity_type]
            if matching:
                self._write(
                    f"UNWIND $rows AS row MATCH (n:Entity {{entity_id: row.entity_id}}) SET n:{label}",
                    {"rows": matching},
                )
        return len(items)

    def upsert_evidence(self, rows: Iterable[dict]) -> int:
        items = list(rows)
        if not items:
            return 0
        self._write(
            "UNWIND $rows AS row MERGE (n:Evidence {evidence_id: row.evidence_id}) "
            "SET n.source_system = row.source_system, n.source_url = row.source_url, "
            "n.retrieved_at = row.retrieved_at, n.payload_sha256 = row.payload_sha256, "
            "n.raw_object_path = row.raw_object_path, n.sectortrace_managed = true",
            {"rows": items},
        )
        return len(items)

    def upsert_claims(self, rows: Iterable[dict]) -> int:
        items = list(rows)
        if not items:
            return 0
        self._write(
            "UNWIND $rows AS row MERGE (n:Claim {claim_id: row.claim_id}) "
            "SET n.predicate = row.predicate, n.claim_text = row.claim_text, "
            "n.extraction_method = row.extraction_method, n.confidence = row.confidence, "
            "n.review_status = row.review_status, n.evidence_id = row.evidence_id, "
            "n.sectortrace_managed = true",
            {"rows": items},
        )
        self._write(
            "UNWIND $rows AS row MATCH (claim:Claim {claim_id: row.claim_id}) "
            "MATCH (entity:Entity {entity_id: row.subject_entity_id}) "
            "MERGE (claim)-[:ABOUT]->(entity)",
            {"rows": [row for row in items if row.get("subject_entity_id")]},
        )
        self._write(
            "UNWIND $rows AS row MATCH (claim:Claim {claim_id: row.claim_id}) "
            "MATCH (evidence:Evidence {evidence_id: row.evidence_id}) "
            "MERGE (claim)-[:SUPPORTED_BY]->(evidence)",
            {"rows": [row for row in items if row.get("evidence_id")]},
        )
        return len(items)

    def upsert_relationships(self, rows: Iterable[dict]) -> int:
        items = list(rows)
        grouped: dict[str, list[dict]] = {}
        for row in items:
            relationship_type = row["relationship_type"]
            if not _RELATIONSHIP_TYPE.fullmatch(relationship_type):
                raise GraphStoreError(f"Unsafe graph relationship type {relationship_type!r}.")
            grouped.setdefault(relationship_type, []).append(row)
        for relationship_type, group in grouped.items():
            self._write(
                f"UNWIND $rows AS row MATCH (a:Entity {{entity_id: row.subject_entity_id}}) "
                f"MATCH (b:Entity {{entity_id: row.object_entity_id}}) "
                f"MERGE (a)-[r:{relationship_type} {{relationship_id: row.relationship_id}}]->(b) "
                "SET r.predicate = row.predicate, r.evidence_id = row.evidence_id, "
                "r.claim_id = row.claim_id, r.valid_from = row.valid_from, r.valid_to = row.valid_to, "
                "r.confidence = row.confidence, r.derivation_type = row.derivation_type, "
                "r.derivation_version = row.derivation_version, r.sectortrace_managed = true",
                {"rows": group},
            )
        return len(items)

    def delete_entity(self, entity_id: str) -> None:
        self._write("MATCH (n:Entity {entity_id: $entity_id, sectortrace_managed: true}) DETACH DELETE n",
                    {"entity_id": entity_id})

    def delete_relationship(self, relationship_id: str) -> None:
        self._write("MATCH ()-[r {relationship_id: $relationship_id, sectortrace_managed: true}]->() DELETE r",
                    {"relationship_id": relationship_id})

    def _require_driver(self) -> Any:
        if self._driver is None:
            raise GraphStoreError("GraphStore.connect() must be called first.")
        return self._driver

    def _write_many(self, statements: Iterable[str]) -> None:
        for statement in statements:
            self._write(statement, {})

    def _write(self, query: str, parameters: dict) -> None:
        driver = self._require_driver()
        started = time.monotonic()
        with driver.session(database=self.settings.neo4j_database) as session:
            session.run(query, parameters).consume()
        # Benchmarking only (performance.md:586), never evidence: nothing here
        # is a `graph_*` warehouse row or portal-reachable, so it cannot become
        # the cross-layer arithmetic docs/CAVEATS.md forbids. Logged only for
        # an actual `UNWIND $rows` batch -- schema DDL and `clear_managed_data`
        # pass no `rows` and are not the per-batch throughput this exists to
        # watch.
        rows = parameters.get("rows")
        if isinstance(rows, list) and rows:
            log.info(
                "graph.store_unwind_batch", rows=len(rows),
                # `default=str` because a row can carry a datetime-shaped
                # value from the warehouse; approximate is enough for a
                # benchmarking byte count, and must never be the reason a
                # write fails.
                bytes=len(json.dumps(rows, default=str).encode("utf-8")),
                duration_seconds=round(time.monotonic() - started, 4),
            )

    def jvm_metrics(self) -> dict[str, Any] | None:
        """Best-effort JVM heap/page-cache read for benchmarking (performance.md:586).

        Out of scope for this Bolt client by default: Neo4j 5 dropped the
        `dbms.queryJmx` procedure this used to answer, and heap/page-cache
        live only in the server's own metrics exporter (Prometheus/CSV/JMX),
        which is an operator deployment concern this process has no route to
        -- there is no equivalent Cypher call to fall back to. The attempt
        below costs nothing when it fails (an older server, or a build with
        the legacy procedure restored, would still answer it) and a rebuild
        must never fail because a benchmarking read did, so every outcome is
        logged and swallowed rather than raised.
        """
        driver = self._require_driver()
        try:
            with driver.session(database=self.settings.neo4j_database) as session:
                record = session.run(
                    "CALL dbms.queryJmx('java.lang:type=Memory') YIELD attributes "
                    "RETURN attributes"
                ).single()
        except Exception as exc:
            log.info("graph.jvm_metrics_unavailable", reason=str(exc))
            return None
        attributes = dict(record["attributes"]) if record else None
        log.info("graph.jvm_metrics", available=attributes is not None)
        return attributes
