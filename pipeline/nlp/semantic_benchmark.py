"""Reproducible pgvector/HNSW parity and latency benchmark."""
from __future__ import annotations

import hashlib
import json
import platform
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from pipeline.nlp import embeddings
from pipeline.nlp.embedding_repository import PostgresEmbeddingRepository


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5))]


def _load_queries(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    queries = payload.get("queries") if isinstance(payload, dict) else payload
    if not isinstance(queries, list) or not queries:
        raise ValueError("semantic benchmark query file must contain a non-empty queries list")
    result = []
    for ordinal, item in enumerate(queries):
        if isinstance(item, str):
            item = {"id": f"q{ordinal + 1}", "query": item}
        if not isinstance(item, dict) or not str(item.get("query", "")).strip():
            raise ValueError(f"semantic benchmark query {ordinal + 1} has no query text")
        result.append({"id": str(item.get("id") or f"q{ordinal + 1}"),
                       "query": str(item["query"]).strip()})
    return result


def run(conn, *, queries_path: Path, model: str | None = None, depth: int = 20,
        warmups: int = 1, repetitions: int = 5, score_tolerance: float = 1e-6) -> dict:
    """Compare indexed results with a forced exact pgvector scan.

    Timing covers the indexed database query only; embedding time is reported
    separately. No result is persisted and no retrieval rank is treated as an
    evidence-quality measure.
    """
    queries = _load_queries(queries_path)
    embedder = embeddings.get_embedder(model)
    repository = PostgresEmbeddingRepository(conn)
    # The extension registers these settings when its library is loaded.  The
    # benchmark must make the indexed candidate search reproducible rather
    # than silently accepting a server-default recall setting; exact reranking
    # below remains the correctness boundary.
    conn.execute("SELECT NULL::public.vector OPERATOR(public.<=>) NULL::public.vector")
    conn.execute("SET hnsw.ef_search=1000")
    conn.execute("SET hnsw.max_scan_tuples=1000000")
    conn.execute("SET hnsw.iterative_scan=strict_order")
    cases = []
    all_parity = True
    for item in queries:
        started = time.perf_counter()
        vector = embedder.encode([item["query"]])[0]
        encode_ms = (time.perf_counter() - started) * 1000
        exact = repository.semantic_candidates(
            query_vector=vector, model_key=embedder.model_key, filter_sql="",
            filter_params=[], depth=depth, exact_baseline=True)
        for _ in range(max(0, warmups)):
            repository.semantic_candidates(
                query_vector=vector, model_key=embedder.model_key, filter_sql="",
                filter_params=[], depth=depth)
        timings = []
        indexed = []
        for _ in range(max(1, repetitions)):
            started = time.perf_counter()
            indexed = repository.semantic_candidates(
                query_vector=vector, model_key=embedder.model_key, filter_sql="",
                filter_params=[], depth=depth, exact_rerank=True)
            timings.append((time.perf_counter() - started) * 1000)
        same_ids = [row[0] for row in indexed] == [row[0] for row in exact]
        max_delta = max((abs(a[1] - b[1]) for a, b in zip(indexed, exact)), default=0.0)
        parity = same_ids and len(indexed) == len(exact) and max_delta <= score_tolerance
        all_parity = all_parity and parity
        cases.append({"id": item["id"], "query_sha256": hashlib.sha256(
            item["query"].encode()).hexdigest(), "result_ids": [row[0] for row in indexed],
            "parity": parity, "max_score_delta": max_delta, "encode_ms": round(encode_ms, 3),
            "indexed_ms": {"min": round(min(timings), 3),
                           "p50": round(statistics.median(timings), 3),
                           "p95": round(_percentile(timings, 0.95), 3),
                           "max": round(max(timings), 3)}})
    return {"created_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "platform": platform.platform(),
            "model_key": embedder.model_key,
            "model_revision": getattr(embedder, "revision_sha", None),
            "vector_count": repository.count(embedder.model_key), "depth": depth,
            "warmups": max(0, warmups), "repetitions": max(1, repetitions),
            "score_tolerance": score_tolerance, "all_parity": all_parity, "cases": cases,
            "caveat": "Latency is local to this run; result rank is retrieval, not evidence quality."}
