"""pipeline/nlp/claims_predict.py -- scoring with the selected heads, and the
fence that keeps predictions out of every export and every portal response."""
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.nlp import claims_predict, claims_train
from tests.nlp_claims_support import STUB_MODEL_KEY, seed_labelled

KW = dict(models=("logreg",), embedder_model_key=STUB_MODEL_KEY, corpus_label="fixture")


def _train(conn, tmp_path, category="vacancy_pressure", **over):
    seed_labelled(conn, category, n_pos=25, n_neg=25, seed=over.pop("seed", 7),
                  separable=over.pop("separable", True))
    return claims_train.train(conn, categories=[category], artifact_root=tmp_path,
                              **{**KW, **over})


def test_selected_head_scores_the_whole_embedded_population(conn, tmp_path):
    _train(conn, tmp_path)
    result = claims_predict.predict(conn, embedder_model_key=STUB_MODEL_KEY)

    assert result["heads"] == 1
    assert result["predictions"] == 50            # one row per embedded chunk
    rows = conn.execute(
        "SELECT label, score, split FROM document_claim_predictions").fetchall()
    assert len(rows) == 50
    assert {r["split"] for r in rows} <= {"train", "heldout", "unlabelled"}
    assert any(r["split"] == "heldout" for r in rows)
    assert all(0.0 <= r["score"] <= 1.0 for r in rows)
    assert all(r["label"] in (0, 1) for r in rows)


def test_prediction_persistence_uses_bounded_executemany_pages(conn, tmp_path, monkeypatch):
    _train(conn, tmp_path)
    monkeypatch.setattr(claims_predict, "PREDICTION_WRITE_BATCH_SIZE", 7)

    class RecordingConnection:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.batch_sizes = []

        def execute(self, *args, **kwargs):
            return self.wrapped.execute(*args, **kwargs)

        def executemany(self, sql, values):
            values = list(values)
            if "document_claim_predictions" in sql:
                self.batch_sizes.append(len(values))
            return self.wrapped.executemany(sql, values)

        def commit(self):
            return self.wrapped.commit()

        def rollback(self):
            return self.wrapped.rollback()

        @property
        def raw(self):
            return self.wrapped.raw

    recording = RecordingConnection(conn)
    result = claims_predict.predict(recording, embedder_model_key=STUB_MODEL_KEY)
    assert result["predictions"] == 50
    assert recording.batch_sizes == [7, 7, 7, 7, 7, 7, 7, 1]


def test_prediction_page_failure_rolls_back_only_that_page(conn, tmp_path, monkeypatch):
    _train(conn, tmp_path)
    monkeypatch.setattr(claims_predict, "PREDICTION_WRITE_BATCH_SIZE", 7)

    class FailingConnection:
        def __init__(self, wrapped):
            self.wrapped = wrapped
            self.prediction_batches = 0

        @property
        def raw(self):
            return self.wrapped.raw

        def execute(self, *args, **kwargs):
            return self.wrapped.execute(*args, **kwargs)

        def executemany(self, sql, values):
            values = list(values)
            if "document_claim_predictions" in sql:
                self.prediction_batches += 1
                if self.prediction_batches == 2:
                    self.wrapped.execute(sql, values[0])
                    raise RuntimeError("fixture prediction page failed")
            return self.wrapped.executemany(sql, values)

        def commit(self):
            return self.wrapped.commit()

        def rollback(self):
            return self.wrapped.rollback()

    with pytest.raises(RuntimeError, match="fixture prediction page failed"):
        claims_predict.predict(FailingConnection(conn), embedder_model_key=STUB_MODEL_KEY)
    assert conn.execute(
        "SELECT COUNT(*) AS count FROM document_claim_predictions"
    ).fetchone()["count"] == 7
    assert conn.execute(
        "SELECT status FROM nlp_runs WHERE stage=%s ORDER BY started_at DESC LIMIT 1",
        ("claims-predict",),
    ).fetchone()["status"] == "failed"


def test_zero_selected_heads_is_a_logged_noop(conn):
    result = claims_predict.predict(conn, embedder_model_key=STUB_MODEL_KEY)
    assert result == {"heads": 0, "predictions": 0, "run_id": None}
    assert conn.execute("SELECT COUNT(*) FROM document_claim_predictions").fetchone().values().__iter__().__next__() == 0


def test_quarantined_head_writes_no_predictions(conn, tmp_path):
    _train(conn, tmp_path, category="agency_reliance", separable=False, seed=8,
           min_precision=0.999)
    result = claims_predict.predict(conn, embedder_model_key=STUB_MODEL_KEY)
    assert result["heads"] == 0 and result["predictions"] == 0


def test_artifact_hash_mismatch_refuses_the_run(conn, tmp_path):
    _train(conn, tmp_path)
    artifact = next(tmp_path.rglob("*.json"))
    artifact.write_text(artifact.read_text() + " ")     # one byte, hash no longer matches
    with pytest.raises(claims_predict.ArtifactMismatch, match="SHA-256"):
        claims_predict.predict(conn, embedder_model_key=STUB_MODEL_KEY)
    assert conn.execute("SELECT COUNT(*) FROM document_claim_predictions").fetchone().values().__iter__().__next__() == 0


def test_dry_run_scores_but_writes_nothing(conn, tmp_path):
    _train(conn, tmp_path)
    result = claims_predict.predict(conn, embedder_model_key=STUB_MODEL_KEY, dry_run=True)
    assert result["predictions"] == 50 and result["dry_run"] is True
    assert conn.execute("SELECT COUNT(*) FROM document_claim_predictions").fetchone().values().__iter__().__next__() == 0


# --- the fence ------------------------------------------------------------

FENCED_TABLES = ("document_claim_predictions", "claim_head_versions")
_ROOT = Path(__file__).resolve().parent.parent / "pipeline"


@pytest.mark.parametrize("table", FENCED_TABLES)
def test_no_export_module_names_the_prediction_tables(table):
    """Exports are opt-in per module; a prediction table appearing in one is
    the mistake this catches. Same discipline as 034C topics -- a finding aid
    never leaves the warehouse."""
    for path in (_ROOT / "exports").glob("*.py"):
        assert table not in path.read_text(encoding="utf-8"), f"{table} referenced in {path.name}"


@pytest.mark.parametrize("table", FENCED_TABLES)
def test_no_portal_query_or_route_names_the_prediction_tables(table):
    portal = [_ROOT / "web" / "public_queries.py", _ROOT / "web" / "public_export.py",
              _ROOT / "web" / "server.py"]
    for path in portal:
        assert table not in path.read_text(encoding="utf-8"), f"{table} referenced in {path.name}"
