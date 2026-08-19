"""Build deliberately bounded NetworkX projections from the warehouse."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import networkx as nx


class GraphTooLargeError(ValueError):
    """Raised before NetworkX is asked to load an unsafe graph selection."""


@dataclass(frozen=True)
class GraphSnapshot:
    graph: nx.Graph
    parameters: dict[str, Any]
    relationship_count: int


def build_commissioner_provider_graph(
    conn: Any,
    *,
    as_of: str | None = None,
    max_nodes: int = 10_000,
    max_edges: int = 50_000,
) -> GraphSnapshot:
    """Create the authority/provider bipartite graph from selected evidence.

    A connection means at least one recorded `COMMISSIONS` or `AWARDED_TO`
    relationship.  Multiple evidence records for the same pair deliberately
    remain one analytical edge: provider reach measures observed connections,
    not the number of source rows supporting each connection.
    """
    clauses = [
        "r.predicate IN ('COMMISSIONS', 'AWARDED_TO')",
        "source.entity_type = 'LOCAL_AUTHORITY'",
        "target.entity_type = 'PROVIDER'",
    ]
    params: list[Any] = []
    if as_of:
        clauses.extend(["(r.valid_from IS NULL OR r.valid_from <= ?)",
                        "(r.valid_to IS NULL OR r.valid_to >= ?)"])
        params.extend([as_of, as_of])
    where = " AND ".join(clauses)
    rows = conn.execute(
        "SELECT r.relationship_id, r.predicate, r.evidence_id, source.entity_id AS source_id, "
        "source.canonical_name AS source_name, target.entity_id AS target_id, "
        "target.canonical_name AS target_name "
        "FROM entity_relationships r "
        "JOIN entities source ON source.entity_id = r.subject_entity_id "
        "JOIN entities target ON target.entity_id = r.object_entity_id "
        f"WHERE {where} ORDER BY r.relationship_id LIMIT ?",
        [*params, max_edges + 1],
    ).fetchall()
    if len(rows) > max_edges:
        raise GraphTooLargeError(
            f"Commissioner-provider selection exceeds max_edges={max_edges}; narrow the filters.")
    graph = nx.Graph(kind="commissioner_provider", as_of=as_of)
    for row in rows:
        record = dict(row)
        graph.add_node(record["source_id"], entity_type="LOCAL_AUTHORITY",
                       canonical_name=record["source_name"])
        graph.add_node(record["target_id"], entity_type="PROVIDER",
                       canonical_name=record["target_name"])
        graph.add_edge(record["source_id"], record["target_id"],
                       predicates={record["predicate"]},
                       relationship_ids={record["relationship_id"]},
                       evidence_ids={record["evidence_id"]} - {None})
    if graph.number_of_nodes() > max_nodes:
        raise GraphTooLargeError(
            f"Commissioner-provider selection has {graph.number_of_nodes()} nodes, "
            f"above max_nodes={max_nodes}; narrow the filters.")
    return GraphSnapshot(
        graph=graph,
        parameters={"as_of": as_of, "max_nodes": max_nodes, "max_edges": max_edges},
        relationship_count=len(rows),
    )


def build_evidence_graph(
    conn: Any,
    *,
    relationship_type: str | None = None,
    max_nodes: int = 10_000,
    max_edges: int = 50_000,
) -> GraphSnapshot:
    """Build a bounded entity relationship graph for future evidence analysis."""
    where, params = "", []
    if relationship_type:
        where, params = " WHERE r.relationship_type = ?", [relationship_type]
    rows = conn.execute(
        "SELECT r.relationship_id, r.predicate, r.evidence_id, r.claim_id, "
        "r.subject_entity_id, r.object_entity_id FROM entity_relationships r"
        f"{where} ORDER BY r.relationship_id LIMIT ?", [*params, max_edges + 1]).fetchall()
    if len(rows) > max_edges:
        raise GraphTooLargeError(f"Evidence selection exceeds max_edges={max_edges}; narrow the filters.")
    graph = nx.MultiDiGraph(kind="evidence", relationship_type=relationship_type)
    for row in rows:
        record = dict(row)
        graph.add_edge(record["subject_entity_id"], record["object_entity_id"],
                       key=record["relationship_id"], **record)
    if graph.number_of_nodes() > max_nodes:
        raise GraphTooLargeError(
            f"Evidence selection has {graph.number_of_nodes()} nodes, above max_nodes={max_nodes}.")
    return GraphSnapshot(
        graph=graph,
        parameters={"relationship_type": relationship_type, "max_nodes": max_nodes,
                    "max_edges": max_edges},
        relationship_count=len(rows),
    )
