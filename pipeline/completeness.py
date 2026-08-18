"""Read-only completeness scorecards for the dataset campaign."""
from __future__ import annotations

from datetime import datetime, timezone

from pipeline import catalog, db
from pipeline.web import health

SOURCE_TABLES = tuple(dict.fromkeys(
    table for _label, table, _column, _module in health.COVERAGE_COLUMNS
)) + (
    "providers", "provider_identifiers", "nhs_job_adverts",
    "gender_pay_gap_reports", "ons_ashe_observations", "provider_pay_pages",
    "council_spend", "skills_for_care_estimates",
)


def _count_tables(conn) -> dict[str, int]:
    names = [name for name in SOURCE_TABLES if catalog.object_type(conn, name)]
    return catalog.row_counts(conn, names)


def _review_state(conn) -> dict[str, dict[str, int]]:
    if not catalog.object_type(conn, "review_queue"):
        return {}
    rows = conn.execute(
        "SELECT item_type, status, COUNT(*) AS n FROM review_queue "
        "GROUP BY item_type, status ORDER BY item_type, status").fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        out.setdefault(row["item_type"], {})[row["status"]] = row["n"]
    return out


def _pending_modules(conn) -> set[str]:
    if not catalog.object_type(conn, "review_queue"):
        return set()
    return {row[0] for row in conn.execute(
        "SELECT DISTINCT module FROM review_queue WHERE status = 'pending' "
        "AND module IS NOT NULL")}


def _freshness(conn) -> dict[str, dict[str, str | None]]:
    out = {}
    for table in _count_tables(conn):
        columns = {column["name"] for column in catalog.columns_of(conn, table)}
        if "retrieved_at" not in columns:
            continue
        row = conn.execute(
            f"SELECT MIN(retrieved_at) AS oldest, MAX(retrieved_at) AS newest "
            f"FROM {catalog.quote(table)}").fetchone()
        out[table] = {"oldest": row["oldest"], "newest": row["newest"]}
    return out


def _provenance(conn) -> dict[str, int]:
    out = {}
    for table in _count_tables(conn):
        columns = {column["name"] for column in catalog.columns_of(conn, table)}
        if not {"source_url", "retrieved_at"}.issubset(columns):
            # Entity/reference tables are intentionally not evidence rows.
            continue
        try:
            out[table] = len(db.rows_missing_provenance(conn, table))
        except (KeyError, ValueError):
            # A backend-specific catalog race should not make a read-only
            # scorecard fail; omit that table and let the next run retry it.
            continue
    return out


def baseline(conn, *, tier: str = "upper") -> dict:
    """Return a serialisable, read-only campaign baseline."""
    coverage = health.coverage(conn, tier=tier)
    pending_modules = _pending_modules(conn)
    candidate_for = {
        "CDP docs": "CDP cands", "Papers": "Paper cands", "FOI": "FOI cands",
    }
    cells = []
    for authority in coverage["authorities"]:
        for column in coverage["columns"]:
            label = column["label"]
            count = authority["cells"].get(label, 0)
            status = "present" if count else "unexplained"
            if not count and label in candidate_for:
                if authority["cells"].get(candidate_for[label], 0):
                    status = "candidate"
            if not count and status == "unexplained":
                module = column["module"]
                if module in pending_modules:
                    status = "pending_review"
            cells.append({"ons_code": authority["ons_code"],
                          "evidence": label, "module": column["module"],
                          "status": status})
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "backend": db.backend_of(conn),
        "coverage": coverage,
        "coverage_cells": cells,
        "table_counts": _count_tables(conn),
        "review_state": _review_state(conn),
        "freshness": _freshness(conn),
        "missing_provenance": _provenance(conn),
        "unexplained_policy": (
            "Each expected cell must be present or carry a dated reason: "
            "candidate, pending_review, blocked, unsupported, not_published, "
            "out_of_scope, or parse_failure."
        ),
    }
