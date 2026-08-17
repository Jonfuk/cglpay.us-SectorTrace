"""Listing claims for a person to review and decide.

The read half of `pipeline/claims.py`, the way `census.py` is the read half of
`census_verify.py` and `candidates.py` of `promote.py` — and out of
`queries.py` for the same reason: this is one specific table with one specific
shape rather than the generic browser.

The shape follows the decision it supports. Reviewing a claim means reading
the statement, seeing what evidence it cites, and deciding whether the
campaign can say it. So the worklist renders the claim text, its caveats, and
each citation's label beside it, with the decision history underneath — the
same "the line is what was parsed, the page is what it meant" logic the
census worklist uses, one level up: the claim is the line, the citations are
the page.

Everything here is read-only. Deciding goes through `pipeline/claims.py`,
which is where the audit trail lives.
"""
from __future__ import annotations

import sqlite3

from pipeline import claims

PAGE = 50


def listing(conn: sqlite3.Connection, status: str = "all", offset: int = 0,
            limit: int = PAGE) -> dict:
    """One page of claims, with citations resolved to display payloads.

    Resolution happens here rather than in the browser so that a citation
    whose row a module run has replaced is shown as unresolvable before the
    reviewer commits to the claim. The `resolved` flag is the honest half:
    a claim that rests on rows that are no longer there is exactly the claim
    a reviewer should see flagged.
    """
    page = claims.listing(conn, status=status, offset=offset, limit=limit)
    for item in page["items"]:
        for citation in item["citations"]:
            citation["resolved"] = claims.resolve_citation(
                conn, citation["evidence_table"], citation["evidence_key"])
    return page


def counts(conn: sqlite3.Connection) -> dict:
    return claims.counts(conn)


def evidence_search(conn: sqlite3.Connection, table: str, q: str,
                    limit: int = 20) -> list[dict]:
    return claims.search_citable(conn, table, q, limit=limit)
