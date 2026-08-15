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


def _universe_answers_buyer(conn: sqlite3.Connection) -> list[tuple]:
    """`unmatched_buyer_name` items whose name the universe build captured.

    The item was filed because m01 could not match the buyer to an authority.
    Phase 18's build (m23) then captured every such name systematically as a
    funder — the queue's labour, done once in a form that produces the
    universe instead of 2,667 unconnected items. The item is answered when
    the name is now a `sector_universe` row (or an awardee row it merged
    into); the evidence names the row and its basis, and says plainly that
    the name is not an authority. A name the build found to be an authority
    after all (overrides changed since m01 ran) is skipped here — that is
    m01's answer to give, on its next run.
    """
    from pipeline.modules.m23_sector_universe import normalise_name

    rows = conn.execute(
        "SELECT id, raw_value FROM review_queue "
        "WHERE item_type = 'unmatched_buyer_name' AND status = 'pending'"
    ).fetchall()
    universe = {r["normalised_name"]: r for r in conn.execute(
        "SELECT normalised_name, canonical_name, entity_type, match_basis "
        "FROM sector_universe WHERE normalised_name IS NOT NULL"
    ).fetchall()}
    out = []
    for item_id, raw in rows:
        row = universe.get(normalise_name(str(raw)))
        if row is None:
            continue
        out.append((item_id,
                     f"the name is not an authority; the universe build captured it as "
                     f"a {row['entity_type']} ({row['canonical_name']!r}, match_basis "
                     f"{row['match_basis']}) in sector_universe"))
    return out


def _universe_answers_group_company(conn: sqlite3.Connection) -> list[tuple]:
    """`possible_group_company` items whose company the universe build
    captured.

    The item asked whether a fuzzy search hit belonged to a tracked
    provider's group. m23 captures every such candidate under its company
    number with m04's 'name_only_unconfirmed' basis — recorded, never
    linked. The item is answered in the sense review_sweep answers: the
    systematic capture exists and the item's form of that labour (one review
    row per candidate, producing nothing) is done. The evidence says so, and
    says that confirmation is still a human's, on the universe row.
    """
    rows = conn.execute(
        "SELECT id, raw_value FROM review_queue "
        "WHERE item_type = 'possible_group_company' AND status = 'pending'"
    ).fetchall()
    companies = {r["company_number"]: r for r in conn.execute(
        "SELECT company_number, canonical_name, match_basis "
        "FROM sector_universe WHERE company_number IS NOT NULL"
    ).fetchall()}
    out = []
    for item_id, raw in rows:
        number = str(raw).split(" ", 1)[0].strip()
        row = companies.get(number)
        if row is None:
            continue
        out.append((item_id,
                     f"the company is captured in sector_universe under {number} "
                     f"({row['canonical_name']!r}, match_basis {row['match_basis']}); "
                     f"NOT confirmed as part of any provider's group — confirmation "
                     f"is a human decision, tracked on the universe row"))
    return out


def _universe_answers_name_match(conn: sqlite3.Connection) -> list[tuple]:
    """`unconfirmed_name_match` items whose company the universe build
    captured. The same shape as the group-company rule; the company was
    already in `companies` (m04 stored exact name matches), and m23 carries
    it into the universe with the same unconfirmed basis.
    """
    rows = conn.execute(
        "SELECT id, raw_value FROM review_queue "
        "WHERE item_type = 'unconfirmed_name_match' AND status = 'pending'"
    ).fetchall()
    companies = {r["company_number"]: r for r in conn.execute(
        "SELECT company_number, canonical_name, match_basis "
        "FROM sector_universe WHERE company_number IS NOT NULL"
    ).fetchall()}
    out = []
    for item_id, raw in rows:
        number = str(raw).split(" ", 1)[0].strip()
        row = companies.get(number)
        if row is None:
            continue
        out.append((item_id,
                     f"the company is captured in sector_universe under {number} "
                     f"({row['canonical_name']!r}, match_basis {row['match_basis']}); "
                     f"the link to the provider is still unconfirmed and stays a "
                     f"human decision"))
    return out


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
    "unmatched_buyer_captured_as_funder": {
        "module": "m23_sector_universe",
        "why": ("filed when the buyer name matched no authority; the universe "
                 "build now captures every such name systematically as a "
                 "funder (Phase 18, F1)"),
        "find": _universe_answers_buyer,
    },
    "possible_group_company_in_universe": {
        "module": "m23_sector_universe",
        "why": ("filed when a company-name search hit did not exactly match a "
                 "provider variant; the universe build captures every such "
                 "candidate under its number with m04's unconfirmed basis"),
        "find": _universe_answers_group_company,
    },
    "unconfirmed_name_match_in_universe": {
        "module": "m23_sector_universe",
        "why": ("filed when an exact company-name match still needed a human; "
                 "the universe build now carries the company with the same "
                 "unconfirmed basis"),
        "find": _universe_answers_name_match,
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
