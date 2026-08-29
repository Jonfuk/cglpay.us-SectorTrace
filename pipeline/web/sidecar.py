"""Evidence sidecar for a review-queue item — read-only decision support (BETA-054).

Beside the decision form, a reviewer wants two things the item row does not
carry: the passage of source text the item is about, and — for the item types
that name something unresolved — a ranked list of what it might be.

Both are aids, never verdicts:

  * the source excerpt is whatever the item's own `context_json` stored (a
    sentence, a snippet, a contravention description) plus its URL and archive
    hash — nothing is re-fetched;
  * the candidates come from the existing `name_matches.suggestions` trigram /
    difflib ranking, relabelled as a **similarity percentage**, with
    `preselected` always false and a short list of known false-match name
    tokens suppressed so a page of "…Council" rows is not offered as if it
    meant something.
"""
from __future__ import annotations

import json

from pipeline.web import name_matches
from pipeline.web.queries import QueryError

# Context keys that hold the passage of source text, in preference order.
_EXCERPT_KEYS = ("sentence", "evidence_span", "snippet", "excerpt",
                  "mention_text", "contravention_text", "match_text",
                  "description", "note")
_URL_KEYS = ("source_url", "url", "page_url", "source_page", "notice_web_url",
              "document_url", "report_url")

# Normalised candidate names that are almost always a false match for an
# unresolved buyer/company name — too generic to be an answer.
_FALSE_MATCH_NORMS = frozenset({
    "council", "the council", "county council", "borough council",
    "city council", "district council", "nhs", "the nhs", "trust",
    "the trust", "limited", "ltd", "unknown",
})


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def sidecar(conn, item_id: int) -> dict:
    """Source excerpt + ranked candidates for one review item. Read-only."""
    row = conn.execute(
        "SELECT id, module, item_type, raw_value, context_json "
        "FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise QueryError(f"No review item {item_id}.")

    context: dict = {}
    if row["context_json"]:
        try:
            parsed = json.loads(row["context_json"])
            if isinstance(parsed, dict):
                context = parsed
        except (TypeError, ValueError):
            context = {}

    excerpt = next((str(context[k]) for k in _EXCERPT_KEYS if context.get(k)), None)
    url = next((str(context[k]) for k in _URL_KEYS if context.get(k)), None)
    source = {
        "excerpt": excerpt,
        "url": url,
        "retrieved_at": context.get("retrieved_at"),
        "payload_sha256": context.get("payload_sha256"),
        "note": None if (excerpt or url)
                else "This item type stored no source excerpt in its context.",
    }

    supported = row["item_type"] in name_matches._TARGETS
    candidates: dict = {
        "supported": supported, "method": None, "query": None,
        "ranking": [], "suppressed": [],
    }
    if supported:
        try:
            ranked = name_matches.suggestions(conn, item_id)
        except name_matches.NameMatchError as exc:
            raise QueryError(str(exc)) from None
        candidates["method"] = ranked.get("method")
        candidates["query"] = ranked.get("query")
        for match in ranked.get("matches", []):
            entry = {
                "target": match["target"],
                "id": match["id"],
                "name": match["name"],
                "similarity_percent": round(match["score"] * 100, 1),
                "preselected": False,
            }
            if _norm(match["name"]) in _FALSE_MATCH_NORMS:
                candidates["suppressed"].append(entry)
            else:
                candidates["ranking"].append(entry)

    return {
        "item_id": item_id,
        "item_type": row["item_type"],
        "module": row["module"],
        "source": source,
        "candidates": candidates,
        "caveat": (
            "A similarity percentage ranks candidates for a reviewer to "
            "choose from — it does not pick one, nothing is preselected, and "
            "approving the item still writes nothing to a canonical table. "
            "The source excerpt is whatever the item stored; open the URL for "
            "the full context."),
    }
