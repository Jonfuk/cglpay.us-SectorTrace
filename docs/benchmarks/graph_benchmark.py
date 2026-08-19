"""Development-only bounded NetworkX benchmark; intentionally not a CI test."""
from __future__ import annotations

import time

import networkx as nx


def main() -> None:
    nodes, edges = 10_000, 50_000
    started = time.perf_counter()
    graph = nx.gnm_random_graph(nodes, edges, seed=76)
    built = time.perf_counter()
    components = nx.number_connected_components(graph)
    analysed = time.perf_counter()
    print(f"nodes={nodes:,} edges={edges:,} build_seconds={built - started:.3f} "
          f"analysis_seconds={analysed - built:.3f} components={components}")


if __name__ == "__main__":
    main()
