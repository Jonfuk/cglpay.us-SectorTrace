"""Append-only PostgreSQL lineage for evidence and analytical outputs.

The vocabulary mirrors PROV's generated/used shape without making a second
provenance store authoritative.  Neo4j may project these rows, but it never
owns or edits them.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from pipeline.analysis.operations import utcnow

OBJECT_KINDS = frozenset({
    "source", "retrieval", "archive_object", "document_version", "element",
    "nlp_output", "claim", "entity", "relationship", "analysis",
    "published_output",
})


def _id(kind: str, canonical_id: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{canonical_id}".encode()).hexdigest()
    return f"lineage-{digest}"


def add_object(conn, *, kind: str, canonical_id: str, source_url: str | None = None,
               retrieved_at: str | None = None, payload_sha256: str | None = None,
               processor_version: str | None = None,
               metadata: dict[str, Any] | None = None, restricted: bool = False) -> str:
    """Insert an immutable object identity; an existing identity is untouched."""
    if kind not in OBJECT_KINDS:
        raise ValueError(f"unknown lineage object kind {kind!r}")
    if not canonical_id:
        raise ValueError("lineage canonical_id must not be empty")
    lineage_id = _id(kind, canonical_id)
    encoded_metadata = json.dumps(metadata or {}, sort_keys=True)
    conn.execute(
        "INSERT INTO lineage_objects (lineage_id, object_kind, canonical_id, source_url, "
        "retrieved_at, payload_sha256, processor_version, metadata_json, restricted, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (lineage_id, kind, canonical_id, source_url, retrieved_at, payload_sha256,
         processor_version, encoded_metadata, int(restricted), utcnow()))
    stored = conn.execute(
        "SELECT source_url, retrieved_at, payload_sha256, processor_version, metadata_json, restricted "
        "FROM lineage_objects WHERE lineage_id = %s", (lineage_id,)).fetchone()
    expected = {"source_url": source_url, "retrieved_at": retrieved_at,
                "payload_sha256": payload_sha256, "processor_version": processor_version}
    conflicts = [name for name, value in expected.items()
                 if value is not None and stored[name] != value]
    if metadata is not None and stored["metadata_json"] != encoded_metadata:
        conflicts.append("metadata_json")
    if bool(stored["restricted"]) != bool(restricted):
        conflicts.append("restricted")
    if conflicts:
        raise ValueError(
            f"lineage identity {kind}/{canonical_id} conflicts on {sorted(set(conflicts))}")
    return lineage_id


def add_edge(conn, *, generated_id: str, used_id: str, activity: str,
             activity_version: str | None = None,
             metadata: dict[str, Any] | None = None) -> str:
    """Record that ``generated_id`` was produced using ``used_id``."""
    canonical = "\0".join((generated_id, used_id, activity, activity_version or ""))
    edge_id = f"lineage-edge-{hashlib.sha256(canonical.encode()).hexdigest()}"
    encoded_metadata = json.dumps(metadata or {}, sort_keys=True)
    conn.execute(
        "INSERT INTO lineage_edges (lineage_edge_id, generated_lineage_id, used_lineage_id, "
        "activity, activity_version, metadata_json, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
        (edge_id, generated_id, used_id, activity, activity_version,
         encoded_metadata, utcnow()))
    stored = conn.execute(
        "SELECT metadata_json FROM lineage_edges WHERE lineage_edge_id = %s", (edge_id,)).fetchone()
    if stored is None or stored["metadata_json"] != encoded_metadata:
        raise ValueError("lineage edge identity conflicts with immutable metadata")
    return edge_id


def add_document_element_paths(conn, element_ids: Iterable[str]) -> dict[str, str]:
    """Materialise source→retrieval→archive→version→element paths in one read.

    Only identifiers and existing provenance are copied. Missing archive rows
    remain absent rather than being guessed from a path prefix.
    """
    ids = list(dict.fromkeys(str(value) for value in element_ids if value))
    if not ids:
        return {}
    marks = ", ".join("%s" for _ in ids)
    rows = conn.execute(
        "SELECT de.document_element_id, de.document_version_id, dv.parser_name, "
        "dv.parser_version, d.evidence_id, e.source_system, e.source_url, e.retrieved_at, "
        "e.payload_sha256, ao.object_id FROM document_elements de "
        "JOIN document_versions dv ON dv.document_version_id = de.document_version_id "
        "JOIN document_records d ON d.document_id = dv.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "LEFT JOIN archive_objects ao ON ao.payload_sha256 = e.payload_sha256 "
        "AND ao.source_system = e.source_system "
        f"WHERE de.document_element_id IN ({marks}) ORDER BY de.document_element_id, ao.object_id",
        ids).fetchall()
    result: dict[str, str] = {}
    seen: set[str] = set()
    for row in rows:
        element_id = row["document_element_id"]
        if element_id in seen:  # one deterministic archive object per payload
            continue
        seen.add(element_id)
        source = add_object(conn, kind="source", canonical_id=row["source_system"])
        retrieval = add_object(
            conn, kind="retrieval", canonical_id=row["evidence_id"],
            source_url=row["source_url"], retrieved_at=row["retrieved_at"],
            payload_sha256=row["payload_sha256"])
        add_edge(conn, generated_id=retrieval, used_id=source, activity="retrieval")
        prior = retrieval
        if row["object_id"]:
            archive = add_object(
                conn, kind="archive_object", canonical_id=row["object_id"],
                payload_sha256=row["payload_sha256"])
            add_edge(conn, generated_id=archive, used_id=retrieval, activity="archive")
            prior = archive
        document_version = add_object(
            conn, kind="document_version", canonical_id=row["document_version_id"],
            processor_version=f"{row['parser_name']}:{row['parser_version']}")
        add_edge(conn, generated_id=document_version, used_id=prior, activity="parse",
                 activity_version=f"{row['parser_name']}:{row['parser_version']}")
        element = add_object(conn, kind="element", canonical_id=element_id)
        add_edge(conn, generated_id=element, used_id=document_version, activity="segment")
        result[element_id] = element
    return result


def paths(conn, canonical_id: str, *, include_restricted: bool = False,
          limit: int = 200) -> list[dict[str, Any]]:
    """Return a bounded transitive trace; restricted objects stay excluded by default."""
    seed_clause = "" if include_restricted else "AND seed.restricted = 0"
    recursive_join = "" if include_restricted else (
        "JOIN lineage_objects recursive_used ON recursive_used.lineage_id = edge.used_lineage_id "
        "AND recursive_used.restricted = 0 ")
    row_clause = "" if include_restricted else (
        "AND generated.restricted = 0 AND COALESCE(used.restricted, 0) = 0")
    rows = conn.execute(
        "WITH RECURSIVE walk(lineage_id, depth, visited) AS ("
        "SELECT seed.lineage_id, 0, ARRAY[seed.lineage_id] FROM lineage_objects seed "
        f"WHERE seed.canonical_id = %s {seed_clause} UNION ALL "
        "SELECT edge.used_lineage_id, walk.depth + 1, walk.visited || edge.used_lineage_id "
        "FROM walk JOIN lineage_edges edge ON edge.generated_lineage_id = walk.lineage_id "
        f"{recursive_join}"
        "WHERE walk.depth < 64 AND NOT edge.used_lineage_id = ANY(walk.visited)) "
        "SELECT walk.depth, generated.object_kind, generated.canonical_id, generated.source_url, "
        "generated.retrieved_at, generated.payload_sha256, edge.activity, edge.activity_version, "
        "used.object_kind AS used_object_kind, used.canonical_id AS used_canonical_id, "
        "used.source_url AS used_source_url, used.retrieved_at AS used_retrieved_at, "
        "used.payload_sha256 AS used_payload_sha256 FROM walk "
        "JOIN lineage_objects generated ON generated.lineage_id = walk.lineage_id "
        "LEFT JOIN lineage_edges edge ON edge.generated_lineage_id = generated.lineage_id "
        "LEFT JOIN lineage_objects used ON used.lineage_id = edge.used_lineage_id "
        f"WHERE TRUE {row_clause} "
        "ORDER BY walk.depth, edge.created_at, edge.lineage_edge_id LIMIT %s",
        (canonical_id, max(1, min(int(limit), 500)))).fetchall()
    return [dict(row) for row in rows]
