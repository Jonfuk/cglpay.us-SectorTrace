"""Scoring the embedded corpus with the selected 034G heads.

Only heads with `selected = 1` in `claim_head_versions` run -- one per
category, the bake-off winner that cleared the precision bar. A quarantined
head never reaches here. Zero selected heads is not an error: it is a no-op
with a logged warning, because the gate is per-head.

Every row written to `document_claim_predictions` is a FINDING AID: it is not
evidence, it is excluded from every export and every portal response, and no
figure is ever computed across it. `split` records whether the chunk was in
the head's fit, so a later reader can exclude the training and held-out
chunks from any tally.
"""
from __future__ import annotations

import json

import numpy as np

from pipeline.nlp import claims, claims_features, runs
from pipeline.nlp.claims_train import LogRegHead
from pipeline.nlp.embeddings import unpack

_SELECTED_SQL = """
SELECT model_version, category, predicate, model_type, embedder_model_key,
       setfit_base_model, artifact_path, artifact_sha256, heldout_candidate_ids_json
FROM claim_head_versions
WHERE selected = 1
ORDER BY category
"""

_UPSERT_PREDICTION = """
INSERT INTO document_claim_predictions
    (document_chunk_id, category, model_version, label, score, split, nlp_run_id, created_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT(document_chunk_id, category, model_version) DO UPDATE SET
    label = excluded.label, score = excluded.score, split = excluded.split,
    nlp_run_id = excluded.nlp_run_id, created_at = excluded.created_at
"""


class ArtifactMismatch(RuntimeError):
    """A head's artifact on disk does not match the SHA-256 recorded when it
    was trained -- a synced warehouse whose `nlp-cache/` did not come with it,
    or a tampered file. Refuse rather than score against the wrong head."""


def _chunk_splits(conn, heldout_ids_json: str, predicate: str) -> dict[str, str]:
    """chunk_id -> 'train' | 'heldout' for the chunks this head was fitted on.
    Everything else is 'unlabelled'."""
    heldout = set(json.loads(heldout_ids_json or "[]"))
    rows = conn.execute(
        "SELECT c.claim_candidate_id AS cid, c.document_chunk_id AS chunk "
        "FROM document_claim_candidates c "
        "JOIN claim_candidate_decisions d ON d.claim_candidate_id = c.claim_candidate_id "
        "WHERE c.predicate = %s", (predicate,)).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        out[r["chunk"]] = "heldout" if r["cid"] in heldout else "train"
    return out


def _load_logreg(path) -> LogRegHead:
    import pathlib

    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    return LogRegHead(coef=data["coef"], intercept=data["intercept"], dim=data["dim"])


def _verify_artifact(head_row) -> None:
    import pathlib

    from pipeline.nlp.claims_train import _hash_bytes, _hash_path

    path = head_row["artifact_path"]
    want = head_row["artifact_sha256"]
    if not want:
        return
    if not path or not pathlib.Path(path).exists():
        raise ArtifactMismatch(
            f"{head_row['model_version']}: artifact {path!r} is missing.")
    p = pathlib.Path(path)
    got = _hash_bytes(p.read_bytes()) if p.is_file() else _hash_path(p)
    if got != want:
        raise ArtifactMismatch(
            f"{head_row['model_version']}: artifact SHA-256 {got[:12]} != recorded {want[:12]}.")


def predict(conn, *, embedder_model_key: str = claims.DEFAULT_EMBEDDER_MODEL_KEY,
            dry_run: bool = False) -> dict:
    """Score every live embedded chunk with each selected head."""
    import structlog

    log = structlog.get_logger()
    heads = [dict(r) for r in conn.execute(_SELECTED_SQL).fetchall()]
    if not heads:
        log.warning("nlp.claims_predict.no_heads",
                    reason="no claim_head_versions row has selected = 1")
        return {"heads": 0, "predictions": 0, "run_id": None}

    population = claims_features.predict_population(conn, embedder_model_key=embedder_model_key)
    matrix = np.asarray([unpack(r.embedding) for r in population], dtype=np.float64) \
        if population else np.zeros((0, 0))

    config = {"embedder_model_key": embedder_model_key,
              "heads": [h["model_version"] for h in heads],
              "population": len(population)}
    run_id = runs.start_run(conn, claims.PREDICT_STAGE, config=config,
                            input_scope={"heads": len(heads)})
    now = runs.utcnow()
    written = 0
    try:
        for h in heads:
            _verify_artifact(h)
            splits = _chunk_splits(conn, h["heldout_candidate_ids_json"], h["predicate"])
            if h["model_type"] == "logreg":
                scores = _load_logreg(h["artifact_path"]).proba(matrix) if len(population) \
                    else np.zeros(0)
            elif h["model_type"] == "setfit":
                from setfit import SetFitModel  # type: ignore

                model = SetFitModel.from_pretrained(h["artifact_path"])
                probs = model.predict_proba([r.text for r in population]) if population else []
                scores = np.asarray([float(p[1]) for p in probs]) if len(probs) else np.zeros(0)
            else:  # pragma: no cover - schema CHECK-equivalent
                raise ValueError(f"unknown model_type {h['model_type']!r}")

            for row, score in zip(population, scores):
                s = float(score)
                conn.execute(_UPSERT_PREDICTION, (
                    row.chunk_id, h["category"], h["model_version"],
                    1 if s >= 0.5 else 0, round(s, 6),
                    splits.get(row.chunk_id, "unlabelled"), run_id, now))
                written += 1
            if not dry_run:
                conn.commit()
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_written=written,
                        error=f"{type(exc).__name__}: {exc}")
        if not dry_run:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=len(population),
                    rows_written=written)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"heads": len(heads), "predictions": written, "run_id": run_id,
            "population": len(population), "dry_run": dry_run}
