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

On PostgreSQL with `pg_trgm` the ranking is `similarity()` over the GIN
indexes migration 0069 adds. Without it — SQLite, or a PostgreSQL server with
no pg_trgm — the same shape is computed with `difflib` over a capped candidate
pull: slower, a different metric, but the same ordering at the sizes here
(347 authorities, ~2k providers/companies). `method` in the response says
which ran so the score is not over-read.
"""
from __future__ import annotations

import difflib
import re

from pipeline import db

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
# something. Applies to both metrics; neither is calibrated, both are 0..1.
_MIN_SCORE = 0.15
# Rows pulled for the Python fallback before ranking — a ceiling comfortably
# above every reference set the targets name, not a filter.
_FALLBACK_CANDIDATE_CAP = 5000


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

    use_trgm = (db.backend_of(conn) == "postgres"
                and db.has_extension(conn, "pg_trgm"))
    rank = _trgm_ranked if use_trgm else _difflib_ranked

    matches: list[dict] = []
    for table, id_col, name_col, extra in targets:
        for got in rank(conn, table, id_col, name_col, extra, query):
            matches.append({"target": table, "id": got[0], "name": got[1],
                            "score": round(float(got[2]), 4)})
    matches.sort(key=lambda m: m["score"], reverse=True)

    return {
        "item_id": item_id,
        "item_type": item_type,
        "query": query,
        "method": "pg_trgm" if use_trgm else "difflib",
        "matches": matches[:_MAX_SUGGESTIONS],
    }


def _trgm_ranked(conn, table, id_col, name_col, extra, query):
    where = f"WHERE {name_col} IS NOT NULL AND similarity({name_col}, ?) >= ?"
    if extra:
        where += f" AND {extra}"
    # Placeholders in text order: similarity() in SELECT, similarity() and the
    # floor in WHERE, then LIMIT.
    return conn.execute(
        f"SELECT {id_col}, {name_col}, similarity({name_col}, ?) AS score "
        f"FROM {table} {where} ORDER BY score DESC LIMIT ?",
        (query, query, _MIN_SCORE, _MAX_SUGGESTIONS)).fetchall()


def _difflib_ranked(conn, table, id_col, name_col, extra, query):
    where = f"WHERE {name_col} IS NOT NULL AND {name_col} <> ''"
    if extra:
        where += f" AND {extra}"
    rows = conn.execute(
        f"SELECT {id_col}, {name_col} FROM {table} {where} LIMIT ?",
        (_FALLBACK_CANDIDATE_CAP,)).fetchall()

    needle = query.lower()
    scored = []
    for got in rows:
        name = got[1] or ""
        score = difflib.SequenceMatcher(None, needle, name.lower()).ratio()
        if score >= _MIN_SCORE:
            scored.append((got[0], name, score))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored[:_MAX_SUGGESTIONS]
