"""Bitemporal observations, deterministic change events, and quality assertions.

Missing observations are never written as removal. ``removed`` is available
only to callers that possess positive source evidence of removal.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

_CHANGE_STATES = {"new", "unchanged", "modified", "removed", "redirected", "superseded"}
_QUALITY_TYPES = {
    "authority",
    "extraction_quality",
    "corroboration",
    "temporal_completeness",
    "review_state",
}


def _id(prefix: str, *parts) -> str:
    body = json.dumps(parts, default=str, separators=(",", ":"), ensure_ascii=False)
    return f"{prefix}-" + hashlib.sha256(body.encode()).hexdigest()


def _time(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def known_date(value) -> date | None:
    """Parse only an explicit ISO source date; ambiguous text remains NULL."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10]) if len(text) >= 10 else None
    except ValueError:
        return None


def classify_change(current, *, evidence_hash: str,
                    source_url: str | None, explicit_state: str | None = None) -> str:
    """Classify an observation without mistaking reappearance for absence.

    A current ``removed``/``historical`` row describes the last observation,
    not the underlying fact.  Seeing the source bytes again must therefore
    create a fresh live state even when their hash and URL are identical to
    the pre-removal value; calling that observation ``unchanged`` would leave
    the evidence permanently current-as-removed.
    """
    if explicit_state is not None and explicit_state not in _CHANGE_STATES - {"unchanged"}:
        raise ValueError(f"invalid explicit evidence state {explicit_state!r}")
    if current is None:
        return explicit_state or "new"
    if explicit_state:
        return explicit_state
    if current["state"] in {"removed", "historical"}:
        return "new"
    if current["evidence_hash"] != evidence_hash:
        return "modified"
    if (current["source_url"] or None) != (source_url or None):
        return "redirected"
    return "unchanged"


def observe(
    conn,
    *,
    layer: str,
    identity: str,
    evidence_hash: str,
    retrieved_at=None,
    source_url: str | None = None,
    payload_sha256: str | None = None,
    source_valid_from=None,
    source_valid_to=None,
    observed_at=None,
    effective_at=None,
    provenance: dict | None = None,
    explicit_state: str | None = None,
) -> dict:
    """Record one observation while retaining the complete prior state."""
    observed = _time(observed_at or retrieved_at)
    current = conn.execute(
        "SELECT * FROM evidence_temporal_state WHERE layer=%s AND evidence_identity=%s "
        "AND is_current ORDER BY created_at DESC LIMIT 1",
        (layer, identity),
    ).fetchone()
    change = classify_change(
        current, evidence_hash=evidence_hash, source_url=source_url,
        explicit_state=explicit_state)

    if change == "unchanged":
        state_id = current["temporal_state_id"]
    else:
        state_id = _id("ets", layer, identity, evidence_hash, source_url, observed.isoformat())
        created_at = datetime.now(timezone.utc)
        if current is not None and current["created_at"] >= created_at:
            # PostgreSQL timestamps have microsecond precision, so successive
            # observations can otherwise tie and make history order unstable.
            created_at = current["created_at"] + timedelta(microseconds=1)
        if current is not None:
            conn.execute(
                "UPDATE evidence_temporal_state SET is_current=false,"
                "state=CASE WHEN state IN ('removed','historical') THEN state ELSE 'superseded' END "
                "WHERE temporal_state_id=%s",
                (current["temporal_state_id"],),
            )
        conn.execute(
            "INSERT INTO evidence_temporal_state(temporal_state_id,layer,evidence_identity,"
            "evidence_hash,source_valid_from,source_valid_to,observed_at,effective_at,retrieved_at,"
            "state,is_current,supersedes_id,source_url,payload_sha256,provenance_json,created_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,%s,%s,%s,%s::jsonb,%s) "
            "ON CONFLICT(temporal_state_id) DO UPDATE SET "
            "is_current=true,retrieved_at=excluded.retrieved_at,source_url=excluded.source_url",
            (
                state_id,
                layer,
                identity,
                evidence_hash,
                source_valid_from,
                source_valid_to,
                observed,
                _time(effective_at) if effective_at else None,
                _time(retrieved_at) if retrieved_at else None,
                change,
                current["temporal_state_id"] if current else None,
                source_url,
                payload_sha256,
                json.dumps(provenance or {}, sort_keys=True),
                created_at,
            ),
        )
    event_id = _id(
        "ece",
        layer,
        identity,
        current["evidence_hash"] if current else None,
        evidence_hash,
        change,
        observed.isoformat(),
    )
    conn.execute(
        "INSERT INTO evidence_change_events(change_event_id,layer,evidence_identity,prior_hash,"
        "current_hash,change_state,prior_state_id,current_state_id,source_url_before,"
        "source_url_after,observed_at,provenance_json) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING",
        (
            event_id,
            layer,
            identity,
            current["evidence_hash"] if current else None,
            evidence_hash,
            change,
            current["temporal_state_id"] if current else None,
            state_id,
            current["source_url"] if current else None,
            source_url,
            observed,
            json.dumps(provenance or {}, sort_keys=True),
        ),
    )
    return {"state_id": state_id, "change_state": change}


def assert_quality(
    conn,
    *,
    layer: str,
    identity: str,
    assertion_type: str,
    value: str | None,
    status: str,
    method: str,
    rationale: str | None = None,
    asserted_by: str | None = None,
    source_url: str | None = None,
    payload_sha256: str | None = None,
    provenance: dict | None = None,
) -> str:
    if assertion_type not in _QUALITY_TYPES:
        raise ValueError(f"unknown evidence-quality assertion {assertion_type!r}")
    prior = conn.execute(
        "SELECT assertion_id FROM evidence_quality_assertions WHERE layer=%s "
        "AND evidence_identity=%s AND assertion_type=%s AND is_current",
        (layer, identity, assertion_type),
    ).fetchone()
    assertion_id = _id(
        "eqa", layer, identity, assertion_type, value, status, method, payload_sha256, rationale
    )
    if prior and prior["assertion_id"] == assertion_id:
        return assertion_id
    if prior:
        conn.execute(
            "UPDATE evidence_quality_assertions SET is_current=false WHERE assertion_id=%s",
            (prior["assertion_id"],),
        )
    conn.execute(
        "INSERT INTO evidence_quality_assertions(assertion_id,layer,evidence_identity,"
        "assertion_type,assertion_value,assertion_status,method,rationale,asserted_by,"
        "asserted_at,source_url,payload_sha256,provenance_json,supersedes_id,is_current) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,true)",
        (
            assertion_id,
            layer,
            identity,
            assertion_type,
            value,
            status,
            method,
            rationale,
            asserted_by,
            datetime.now(timezone.utc),
            source_url,
            payload_sha256,
            json.dumps(provenance or {}, sort_keys=True),
            prior["assertion_id"] if prior else None,
        ),
    )
    return assertion_id


def logical_source_identity(reference) -> str:
    key = reference.source_key or reference.source_url or reference.evidence_id
    return f"{reference.source_system}|{reference.source_table or ''}|{key}"
