"""Training the 034G claim-prediction heads -- the per-category bake-off.

For each gate category the readiness gate reports `ready`, two candidate
models are fitted on an identical train split and scored once on an identical
deterministic held-out set:

  * ``logreg`` -- a pure-Python + numpy logistic regression on the stored 034A
    chunk embeddings. No scikit-learn: at this size (a few hundred 384-d
    vectors) full-batch gradient descent is milliseconds, and a head with no
    learned artifact beyond a coefficient vector is the more transparent
    thing to version. This is the same call the project makes computing exact
    cosine in Python rather than pulling a BLAS.
  * ``setfit`` -- sentence-transformer body + contrastive fine-tune + a
    classifier head. Helps most when the data is tiny *and* the base embedder
    is a poor domain fit; whether that beats plain logreg here is the point
    of measuring both.

Per category the head with the higher held-out **precision** that also clears
`min_precision` is `selected` and may write predictions; a head below the bar
is `quarantined` (recorded, never writes); a head that cleared the bar but
lost on precision is `lost-bakeoff`. Ties go to logreg.

Nothing is promoted, nothing is written to `graph_claims`, the review queue
is not touched. See `docs/claim-predictions-spec.md`.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

from pipeline.nlp import claims, claims_features, runs
from pipeline.nlp import gate as gate_mod
from pipeline.nlp.embeddings import unpack

_LOGREG_HYPERPARAMS = {"l2": 1.0, "iters": 400, "lr": 0.5}
_SETFIT_HYPERPARAMS = {"epochs": 1, "batch_size": 16, "num_iterations": 20}


# --- the pure-Python logistic-regression head ------------------------------

@dataclass
class LogRegHead:
    coef: list[float]
    intercept: float
    dim: int

    def proba(self, matrix: np.ndarray) -> np.ndarray:
        z = matrix @ np.asarray(self.coef, dtype=np.float64) + self.intercept
        return 1.0 / (1.0 + np.exp(-z))


def _fit_logreg(matrix: np.ndarray, labels: np.ndarray, *,
                l2: float, iters: int, lr: float) -> LogRegHead:
    """Full-batch gradient descent, L2-penalised, class-balanced so a skewed
    corpus does not train a head that just predicts the majority class."""
    n, d = matrix.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    pos = float(labels.sum())
    neg = float(n - pos)
    # weight each class to a total mass of n/2, so neither dominates the step.
    wpos = (n / (2.0 * pos)) if pos else 0.0
    wneg = (n / (2.0 * neg)) if neg else 0.0
    sample_w = np.where(labels == 1, wpos, wneg)
    for _ in range(iters):
        z = matrix @ w + b
        pred = 1.0 / (1.0 + np.exp(-z))
        err = (pred - labels) * sample_w
        grad_w = matrix.T @ err / n + l2 * w / n
        grad_b = float(err.sum() / n)
        w -= lr * grad_w
        b -= lr * grad_b
    return LogRegHead(coef=[float(x) for x in w], intercept=float(b), dim=d)


# --- evaluation -----------------------------------------------------------

@dataclass(frozen=True)
class Metrics:
    precision: float
    recall: float
    f1: float

    @staticmethod
    def score(y_true: list[int], y_pred: list[int]) -> "Metrics":
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) else 0.0)
        return Metrics(round(precision, 4), round(recall, 4), round(f1, 4))


# --- feature matrices ---------------------------------------------------

def _matrix(examples: list[claims_features.Example]) -> tuple[np.ndarray, np.ndarray, list]:
    """(X, y, kept) for the examples whose chunk is embedded. An example with
    no vector is dropped from BOTH models' sets by the caller so the bake-off
    stays a fair comparison; here it is just skipped."""
    rows, ys, kept = [], [], []
    for e in examples:
        if e.embedding is None:
            continue
        rows.append(unpack(e.embedding))
        ys.append(e.label)
        kept.append(e)
    if not rows:
        return np.zeros((0, 0), dtype=np.float64), np.zeros(0), []
    return (np.asarray(rows, dtype=np.float64), np.asarray(ys, dtype=np.float64), kept)


# --- artifacts --------------------------------------------------------

def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_path(path) -> str:
    """SHA-256 of a file, or of a directory's sorted (relpath, bytes)."""
    if path.is_file():
        return _hash_bytes(path.read_bytes())
    h = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(child.relative_to(path).as_posix().encode("utf-8"))
        h.update(child.read_bytes())
    return h.hexdigest()


# --- head results carried through the bake-off -----------------------

@dataclass
class HeadResult:
    model_type: str
    model_version: str
    config_sha256: str
    metrics: Metrics
    n_train_pos: int
    n_train_neg: int
    n_heldout_pos: int
    n_heldout_neg: int
    status: str
    artifact_path: str | None
    artifact_sha256: str | None
    setfit_base_model: str | None
    predictor: object = field(repr=False, default=None)  # LogRegHead or a SetFit model, for the caller


def _model_version(model_type: str, category: str, cutoff: str, config_hash: str) -> str:
    day = "".join(ch for ch in cutoff[:10] if ch.isdigit()) or "00000000"
    return f"{model_type}-{category}-{day}-{config_hash[:8]}"


def _config_hash(model_type: str, category: str, predicate: str, *, embedder_model_key: str,
                 corpus: str, corpus_cutoff: str, min_precision: float) -> str:
    hp = _LOGREG_HYPERPARAMS if model_type == "logreg" else _SETFIT_HYPERPARAMS
    return runs.config_sha256({
        "model_type": model_type, "category": category, "predicate": predicate,
        "embedder_model_key": embedder_model_key if model_type == "logreg" else None,
        "setfit_base_model": claims.SETFIT_BASE_MODEL if model_type == "setfit" else None,
        "hyperparams": hp, "heldout_seed": claims.HELDOUT_SEED,
        "heldout_per_class": claims.HELDOUT_PER_CLASS, "corpus": corpus,
        "corpus_cutoff": corpus_cutoff, "min_precision": min_precision,
    })


# --- the two fitters -------------------------------------------------

def _train_logreg(category, predicate, train_ex, heldout_ex, *, embedder_model_key,
                  corpus, corpus_cutoff, min_precision, artifact_root, write_artifacts):
    Xtr, ytr, kept_tr = _matrix(train_ex)
    Xho, yho, kept_ho = _matrix(heldout_ex)
    if Xtr.shape[0] == 0 or Xho.shape[0] == 0:
        raise claims_features.FeatureError(
            f"{category}: no embedded examples under {embedder_model_key!r} "
            "-- run `nlp embed` over the corpus first.")
    head = _fit_logreg(Xtr, ytr, **_LOGREG_HYPERPARAMS)
    pred = [1 if p >= 0.5 else 0 for p in head.proba(Xho)]
    metrics = Metrics.score([int(v) for v in yho], pred)
    config_hash = _config_hash("logreg", category, predicate,
                               embedder_model_key=embedder_model_key, corpus=corpus,
                               corpus_cutoff=corpus_cutoff, min_precision=min_precision)
    version = _model_version("logreg", category, corpus_cutoff, config_hash)

    blob = json.dumps({
        "model_type": "logreg", "category": category, "predicate": predicate,
        "embedder_model_key": embedder_model_key, "dim": head.dim,
        "coef": head.coef, "intercept": head.intercept,
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    artifact_path = artifact_sha256 = None
    if write_artifacts:
        dest = artifact_root / category
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / f"{version}.json"
        target.write_bytes(blob)
        artifact_path = target.as_posix()
    artifact_sha256 = _hash_bytes(blob)

    return HeadResult(
        model_type="logreg", model_version=version, config_sha256=config_hash,
        metrics=metrics, n_train_pos=int(ytr.sum()), n_train_neg=int(len(ytr) - ytr.sum()),
        n_heldout_pos=int(yho.sum()), n_heldout_neg=int(len(yho) - yho.sum()),
        status="passed" if metrics.precision >= min_precision else "quarantined",
        artifact_path=artifact_path, artifact_sha256=artifact_sha256,
        setfit_base_model=None, predictor=head)


def _train_setfit(category, predicate, train_ex, heldout_ex, *, embedder_model_key,
                  corpus, corpus_cutoff, min_precision, artifact_root, write_artifacts):
    # Imported here, never at module load: setfit (and its datasets / sklearn
    # deps) is `nlp`-extra only and absent from the default test env.
    from datasets import Dataset  # type: ignore
    from setfit import SetFitModel, Trainer, TrainingArguments  # type: ignore

    kept_tr = [e for e in train_ex if e.embedding is not None]
    kept_ho = [e for e in heldout_ex if e.embedding is not None]
    if not kept_tr or not kept_ho:
        raise claims_features.FeatureError(
            f"{category}: no embedded examples for the SetFit bake-off arm.")

    model = SetFitModel.from_pretrained(claims.SETFIT_BASE_MODEL)
    train_ds = Dataset.from_dict({"text": [e.text for e in kept_tr],
                                  "label": [e.label for e in kept_tr]})
    args = TrainingArguments(
        batch_size=_SETFIT_HYPERPARAMS["batch_size"],
        num_epochs=_SETFIT_HYPERPARAMS["epochs"],
        num_iterations=_SETFIT_HYPERPARAMS["num_iterations"])
    Trainer(model=model, args=args, train_dataset=train_ds).train()

    preds = [int(v) for v in model.predict([e.text for e in kept_ho])]
    metrics = Metrics.score([e.label for e in kept_ho], preds)
    config_hash = _config_hash("setfit", category, predicate,
                               embedder_model_key=embedder_model_key, corpus=corpus,
                               corpus_cutoff=corpus_cutoff, min_precision=min_precision)
    version = _model_version("setfit", category, corpus_cutoff, config_hash)

    artifact_path = artifact_sha256 = None
    dest = artifact_root / "setfit" / category / version
    if write_artifacts:
        dest.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(dest))
        artifact_path = dest.as_posix()
        artifact_sha256 = _hash_path(dest)

    return HeadResult(
        model_type="setfit", model_version=version, config_sha256=config_hash,
        metrics=metrics,
        n_train_pos=sum(e.label for e in kept_tr),
        n_train_neg=sum(1 - e.label for e in kept_tr),
        n_heldout_pos=sum(e.label for e in kept_ho),
        n_heldout_neg=sum(1 - e.label for e in kept_ho),
        status="passed" if metrics.precision >= min_precision else "quarantined",
        artifact_path=artifact_path, artifact_sha256=artifact_sha256,
        setfit_base_model=claims.SETFIT_BASE_MODEL, predictor=model)


_FITTERS = {"logreg": _train_logreg, "setfit": _train_setfit}


# --- persistence ---------------------------------------------------

_UPSERT_HEAD = """
INSERT INTO claim_head_versions (
    model_version, category, predicate, model_type, embedder_model_key,
    setfit_base_model, config_sha256, corpus, corpus_cutoff, corpus_status,
    heldout_candidate_ids_json, n_train_pos, n_train_neg, n_heldout_pos,
    n_heldout_neg, heldout_precision, heldout_recall, heldout_f1, min_precision,
    status, selected, artifact_path, artifact_sha256, code_commit, nlp_run_id,
    trained_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(model_version) DO UPDATE SET
    heldout_candidate_ids_json = excluded.heldout_candidate_ids_json,
    n_train_pos = excluded.n_train_pos, n_train_neg = excluded.n_train_neg,
    n_heldout_pos = excluded.n_heldout_pos, n_heldout_neg = excluded.n_heldout_neg,
    heldout_precision = excluded.heldout_precision,
    heldout_recall = excluded.heldout_recall, heldout_f1 = excluded.heldout_f1,
    min_precision = excluded.min_precision, status = excluded.status,
    selected = excluded.selected, artifact_path = excluded.artifact_path,
    artifact_sha256 = excluded.artifact_sha256, code_commit = excluded.code_commit,
    nlp_run_id = excluded.nlp_run_id, trained_at = excluded.trained_at
"""


def _persist_category(conn, *, category, predicate, results: list[HeadResult],
                      heldout_ids: list[str], embedder_model_key, corpus, corpus_status,
                      corpus_cutoff, min_precision, run_id, now):
    # Pick the winner: highest held-out precision among heads that cleared the
    # bar, logreg first so a tie stays with it.
    passed = [r for r in sorted(results, key=lambda r: (r.model_type != "logreg",))
              if r.status == "passed"]
    winner = max(passed, key=lambda r: r.metrics.precision, default=None)
    for r in results:
        if r is winner:
            r.status = "passed"
        elif r.status == "passed":
            r.status = "lost-bakeoff"

    # One live head per category: clear the old selection before the new
    # winner is written (the partial unique index forbids two).
    conn.execute("UPDATE claim_head_versions SET selected = 0 "
                 "WHERE category = ? AND selected = 1", (category,))
    heldout_json = json.dumps(sorted(heldout_ids))
    for r in results:
        conn.execute(_UPSERT_HEAD, (
            r.model_version, category, predicate, r.model_type,
            embedder_model_key if r.model_type == "logreg" else None,
            r.setfit_base_model, r.config_sha256, corpus, corpus_cutoff, corpus_status,
            heldout_json, r.n_train_pos, r.n_train_neg, r.n_heldout_pos, r.n_heldout_neg,
            r.metrics.precision, r.metrics.recall, r.metrics.f1, min_precision,
            r.status, 1 if r is winner else 0, r.artifact_path, r.artifact_sha256,
            runs.code_commit(), run_id, now))
    return winner


# --- the stage -----------------------------------------------------

def train(conn, *, categories: list[str] | None = None,
          models: tuple[str, ...] = claims.MODEL_TYPES,
          min_precision: float = claims.MIN_HEAD_PRECISION,
          embedder_model_key: str = claims.DEFAULT_EMBEDDER_MODEL_KEY,
          corpus_label: str = "beta-box", corpus_status: str = "experimental",
          artifact_root=None, dry_run: bool = False) -> dict:
    """Run the bake-off for each ready (or explicitly named) category. Returns
    a per-category summary. `--category` bypasses the gate and always records
    `corpus_status='experimental'` unless overridden."""
    artifact_root = artifact_root or claims.ARTIFACT_ROOT
    report = gate_mod.check(conn)
    if categories is None:
        categories = [n for n, c in report["categories"].items() if c["ready"]]
        if not report["ready"] or not categories:
            return {"trained": [], "blocking": report["blocking"], "ready": report["ready"]}
    unknown = [c for c in categories if c not in gate_mod.GATE_CATEGORIES]
    if unknown:
        raise claims_features.FeatureError(f"not gate categories: {unknown}")

    config = {"models": list(models), "min_precision": min_precision,
              "embedder_model_key": embedder_model_key, "corpus": corpus_label,
              "corpus_status": corpus_status, "categories": categories,
              "heldout_seed": claims.HELDOUT_SEED}
    run_id = runs.start_run(conn, claims.TRAIN_STAGE, config=config,
                            input_scope={"categories": categories})
    now = runs.utcnow()
    summary: list[dict] = []
    processed = 0
    try:
        for category in categories:
            predicate = gate_mod.GATE_CATEGORIES[category]
            examples = claims_features.labelled_examples(
                conn, category, embedder_model_key=embedder_model_key)
            train_ex, heldout_ex = claims_features.split_examples(examples, category)
            cutoff = claims_features.corpus_cutoff(train_ex + heldout_ex)
            heldout_ids = [e.candidate_id for e in heldout_ex]

            results: list[HeadResult] = []
            unavailable: list[dict] = []
            for model_type in models:
                try:
                    results.append(_FITTERS[model_type](
                        category, predicate, train_ex, heldout_ex,
                        embedder_model_key=embedder_model_key, corpus=corpus_label,
                        corpus_cutoff=cutoff, min_precision=min_precision,
                        artifact_root=artifact_root, write_artifacts=not dry_run))
                except ImportError as exc:
                    # A bake-off arm whose backend will not import (SetFit vs a
                    # transformers major it has not caught up to, say). Skip the
                    # arm, keep the others -- "run whatever ran", the same
                    # spirit as claims_predict running whatever passed.
                    unavailable.append({"model_type": model_type,
                                        "error": f"{type(exc).__name__}: {exc}"})
            processed += 1
            winner = _persist_category(
                conn, category=category, predicate=predicate, results=results,
                heldout_ids=heldout_ids, embedder_model_key=embedder_model_key,
                corpus=corpus_label, corpus_status=corpus_status, corpus_cutoff=cutoff,
                min_precision=min_precision, run_id=run_id, now=now) if results else None
            if not dry_run:
                conn.commit()
            entry = {
                "category": category, "corpus_cutoff": cutoff,
                "n_train": len(train_ex), "n_heldout": len(heldout_ex),
                "selected": winner.model_version if winner else None,
                "heads": [{"model_type": r.model_type, "model_version": r.model_version,
                           "precision": r.metrics.precision, "recall": r.metrics.recall,
                           "f1": r.metrics.f1, "status": r.status} for r in results],
            }
            if unavailable:
                entry["unavailable"] = unavailable
            summary.append(entry)
    except Exception as exc:  # noqa: BLE001 - recorded on the run, then re-raised
        runs.finish_run(conn, run_id, status="failed", rows_processed=processed,
                        error=f"{type(exc).__name__}: {exc}")
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
        raise
    runs.finish_run(conn, run_id, status="ok", rows_processed=processed,
                    rows_written=len(summary))
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
    return {"trained": summary, "run_id": run_id, "ready": report["ready"],
            "min_precision": min_precision, "dry_run": dry_run}
