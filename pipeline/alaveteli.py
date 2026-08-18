"""Parsing for Alaveteli's JSON read API — the shape WhatDoTheyKnow returns.

Pure functions: no HTTP, no database, no settings.

Two shapes live here, and they are reached very differently.

  * The **feed** shape (`parse_feed_event`, `parse_feed_page`) — served by
    `/feed/search/<query>.json`, which does answer this pipeline. Module 15
    uses it. It is a discovery source only: entries carry a search snippet,
    never a full message body.

  * The **read API** shape (`parse_info_request`, `parse_authority`,
    `extract_response_texts`) — `/request/<slug>.json` and `/body/<slug>.json`,
    which as of 2026-08-11 answer this pipeline with a Cloudflare 403. The
    human-promotion path also accepts the canonical rendered request HTML when
    the JSON route returns 502; it uses `parse_info_request_html` and keeps
    outgoing correspondence out of the response field.

Callers get a `ParseOutcome` rather than a bare dict, because this pipeline's
rule is that an unparseable field becomes NULL and is logged — never
defaulted to an empty string. A blank authority name that joins to nothing is
indistinguishable from real data downstream, which is the failure mode this
shape prevents: the caller must handle `.failures` to get at `.record`.

Alaveteli wraps objects inconsistently depending on endpoint and version —
sometimes `{"info_request": {...}}`, sometimes the object bare — so every
accessor unwraps defensively.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

# Alaveteli's `described_state` vocabulary. These ten are *observed* values,
# taken from the filters WhatDoTheyKnow exposes on its own public feeds, not
# guessed at from the source. Alaveteli may define others.
#
# That is why an unrecognised state is recorded as a parse failure and stored
# as NULL rather than passed through: the failure log then tells us exactly
# which states are missing here, instead of an unknown string flowing into
# `foi_requests.status` and being counted in a campaign figure. Add to this
# set only after seeing a value in the log.
KNOWN_DESCRIBED_STATES = frozenset({
    "successful",
    "partially_successful",
    "rejected",
    "not_held",
    "waiting_response",
    "waiting_clarification",
    "internal_review",
    "gone_postal",
    "error_message",
    "requires_admin",
    # Both observed in live /feed/search/ output on 2026-08-11, which is the
    # bar this set documents for admission. `attention_requested` was
    # previously this module's example of a state that *should* fail, and
    # `user_withdrawn` was the first full run's only parse failure — the
    # mechanism working as intended rather than a surprise. Neither discloses
    # anything, so neither joins DISCLOSING_STATES.
    "attention_requested",
    "user_withdrawn",
})

# Event `variety` values, from the same source.
KNOWN_EVENT_VARIETIES = frozenset({"sent", "followup_sent", "response", "comment"})

# Which described_states mean the authority actually released something. Used
# to separate "we have a response" from "we are still waiting", which is the
# distinction that matters when claiming coverage.
DISCLOSING_STATES = frozenset({"successful", "partially_successful"})


@dataclass(frozen=True)
class ParseFailure:
    """One field that could not be parsed. Maps onto db.record_parse_failure."""

    field_name: str
    raw_fragment: str
    reason: str


@dataclass
class ParseOutcome:
    """A parsed record plus everything that went wrong producing it.

    `record` is None only when the input was too malformed to identify at
    all. A record with failures is still usable — the affected fields are
    NULL — which is the normal case and why the two are returned together.
    """

    record: dict[str, Any] | None
    failures: list[ParseFailure] = field(default_factory=list)


def _unwrap(raw: Any, key: str) -> dict[str, Any]:
    """Alaveteli sometimes nests an object under its type name and sometimes
    returns it bare. Accept both rather than depending on which endpoint or
    version produced it.
    """
    if not isinstance(raw, dict):
        return {}
    inner = raw.get(key)
    if isinstance(inner, dict):
        return inner
    return raw


def _clean(value: Any) -> str | None:
    """Trim to a real string or None. Never "" — an empty string reads as
    data downstream, a NULL does not.
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _iso_datetime(value: Any, field_name: str, failures: list[ParseFailure]) -> str | None:
    """Normalise a timestamp to ISO-8601, or record why it could not be.

    Python 3.10's `fromisoformat` rejects a trailing 'Z', which Alaveteli
    does emit, so that is translated before parsing rather than being allowed
    to look like a malformed date.
    """
    text = _clean(value)
    if text is None:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        return datetime.fromisoformat(candidate).isoformat()
    except ValueError:
        failures.append(ParseFailure(field_name, text, "unrecognised datetime format"))
        return None


def _described_state(value: Any, failures: list[ParseFailure]) -> str | None:
    state = _clean(value)
    if state is None:
        return None
    if state not in KNOWN_DESCRIBED_STATES:
        failures.append(ParseFailure(
            "described_state", state,
            "not in the observed Alaveteli state vocabulary — verify and add "
            "to KNOWN_DESCRIBED_STATES before relying on it",
        ))
        return None
    return state


def parse_authority(raw: Any) -> ParseOutcome:
    """An authority from /body/<slug>.json.

    Note this is *not* the pipeline's route to the authority register — the
    published CSV covers all 317 in one request and carries the GSS codes
    that make the join exact. This is here for the per-authority detail the
    CSV omits, chiefly the request count.
    """
    body = _unwrap(raw, "public_body")
    failures: list[ParseFailure] = []

    slug = _clean(body.get("url_name"))
    name = _clean(body.get("name"))
    if slug is None and name is None:
        return ParseOutcome(None, [ParseFailure(
            "public_body", str(raw)[:200], "no url_name or name — not an authority object")])

    count = body.get("info_requests_count")
    if count is not None and not isinstance(count, int):
        failures.append(ParseFailure("info_requests_count", str(count)[:100], "not an integer"))
        count = None

    return ParseOutcome({
        "wdtk_body_slug": slug,
        "authority_name": name,
        "short_name": _clean(body.get("short_name")),
        "home_page_url": _clean(body.get("home_page")),
        "notes": _clean(body.get("notes")),
        "request_count": count,
    }, failures)


def extract_response_texts(raw: Any) -> list[str]:
    """Bodies of incoming responses, in the order Alaveteli lists them.

    Only events of variety `response` are taken. The requester's own outgoing
    messages are on the same timeline, and including them would put the
    campaign's own words into a field labelled as the authority's answer.
    """
    info = _unwrap(raw, "info_request")
    texts: list[str] = []
    for event in info.get("info_request_events") or []:
        ev = _unwrap(event, "info_request_event")
        variety = _clean(ev.get("event_type")) or _clean(ev.get("variety"))
        if variety != "response":
            continue
        incoming = ev.get("incoming_message")
        body = _clean(incoming.get("body")) if isinstance(incoming, dict) else _clean(ev.get("body"))
        if body:
            texts.append(body)
    return texts


# --- the /feed/search/ shape ----------------------------------------------------
#
# A different serialisation from the read API above, and the distinction
# matters: a feed entry is an *event* with the request nested inside it, not a
# request with events nested inside it. One request appears once per matching
# event, so callers must deduplicate on request_slug.
#
# The important limitation is that a feed entry carries `snippet` — a short,
# search-highlighted extract — and never a full message body. This is a
# discovery source. It cannot populate `foi_requests.response_text`, and
# treating a snippet as a response would put a truncated fragment into a
# column the campaign quotes from.

_HIGHLIGHT_RE = re.compile(r"</?span[^>]*>", re.IGNORECASE)


def gss_from_tags(tags: Any) -> str | None:
    """The GSS code from a feed `public_body.tags` value.

    Note this is *not* the same shape as the authority CSV's tag string, which
    `m15_foi.extract_gss_code` handles — here Alaveteli emits a list of
    [key, value] pairs. Two accessors rather than one shared regex, because
    silently accepting either shape would hide the day one of them changes.
    """
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if isinstance(tag, (list, tuple)) and len(tag) == 2:
            key, value = tag
            if key in ("gss", "statistical_geography") and isinstance(value, str):
                code = value.strip()
                if code:
                    return code
    return None


def clean_snippet(value: Any) -> str | None:
    """A feed snippet with its search-highlight markup removed.

    Alaveteli wraps matched terms in `<span class="highlight">`. Left in, that
    markup reaches anything rendering the text, and worse, it would count as
    part of the extract if the snippet were ever quoted.
    """
    text = _clean(value)
    if text is None:
        return None
    stripped = _HIGHLIGHT_RE.sub("", text)
    return _clean(re.sub(r"\s+", " ", stripped))


def parse_feed_event(raw: Any, *, base_url: str = "https://www.whatdotheyknow.com") -> ParseOutcome:
    """One event from /feed/search/<query>.json.

    `response_text` is deliberately absent from the returned record rather
    than set from `snippet` — see the note above.
    """
    if not isinstance(raw, dict):
        return ParseOutcome(None, [ParseFailure(
            "feed_event", str(raw)[:200], "not an object")])

    failures: list[ParseFailure] = []
    info = _unwrap(raw.get("info_request") or {}, "info_request")
    slug = _clean(info.get("url_title"))
    if slug is None:
        return ParseOutcome(None, [ParseFailure(
            "info_request", str(raw)[:200], "no nested info_request.url_title — not a feed event")])

    body = raw.get("public_body")
    body = body if isinstance(body, dict) else {}

    variety = _clean(raw.get("event_type"))
    if variety is not None and variety not in KNOWN_EVENT_VARIETIES:
        failures.append(ParseFailure(
            "event_type", variety, "not in the observed Alaveteli event vocabulary"))
        variety = None

    # The event's own described_state is null on search results; the request's
    # is the populated one. Read only the latter rather than falling back
    # between them, so a future change to either is visible.
    status = _described_state(info.get("described_state"), failures)

    return ParseOutcome({
        "external_id": str(info["id"]) if info.get("id") is not None else None,
        "request_slug": slug,
        "request_url": f"{base_url.rstrip('/')}/request/{slug}",
        "subject": _clean(info.get("title")),
        "authority_name": _clean(body.get("name")),
        "authority_slug": _clean(body.get("url_name")),
        "ons_code": gss_from_tags(body.get("tags")),
        "status": status,
        "disclosed": (status in DISCLOSING_STATES) if status else None,
        "law_used": _clean(info.get("law_used")),
        "prominence": _clean(info.get("prominence")),
        "request_date": _iso_datetime(info.get("created_at"), "created_at", failures),
        "last_updated": _iso_datetime(info.get("updated_at"), "updated_at", failures),
        "event_type": variety,
        "event_date": _iso_datetime(raw.get("created_at"), "event.created_at", failures),
        "snippet": clean_snippet(raw.get("snippet")),
    }, failures)


def parse_feed_page(raw: Any) -> tuple[list[dict[str, Any]], list[ParseFailure]]:
    """A whole /feed/search/ page. Returns (records, failures).

    A page is a bare JSON array. An entry that cannot be identified at all is
    dropped with a failure recorded rather than aborting the page — one
    malformed event should not discard the other 24.
    """
    if not isinstance(raw, list):
        return [], [ParseFailure("feed_page", str(raw)[:200], "expected a JSON array of events")]

    records: list[dict[str, Any]] = []
    failures: list[ParseFailure] = []
    for entry in raw:
        outcome = parse_feed_event(entry)
        failures.extend(outcome.failures)
        if outcome.record is not None:
            records.append(outcome.record)
    return records, failures


def parse_info_request(raw: Any, *, base_url: str = "https://www.whatdotheyknow.com") -> ParseOutcome:
    """One FOI request from /request/<slug>.json or a listing entry.

    A listing entry carries no events, so `response_text` comes back None
    rather than "" — the caller can tell "not fetched yet" from "fetched, no
    response", which an empty string would collapse.
    """
    info = _unwrap(raw, "info_request")
    failures: list[ParseFailure] = []

    external_id = info.get("id")
    slug = _clean(info.get("url_title"))
    if external_id is None and slug is None:
        return ParseOutcome(None, [ParseFailure(
            "info_request", str(raw)[:200], "no id or url_title — not a request object")])

    public_body = info.get("public_body")
    if isinstance(public_body, dict):
        authority_name = _clean(public_body.get("name"))
        authority_slug = _clean(public_body.get("url_name"))
    else:
        authority_name = _clean(info.get("public_body_name"))
        authority_slug = None

    initial = info.get("initial_request")
    description = _clean(initial.get("body")) if isinstance(initial, dict) else None

    # display_status is a humanised label ("Awaiting response"); described_state
    # is the machine value. Only the latter is trusted, so a missing
    # described_state yields NULL rather than falling back to prose that would
    # never match the vocabulary.
    status = _described_state(info.get("described_state"), failures)

    responses = extract_response_texts(raw)
    has_events = bool(info.get("info_request_events"))

    return ParseOutcome({
        "external_id": str(external_id) if external_id is not None else None,
        "request_slug": slug,
        "request_url": f"{base_url.rstrip('/')}/request/{slug}" if slug else None,
        "subject": _clean(info.get("title")),
        "description": description,
        "authority_name": authority_name,
        "authority_slug": authority_slug,
        "status": status,
        "disclosed": (status in DISCLOSING_STATES) if status else None,
        "request_date": _iso_datetime(info.get("created_at"), "created_at", failures),
        "last_updated": _iso_datetime(info.get("updated_at"), "updated_at", failures),
        "response_text": "\n\n---\n\n".join(responses) if responses else None,
        "response_count": len(responses) if has_events else None,
    }, failures)


class _WdtkHtmlParser(HTMLParser):
    """Extract the stable, semantic parts of a rendered WDTK request page.

    This deliberately reads only ``incoming`` correspondence blocks. The
    page repeats the requester's outgoing message below each response, and
    including it would put the question into ``response_text``.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self._in_title = False
        self._incoming_depth = 0
        self._body_depth = 0
        self._body: list[list[str]] = []
        self._current: list[str] | None = None
        self._times: list[str] = []
        self._strong: list[str] = []
        self._in_strong = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        classes = set((attr.get("class") or "").split())
        if tag == "h1":
            self._in_title = True
        if tag == "time" and attr.get("datetime"):
            self._times.append(attr["datetime"])
        if tag == "strong":
            self._in_strong = True
        if tag == "div" and attr.get("id", "").startswith("incoming-"):
            self._incoming_depth = 1
            self._current = []
        elif self._incoming_depth:
            self._incoming_depth += tag == "div"
        if self._incoming_depth and "correspondence_text" in classes:
            self._body_depth = 1
        elif self._body_depth:
            self._body_depth += tag == "div"
        if self._body_depth and tag in {"p", "br", "li"} and self._current is not None:
            self._current.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_title = False
        if tag == "strong":
            self._in_strong = False
        if self._body_depth and tag == "div":
            self._body_depth -= 1
        if self._incoming_depth and tag == "div":
            self._incoming_depth -= 1
            if self._incoming_depth == 0 and self._current is not None:
                self._body.append(self._current)
                self._current = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        if self._in_strong:
            self._strong.append(data)
        if self._body_depth and self._current is not None:
            self._current.append(data)


def parse_info_request_html(html: str, *, base_url: str = "https://www.whatdotheyknow.com",
                            request_url: str | None = None) -> ParseOutcome:
    """Parse the canonical rendered WDTK page used when its JSON route fails."""
    parser = _WdtkHtmlParser()
    try:
        parser.feed(html)
    except Exception as exc:  # HTMLParser is permissive, but keep NULL-first semantics.
        return ParseOutcome(None, [ParseFailure("wdtk_html", html[:200],
                                                f"malformed HTML: {type(exc).__name__}")])

    def clean(text: str) -> str | None:
        value = re.sub(r"\s+", " ", text).strip()
        return value or None

    responses = [clean("".join(parts)) for parts in parser._body]
    responses = [response for response in responses if response]
    title = clean("".join(parser.title))
    status = None
    status_text = clean(" ".join(parser._strong)) or ""
    for candidate in KNOWN_DESCRIBED_STATES:
        if re.search(rf"\b{re.escape(candidate.replace('_', ' '))}\b", status_text,
                     re.IGNORECASE):
            status = candidate
            break
    failures: list[ParseFailure] = []
    if not parser._body:
        failures.append(ParseFailure("response_text", "", "no incoming correspondence blocks"))
    return ParseOutcome({
        "request_url": request_url,
        "subject": title,
        "request_date": parser._times[0] if parser._times else None,
        "status": status,
        "disclosed": (status in DISCLOSING_STATES) if status else None,
        "response_text": "\n\n---\n\n".join(responses) if responses else None,
        "response_count": len(responses),
    }, failures)
