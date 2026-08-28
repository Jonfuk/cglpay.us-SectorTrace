-- pgvector column on document_embeddings, SQLite dialect.
--
-- On PostgreSQL (../postgres/0071_document_embeddings_vector.sql) this adds
-- `embedding_vec`, a pgvector `vector(384)` **derived** from the existing
-- `embedding` bytea, plus an HNSW index — so semantic search is an
-- approximate-nearest-neighbour lookup instead of pulling every row and
-- scoring it with a Python cosine loop. Measured on the live mirror at
-- 167,779 embeddings: one exact semantic query took ~30 s; the ANN index
-- makes it interactive. This is the migration `docs/semantic-analysis.md`
-- gated on that measurement.
--
-- SQLite has no vector type and keeps the exact path
-- (`pipeline/nlp/semantic_search.py` falls back when the column/extension is
-- absent). The `embedding` bytea both trees already carry is the source of
-- truth; `embedding_vec` is rebuilt from it by
-- `pipeline/nlp/embeddings.py:backfill_vectors`, and `pgload` / `pgsync` skip
-- it (pipeline/pgload.py PG_DERIVED_COLUMNS).
--
-- Only the index NAME here, as an inert btree on a primary-key column, for
-- object-set parity with the PostgreSQL tree
-- (tests/test_migration_equivalence.py) — the 0053 precedent.

CREATE INDEX IF NOT EXISTS idx_document_embeddings_vec
    ON document_embeddings (model_key);
