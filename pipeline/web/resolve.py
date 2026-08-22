"""Turning a decision into an answer the pipeline can use.

Approving a review item records a judgement. For most item types that is all
it can honestly do. For two of them it can do more, because the item states
exactly what is missing: `authority_website_unknown` and
`committee_url_unknown` are both "nobody has told this pipeline where this
council publishes", and a person with a browser can find out in a minute.

304 of the 2,172 queued items are those two. Resolving one writes to
`authority_url_overrides`, which `authority_websites.website_for()` reads
ahead of the code registry, so the next run of Module 9 or 10 searches an
authority it previously skipped.

The rule this module exists to enforce: **a URL is checked before it is
stored.** The registry it supplements is populated only with entries confirmed
by a real request, on the reasoning that a wrong base URL either searches an
unrelated site or silently finds nothing while looking like it worked. A form
that accepted typed URLs on trust would put exactly that failure into a table
the modules treat as authoritative, and would do it faster than anyone could
notice. So the server fetches the URL itself, through the same client the
modules use — robots respected, rate limit shared, response archived — and
stores what it saw alongside what it was told.
"""
from __future__ import annotations

import re
import sqlite3
from urllib.parse import urljoin, urlparse

from pipeline import authority_websites
from pipeline.authority_websites import detect_committee_system
from pipeline.config import Settings, get_settings
from pipeline.http import PipelineHTTPClient, RobotsDisallowed
from pipeline.web.review import MAX_NOTE_LENGTH, _apply, _utcnow

# The item types this module can do more than acknowledge, and what each one
# is actually asking for. Anything not here is judgement-only, and the UI
# offers no form for it rather than inventing a resolution nobody can act on.
RESOLVABLE = {
    "authority_website_unknown": {
        "module": "m09_cdp_documents",
        "field": "base_url",
        "label": "Council website",
        "help": "The council's main domain, e.g. https://www.kent.gov.uk — "
                 "Module 9 searches document paths under it.",
    },
    "committee_url_unknown": {
        "module": "m10_committee_papers",
        "field": "committee_url",
        "label": "Committee system URL",
        "help": "The committee/democracy site root, e.g. "
                 "https://democracy.kent.gov.uk — often a different host to "
                 "the main council site.",
    },
}


class ResolveError(Exception):
    """A resolution that was refused, with a message for the reviewer."""


# Does this string already carry a URL scheme?
#
# Two forms, because "contains ://" is not the question. An authority-based
# scheme (http://, file://) is easy. An opaque one — javascript:, mailto:,
# data: — has no slashes, and treating it as scheme-less means prefixing
# https:// onto it, which turns a thing that should be refused for what it is
# into a thing refused for having a strange-looking hostname.
#
# The second pattern excludes dots and a digit after the colon on purpose, so
# `democracy.kent.gov.uk:8443` reads as a host and port rather than as a
# scheme called `democracy.kent.gov.uk`.
_HAS_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://|^[a-zA-Z][a-zA-Z0-9+-]*:(?!\d)")


def normalise_url(raw: str) -> str:
    """A URL this pipeline is willing to fetch, or a refusal saying why.

    Scheme and host are checked here rather than left to the fetch: a typo
    that produces a `file:` or `javascript:` URL should be refused as a
    mistake, not attempted and reported as a failed request.
    """
    url = (raw or "").strip()
    if not url:
        raise ResolveError("Enter a URL.")
    if not _HAS_SCHEME.match(url):
        # A council site typed without a scheme is the common case, not an
        # error worth rejecting.
        url = f"https://{url}"

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ResolveError(
            f"{parsed.scheme}: URLs are not fetchable here — use http or https.")
    if not parsed.netloc or "." not in parsed.netloc:
        raise ResolveError(f"{raw!r} does not look like a web address.")
    return url.rstrip("/")


def check_url(url: str, settings: Settings | None = None,
               conn: sqlite3.Connection | None = None, resolver=None) -> dict:
    """Fetch `url`, and probe it for a known committee system.

    Runs through PipelineHTTPClient, so this request is subject to the same
    robots rules and the same per-host rate limit as everything else the
    pipeline asks of a council — a reviewer clicking Check is a visitor to
    that council's site like any other, and the politeness commitment does not
    have an exception for people in a hurry.

    The destination is guarded (pipeline/netguard.py): this is one of two
    places where a URL typed by whoever can reach the operator UI becomes a
    request from this machine, and nothing here authenticates anybody. A
    council's website is a public address; the network the server is sitting
    on is not.
    """
    settings = settings or get_settings()
    url = normalise_url(url)
    result: dict = {"url": url, "status": None, "ok": False,
                     "system": "unknown", "signature": None, "error": None}

    with PipelineHTTPClient("review_ui", settings, conn,
                              guard_destination=True, resolver=resolver) as client:
        try:
            response = client.get(url)
        except RobotsDisallowed:
            result["error"] = (
                "That site's robots.txt disallows this path for automated "
                "clients, so the pipeline could not fetch it and would not be "
                "able to search it either.")
            return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
            return result

        result["status"] = response.status_code
        result["ok"] = response.ok
        if not response.ok:
            return result

        # Probe the signature paths rather than believing the form. A HEAD
        # would be lighter, but several ModernGov instances answer HEAD with
        # 405 while serving the page perfectly well on GET.
        def probe(path: str) -> str | bool:
            try:
                probed = client.get(urljoin(url + "/", path.lstrip("/")))
            except Exception:
                return False
            if not probed.ok:
                return False
            return probed.body.decode("utf-8", errors="replace")

        result["system"], result["signature"] = detect_committee_system(probe)

    return result


def _authority_name(conn: sqlite3.Connection, ons_code: str) -> str | None:
    """The authority's name, so the tracked file is readable by a person.

    Best effort: a missing name is cosmetic, and the ONS code is the key.
    """
    try:
        row = conn.execute(
            "SELECT name FROM authorities WHERE ons_code = ?", (ons_code,)).fetchone()
    except Exception:
        return None
    return row["name"] if row else None


def resolve_authority_url(
    conn: sqlite3.Connection,
    item_id: int,
    url: str,
    resolved_by: str,
    note: str | None = None,
    settings: Settings | None = None,
) -> dict:
    """Answer a queue item with a verified URL, and approve it.

    One operation, not two. The override and the decision are each other's
    audit trail — an override with no decision is a URL nobody owns, and an
    approval with no override is a queue item that says it was dealt with
    while the module that raised it carries on skipping the authority.
    """
    settings = settings or get_settings()
    resolved_by = (resolved_by or "").strip()
    if not resolved_by:
        raise ResolveError(
            "A reviewer name is required — an assertion about where a council "
            "publishes is worth what the name attached to it is worth.")

    note = (note or "").strip() or None
    if note and len(note) > MAX_NOTE_LENGTH:
        raise ResolveError(f"Note is too long ({MAX_NOTE_LENGTH} characters maximum).")

    item = conn.execute(
        "SELECT * FROM review_queue WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ResolveError(f"No review item {item_id}.")

    spec = RESOLVABLE.get(item["item_type"])
    if spec is None:
        raise ResolveError(
            f"{item['item_type']} items are not resolvable with a URL — "
            "approving one records a judgement and nothing else.")

    # For both resolvable types the raw value is the ONS code of the authority
    # nobody could find. That is the whole reason they can be resolved.
    ons_code = (item["raw_value"] or "").strip()
    if not ons_code:
        raise ResolveError("This item carries no authority code to attach a URL to.")

    checked = check_url(url, settings, conn)
    if not checked["ok"]:
        raise ResolveError(
            f"{checked['url']} did not answer"
            + (f" ({checked['error']})" if checked["error"] else
                f" — HTTP {checked['status']}")
            + ". Nothing was saved: a URL that does not respond would make the "
              "module search an unreachable site and find nothing, which looks "
              "identical to a council that publishes nothing.")

    now = _utcnow()
    field = spec["field"]
    existing = conn.execute(
        "SELECT * FROM authority_url_overrides WHERE ons_code = ?", (ons_code,)).fetchone()

    row = {
        "ons_code": ons_code,
        # Answering one question must not erase the answer to the other.
        "base_url": existing["base_url"] if existing else None,
        "committee_url": existing["committee_url"] if existing else None,
        "committee_system": existing["committee_system"] if existing else None,
        "checked_url": checked["url"],
        "checked_status": checked["status"],
        "checked_at": now,
        "verified_by": resolved_by,
        "verified_at": now,
        "note": note,
        "review_item_id": item_id,
    }
    row[field] = checked["url"]
    if field == "committee_url" and checked["system"] != "unknown":
        row["committee_system"] = checked["system"]

    with conn:
        conn.execute(
            "INSERT INTO authority_url_overrides "
            "(ons_code, base_url, committee_url, committee_system, checked_url, "
            " checked_status, checked_at, verified_by, verified_at, note, review_item_id) "
            "VALUES (:ons_code, :base_url, :committee_url, :committee_system, :checked_url, "
            " :checked_status, :checked_at, :verified_by, :verified_at, :note, :review_item_id) "
            "ON CONFLICT (ons_code) DO UPDATE SET "
            "  base_url = excluded.base_url, committee_url = excluded.committee_url, "
            "  committee_system = excluded.committee_system, "
            "  checked_url = excluded.checked_url, checked_status = excluded.checked_status, "
            "  checked_at = excluded.checked_at, verified_by = excluded.verified_by, "
            "  verified_at = excluded.verified_at, note = excluded.note, "
            "  review_item_id = excluded.review_item_id",
            row,
        )

        decision_note = f"{spec['label']}: {checked['url']}"
        if checked["system"] != "unknown":
            decision_note += f" ({checked['system']})"
        if note:
            decision_note += f" — {note}"
        decision = _apply(conn, [item_id], "approved", resolved_by, decision_note, now)

    # And again where git can see it. The override row above is the live
    # record and this is the one that survives it: on 2026-08-13 that table
    # was emptied and 191 verified URLs went with it, of which only the 105
    # a verification document happened to record could be recovered.
    #
    # Written after the transaction, deliberately. The answer is stored and
    # the item is decided by this point, so a filesystem that refuses cannot
    # undo either -- it can only leave this copy missing, which is what the
    # warning inside says.
    authority_websites.record_verified_website(
        ons_code=ons_code,
        name=_authority_name(conn, ons_code),
        field=field,
        url=checked["url"],
        committee_system=(checked["system"]
                           if field == "committee_url" and checked["system"] != "unknown"
                           else None),
        verified_by=resolved_by,
        verified_on=now[:10],
        settings=settings,
    )

    return {
        "ons_code": ons_code,
        "field": field,
        "url": checked["url"],
        "status": checked["status"],
        "system": checked["system"],
        "module": spec["module"],
        "decision": decision,
        "resolved_by": resolved_by,
        "resolved_at": now,
    }


def resolvable_types() -> dict:
    """What the UI needs to render a resolution form per item type."""
    return RESOLVABLE


def overrides(conn: sqlite3.Connection) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM authority_url_overrides ORDER BY verified_at DESC")]
