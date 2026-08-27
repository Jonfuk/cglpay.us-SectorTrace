"""Retrieval eval harness -- the gate for changing the embedding model.

A model swap ("BGE looks better") is not a judgement call to make from a
demo. This scores a search mode against a human-marked query set and reports
Recall@k, MRR and nDCG@k, so "better" is a number measured the same way twice.

The query set is JSON, not YAML: every fixture in this repo is JSON and there
is no YAML dependency in the base install, and the eval must run in the
offline suite with nothing extra. Each entry:

    {
      "id": "recruit-retain",
      "query": "treatment providers struggling to recruit and retain staff",
      "source_system": "committee_paper_promotion",   # optional filter
      "relevant_markers": [
        "recruitment and retention remains the single biggest risk",
        "agency staff now cover a third of key-worker posts"
      ]
    }

A returned chunk is *relevant* if its text contains one of the markers
(case-insensitively). Markers are verbatim passages a person read and judged
on-topic -- content-derived chunk ids are not stable enough to paste into a
fixture, and a distinctive sentence is. `n_relevant` for a query is the
number of markers.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pipeline.nlp import semantic_search

DEFAULT_QUERY_SET = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "nlp"
    / "retrieval_queries.json")

_K = (5, 10)


def _load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    queries = data["queries"] if isinstance(data, dict) else data
    for entry in queries:
        if not entry.get("query"):
            raise ValueError(f"query {entry.get('id')!r} has no query text")
    # A query with no markers yet is kept and reported as `unmarked`, not
    # rejected: the campaign query set is grown against the live warehouse
    # one judged passage at a time, and a half-filled file must still run.
    return queries


def _relevant_ranks(results: list[dict], markers: list[str]) -> list[int]:
    """1-based ranks at which each distinct marker is first satisfied, sorted.

    One result can only discharge one marker, and one marker is credited
    once: two hits of the same passage are not two relevant documents.
    """
    lowered = [(i + 1, (r.get("text") or "").lower()) for i, r in enumerate(results)]
    ranks: list[int] = []
    used_positions: set[int] = set()
    for marker in markers:
        needle = marker.lower().strip()
        for pos, text in lowered:
            if pos in used_positions:
                continue
            if needle and needle in text:
                ranks.append(pos)
                used_positions.add(pos)
                break
    return sorted(ranks)


def _recall_at(ranks: list[int], n_relevant: int, k: int) -> float:
    if n_relevant == 0:
        return 0.0
    return sum(1 for r in ranks if r <= k) / n_relevant


def _dcg(ranks: set[int], k: int) -> float:
    return sum(1.0 / math.log2(r + 1) for r in ranks if r <= k)


def _ndcg_at(ranks: list[int], n_relevant: int, k: int) -> float:
    if n_relevant == 0:
        return 0.0
    ideal = _dcg(set(range(1, min(n_relevant, k) + 1)), k)
    if ideal == 0.0:
        return 0.0
    return _dcg(set(ranks), k) / ideal


def _aggregate(per_query: list[dict]) -> dict:
    """Averaged over the *marked* queries only -- an unmarked query has no
    ground truth to score against and would otherwise drag every metric to
    zero."""
    scored = [q for q in per_query if not q["unmarked"]]
    n = len(scored) or 1
    metrics: dict = {
        "scored_queries": len(scored),
        "mrr": round(sum(q["rr"] for q in scored) / n, 6),
    }
    for k in _K:
        metrics[f"recall@{k}"] = round(
            sum(q["recall"][f"@{k}"] for q in scored) / n, 6)
        metrics[f"ndcg@{k}"] = round(
            sum(q["ndcg"][f"@{k}"] for q in scored) / n, 6)
    return metrics


def run(conn, *, queries_path: Path | str | None = None, mode: str = "hybrid",
        model: str | None = None) -> dict:
    path = Path(queries_path) if queries_path else DEFAULT_QUERY_SET
    queries = _load(path)
    depth = max(_K)

    per_query: list[dict] = []
    for entry in queries:
        result = semantic_search.search(
            conn, entry["query"], mode=mode, limit=depth,
            source_system=entry.get("source_system"), model=model)
        markers = entry.get("relevant_markers") or []
        ranks = _relevant_ranks(result["results"], markers)
        per_query.append({
            "id": entry.get("id"),
            "query": entry["query"],
            "unmarked": not markers,
            "n_relevant": len(markers),
            "n_found": len(ranks),
            "first_rank": ranks[0] if ranks else None,
            "rr": round(1.0 / ranks[0], 6) if ranks else 0.0,
            "recall": {f"@{k}": round(_recall_at(ranks, len(markers), k), 6) for k in _K},
            "ndcg": {f"@{k}": round(_ndcg_at(ranks, len(markers), k), 6) for k in _K},
        })

    return {
        "queries_path": str(path),
        "mode": mode,
        "model": model,
        "n_queries": len(per_query),
        "metrics": _aggregate(per_query),
        "per_query": per_query,
    }
