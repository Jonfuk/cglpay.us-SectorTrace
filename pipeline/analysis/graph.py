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


class SignalGraphStore:
    """Small driver wrapper whose Cypher never mentions canonical Claim nodes."""

    def __init__(self, driver: Any):
        self.driver = driver

    def ensure_schema(self) -> None:
        with self.driver.session() as session:
            for label in NODE_LABELS:
                session.run(f"CREATE INDEX signal_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) ON (n.id)").consume()

    def _run(self, query: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self.driver.session() as session:
            session.run(query, rows=rows).consume()
        return len(rows)

    def upsert_releases(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n:AnalysisRelease {id: row.id}) SET n.status=row.status, n.manifest_sha256=row.manifest_sha256", list(rows))

    def upsert_signals(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n:AutomatedSignal {id: row.id}) SET n.domain_id=row.domain_id, n.signal_type=row.signal_type, n.subject_id=row.subject_id, n.direction=row.direction, n.assertion_status=row.assertion_status, n.human_verified=false", list(rows))

    def upsert_structured(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n:StructuredSignal {id: row.id}) SET n.signal_id=row.signal_id, n.metric=row.metric, n.absolute_change=row.absolute_change, n.robust_z=row.robust_z", list(rows))

    def upsert_themes(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MERGE (n:EmergingTheme {id: row.id}) SET n.domain_id=row.domain_id, n.theme_key=row.theme_key, n.status=row.status", list(rows))

    def connect_release(self, rows: Iterable[dict[str, Any]]) -> int:
        return self._run("UNWIND $rows AS row MATCH (s:AutomatedSignal {id: row.signal_id}), (r:AnalysisRelease {id: row.release_id}) MERGE (s)-[:GENERATED_IN_RELEASE]->(r)", list(rows))


def project_release(conn, store: SignalGraphStore, release_id: str) -> dict[str, Any]:
    run_id = f"signal-graph-run-{uuid.uuid4()}"
    conn.execute("INSERT INTO signal_graph_projection_runs (run_id, release_id, started_at, status) VALUES (?, ?, ?, 'running')", (run_id, release_id, utcnow()))
    conn.commit()
    try:
        store.ensure_schema()
        release = conn.execute("SELECT release_id AS id, status, manifest_sha256 FROM analysis_releases WHERE release_id = ?", (release_id,)).fetchone()
        if release is None:
            raise SignalGraphError(f"unknown analysis release {release_id!r}")
        signals = [dict(row) for row in conn.execute("SELECT signal_id AS id, domain_id, signal_type, subject_id, direction, assertion_status FROM automated_signals WHERE release_id = ?", (release_id,))]
        structured = [dict(row) for row in conn.execute("SELECT structured_signal_id AS id, signal_id, metric, absolute_change, robust_z FROM structured_signals WHERE signal_id IN (SELECT signal_id FROM automated_signals WHERE release_id = ?)", (release_id,))]
        themes = [dict(row) for row in conn.execute("SELECT theme_id AS id, domain_id, theme_key, status FROM emerging_themes WHERE release_id = ?", (release_id,))]
        store.upsert_releases([dict(release)])
        store.upsert_signals(signals)
        store.upsert_structured(structured)
        store.upsert_themes(themes)
        store.connect_release([{"signal_id": row["id"], "release_id": release_id} for row in signals])
        result = {"run_id": run_id, "release_id": release_id, "signals": len(signals), "structured": len(structured), "themes": len(themes)}
        conn.execute("UPDATE signal_graph_projection_runs SET completed_at = ?, status = 'completed', signal_count = ?, theme_count = ? WHERE run_id = ?", (utcnow(), len(signals), len(themes), run_id))
        conn.commit()
        return result
    except Exception as exc:
        conn.execute("UPDATE signal_graph_projection_runs SET completed_at = ?, status = 'failed', error_detail = ? WHERE run_id = ?", (utcnow(), str(exc), run_id))
        conn.commit()
        raise


def save_entity_suggestion(conn, *, raw_name: str, raw_span: str | None = None,
                           signal_id: str | None = None, proposed_entity_type: str | None = None,
                           proposed_canonical_id: str | None = None,
                           identifier_evidence: list | None = None, model_outputs: list | None = None,
                           source_passage: str | None = None, rejection_reasons: list | None = None) -> str:
    suggestion_id = f"entity-suggestion-{uuid.uuid4()}"
    conn.execute("INSERT INTO entity_link_suggestions (suggestion_id, signal_id, raw_name, raw_span, proposed_entity_type, proposed_canonical_id, identifier_evidence_json, model_outputs_json, source_passage, rejection_reasons_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (suggestion_id, signal_id, raw_name, raw_span, proposed_entity_type, proposed_canonical_id, json.dumps(identifier_evidence or []), json.dumps(model_outputs or []), source_passage, json.dumps(rejection_reasons or []), utcnow()))
    return suggestion_id


def exact_entity_attachment(proposed_canonical_id: str | None, identifier_evidence: list | None) -> str | None:
    """Only deterministic exact identifiers may auto-attach."""
    if proposed_canonical_id and identifier_evidence and all(item.get("exact") is True for item in identifier_evidence if isinstance(item, dict)):
        return proposed_canonical_id
    return None
