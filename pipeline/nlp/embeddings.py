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

New vectors are stored once as pgvector through `PostgresEmbeddingRepository`.
The little-endian codec remains only for validating and removing pre-Phase-3
rows during the maintenance-window migration and for classifier in-memory
compatibility. See docs/semantic-analysis.md.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
import threading
from typing import Any

from pipeline.nlp import models, runs, stage_state
from pipeline.nlp.embedding_repository import PostgresEmbeddingRepository, vector_literal

STUB_MODEL_KEY = "embed:stub"
STUB_DIMENSION = 384
ST_DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# The dimension of the one canonical pgvector value. Both the offline stub
# and the supported sentence-transformer use this width; an incompatible
# model is rejected at the repository boundary rather than diverted to a
# second persistence/search implementation.
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


vec_literal = vector_literal  # retained public compatibility; conversion is repository-owned


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
    model_id = "hash-stub/signed-bow-384"
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
            conn,
            model_key=self.model_key,
            model_provider=self.provider,
            model_id=self.model_id,
            revision_sha=None,
            framework=self.framework,
            framework_version=self.framework_version,
            dimension=self.dimension,
            distance_metric="cosine",
            normalised=True,
        )


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
        _get_dim = (
            getattr(self._model, "get_embedding_dimension", None)
            or self._model.get_sentence_embedding_dimension
        )
        self.dimension = int(_get_dim())
        self.revision_sha = _resolve_revision(self.model_id)

    def encode(self, texts) -> list[list[float]]:
        self._load()
        vectors = self._model.encode(
            list(texts), normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False
        )
        return [[float(x) for x in row] for row in vectors]

    def register(self, conn) -> None:
        self._load()
        models.upsert_model(
            conn,
            model_key=self.model_key,
            model_provider=self.provider,
            model_id=self.model_id,
            revision_sha=self.revision_sha,
            framework=self.framework,
            framework_version=self.framework_version,
            dimension=self.dimension,
            distance_metric="cosine",
            normalised=True,
        )


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


def _live_chunks_page(conn, source_system: str | None, *, after: str | None,
                      page_size: int) -> list:
    sql = (
        "SELECT dc.document_chunk_id,dc.text FROM document_chunks dc "
        "JOIN document_versions v ON v.document_version_id=dc.document_version_id "
        "AND v.is_active=1 JOIN document_records d ON d.document_id=v.document_id "
        "JOIN evidence_records e ON e.evidence_id=d.evidence_id WHERE dc.superseded=0"
    )
    params: list = []
    if source_system:
        sql += " AND e.source_system=%s"
        params.append(source_system)
    if after is not None:
        sql += " AND dc.document_chunk_id>%s"
        params.append(after)
    sql += " ORDER BY dc.document_chunk_id LIMIT %s"
    params.append(page_size)
    return conn.execute(sql, params).fetchall()


def run(
    conn,
    *,
    model: str | None = None,
    source_system: str | None = None,
    limit: int | None = None,
    batch_size: int = _DEFAULT_BATCH,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    """Embed live `document_chunks` into `document_embeddings`. Bounded by
    `limit`, safe to repeat, and offline by default (`model="stub"`)."""
    embedder = get_embedder(model)
    config = {
        "model": model or "stub",
        "model_key": embedder.model_key,
        "source_system": source_system,
        "limit": limit,
        "batch_size": batch_size,
    }
    # register() may need to load a real model; do it before start_run so a
    # missing `nlp` extra fails without leaving a dangling 'running' row.
    embedder.register(conn)
    run_id = runs.start_run(
        conn,
        "embed",
        config=config,
        model_key=embedder.model_key,
        model_revision=getattr(embedder, "revision_sha", None),
        input_scope={"source_system": source_system, "limit": limit},
    )

    state_config = {"model_key": embedder.model_key, "dimension": embedder.dimension}
    model_version = stage_state.combined_hash(
        embedder.model_key, getattr(embedder, "revision_sha", None))
    now = runs.utcnow()
    written = 0
    processed = 0
    scanned = 0
    skipped = 0
    after_key = None
    batch_ordinal = 0

    repository = PostgresEmbeddingRepository(conn)
    try:
        size = max(1, batch_size)
        while limit is None or scanned < limit:
            page_size = min(size, limit - scanned) if limit is not None else size
            page = _live_chunks_page(
                conn, source_system, after=after_key, page_size=page_size)
            if not page:
                break
            after_key = page[-1]["document_chunk_id"]
            scanned += len(page)
            hashes = {row["document_chunk_id"]: hashlib.sha256(
                (row["text"] or "").encode()).hexdigest() for row in page}
            pending_ids = stage_state.pending_identities(
                conn, "embeddings", [(identity, input_hash, None)
                                     for identity, input_hash in hashes.items()],
                processor_version="pgvector-repository-v1",
                model_or_ontology_version=model_version,
                configuration=state_config, force=force)
            batch = [row for row in page if row["document_chunk_id"] in pending_ids]
            skipped += len(page) - len(batch)
            try:
                if batch:
                    vectors = embedder.encode([row["text"] for row in batch])
                    with conn.raw.transaction():
                        repository.store_many(
                            (row["document_chunk_id"], embedder.model_key, vector, run_id, now)
                            for row, vector in zip(batch, vectors))
                        for row, vector in zip(batch, vectors):
                            stage_state.mark_complete(
                                conn, "embeddings", row["document_chunk_id"],
                                hashes[row["document_chunk_id"]],
                                processor_version="pgvector-repository-v1", output=vector,
                                model_or_ontology_version=model_version,
                                configuration=state_config, run_id=run_id)
                    written += len(batch)
                    processed += len(batch)
            except Exception as batch_exc:
                # The savepoint above rolls back the whole persistence batch;
                # retain attribution for every input whose outcome is unknown.
                for row in batch:
                    stage_state.mark_failed(
                        conn,
                        "embeddings",
                        row["document_chunk_id"],
                        hashes[row["document_chunk_id"]],
                        processor_version="pgvector-repository-v1",
                        error=batch_exc,
                        run_id=run_id,
                        model_or_ontology_version=model_version,
                        configuration=state_config,
                    )
                raise
            if not dry_run:
                stage_state.checkpoint(
                    conn,
                    run_id=run_id,
                    stage="embeddings",
                    batch_ordinal=batch_ordinal,
                    last_input_identity=after_key,
                    rows_processed=scanned,
                    rows_written=written,
                )
                conn.commit()
            batch_ordinal += 1
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(
            conn,
            run_id,
            status="failed",
            rows_processed=processed,
            rows_written=written,
            error=f"{type(exc).__name__}: {exc}",
        )
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=processed, rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {
        "run_id": run_id,
        "model_key": embedder.model_key,
        "pending": processed,
        "embedded": written,
        "skipped_unchanged": skipped,
        "dry_run": dry_run,
    }


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
        "WHERE e.extname = 'vector'"
    ).fetchone()
    if not extension:
        return
    conn.execute(
        "SELECT set_config('search_path', %s, true)",
        (f"{extension['application_schema']},{extension['vector_schema']},pg_catalog",),
    )


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
            "WHERE embedding_vec IS NOT NULL"
        )


def backfill_vectors(conn, *, batch_size: int = 2000, limit: int | None = None) -> dict:
    """Fill `document_embeddings.embedding_vec` from the stored `embedding`
    bytea for rows that predate the column (migration 0071).

    Idempotent and resume-safe (`WHERE embedding_vec IS NULL`). A no-op unless
    the warehouse is PostgreSQL with pgvector. Also (re)creates the column and
    its HNSW index, so a cluster that gained pgvector after 0071 ran is caught
    up by the next `pipeline nlp backfill-vectors` or a mirror sync.

    The HNSW index remains present throughout. Bulk legacy conversion belongs
    in the writer-paused compact-table migration, which builds its replacement
    index before the short swap; this compatibility command must not silently
    expose a sequential semantic-search path.

    Only the `VECTOR_COLUMN_DIM`-wide rows: the column is typed to that width.
    """
    legacy = conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() "
        "AND table_name='document_embeddings' AND column_name='embedding'"
    ).fetchone()
    if legacy is None:
        _ensure_vector_index(conn)
        return {"backend": "postgres", "pending": 0, "written": 0, "status": "already_canonical"}

    with conn:
        _set_vector_search_path(conn)
        conn.execute(
            f"ALTER TABLE document_embeddings ADD COLUMN IF NOT EXISTS "
            f"embedding_vec public.vector({VECTOR_COLUMN_DIM})"
        )

    _ensure_vector_index(conn)

    written = 0
    after_chunk = None
    after_model = None
    size = max(1, batch_size)
    while limit is None or written < limit:
        take = min(size, limit - written) if limit is not None else size
        params: list = [VECTOR_COLUMN_DIM]
        after_sql = ""
        if after_chunk is not None:
            after_sql = " AND (document_chunk_id,model_key)>(%s,%s)"
            params.extend([after_chunk, after_model])
        params.append(take)
        chunk = conn.execute(
            "SELECT document_chunk_id,model_key,embedding FROM document_embeddings "
            "WHERE embedding_vec IS NULL AND dimension=%s" + after_sql +
            " ORDER BY document_chunk_id,model_key LIMIT %s", params).fetchall()
        if not chunk:
            break
        _set_vector_search_path(conn)
        conn.executemany(
            "UPDATE document_embeddings SET embedding_vec = %s::public.vector "
            "WHERE document_chunk_id = %s AND model_key = %s",
            [
                (vec_literal(unpack(r["embedding"])), r["document_chunk_id"], r["model_key"])
                for r in chunk
            ],
        )
        conn.commit()
        written += len(chunk)
        after_chunk = chunk[-1]["document_chunk_id"]
        after_model = chunk[-1]["model_key"]

    return {"backend": "postgres", "pending": written, "written": written}
