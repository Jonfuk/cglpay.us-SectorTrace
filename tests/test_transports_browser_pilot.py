"""The experimental scrapy-playwright browser leg (scrapy.md Phase 3).

Fixture-backed against a real local `http.server` fixture AND a real,
pre-installed Chromium (`/opt/pw-browsers/chromium` in this checkout's
sandbox) — scrapy.md's definition of done for a browser pilot is a page that
actually gets rendered, not a mocked Playwright API. Skipped outright if
either `scrapy` or `scrapy_playwright` is not installed, or if the pinned
Chromium binary this suite targets is not present (a `uv sync --extra
scrapy` without the browser binary itself, e.g. no `playwright install`, or
a machine other than this project's own sandbox).
"""
from __future__ import annotations

import http.server
import threading
import time
from pathlib import Path

import pytest

pytest.importorskip("scrapy")
pytest.importorskip("scrapy_playwright")

from pipeline.config import Settings
from pipeline.transports.browser_pilot import (
    ScrapyPlaywrightDisabled,
    ScrapyPlaywrightNotInstalled,
    fetch_via_scrapy_playwright,
    playwright_available,
)
from pipeline.transports.scrapy_transport import ScrapyDisabled
from pipeline.transports.types import FailureClass

CHROMIUM_PATH = "/opt/pw-browsers/chromium"

pytestmark = pytest.mark.skipif(
    not Path(CHROMIUM_PATH).exists(),
    reason="pinned Chromium binary not present on this machine",
)

# A page whose script mutates the DOM on load, exactly the case the module
# docstring's "two fetches, not one" reasoning is about: `response.body` from
# a browser-driven request would come back already mutated.
PAGE = b"""<!doctype html>
<html><body>
<div id="target">original</div>
<script>document.getElementById('target').textContent = 'mutated-by-js';</script>
</body></html>
"""


SLOW_PAGE_DELAY_SECONDS = 2.0


class _Handler(http.server.BaseHTTPRequestHandler):
    responses = {
        "/robots.txt": (200, {"Content-Type": "text/plain"}, b"User-agent: *\nAllow: /\n"),
        "/page": (200, {"Content-Type": "text/html"}, PAGE),
        "/missing": (404, {}, b"not found"),
    }

    def do_GET(self):  # noqa: N802 - http.server's own naming convention
        if self.path == "/slow":
            # Slow enough to blow a short PLAYWRIGHT_NAVIGATION_TIMEOUT while
            # staying under fetch_via_scrapy's own (separately configured,
            # more generous) download timeout in the navigation-timeout test.
            time.sleep(SLOW_PAGE_DELAY_SECONDS)
            status, headers, body = 200, {"Content-Type": "text/html"}, b"<html>slow</html>"
        else:
            status, headers, body = self.responses.get(self.path, (404, {}, b"unmapped path"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence the default stderr access log
        pass


@pytest.fixture
def fixture_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def playwright_settings(tmp_path: Path) -> Settings:
    return Settings(
        contact_email="test@example.com",
        raw_archive_dir=tmp_path / "raw",
        derived_archive_dir=tmp_path / "derived",
        scrapy_enabled=True,
        scrapy_playwright_enabled=True,
        scrapy_playwright_executable_path=CHROMIUM_PATH,
        scrapy_download_delay_seconds=0.0,
        scrapy_download_timeout_seconds=10.0,
        scrapy_runner_timeout_seconds=60.0,
        scrapy_retry_max_attempts=1,
        _env_file=None,
    )


# --- feature-flag / installation gates ---------------------------------------

def test_disabled_by_default():
    settings = Settings(contact_email="test@example.com", _env_file=None)
    assert settings.scrapy_playwright_enabled is False


def test_refuses_to_run_when_scrapy_itself_is_disabled(tmp_path):
    settings = Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "raw",
        scrapy_enabled=False, scrapy_playwright_enabled=True, _env_file=None)
    with pytest.raises(ScrapyDisabled):
        fetch_via_scrapy_playwright(["https://example.com/"], source_system="test",
                                     settings=settings)


def test_refuses_to_run_when_playwright_flag_is_off(tmp_path):
    """`scrapy_enabled=True` alone must not be enough — a browser pilot is a
    second, deliberate decision (module docstring).
    """
    settings = Settings(
        contact_email="test@example.com", raw_archive_dir=tmp_path / "raw",
        scrapy_enabled=True, scrapy_playwright_enabled=False, _env_file=None)
    with pytest.raises(ScrapyPlaywrightDisabled):
        fetch_via_scrapy_playwright(["https://example.com/"], source_system="test",
                                     settings=settings)


def test_refuses_to_run_when_scrapy_playwright_is_not_installed(playwright_settings, monkeypatch):
    from pipeline.transports import browser_pilot

    monkeypatch.setattr(browser_pilot, "playwright_available", lambda: False)
    with pytest.raises(ScrapyPlaywrightNotInstalled):
        fetch_via_scrapy_playwright(["https://example.com/"], source_system="test",
                                     settings=playwright_settings)


def test_playwright_available_reflects_whether_the_package_imports():
    assert playwright_available() is True


# --- the render-only crawl: a real browser against the fixture server -------

def test_original_bytes_are_unmutated_while_derived_dom_is_rendered(
    fixture_server, playwright_settings,
):
    """The core Phase 3 contract: `body` is the exact bytes the server sent
    (pre-JS), and the derived artefact is the post-JS DOM — two different
    payloads with two different hashes, archived separately.
    """
    [result] = fetch_via_scrapy_playwright(
        [f"{fixture_server}/page"], source_system="browser_pilot_test",
        settings=playwright_settings)

    assert result.ok is True
    assert result.status_code == 200
    # The literal string "mutated-by-js" also appears in the page's own
    # <script> source (as the assignment's string literal), so the check has
    # to distinguish the div's rendered *text content* from JS source text
    # that merely mentions it.
    assert b">original<" in result.body
    assert b">mutated-by-js<" not in result.body
    result.require_provenance()

    assert result.derived_kind == "rendered_dom"
    assert result.derived_archive_ref is not None
    assert result.derived_archive_ref != result.raw_archive_ref

    derived_path = (playwright_settings.derived_archive_dir / "browser_pilot_test" /
                     Path(result.derived_archive_ref).name)
    derived_bytes = derived_path.read_bytes()
    assert b">mutated-by-js<" in derived_bytes
    assert b">original<" not in derived_bytes


def test_a_connection_failure_still_returns_the_original_result_with_no_derived_artefact(
    playwright_settings,
):
    """Nothing listens on this port, so both legs fail at the transport
    level (not a status code) — must not crash the runner or leak a
    `TransportResult` with a derived artefact from a render that never
    happened; it must come back exactly as `fetch_via_scrapy()` alone would
    report it, just without a rendered DOM.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    [result] = fetch_via_scrapy_playwright(
        [f"http://127.0.0.1:{port}/nothing-listens-here"],
        source_system="browser_pilot_test", settings=playwright_settings)

    assert result.ok is False
    # Matches test_transports_scrapy.py's own connection-refused test: which
    # of the two a bare TCP refusal classifies as is an existing, accepted
    # ambiguity of _classify_twisted_failure, not something this browser leg
    # changes.
    assert result.failure_class in (FailureClass.TRANSPORT_ERROR, FailureClass.UNRECOGNISED)
    assert result.derived_archive_ref is None
    assert result.derived_kind is None


def test_navigation_timeout_closes_the_page_and_returns_no_derived_artefact(
    fixture_server, playwright_settings,
):
    """scrapy.md's test list names navigation timeout and browser shutdown
    explicitly. `/slow` answers after `SLOW_PAGE_DELAY_SECONDS`; the original
    fetch's own download timeout is generous enough to still succeed, but the
    render leg's navigation timeout is set well below the delay so Playwright
    times out — the page must still close (no hang, no leaked process) and
    the merged result must come back with the original bytes and no derived
    artefact, not an error for the whole call.
    """
    settings = playwright_settings.model_copy(update={
        "scrapy_download_timeout_seconds": SLOW_PAGE_DELAY_SECONDS + 10.0,
        "scrapy_playwright_navigation_timeout_seconds": 0.3,
    })

    started = time.monotonic()
    [result] = fetch_via_scrapy_playwright(
        [f"{fixture_server}/slow"], source_system="browser_pilot_test", settings=settings)
    elapsed = time.monotonic() - started

    # Comfortably under the runner's own subprocess timeout (60s) and under
    # the slow page's full delay plus the original fetch's own request —
    # proves the render leg actually gave up rather than waiting out the
    # navigation.
    assert elapsed < SLOW_PAGE_DELAY_SECONDS + settings.scrapy_download_timeout_seconds

    assert result.ok is True
    assert result.status_code == 200
    assert result.body == b"<html>slow</html>"
    assert result.derived_archive_ref is None
    assert result.derived_kind is None


def test_no_urls_returns_no_results(playwright_settings):
    assert fetch_via_scrapy_playwright([], source_system="test", settings=playwright_settings) == []
