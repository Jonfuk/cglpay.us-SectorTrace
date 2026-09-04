"""The sole PostgreSQL embedding persistence and retrieval boundary."""
from __future__ import annotations

import hashlib
import json
import struct
import uuid
from datetime import datetime, timezone
from pathlib import Path

VECTOR_DIMENSION = 384
# The benchmark asks HNSW for a bounded superset, then re-ranks that superset
# with the exact pgvector distance.  A final LIMIT directly on an approximate
# graph cannot honestly prove the 1e-6 result contract: a near neighbour that
# was not visited cannot be recovered by comparing the scores of the rows that
# were visited.
_PARITY_CANDIDATE_FACTOR = 1000


def vector_literal(vector) -> str:
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"


def float32_bytes(vector) -> bytes:
    values = list(vector)
    return struct.pack(f"<{len(values)}f", *values)


def vector_values(value) -> list[float]:
    if isinstance(value, str):
        return [float(item) for item in value.strip("[]").split(",") if item]
    return [float(item) for item in value]


class PostgresEmbeddingRepository:
    def __init__(self, conn):
        self.conn = conn

    def store_many(self, rows) -> int:
        values = list(rows)
        if not values:
            return 0
        wrong = sorted({len(vector) for _, _, vector, _, _ in values if len(vector) != VECTOR_DIMENSION})
        if wrong:
            raise ValueError(
                f"canonical pgvector repository requires {VECTOR_DIMENSION} dimensions; got {wrong}")
        self.conn.executemany(
            "INSERT INTO document_embeddings(document_chunk_id,model_key,dimension,"
            "embedding_vec,nlp_run_id,created_at) VALUES (%s,%s,%s,%s::public.vector,%s,%s) "
            "ON CONFLICT(document_chunk_id,model_key) DO UPDATE SET "
            "dimension=excluded.dimension,embedding_vec=excluded.embedding_vec,"
            "nlp_run_id=excluded.nlp_run_id,created_at=excluded.created_at",
            [(chunk_id, model_key, len(vector), vector_literal(vector), run_id, created_at)
             for chunk_id, model_key, vector, run_id, created_at in values])
        return len(values)

    def semantic_candidates(self, *, query_vector, model_key: str, filter_sql: str,
                            filter_params: list, depth: int,
                            exact_baseline: bool = False,
                            exact_rerank: bool = False) -> list[tuple[str, float]]:
        literal = vector_literal(query_vector)
        planner = None
        if exact_baseline:
            planner = self.conn.execute(
                "SELECT current_setting('enable_indexscan') AS indexscan,"
                "current_setting('enable_bitmapscan') AS bitmapscan").fetchone()
            self.conn.execute("SELECT set_config('enable_indexscan','off',true),"
                              "set_config('enable_bitmapscan','off',true)")
        try:
            query_limit = (max(depth, 1) * _PARITY_CANDIDATE_FACTOR
                           if exact_rerank else depth)
            rows = self.conn.execute(
                "SELECT em.document_chunk_id AS cid,"
                "1-(em.embedding_vec OPERATOR(public.<=>) %s::public.vector) AS score "
                "FROM document_embeddings em "
                "JOIN document_chunks dc ON dc.document_chunk_id=em.document_chunk_id "
                "AND dc.superseded=0 "
                "JOIN document_versions dv ON dv.document_version_id=dc.document_version_id "
                "AND dv.is_active=1 "
                "JOIN document_records d ON d.document_id=dv.document_id "
                "JOIN evidence_records e ON e.evidence_id=d.evidence_id "
                "WHERE em.model_key=%s AND em.embedding_vec IS NOT NULL" + filter_sql +
                " ORDER BY em.embedding_vec OPERATOR(public.<=>) %s::public.vector,"
                "em.document_chunk_id LIMIT %s",
                [literal, model_key, *filter_params, literal, query_limit]).fetchall()
        finally:
            if planner is not None:
                self.conn.execute(
                    "SELECT set_config('enable_indexscan',%s,true),"
                    "set_config('enable_bitmapscan',%s,true)",
                    (planner["indexscan"], planner["bitmapscan"]))
        if exact_rerank:
            # HNSW supplied the bounded candidate set; this sort is over the
            # exact scores selected in the query, so approximate graph order
            # cannot leak into the parity result.
            rows.sort(key=lambda row: (-float(row["score"]), row["cid"]))
            rows = rows[:depth]
        return [(row["cid"], float(row["score"])) for row in rows]

    def count(self, model_key: str) -> int:
        return int(self.conn.execute(
            "SELECT COUNT(*) AS count FROM document_embeddings "
            "WHERE model_key=%s AND embedding_vec IS NOT NULL", (model_key,)).fetchone()["count"])

    def count_all(self, model_key: str) -> int:
        """Rows for a model, including an interrupted legacy backfill."""
        return int(self.conn.execute(
            "SELECT COUNT(*) AS count FROM document_embeddings WHERE model_key=%s",
            (model_key,)).fetchone()["count"])

    def iter_population(self, model_key: str, *, page_size: int = 2000):
        """Yield bounded classifier pages using the stable chunk-id key."""
        after = None
        size = max(1, page_size)
        while True:
            params = [model_key]
            after_sql = ""
            if after is not None:
                after_sql = " AND dc.document_chunk_id>%s"
                params.append(after)
            params.append(size)
            rows = self.conn.execute(
                "SELECT dc.document_chunk_id,dc.text,em.embedding_vec "
                "FROM document_chunks dc JOIN document_embeddings em "
                "ON em.document_chunk_id=dc.document_chunk_id AND em.model_key=%s "
                "JOIN document_versions dv ON dv.document_version_id=dc.document_version_id "
                "AND dv.is_active=1 "
                "WHERE dc.superseded=0 AND em.embedding_vec IS NOT NULL" + after_sql +
                " ORDER BY dc.document_chunk_id LIMIT %s", params).fetchall()
            if not rows:
                return
            yield [(row["document_chunk_id"], row["text"] or "",
                    float32_bytes(vector_values(row["embedding_vec"]))) for row in rows]
            after = rows[-1]["document_chunk_id"]

    def population(self, model_key: str):
        """Compatibility materialisation; new corpus consumers should iterate."""
        return [row for page in self.iter_population(model_key) for row in page]

    def vectors_for_chunks(self, model_key: str, chunk_ids: list[str]) -> dict[str, bytes]:
        if not chunk_ids:
            return {}
        rows = self.conn.execute(
            "SELECT document_chunk_id,embedding_vec FROM document_embeddings "
            "WHERE model_key=%s AND document_chunk_id=ANY(%s) AND embedding_vec IS NOT NULL",
            (model_key, chunk_ids)).fetchall()
        return {row["document_chunk_id"]: float32_bytes(vector_values(row["embedding_vec"]))
                for row in rows}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_restore_receipt(backup_archive: Path, restore_receipt: Path) -> dict:
    """Verify that a restore receipt names this intact SectorTrace backup."""
    from pipeline import pgbackup

    verified = pgbackup.verify_archive(backup_archive)
    receipt = json.loads(restore_receipt.read_text(encoding="utf-8"))
    archive_digest = _sha256_file(backup_archive)
    if receipt.get("archive_sha256") != archive_digest:
        raise RuntimeError("restore receipt does not name the supplied backup bytes")
    if Path(receipt.get("from", "")).resolve() != backup_archive.resolve():
        raise RuntimeError("restore receipt source path does not match the supplied backup")
    if receipt.get("rows") != verified["rows"] or receipt.get("tables") != verified["tables"]:
        raise RuntimeError("restore receipt row/table counts do not match the verified backup")
    if not receipt.get("restored_at") or not receipt.get("restored"):
        raise RuntimeError("restore receipt lacks target and completion timestamp")
    return {"archive_sha256": archive_digest, "rows": verified["rows"],
            "tables": verified["tables"], "restored_at": receipt["restored_at"]}


def compact_legacy_table(conn, *, backup_archive: Path | None = None,
                         restore_receipt: Path | None = None, dry_run: bool = False,
                         parity_queries: list[tuple[str, list[float]]] = ()) -> dict:
    """Validate and remove the legacy bytea copy during a writer pause.

    The caller must provide evidence that the normal PostgreSQL backup restored
    successfully. The transaction takes an exclusive lock only for the final
    validation/drop; HNSW is already built on the canonical column.
    """
    restore_evidence = None
    if backup_archive is not None or restore_receipt is not None:
        if backup_archive is None or restore_receipt is None:
            raise RuntimeError("both backup archive and isolated-restore receipt are required")
        restore_evidence = validate_restore_receipt(backup_archive, restore_receipt)
    if not dry_run and restore_evidence is None:
        raise RuntimeError("verified PostgreSQL backup and isolated-restore receipt are required")
    locked = conn.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext('sectortrace:embedding-compaction')) AS locked"
    ).fetchone()["locked"]
    if not locked:
        raise RuntimeError("another embedding compaction is already running")
    columns = {row["column_name"] for row in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=current_schema() AND table_name='document_embeddings'")}
    if "embedding" not in columns:
        return {"status": "already_canonical", "legacy_column_removed": True}
    migration_id = "embed-migration-" + uuid.uuid4().hex
    counts = conn.execute(
        "SELECT model_key,dimension,COUNT(*) AS count FROM document_embeddings "
        "GROUP BY model_key,dimension ORDER BY model_key,dimension").fetchall()
    count_map = [dict(row) for row in counts]
    total = sum(int(row["count"]) for row in counts)
    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT INTO embedding_migration_audits(migration_id,status,source_row_count,"
        "model_dimension_counts,backup_restore_verified,backup_archive_sha256,"
        "restore_receipt_json,started_at) "
        "VALUES (%s,'validating',%s,%s::jsonb,%s,%s,%s::jsonb,%s)",
        (migration_id, total, json.dumps(count_map, default=str),
         restore_evidence is not None,
         restore_evidence["archive_sha256"] if restore_evidence else None,
         json.dumps(restore_evidence, sort_keys=True) if restore_evidence else None, now))
    bad = conn.execute(
        "SELECT COUNT(*) AS count FROM document_embeddings "
        "WHERE embedding_vec IS NULL OR dimension<>%s", (VECTOR_DIMENSION,)).fetchone()["count"]
    if bad:
        raise RuntimeError(f"refusing embedding swap: {bad} rows lack a {VECTOR_DIMENSION}d pgvector value")
    sample = conn.execute(
        "SELECT document_chunk_id,model_key,embedding,embedding_vec FROM document_embeddings "
        "ORDER BY document_chunk_id,model_key LIMIT 100").fetchall()
    digest = hashlib.sha256()
    for row in sample:
        vector_bytes = float32_bytes(vector_values(row["embedding_vec"]))
        if row["embedding"] is not None and vector_bytes != bytes(row["embedding"]):
            raise RuntimeError(f"float32 mismatch for {row['document_chunk_id']}")
        digest.update(vector_bytes)
    conn.execute("DROP TABLE IF EXISTS document_embeddings_compact")
    conn.execute(
        "CREATE TABLE document_embeddings_compact("
        "document_chunk_id text NOT NULL REFERENCES document_chunks(document_chunk_id),"
        "model_key text NOT NULL REFERENCES nlp_model_registry(model_key),"
        "dimension bigint NOT NULL,embedding_vec public.vector(384) NOT NULL,"
        "nlp_run_id text REFERENCES nlp_runs(run_id),created_at text NOT NULL,"
        "PRIMARY KEY(document_chunk_id,model_key))")
    conn.execute(
        "INSERT INTO document_embeddings_compact(document_chunk_id,model_key,dimension,"
        "embedding_vec,nlp_run_id,created_at) SELECT document_chunk_id,model_key,dimension,"
        "embedding_vec,nlp_run_id,created_at FROM document_embeddings "
        "ORDER BY document_chunk_id,model_key")
    replacement = conn.execute(
        "SELECT COUNT(*) AS count FROM document_embeddings_compact").fetchone()["count"]
    if int(replacement) != total:
        raise RuntimeError(f"replacement count {replacement} != source count {total}")
    conn.execute("SET LOCAL max_parallel_maintenance_workers=0")
    conn.execute(
        "CREATE INDEX idx_document_embeddings_compact_model "
        "ON document_embeddings_compact(model_key)")
    conn.execute(
        "CREATE INDEX idx_document_embeddings_compact_vec ON document_embeddings_compact "
        "USING hnsw (embedding_vec public.vector_cosine_ops)")

    queries = list(parity_queries)
    if not queries:
        queries = [(row["model_key"], vector_values(row["embedding_vec"])) for row in sample[:3]]
    parity = []
    for model_key, query in queries:
        literal = vector_literal(query)
        old = conn.execute(
            "SELECT document_chunk_id,1-(embedding_vec OPERATOR(public.<=>) %s::public.vector) score "
            "FROM document_embeddings WHERE model_key=%s ORDER BY embedding_vec "
            "OPERATOR(public.<=>) %s::public.vector,document_chunk_id LIMIT 20",
            (literal, model_key, literal)).fetchall()
        new = conn.execute(
            "SELECT document_chunk_id,1-(embedding_vec OPERATOR(public.<=>) %s::public.vector) score "
            "FROM document_embeddings_compact WHERE model_key=%s ORDER BY embedding_vec "
            "OPERATOR(public.<=>) %s::public.vector,document_chunk_id LIMIT 20",
            (literal, model_key, literal)).fetchall()
        if [r["document_chunk_id"] for r in old] != [r["document_chunk_id"] for r in new]:
            raise RuntimeError(f"semantic result identity/order mismatch for {model_key}")
        if any(abs(float(a["score"]) - float(b["score"])) > 1e-6 for a, b in zip(old, new)):
            raise RuntimeError(f"semantic score mismatch above 1e-6 for {model_key}")
        parity.append((model_key, [(r["document_chunk_id"], round(float(r["score"]), 6))
                                   for r in old]))
    parity_digest = hashlib.sha256(json.dumps(parity, sort_keys=True).encode()).hexdigest()

    if dry_run:
        result = {"status": "dry_run", "rows": total,
                  "sampled_value_digest": digest.hexdigest(),
                  "semantic_parity_digest": parity_digest,
                  "restore_evidence_verified": restore_evidence is not None}
        conn.rollback()
        return result

    # Writers are paused by the operator; this short lock is the actual swap.
    conn.execute("LOCK TABLE document_embeddings IN ACCESS EXCLUSIVE MODE")
    drift = conn.execute(
        "SELECT EXISTS((SELECT document_chunk_id,model_key,dimension,embedding_vec "
        "FROM document_embeddings EXCEPT SELECT document_chunk_id,model_key,dimension,"
        "embedding_vec FROM document_embeddings_compact) UNION ALL "
        "(SELECT document_chunk_id,model_key,dimension,embedding_vec "
        "FROM document_embeddings_compact EXCEPT SELECT document_chunk_id,model_key,dimension,"
        "embedding_vec FROM document_embeddings)) AS drift").fetchone()["drift"]
    if drift:
        raise RuntimeError("embedding rows changed during validation; writers were not paused")
    # The old table still owns the canonical index names until it is dropped.
    # Release those names while the table lock is held so the replacement can
    # inherit the names that retrieval and operational checks already know.
    conn.execute("DROP INDEX IF EXISTS idx_document_embeddings_model")
    conn.execute("DROP INDEX IF EXISTS idx_document_embeddings_vec")
    conn.execute("ALTER TABLE document_embeddings RENAME TO document_embeddings_legacy")
    conn.execute("ALTER TABLE document_embeddings_compact RENAME TO document_embeddings")
    conn.execute("DROP TABLE document_embeddings_legacy")
    conn.execute("ALTER INDEX idx_document_embeddings_compact_model "
                 "RENAME TO idx_document_embeddings_model")
    conn.execute("ALTER INDEX idx_document_embeddings_compact_vec "
                 "RENAME TO idx_document_embeddings_vec")
    conn.execute(
        "UPDATE embedding_migration_audits SET status='complete',replacement_row_count=%s,"
        "sampled_value_digest=%s,semantic_parity_digest=%s,completed_at=%s "
        "WHERE migration_id=%s",
        (total, digest.hexdigest(), parity_digest,
         datetime.now(timezone.utc), migration_id))
    conn.commit()
    return {"status": "complete", "migration_id": migration_id, "rows": total,
            "sampled_value_digest": digest.hexdigest(), "legacy_column_removed": True}
