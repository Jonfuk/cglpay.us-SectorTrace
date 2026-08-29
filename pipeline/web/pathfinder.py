"""Relationship pathfinder (BETA-093).

The shortest *verified* path between two entities through the source-backed
edges of `v_entity_edges`. A neighbourhood view says what surrounds one
entity; this says how two known entities are connected, and shows the source
behind every hop.

Three rules, from the objective:

  * **Verified edges only.** An edge whose `basis` is an unconfirmed name
    match — `name_only_unconfirmed`, `supplier_name_unmatched` — has not
    passed the review gate that would make it a fact (an alias confirmed into
    `supplier_aliases`, an identifier confirmed into `provider_identifiers`),
    so it is excluded. The restricted shared-officer edges are not in
    `v_entity_edges` at all and never reach here.
  * **Deterministic.** Neighbours are expanded in `(relationship, node id)`
    order, so among several shortest paths the same one is always returned.
  * **Bounded.** At most `_MAX_HOPS` hops; the frontier is capped.

Read-only. No new edge is written or inferred.
"""
from __future__ import annotations

import sqlite3
from collections import deque

from pipeline.web.public_queries import _public, _rows
from pipeline.web.queries import QueryError

# Bases that mean "matched on a name and nobody has confirmed it" — the
# review gate has not been passed, so the edge is not verified.
_UNVERIFIED_BASES = frozenset({
    "name_only_unconfirmed", "supplier_name_unmatched", "name_match_only",
    "", None,
})

# The entity kinds a caller may name as an endpoint. `v_entity_edges` also
# has `company` / `cqc_provider` / `tribunal_case` / scheme nodes, which a
# path can pass *through* but which are not useful things to ask about.
_ENDPOINT_TYPES = frozenset({"provider", "authority", "supplier"})

_MAX_HOPS = 6
_MAX_FRONTIER = 20_000

_REL_LABEL = {
    "registered_as": "is registered as the company",
    "identified_by": "is identified by",
    "cqc_registered_as": "is CQC-registered as",
    "awarded_contract_to": "awarded a contract to",
    "respondent_in": "was a respondent in",
}


def _node(kind: str, ident: str) -> str:
    return f"{kind}:{ident}"


def _load_adjacency(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    """Every verified edge as an undirected adjacency map. Edges are
    deduplicated on (source node, target node, relationship) so a provider
    with fifty contract notices to one authority is one edge, not fifty."""
    seen: set[tuple[str, str, str]] = set()
    adj: dict[str, list[dict]] = {}
    for row in _rows(conn, """
        SELECT source_type, source_id, relationship, target_type, target_id,
               target_label, basis, source_url, retrieved_at
        FROM v_entity_edges"""):
        if row["basis"] in _UNVERIFIED_BASES:
            continue
        a = _node(row["source_type"], row["source_id"])
        b = _node(row["target_type"], row["target_id"])
        if a == b:
            continue
        key = (a, b, row["relationship"])
        if key in seen:
            continue
        seen.add(key)
        edge = {
            "relationship": row["relationship"],
            "basis": row["basis"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "source_label": row["source_id"],
            "target_label": row["target_label"] or row["target_id"],
        }
        adj.setdefault(a, []).append({**edge, "to": b, "dir": "out"})
        adj.setdefault(b, []).append({
            **edge, "to": a, "dir": "in",
            "source_label": row["target_label"] or row["target_id"],
            "target_label": row["source_id"],
        })
    for node in adj:
        adj[node].sort(key=lambda e: (e["relationship"], e["to"]))
    return adj


def find_path(conn: sqlite3.Connection, *, from_type: str, from_id: str,
              to_type: str, to_id: str, max_hops: int = _MAX_HOPS) -> dict:
    _public(["v_entity_edges", "contracts", "companies", "cqc_providers",
              "provider_identifiers", "tribunal_cases", "supplier_aliases"])
    for kind in (from_type, to_type):
        if kind not in _ENDPOINT_TYPES:
            raise QueryError(
                f"endpoint kind must be one of {sorted(_ENDPOINT_TYPES)}, got {kind!r}")
    if not from_id or not to_id:
        raise QueryError("both endpoints need an id")
    max_hops = max(1, min(int(max_hops), 8))

    start, goal = _node(from_type, from_id), _node(to_type, to_id)
    common = {
        "from": {"type": from_type, "id": from_id, "node": start},
        "to": {"type": to_type, "id": to_id, "node": goal},
        "max_hops": max_hops,
        "verified_only": True,
        "note": "Only edges whose basis passed a review gate are followed — an "
                "unconfirmed name match is not a path. Among equally short "
                "paths the one first in (relationship, node id) order is "
                "returned.",
    }
    if start == goal:
        return {**common, "found": True, "hops": 0, "path": [],
                "nodes": [{"node": start, "type": from_type, "id": from_id}]}

    adj = _load_adjacency(conn)
    if start not in adj:
        return {**common, "found": False,
                "reason": f"{start} has no verified edges."}
    if goal not in adj:
        return {**common, "found": False,
                "reason": f"{goal} has no verified edges."}

    # BFS with a parent map; deterministic because each node's edge list is
    # pre-sorted and the queue is FIFO.
    parent: dict[str, tuple[str, dict]] = {start: ("", {})}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    visited = 0
    while queue:
        node, depth = queue.popleft()
        if depth >= max_hops:
            continue
        for edge in adj.get(node, ()):
            nxt = edge["to"]
            if nxt in parent:
                continue
            parent[nxt] = (node, edge)
            if nxt == goal:
                queue.clear()
                break
            queue.append((nxt, depth + 1))
            visited += 1
            if visited > _MAX_FRONTIER:
                return {**common, "found": False,
                        "reason": "search space too large; narrow the endpoints."}

    if goal not in parent:
        return {**common, "found": False,
                "reason": f"no verified path within {max_hops} hops."}

    # Walk back from the goal.
    chain: list[tuple[str, dict]] = []
    cur = goal
    while cur != start:
        prev, edge = parent[cur]
        chain.append((cur, edge))
        cur = prev
    chain.reverse()

    path = []
    nodes = [{"node": start, "type": from_type, "id": from_id}]
    cur = start
    for target_node, edge in chain:
        kind, ident = target_node.split(":", 1)
        path.append({
            "from": cur,
            "relationship": edge["relationship"],
            "relationship_label": _REL_LABEL.get(edge["relationship"], edge["relationship"]),
            "basis": edge["basis"],
            "to": target_node,
            "to_label": edge["target_label"],
            "source_url": edge["source_url"],
            "retrieved_at": edge["retrieved_at"],
        })
        nodes.append({"node": target_node, "type": kind, "id": ident,
                       "label": edge["target_label"]})
        cur = target_node

    return {**common, "found": True, "hops": len(path), "path": path, "nodes": nodes}
