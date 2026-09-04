"""Optional Scrapy transport (scrapy.md Phase 0/1).

An experimental, disabled-by-default second implementation of
`pipeline.transports.types.TransportResult`, built on Scrapy instead of
httpx. Nothing in this codebase imports this module at start-up — not
`pipeline/http.py`, not `pipeline/registry.py`, not `pipeline/runner.py`, not
any `pipeline/modules/*` file — so a normal `uv sync` and a normal collection
run never touch Scrapy or Twisted at all. Two separate gates stand between
"the package is on disk" and "a request goes out":

  * `Settings.scrapy_enabled` (off by default) — `fetch_via_scrapy()` refuses
    to run while it is False, so having `uv sync --extra scrapy` installed is
    never enough on its own.
  * Nothing currently *calls* `fetch_via_scrapy()` from a production module.
    Phase 1 explicitly stops here; wiring a module to select this transport
    is a later, separately reviewed task (scrapy.md Phase 2+).

**Why a subprocess.** Twisted's reactor can be started (`CrawlerProcess.start()`)
exactly once per Python process — a second call anywhere in that process
raises `ReactorNotRestartable`. This runner has to be callable more than
once from a single long-lived process (this test suite calls it from several
tests; a future admin route would call it more than once across the life of
the web server), so each call runs its crawl in a fresh `spawn`-context
subprocess rather than in the caller's own interpreter. That also gives the
"bounded page/context counts and memory monitoring" operational note
something concrete to stand on: the crawl's memory is released when the
subprocess exits, and a stuck crawl is killed by `scrapy_runner_timeout_seconds`
rather than hanging the caller.

One consequence worth being explicit about: state that exists only in the
calling process — a monkeypatched resolver, a mocked HTTP transport — is not
visible inside the subprocess, because it is a fresh interpreter. Tests that
need to steer DNS resolution here do it with a literal IP in the URL
(`http://127.0.0.1:<port>/`), which needs no lookup at all rather than
patching `pipeline.netguard.DEFAULT_RESOLVER`; tests of the destination
guard's *decision logic* call the middleware directly instead of running a
crawl, for the same reason `pipeline/http.py`'s own robots parser is unit
tested directly rather than only through a live client.

**What this is not yet.** This is the "minimal runner" of scrapy.md Phase 1:
one bounded list of URLs in, one `TransportResult` per URL out, no link
following, no Items, no item pipeline, no staging tables. The
"Conventional Scrapy items and pipelines" and "Persistence strategy" sections
of scrapy.md describe Phase 2+ work once a real crawl-heavy module is chosen
to migrate.

**Robots and destination-guard parity.** The downloader middleware below
re-uses `pipeline.http.RobotsRules` (the RFC 9309 wildcard-aware parser) and
`pipeline.netguard.check_url` directly, rather than Scrapy's own
`RobotsTxtMiddleware` (which is disabled here). Two independent robots
interpretations for the same host would be a second thing to keep in sync
and a second place for the "we honour robots.txt" claim to quietly stop
being true; reusing the already-correct implementation removes that risk
entirely, at the cost of a blocking `httpx` call to fetch `robots.txt` inside
`process_request` (see `RobotsComplianceMiddleware`) — acceptable for a
bounded handful of requests, and the thing to revisit before a real
crawl-heavy module moves onto this path.
"""
from __future__ import annotations

import hashlib
import io
import multiprocessing
from datetime import datetime, timezone
from queue import Empty
from typing import Sequence
from urllib.parse import urlparse

import httpx
import structlog

from pipeline.archive import get_archive
from pipeline.config import Settings
from pipeline.http import RobotsRules
from pipeline.netguard import BlockedAddress, check_url
from pipeline.transports.types import FailureClass, TransportResult

log = structlog.get_logger()


class ScrapyNotInstalled(RuntimeError):
    """The `scrapy` extra is not installed (`uv sync --extra scrapy`)."""


class ScrapyDisabled(RuntimeError):
    """`Settings.scrapy_enabled` is False.

    Raised rather than silently falling back to HTTPX: scrapy.md is explicit
    that a source must never select an alternate transport merely because a
    person or a caller put a URL in a field, and a runner that fell back
    quietly would make that true by accident.
    """


def available() -> bool:
    """Whether the `scrapy` extra is importable. Checked, never assumed —
    the same convention as `pipeline.ocr.available()` for the `ocr` extra.
    """
    try:
        import scrapy  # noqa: F401
    except ImportError:
        return False
    return True


def fetch_via_scrapy(
    urls: Sequence[str],
    *,
    source_system: str,
    settings: Settings,
    module: str | None = None,
    guard_destination: bool = False,
    resolver=None,
) -> list[TransportResult]:
    """Fetch a bounded list of URLs through Scrapy, one crawl per call.

    Returns exactly one `TransportResult` per distinct URL in `urls`,
    regardless of how the crawl went — including a runner timeout or a
    subprocess crash, both of which are reported as an explicit failure for
    every URL that has no result rather than left as a silent gap. See the
    module docstring for why this runs in a subprocess.

    `guard_destination` and `resolver` carry the same meaning as on
    `PipelineHTTPClient`: off by default (a module fetches addresses it
    discovered from a published page), on for a caller taking a URL from a
    person. `resolver` only affects a hostname that needs a DNS lookup — a
    literal IP in the URL resolves without one, which is how tests exercise
    the guard without needing the child process to see a patched resolver.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled(
            "SCRAPY_ENABLED is False. This is the deliberate default — set "
            "it explicitly (and install `uv sync --extra scrapy`) before "
            "calling fetch_via_scrapy()."
        )
    if not available():
        raise ScrapyNotInstalled(
            "The `scrapy` extra is not installed. Run `uv sync --extra scrapy`."
        )

    # Bounded and de-duplicated: this is a fixed list of requests, not a
    # crawl that discovers more of itself, and fetching the same URL twice
    # in one call would just be two archive lookups of the same bytes.
    requested = list(dict.fromkeys(urls))
    if not requested:
        return []

    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_bounded_crawl,
        args=(queue, requested, source_system, module, settings,
              guard_destination, resolver),
    )
    log.info("scrapy.runner_starting", source_system=source_system, module=module,
              urls=len(requested))
    process.start()
    process.join(settings.scrapy_runner_timeout_seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(5)
        log.warning("scrapy.runner_timeout", source_system=source_system, module=module,
                     urls=len(requested), timeout=settings.scrapy_runner_timeout_seconds)

    results: list[TransportResult] = []
    for _ in requested:
        try:
            results.append(queue.get(timeout=2))
        except Empty:
            break

    # Every requested URL gets a result. A timed-out or crashed subprocess
    # otherwise leaves a gap that looks, to a caller counting responses,
    # exactly like a source that published nothing — which is the one
    # outcome scrapy.md's design constraints rule out explicitly.
    seen = {result.requested_url for result in results}
    now = datetime.now(timezone.utc)
    for url in requested:
        if url in seen:
            continue
        if timed_out:
            detail = (f"Scrapy runner did not finish within "
                       f"{settings.scrapy_runner_timeout_seconds}s")
            failure_class = FailureClass.TIMEOUT
        else:
            detail = ("Scrapy runner exited without a result for this URL "
                       f"(exit code {process.exitcode})")
            failure_class = FailureClass.UNRECOGNISED
        results.append(TransportResult(
            transport="scrapy", source_system=source_system, module=module,
            requested_url=url, retrieved_at=now, ok=False,
            failure_class=failure_class, failure_detail=detail,
        ))

    log.info("scrapy.runner_finished", source_system=source_system, module=module,
              urls=len(requested), ok=sum(1 for r in results if r.ok),
              failed=sum(1 for r in results if not r.ok))
    return results


def _run_bounded_crawl(queue, urls, source_system, module, settings: Settings,
                        guard_destination: bool, resolver) -> None:
    """Runs inside the spawned subprocess: a fresh interpreter, so there is
    no Twisted reactor state, monkeypatch, or mock left over from whatever
    else the calling process was doing.
    """
    try:
        from scrapy.crawler import CrawlerProcess

        crawler_settings = {
            "LOG_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
            # Scrapy's own robots middleware is protego-based; this project's
            # RobotsComplianceMiddleware below re-uses pipeline.http.RobotsRules
            # instead, so there is exactly one robots interpretation shared
            # with the HTTPX transport. See the module docstring.
            "ROBOTSTXT_OBEY": False,
            "COOKIES_ENABLED": False,
            # Phase 1 is a minimal bounded runner, not a parity implementation
            # of PipelineHTTPClient's tenacity retry/backoff policy. A source
            # migrated onto this transport (Phase 2+) is exactly where a
            # measured retry policy belongs.
            "RETRY_ENABLED": False,
            "AUTOTHROTTLE_ENABLED": False,
            "USER_AGENT": settings.user_agent,
            "DOWNLOAD_TIMEOUT": settings.scrapy_download_timeout_seconds,
            "DOWNLOAD_DELAY": settings.scrapy_download_delay_seconds,
            "CONCURRENT_REQUESTS_PER_DOMAIN": settings.scrapy_concurrent_requests_per_domain,
            "DOWNLOADER_MIDDLEWARES": {
                "pipeline.transports.scrapy_transport.StructuredLoggingMiddleware": 100,
                "pipeline.transports.scrapy_transport.RobotsComplianceMiddleware": 200,
                "pipeline.transports.scrapy_transport.DestinationGuardMiddleware": 250,
                "pipeline.transports.scrapy_transport.ProvenanceArchiveMiddleware": 900,
            },
            "PIPELINE_SETTINGS": settings,
            "PIPELINE_GUARD_DESTINATION": guard_destination,
            "PIPELINE_RESOLVER": resolver,
        }
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(
            _spider_class(), urls=urls, source_system=source_system,
            module=module, result_queue=queue,
        )
        process.start()
    except Exception as exc:  # noqa: BLE001 - reported per URL, not swallowed
        # Something failed before (or outside) any per-request handling —
        # a bad setting, an import error, a crawler-startup failure. Every
        # requested URL still gets an explicit result rather than the caller
        # seeing an empty queue it could mistake for "nothing was fetched".
        now = datetime.now(timezone.utc)
        for url in urls:
            queue.put(TransportResult(
                transport="scrapy", source_system=source_system, module=module,
                requested_url=url, retrieved_at=now, ok=False,
                failure_class=FailureClass.UNRECOGNISED,
                failure_detail=f"{type(exc).__name__}: {exc}",
            ))


class StructuredLoggingMiddleware:
    """`log.info("scrapy.<event>", ...)` for every request/exception —
    CLAUDE.md's "structured logging only" applied to this transport.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        log.info("scrapy.request", url=request.url, source_system=spider.source_system,
                  module=spider.module)
        return None

    def process_exception(self, request, exception, spider):
        log.warning("scrapy.exception", url=request.url, source_system=spider.source_system,
                     module=spider.module, error=f"{type(exception).__name__}: {exception}")
        return None


class RobotsComplianceMiddleware:
    """robots.txt compliance via `pipeline.http.RobotsRules`, not Scrapy's own.

    See the module docstring for why: this project's parser understands the
    wildcard rules (`*/feed/*`) that `urllib.robotparser` — and, separately,
    Scrapy's bundled `protego` — do not treat identically, and "we honour
    robots.txt" needs to mean the same thing on every transport.
    """

    def __init__(self, pipeline_settings: Settings) -> None:
        self._settings = pipeline_settings
        self._rules_cache: dict[str, RobotsRules] = {}
        self._client = httpx.Client(timeout=10.0)

    @classmethod
    def from_crawler(cls, crawler):
        from scrapy import signals

        mw = cls(crawler.settings.get("PIPELINE_SETTINGS"))
        crawler.signals.connect(mw._closed, signal=signals.spider_closed)
        return mw

    def _closed(self, spider) -> None:
        self._client.close()

    def _rules_for(self, url: str) -> RobotsRules:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        rules = self._rules_cache.get(origin)
        if rules is None:
            try:
                response = self._client.get(
                    f"{origin}/robots.txt",
                    headers={"User-Agent": self._settings.user_agent},
                )
                text = response.text if response.status_code == 200 else ""
            except httpx.HTTPError:
                text = ""
            rules = RobotsRules(text, self._settings.user_agent)
            self._rules_cache[origin] = rules
        return rules

    def process_request(self, request, spider):
        from scrapy.exceptions import IgnoreRequest

        if self._rules_for(request.url).can_fetch(request.url):
            return None

        override = self._settings.robots_override_for(request.url)
        if override is not None:
            log.warning("scrapy.robots_override", url=request.url, allowed_by=override,
                         source_system=spider.source_system, module=spider.module)
            return None

        detail = (f"robots.txt disallows fetching {request.url} as "
                  f"{self._settings.user_agent!r}")
        log.info("scrapy.robots_disallowed", url=request.url,
                  source_system=spider.source_system, module=spider.module)
        request.meta["failure_class"] = FailureClass.ROBOTS_DISALLOWED
        request.meta["failure_detail"] = detail
        raise IgnoreRequest(detail)


class DestinationGuardMiddleware:
    """The same SSRF guard `pipeline/netguard.py` applies to
    `web/resolve.py` and `promote.py` — off by default, exactly as on
    `PipelineHTTPClient`, and only worth turning on for a caller handing this
    transport a URL that came from a person rather than a published page.
    """

    def __init__(self, guard_destination: bool, resolver) -> None:
        self._guard_destination = guard_destination
        self._resolver = resolver

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            bool(crawler.settings.get("PIPELINE_GUARD_DESTINATION", False)),
            crawler.settings.get("PIPELINE_RESOLVER"),
        )

    def process_request(self, request, spider):
        if not self._guard_destination:
            return None
        from scrapy.exceptions import IgnoreRequest

        try:
            check_url(request.url, self._resolver)
        except BlockedAddress as exc:
            log.warning("scrapy.blocked_destination", url=request.url,
                         source_system=spider.source_system, module=spider.module,
                         reason=str(exc))
            request.meta["failure_class"] = FailureClass.BLOCKED_DESTINATION
            request.meta["failure_detail"] = str(exc)
            raise IgnoreRequest(str(exc)) from exc
        return None


class ProvenanceArchiveMiddleware:
    """Archives the exact response bytes and stamps retrieval provenance.

    Runs last (highest priority number) among this project's middlewares, so
    it only ever sees a response that robots/guard did not already refuse.
    Stamped onto `request.meta` rather than `response.meta`: at the point
    `process_response` runs, the engine has not yet bound `response.request`,
    so `response.meta` (which proxies to `self.request.meta`) raises. Writing
    to `request.meta` directly reaches the same dict once the spider callback
    sees it — `response.meta` and `request.meta` really are the same object.
    """

    def __init__(self, pipeline_settings: Settings) -> None:
        self._archive = get_archive(pipeline_settings)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.get("PIPELINE_SETTINGS"))

    def process_response(self, request, response, spider):
        body = response.body or b""
        retrieved_at = datetime.now(timezone.utc)
        sha256 = hashlib.sha256(body).hexdigest() if body else ""
        raw_archive_ref = None
        if body:
            content_type = response.headers.get(b"Content-Type")
            content_type = content_type.decode("latin-1") if content_type else None
            archived = self._archive.put_stream(
                spider.source_system, sha256, content_type, io.BytesIO(body))
            raw_archive_ref = archived.logical_path

        request.meta["retrieved_at"] = retrieved_at
        request.meta["payload_sha256"] = sha256
        request.meta["raw_archive_ref"] = raw_archive_ref
        log.info("scrapy.response", url=request.url, final_url=response.url,
                  status=response.status, source_system=spider.source_system,
                  module=spider.module, payload_sha256=sha256,
                  raw_archive_ref=raw_archive_ref)
        return response


def _spider_class():
    """Builds the bounded-fetch spider class.

    A function rather than a module-level class so `scrapy.Spider` is
    imported only here — called exclusively from inside `_run_bounded_crawl`,
    i.e. only inside the subprocess, and only after `fetch_via_scrapy` has
    already confirmed `available()`. That keeps this module importable (for
    `available()` itself, and for the exceptions above) on a checkout that
    has not installed the `scrapy` extra at all.

    Not a crawler in the link-following sense scrapy.md's later phases mean
    by the word — this fetches a fixed list of URLs and nothing they link
    to, the "minimal runner" of Phase 1.
    """
    import scrapy

    class _BoundedFetchSpider(scrapy.Spider):
        name = "pipeline_bounded_fetch"

        def __init__(self, urls, source_system, module, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.urls = list(urls)
            self.source_system = source_system
            self.module = module
            self.result_queue = result_queue

        def _build_request(self, url: str):
            return scrapy.Request(
                url, callback=self.parse, errback=self.on_failure, dont_filter=True,
                meta={"handle_httpstatus_all": True, "pipeline_requested_url": url},
            )

        async def start(self):
            for url in self.urls:
                yield self._build_request(url)

        def start_requests(self):
            # Scrapy < 2.13 compatibility path (scrapy.md pins `scrapy>=2.11`):
            # `start()` above is what a 2.13+ engine actually calls instead.
            for url in self.urls:
                yield self._build_request(url)

        def parse(self, response):
            requested_url = response.meta.get("pipeline_requested_url", response.url)
            retrieved_at = response.meta.get("retrieved_at") or datetime.now(timezone.utc)
            body = response.body or b""
            status = response.status

            if status >= 400:
                ok, failure_class, detail = False, FailureClass.HTTP_ERROR, f"HTTP {status}"
            elif not body:
                ok, failure_class, detail = (
                    False, FailureClass.EMPTY_RESPONSE, "response carried no body")
            else:
                ok, failure_class, detail = True, FailureClass.NONE, None

            headers = {
                key.decode("latin-1"): b",".join(values).decode("latin-1")
                for key, values in response.headers.items()
            }
            self.result_queue.put(TransportResult(
                transport="scrapy", source_system=self.source_system, module=self.module,
                requested_url=requested_url, final_url=response.url, status_code=status,
                retrieved_at=retrieved_at, ok=ok, failure_class=failure_class,
                failure_detail=detail, headers=headers, body=body,
                payload_sha256=response.meta.get("payload_sha256", ""),
                raw_archive_ref=response.meta.get("raw_archive_ref"),
                transport_meta={"scrapy_version": scrapy.__version__},
            ))

        def on_failure(self, failure):
            from scrapy.exceptions import IgnoreRequest

            request = failure.request
            exc = failure.value
            requested_url = request.meta.get("pipeline_requested_url", request.url)
            retrieved_at = datetime.now(timezone.utc)

            if isinstance(exc, IgnoreRequest):
                failure_class = request.meta.get("failure_class", FailureClass.UNRECOGNISED)
                detail = request.meta.get("failure_detail", str(exc))
            else:
                failure_class, detail = _classify_twisted_failure(exc)

            self.result_queue.put(TransportResult(
                transport="scrapy", source_system=self.source_system, module=self.module,
                requested_url=requested_url, retrieved_at=retrieved_at, ok=False,
                failure_class=failure_class, failure_detail=detail,
            ))

    return _BoundedFetchSpider


def _classify_twisted_failure(exc: BaseException) -> tuple[FailureClass, str]:
    """Twisted's own exception hierarchy, mapped onto this contract's
    smaller, transport-neutral set. Anything not named here is
    `UNRECOGNISED` rather than guessed at — the design constraint that a
    response this pipeline has not been taught to recognise must become a
    visible failure, not an empty one.
    """
    from scrapy.exceptions import DownloadTimeoutError
    from twisted.internet.error import (
        ConnectError,
        DNSLookupError,
        TCPTimedOutError,
    )
    from twisted.internet.error import (
        TimeoutError as TwistedTimeoutError,
    )

    if isinstance(exc, (TwistedTimeoutError, TCPTimedOutError, DownloadTimeoutError)):
        return FailureClass.TIMEOUT, str(exc)
    if isinstance(exc, (ConnectError, DNSLookupError)):
        return FailureClass.TRANSPORT_ERROR, str(exc)
    return FailureClass.UNRECOGNISED, f"{type(exc).__name__}: {exc}"
