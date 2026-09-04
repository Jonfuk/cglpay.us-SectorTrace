"""Small, offline diagnostic for the Phase 2 narrative prefilter.

This deliberately measures only the deterministic gate over the committed
regression fixture.  It estimates the *potential* candidate reduction; it does
not represent human adjudication and it does not measure model cost while
suppression is disabled.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from pipeline.analysis.narrative import narrative_candidate_prefilter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "tests" / "fixtures" / "analysis" / "narrative_prefilter_regression.jsonl"


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction + 0.5))]


def _time(rows: list[dict], *, enabled: bool, repeat: int, repetitions: int) -> list[float]:
    def run_once() -> int:
        accepted = 0
        for _ in range(repeat):
            accepted += sum(
                narrative_candidate_prefilter(row["text"], enabled=enabled)
                for row in rows)
        return accepted

    run_once()  # warm the interpreter and regex machinery
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter_ns()
        run_once()
        samples.append((time.perf_counter_ns() - started) / 1_000_000)
    return samples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--repeat", type=int, default=10_000,
                        help="Times to replay the fixed corpus per sample.")
    parser.add_argument("--repetitions", type=int, default=7,
                        help="Timed samples after one warm-up.")
    parser.add_argument("--output", type=Path,
                        help="Optional JSON report destination.")
    args = parser.parse_args()
    if args.repeat < 1 or args.repetitions < 1:
        parser.error("--repeat and --repetitions must be positive")

    rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    baseline = _time(rows, enabled=False, repeat=args.repeat, repetitions=args.repetitions)
    candidate = _time(rows, enabled=True, repeat=args.repeat, repetitions=args.repetitions)
    candidate_once = [narrative_candidate_prefilter(row["text"], enabled=True) for row in rows]
    baseline_once = [narrative_candidate_prefilter(row["text"], enabled=False) for row in rows]
    baseline_p50 = statistics.median(baseline)
    candidate_p50 = statistics.median(candidate)
    report = {
        "benchmark_version": "phase2-prefilter-micro-v1",
        "corpus": str(args.corpus.relative_to(ROOT)) if args.corpus.is_relative_to(ROOT)
        else str(args.corpus),
        "corpus_is_production_adjudication": False,
        "rows": len(rows),
        "repeat_per_sample": args.repeat,
        "repetitions": args.repetitions,
        "baseline_enabled_false": {
            "accepted_per_pass": sum(baseline_once),
            "samples_ms": [round(value, 3) for value in baseline],
            "p50_ms": round(baseline_p50, 3),
            "p95_ms": round(_percentile(baseline, 0.95), 3),
        },
        "prefilter_enabled_true": {
            "accepted_per_pass": sum(candidate_once),
            "samples_ms": [round(value, 3) for value in candidate],
            "p50_ms": round(candidate_p50, 3),
            "p95_ms": round(_percentile(candidate, 0.95), 3),
        },
        "potential_model_calls_avoided_per_pass": len(rows) - sum(candidate_once),
        "potential_candidate_reduction_fraction": round(
            (len(rows) - sum(candidate_once)) / len(rows), 6),
        "prefilter_cpu_overhead_fraction": round(
            (candidate_p50 - baseline_p50) / baseline_p50, 6) if baseline_p50 else None,
        "caveat": (
            "Fixture-only deterministic timing. Potential model-call reduction is not "
            "realised while suppression is disabled and this fixture is not human adjudication."
        ),
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
