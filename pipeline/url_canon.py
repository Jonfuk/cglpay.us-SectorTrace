"""Conservative URL canonicalisation (BETA-057).

Just enough to tell "the same document, discovered twice" from "two
addresses that merely look alike" — and no more. It:

  * lowercases the scheme and host (both are case-insensitive by spec);
  * drops the fragment (`#...` — client-side, never identifies a document);
  * drops a known-tracking query parameter (`utm_*`, `gclid`, `fbclid`, …);
  * sorts the remaining query parameters so order does not matter;
  * strips a single trailing slash from the path.

It does **not** follow a redirect, resolve `..`, add or remove `www`, guess
that `/index.html` equals `/`, or touch percent-encoding. Those are all
places where "probably the same" turns into a wrong merge, and this function
exists to feed a *signal*, not to decide identity.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query keys that are analytics / campaign tracking, never part of a
# document's identity. Matched case-insensitively.
_TRACKING = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "_ga", "_gl",
    "igshid", "ref_src", "ref_url", "spm", "yclid",
})

_DEFAULT_PORTS = {"http": 80, "https": 443}


def canonical(url: str) -> str:
    """The canonical form, or the input stripped if it does not parse as an
    absolute http(s) URL (so a caller can filter on the `http` prefix)."""
    raw = (url or "").strip()
    parts = urlsplit(raw)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return raw

    scheme = parts.scheme.lower()
    host = parts.hostname.lower()
    if parts.port and parts.port != _DEFAULT_PORTS.get(scheme):
        host = f"{host}:{parts.port}"

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]

    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in _TRACKING]
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, host, path, query, ""))
