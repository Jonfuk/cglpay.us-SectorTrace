"""Span-extraction eval — precision / recall / F1 per label.

"The code runs" is not "the extractor improved". This scores a span
extractor against a human-annotated set and reports P/R/F1 overall and per
label, so a model or threshold change is a measured decision.

The gold set is JSON (no YAML dependency in the base install; must run in the
offline suite). Each entry:

    {
      "id": "cgl-ost",
      "text": "Change Grow Live delivers opioid substitution treatment ...",
      "source_system": "committee_paper_promotion",   # optional
      "spans": [
        {"label": "PROVIDER", "text": "Change Grow Live"},
        {"label": "TREATMENT", "text": "opioid substitution treatment"}
      ]
    }

A predicted span counts as a hit when a gold span shares its label and its
surface text (case-insensitively), each gold span consumed once. Offsets are
not compared — annotators mark strings, and the two extractors tokenise
differently.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.nlp import spans as spans_mod

DEFAULT_GOLD_SET = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "nlp" / "gold_spans.json")


def _load(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data["entries"] if isinstance(data, dict) else data
    for entry in entries:
        if not entry.get("text"):
            raise ValueError(f"gold entry {entry.get('id')!r} has no text")
    return entries


def _score_entry(predicted: list, gold: list[dict]) -> dict[str, list[int]]:
    """{label: [tp, fp, fn]} for one entry."""
    remaining: dict[tuple[str, str], int] = {}
    for span in gold:
        key = (span["label"].upper(), span["text"].strip().lower())
        remaining[key] = remaining.get(key, 0) + 1
    tally: dict[str, list[int]] = {}
    for span in predicted:
        key = (span.label.upper(), span.text.strip().lower())
        slot = tally.setdefault(key[0], [0, 0, 0])
        if remaining.get(key, 0) > 0:
            remaining[key] -= 1
            slot[0] += 1          # tp
        else:
            slot[1] += 1          # fp
    for (label, _), count in remaining.items():
        tally.setdefault(label, [0, 0, 0])[2] += count   # fn
    return tally


def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 6), "recall": round(recall, 6),
            "f1": round(f1, 6), "tp": tp, "fp": fp, "fn": fn}


def run(conn, *, gold_path: Path | str | None = None,
        extractor: str | None = None) -> dict:
    path = Path(gold_path) if gold_path else DEFAULT_GOLD_SET
    entries = _load(path)
    ex = spans_mod.get_extractor(extractor)

    totals: dict[str, list[int]] = {}
    per_entry: list[dict] = []
    for entry in entries:
        predicted = ex.extract(entry["text"])
        tally = _score_entry(predicted, entry.get("spans") or [])
        for label, (tp, fp, fn) in tally.items():
            slot = totals.setdefault(label, [0, 0, 0])
            slot[0] += tp
            slot[1] += fp
            slot[2] += fn
        per_entry.append({
            "id": entry.get("id"),
            "n_gold": len(entry.get("spans") or []),
            "n_predicted": len(predicted),
            "by_label": {label: _prf(*v) for label, v in tally.items()},
        })

    micro = [sum(v[i] for v in totals.values()) for i in range(3)]
    return {
        "gold_path": str(path),
        "extractor": ex.name,
        "extractor_version": ex.version,
        "n_entries": len(entries),
        "overall": _prf(*micro),
        "by_label": {label: _prf(*v) for label, v in sorted(totals.items())},
        "per_entry": per_entry,
    }
