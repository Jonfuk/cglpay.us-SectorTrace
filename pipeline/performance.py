"""Subsystem performance harness and machine-readable reports."""
from __future__ import annotations

import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUITES = (
    "web", "writes", "analysis", "nlp", "semantic", "ontology",
    "documents", "archive", "graph", "postgres", "ci", "all",
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _metadata() -> dict[str, Any]:
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def run(settings, suite: str = "all", *, output: Path | None = None) -> dict[str, Any]:
    if suite not in SUITES:
        raise ValueError(f"unknown performance suite {suite!r}; choose from {', '.join(SUITES)}")
    from pipeline import benchmark

    selected = [name for name in SUITES[:-1]] if suite == "all" else [suite]
    report: dict[str, Any] = {"suite": suite, "environment": _metadata(), "suites": {}}
    for name in selected:
        started_wall = time.perf_counter()
        started_cpu = time.process_time()
        if name == "web":
            result = benchmark.benchmark(settings, reads=True, writes=False)
        elif name == "writes":
            result = benchmark.benchmark(settings, reads=False, writes=True)
        else:
            result = {
                "status": "measurement_not_configured",
                "note": "Reserved for its subsystem benchmark; no timing claim is made.",
            }
        result["wall_seconds"] = round(time.perf_counter() - started_wall, 6)
        result["cpu_seconds"] = round(time.process_time() - started_cpu, 6)
        result["digest"] = _digest(result)
        report["suites"][name] = result
    report["digest"] = _digest(report["suites"])
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        report["written_to"] = str(output)
    return report

