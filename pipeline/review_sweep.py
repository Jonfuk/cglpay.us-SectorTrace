"""Closing review items the pipeline has since answered for itself.

Most of `review_queue` needs a person. A few items do not: they were filed
because the pipeline was missing something, and it has since gone and got it.
Those are not judgements waiting to be made, they are stale — and a queue whose
bulk is questions already answered is a queue people stop reading.

One rule so far, and the shape is meant to make a second obvious rather than to
be a framework:

    pfd_concerns_in_pdf_only — filed when m08 could read only the metadata stub
    and the coroner's concerns lived in a PDF nobody had fetched. m08 reads
    those PDFs now. If the report has `matters_of_concern`, the question is
    answered.

Three rules the sweep obeys, and they are the whole safety argument:

  * **It only ever touches `pending`.** A person's decision is never
    overwritten, in either direction. `record_review_item` already refuses to
    refresh a decided item; this is the same discipline from the other side.

  * **It is evidence-driven, not time-driven.** An item closes because the
    warehouse now holds the answer — checked per item, in SQL, against the
    actual row — not because a module ran or a date passed.

  * **Every closure is recorded and reversible.** `review_resolutions` keeps
    the rule and the evidence; resetting an item to pending is an ordinary
    review decision.

It fetches nothing. It is a query over what is already there, so it is safe to
run any time, and it is idempotent.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Each rule finds pending items of one type that the warehouse can now answer,
# and says in words what answered them. The SELECT must return
# (review_item_id, evidence).
RULES: dict[str, dict] = {
    "pfd_concerns_in_pdf_only": {
        "module": "m08_pfd_reports",
        "why": ("filed when the report's concerns were in a PDF this pipeline "
                 "had not read; m08 reads them now"),
        "sql": """
            SELECT r.id,
                   'the report''s matters_of_concern were read from its PDF ('
                   || LENGTH(p.matters_of_concern) || ' characters)'
              FROM review_queue r
              JOIN pfd_reports p ON p.report_ref = r.raw_value
             WHERE r.item_type = 'pfd_concerns_in_pdf_only'
               AND r.status = 'pending'
               AND p.matters_of_concern IS NOT NULL
               AND TRIM(p.matters_of_concern) != ''
        """,
    },
}


def preview(conn: sqlite3.Connection, rule: str | None = None) -> dict[str, int]:
    """How many items each rule would close, without closing any.

    A sweep that reports what it is about to do is one somebody will actually
    run against a warehouse they care about.
    """
    out = {}
    for name, spec in RULES.items():
        if rule and name != rule:
            continue
        out[name] = len(conn.execute(spec["sql"]).fetchall())
    return out


def sweep(conn: sqlite3.Connection, rule: str | None = None,
           dry_run: bool = False) -> dict:
    """Close what can be closed. Returns what was closed, per rule."""
    if rule is not None and rule not in RULES:
        raise KeyError(f"unknown rule {rule!r}; expected one of "
                        f"{', '.join(sorted(RULES))}")

    closed: dict[str, int] = {}
    resolved_at = _now()
    for name, spec in RULES.items():
        if rule and name != rule:
            continue
        rows = conn.execute(spec["sql"]).fetchall()
        closed[name] = len(rows)
        if dry_run or not rows:
            continue

        for item_id, evidence in rows:
            conn.execute(
                "INSERT INTO review_resolutions "
                "(review_item_id, rule, evidence, status_before, resolved_at) "
                "VALUES (?, ?, ?, 'pending', ?)",
                (item_id, name, evidence, resolved_at))
            # Guarded on 'pending' in the UPDATE as well as in the SELECT: the
            # two are not one statement, and a person deciding an item between
            # them must win.
            conn.execute(
                "UPDATE review_queue SET status = 'answered', resolved_at = ? "
                "WHERE id = ? AND status = 'pending'",
                (resolved_at, item_id))
        conn.commit()
        log.info("review.swept", rule=name, closed=len(rows), module=spec["module"])

    return {"closed": closed, "total": sum(closed.values()), "dry_run": dry_run,
             "resolved_at": resolved_at}


def reopen(conn: sqlite3.Connection, rule: str) -> int:
    """Undo a rule's closures, for when the rule turns out to be wrong.

    The reason `review_resolutions` records which rule fired: a bad rule is
    undone in one operation rather than by hand across hundreds of rows.
    """
    if rule not in RULES:
        raise KeyError(f"unknown rule {rule!r}")

    ids = [row[0] for row in conn.execute(
        "SELECT review_item_id FROM review_resolutions WHERE rule = ?", (rule,))]
    if not ids:
        return 0
    marks = ", ".join("?" for _ in ids)
    cursor = conn.execute(
        f"UPDATE review_queue SET status = 'pending', resolved_at = NULL "
        f"WHERE id IN ({marks}) AND status = 'answered'", ids)
    conn.execute("DELETE FROM review_resolutions WHERE rule = ?", (rule,))
    conn.commit()
    log.info("review.reopened", rule=rule, reopened=cursor.rowcount)
    return cursor.rowcount
