"""Deterministic structured-data comparisons and robust anomaly ranking."""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Iterable

from pipeline.analysis.signals import Signal, new_signal

MISSING_STATUSES = frozenset({"missing", "suppressed", "schema_incompatible", "unavailable"})


@dataclass(frozen=True)
class Observation:
    source_table: str
    source_row_id: str
    subject_type: str
    subject_id: str
    metric: str
    value: float | int | str | None
    unit: str
    period_start: str | None
    period_end: str | None
    status: str = "observed"

    @classmethod
    def from_row(cls, row: dict[str, Any], *, source_table: str, source_row_id: str,
                 subject_type: str, subject_id: str, metric: str, value_key: str = "value",
                 unit_key: str = "unit", period_start_key: str = "period_start",
                 period_end_key: str = "period_end") -> "Observation":
        return cls(source_table, source_row_id, subject_type, subject_id, metric,
                   row.get(value_key), str(row.get(unit_key) or ""),
                   row.get(period_start_key), row.get(period_end_key),
                   str(row.get("status") or "observed"))


def numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def comparable(previous: Observation, current: Observation) -> tuple[bool, str | None]:
    if previous.unit != current.unit:
        return False, "unit_incompatible"
    if previous.metric != current.metric:
        return False, "metric_incompatible"
    if not previous.period_end or not current.period_end:
        return False, "period_missing"
    if previous.status in MISSING_STATUSES or current.status in MISSING_STATUSES:
        return False, "observation_unavailable"
    if numeric(previous.value) is None or numeric(current.value) is None:
        return False, "non_numeric"
    return True, None


def direction_for_delta(delta: float, *, improving_when: str = "decrease") -> str:
    if delta == 0:
        return "neutral"
    adverse = delta > 0 if improving_when == "decrease" else delta < 0
    return "adverse" if adverse else "improving"


def compare_periods(previous: Observation, current: Observation, *, improving_when: str = "decrease") -> dict[str, Any]:
    ok, reason = comparable(previous, current)
    result: dict[str, Any] = {
        "comparable": ok, "incompatibility_reason": reason,
        "previous": previous.__dict__.copy(), "current": current.__dict__.copy(),
        "period_start": previous.period_end, "period_end": current.period_end,
    }
    if not ok:
        result.update({"absolute_change": None, "percentage_change": None, "direction": "unknown"})
        return result
    before, after = numeric(previous.value), numeric(current.value)
    assert before is not None and after is not None
    delta = after - before
    result["absolute_change"] = delta
    result["percentage_change"] = None if before == 0 else (delta / before) * 100
    result["direction"] = direction_for_delta(delta, improving_when=improving_when)
    result["calculation"] = "current.value - previous.value; percentage omitted when baseline is zero"
    return result


def robust_z(value: float, history: Iterable[float]) -> float | None:
    values = [v for v in history if numeric(v) is not None]
    if len(values) < 5:
        return None
    median = statistics.median(values)
    mad = statistics.median([abs(v - median) for v in values])
    if mad == 0:
        return None
    return 0.6745 * (value - median) / mad


def anomaly(value: float, history: Iterable[float]) -> dict[str, Any]:
    values = list(history)
    score = robust_z(value, values)
    return {"robust_z": score, "statistically_unusual": score is not None and abs(score) >= 3.5,
            "history_count": len(values),
            "rule": "abs(0.6745 * (value - median) / MAD) >= 3.5; no score for <5 observations or MAD=0"}


def structured_signal(comparison: dict[str, Any], *, release_id: str, domain_id: str,
                      signal_type: str, improving_when: str = "decrease") -> Signal | None:
    if not comparison.get("comparable"):
        return None
    current = comparison["current"]
    previous = comparison["previous"]
    refs = [f"{previous['source_table']}:{previous['source_row_id']}",
            f"{current['source_table']}:{current['source_row_id']}"]
    return new_signal(release_id=release_id, domain_id=domain_id,
                      taxonomy_namespace=domain_id, signal_type=signal_type,
                      subject_type=current["subject_type"], subject_id=current["subject_id"],
                      direction=comparison["direction"], assertion_status="affirmed",
                      period_start=comparison.get("period_start"), period_end=comparison.get("period_end"),
                      evidence_refs=refs, derivation_method="deterministic_structured_comparison",
                      confidence_contract={"canonical_numbers": True, "comparison": comparison})


def rank_anomalies(observations: Iterable[Observation]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Observation]] = {}
    for observation in observations:
        grouped.setdefault((observation.subject_id, observation.metric), []).append(observation)
    ranked = []
    for (subject_id, metric), rows in grouped.items():
        rows.sort(key=lambda row: row.period_end or "")
        current = rows[-1]
        value = numeric(current.value)
        if value is None or current.status in MISSING_STATUSES:
            continue
        result = anomaly(value, [numeric(row.value) for row in rows[:-1] if numeric(row.value) is not None])
        ranked.append({"subject_id": subject_id, "metric": metric, "observation": current.__dict__.copy(), **result})
    return sorted(ranked, key=lambda row: abs(row["robust_z"] or 0), reverse=True)
