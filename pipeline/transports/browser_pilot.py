"""scrapy.md Phase 3: an experimental browser leg (scrapy-playwright) on
top of the Scrapy transport built in Phase 0/1.

Off by default, on two separate flags: `Settings.scrapy_enabled` (the
Scrapy transport itself) and `Settings.scrapy_playwright_enabled` (this
module specifically) must both be true. Nothing in this codebase calls
`fetch_via_scrapy_playwright()` — like `pipeline/transports/pilots/`, this
exists to measure and compare, not to collect. Per scrapy.md: "Use
`scrapy-playwright` only on requests that demonstrably need it" — a browser
is not a general Cloudflare bypass or an automatic fallback for a blocked
source, and nothing here adds one; a caller decides, per URL, that a page
is worth rendering, the same way scrapy.md's example
(`meta={"playwright": True}`) is written as something a spider author
chooses deliberately.

**Two fetches, not one, and why.** `scrapy-playwright`'s download handler
populates `response.body` from `page.content()` — the DOM *after* Chromium
has run the page's JavaScript — not from the original bytes the server
sent. Confirmed directly against this checkout's own pre-installed
Chromium: a page whose script mutates the DOM on load comes back from
`response.body` already mutated, identical to `page.content()`, on every
version of scrapy-playwright available to this project (0.0.48; the
installed handler discards Playwright's own `Response.body()` — the true
original bytes — after reading only its headers and status). Handing that
to `ProvenanceArchiveMiddleware` would archive the rendered DOM under
`raw_archive_ref`, exactly the mislabelling scrapy.md's "browser/derived DOM
distinction" forbids.

So `fetch_via_scrapy_playwright()` does not try to extract original bytes
from inside a single browser-driven request. It calls `fetch_via_scrapy()`
— the ordinary, no-browser transport, unmodified — for the original
response, and a second, browser-only crawl for the rendered DOM, then
merges the two by URL: the original `TransportResult` (body/payload_sha256/
raw_archive_ref exactly as `fetch_via_scrapy()` already produces and already
tests) gains `derived_archive_ref`/`derived_kind="rendered_dom"` pointing at
the rendered capture, archived separately via
`pipeline.archive.archive_derived_artifact()`. The cost is one extra request
per URL; the alternative is fighting a third-party handler's internals to
recover bytes it already discarded, which is both more fragile and — per
scrapy.md's own caution against a full rewrite that "consumes time without
improving coverage" — not what this phase asks for.

**Bounded and monitored.** `PLAYWRIGHT_MAX_CONTEXTS`/
`PLAYWRIGHT_MAX_PAGES_PER_CONTEXT` come from `Settings` (default 1/1 — one
page at a time, deliberately conservative for a pilot); `MEMUSAGE_ENABLED`
is on with `MEMUSAGE_LIMIT_MB` from `Settings`. A page is always closed, in
both the success (`parse`) and failure (`on_failure`) paths, whether or not
navigation produced a result — scrapy.md is explicit that this is not
optional.

**What this still does not do.** No retry policy on the browser leg
(`RetryWithBackoffMiddleware` is not wired in here — retrying a navigation
that partially rendered is a real design question this scaffolding phase
does not answer); no XHR/fetch response capture for pages whose data
arrives that way (scrapy.md names this as a further refinement, not a
Phase 3 requirement); no automatic decision about *which* pages need a
browser (that is Phase 3's actual measurement work, against real m09/m10
pages, once this session's network restriction lifts — see
`docs/verification/m32-scrapy-pilot-verification.md` for the analogous Phase 2 gap and
exactly what "network restriction" means here).
"""
from __future__ import annotations

import hashlib
import multiprocessing
from dataclasses import dataclass, replace
from typing import Sequence

import structlog

from pipeline.archive import archive_derived_artifact
from pipeline.config import Settings
from pipeline.transports.scrapy_transport import (
    ScrapyDisabled,
    ScrapyNotInstalled,
    available,
    drain_subprocess,
    fetch_via_scrapy,
)
from pipeline.transports.types import TransportResult

log = structlog.get_logger()


class ScrapyPlaywrightDisabled(RuntimeError):
    """`Settings.scrapy_playwright_enabled` is False.

    Distinct from `ScrapyDisabled`: a caller can have Scrapy itself enabled
    (and be using `fetch_via_scrapy()` in production) without that implying
    consent to launch a browser. Both flags are checked, and either being
    off refuses to run.
    """


class ScrapyPlaywrightNotInstalled(RuntimeError):
    """The `scrapy-playwright` package is not importable.

    It ships in the same optional `scrapy` extra as `scrapy` itself
    (`uv sync --extra scrapy` installs both), but is checked separately —
    installing the Python package is still not the same as having a browser
    binary (`playwright install`, or this checkout's pre-provisioned
    Chromium); this module cannot detect the latter without trying to
    launch one, so a launch failure surfaces as an ordinary crawl failure
    downstream rather than as this exception.
    """


def playwright_available() -> bool:
    """Whether the `scrapy-playwright` package is importable. Checked, never
    assumed — the same convention as `pipeline.ocr.available()` and
    `pipeline.transports.scrapy_transport.available()`.
    """
    try:
        import scrapy_playwright  # noqa: F401
    except ImportError:
        return False
    return True


@dataclass(frozen=True)
class RenderedCapture:
    """One URL's browser-rendered DOM, or why there isn't one."""

    requested_url: str
    final_url: str | None
    status_code: int | None
    rendered_html: str | None
    error: str | None = None


def fetch_via_scrapy_playwright(
    urls: Sequence[str],
    *,
    source_system: str,
    settings: Settings,
    module: str | None = None,
    guard_destination: bool = False,
    resolver=None,
) -> list[TransportResult]:
    """The original response for every URL (via `fetch_via_scrapy()`,
    unmodified), each carrying a rendered-DOM derived artefact where
    rendering succeeded. See the module docstring for why this is two
    fetches rather than one.

    Refuses to run unless `settings.scrapy_enabled` *and*
    `settings.scrapy_playwright_enabled` are both true, and unless both the
    `scrapy` and `scrapy-playwright` packages are importable.
    """
    if not settings.scrapy_enabled:
        raise ScrapyDisabled(
            "SCRAPY_ENABLED is False. Set it explicitly (and install "
            "`uv sync --extra scrapy`) before calling fetch_via_scrapy_playwright()."
        )
    if not settings.scrapy_playwright_enabled:
        raise ScrapyPlaywrightDisabled(
            "SCRAPY_PLAYWRIGHT_ENABLED is False. This is the deliberate default — "
            "a browser pilot is a second, explicit decision on top of SCRAPY_ENABLED."
        )
    if not available():
        raise ScrapyNotInstalled(
            "The `scrapy` extra is not installed. Run `uv sync --extra scrapy`."
        )
    if not playwright_available():
        raise ScrapyPlaywrightNotInstalled(
            "scrapy-playwright is not installed. Run `uv sync --extra scrapy`."
        )

    original_results = fetch_via_scrapy(
        urls, source_system=source_system, settings=settings, module=module,
        guard_destination=guard_destination, resolver=resolver)

    captures = _fetch_rendered_dom(
        [result.requested_url for result in original_results],
        source_system=source_system, settings=settings,
        guard_destination=guard_destination, resolver=resolver)

    merged: list[TransportResult] = []
    for result in original_results:
        capture = captures.get(result.requested_url)
        if capture is None or capture.rendered_html is None:
            merged.append(result)
            continue
        body = capture.rendered_html.encode("utf-8")
        sha256 = hashlib.sha256(body).hexdigest()
        archive_ref = archive_derived_artifact(settings, source_system, sha256,
                                                "text/html; charset=utf-8", body)
        merged.append(replace(result, derived_archive_ref=archive_ref,
                              derived_kind="rendered_dom"))
    return merged


def _fetch_rendered_dom(
    urls: Sequence[str], *, source_system: str, settings: Settings,
    guard_destination: bool, resolver,
) -> dict[str, RenderedCapture]:
    requested = list(dict.fromkeys(urls))
    if not requested:
        return {}

    ctx = multiprocessing.get_context("spawn")
    queue: multiprocessing.Queue = ctx.Queue()
    process = ctx.Process(
        target=_run_render_crawl,
        args=(queue, requested, source_system, settings, guard_destination, resolver),
    )
    log.info("scrapy.playwright_starting", source_system=source_system, urls=len(requested))
    process.start()
    items, timed_out = drain_subprocess(process, queue, settings.scrapy_runner_timeout_seconds)
    if timed_out:
        log.warning("scrapy.playwright_timeout", source_system=source_system,
                     urls=len(requested), timeout=settings.scrapy_runner_timeout_seconds)

    captures: dict[str, RenderedCapture] = {item.requested_url: item for item in items}
    for url in requested:
        if url not in captures:
            captures[url] = RenderedCapture(
                requested_url=url, final_url=None, status_code=None, rendered_html=None,
                error=("Scrapy playwright runner did not finish within "
                       f"{settings.scrapy_runner_timeout_seconds}s") if timed_out
                      else f"runner exited without a result for this URL (exit code {process.exitcode})")

    log.info("scrapy.playwright_finished", source_system=source_system, urls=len(requested),
              rendered=sum(1 for c in captures.values() if c.rendered_html is not None))
    return captures


def _run_render_crawl(queue, urls, source_system: str, settings: Settings,
                       guard_destination: bool, resolver) -> None:
    """Runs inside a spawned subprocess — same reasoning as
    `scrapy_transport._run_bounded_crawl`: Twisted's reactor can only start
    once per process, and this has to be callable more than once from a
    single long-lived caller.
    """
    try:
        from scrapy.crawler import CrawlerProcess

        launch_options: dict = {"headless": True}
        if settings.scrapy_playwright_executable_path:
            launch_options["executable_path"] = settings.scrapy_playwright_executable_path

        crawler_settings = {
            "LOG_ENABLED": False,
            "TELNETCONSOLE_ENABLED": False,
            "ROBOTSTXT_OBEY": False,
            "COOKIES_ENABLED": False,
            "RETRY_ENABLED": False,
            "AUTOTHROTTLE_ENABLED": False,
            "USER_AGENT": settings.user_agent,
            "DOWNLOAD_DELAY": settings.scrapy_download_delay_seconds,
            "CONCURRENT_REQUESTS_PER_DOMAIN": settings.scrapy_concurrent_requests_per_domain,
            # scrapy-playwright requires the asyncio reactor explicitly —
            # unlike the rest of this package, this is not merely Scrapy's
            # own 2.13+ default.
            "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
            "DOWNLOAD_HANDLERS": {
                "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
                "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            },
            "PLAYWRIGHT_BROWSER_TYPE": "chromium",
            "PLAYWRIGHT_LAUNCH_OPTIONS": launch_options,
            "PLAYWRIGHT_MAX_CONTEXTS": settings.scrapy_playwright_max_contexts,
            "PLAYWRIGHT_MAX_PAGES_PER_CONTEXT": settings.scrapy_playwright_max_pages_per_context,
            # Named PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT, not
            # PLAYWRIGHT_NAVIGATION_TIMEOUT, in the installed scrapy-playwright
            # (0.0.48) — confirmed by reading handler.py directly after a
            # fixture test with a deliberately short timeout kept succeeding:
            # the wrong key name was silently ignored and Playwright fell back
            # to its own 30s default.
            "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": int(
                settings.scrapy_playwright_navigation_timeout_seconds * 1000),
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": settings.scrapy_playwright_memory_limit_mb,
            "DOWNLOADER_MIDDLEWARES": {
                "pipeline.transports.scrapy_transport.StructuredLoggingMiddleware": 100,
                "pipeline.transports.scrapy_transport.RobotsComplianceMiddleware": 200,
                "pipeline.transports.scrapy_transport.DestinationGuardMiddleware": 250,
                # Deliberately no ProvenanceArchiveMiddleware here:
                # response.body on this crawl is the rendered DOM, not the
                # original bytes (see the module docstring) — archiving it
                # as though it were would mislabel a derived artefact as
                # source bytes. The original fetch's provenance comes from
                # the separate fetch_via_scrapy() call in
                # fetch_via_scrapy_playwright(). No RetryWithBackoffMiddleware
                # either — retrying a browser navigation is out of scope for
                # this scaffolding phase (see the module docstring).
            },
            "PIPELINE_SETTINGS": settings,
            "PIPELINE_GUARD_DESTINATION": guard_destination,
            "PIPELINE_RESOLVER": resolver,
        }
        process = CrawlerProcess(settings=crawler_settings, install_root_handler=False)
        process.crawl(_spider_class(), urls=urls, source_system=source_system, result_queue=queue)
        process.start()
    except Exception as exc:  # noqa: BLE001 - reported per URL, not swallowed
        for url in urls:
            queue.put(RenderedCapture(
                requested_url=url, final_url=None, status_code=None, rendered_html=None,
                error=f"{type(exc).__name__}: {exc}"))


def _spider_class():
    """Builds the render-only spider class — see
    `scrapy_transport._spider_class` for why this is a function rather than
    a module-level class.
    """
    import scrapy

    class _RenderOnlySpider(scrapy.Spider):
        name = "pipeline_render_only"

        def __init__(self, urls, source_system, result_queue, **kwargs):
            super().__init__(**kwargs)
            self.urls = list(urls)
            self.source_system = source_system
            self.module = None
            self.result_queue = result_queue

        def _build_request(self, url: str):
            return scrapy.Request(
                url, callback=self.parse, errback=self.on_failure, dont_filter=True,
                meta={"playwright": True, "playwright_include_page": True,
                      "handle_httpstatus_all": True, "pipeline_requested_url": url},
            )

        async def start(self):
            for url in self.urls:
                yield self._build_request(url)

        def start_requests(self):
            # Scrapy < 2.13 compatibility path, as in _BoundedFetchSpider.
            for url in self.urls:
                yield self._build_request(url)

        async def parse(self, response):
            requested_url = response.meta.get("pipeline_requested_url", response.url)
            page = response.meta.get("playwright_page")
            rendered_html = None
            try:
                if page is not None:
                    rendered_html = await page.content()
            finally:
                # Always closed — success or failure to read content —
                # scrapy.md: "Browser pages must always close in success
                # and error paths."
                if page is not None and not page.is_closed():
                    await page.close()

            self.result_queue.put(RenderedCapture(
                requested_url=requested_url, final_url=response.url,
                status_code=response.status, rendered_html=rendered_html))

        async def on_failure(self, failure):
            request = failure.request
            requested_url = request.meta.get("pipeline_requested_url", request.url)
            page = request.meta.get("playwright_page")
            if page is not None and not page.is_closed():
                await page.close()
            self.result_queue.put(RenderedCapture(
                requested_url=requested_url, final_url=None, status_code=None,
                rendered_html=None, error=f"{type(failure.value).__name__}: {failure.value}"))

    return _RenderOnlySpider
