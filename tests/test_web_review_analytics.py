"""Review-outcome analytics (BETA-105).

Review decisions over time by source, item type, reason and evidence age.
Aggregates only; groups below the minimum are suppressed; no reviewer is
named, scored or ranked.
"""
from __future__ import annotations

import json
import sqlite3

from pipeline.web import review_analytics

_seq = [0]


def _rq(conn, module, item_type, status, created, resolved=None):
    _seq[0] += 1
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, status, "
        " created_at, resolved_at) VALUES (%s, %s, %s, %s, %s, %s)",
        (module, item_type, f"v{_seq[0]}", status, created, resolved))


def _ad(conn, scheme, status, reason, decided_by, decided_at):
    conn.execute(
        "INSERT INTO alias_decisions (decision_id, unmatched_name, "
        " target_scheme, canonical_id, canonical_name, status, decided_by, "
        " reason, decided_at) VALUES (md5(random()::text), 'x', %s, 'c', 'C', "
        " %s, %s, %s, %s)", (scheme, status, decided_by, reason, decided_at))


def test_by_source_aggregates_pending_and_resolved(conn: sqlite3.Connection) -> None:
    for _ in range(6):
        _rq(conn, "m01_procurement", "buyer_name", "pending", "2026-07-01T00:00:00Z")
    for _ in range(4):
        _rq(conn, "m01_procurement", "buyer_name", "confirmed",
            "2026-06-01T00:00:00Z", "2026-06-02T00:00:00Z")
    conn.commit()
    out = review_analytics.analytics(conn, min_group=1)
    cell = next(c for c in out["by_source"]
                if c["source"] == "m01_procurement" and c["item_type"] == "buyer_name")
    assert cell["pending"] == 6 and cell["resolved"] == 4 and cell["total"] == 10


def test_small_groups_are_suppressed(conn: sqlite3.Connection) -> None:
    for _ in range(2):
        _rq(conn, "m15_foi", "rare_type", "pending", "2026-07-01T00:00:00Z")
    for _ in range(9):
        _rq(conn, "m01_procurement", "buyer_name", "pending", "2026-07-01T00:00:00Z")
    conn.commit()
    out = review_analytics.analytics(conn, min_group=5)
    rare = next(c for c in out["by_source"] if c["item_type"] == "rare_type")
    assert rare["suppressed"] is True and rare["total"] is None
    big = next(c for c in out["by_source"] if c["item_type"] == "buyer_name")
    assert big["suppressed"] is False and big["total"] == 9
    assert out["suppressed_groups"] >= 1


def test_no_reviewer_identity_reaches_the_payload(conn: sqlite3.Connection) -> None:
    for i in range(7):
        _ad(conn, "buyer", "accepted", "clear match", "alice.reviewer",
            f"2026-07-0{i + 1}T00:00:00Z")
    conn.commit()
    out = review_analytics.analytics(conn, min_group=1)
    blob = json.dumps(out)
    assert "alice" not in blob            # the reviewer's name never appears
    assert '"decided_by"' not in blob     # nor as a key/axis
    reason = next(r for r in out["reason_codes"] if r["reason"] == "clear match")
    assert reason["n"] == 7


def test_resolution_age_is_bucketed(conn: sqlite3.Connection) -> None:
    _rq(conn, "m", "t", "confirmed", "2026-06-01T00:00:00Z", "2026-06-01T06:00:00Z")
    _rq(conn, "m", "t", "confirmed", "2026-06-01T00:00:00Z", "2026-06-04T00:00:00Z")
    _rq(conn, "m", "t", "confirmed", "2026-06-01T00:00:00Z", "2026-08-01T00:00:00Z")
    conn.commit()
    out = review_analytics.analytics(conn, min_group=1)
    buckets = {r["bucket"]: r["n"] for r in out["resolution_age"]}
    assert buckets.get("<1 day") == 1
    assert buckets.get("1-7 days") == 1
    assert buckets.get("30+ days") == 1


def test_the_note_states_the_privacy_contract(conn: sqlite3.Connection) -> None:
    out = review_analytics.analytics(conn)
    n = out["note"].lower()
    assert "aggregates only" in n
    assert "no reviewer is named" in n
    assert "not people" in n


def test_the_route_is_registered() -> None:
    from pipeline.web import server
    src = server.__file__
    assert '/api/admin/review-analytics' in open(src, encoding="utf-8").read()
