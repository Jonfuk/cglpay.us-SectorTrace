"""Listing candidates for a person to decide on.

The read half of `pipeline/promote.py`. Kept out of `admin.py` because that
file is about running the pipeline and this is about reading what it found,
and out of `queries.py` because these are three specific tables with three
specific shapes rather than the generic table browser.

Everything here is read-only. Deciding goes through `promote.py`, which is
where the audit trail and the fetch live.
"""
from __future__ import annotations

import sqlite3

from pipeline.promote import KINDS, PromotionError
from pipeline.web.queries import escape_like

# A page of candidates. Larger than the review queue's because a candidate is
# one line -- a title and a URL -- rather than a card of context.
PAGE = 100

# Which of a candidate's own columns are worth showing in a list, per kind.
# Everything else is in the detail payload; these are what a person scans.
SUMMARY_COLUMNS = {
    "cdp_document": ("title", "document_type_guess", "confidence"),
    "committee_paper": ("report_title", "committee_name", "meeting_date",
                         "match_quality"),
    "foi_request": ("title", "topic", "request_date", "wdtk_status"),
}


def _spec(kind: str) -> dict:
    if kind not in KINDS:
        raise PromotionError(
            f"unknown candidate kind {kind!r}; expected one of "
            f"{', '.join(sorted(KINDS))}.")
    return KINDS[kind]


def counts(conn: sqlite3.Connection) -> dict:
    """How many of each kind are waiting, decided, or already evidence.

    The number this whole phase exists to move is `undecided`.
    """
    out = {}
    for kind, spec in KINDS.items():
        table = spec["candidate_table"]
        row = conn.execute(
            f"SELECT COUNT(*) AS total, "
            f"       SUM(CASE WHEN verified = 1 THEN 1 ELSE 0 END) AS promoted, "
            f"       SUM(CASE WHEN rejected = 1 THEN 1 ELSE 0 END) AS rejected "
            f"FROM {table}").fetchone()
        total = row["total"] or 0
        promoted = row["promoted"] or 0
        rejected = row["rejected"] or 0
        out[kind] = {
            "candidate_table": table,
            "target_table": spec["target_table"],
            "total": total,
            "promoted": promoted,
            "rejected": rejected,
            "undecided": total - promoted - rejected,
            "evidence_rows": conn.execute(
                f"SELECT COUNT(*) AS count FROM {spec['target_table']}").fetchone()["count"],
        }
    return out


def authorities_with_candidates(conn: sqlite3.Connection, kind: str) -> list[dict]:
    """The authorities this kind has candidates for, for the filter.

    Names come from `authorities`; a candidate whose code is not in the spine
    is still listed, under its code, rather than dropped by an inner join.
    """
    spec = _spec(kind)
    column = spec["authority_column"]
    rows = conn.execute(
        f"SELECT c.{column} AS ons_code, a.name AS name, COUNT(*) AS candidates "
        f"FROM {spec['candidate_table']} c "
        f"LEFT JOIN authorities a ON a.ons_code = c.{column} "
        f"GROUP BY 1, 2 ORDER BY a.name IS NULL, a.name, 1")
    return [dict(row) for row in rows]


def listing(conn: sqlite3.Connection, kind: str, status: str = "undecided",
             authority: str | None = None, search: str | None = None,
             offset: int = 0, limit: int = PAGE) -> dict:
    """One page of candidates, with the filters applied server-side."""
    spec = _spec(kind)
    table = spec["candidate_table"]
    url_column = spec["candidate_url_column"]
    authority_column = spec["authority_column"]

    where = []
    params: list = []
    if status == "undecided":
        where.append("verified = 0 AND rejected = 0")
    elif status == "promoted":
        where.append("verified = 1")
    elif status == "rejected":
        where.append("rejected = 1")
    elif status != "all":
        raise PromotionError(
            f"unknown status {status!r}; expected undecided, promoted, "
            "rejected or all.")

    if authority:
        where.append(f"{authority_column} = %s")
        params.append(authority)
    if search:
        # Searched across the URL and whichever columns this kind shows, so
        # what a person types matches what they can see.
        columns = [url_column, *SUMMARY_COLUMNS[kind]]
        where.append("(" + " OR ".join(
            f"COALESCE(CAST({c} AS text), '') LIKE %s ESCAPE '\\'"
            for c in columns) + ")")
        params.extend([f"%{escape_like(search)}%"] * len(columns))

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) AS count FROM {table} {clause}", params).fetchone()["count"]

    limit = max(1, min(int(limit), PAGE))
    rows = conn.execute(
        f"SELECT * FROM {table} {clause} "
        f"ORDER BY {authority_column}, {url_column} LIMIT %s OFFSET %s",
        [*params, limit, max(0, int(offset))])

    names = {row["ons_code"]: row["name"]
              for row in conn.execute("SELECT ons_code, name FROM authorities")}
    items = []
    for row in rows:
        record = dict(row)
        code = record.get(authority_column)
        items.append({
            "url": record[url_column],
            "authority_ons_code": code,
            "authority_name": names.get(code),
            "verified": record.get("verified", 0),
            "rejected": record.get("rejected", 0),
            "summary": {c: record.get(c) for c in SUMMARY_COLUMNS[kind]},
            # The discovery provenance: where the link was found, not the
            # document. Shown as such in the UI.
            "discovered": {
                "source_url": record.get("source_url"),
                "retrieved_at": record.get("retrieved_at"),
                "discovery": (record.get("discovery_method")
                               or record.get("discovery_source")
                               or record.get("committee_system")),
            },
        })

    return {"kind": kind, "status": status, "total": total, "offset": offset,
             "limit": limit, "items": items,
             "requires": list(spec["requires"])}


def detail(conn: sqlite3.Connection, kind: str, url: str) -> dict | None:
    """One candidate in full, plus any promotion already recorded for it."""
    spec = _spec(kind)
    row = conn.execute(
        f"SELECT * FROM {spec['candidate_table']} "
        f"WHERE {spec['candidate_url_column']} = %s", (url,)).fetchone()
    if row is None:
        return None

    promotions = [dict(p) for p in conn.execute(
        "SELECT id, promoted_by, promoted_at, note, http_status, payload_sha256 "
        "FROM evidence_promotions WHERE candidate_table = %s AND candidate_url = %s "
        "ORDER BY id DESC", (spec["candidate_table"], url))]

    return {"kind": kind, "url": url, "candidate": dict(row),
             "promotions": promotions, "requires": list(spec["requires"])}
