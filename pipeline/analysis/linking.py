"""Deterministic cross-source signal links; source records stay separate."""
from __future__ import annotations

import json
import re
import uuid
from datetime import date
from typing import Any

from pipeline.analysis.domains import AnalysisDomainSpec
from pipeline.analysis.signals import utcnow

RELATIONSHIP_TYPES = frozenset({
    "same_event", "entity_overlap", "temporal_context", "metric_context",
    "value_conflict", "narrative_structured_alignment",
})
_CAUSAL = re.compile(r"\b(?:caused|causes|led to|resulted in|because of|driven by)\b", re.I)


def _days_apart(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        return abs((date.fromisoformat(left[:10]) - date.fromisoformat(right[:10])).days)
    except ValueError:
        return None


def _signal_domain(signal: dict[str, Any]) -> str:
    return str(signal.get("domain_id") or "")


def link_signals(left: dict[str, Any], right: dict[str, Any], *,
                 left_spec: AnalysisDomainSpec, right_spec: AnalysisDomainSpec,
                 relationship_type: str, window_days: int | None = None,
                 explanation: str | None = None) -> dict[str, Any] | None:
    """Return a link only when both domain contracts permit it."""
    if relationship_type not in RELATIONSHIP_TYPES:
        raise ValueError(f"relationship type {relationship_type!r} is not allowlisted")
    if relationship_type not in left_spec.cross_source_rules or relationship_type not in right_spec.cross_source_rules:
        return None
    if left.get("subject_type") != right.get("subject_type") or left.get("subject_id") != right.get("subject_id"):
        return None
    if window_days is not None:
        distance = _days_apart(left.get("period_end"), right.get("period_end"))
        if distance is None or distance > window_days:
            return None
    if relationship_type == "value_conflict":
        if left.get("metric") != right.get("metric") or left.get("period_end") != right.get("period_end"):
            return None
        if left.get("value") == right.get("value"):
            return None
    if explanation and _CAUSAL.search(explanation):
        raise ValueError("cross-source explanations cannot use causal language")
    return {
        "link_id": f"link-{uuid.uuid4()}",
        "release_id": left.get("release_id") or right.get("release_id"),
        "left_signal_id": left.get("signal_id"), "right_signal_id": right.get("signal_id"),
        "relationship_type": relationship_type, "subject_type": left["subject_type"],
        "subject_id": left["subject_id"], "period_start": min(filter(None, (left.get("period_start"), right.get("period_start"))), default=None),
        "period_end": max(filter(None, (left.get("period_end"), right.get("period_end"))), default=None),
        "join_reason": {"canonical_subject_match": True, "window_days": window_days,
                         "left_domain": _signal_domain(left), "right_domain": _signal_domain(right)},
        "explanation": explanation,
    }


def save_link(conn, link: dict[str, Any]) -> None:
    save_links(conn, [link])


def save_links(conn, links: list[dict[str, Any]]) -> int:
    if not links:
        return 0
    conn.executemany(
        "INSERT INTO cross_source_signal_links (link_id, release_id, left_signal_id, right_signal_id, "
        "relationship_type, subject_type, subject_id, period_start, period_end, join_reason_json, "
        "explanation, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (left_signal_id, right_signal_id, relationship_type) DO NOTHING",
        [(link["link_id"], link["release_id"], link["left_signal_id"], link["right_signal_id"],
          link["relationship_type"], link["subject_type"], link["subject_id"],
          link.get("period_start"), link.get("period_end"),
          json.dumps(link["join_reason"], sort_keys=True), link.get("explanation"), utcnow())
         for link in links])
    return len(links)


def list_links(conn, *, release_id: str | None = None, subject_id: str | None = None,
               relationship_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    where, params = [], []
    if release_id:
        where.append("release_id = %s")
        params.append(release_id)
    if subject_id:
        where.append("subject_id = %s")
        params.append(subject_id)
    if relationship_type:
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError("unknown relationship type")
        where.append("relationship_type = %s")
        params.append(relationship_type)
    params.append(max(1, min(int(limit), 500)))
    sql = "SELECT * FROM cross_source_signal_links"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC LIMIT %s"
    rows = conn.execute(sql, params).fetchall()
    return [{**dict(row), "join_reason": json.loads(row["join_reason_json"])} for row in rows]
