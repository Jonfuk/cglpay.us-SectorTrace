"""Initial neutral graph metrics and reproducible warehouse persistence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from pipeline.analytics.graph_builder import GraphSnapshot

ANALYSIS_VERSION = "1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def commissioner_provider_metrics(snapshot: GraphSnapshot) -> list[dict[str, Any]]:
    """Return unique observed counterpart counts and component membership.

    These are structural measures, not assertions about performance, funding,
    market dominance, or causal influence.
    """
    graph = snapshot.graph
    metrics: list[dict[str, Any]] = []
    components = list(nx.connected_components(graph))
    component_index = {node: number for number, members in enumerate(components, 1) for node in members}
    for entity_id, attrs in graph.nodes(data=True):
        counterpart_type = ("LOCAL_AUTHORITY" if attrs["entity_type"] == "PROVIDER" else "PROVIDER")
        reach = sum(1 for neighbour in graph.neighbors(entity_id)
                    if graph.nodes[neighbour]["entity_type"] == counterpart_type)
        metrics.extend([
            {"entity_id": entity_id, "metric_name": "observed_counterpart_count", "metric_value": reach},
            {"entity_id": entity_id, "metric_name": "connected_component", "metric_value": component_index[entity_id]},
        ])
    return metrics


def provider_network_metrics(snapshot: GraphSnapshot) -> list[dict[str, Any]]:
    """Project providers sharing an authority and calculate transparent metrics."""
    bipartite = snapshot.graph
    providers = [node for node, attrs in bipartite.nodes(data=True)
                 if attrs["entity_type"] == "PROVIDER"]
    projected = nx.bipartite.weighted_projected_graph(bipartite, providers)
    components = list(nx.connected_components(projected))
    component_index = {node: number for number, members in enumerate(components, 1) for node in members}
    degree = nx.degree_centrality(projected) if len(projected) > 1 else {node: 0.0 for node in providers}
    betweenness = nx.betweenness_centrality(projected, normalized=True)
    metrics: list[dict[str, Any]] = []
    for provider in providers:
        metrics.extend([
            {"entity_id": provider, "metric_name": "provider_network_degree_centrality",
             "metric_value": degree.get(provider, 0.0)},
            {"entity_id": provider, "metric_name": "provider_network_betweenness_centrality",
             "metric_value": betweenness.get(provider, 0.0)},
            {"entity_id": provider, "metric_name": "provider_network_component",
             "metric_value": component_index.get(provider, 0)},
        ])
    return metrics


def persist_metrics(
    conn: Any,
    metrics: list[dict[str, Any]],
    *,
    analysis_name: str,
    graph_snapshot: str,
    parameters: dict[str, Any],
    analysis_version: str = ANALYSIS_VERSION,
) -> int:
    """Store derived values with enough metadata to reproduce their meaning."""
    calculated_at = _now()
    parameter_json = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
    for metric in metrics:
        conn.execute(
            "INSERT INTO graph_metrics (entity_id, metric_name, metric_value, analysis_name, "
            "analysis_version, graph_snapshot, calculated_at, parameters_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(entity_id, metric_name, analysis_name, analysis_version, graph_snapshot) "
            "DO UPDATE SET metric_value = excluded.metric_value, calculated_at = excluded.calculated_at, "
            "parameters_json = excluded.parameters_json",
            (metric["entity_id"], metric["metric_name"], metric["metric_value"], analysis_name,
             analysis_version, graph_snapshot, calculated_at, parameter_json),
        )
    conn.commit()
    return len(metrics)
