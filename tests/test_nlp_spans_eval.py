"""pipeline/nlp/spans_eval.py — precision / recall / F1 for span extraction."""
from __future__ import annotations

import json

from pipeline.nlp import spans_eval


def _gold_file(tmp_path, entries):
    path = tmp_path / "gold.json"
    path.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return path


def test_perfect_extraction_scores_one(tmp_path, conn):
    # The gold set includes the nested SUBSTANCE span the stub also finds, so
    # a complete annotation scores 1.0 across the board.
    path = _gold_file(tmp_path, [{
        "id": "cgl",
        "text": "Change Grow Live delivers opioid substitution treatment.",
        "spans": [
            {"label": "PROVIDER", "text": "Change Grow Live"},
            {"label": "SUBSTANCE", "text": "opioid"},
            {"label": "TREATMENT", "text": "opioid substitution treatment"},
        ],
    }])
    report = spans_eval.run(conn, gold_path=path, extractor="stub")
    assert report["overall"]["precision"] == 1.0
    assert report["overall"]["recall"] == 1.0
    assert report["overall"]["f1"] == 1.0
    assert report["by_label"]["PROVIDER"]["tp"] == 1


def test_a_missed_gold_span_lowers_recall(tmp_path, conn):
    path = _gold_file(tmp_path, [{
        "id": "loc",
        "text": "Change Grow Live operates in Kent.",
        "spans": [
            {"label": "PROVIDER", "text": "Change Grow Live"},
            {"label": "LOCATION", "text": "Kent"},
        ],
    }])
    report = spans_eval.run(conn, gold_path=path, extractor="stub")
    # the stub finds the provider but not LOCATION
    assert report["by_label"]["PROVIDER"]["recall"] == 1.0
    assert report["by_label"]["LOCATION"]["fn"] == 1
    assert report["overall"]["recall"] == 0.5


def test_a_spurious_prediction_lowers_precision(tmp_path, conn):
    path = _gold_file(tmp_path, [{
        "id": "noise",
        "text": "methadone was discussed",
        "spans": [],
    }])
    report = spans_eval.run(conn, gold_path=path, extractor="stub")
    assert report["overall"]["fp"] >= 1
    assert report["overall"]["precision"] == 0.0


def test_committed_gold_set_loads_and_scores(conn):
    report = spans_eval.run(conn, extractor="stub")
    assert report["n_entries"] >= 4
    assert report["extractor"] == "ontology-stub"
    # the stub is dictionary-backed: it should do well on TREATMENT/ROLE,
    # this is a smoke check that the harness produces sane numbers.
    assert 0.0 <= report["overall"]["f1"] <= 1.0
    assert report["by_label"]["TREATMENT"]["tp"] >= 1
