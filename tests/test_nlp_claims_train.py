"""pipeline/nlp/claims_train.py -- the per-category bake-off.

The logreg arm trains for real in this suite (pure Python + numpy, a fixture
of a few dozen 16-d vectors). The SetFit arm needs the `nlp` extra and a real
fine-tune, so it lives in tests/test_nlp_claims_setfit.py behind the `slow`
marker; the winner-selection logic it feeds is unit-tested here with
fabricated results, no model required.
"""
from __future__ import annotations

import json

import pytest

from pipeline.nlp import claims, claims_train
from pipeline.nlp.claims_train import HeadResult, Metrics, _persist_category
from tests.nlp_claims_support import STUB_MODEL_KEY, seed_labelled

LOGREG = ("logreg",)
KW = dict(models=LOGREG, embedder_model_key=STUB_MODEL_KEY, corpus_label="fixture")


def _heads(conn, category=None):
    sql = "SELECT * FROM claim_head_versions"
    params = ()
    if category:
        sql += " WHERE category = ?"
        params = (category,)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def test_logreg_head_trains_selects_and_records(conn, tmp_path):
    seed_labelled(conn, "vacancy_pressure", n_pos=25, n_neg=25, seed=1)
    result = claims_train.train(conn, categories=["vacancy_pressure"],
                                artifact_root=tmp_path, **KW)

    [row] = _heads(conn, "vacancy_pressure")
    assert row["model_type"] == "logreg"
    assert row["status"] == "passed" and row["selected"] == 1
    assert row["model_version"].startswith("logreg-vacancy_pressure-")
    assert row["corpus"] == "fixture" and row["corpus_status"] == "experimental"
    assert row["heldout_precision"] >= 0.8          # separable fixture
    assert row["n_heldout_pos"] == claims.HELDOUT_PER_CLASS
    assert json.loads(row["heldout_candidate_ids_json"])  # the carve is recorded
    # the artifact is on disk and its hash is what was stored
    assert (tmp_path / "vacancy_pressure").glob("*.json")
    assert row["artifact_sha256"]
    # the run is closed ok
    run = conn.execute("SELECT status FROM nlp_runs WHERE run_id = ?",
                       (result["run_id"],)).fetchone()
    assert run["status"] == "ok"


def test_head_below_the_precision_bar_is_quarantined(conn, tmp_path):
    seed_labelled(conn, "agency_reliance", n_pos=25, n_neg=25, separable=False, seed=2)
    claims_train.train(conn, categories=["agency_reliance"],
                       min_precision=0.999, artifact_root=tmp_path, **KW)
    [row] = _heads(conn, "agency_reliance")
    assert row["status"] == "quarantined"
    assert row["selected"] == 0            # no prediction rights


def test_a_bakeoff_arm_that_will_not_import_is_skipped(conn, tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise ImportError("cannot import name 'default_logdir' from 'transformers.training_args'")

    monkeypatch.setitem(claims_train._FITTERS, "setfit", _boom)
    seed_labelled(conn, "vacancy_pressure", n_pos=25, n_neg=25, seed=20)
    result = claims_train.train(conn, categories=["vacancy_pressure"],
                                models=("logreg", "setfit"),
                                embedder_model_key=STUB_MODEL_KEY, corpus_label="fixture",
                                artifact_root=tmp_path)
    [entry] = result["trained"]
    assert [h["model_type"] for h in entry["heads"]] == ["logreg"]   # logreg still trained
    assert entry["unavailable"][0]["model_type"] == "setfit"
    assert "default_logdir" in entry["unavailable"][0]["error"]
    assert [r["model_type"] for r in _heads(conn, "vacancy_pressure")] == ["logreg"]


def test_dry_run_writes_no_rows_and_no_artifacts(conn, tmp_path):
    seed_labelled(conn, "vacancy_pressure", n_pos=25, n_neg=25, seed=3)
    claims_train.train(conn, categories=["vacancy_pressure"], dry_run=True,
                       artifact_root=tmp_path, **KW)
    assert _heads(conn) == []
    assert list(tmp_path.rglob("*.json")) == []


def test_gate_refusal_when_not_ready(conn):
    result = claims_train.train(conn, **KW)   # empty warehouse, no --category
    assert result["trained"] == [] and result["ready"] is False
    assert _heads(conn) == []


def test_retrain_keeps_one_selected_head_per_category(conn, tmp_path):
    seed_labelled(conn, "tupe_transfer", n_pos=25, n_neg=25, seed=4)
    claims_train.train(conn, categories=["tupe_transfer"], artifact_root=tmp_path, **KW)
    # a second run at a later corpus cutoff -> a new model_version
    conn.execute("UPDATE claim_candidate_decisions SET decided_at = '2026-10-01T00:00:00+00:00'")
    conn.commit()
    claims_train.train(conn, categories=["tupe_transfer"], artifact_root=tmp_path, **KW)
    rows = _heads(conn, "tupe_transfer")
    assert len(rows) == 2                                  # both kept
    assert sum(r["selected"] for r in rows) == 1           # exactly one live


def test_two_selected_rows_for_one_category_is_a_write_error(conn, tmp_path):
    import sqlite3

    seed_labelled(conn, "vacancy_pressure", n_pos=25, n_neg=25, seed=5)
    claims_train.train(conn, categories=["vacancy_pressure"], artifact_root=tmp_path, **KW)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO claim_head_versions (model_version, category, predicate, model_type, "
            "config_sha256, corpus, corpus_cutoff, corpus_status, heldout_candidate_ids_json, "
            "n_train_pos, n_train_neg, n_heldout_pos, n_heldout_neg, heldout_precision, "
            "heldout_recall, heldout_f1, min_precision, status, selected, nlp_run_id, trained_at) "
            "SELECT 'dupe', category, predicate, 'logreg', 'x', corpus, corpus_cutoff, "
            "corpus_status, '[]', 0,0,0,0,0,0,0,0.8, 'passed', 1, nlp_run_id, trained_at "
            "FROM claim_head_versions WHERE category = 'vacancy_pressure' LIMIT 1")


def _prep_run(conn, run_id):
    """A committed nlp_model_registry row and nlp_runs row for the FK targets
    of a direct _persist_category call. Committed because the write-slot
    connection can roll back uncommitted setup between statements."""
    conn.execute("INSERT INTO nlp_model_registry (model_key, model_provider, model_id, "
                 "first_seen_at) VALUES (?, 'stub', 'stub', ?) ON CONFLICT DO NOTHING",
                 (STUB_MODEL_KEY, "2026-08-31T00:00:00+00:00"))
    conn.execute("INSERT INTO nlp_runs (run_id, stage, status, started_at, config_sha256) "
                 "VALUES (?, 'claims-train', 'running', ?, 'x')",
                 (run_id, "2026-08-31T00:00:00+00:00"))
    conn.commit()


def _result(model_type, precision, status="passed"):
    return HeadResult(
        model_type=model_type, model_version=f"{model_type}-c-0-x",
        config_sha256="x" * 64, metrics=Metrics(precision, 0.5, 0.5),
        n_train_pos=1, n_train_neg=1, n_heldout_pos=1, n_heldout_neg=1,
        status=status, artifact_path=None, artifact_sha256="h",
        setfit_base_model=None)


def test_bakeoff_prefers_logreg_on_a_precision_tie(conn):
    _prep_run(conn, "r1")
    results = [_result("logreg", 0.9), _result("setfit", 0.9)]
    winner = _persist_category(
        conn, category="vacancy_pressure", predicate="workforce.has_vacancy_pressure",
        results=results, heldout_ids=["cand-x"], embedder_model_key=STUB_MODEL_KEY,
        corpus="fixture", corpus_status="experimental", corpus_cutoff="2026-08-31",
        min_precision=0.8, run_id="r1", now="2026-08-31T00:00:00+00:00")
    assert winner.model_type == "logreg"
    by_type = {r["model_type"]: r for r in conn.execute(
        "SELECT model_type, status, selected FROM claim_head_versions "
        "WHERE category = 'vacancy_pressure'").fetchall()}
    assert by_type["logreg"]["selected"] == 1 and by_type["logreg"]["status"] == "passed"
    assert by_type["setfit"]["selected"] == 0 and by_type["setfit"]["status"] == "lost-bakeoff"


def test_bakeoff_quarantines_both_when_neither_clears_the_bar(conn):
    _prep_run(conn, "r2")
    results = [_result("logreg", 0.4, "quarantined"), _result("setfit", 0.6, "quarantined")]
    winner = _persist_category(
        conn, category="agency_reliance", predicate="workforce.relies_on_agency",
        results=results, heldout_ids=[], embedder_model_key=STUB_MODEL_KEY,
        corpus="fixture", corpus_status="experimental", corpus_cutoff="2026-08-31",
        min_precision=0.8, run_id="r2", now="2026-08-31T00:00:00+00:00")
    assert winner is None
    assert all(r["selected"] == 0 for r in conn.execute(
        "SELECT selected FROM claim_head_versions WHERE category = 'agency_reliance'"))
