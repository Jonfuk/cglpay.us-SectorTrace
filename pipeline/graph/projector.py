"""Replayable warehouse-to-Neo4j projection and transactional queue handling."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pipeline.graph.store import PROJECTOR_VERSION, GraphStore

SCHEMA_VERSION = "0050"

_PROJECTED_COLUMNS = {
    "entities": ("entity_id", "canonical_name", "entity_type", "status"),
    "evidence_records": ("evidence_id", "source_system", "source_url",
                          "retrieved_at", "payload_sha256", "raw_object_path"),
    "graph_claims": ("claim_id", "predicate", "claim_text", "extraction_method",
                      "confidence", "review_status", "evidence_id",
                      "subject_entity_id"),
    "entity_relationships": ("relationship_id", "subject_entity_id",
                              "object_entity_id", "relationship_type", "predicate",
                              "evidence_id", "claim_id", "valid_from", "valid_to",
                              "confidence", "derivation_type", "derivation_version"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphProjector:
    """Projects only warehouse records; ingestion modules never dual-write."""

    def __init__(self, conn: Any, store: GraphStore, batch_size: int = 500):
        self.conn = conn
        self.store = store
        self.batch_size = batch_size

    def rebuild(self, clear: bool = False) -> dict[str, int | str]:
        run_id = str(uuid.uuid4())
        started_at = _now()
        self.conn.execute(
            "INSERT INTO graph_projection_runs (run_id, started_at, status, schema_version, "
            "projector_version, warehouse_snapshot) VALUES (?, ?, 'running', ?, ?, ?)",
            (run_id, started_at, SCHEMA_VERSION, PROJECTOR_VERSION, started_at),
        )
        self.conn.commit()
        counts = {"entities": 0, "relationships": 0, "claims": 0, "evidence": 0}
        try:
            self.store.ensure_schema()
            if clear:
                self.store.clear_managed_data()
            counts["entities"] = self._project_table("entities", self.store.upsert_entities)
            counts["evidence"] = self._project_table("evidence_records", self.store.upsert_evidence)
            counts["claims"] = self._project_table("graph_claims", self.store.upsert_claims)
            counts["relationships"] = self._project_table(
                "entity_relationships", self.store.upsert_relationships)
        except Exception as exc:
            self.conn.execute(
                "UPDATE graph_projection_runs SET completed_at = ?, status = 'failed', "
                "error_count = 1, error_detail = ? WHERE run_id = ?",
                (_now(), str(exc), run_id),
            )
            self.conn.commit()
            raise
        self.conn.execute(
            "UPDATE graph_projection_runs SET completed_at = ?, status = 'completed', "
            "entity_count = ?, relationship_count = ?, claim_count = ? WHERE run_id = ?",
            (_now(), counts["entities"], counts["relationships"], counts["claims"], run_id),
        )
        self.conn.commit()
        return {"run_id": run_id, **counts}

    def sync_delta(self, limit: int = 500) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT * FROM graph_projection_queue WHERE processed_at IS NULL ORDER BY id LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        processed = 0
        failed = 0
        for row in rows:
            item = dict(row)
            try:
                self._sync_item(item)
                self.conn.execute(
                    "UPDATE graph_projection_queue SET processed_at = ?, attempt_count = attempt_count + 1, "
                    "last_error = NULL WHERE id = ?",
                    (_now(), item["id"]),
                )
                self.conn.commit()
                processed += 1
            except Exception as exc:
                self.conn.execute(
                    "UPDATE graph_projection_queue SET attempt_count = attempt_count + 1, last_error = ? "
                    "WHERE id = ?",
                    (str(exc), item["id"]),
                )
                self.conn.commit()
                failed += 1
        return {"processed": processed, "failed": failed}

    def status(self) -> dict[str, int]:
        pending = self.conn.execute(
            "SELECT COUNT(*) FROM graph_projection_queue WHERE processed_at IS NULL").fetchone()[0]
        return {"pending": int(pending)}

    def _project_table(self, table: str, upsert: Any) -> int:
        total = 0
        key = _PROJECTED_COLUMNS[table][0]
        columns = ", ".join(_PROJECTED_COLUMNS[table])
        last_key = None
        while True:
            if last_key is None:
                sql = (f"SELECT {columns} FROM {table} "
                       f"ORDER BY {key} LIMIT ?")
                params = (self.batch_size,)
            else:
                sql = (f"SELECT {columns} FROM {table} WHERE {key} > ? "
                       f"ORDER BY {key} LIMIT ?")
                params = (last_key, self.batch_size)
            rows = self.conn.execute(sql, params).fetchall()
            if not rows:
                return total
            total += upsert([dict(row) for row in rows])
            last_key = rows[-1][key]

    def _sync_item(self, item: dict) -> None:
        operation = item["operation"]
        object_type = item["object_type"]
        object_id = item["object_id"]
        if operation == "DELETE_ENTITY":
            self.store.delete_entity(object_id)
            return
        if operation == "DELETE_RELATIONSHIP":
            self.store.delete_relationship(object_id)
            return
        mapping = {
            "UPSERT_ENTITY": ("entities", "entity_id", self.store.upsert_entities),
            "UPSERT_EVIDENCE": ("evidence_records", "evidence_id", self.store.upsert_evidence),
            "UPSERT_CLAIM": ("graph_claims", "claim_id", self.store.upsert_claims),
            "UPSERT_RELATIONSHIP": ("entity_relationships", "relationship_id",
                                    self.store.upsert_relationships),
        }
        try:
            table, key, upsert = mapping[operation]
        except KeyError as exc:
            raise ValueError(f"Unknown graph projection operation {operation!r} for {object_type!r}.") from exc
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (object_id,)).fetchone()
        if row is None:
            raise ValueError(f"Queued {operation} refers to absent {table} record {object_id!r}.")
        upsert([dict(row)])
