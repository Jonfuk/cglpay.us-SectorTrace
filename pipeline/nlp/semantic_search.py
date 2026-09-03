"""Hybrid retrieval over `document_chunks` -- an `/api/admin/*` finding aid.

Three independent candidate paths:

* ``keyword`` -- the PostgreSQL ``tsvector`` full-text index over
  ``document_elements``, lifted from the matching *element* up to its
  containing *chunk* so every mode returns the same unit and the same ids.
* ``semantic`` -- cosine of the query embedding against ``document_embeddings``
  for one model, ordered in the database against the pgvector/HNSW index
  (migration 0071).
* ``fuzzy`` -- PostgreSQL pg_trgm over chunk text.
* ``hybrid`` -- Reciprocal Rank Fusion (k=60) of all three ranked lists. The
  default: keyword catches the literal term, semantic catches the paraphrase,
  and "services struggling to recruit enough workers" needs both.

A result is a passage that matched a query, not a finding. Nothing here
writes, promotes, or attributes anything -- that stays the review-queue ->
`graph_claims` path (migration 0050).
"""
from __future__ import annotations

from dataclasses import dataclass

from pipeline.config import get_settings
from pipeline.nlp import embeddings
from pipeline.nlp.embedding_repository import PostgresEmbeddingRepository

MODES = ("keyword", "fuzzy", "semantic", "hybrid")

# RRF's rank offset. 60 is the value from the paper everyone cites (Cormack et
# al., 2009) and the one Elasticsearch/OpenSearch default to; it damps the
# influence of a single list's top rank without a tuning pass this tranche
# cannot yet justify.
_RRF_K = 60

# How deep each mode ranks before fusion and truncation to `limit`. Wide
# enough that a chunk ranked outside one list can still be rescued by the
# other; bounded so each PostgreSQL candidate query and the fusion stay small.
_CANDIDATE_DEPTH = 200

_SNIPPET_MAX = 320

CAVEAT = (
    "This searches paragraph-level chunks of parsed committee papers and "
    "community drug partnership documents -- not the whole warehouse, and not "
    "every document type the pipeline collects. A result is a passage that "
    "matched the query (by wording, by embedding similarity, or both), not a "
    "finding: open the source page and its own caveats before citing anything."
)


class SearchError(ValueError):
    """A bad query or mode -- surfaced to the caller, not a 500."""


@dataclass
class Filters:
    """Metadata pre-filters, applied to the candidate chunk set in every mode
    so a filtered search is cheaper, not merely trimmed afterwards. 034A
    exposes what a chunk can be filtered by today; authority/provider joins
    arrive with the entity-mention tranches."""

    source_system: str | None = None
    date_from: str | None = None
    date_to: str | None = None

    def sql(self, *, evidence: str = "e", doc: str = "d") -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if self.source_system:
            clauses.append(f"{evidence}.source_system = %s")
            params.append(self.source_system)
        if self.date_from:
            clauses.append(f"{doc}.published_at >= %s")
            params.append(self.date_from)
        if self.date_to:
            clauses.append(f"{doc}.published_at <= %s")
            params.append(self.date_to)
        return (" AND " + " AND ".join(clauses) if clauses else ""), params

    def describe(self) -> dict:
        return {"source_system": self.source_system,
                "date_from": self.date_from, "date_to": self.date_to}


# --- keyword: FTS element hit -> containing chunk ---------------------------

def _element_to_chunk_sql(placeholders: str, filter_sql: str) -> str:
    """Map a set of matched element ids to the live chunk that contains each.

    A chunk is a contiguous run of elements (`element_start_id`..`element_end_id`
    by `sequence`), so containment is a sequence-range test. The correlated
    sub-selects resolve the run's bounds; the candidate set is a few hundred
    elements, so this stays cheap without its own index.
    """
    return (
        "SELECT de.document_element_id AS eid, dc.document_chunk_id AS cid "
        "FROM document_elements de "
        "JOIN document_chunks dc "
        "  ON dc.document_version_id = de.document_version_id "
        " AND dc.superseded = 0 "
        " AND de.sequence >= (SELECT sequence FROM document_elements "
        "                     WHERE document_element_id = dc.element_start_id) "
        " AND de.sequence <= (SELECT sequence FROM document_elements "
        "                     WHERE document_element_id = dc.element_end_id) "
        "JOIN document_versions dv ON dv.document_version_id = dc.document_version_id AND dv.is_active = 1 "
        "JOIN document_records d ON d.document_id = dv.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        f"WHERE de.document_element_id IN ({placeholders})" + filter_sql
    )


def _keyword_ranked(conn, query: str, filters: Filters, depth: int) -> list[str]:
    """Chunk ids best-match first, from the chunk tsvector GIN index."""
    filter_sql, filter_params = filters.sql()
    rows = conn.execute(
        "SELECT dc.document_chunk_id AS cid,"
        "ts_rank_cd(to_tsvector('simple',dc.text),plainto_tsquery('simple',%s)) AS rank "
        "FROM document_chunks dc "
        "JOIN document_versions dv ON dv.document_version_id=dc.document_version_id AND dv.is_active=1 "
        "JOIN document_records d ON d.document_id=dv.document_id "
        "JOIN evidence_records e ON e.evidence_id=d.evidence_id "
        "WHERE dc.superseded=0 AND to_tsvector('simple',dc.text) "
        "@@ plainto_tsquery('simple',%s)" + filter_sql +
        " ORDER BY rank DESC,dc.document_chunk_id LIMIT %s",
        [query, query, *filter_params, depth]).fetchall()
    return [row["cid"] for row in rows]


def _fuzzy_ranked(conn, query: str, filters: Filters, depth: int) -> list[str]:
    """A distinct pg_trgm candidate path; similarity is retrieval-only."""
    filter_sql, filter_params = filters.sql()
    rows = conn.execute(
        "SELECT dc.document_chunk_id AS cid,similarity(dc.text,%s) AS rank "
        "FROM document_chunks dc "
        "JOIN document_versions dv ON dv.document_version_id=dc.document_version_id AND dv.is_active=1 "
        "JOIN document_records d ON d.document_id=dv.document_id "
        "JOIN evidence_records e ON e.evidence_id=d.evidence_id "
        "WHERE dc.superseded=0 AND dc.text OPERATOR(public.%%) %s" + filter_sql +
        " ORDER BY rank DESC,dc.document_chunk_id LIMIT %s",
        [query, query, *filter_params, depth]).fetchall()
    return [row["cid"] for row in rows]


# --- semantic: query embedding vs document_embeddings ---------------------

def _semantic_ranked(conn, query: str, filters: Filters, depth: int,
                     model: str | None) -> tuple[str | None, list[tuple[str, float]], str | None]:
    """(model_key, [(chunk_id, cosine), ...] best first, note-or-None)."""
    try:
        embedder = embeddings.get_embedder(model)
        query_vec = embedder.encode([query])[0]
    except embeddings.EmbeddingUnavailable as exc:
        return None, [], str(exc)
    model_key = embedder.model_key

    filter_sql, filter_params = filters.sql()

    # pgvector/HNSW is the only semantic-search path (performance.md Phase 3):
    # order by cosine distance in the database, against the HNSW index
    # (migration 0071), and take only `depth` rows. The former exact path that
    # pulled every embedding for the model and scored each in a Python loop
    # (~30 s per query at 167k embeddings) is gone with the SQLite backend.
    repository = PostgresEmbeddingRepository(conn)
    rows = repository.semantic_candidates(
        query_vector=query_vec, model_key=model_key, filter_sql=filter_sql,
        filter_params=filter_params, depth=depth)
    if rows:
        return model_key, rows, None
    backfilled = repository.count(model_key)
    if backfilled == 0:
        total = repository.count_all(model_key)
        note = (f"no embeddings for model {model_key!r} -- run `pipeline nlp embed`"
                if total == 0
                else "pgvector is installed but embedding_vec is empty -- "
                     "run `pipeline nlp backfill-vectors`")
        return model_key, [], note
    return model_key, [], None  # filters matched nothing


# --- fusion --------------------------------------------------------------

def _rrf(keyword_hits: list[str], fuzzy_hits: list[str],
         semantic_hits: list[tuple[str, float]]) -> list[tuple[str, dict]]:
    scores: dict[str, dict] = {}
    for rank, cid in enumerate(keyword_hits, 1):
        meta = scores.setdefault(cid, {"rrf": 0.0})
        meta["keyword_rank"] = rank
        meta["rrf"] += 1.0 / (_RRF_K + rank)
    for rank, cid in enumerate(fuzzy_hits, 1):
        meta = scores.setdefault(cid, {"rrf": 0.0})
        meta["fuzzy_rank"] = rank
        meta["rrf"] += 1.0 / (_RRF_K + rank)
    for rank, (cid, cos) in enumerate(semantic_hits, 1):
        meta = scores.setdefault(cid, {"rrf": 0.0})
        meta["semantic_rank"] = rank
        meta["cosine"] = round(cos, 6)
        meta["rrf"] += 1.0 / (_RRF_K + rank)
    ordered = sorted(scores.items(), key=lambda kv: (
        -kv[1]["rrf"],
        min(kv[1].get("keyword_rank", 10**9), kv[1].get("fuzzy_rank", 10**9),
            kv[1].get("semantic_rank", 10**9)),
        kv[0]))
    return [(cid, {**meta, "rrf": round(meta["rrf"], 6)}) for cid, meta in ordered]


# --- hydration ---------------------------------------------------------

def _hydrate(conn, ranked: list[tuple[str, dict]]) -> list[dict]:
    if not ranked:
        return []
    ids = [cid for cid, _ in ranked]
    placeholders = ",".join("%s" for _ in ids)
    rows = {row["document_chunk_id"]: row for row in conn.execute(
        "SELECT dc.document_chunk_id, dc.text, dc.page_start, dc.page_end, "
        "dc.token_estimate, dc.char_start, dc.char_end, dc.preceding_heading_element_id, "
        "d.document_id, d.document_type, d.title, d.filename, d.published_at, "
        "e.source_url, e.retrieved_at, e.source_system "
        "FROM document_chunks dc "
        "JOIN document_versions dv ON dv.document_version_id = dc.document_version_id "
        "JOIN document_records d ON d.document_id = dv.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        f"WHERE dc.document_chunk_id IN ({placeholders})", ids)}

    out: list[dict] = []
    for cid, meta in ranked:
        row = rows.get(cid)
        if row is None:  # chunk superseded between ranking and hydration
            continue
        text = row["text"] or ""
        out.append({
            "document_chunk_id": cid,
            "document_id": row["document_id"],
            "document_type": row["document_type"],
            "title": row["title"] or row["filename"],
            "source_system": row["source_system"],
            "page_start": row["page_start"],
            "page_end": row["page_end"],
            "token_estimate": row["token_estimate"],
            "snippet": text if len(text) <= _SNIPPET_MAX else text[: _SNIPPET_MAX - 1] + "…",
            "text": text,
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "published_at": row["published_at"],
            "score": meta,
        })
    return out


# --- entry point -----------------------------------------------------

def search(conn, query: str, *, mode: str = "hybrid", limit: int = 20,
           source_system: str | None = None, date_from: str | None = None,
           date_to: str | None = None, model: str | None = None) -> dict:
    """Retrieve chunks for `query`. Read-only; writes, promotes and attributes
    nothing."""
    query = (query or "").strip()
    if not query:
        raise SearchError("search needs a query.")
    if mode not in MODES:
        raise SearchError(f"mode must be one of {', '.join(MODES)}; got {mode!r}.")
    limit = max(1, min(int(limit), 100))
    filters = Filters(source_system=source_system or None,
                      date_from=date_from or None, date_to=date_to or None)
    if model is None:
        model = get_settings().nlp_embedding_model

    notes: list[str] = []
    keyword_hits: list[str] = []
    fuzzy_hits: list[str] = []
    semantic_hits: list[tuple[str, float]] = []
    model_key: str | None = None

    if mode in ("keyword", "hybrid"):
        keyword_hits = _keyword_ranked(conn, query, filters, _CANDIDATE_DEPTH)
    if mode in ("fuzzy", "hybrid"):
        fuzzy_hits = _fuzzy_ranked(conn, query, filters, _CANDIDATE_DEPTH)
    if mode in ("semantic", "hybrid"):
        model_key, semantic_hits, note = _semantic_ranked(
            conn, query, filters, _CANDIDATE_DEPTH, model)
        if note:
            notes.append(note)

    if mode == "keyword":
        ranked = [(cid, {"keyword_rank": i + 1}) for i, cid in enumerate(keyword_hits)]
    elif mode == "fuzzy":
        ranked = [(cid, {"fuzzy_rank": i + 1}) for i, cid in enumerate(fuzzy_hits)]
    elif mode == "semantic":
        ranked = [(cid, {"semantic_rank": i + 1, "cosine": round(score, 6)})
                  for i, (cid, score) in enumerate(semantic_hits)]
    else:
        ranked = _rrf(keyword_hits, fuzzy_hits, semantic_hits)
        if not semantic_hits and (keyword_hits or fuzzy_hits):
            notes.append("hybrid degraded to keyword-only/fuzzy retrieval (no semantic candidates)")

    results = _hydrate(conn, ranked[:limit])
    return {
        "mode": mode,
        "query": query,
        "model_key": model_key,
        "count": len(results),
        "filters": filters.describe(),
        "notes": notes,
        "caveat": CAVEAT,
        "results": results,
    }
