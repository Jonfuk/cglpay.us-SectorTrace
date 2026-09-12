"""Human alias-resolution workflow (BETA-056).

Unmatched procurement buyer names and Companies House company names get
resolved to an authority / provider by a person, and every such decision is a
named, append-only, reversible row in `alias_decisions`. A fuzzy match is
never silently promoted to canonical identity — `decide()` requires a named
reviewer and, for an `accepted` decision, a `canonical_id` that actually
exists.

`verified_aliases` (the view from migration 0075) is the deterministic
registry: the latest accepted, non-superseded decision per name.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pipeline import catalog
from pipeline.web.queries import QueryError

SCHEMES = ("buyer", "provider")
STATUSES = ("proposed", "accepted", "rejected", "superseded")

# scheme -> (review item_type that flags an unmatched name of this kind,
#            the target table, its id column, its name column).
_SCHEME_TARGET = {
    "buyer": ("unmatched_buyer_name", "authorities", "ons_code", "name"),
    "provider": ("possible_group_company", "providers", "provider_key",
                  "canonical_name"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rows(conn, sql, params=()):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def _decisions_by_name(conn, scheme: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in _rows(conn,
                     "SELECT decision_id, unmatched_name, canonical_id, "
                     "canonical_name, status, decided_by, reason, decided_at, "
                     "supersedes_id FROM alias_decisions WHERE target_scheme = %s "
                     "ORDER BY decided_at", (scheme,)):
        out.setdefault(row["unmatched_name"], []).append(row)
    return out


def unresolved(conn, *, scheme: str, limit: int = 100) -> dict:
    """The unmatched names for a scheme, each with its decision history and
    whether it is currently resolved (an accepted, non-superseded decision)."""
    if scheme not in SCHEMES:
        raise QueryError(f"scheme must be one of {', '.join(SCHEMES)}.")
    item_type, _table, _id_col, _name_col = _SCHEME_TARGET[scheme]
    limit = max(1, min(int(limit), 1000))

    names = [r["raw_value"] for r in _rows(
        conn, "SELECT DISTINCT raw_value FROM review_queue WHERE item_type = %s "
              "AND raw_value IS NOT NULL ORDER BY raw_value LIMIT %s",
        (item_type, limit))]

    history = _decisions_by_name(conn, scheme)
    verified = {row["unmatched_name"]: row for row in _rows(
        conn, "SELECT unmatched_name, canonical_id, canonical_name, decided_by "
              "FROM verified_aliases WHERE target_scheme = %s", (scheme,))
        if catalog.object_type(conn, "verified_aliases")}

    items = []
    for name in names:
        items.append({
            "unmatched_name": name,
            "resolved": name in verified,
            "verified": verified.get(name),
            "decisions": history.get(name, []),
        })
    return {
        "scheme": scheme,
        "item_type": item_type,
        "items": items,
        "count": len(items),
        "caveat": (
            "An unmatched name is resolved only by an accepted, named "
            "decision recorded here — the fuzzy-match ranking (BETA-054) is a "
            "suggestion, and nothing applies it automatically. A correction "
            "is a new decision that supersedes the old one; the history is "
            "kept."),
    }


def verified(conn) -> dict:
    """The whole verified-alias registry."""
    if not catalog.object_type(conn, "verified_aliases"):
        return {"aliases": [], "count": 0}
    aliases = _rows(conn, "SELECT target_scheme, unmatched_name, canonical_id, "
                          "canonical_name, decided_by, decided_at "
                          "FROM verified_aliases ORDER BY target_scheme, "
                          "unmatched_name")
    return {"aliases": aliases, "count": len(aliases)}


def decide(conn, *, unmatched_name: str, target_scheme: str, status: str,
           decided_by: str, canonical_id: str | None = None,
           reason: str | None = None, review_item_id: int | None = None,
           supersedes_id: str | None = None) -> dict:
    """Append one alias decision. Named reviewer required; `accepted` needs a
    real `canonical_id`. Fuzzy matches are never applied automatically — this
    is the only path that resolves a name, and a person calls it."""
    decided_by = (decided_by or "").strip()
    if not decided_by:
        raise QueryError("decided_by is required and is never defaulted.")
    if target_scheme not in SCHEMES:
        raise QueryError(f"target_scheme must be one of {', '.join(SCHEMES)}.")
    if status not in ("proposed", "accepted", "rejected"):
        raise QueryError("status must be proposed, accepted or rejected "
                          "(a superseded row is written by a superseding decision).")
    unmatched_name = (unmatched_name or "").strip()
    if not unmatched_name:
        raise QueryError("unmatched_name is required.")

    _item_type, table, id_col, name_col = _SCHEME_TARGET[target_scheme]
    canonical_name = None
    if status == "accepted":
        if not canonical_id:
            raise QueryError("an accepted decision needs a canonical_id.")
        row = conn.execute(
            f"SELECT {name_col} AS n FROM {table} WHERE {id_col} = %s",
            (canonical_id,)).fetchone()
        if row is None:
            raise QueryError(
                f"canonical_id {canonical_id!r} is not a row in {table}.")
        canonical_name = row["n"]
    elif canonical_id:
        raise QueryError("canonical_id only makes sense with status='accepted'.")

    if supersedes_id and conn.execute(
            "SELECT 1 FROM alias_decisions WHERE decision_id = %s",
            (supersedes_id,)).fetchone() is None:
        raise QueryError(f"supersedes_id {supersedes_id!r} does not exist.")

    decision_id = uuid.uuid4().hex
    now = _now()
    conn.execute(
        "INSERT INTO alias_decisions (decision_id, unmatched_name, "
        " target_scheme, canonical_id, canonical_name, status, decided_by, "
        " reason, review_item_id, supersedes_id, decided_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (decision_id, unmatched_name, target_scheme, canonical_id,
         canonical_name, status, decided_by, reason, review_item_id,
         supersedes_id, now))
    # No row is updated or deleted. A `supersedes_id` on this new row is what
    # takes the old decision out of `verified_aliases`; the old row stays in
    # the history exactly as it was recorded.
    conn.commit()
    return {"decision_id": decision_id, "status": status,
            "canonical_id": canonical_id, "canonical_name": canonical_name,
            "decided_at": now}
