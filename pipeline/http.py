"""Shared HTTP client: robots.txt compliance, per-host rate limiting,
conditional requests, retry/backoff, and provenance capture (constraints 1
and 4). Every module fetches through this — no module should call httpx
directly.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from pipeline import db
from pipeline.config import Settings, get_settings

log = structlog.get_logger()


class RobotsDisallowed(Exception):
    """robots.txt forbids fetching this URL for our user agent."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return False


_fallback_wait = wait_exponential(multiplier=1, min=1, max=30)


def _wait_respecting_retry_after(retry_state):
    """429/503 responses on these APIs document a Retry-After header
    (seconds) that must be honoured rather than guessed at with blind
    exponential backoff — some sources (e.g. Contracts Finder) impose a
    multi-minute block on repeat offenders.
    """
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, httpx.HTTPStatusError):
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return _fallback_wait(retry_state)


@dataclass
class FetchResult:
    url: str
    status_code: int
    body: bytes
    headers: httpx.Headers
    retrieved_at: datetime
    payload_sha256: str
    not_modified: bool
    archived_path: Path | None

    @property
    def content_type(self) -> str | None:
        return self.headers.get("content-type")

    @property
    def ok(self) -> bool:
        """True when this result carries usable content.

        Modules must test this rather than `status_code == 200`: a 304 is a
        successful conditional request whose body is served from the raw
        archive, and treating it as a failure silently drops every document
        on the second and subsequent runs.
        """
        return bool(self.body) and self.status_code < 400

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"{self.status_code} for {self.url}", request=None, response=None  # type: ignore[arg-type]
            )


class _RateLimiter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._last_request_at: dict[str, float] = {}

    def wait(self, host: str) -> None:
        min_interval = self._settings.rate_limit_for_host(host)
        last = self._last_request_at.get(host)
        now = time.monotonic()
        if last is not None:
            elapsed = now - last
            remaining = min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
        self._last_request_at[host] = time.monotonic()


class RobotsRules:
    """robots.txt rule matching with wildcard support, per RFC 9309.

    This does not use `urllib.robotparser`, and that is the whole point.
    The stdlib parser matches a rule with `path.startswith(rule)`, so it has
    no support for `*` or `$` — a rule like `Disallow: */feed/*` matches
    nothing at all, because no real path starts with a literal asterisk. Sites
    that write their rules that way are silently treated as allow-all.

    That is not a hypothetical. mySociety's robots.txt is written almost
    entirely in that style (`*/feed/*`, `*/search/*`,
    `*/request/*/response/*`), so under the stdlib parser this pipeline would
    have believed it was honouring robots.txt while ignoring every rule on the
    host. Since "we respect robots.txt" is a claim this project makes in
    writing and relies on when asking sources for access, it has to be true of
    the wildcard rules too.

    Matching follows RFC 9309: the most specific rule wins (longest pattern),
    Allow beats Disallow on a tie, and an empty Disallow value means allow.
    """

    def __init__(self, text: str, user_agent: str) -> None:
        self._rules: list[tuple[str, bool, re.Pattern[str]]] = []
        self._parse(text, user_agent)

    @staticmethod
    def _token(user_agent: str) -> str:
        """The product token from a full User-Agent string.

        robots.txt groups name a product token ("googlebot"), not the whole
        header, so `cglpay-evidence-pipeline/0.1 (+contact: ...)` has to be
        reduced to `cglpay-evidence-pipeline` before it can match a group.
        """
        return user_agent.split("/")[0].strip().lower()

    @staticmethod
    def _compile(pattern: str) -> re.Pattern[str]:
        """A robots path pattern as a regex anchored at the start of the path.

        `*` is any sequence; a trailing `$` anchors the end. Everything else is
        matched literally, so a `.` or `?` in a path cannot act as a
        metacharacter and quietly widen a rule.
        """
        anchored_end = pattern.endswith("$")
        if anchored_end:
            pattern = pattern[:-1]
        regex = "".join(".*" if ch == "*" else re.escape(ch) for ch in pattern)
        return re.compile(f"^{regex}{'$' if anchored_end else ''}")

    def _parse(self, text: str, user_agent: str) -> None:
        token = self._token(user_agent)
        # Collect rules per group first: a specific group for our token
        # overrides the wildcard group entirely rather than adding to it.
        groups: dict[str, list[tuple[str, bool]]] = {}
        current: list[str] = []
        starting_group = False

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, _, value = line.partition(":")
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                if not starting_group:
                    current = []
                    starting_group = True
                current.append(value.lower())
                groups.setdefault(value.lower(), [])
            elif field in ("allow", "disallow"):
                starting_group = False
                for agent in current:
                    groups.setdefault(agent, []).append((value, field == "allow"))

        selected = groups.get(token)
        if selected is None:
            selected = groups.get("*", [])

        for value, is_allow in selected:
            if not value:
                # "Disallow:" with no value means allow everything; it carries
                # no pattern, so it simply contributes no rule.
                continue
            self._rules.append((value, is_allow, self._compile(value)))

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        best_len = -1
        allowed = True
        for pattern, is_allow, regex in self._rules:
            if not regex.match(path):
                continue
            # Longest pattern wins; Allow wins a tie of equal length.
            if len(pattern) > best_len or (len(pattern) == best_len and is_allow):
                best_len = len(pattern)
                allowed = is_allow
        return allowed


class _RobotsCache:
    def __init__(self, client: httpx.Client, user_agent: str) -> None:
        self._client = client
        self._user_agent = user_agent
        self._rules: dict[str, RobotsRules] = {}

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        rules = self._rules.get(origin)
        if rules is None:
            robots_url = f"{origin}/robots.txt"
            try:
                resp = self._client.get(robots_url, timeout=10)
                # No robots.txt, or unreachable in a way that isn't a hard
                # block — treat as allow-all per RFC convention.
                text = resp.text if resp.status_code == 200 else ""
            except httpx.HTTPError:
                text = ""
            rules = RobotsRules(text, self._user_agent)
            self._rules[origin] = rules
        return rules.can_fetch(url)


def _find_archived(raw_dir: Path, source_system: str, sha256: str) -> Path | None:
    """Locate a previously archived body by its content hash. The extension
    varies with content-type, so match on the stem.
    """
    if not sha256:
        return None
    out_dir = raw_dir / source_system
    if not out_dir.is_dir():
        return None
    for candidate in out_dir.glob(f"{sha256}.*"):
        if candidate.is_file():
            return candidate
    return None


def _archive_raw(raw_dir: Path, source_system: str, sha256: str, content_type: str | None, body: bytes) -> Path:
    ext = (mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else None) or ".bin"
    out_dir = raw_dir / source_system
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{sha256}{ext}"
    if not out_path.exists():
        out_path.write_bytes(body)
    return out_path


class PipelineHTTPClient:
    """One instance per module run. Wraps httpx.Client with robots checking,
    rate limiting, conditional requests and provenance capture/archiving.
    """

    def __init__(
        self,
        source_system: str,
        settings: Settings | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.source_system = source_system
        self.settings = settings or get_settings()
        self.conn = conn
        self._client = httpx.Client(
            headers={"User-Agent": self.settings.user_agent},
            follow_redirects=True,
            timeout=30.0,
        )
        self._rate_limiter = _RateLimiter(self.settings)
        self._robots = _RobotsCache(self._client, self.settings.user_agent)
        self._overrides_recorded: set[str] = set()

    def __enter__(self) -> "PipelineHTTPClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def set_basic_auth(self, username: str, password: str = "") -> None:
        """HTTP basic auth for sources that authenticate that way (Companies
        House passes the API key as the username with an empty password).
        Credentials live on the httpx client, so they are never captured into
        provenance or written to the raw archive.
        """
        self._client.auth = httpx.BasicAuth(username, password)

    def set_default_headers(self, headers: dict[str, str]) -> None:
        """Headers applied to every request from this client — used for
        subscription-key auth (CQC, Charity Commission). Set here rather than
        passed per-call so a key cannot leak into a logged request URL.
        """
        self._client.headers.update(headers)

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=_wait_respecting_retry_after,
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _do_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        response = self._client.request(method, url, **kwargs)
        if response.status_code >= 500 or response.status_code == 429:
            response.raise_for_status()
        return response

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        use_conditional: bool = True,
        archive: bool = True,
    ) -> FetchResult:
        if not self._robots.can_fetch(url):
            # A configured exception does not make the fetch invisible. It is
            # logged every time and recorded once per (module, prefix) in the
            # review queue, so an override can never end up being the quiet
            # default — see Settings.robots_exceptions for the reasoning that
            # has to accompany each entry.
            override = self.settings.robots_override_for(url)
            if override is None:
                raise RobotsDisallowed(
                    f"robots.txt disallows fetching {url} as {self.settings.user_agent!r}")
            log.warning("http.robots_override", url=url, allowed_by=override,
                        source_system=self.source_system)
            if self.conn is not None and override not in self._overrides_recorded:
                self._overrides_recorded.add(override)
                db.record_review_item(
                    self.conn, self.source_system, "robots_override_in_use", override,
                    json.dumps({"note": "robots.txt disallows this prefix; fetched under an "
                                        "explicit exception in Settings.robots_exceptions",
                                "user_agent": self.settings.user_agent}))

        host = urlparse(url).netloc
        self._rate_limiter.wait(host)

        # Resolve the full request URL (with query params) up front so
        # provenance and the conditional-request cache key reflect the
        # exact resource fetched, not just the base endpoint.
        request_url = str(httpx.URL(url, params=params)) if params else url

        request_headers = dict(headers or {})
        cached = db.get_http_cache(self.conn, request_url) if (self.conn and use_conditional) else None
        if cached:
            if cached["etag"]:
                request_headers["If-None-Match"] = cached["etag"]
            if cached["last_modified"]:
                request_headers["If-Modified-Since"] = cached["last_modified"]

        log.info("http.get", url=request_url, source_system=self.source_system)
        response = self._do_request("GET", url, params=params, headers=request_headers)
        retrieved_at = datetime.now(timezone.utc)

        not_modified = response.status_code == 304
        archived_path = None

        if not_modified:
            # A 304 means "unchanged since you last fetched it" — the caller
            # still needs the content. Serve the archived copy rather than
            # handing back an empty body, which callers would otherwise read
            # as "this document has no content" and silently record as zero
            # rows. If the archive is missing, re-fetch unconditionally: a
            # cache entry without its payload is not a usable cache hit.
            sha256 = cached["payload_sha256"] if cached else ""
            archived_path = _find_archived(self.settings.raw_archive_dir, self.source_system, sha256)
            if archived_path is not None:
                body = archived_path.read_bytes()
            else:
                log.info("http.cache_miss_refetch", url=request_url, source_system=self.source_system)
                response = self._do_request("GET", url, params=params, headers=dict(headers or {}))
                retrieved_at = datetime.now(timezone.utc)
                not_modified = False
                body = response.content
                sha256 = hashlib.sha256(body).hexdigest() if body else ""
                if archive and body:
                    archived_path = _archive_raw(
                        self.settings.raw_archive_dir, self.source_system, sha256,
                        response.headers.get("content-type"), body,
                    )
        else:
            body = response.content
            sha256 = hashlib.sha256(body).hexdigest() if body else ""
            if archive and body:
                archived_path = _archive_raw(
                    self.settings.raw_archive_dir, self.source_system, sha256,
                    response.headers.get("content-type"), body,
                )

        if self.conn is not None:
            db.set_http_cache(
                self.conn,
                url=request_url,
                host=host,
                etag=response.headers.get("etag"),
                last_modified=response.headers.get("last-modified"),
                payload_sha256=sha256,
            )

        return FetchResult(
            url=request_url,
            status_code=response.status_code,
            body=body,
            headers=response.headers,
            retrieved_at=retrieved_at,
            payload_sha256=sha256,
            not_modified=not_modified,
            archived_path=archived_path,
        )
