"""Warehouse writers/read models for the isolated analysis layer."""
from __future__ import annotations

import json
import uuid
from typing import Iterable

from pipeline.analysis.domains import get_domain
from pipeline.analysis.signals import Signal, utcnow


def save_signal(conn, signal: Signal) -> None:
    """Persist one signal without touching canonical or graph-claim tables."""
    get_domain(signal.domain_id)
    conn.execute(
        "INSERT INTO automated_signals (signal_id, release_id, domain_id, taxonomy_namespace, "
        "signal_type, subject_type, subject_id, direction, assertion_status, period_start, "
        "period_end, evidence_refs_json, derivation_method, confidence_contract_json, "
        "human_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (signal_id) DO NOTHING",
        signal.db_values())


def save_signals(conn, signals: Iterable[Signal]) -> int:
    count = 0
    for signal in signals:
        save_signal(conn, signal)
        count += 1
    return count


def save_structured_signal(conn, signal: Signal, comparison: dict) -> str:
    """Persist the common signal and its exact structured calculation."""
    save_signal(conn, signal)
    previous = comparison["previous"]
    current = comparison["current"]
    # A stable child id makes cancel/resume idempotent. Re-running a cached
    # comparison must not create a second structured row for the same signal.
    structured_id = f"structured-{signal.signal_id}"
    conn.execute(
        "INSERT INTO structured_signals (structured_signal_id, signal_id, source_table, source_row_id, "
        "comparison_source_table, comparison_source_row_id, metric, unit, value_before, value_after, "
        "absolute_change, percentage_change, comparable, robust_z, anomaly_status, calculation_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (structured_signal_id) DO UPDATE SET "
        "absolute_change = excluded.absolute_change, percentage_change = excluded.percentage_change, "
        "robust_z = excluded.robust_z, anomaly_status = excluded.anomaly_status, "
        "calculation_json = excluded.calculation_json",
        (structured_id, signal.signal_id, current["source_table"], current["source_row_id"],
         previous["source_table"], previous["source_row_id"], current["metric"], current["unit"],
         str(previous["value"]), str(current["value"]), comparison.get("absolute_change"),
         comparison.get("percentage_change"), int(bool(comparison.get("comparable"))),
         comparison.get("robust_z"), "unusual" if comparison.get("statistically_unusual") else None,
         json.dumps(comparison, sort_keys=True), utcnow()))
    return structured_id


def signal_row(row) -> dict:
    item = dict(row)
    item["evidence_refs"] = json.loads(item.pop("evidence_refs_json") or "[]")
    item["confidence_contract"] = json.loads(item.pop("confidence_contract_json") or "{}")
    item["human_verified"] = bool(item["human_verified"])
    return item


def list_signals(conn, *, release_id: str | None = None, domain_id: str | None = None,
                 subject_id: str | None = None, limit: int = 100) -> list[dict]:
    where: list[str] = []
    params: list = []
    if release_id:
        where.append("release_id = ?")
        params.append(release_id)
    if domain_id:
        get_domain(domain_id)
        where.append("domain_id = ?")
        params.append(domain_id)
    if subject_id:
        where.append("subject_id = ?")
        params.append(subject_id)
    params.append(max(1, min(int(limit), 500)))
    rows = conn.execute("SELECT * FROM automated_signals" +
                       ((" WHERE " + " AND ".join(where)) if where else "") +
                       " ORDER BY created_at DESC LIMIT ?", params).fetchall()
    return [signal_row(row) for row in rows]


def promotion_ready(theme: dict, *, novelty_threshold: float = .85) -> bool:
    return (theme.get("passage_count", 0) >= 10 and theme.get("document_count", 0) >= 5 and
            theme.get("subject_count", 0) >= 3 and
            (theme.get("novelty_similarity") is not None and
             theme["novelty_similarity"] < novelty_threshold) and
            bool(theme.get("both_verifiers_passed", False)) and
            not bool(theme.get("existing_family_match", False)))


def record_theme(conn, *, release_id: str, domain_id: str, theme: dict) -> str:
    theme_id = theme.get("theme_id") or f"theme-{uuid.uuid4()}"
    status = "promotion_ready" if promotion_ready(theme) else theme.get("status", "shadow")
    conn.execute(
        "INSERT INTO emerging_themes (theme_id, release_id, domain_id, theme_key, status, "
        "passage_count, document_count, subject_count, novelty_similarity, evidence_json, "
        "promotion_reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (theme_id, release_id, domain_id, theme.get("theme_key", "unknown"), status,
         theme.get("passage_count", 0), theme.get("document_count", 0),
         theme.get("subject_count", 0), theme.get("novelty_similarity"),
         json.dumps(theme.get("passages", []), sort_keys=True),
         "recurrence and grounding bar met" if status == "promotion_ready" else None, utcnow()))
    return theme_id


def record_topic(conn, *, release_id: str, domain_id: str, topic_number: int,
                 theme: dict) -> str:
    """Persist the stable topic explorer row alongside its emerging theme."""
    topic_id = f"topic-{release_id}-{domain_id}-{topic_number}"
    conn.execute(
        "INSERT INTO analysis_topics (topic_id, release_id, domain_id, topic_number, label, "
        "novelty_similarity, outlier, representative_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT (topic_id) DO UPDATE SET label = excluded.label, "
        "novelty_similarity = excluded.novelty_similarity, outlier = excluded.outlier, "
        "representative_json = excluded.representative_json",
        (topic_id, release_id, domain_id, topic_number, theme.get("theme_key"),
         theme.get("novelty_similarity"), int(bool(theme.get("outlier"))),
         json.dumps(theme.get("passages", [])[:5], sort_keys=True), utcnow()))
    return topic_id
