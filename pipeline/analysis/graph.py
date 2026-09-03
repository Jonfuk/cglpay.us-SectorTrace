"""Optional Neo4j projection for automated analysis signals only."""
from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from pipeline.analysis.signals import utcnow

NODE_LABELS = ("AutomatedSignal", "StructuredSignal", "EmergingTheme", "AnalysisRelease")
EDGE_TYPES = ("DERIVED_FROM", "ABOUT_AUTHORITY", "ABOUT_PROVIDER", "ABOUT_METRIC",
              "RELATED_SIGNAL", "GENERATED_IN_RELEASE")


class SignalGraphError(RuntimeError):
    pass


def queue_release_projection(conn, release_id: str) -> dict[str, Any]:
    """Queue an isolated signal projection for a known analysis release."""
    release = conn.execute("SELECT release_id FROM analysis_releases WHERE release_id = %s", (release_id,)).fetchone()
    if release is None:
        raise KeyError(release_id)
    objects = [("release", release_id)]
    objects.extend(("signal", row["signal_id"]) for row in conn.execute(
        "SELECT signal_id FROM automated_signals WHERE release_id = %s", (release_id,)))
    objects.extend(("theme", row["theme_id"]) for row in conn.execute(
        "SELECT theme_id FROM emerging_themes WHERE release_id = %s", (release_id,)))
    pending = 0
    for object_type, object_id in objects:
        existing = conn.execute(
            "SELECT 1 FROM signal_graph_projection_queue WHERE release_id = %s AND object_type = %s "
            "AND object_id = %s AND processed_at IS NULL LIMIT 1",
            (release_id, object_type, object_id)).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO signal_graph_projection_queue (queue_id, release_id, object_type, object_id, operation, created_at) "
            "VALUES (%s, %s, %s, %s, 'upsert', %s)",
            (f"signal-graph-queue-{uuid.uuid4()}", release_id, object_type, object_id, utcnow()))
        pending += 1
    conn.commit()
    return {"release_id": release_id, "queued": pending, "status": "queued"}


def signal_store_from_settings(settings: Any) -> SignalGraphStore:
    """Build the optional Neo4j signal store, failing closed when disabled."""
    if not getattr(settings, "neo4j_enabled", False):
        raise SignalGraphError("Neo4j signal projection is disabled")
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise SignalGraphError("the graph extra is not installed") from exc
    driver = GraphDatabase.driver(settings.neo4j_uri,
                                  auth=(settings.neo4j_user, settings.neo4j_password))
    if getattr(settings, "neo4j_verify_connectivity", True):
        with driver.session(database=settings.neo4j_database) as session:
            session.run("RETURN 1").consume()
    return SignalGraphStore(driver, database=getattr(settings, "neo4j_database", None))


class SignalGraphStore:
    """Small driver wrapper whose Cypher never mentions canonical Claim nodes."""

    def __init__(self, driver: Any, *, database: str | None = None):
        self.driver = driver
        self.database = database

    def _session(self):
        return self.driver.session(database=self.database) if self.database else self.driver.session()

    def ensure_schema(self) -> None:
        with self._session() as session:
            for label in NODE_LABELS:
                session.run(f"CREATE INDEX signal_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) ON (n.id)").consume()

    def _run(self, query: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self._session() as session:
            session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_releases(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n%(AnalysisRelease)s {id: row.id}) SET n.status=row.status, n.manifest_sha256=row.manifest_sha256", list(rows))

    def upsert_signals(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n%(AutomatedSignal)s {id: row.id}) SET n.domain_id=row.domain_id, n.signal_type=row.signal_type, n.subject_id=row.subject_id, n.direction=row.direction, n.assertion_status=row.assertion_status, n.human_verified=false", list(rows))

    def upsert_structured(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n%(StructuredSignal)s {id: row.id}) SET n.signal_id=row.signal_id, n.metric=row.metric, n.absolute_change=row.absolute_change, n.robust_z=row.robust_z", list(rows))

    def upsert_themes(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n%(EmergingTheme)s {id: row.id}) SET n.domain_id=row.domain_id, n.theme_key=row.theme_key, n.status=row.status", list(rows))

    def connect_release(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MATCH (s:AutomatedSignal {id: row.signal_id}), (r:AnalysisRelease {id: row.release_id}) MERGE (s)-[:GENERATED_IN_RELEASE]->(r)", list(rows))


def project_release(conn, store: SignalGraphStore, release_id: str) -> dict[str, Any]:
    run_id = f"signal-graph-run-{uuid.uuid4()}"
    conn.execute("INSERT INTO signal_graph_projection_runs (run_id, release_id, started_at, status) VALUES (%s, %s, %s, 'running')", (run_id, release_id, utcnow()))
    conn.commit()
    try:
        store.ensure_schema()
        release = conn.execute("SELECT release_id AS id, status, manifest_sha256 FROM analysis_releases WHERE release_id = %s", (release_id,)).fetchone()
        if release is None:
            raise SignalGraphError(f"unknown analysis release {release_id!r}")
        signals = [dict(row) for row in conn.execute("SELECT signal_id AS id, domain_id, signal_type, subject_id, direction, assertion_status FROM automated_signals WHERE release_id = %s", (release_id,))]
        structured = [dict(row) for row in conn.execute("SELECT structured_signal_id AS id, signal_id, metric, absolute_change, robust_z FROM structured_signals WHERE signal_id IN (SELECT signal_id FROM automated_signals WHERE release_id = %s)", (release_id,))]
        themes = [dict(row) for row in conn.execute("SELECT theme_id AS id, domain_id, theme_key, status FROM emerging_themes WHERE release_id = %s", (release_id,))]
        store.upsert_releases([dict(release)])
        store.upsert_signals(signals)
        store.upsert_structured(structured)
        store.upsert_themes(themes)
        store.connect_release([{"signal_id": row["id"], "release_id": release_id} for row in signals])
        result = {"run_id": run_id, "release_id": release_id, "signals": len(signals), "structured": len(structured), "themes": len(themes)}
        conn.execute("UPDATE signal_graph_projection_runs SET completed_at = %s, status = 'completed', signal_count = %s, theme_count = %s WHERE run_id = %s", (utcnow(), len(signals), len(themes), run_id))
        conn.commit()
        return result
    except Exception as exc:
        conn.execute("UPDATE signal_graph_projection_runs SET completed_at = %s, status = 'failed', error_detail = %s WHERE run_id = %s", (utcnow(), str(exc), run_id))
        conn.commit()
        raise


def save_entity_suggestion(conn, *, raw_name: str, raw_span: str | None = None,
                           signal_id: str | None = None, proposed_entity_type: str | None = None,
                           proposed_canonical_id: str | None = None,
                           identifier_evidence: list | None = None, model_outputs: list | None = None,
                           source_passage: str | None = None, rejection_reasons: list | None = None) -> str:
    suggestion_id = f"entity-suggestion-{uuid.uuid4()}"
    conn.execute("INSERT INTO entity_link_suggestions (suggestion_id, signal_id, raw_name, raw_span, proposed_entity_type, proposed_canonical_id, identifier_evidence_json, model_outputs_json, source_passage, rejection_reasons_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", (suggestion_id, signal_id, raw_name, raw_span, proposed_entity_type, proposed_canonical_id, json.dumps(identifier_evidence or []), json.dumps(model_outputs or []), source_passage, json.dumps(rejection_reasons or []), utcnow()))
    return suggestion_id


def exact_entity_attachment(proposed_canonical_id: str | None, identifier_evidence: list | None) -> str | None:
    """Only deterministic exact identifiers may auto-attach."""
    if proposed_canonical_id and identifier_evidence and all(item.get("exact") is True for item in identifier_evidence if isinstance(item, dict)):
        return proposed_canonical_id
    return None
