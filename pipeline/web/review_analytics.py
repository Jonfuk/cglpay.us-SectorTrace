"""Review-outcome analytics (BETA-105).

Review decisions over time by source, item type, reason and evidence age —
so a recurring source or workflow problem is visible. **Never about people.**

Two rules the objective and rationale set:
  * no reviewer is named, scored or ranked — `alias_decisions.decided_by` is
    never selected, and there is no per-reviewer axis at all;
  * small groups are suppressed. Any fine-grained cell with fewer than
    `min_group` items reports a `null` count and a `suppressed` flag, so a
    single reviewer's pattern cannot be reconstructed from a thin slice.
"""
from __future__ import annotations

import sqlite3

from pipeline.web.public_queries import _public, _rows

_MIN_GROUP = 5


def _since_clause(column: str, since: str | None) -> tuple[str, tuple]:
    if since:
        return f" WHERE {column} >= ?", (since,)
    return "", ()


def _suppress(rows: list[dict], key: str, min_group: int) -> tuple[list[dict], int]:
    """Blank the count on any row below the threshold; return (rows, n_suppressed)."""
    hidden = 0
    for r in rows:
        if r[key] is not None and r[key] < min_group:
            r["suppressed"] = True
            hidden += 1
            r[key] = None
        else:
            r["suppressed"] = False
    return rows, hidden


def analytics(conn: sqlite3.Connection, *, since: str | None = None,
              min_group: int = _MIN_GROUP) -> dict:
    _public(["review_queue", "alias_decisions"])
    min_group = max(1, int(min_group))
    rq_where, rq_p = _since_clause("created_at", since)
    ad_where, ad_p = _since_clause("decided_at", since)
    suppressed_total = 0

    # --- review_queue: source x item type x status --------------------------
    raw = _rows(conn, f"""
        SELECT module AS source, item_type, status, COUNT(*) AS n
        FROM review_queue{rq_where}
        GROUP BY module, item_type, status
        ORDER BY module, item_type, status""", rq_p)
    by_source: dict[tuple, dict] = {}
    for r in raw:
        cell = by_source.setdefault((r["source"], r["item_type"]), {
            "source": r["source"], "item_type": r["item_type"],
            "pending": 0, "resolved": 0, "total": 0})
        cell["total"] += r["n"]
        if r["status"] == "pending":
            cell["pending"] += r["n"]
        else:
            cell["resolved"] += r["n"]
    source_rows = sorted(by_source.values(),
                          key=lambda c: (-c["total"], c["source"], c["item_type"]))
    source_rows, hidden = _suppress(source_rows, "total", min_group)
    suppressed_total += hidden

    # --- resolution age buckets (resolved items only) ----------------------
    age = _rows(conn, f"""
        SELECT bucket, COUNT(*) AS n FROM (
            SELECT CASE
                     WHEN julianday(resolved_at) - julianday(created_at) < 1 THEN '<1 day'
                     WHEN julianday(resolved_at) - julianday(created_at) < 7 THEN '1-7 days'
                     WHEN julianday(resolved_at) - julianday(created_at) < 30 THEN '7-30 days'
                     ELSE '30+ days'
                   END AS bucket
            FROM review_queue
            WHERE resolved_at IS NOT NULL{' AND created_at >= ?' if since else ''})
        GROUP BY bucket""", rq_p)
    age_order = {"<1 day": 0, "1-7 days": 1, "7-30 days": 2, "30+ days": 3}
    age_rows = sorted(age, key=lambda r: age_order.get(r["bucket"], 9))

    # --- month trend: created vs resolved (coarse, not suppressed) --------
    months = _rows(conn, f"""
        SELECT substr(created_at, 1, 7) AS month,
               COUNT(*) AS created,
               SUM(CASE WHEN resolved_at IS NOT NULL THEN 1 ELSE 0 END) AS resolved
        FROM review_queue{rq_where}
        GROUP BY month ORDER BY month""", rq_p)

    # --- alias decisions: scheme x status (no decided_by) ----------------
    ad = _rows(conn, f"""
        SELECT target_scheme, status, COUNT(*) AS n
        FROM alias_decisions{ad_where}
        GROUP BY target_scheme, status ORDER BY target_scheme, status""", ad_p)

    # --- reason codes from alias_decisions.reason -----------------------
    reasons = _rows(conn, f"""
        SELECT COALESCE(NULLIF(TRIM(reason), ''), '(no reason recorded)') AS reason,
               COUNT(*) AS n
        FROM alias_decisions{ad_where}
        GROUP BY reason ORDER BY n DESC LIMIT 30""", ad_p)
    reasons, hidden = _suppress(reasons, "n", min_group)
    suppressed_total += hidden

    return {
        "since": since,
        "min_group": min_group,
        "by_source": source_rows,
        "resolution_age": age_rows,
        "by_month": months,
        "alias_decisions": ad,
        "reason_codes": reasons,
        "suppressed_groups": suppressed_total,
        "note": "Aggregates only. A group smaller than the minimum is "
                "suppressed so a single reviewer's slice cannot be "
                "reconstructed. No reviewer is named, scored or ranked — this "
                "is about sources and workflow, not people.",
    }
