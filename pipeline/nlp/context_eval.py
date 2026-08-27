"""Assertion-detector eval -- accuracy per class, and the hard negatives.

"The rule fires" is not "the rule is right". This scores a detector against
labelled sentences and reports overall accuracy, per-class precision /
recall, and a confusion count. The hard negatives are in the same file and
carry `"hard_negative": true` so their pass/fail is called out separately --
those are the sentences the whole tranche exists to get right.

JSON, not YAML (no YAML dependency in the base install; must run offline).
Each case:

    {
      "id": "no-concerns",
      "text": "No staffing concerns were identified.",
      "target": "staffing concerns",
      "expected": "NEGATED",
      "hard_negative": true
    }
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.nlp import context as context_mod

DEFAULT_CASE_SET = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "nlp" / "assertion_cases.json")


def _load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data["cases"] if isinstance(data, dict) else data
    for case in cases:
        if not case.get("text") or not case.get("target") or not case.get("expected"):
            raise ValueError(f"case {case.get('id')!r} is missing text/target/expected")
        if case["expected"] not in context_mod.STATUSES:
            raise ValueError(f"case {case.get('id')!r}: unknown expected {case['expected']!r}")
    return cases


def _predict(tagger, text: str, target: str) -> str:
    lowered = text.lower()
    idx = lowered.find(target.lower())
    if idx < 0:
        return "UNKNOWN"
    located = context_mod.sentence_for(text, idx, idx + len(target))
    if located is None:
        return "UNKNOWN"
    sentence, start, end = located
    return tagger.tag(sentence, start, end).status


def run(*, cases_path: Path | str | None = None, detector: str | None = None) -> dict:
    path = Path(cases_path) if cases_path else DEFAULT_CASE_SET
    cases = _load(path)
    tagger = context_mod.get_tagger(detector)

    correct = 0
    confusion: dict[str, dict[str, int]] = {}
    per_class: dict[str, list[int]] = {}   # expected -> [tp, fp, fn]
    hard_fail: list[str] = []
    per_case: list[dict] = []

    for case in cases:
        predicted = _predict(tagger, case["text"], case["target"])
        expected = case["expected"]
        hit = predicted == expected
        correct += hit
        confusion.setdefault(expected, {}).setdefault(predicted, 0)
        confusion[expected][predicted] += 1
        per_class.setdefault(expected, [0, 0, 0])
        per_class.setdefault(predicted, [0, 0, 0])
        if hit:
            per_class[expected][0] += 1
        else:
            per_class[predicted][1] += 1
            per_class[expected][2] += 1
        if case.get("hard_negative") and not hit:
            hard_fail.append(case.get("id"))
        per_case.append({"id": case.get("id"), "expected": expected,
                         "predicted": predicted, "correct": hit,
                         "hard_negative": bool(case.get("hard_negative"))})

    def _prf(tp: int, fp: int, fn: int) -> dict:
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4),
                "tp": tp, "fp": fp, "fn": fn}

    n_hard = sum(1 for c in cases if c.get("hard_negative"))
    return {
        "cases_path": str(path),
        "detector": tagger.name,
        "detector_version": tagger.version,
        "n_cases": len(cases),
        "accuracy": round(correct / len(cases), 4) if cases else 0.0,
        "hard_negatives": {"total": n_hard, "failed": hard_fail,
                           "passed": n_hard - len(hard_fail)},
        "by_class": {status: _prf(*counts) for status, counts in sorted(per_class.items())},
        "confusion": confusion,
        "per_case": per_case,
    }
