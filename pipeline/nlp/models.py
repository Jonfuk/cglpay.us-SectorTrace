"""`nlp_model_registry` — the resolved identity of every model used.

A model *name* is not a stable identity: `all-MiniLM-L6-v2` today and the
same string in two years are not guaranteed to be the same weights. So the
registry records the provider, the id, and — where the provider exposes one —
the resolved revision/commit SHA, alongside the framework version. A
deterministic stub (used in CI and by `--model stub`) has no revision and
says so.

034A ships the table and these helpers; the first writer is the embeddings
stage in the next tranche.
"""
from __future__ import annotations

from pipeline.nlp.runs import utcnow


def upsert_model(conn, *, model_key: str, model_provider: str, model_id: str,
                 revision_sha: str | None = None, framework: str | None = None,
                 framework_version: str | None = None, tokenizer_revision: str | None = None,
                 dimension: int | None = None, distance_metric: str = "cosine",
                 normalised: bool = True) -> None:
    """Record a model's resolved identity. Idempotent on `model_key`; a later
    call with a different revision updates it in place (a run's own
    `model_revision` column keeps the historical record)."""
    conn.execute(
        "INSERT INTO nlp_model_registry (model_key, model_provider, model_id, revision_sha, "
        "framework, framework_version, tokenizer_revision, dimension, distance_metric, "
        "normalised, first_seen_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT(model_key) DO UPDATE SET model_provider=excluded.model_provider, "
        "model_id=excluded.model_id, revision_sha=excluded.revision_sha, "
        "framework=excluded.framework, framework_version=excluded.framework_version, "
        "tokenizer_revision=excluded.tokenizer_revision, dimension=excluded.dimension, "
        "distance_metric=excluded.distance_metric, normalised=excluded.normalised",
        (model_key, model_provider, model_id, revision_sha, framework, framework_version,
         tokenizer_revision, dimension, distance_metric, 1 if normalised else 0, utcnow()))


def get_model(conn, model_key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM nlp_model_registry WHERE model_key=%s", (model_key,)).fetchone()
    return dict(row) if row is not None else None
