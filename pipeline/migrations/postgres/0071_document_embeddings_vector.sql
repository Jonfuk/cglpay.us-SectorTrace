-- pgvector column on document_embeddings, PostgreSQL dialect of
-- ../0071_document_embeddings_vector.sql.
--
-- `embedding_vec` is a *derived* column: the same vector as the `embedding`
-- bytea (little-endian float32), in pgvector's type, so an HNSW index can
-- answer semantic search as an approximate-nearest-neighbour lookup. Without
-- it `_semantic_ranked` pulls every row for the model and scores each with a
-- Python cosine loop — ~30 s for one query at 167,779 embeddings on the live
-- mirror. This is the migration `docs/semantic-analysis.md` held until a
-- measurement showed exact search was too slow.
--
-- vector(384) is `all-MiniLM-L6-v2`'s dimension (embeddings.ST_DEFAULT_MODEL).
-- A model with a different dimension is a new migration, which is already how
-- a model change is handled here — it is gated on the retrieval eval.
--
-- Derived, so not copied or compared across backends: pgverify iterates
-- SQLite's columns, pgsync / pgload drop it (pipeline/pgload.py
-- PG_DERIVED_COLUMNS), and `embeddings.backfill_vectors` rebuilds it from the
-- bytea after a migration or a load. Backfill is Python, not SQL — there is
-- no bytea -> vector function — so it is not in this file; `apply_migrations`
-- calls it once when this migration first applies.
--
-- Guarded like 0069/0070: on a server without pgvector the column and index
-- are skipped and semantic search keeps sweeping in Python. The HNSW index is
-- partial (`WHERE embedding_vec IS NOT NULL`) so it builds instantly on the
-- empty column and grows as the backfill fills rows.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
        ALTER TABLE document_embeddings ADD COLUMN IF NOT EXISTS embedding_vec vector(384);
        CREATE INDEX IF NOT EXISTS idx_document_embeddings_vec
            ON document_embeddings USING hnsw (embedding_vec vector_cosine_ops)
            WHERE embedding_vec IS NOT NULL;
    ELSE
        RAISE NOTICE 'vector (pgvector) not installed - embedding_vec skipped; semantic search will sweep in Python';
    END IF;
END $$;
