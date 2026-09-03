"""Chunk embeddings: `document_chunks` -> `document_embeddings`.

034A ships two embedders and no third path:

* ``stub`` -- deterministic, dependency-free, no download. A signed hashed
  bag-of-words folded into a fixed-width unit vector. It is a *stand-in*, not
  a good retriever: it lets CI, the retrieval-eval harness and offline
  development exercise the whole path -- embed, store, cosine, rank, fuse --
  with no model on disk. Its registry row carries provider ``hash-stub`` and
  a NULL ``revision_sha``, so nothing downstream can mistake it for a real
  model.
* a sentence-transformers id (default ``sentence-transformers/all-MiniLM-L6-v2``),
  imported lazily, present only with the ``nlp`` extra, first-use download,
  excluded from the Railway image -- the same pattern as ``documents``/``ocr``.
  Its resolved revision SHA is recorded on the run and the registry row where
  the hub exposes one.

The vector is stored two ways on the row: a little-endian float32 blob with
its dimension, and — for models of the width the column is typed to
(VECTOR_COLUMN_DIM) — a pgvector `embedding_vec` with an HNSW index (migration
0071), which is the semantic-search path. Collapsing to the single pgvector
copy is Phase 3 of performance.md. See docs/semantic-analysis.md.
"""
from __future__ import annotations

import hashlib
import math
import re
import struct
import threading
from typing import Any

from pipeline.nlp import models, runs

STUB_MODEL_KEY = "embed:stub"
STUB_DIMENSION = 256
ST_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The dimension the pgvector `embedding_vec` column (migration 0071) is typed
# to — `all-MiniLM-L6-v2`'s. Only embeddings of this width are mirrored into
# that column and its HNSW index; the offline `stub` (256) and any future
# model of a different width are left to the exact Python path until a
# migration gives them their own column. See docs/semantic-analysis.md.
VECTOR_COLUMN_DIM = 384

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'\-]*")
_DEFAULT_BATCH = 256


class EmbeddingUnavailable(RuntimeError):
    """The requested embedder needs a dependency that is not installed. Raised
    rather than crashing so a caller can fall back to keyword-only search or
    tell the operator to `uv sync --extra nlp`."""


# --- vector <-> blob, and exact cosine ---------------------------------------

def pack(vector) -> bytes:
    """A vector -> its on-disk form: little-endian float32, no header. The
    dimension lives on the row, so this is the whole encoding."""
    values = list(vector)
    return struct.pack("<%df" % len(values), *values)


def unpack(blob: bytes) -> list[float]:
    return list(struct.unpack("<%df" % (len(blob) // 4), blob))


def vec_literal(vector) -> str:
    """A vector as pgvector's text input form: ``[0.1,0.2,...]``.

    Bound as a plain string and cast with ``?::public.vector`` at the call site, so
    the pgvector psycopg adapter is not a dependency. ``repr`` on a float
    round-trips exactly, which the on-disk bytea already guarantees anyway.
    """
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def cosine(a, b) -> float:
    """Exact cosine similarity. Vectors are written normalised, but a round
    trip through float32 can leave the norm a ulp off 1.0, so this does not
    assume unit length."""
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / math.sqrt(na * nb)


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return vector if norm == 0.0 else [x / norm for x in vector]


# --- embedders -------------------------------------------------------------

class StubEmbedder:
    """Signed hashed bag-of-words. Deterministic across machines and Python
    builds: the bucket and sign come from SHA-1 of the lowercased token, never
    from Python's salted ``hash()``. Two passages that share vocabulary score
    close; a paraphrase with no shared words scores near zero. That is enough
    to exercise ranking and fusion, and not enough to trust as retrieval."""

    model_key = STUB_MODEL_KEY
    dimension = STUB_DIMENSION
    provider = "hash-stub"
    model_id = "hash-stub/signed-bow-256"
    revision_sha = None
    framework = "stdlib"
    framework_version = None

    def encode(self, texts) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dimension
            for token in _TOKEN.findall((text or "").lower()):
                digest = hashlib.sha1(token.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % self.dimension
                vec[bucket] += 1.0 if digest[4] & 1 else -1.0
            out.append(_normalise(vec))
        return out

    def register(self, conn) -> None:
        models.upsert_model(
            conn, model_key=self.model_key, model_provider=self.provider,
            model_id=self.model_id, revision_sha=None, framework=self.framework,
            framework_version=self.framework_version, dimension=self.dimension,
            distance_metric="cosine", normalised=True)


class SentenceTransformerEmbedder:
    """A sentence-transformers model, loaded lazily. Nothing here imports the
    library until `encode`/`register` is called, so `get_embedder("stub")`
    stays importable with no extra installed."""

    provider = "sentence-transformers"
    framework = "sentence-transformers"

    def __init__(self, model_id: str = ST_DEFAULT_MODEL):
        self.model_id = model_id
        # A short, stable handle for the registry / embeddings rows. The full
        # id is still recorded on the registry row's model_id column.
        self.model_key = "embed:" + model_id.rsplit("/", 1)[-1].lower()
        self.revision_sha: str | None = None
        self.framework_version: str | None = None
        self.dimension: int | None = None
        self._model = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import sentence_transformers  # noqa: PLC0415 - lazy: only with the `nlp` extra
        except ImportError as exc:  # pragma: no cover - the path without the extra
            raise EmbeddingUnavailable(
                f"Embedding model {self.model_id!r} needs the `nlp` extra "
                "(`uv sync --extra nlp`). Pass --model stub for an offline run."
            ) from exc
        self.framework_version = getattr(sentence_transformers, "__version__", None)
        self._model = sentence_transformers.SentenceTransformer(self.model_id, device="cpu")
        # Renamed get_sentence_embedding_dimension -> get_embedding_dimension in
        # sentence-transformers 6.0; the old name is a deprecated alias that
        # warns and will eventually go. Prefer the new one, fall back for <6.0.
        _get_dim = getattr(
            self._model, "get_embedding_dimension", None
        ) or self._model.get_sentence_embedding_dimension
        self.dimension = int(_get_dim())
        self.revision_sha = _resolve_revision(self.model_id)

    def encode(self, texts) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True,
            show_progress_bar=False)
        return [[float(x) for x in row] for row in vectors]

    def register(self, conn) -> None:
        self._load()
        models.upsert_model(
            conn, model_key=self.model_key, model_provider=self.provider,
            model_id=self.model_id, revision_sha=self.revision_sha,
            framework=self.framework, framework_version=self.framework_version,
            dimension=self.dimension, distance_metric="cosine", normalised=True)


def _resolve_revision(model_id: str) -> str | None:
    """Best effort: the hub commit the weights resolved to. None -- not an
    error -- when huggingface_hub is absent or the machine is offline; the run
    still records the framework version and everything else."""
    try:
        from huggingface_hub import model_info  # noqa: PLC0415
        return model_info(model_id).sha
    except Exception:  # noqa: BLE001 - a provenance nicety, never a failure
        return None


# One embedder instance per model name, process-wide. A sentence-transformers
# model costs a disk read and a torch init on first `encode`; without this the
# assistant's retrieval tool reloaded it on every call (BETA-116 — nine
# "Loading weights" lines and a 1.2 GB RSS spike in one `assistant-eval` run).
# The lock is held across the (slow) construction so concurrent callers on the
# threaded web server wait rather than each build their own.
_EMBEDDERS: dict[str, Any] = {}
_EMBEDDERS_LOCK = threading.Lock()


def get_embedder(name: str | None):
    """`None` / `"stub"` -> the deterministic stub; anything else is taken as a
    sentence-transformers id. Instances are cached by name for the life of the
    process; the model itself still loads lazily inside the instance."""
    key = name or "stub"
    with _EMBEDDERS_LOCK:
        embedder = _EMBEDDERS.get(key)
        if embedder is None:
            embedder = StubEmbedder() if key == "stub" else SentenceTransformerEmbedder(key)
            _EMBEDDERS[key] = embedder
        return embedder


# --- the stage -----------------------------------------------------------

def _scope_version_ids(conn, source_system: str | None) -> set[str] | None:
    """The active versions in scope, or None for 'all'. A set so the pending
    query can filter without re-joining evidence for every chunk."""
    if not source_system:
        return None
    rows = conn.execute(
        "SELECT v.document_version_id FROM document_versions v "
        "JOIN document_records d ON d.document_id = v.document_id "
        "JOIN evidence_records e ON e.evidence_id = d.evidence_id "
        "WHERE v.is_active = 1 AND e.source_system = ?", (source_system,)).fetchall()
    return {row["document_version_id"] for row in rows}


def _pending_chunks(conn, model_key: str, version_ids: set[str] | None,
                    limit: int | None) -> list:
    """Live chunks with no vector for this model. The LEFT JOIN ... IS NULL is
    what makes the stage resume-safe: a re-run fills gaps and re-embeds
    nothing ("existing but empty is not done")."""
    sql = (
        "SELECT dc.document_chunk_id, dc.text FROM document_chunks dc "
        "LEFT JOIN document_embeddings em ON em.document_chunk_id = dc.document_chunk_id "
        "AND em.model_key = ? "
        "WHERE dc.superseded = 0 AND em.document_chunk_id IS NULL")
    params: list = [model_key]
    if version_ids is not None:
        if not version_ids:
            return []
        placeholders = ",".join("?" for _ in version_ids)
        sql += f" AND dc.document_version_id IN ({placeholders})"
        params.extend(sorted(version_ids))
    sql += " ORDER BY dc.created_at, dc.document_chunk_id"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def run(conn, *, model: str | None = None, source_system: str | None = None,
        limit: int | None = None, batch_size: int = _DEFAULT_BATCH,
        dry_run: bool = False) -> dict:
    """Embed live `document_chunks` into `document_embeddings`. Bounded by
    `limit`, safe to repeat, and offline by default (`model="stub"`)."""
    embedder = get_embedder(model)
    config = {"model": model or "stub", "model_key": embedder.model_key,
              "source_system": source_system, "limit": limit, "batch_size": batch_size}
    # register() may need to load a real model; do it before start_run so a
    # missing `nlp` extra fails without leaving a dangling 'running' row.
    embedder.register(conn)
    run_id = runs.start_run(
        conn, "embed", config=config, model_key=embedder.model_key,
        model_revision=getattr(embedder, "revision_sha", None),
        input_scope={"source_system": source_system, "limit": limit})

    version_ids = _scope_version_ids(conn, source_system)
    pending = _pending_chunks(conn, embedder.model_key, version_ids, limit)
    now = runs.utcnow()
    written = 0

    # Fill the pgvector ANN column in the same statement so a fresh embed run
    # needs no separate backfill. Only for the width the `embedding_vec` column
    # is typed to (migration 0071); the stub and any other-width model stay on
    # the exact path, which writes the blob alone. pgvector is mandatory now, so
    # the only question left is whether this model's width fits the column.
    with_vec = getattr(embedder, "dimension", None) == VECTOR_COLUMN_DIM
    if with_vec:
        _set_vector_search_path(conn)
        insert_sql = (
            "INSERT INTO document_embeddings (document_chunk_id, model_key, dimension, "
            "embedding, embedding_vec, nlp_run_id, created_at) "
            "VALUES (?, ?, ?, ?, ?::public.vector, ?, ?) "
            "ON CONFLICT(document_chunk_id, model_key) DO UPDATE SET "
            "dimension=excluded.dimension, embedding=excluded.embedding, "
            "embedding_vec=excluded.embedding_vec, "
            "nlp_run_id=excluded.nlp_run_id, created_at=excluded.created_at")
    else:
        insert_sql = (
            "INSERT INTO document_embeddings (document_chunk_id, model_key, dimension, "
            "embedding, nlp_run_id, created_at) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(document_chunk_id, model_key) DO UPDATE SET "
            "dimension=excluded.dimension, embedding=excluded.embedding, "
            "nlp_run_id=excluded.nlp_run_id, created_at=excluded.created_at")

    try:
        for start in range(0, len(pending), max(1, batch_size)):
            batch = pending[start:start + max(1, batch_size)]
            vectors = embedder.encode([row["text"] for row in batch])
            for row, vector in zip(batch, vectors):
                base = [row["document_chunk_id"], embedder.model_key, len(vector),
                        pack(vector)]
                if with_vec:
                    base.append(vec_literal(vector))
                base += [run_id, now]
                conn.execute(insert_sql, tuple(base))
                written += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=len(pending),
                        rows_written=written, error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(pending),
                    rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"run_id": run_id, "model_key": embedder.model_key,
            "pending": len(pending), "embedded": written, "dry_run": dry_run}


def _set_vector_search_path(conn) -> None:
    """Expose pgvector only inside the current transaction.

    Scratch schemas deliberately omit the database's extension schema from
    their ordinary search path. This preserves schema isolation while allowing
    pgvector's ``vector`` type and ``vector_cosine_ops`` to resolve for the
    small number of statements that use them.
    """
    extension = conn.execute(
        "SELECT current_schema() AS application_schema, n.nspname AS "
        "vector_schema FROM pg_extension e "
        "JOIN pg_namespace n ON n.oid = e.extnamespace "
        "WHERE e.extname = 'vector'").fetchone()
    if not extension:
        return
    conn.execute(
        "SELECT set_config('search_path', ?, true)",
        (f"{extension['application_schema']},"
         f"{extension['vector_schema']},pg_catalog",))


def _ensure_vector_index(conn) -> None:
    """Create the HNSW index on `embedding_vec` if it is absent, single-threaded.

    Serial build only: pgvector's *parallel* build reserves a /dev/shm segment
    the size of maintenance_work_mem before it counts rows, which overflows the
    container's shm_size and aborts the build with "could not resize shared
    memory segment ... No space left on device" (see migrations/postgres/0071).
    A serial build uses backend-private memory and needs no /dev/shm. SET LOCAL
    scopes the setting to this transaction.
    """
    with conn:
        _set_vector_search_path(conn)
        conn.execute("SET LOCAL max_parallel_maintenance_workers = 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_document_embeddings_vec "
            "ON document_embeddings USING hnsw (embedding_vec vector_cosine_ops) "
            "WHERE embedding_vec IS NOT NULL")


def backfill_vectors(conn, *, batch_size: int = 2000, limit: int | None = None) -> dict:
    """Fill `document_embeddings.embedding_vec` from the stored `embedding`
    bytea for rows that predate the column (migration 0071).

    Idempotent and resume-safe (`WHERE embedding_vec IS NULL`). A no-op unless
    the warehouse is PostgreSQL with pgvector. Also (re)creates the column and
    its HNSW index, so a cluster that gained pgvector after 0071 ran is caught
    up by the next `pipeline nlp backfill-vectors` or a mirror sync.

    A full catch-up (no `limit`) drops the HNSW index, fills the column, then
    builds the index once: inserting rows one at a time into a live HNSW index
    is pgvector's slowest path — each `UPDATE` pays a graph insertion — so on
    the one-time fill of a populated table this is a single serial build rather
    than N indexed writes. While the index is dropped, semantic search falls
    back to a sequential scan (semantic_search handles that); on the mirror this
    runs during the sync, off any query path. A `limit`ed run keeps the index in
    place, so a resume-by-limit pass does not rebuild the whole graph each time.

    Only the `VECTOR_COLUMN_DIM`-wide rows: the column is typed to that width.
    """
    with conn:
        _set_vector_search_path(conn)
        conn.execute(
            f"ALTER TABLE document_embeddings ADD COLUMN IF NOT EXISTS "
            f"embedding_vec public.vector({VECTOR_COLUMN_DIM})")

    sql = ("SELECT document_chunk_id, model_key, embedding FROM document_embeddings "
           "WHERE embedding_vec IS NULL AND dimension = ?")
    params: list = [VECTOR_COLUMN_DIM]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    pending = conn.execute(sql, params).fetchall()

    if not pending:
        # Nothing to fill — but make sure the index exists for the inline-insert
        # path (embeddings.run). Never drop a populated index to rebuild it over
        # no new rows.
        _ensure_vector_index(conn)
        return {"backend": "postgres", "pending": 0, "written": 0}

    rebuild = limit is None
    if rebuild:
        with conn:
            conn.execute("DROP INDEX IF EXISTS idx_document_embeddings_vec")
    else:
        _ensure_vector_index(conn)  # keep the index; a limited run inserts into it

    written = 0
    for start in range(0, len(pending), max(1, batch_size)):
        chunk = pending[start:start + max(1, batch_size)]
        _set_vector_search_path(conn)
        conn.executemany(
            "UPDATE document_embeddings SET embedding_vec = ?::public.vector "
            "WHERE document_chunk_id = ? AND model_key = ?",
            [(vec_literal(unpack(r["embedding"])), r["document_chunk_id"], r["model_key"])
             for r in chunk])
        conn.commit()
        written += len(chunk)

    if rebuild:
        _ensure_vector_index(conn)
    return {"backend": "postgres", "pending": len(pending), "written": written}
