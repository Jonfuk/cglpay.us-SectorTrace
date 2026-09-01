"""Deterministic structured-data comparisons and robust anomaly ranking."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from pipeline.analysis.signals import Signal, new_signal

MISSING_STATUSES = frozenset({"missing", "suppressed", "schema_incompatible", "unavailable"})

# These adapters intentionally name fields from the canonical module schemas.
# They are part of the provenance contract: a new source schema must be added
# explicitly rather than inferred from arbitrary columns.
_TABLE_ADAPTERS: dict[str, dict[str, Any]] = {
    "contracts": {"subject_id": "supplier_id", "subject_type": "provider_id",
                  "period": "date_start", "metrics": ("value_core", "value_max"), "unit": "currency"},
    "council_spend": {"subject_id": "provider_key", "subject_type": "provider_id",
                      "period": "period", "metrics": ("amount",), "unit": "GBP"},
    "charity_financials": {"subject_id": "charity_number", "subject_type": "provider_id",
                            "period": "financial_year_end",
                            "metrics": ("total_income", "total_expenditure", "income_from_govt_contracts",
                                        "income_from_govt_grants", "inc_charitable_activities",
                                        "exp_charitable_activities"), "unit": "GBP"},
    "charity_accounts_extracts": {"subject_id": "charity_number", "subject_type": "provider_id",
                                   "period": "financial_year_end",
                                   "metrics": ("staff_costs_total", "wages_and_salaries",
                                                "agency_and_third_party", "key_management_remuneration"),
                                   "unit": "GBP"},
    "workforce_census_metrics": {"subject_id": "workforce_segment", "subject_type": "workforce_segment",
                                  "period": "census_year", "metrics": ("value",), "unit": "unit"},
    "nhs_job_adverts": {"subject_id": "provider_key", "subject_type": "provider_id",
                        "period": "posted_date", "metrics": ("salary_min", "salary_max"), "unit": "salary_period"},
    "provider_pay_mentions": {"subject_id": "provider_key", "subject_type": "provider_id",
                               "period": "retrieved_at", "metrics": ("salary_min", "salary_max"), "unit": "salary_period"},
    "ndtms_la_statistics": {"subject_id": "ons_code", "subject_type": "authority_id",
                             "period": "financial_year", "metrics": ("value",), "unit": "published"},
    "ndtms_monthly_statistics": {"subject_id": "ons_code", "subject_type": "authority_id",
                                  "period": "report_month", "metrics": ("value",), "unit": "published"},
    "fingertips_la_values": {"subject_id": "ons_code", "subject_type": "authority_id",
                             "period": "time_period_sortable", "metrics": ("value",), "unit": "published"},
    "la_revenue_budgets": {"subject_id": "ons_code", "subject_type": "authority_id",
                           "period": "financial_year", "metrics": ("amount",), "unit": "GBP"},
    "rough_sleeping_snapshot": {"subject_id": "ons_code", "subject_type": "authority_id",
                                 "period": "snapshot_year", "metrics": ("count", "rate_per_100k"), "unit": "published"},
    "statutory_homelessness_snapshot": {"subject_id": "ons_code", "subject_type": "authority_id",
                                         "period": "quarter_start", "metrics": ("total_initial_assessments",
                                                                                    "total_owed_duty"), "unit": "count"},
    "temporary_accommodation_snapshot": {"subject_id": "ons_code", "subject_type": "authority_id",
                                          "period": "quarter_start", "metrics": ("total_households_ta",
                                                                                     "children_in_ta"), "unit": "count"},
}


def _columns(conn, table: str) -> set[str]:
    try:
        return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        # PostgreSQL deliberately has no PRAGMA. On a write connection the
        # failed probe aborts the transaction, so clear it before using cursor
        # descriptions as the portable schema probe.
        conn.rollback()
        cursor = conn.execute(f"SELECT * FROM {table} LIMIT 0")
        return {str(item[0]) for item in (getattr(cursor, "description", None) or [])}


def _row_id(row: Any, columns: set[str], table: str, index: int) -> str:
    for key in ("id", "notice_id", "job_reference", "report_ref", "publication_slug",
                "document_url", "financial_year_end", "source_row_id"):
        if key in columns and row[key] not in (None, ""):
            return str(row[key])
    return f"{table}:{index}"


def observations_from_table(conn, table: str) -> list[Observation]:
    """Read only explicitly mapped numeric fields from one canonical table."""
    mapping = _TABLE_ADAPTERS.get(table)
    if mapping is None:
        return []
    try:
        columns = _columns(conn, table)
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
    except Exception:
        return []
    required = {mapping["subject_id"], mapping["period"]}
    if not required <= columns:
        return []
    result: list[Observation] = []
    for index, raw in enumerate(rows):
        row = dict(raw)
        subject_id = row.get(mapping["subject_id"])
        subject_type = mapping["subject_type"]
        if table == "contracts" and subject_id in (None, ""):
            subject_id, subject_type = row.get("buyer_ons_code"), "authority_id"
        if table == "council_spend" and subject_id in (None, ""):
            subject_id, subject_type = row.get("authority_ons_code"), "authority_id"
        if subject_id in (None, ""):
            continue
        period = row.get(mapping["period"])
        if table == "contracts" and period in (None, ""):
            period = row.get("date_published")
        for metric in mapping["metrics"]:
            if metric not in columns or numeric(row.get(metric)) is None:
                continue
            unit = row.get(mapping["unit"], mapping["unit"]) if mapping["unit"] in columns else mapping["unit"]
            if unit in (None, ""):
                unit = mapping["unit"]
            if table == "contracts" and metric == "value_core":
                unit = row.get("currency") or "currency"
            if table == "la_revenue_budgets" and row.get("amounts_multiplier"):
                unit = f"GBP*{row['amounts_multiplier']}"
            result.append(Observation(
                source_table=table, source_row_id=_row_id(row, columns, table, index),
                subject_type=subject_type, subject_id=str(subject_id), metric=metric,
                value=row.get(metric), unit=str(unit), period_start=None, period_end=str(period)))
    return result


def observations_for_domain(conn, source_tables: Iterable[str]) -> list[Observation]:
    observations: list[Observation] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for table in source_tables:
        if table == "hse_enforcement_notices":
            try:
                rows = conn.execute(
                    "SELECT provider_key, SUBSTR(issue_date, 1, 4) AS period_end, COUNT(*) AS value "
                    "FROM hse_enforcement_notices WHERE provider_key IS NOT NULL AND issue_date IS NOT NULL "
                    "GROUP BY provider_key, SUBSTR(issue_date, 1, 4)").fetchall()
            except Exception:
                rows = []
            for row in rows:
                observations.append(Observation(
                    source_table=table, source_row_id=f"{table}:{row['provider_key']}:{row['period_end']}",
                    subject_type="provider_id", subject_id=str(row["provider_key"]),
                    metric="enforcement_notice_count", value=row["value"], unit="count",
                    period_start=None, period_end=str(row["period_end"])))
            continue
        for observation in observations_from_table(conn, table):
            key = (observation.source_table, observation.source_row_id, observation.subject_id,
                   observation.metric, str(observation.period_end))
            if key not in seen:
                observations.append(observation)
                seen.add(key)
    return observations


def comparisons_for_domain(observations: Iterable[Observation], *, improving_when: str = "decrease") -> list[dict[str, Any]]:
    """Create consecutive, same-unit comparisons and anomaly metadata."""
    grouped: dict[tuple[str, str, str, str], list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.subject_type, observation.subject_id, observation.metric,
                 observation.unit)].append(observation)
    results: list[dict[str, Any]] = []
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.period_end or ""))
        for index in range(1, len(rows)):
            previous, current = rows[index - 1], rows[index]
            comparison = compare_periods(previous, current, improving_when=improving_when)
            current_value = numeric(current.value)
            if current_value is not None:
                comparison.update(anomaly(current_value, [numeric(row.value) for row in rows[:index]
                                                          if numeric(row.value) is not None]))
            results.append(comparison)
    return results


def categorical_transitions(rows: Iterable[dict[str, Any]], *, subject_key: str,
                            metric: str, period_key: str, source_table: str,
                            source_id_key: str, direction: dict[str, str] | None = None,
                            subject_type: str = "canonical_subject") -> list[dict[str, Any]]:
    """Return auditable categorical state changes without numeric coercion."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(subject_key) in (None, "") or row.get(metric) in (None, ""):
            continue
        grouped[str(row[subject_key])].append(dict(row))
    result = []
    for subject_id, values in grouped.items():
        values.sort(key=lambda row: str(row.get(period_key) or ""))
        for previous, current in zip(values, values[1:]):
            before, after = str(previous[metric]), str(current[metric])
            if before == after:
                continue
            result.append({
                "comparable": True, "incompatibility_reason": None,
                "previous": {"source_table": source_table, "source_row_id": str(previous[source_id_key]),
                              "subject_type": subject_type, "subject_id": subject_id,
                              "metric": metric, "value": before, "unit": "category",
                              "period_end": previous.get(period_key)},
                "current": {"source_table": source_table, "source_row_id": str(current[source_id_key]),
                             "subject_type": subject_type, "subject_id": subject_id,
                             "metric": metric, "value": after, "unit": "category",
                             "period_end": current.get(period_key)},
                "period_start": previous.get(period_key), "period_end": current.get(period_key),
                "absolute_change": None, "percentage_change": None,
                "direction": (direction or {}).get(f"{before}->{after}", "unknown"),
                "calculation": "categorical state transition; no arithmetic performed",
            })
    return result


def categorical_signal(comparison: dict[str, Any], *, release_id: str, domain_id: str,
                       signal_type: str) -> Signal:
    """Create an automated signal for an explicitly observed category change."""
    current = comparison["current"]
    refs = [f"{comparison['previous']['source_table']}:{comparison['previous']['source_row_id']}",
            f"{current['source_table']}:{current['source_row_id']}"]
    return new_signal(release_id=release_id, domain_id=domain_id,
                      taxonomy_namespace=domain_id, signal_type=signal_type,
                      subject_type=current["subject_type"], subject_id=current["subject_id"],
                      direction=comparison["direction"], assertion_status="affirmed",
                      period_start=comparison.get("period_start"), period_end=comparison.get("period_end"),
                      evidence_refs=refs, derivation_method="deterministic_categorical_transition",
                      confidence_contract={"canonical_values": True, "comparison": comparison})


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
