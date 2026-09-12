"""Versioned deterministic narrative prefilter and recall gate."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable

from pipeline.analysis.operations import utcnow

RULES_VERSION = "lexical-v1"
TERMS = frozenset({
    "shortage", "vacancy", "vacancies", "workload", "pressure", "retention",
    "recruitment", "recruit", "pay", "salary", "staffing", "workforce",
    "capacity", "demand", "waiting", "backlog", "commission", "service",
})
THRESHOLDS = {"minimum_term_hits": 1, "overall_recall": 0.99, "critical_recall": 1.0}


def rules_sha256() -> str:
    value = {"version": RULES_VERSION, "terms": sorted(TERMS),
             "minimum_term_hits": THRESHOLDS["minimum_term_hits"]}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _result_payload(*, corpus_version: str, corpus_sha256: str, positives: int,
                    accepted_positives: int, critical_positives: int,
                    accepted_critical: int,
                    critical_categories: dict[str, dict[str, int | float]],
                    overall_recall: float, critical_recall: float,
                    gate_passed: bool) -> dict[str, Any]:
    return {
        "corpus_version": corpus_version, "corpus_sha256": corpus_sha256,
        "rules_version": RULES_VERSION, "rules_sha256": rules_sha256(),
        "thresholds": THRESHOLDS, "positives": positives,
        "accepted_positives": accepted_positives, "overall_recall": overall_recall,
        "critical_positives": critical_positives, "accepted_critical": accepted_critical,
        "critical_categories": critical_categories,
        "critical_recall": critical_recall, "gate_passed": gate_passed,
    }


def matches(text: str) -> bool:
    words = set(re.findall(r"[a-z][a-z-]{2,}", (text or "").casefold()))
    return len(words & TERMS) >= THRESHOLDS["minimum_term_hits"]


@dataclass(frozen=True)
class GateResult:
    corpus_version: str
    corpus_sha256: str
    positives: int
    accepted_positives: int
    critical_positives: int
    accepted_critical: int
    critical_categories: dict[str, dict[str, int | float]]
    overall_recall: float
    critical_recall: float
    gate_passed: bool
    result_sha256: str


def evaluate(corpus: Iterable[dict[str, Any]], *, corpus_version: str) -> GateResult:
    """Evaluate labels without treating an empty/no-critical corpus as passing."""
    if not corpus_version.strip():
        raise ValueError("an adjudicated corpus needs a non-empty version")
    rows = [dict(row) for row in corpus]
    identifiers = []
    for number, row in enumerate(rows, start=1):
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError(f"corpus row {number} needs a stable id")
        if not isinstance(row.get("text"), str):
            raise ValueError(f"corpus row {number} needs text")
        if not isinstance(row.get("positive"), bool) or not isinstance(row.get("critical"), bool):
            raise ValueError(f"corpus row {number} needs boolean positive and critical labels")
        if row["critical"] and not row["positive"]:
            raise ValueError(f"corpus row {number} cannot be critical without being positive")
        if row["critical"] and (not isinstance(row.get("category"), str) or
                                not row["category"].strip()):
            raise ValueError(f"critical corpus row {number} needs a category")
        identifiers.append(row["id"])
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("corpus row ids must be unique")
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    corpus_digest = hashlib.sha256(canonical.encode()).hexdigest()
    positives = [row for row in rows if bool(row.get("positive"))]
    critical = [row for row in positives if bool(row.get("critical"))]
    accepted = sum(matches(str(row.get("text") or "")) for row in positives)
    critical_accepted = sum(matches(str(row.get("text") or "")) for row in critical)
    critical_categories = {}
    for category in sorted({str(row["category"]) for row in critical}):
        category_rows = [row for row in critical if row["category"] == category]
        category_accepted = sum(matches(row["text"]) for row in category_rows)
        critical_categories[category] = {
            "positives": len(category_rows), "accepted": category_accepted,
            "recall": category_accepted / len(category_rows),
        }
    overall = accepted / len(positives) if positives else 0.0
    critical_recall = critical_accepted / len(critical) if critical else 0.0
    passed = bool(positives and critical and overall >= THRESHOLDS["overall_recall"] and
                  critical_recall >= THRESHOLDS["critical_recall"] and
                  all(item["recall"] == 1.0 for item in critical_categories.values()))
    result_payload = _result_payload(
        corpus_version=corpus_version, corpus_sha256=corpus_digest,
        positives=len(positives), accepted_positives=accepted,
        critical_positives=len(critical), accepted_critical=critical_accepted,
        critical_categories=critical_categories, overall_recall=overall,
        critical_recall=critical_recall, gate_passed=passed)
    result_digest = hashlib.sha256(json.dumps(
        result_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return GateResult(corpus_version, corpus_digest, len(positives), accepted,
                      len(critical), critical_accepted, critical_categories,
                      overall, critical_recall, passed, result_digest)


def save_result(conn, result: GateResult, *, adjudicated_by: str) -> str:
    if not adjudicated_by.strip():
        raise ValueError("an adjudicated corpus must name its reviewer")
    if result.positives <= 0 or result.critical_positives <= 0:
        raise ValueError("an adjudicated corpus needs positive and critical examples")
    existing = conn.execute(
        "SELECT result_id, corpus_sha256, result_sha256 FROM analysis_prefilter_results "
        "WHERE corpus_version = %s", (result.corpus_version,)).fetchone()
    if existing:
        if (existing["corpus_sha256"] != result.corpus_sha256 or
                existing["result_sha256"] != result.result_sha256):
            raise ValueError("corpus version already belongs to different immutable bytes or results")
        return existing["result_id"]
    result_id = f"prefilter-{result.result_sha256}"
    conn.execute(
        "INSERT INTO analysis_prefilter_results (result_id, corpus_version, corpus_sha256, "
        "rules_version, rules_sha256, thresholds_json, result_sha256, positives, "
        "accepted_positives, critical_positives, accepted_critical, critical_categories_json, "
        "overall_recall, critical_recall, gate_passed, adjudicated_by, evaluated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (result_id, result.corpus_version, result.corpus_sha256, RULES_VERSION,
         rules_sha256(), json.dumps(THRESHOLDS, sort_keys=True), result.result_sha256,
         result.positives, result.accepted_positives, result.critical_positives,
         result.accepted_critical, json.dumps(result.critical_categories, sort_keys=True),
         result.overall_recall,
         result.critical_recall, int(result.gate_passed), adjudicated_by, utcnow()))
    return result_id


def qualifying_gate(conn, *, explicitly_enabled: bool = False) -> dict[str, Any] | None:
    """Return the exact qualifying gate only after every persisted check passes."""
    if not explicitly_enabled:
        return None
    row = conn.execute(
        "SELECT corpus_version, corpus_sha256, result_sha256, gate_passed, positives, "
        "accepted_positives, critical_positives, accepted_critical, critical_categories_json, "
        "overall_recall, critical_recall, thresholds_json "
        "FROM analysis_prefilter_results "
        "WHERE rules_version = %s AND rules_sha256 = %s ORDER BY evaluated_at DESC LIMIT 1",
        (RULES_VERSION, rules_sha256())).fetchone()
    if not row or not row["gate_passed"]:
        return None
    try:
        same_thresholds = json.loads(row["thresholds_json"]) == THRESHOLDS
    except (TypeError, ValueError):
        return None
    try:
        categories = json.loads(row["critical_categories_json"])
        categories_pass = bool(categories) and all(
            int(item["positives"]) > 0 and int(item["accepted"]) == int(item["positives"]) and
            float(item["recall"]) == 1.0 for item in categories.values())
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    persisted_payload = _result_payload(
        corpus_version=row["corpus_version"], corpus_sha256=row["corpus_sha256"],
        positives=int(row["positives"]), accepted_positives=int(row["accepted_positives"]),
        critical_positives=int(row["critical_positives"]),
        accepted_critical=int(row["accepted_critical"]), critical_categories=categories,
        overall_recall=float(row["overall_recall"]),
        critical_recall=float(row["critical_recall"]), gate_passed=bool(row["gate_passed"]))
    persisted_digest = hashlib.sha256(json.dumps(
        persisted_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    allowed = bool(
        row["corpus_version"] and row["corpus_sha256"] and row["result_sha256"] and
        persisted_digest == row["result_sha256"] and int(row["positives"]) > 0 and
        int(row["accepted_positives"]) / int(row["positives"]) >=
        THRESHOLDS["overall_recall"] and int(row["critical_positives"]) > 0 and
        int(row["accepted_critical"]) == int(row["critical_positives"]) and
        categories_pass and same_thresholds and
        float(row["overall_recall"]) >= THRESHOLDS["overall_recall"] and
        float(row["critical_recall"]) >= THRESHOLDS["critical_recall"])
    return dict(row) if allowed else None


def suppression_allowed(conn, *, explicitly_enabled: bool = False) -> bool:
    """Suppression needs both owner opt-in and a gate for these exact rules."""
    return qualifying_gate(conn, explicitly_enabled=explicitly_enabled) is not None
