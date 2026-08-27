"""Operator-side adapter for the semantic-analysis retrieval layer.

`pipeline/nlp/` is deliberately web-agnostic -- it never imports anything from
`pipeline/web/`. This is the one-way bridge: it translates the query-string
into a `semantic_search.search()` call and its `SearchError` into the
`QueryError` the request handler already turns into a 400.

An `/api/admin/*` route, not `/api/v1/*`: this is a finding aid over the
parsed archive, no personal data and nothing exported, but it is the
operator's tool and stays behind the same network-trust boundary as the rest
of `/api/admin`. `tests/test_portal_isolation.py` pins that.
"""
from __future__ import annotations

from pipeline.nlp import semantic_search
from pipeline.web.queries import QueryError


def search(conn, *, query: str, mode: str, limit: int, source_system: str | None,
           date_from: str | None, date_to: str | None) -> dict:
    try:
        return semantic_search.search(
            conn, query, mode=mode, limit=limit, source_system=source_system,
            date_from=date_from, date_to=date_to)
    except semantic_search.SearchError as exc:
        raise QueryError(str(exc)) from None
