"""Fuzzy-name suggestions for a review-queue item — an operator aid, read-only.

Two review item types name something the pipeline could not resolve
deterministically:

  * `unmatched_buyer_name` — a procurement notice's buyer name that
    `m01_procurement` could not match to an `authorities` row (2,600+ of these);
  * `possible_group_company` — a Companies House company that `m04_companies`
    found under a provider's name but could not confirm belongs to that
    provider.

For both, the resolution is a person picking the right target. This ranks the
candidates by trigram similarity so the likely answer is near the top. It does
not choose one, and approving the item still writes nothing to a canonical
table (pipeline/web/review.py) — `buyer_name_overrides.py` and
`provider_identifiers` are edited by hand, deliberately (settled decision 4's
spirit: judgement is not automated).

The ranking is `similarity()` over the `pg_trgm` GIN indexes migration 0069
adds. pg_trgm is a required extension now, so this is the only path; the
`difflib` fallback that once stood in for it on SQLite is gone. `method` in the
response stays ("pg_trgm") so the score is not over-read.
"""
from __future__ import annotations

import re

# item_type -> the reference sets to rank a candidate name against, each as
# (table, id_column, name_column, extra_where_or_None). Table and column names
# are module constants, never a request value, so they are safe to interpolate
# — the same rule health.COVERAGE_COLUMNS relies on.
_TARGETS: dict[str, list[tuple[str, str, str, str | None]]] = {
    "unmatched_buyer_name": [
        ("authorities", "ons_code", "name", "active_to IS NULL"),
    ],
    "possible_group_company": [
        ("providers", "provider_key", "canonical_name", None),
        ("companies", "company_number", "company_name", None),
    ],
}

_MAX_SUGGESTIONS = 12
# A floor so a page of near-random matches is not offered as if it meant
# something. Not calibrated; 0..1.
_MIN_SCORE = 0.15


class NameMatchError(ValueError):
    """A bad item id — surfaced to the caller, not a 500."""


def _query_text(item_type: str, raw_value: str) -> str:
    """The part of `raw_value` worth matching.

    `possible_group_company` items are "<company number> <name>"; the number
    is an exact identifier, not something to fuzzy-match.
    """
    raw_value = (raw_value or "").strip()
    if item_type == "possible_group_company":
        return re.sub(r"^\S+\s+", "", raw_value).strip() or raw_value
    return raw_value


def suggestions(conn, item_id: int) -> dict:
    """Ranked candidate targets for review item `item_id`. Read-only."""
    row = conn.execute(
        "SELECT id, item_type, raw_value FROM review_queue WHERE id = ?",
        (item_id,)).fetchone()
    if row is None:
        raise NameMatchError(f"No review item {item_id}.")

    item_type = row["item_type"]
    targets = _TARGETS.get(item_type)
    if not targets:
        return {"item_id": item_id, "item_type": item_type, "query": None,
                "method": None, "matches": [],
                "note": f"{item_type!r} has no reference set to rank against."}

    query = _query_text(item_type, row["raw_value"])
    if not query:
        return {"item_id": item_id, "item_type": item_type, "query": "",
                "method": None, "matches": []}

    # pg_trgm is a required extension now, so ranking always goes through it;
    # the difflib fallback that stood in for it went with the SQLite backend.
    matches: list[dict] = []
    for table, id_col, name_col, extra in targets:
        for got in _trgm_ranked(conn, table, id_col, name_col, extra, query):
            matches.append({"target": table, "id": got[0], "name": got[1],
                            "score": round(float(got[2]), 4)})
    matches.sort(key=lambda m: m["score"], reverse=True)

    return {
        "item_id": item_id,
        "item_type": item_type,
        "query": query,
        "method": "pg_trgm",
        "matches": matches[:_MAX_SUGGESTIONS],
    }


def _trgm_ranked(conn, table, id_col, name_col, extra, query):
    # psycopg sends an untyped placeholder as `unknown`; pg_trgm's overloaded
    # function needs the search value resolved to text before it can plan.
    where = f"WHERE {name_col} IS NOT NULL AND public.similarity({name_col}, ?::text) >= ?"
    if extra:
        where += f" AND {extra}"
    # Placeholders in text order: similarity() in SELECT, similarity() and the
    # floor in WHERE, then LIMIT.
    return conn.execute(
        f"SELECT {id_col}, {name_col}, public.similarity({name_col}, ?::text) AS score "
        f"FROM {table} {where} ORDER BY score DESC LIMIT ?",
        (query, query, _MIN_SCORE, _MAX_SUGGESTIONS)).fetchall()
