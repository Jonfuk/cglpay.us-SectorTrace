"""Closing review items the pipeline has since answered for itself.

Most of `review_queue` needs a person. A few items do not: they were filed
because the pipeline was missing something, and it has since gone and got it.
Those are not judgements waiting to be made, they are stale — and a queue whose
bulk is questions already answered is a queue people stop reading.

Two rules, and between them they show the shape:

    pfd_concerns_in_pdf_only — filed when m08 could read only the metadata stub
    and the coroner's concerns lived in a PDF nobody had fetched. m08 reads
    those PDFs now. If the report has `matters_of_concern`, the question is
    answered.

    committee_url_unknown — filed when nothing knew where a council publishes.
    If the authority is now in `pipeline/authority_websites.py` with a
    committee URL, it is known. This one is a Python predicate rather than a
    SELECT, because the answer lives in code rather than in a table — which is
    the point of it being there.

Three rules the sweep obeys, and they are the whole safety argument:

  * **It only ever touches `pending`.** A person's decision is never
    overwritten, in either direction. `record_review_item` already refuses to
    refresh a decided item; this is the same discipline from the other side.

  * **It is evidence-driven, not time-driven.** An item closes because the
    answer actually exists — checked per item against the row or the registry
    entry that holds it — not because a module ran or a date passed.

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


def _registry_answers_committee_url(conn: sqlite3.Connection) -> list[tuple]:
    """`committee_url_unknown` items whose authority is now in the registry.

    The one rule that cannot be a SELECT: the answer lives in
    `pipeline/authority_websites.py`, which is code rather than a table —
    deliberately, because a committed entry survives the warehouse and is
    reviewable in a diff.
    """
    from pipeline.authority_websites import AUTHORITY_WEBSITES

    rows = conn.execute(
        "SELECT id, raw_value FROM review_queue "
        "WHERE item_type = 'committee_url_unknown' AND status = 'pending'"
    ).fetchall()
    out = []
    for item_id, ons_code in rows:
        entry = AUTHORITY_WEBSITES.get(ons_code)
        if entry is not None and entry.committee_url:
            out.append((item_id,
                         f"the committee URL is in the registry: "
                         f"{entry.committee_url} (verified {entry.verified_on})"))
    return out


def _website_answers_authority_website(conn: sqlite3.Connection) -> list[tuple]:
    """`authority_website_unknown` items whose authority has a base URL now.

    The item is filed by m09 when `website_for()` returns nothing. It is
    answered by exactly the same call returning an entry with a base_url —
    from a reviewer's override, the tracked verified file, the hand-verified
    registry, or m15's mySociety profiles. Mirroring the module's own
    condition (rather than naming one source) keeps the two from disagreeing
    about what "known" means: if m09 would not raise the item today, the
    item is stale.
    """
    from pipeline.authority_websites import website_for

    rows = conn.execute(
        "SELECT id, raw_value FROM review_queue "
        "WHERE item_type = 'authority_website_unknown' AND status = 'pending'"
    ).fetchall()
    out = []
    for item_id, ons_code in rows:
        entry = website_for(str(ons_code), conn)
        if entry is not None and entry.base_url:
            out.append((item_id,
                         f"the authority has a base URL now: {entry.base_url} "
                         f"({entry.source}); m09 would not raise this item today"))
    return out


# Each rule finds pending items of one type that the warehouse can now answer,
# and says in words what answered them. A rule is either a `sql` returning
# (review_item_id, evidence), or a `find(conn)` doing the same in Python for
# the cases where the answer is not in the database at all.
RULES: dict[str, dict] = {
    "committee_url_in_registry": {
        "module": "m10_committee_papers",
        "why": ("filed when nothing knew where this council publishes; the "
                 "committee URL has since been verified and committed to "
                 "pipeline/authority_websites.py"),
        "find": _registry_answers_committee_url,
    },
    "authority_website_available": {
        "module": "m09_cdp_documents",
        "why": ("filed when website_for() returned no base URL for this "
                 "authority; it has one now — a reviewer's override, the "
                 "tracked verified file, the hand-verified registry, or m15's "
                 "mySociety profiles — and m09 would not raise the item today"),
        "find": _website_answers_authority_website,
    },
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


def _matches(conn: sqlite3.Connection, spec: dict) -> list[tuple]:
    """The items one rule would close, however that rule is expressed."""
    if "find" in spec:
        return list(spec["find"](conn))
    return [tuple(row) for row in conn.execute(spec["sql"]).fetchall()]


def preview(conn: sqlite3.Connection, rule: str | None = None) -> dict[str, int]:
    """How many items each rule would close, without closing any.

    A sweep that reports what it is about to do is one somebody will actually
    run against a warehouse they care about.
    """
    out = {}
    for name, spec in RULES.items():
        if rule and name != rule:
            continue
        out[name] = len(_matches(conn, spec))
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
        rows = _matches(conn, spec)
        if dry_run or not rows:
            closed[name] = len(rows)
            continue

        applied = 0
        try:
            for item_id, evidence in rows:
                # Change state first and record a resolution only when the
                # conditional update actually won. A concurrent human decision
                # must not acquire a false automated audit row.
                cursor = conn.execute(
                    "UPDATE review_queue SET status = 'answered', resolved_at = ? "
                    "WHERE id = ? AND status = 'pending'",
                    (resolved_at, item_id))
                if cursor.rowcount != 1:
                    continue
                conn.execute(
                    "INSERT INTO review_resolutions "
                    "(review_item_id, rule, evidence, status_before, resolved_at) "
                    "VALUES (?, ?, ?, 'pending', ?)",
                    (item_id, name, evidence, resolved_at))
                applied += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        closed[name] = applied
        log.info("review.swept", rule=name, closed=applied, module=spec["module"])

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
