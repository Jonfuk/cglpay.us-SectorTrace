"""The SetFit arm of the bake-off -- a real contrastive fine-tune, so it needs
the `nlp` extra and is far too slow for CI. Marked `slow`, deselected by
default (see pyproject `addopts`); run with `-m slow`.
"""
from __future__ import annotations

import pytest

from tests.nlp_claims_support import STUB_MODEL_KEY, seed_labelled

pytestmark = pytest.mark.slow


def test_setfit_head_trains_and_takes_part_in_the_bakeoff(conn, tmp_path):
    pytest.importorskip("setfit")
    from pipeline.nlp import claims_train

    seed_labelled(conn, "vacancy_pressure", n_pos=25, n_neg=25, seed=99)
    result = claims_train.train(
        conn, categories=["vacancy_pressure"], models=("logreg", "setfit"),
        embedder_model_key=STUB_MODEL_KEY, corpus_label="fixture", artifact_root=tmp_path)

    heads = {r["model_type"]: dict(r) for r in conn.execute(
        "SELECT * FROM claim_head_versions WHERE category = 'vacancy_pressure'").fetchall()}
    assert set(heads) == {"logreg", "setfit"}
    assert sum(h["selected"] for h in heads.values()) <= 1
    assert heads["setfit"]["setfit_base_model"]
    assert heads["setfit"]["status"] in {"passed", "quarantined", "lost-bakeoff"}
    assert result["trained"][0]["selected"] in (
        heads["logreg"]["model_version"], heads["setfit"]["model_version"], None)
