"""Source/domain health metrics and safe adaptation proposals."""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class HealthSnapshot:
    source_table: str
    collected_at: str
    collection_success: bool | None = None
    freshness_at: str | None = None
    content_hash: str | None = None
    parse_success: bool | None = None
    expected_schema: dict[str, Any] | None = None
    observed_schema: dict[str, Any] | None = None
    row_count: int | None = None
    document_count: int | None = None
    embedding_coverage: float | None = None
    outlier_rate: float | None = None
    extractor_agreement: float | None = None
    verifier_pass_rate: float | None = None
    cost_micros: int | None = None
    latency_ms: int | None = None
    cache_hits: int = 0
    signal_yield: float | None = None


def _percentage_point_change(old: Any, new: Any) -> float | None:
    if old is None or new is None:
        return None
    return abs(float(new) - float(old))


def detect_drift(current: dict[str, Any], baseline: dict[str, Any] | None = None,
                 *, expected_cadence_hours: float | None = None,
                 now: datetime | None = None) -> list[dict[str, Any]]:
    """Produce proposals only; no parser, policy, taxonomy or model is changed."""
    proposals: list[dict[str, Any]] = []
    baseline = baseline or {}
    expected_schema = current.get("expected_schema") or {}
    observed_schema = current.get("observed_schema") or {}
    # Health snapshots currently carry a table-name marker as their expected
    # schema, while observed_schema is the actual column/type map. That marker
    # is not a schema contract and must not be compared to the column map.
    # Explicit column maps remain comparable for future callers.
    comparable_schema = not (set(expected_schema) == {"table"} and
                             isinstance(observed_schema, dict) and "table" not in observed_schema)
    if expected_schema and observed_schema and comparable_schema and expected_schema != observed_schema:
        proposals.append({"proposal_type": "schema_drift", "trigger": {"expected": expected_schema, "observed": observed_schema}})
    if current.get("content_hash") != baseline.get("content_hash") and not current.get("row_count"):
        proposals.append({"proposal_type": "content_changed_no_usable_records", "trigger": {"content_hash_changed": True, "row_count": current.get("row_count")}})
    if current.get("parse_success") is False:
        proposals.append({"proposal_type": "parse_failure", "trigger": {"parse_success": False}})
    parse_delta = _percentage_point_change(baseline.get("parse_success_rate"), current.get("parse_success_rate"))
    if parse_delta is not None and current.get("parse_success_rate", 1) < baseline.get("parse_success_rate", 1) and parse_delta >= .05:
        proposals.append({"proposal_type": "parse_rate_drift", "trigger": {"percentage_points": parse_delta}})
    for name in ("extractor_agreement", "verifier_pass_rate"):
        delta = _percentage_point_change(baseline.get(name), current.get(name))
        if delta is not None and current.get(name, 1) < baseline.get(name, 1) and delta >= .05:
            proposals.append({"proposal_type": f"{name}_drift", "trigger": {"percentage_points": delta}})
    if (baseline.get("outlier_rate") is not None and current.get("outlier_rate") is not None and
            abs(current["outlier_rate"] - baseline["outlier_rate"]) >= .10):
        proposals.append({"proposal_type": "outlier_rate_drift", "trigger": {"absolute_change": current["outlier_rate"] - baseline["outlier_rate"]}})
    if (baseline.get("topic_distribution_divergence") is not None and
            current.get("topic_distribution_divergence", 0) > .15):
        proposals.append({"proposal_type": "topic_distribution_drift", "trigger": {"divergence": current["topic_distribution_divergence"]}})
    if baseline.get("model_id") and current.get("model_id") and baseline["model_id"] != current["model_id"]:
        proposals.append({"proposal_type": "model_changed", "trigger": {"old": baseline["model_id"], "new": current["model_id"]}})
    if expected_cadence_hours and current.get("freshness_at"):
        try:
            age = (now or datetime.now(timezone.utc)) - datetime.fromisoformat(current["freshness_at"])
            if age.total_seconds() > expected_cadence_hours * 3600:
                proposals.append({"proposal_type": "freshness_drift", "trigger": {"age_hours": age.total_seconds() / 3600, "expected_hours": expected_cadence_hours}})
        except ValueError:
            proposals.append({"proposal_type": "freshness_unparseable", "trigger": {"freshness_at": current["freshness_at"]}})
    return proposals


def save_snapshot(conn, snapshot: HealthSnapshot, *, release_id: str | None = None,
                  domain_id: str | None = None) -> str:
    data = asdict(snapshot)
    snapshot_id = f"health-{uuid.uuid4()}"
    conn.execute(
        "INSERT INTO analysis_health_snapshots (health_snapshot_id, release_id, domain_id, source_table, "
        "collected_at, collection_success, freshness_at, content_hash, parse_success, expected_schema_json, "
        "observed_schema_json, row_count, document_count, embedding_coverage, outlier_rate, extractor_agreement, "
        "verifier_pass_rate, cost_micros, latency_ms, cache_hits, signal_yield) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (release_id, source_table) WHERE release_id IS NOT NULL DO NOTHING",
        (snapshot_id, release_id, domain_id, data["source_table"], data["collected_at"],
         None if data["collection_success"] is None else int(data["collection_success"]), data["freshness_at"],
         data["content_hash"], None if data["parse_success"] is None else int(data["parse_success"]),
         json.dumps(data["expected_schema"] or {}, sort_keys=True), json.dumps(data["observed_schema"] or {}, sort_keys=True),
         data["row_count"], data["document_count"], data["embedding_coverage"], data["outlier_rate"],
         data["extractor_agreement"], data["verifier_pass_rate"], data["cost_micros"], data["latency_ms"],
         data["cache_hits"], data["signal_yield"]))
    return snapshot_id


def save_proposal(conn, proposal: dict[str, Any], *, release_id: str | None = None,
                  domain_id: str | None = None) -> str:
    proposal_id = proposal.get("proposal_id") or f"proposal-{uuid.uuid4()}"
    conn.execute(
        "INSERT INTO adaptation_proposals (proposal_id, release_id, domain_id, proposal_type, trigger_json, "
        "status, automatic_action, created_at) VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)",
        (proposal_id, release_id, domain_id, proposal["proposal_type"], json.dumps(proposal.get("trigger", {}), sort_keys=True),
         "retry/cache/resume only" if proposal["proposal_type"] in {"transient_retry", "cache_reuse", "resume_batch"} else None, utcnow()))
    return proposal_id


def decide_proposal(conn, proposal_id: str, *, status: str, admin_reason: str | None = None) -> None:
    if status not in {"accepted", "deferred", "dismissed"}:
        raise ValueError("proposal decision must be accepted, deferred or dismissed")
    conn.execute("UPDATE adaptation_proposals SET status = %s, admin_reason = %s, decided_at = %s WHERE proposal_id = %s",
                 (status, admin_reason, utcnow(), proposal_id))
