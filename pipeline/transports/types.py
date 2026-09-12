"""The transport-neutral fetch result (scrapy.md Phase 0).

This is deliberately not `pipeline.http.FetchResult`. That dataclass is
shaped around one httpx response object and is the right shape for
`PipelineHTTPClient`'s callers; a second transport should not have to grow
httpx-flavoured fields it cannot fill in (or worse, fill in with something
that only looks like an httpx response). `TransportResult` is instead shaped
around what CLAUDE.md's provenance rule actually requires: a source URL, a
retrieval time, an exact payload hash, and an archive reference — plus an
explicit statement of *why* a fetch failed, because "no body" must never be
readable as "found nothing".

`require_provenance()` is the enforcement point. It is deliberately a method
on the result rather than a convention callers are trusted to follow: a
candidate/finding writer that skips calling it is a bug the type system
cannot catch, but a writer that calls it gets the "NULL, or reviewed, never
guessed" rule for free. This does not touch `foi_request_candidates` or any
other evidence table — Phase 0/1 introduces the check, later work is what
wires a persistence path through it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class FailureClass(str, Enum):
    """Why a fetch did not produce a usable response.

    `NONE` is the only value that means "treat this as success" — every other
    member exists so a timeout, a block, or a response nobody has taught this
    pipeline to recognise comes back as a *labelled* failure rather than an
    empty body a caller could mistake for "the source published nothing".
    """

    NONE = "none"
    ROBOTS_DISALLOWED = "robots_disallowed"
    BLOCKED_DESTINATION = "blocked_destination"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    EMPTY_RESPONSE = "empty_response"
    UNRECOGNISED = "unrecognised"


class MissingProvenance(RuntimeError):
    """A result cannot carry the provenance CLAUDE.md requires of evidence.

    Raised by `TransportResult.require_provenance()`, never swallowed: a
    caller that catches this and persists anyway has defeated the point of
    calling it.
    """


@dataclass(frozen=True)
class TransportResult:
    """What any transport must be able to say about one fetch attempt.

    `body`/`payload_sha256`/`raw_archive_ref` are about the network response
    only. A browser-rendered DOM is a different artefact (scrapy.md's
    "browser/derived DOM distinction") and must never be assigned to `body`
    here. It gets its own typed fields — `derived_archive_ref`/`derived_kind`
    — rather than living in `transport_meta` as this module first sketched:
    a derived artefact is exactly the kind of thing "provenance or NULL"
    means to be explicit about, and a dict key a future reader could
    misspell without either side noticing is the wrong shape for it. Both
    are `None` for every transport that has no browser leg — see
    `pipeline.transports.browser_pilot` for the one that does.
    """

    transport: str
    source_system: str
    requested_url: str
    retrieved_at: datetime
    ok: bool
    failure_class: FailureClass
    module: str | None = None
    final_url: str | None = None
    status_code: int | None = None
    failure_detail: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    payload_sha256: str = ""
    raw_archive_ref: str | None = None
    # A derived artefact from the SAME fetch attempt — currently only a
    # browser-rendered DOM (`derived_kind="rendered_dom"`), archived through
    # `pipeline.archive.get_derived_archive()` rather than the raw archive.
    # Never required by `require_provenance()`: most transports have no
    # derived artefact at all, and that is a complete, ordinary result, not
    # a missing one.
    derived_archive_ref: str | None = None
    derived_kind: str | None = None
    transport_meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # A caller setting ok=True with a failure class (or vice versa) has a
        # bug worth surfacing immediately, not once the result reaches a
        # writer three layers away.
        if self.ok and self.failure_class is not FailureClass.NONE:
            raise ValueError("ok=True must carry FailureClass.NONE")
        if not self.ok and self.failure_class is FailureClass.NONE:
            raise ValueError("a failed fetch must carry a non-NONE failure_class")

    @property
    def content_type(self) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == "content-type":
                return value
        return None

    def require_provenance(self) -> None:
        """Raise `MissingProvenance` unless this result may become evidence.

        `requested_url` and `retrieved_at` are required unconditionally — an
        attempt that never comes back still has to say what was asked for and
        when. `payload_sha256`/`raw_archive_ref` are required only when bytes
        were actually received (`body` non-empty): a 404 with no body has
        nothing to hash, but the existing HTTPX path archives and hashes an
        error page's body exactly as it does a 200's, and this contract holds
        every transport to the same rule.
        """
        missing = [name for name, present in (
            ("requested_url", bool(self.requested_url)),
            ("retrieved_at", self.retrieved_at is not None),
        ) if not present]
        if self.body:
            missing.extend(name for name, present in (
                ("payload_sha256", bool(self.payload_sha256)),
                ("raw_archive_ref", bool(self.raw_archive_ref)),
            ) if not present)
        if missing:
            raise MissingProvenance(
                f"{self.transport} result for {self.requested_url!r} is missing "
                f"required provenance: {', '.join(missing)}"
            )
