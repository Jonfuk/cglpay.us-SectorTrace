"""Atom feeds for external subscription (BETA-089).

One stable, well-formed Atom 1.0 feed over the "what changed?" stream
(BETA-090), filterable by the same `kind` / `source` / `since` parameters as
`/api/v1/changes`. A reader saves the feed URL in their own reader; there is
no account and no per-user state.

"Stable" means the feed's `<id>` and every entry `<id>` are host-independent
tag URIs derived from the event's own content, so the same change keeps the
same id across releases and across the dev / production hosts.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from pipeline.web import public_queries

# RFC 4151 tag URI authority + date. Fixed strings — the point is that they do
# not vary with the host the feed is served from.
_TAG_AUTHORITY = "trace.cglpay.us,2026"
_FEED_LIMIT = 100


def _rfc3339(value: str | None) -> str:
    """An ISO-ish timestamp normalised to RFC 3339 with a `Z`. Falls back to
    now for an entry the warehouse recorded without a date."""
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(value).strip().replace(" ", "T")
    if text.endswith("Z"):
        return text
    if "+" in text[10:] or text[10:].startswith("-"):
        return text
    return text + "Z"


def _entry_id(event: dict) -> str:
    digest = hashlib.sha1(
        f"{event.get('kind')}|{event.get('at')}|{event.get('detail')}"
        .encode("utf-8")).hexdigest()[:16]
    return f"tag:{_TAG_AUTHORITY}:change/{event.get('kind', 'event')}/{digest}"


def changes_atom(conn, *, kind=None, source=None, since=None,
                  self_url: str, site_url: str = "https://trace.cglpay.us/") -> str:
    """The change feed as an Atom 1.0 document (a string).

    `self_url` is the absolute URL this feed was requested at, for the
    `rel="self"` link. The feed `<id>` is not that URL — it is a fixed tag
    URI plus the active filter, so the same filtered feed has one identity
    wherever it is served.
    """
    data = public_queries.change_feed(
        conn, kind=kind, source=source, since=since, limit=_FEED_LIMIT)
    events = data.get("events", [])

    filter_key = "/".join(
        p for p in (kind or "", source or "", (since or "")[:10]) if p) or "all"
    feed_id = f"tag:{_TAG_AUTHORITY}:feed/changes/{filter_key}"
    updated = max((_rfc3339(e.get("at")) for e in events if e.get("at")),
                  default=_rfc3339(None))
    title = "SectorTrace — what changed" + (f" ({filter_key})" if filter_key != "all" else "")

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(title)}</title>",
        f"  <id>{escape(feed_id)}</id>",
        f"  <updated>{updated}</updated>",
        f'  <link rel="self" type="application/atom+xml" href="{escape(self_url)}"/>',
        f'  <link rel="alternate" type="text/html" href="{escape(site_url)}#/changes"/>',
        "  <generator>SectorTrace</generator>",
        f"  <subtitle>{escape(data.get('caveat', ''))}</subtitle>",
    ]
    for event in events:
        entry_updated = _rfc3339(event.get("at"))
        summary = event.get("detail") or event.get("kind") or "change"
        etitle = f"{(event.get('kind') or 'change').title()}: {summary}"
        lines += [
            "  <entry>",
            f"    <title>{escape(etitle[:200])}</title>",
            f"    <id>{escape(_entry_id(event))}</id>",
            f"    <updated>{entry_updated}</updated>",
            f'    <link rel="alternate" type="text/html" href="{escape(site_url)}#/changes"/>',
            f"    <category term=\"{escape(event.get('kind') or 'change')}\"/>",
        ]
        if event.get("source"):
            lines.append(f"    <author><name>{escape(str(event['source']))}</name></author>")
        lines.append(f"    <summary>{escape(str(summary))}</summary>")
        lines.append("  </entry>")
    lines.append("</feed>")
    return "\n".join(lines) + "\n"
