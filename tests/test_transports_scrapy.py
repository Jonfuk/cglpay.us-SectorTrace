"""The optional Scrapy transport (scrapy.md Phase 0/1).

Most assertions here call the downloader middleware classes directly —
`process_request`/`process_response` with a hand-built `scrapy.Request`/
`Response`, no reactor, no subprocess — the same pattern
`pipeline.http.RobotsRules` is unit tested with directly rather than only
through a live client. A handful of tests run a real bounded crawl against a
local, in-process fixture HTTP server, because scrapy.md's definition of done
asks for at least one fetch that actually went through Scrapy's engine.

Everything here is skipped outright if the `scrapy` extra is not installed —
it is optional, and this file must not turn "not installed" into a failing
suite.
"""
from __future__ import annotations

import asyncio
import gzip
import hashlib
import http.server
import threading
from pathlib import Path

import pytest

pytest.importorskip("scrapy")

from pipeline.config import Settings
from pipeline.transports.scrapy_transport import (
    DestinationGuardMiddleware,
    ProvenanceArchiveMiddleware,
    RetryWithBackoffMiddleware,
    RobotsComplianceMiddleware,
    ScrapyDisabled,
    ScrapyNotInstalled,
    available,
    fetch_via_scrapy,
)
from pipeline.transports.types import FailureClass


def _run(coro):
    """Run a coroutine returned by an `async def` middleware method from a
    plain (sync) test function — no pytest-asyncio dependency needed for the
    handful of call sites that exercise `process_request`/`process_response`/
    `process_exception` directly.
    """
    return asyncio.run(coro)

# --- a local, in-process fixture server --------------------------------------
#
# A real socket on loopback, not a mock: scrapy.md explicitly asks for
# fixture-backed tests "using a local in-process fixture server or mocked
# downloader", and the subprocess runner (see scrapy_transport.py's module
# docstring for why it is a subprocess) cannot see a monkeypatched httpx
# transport running in the test process anyway — a real socket is the one
# thing that reaches it.

class _Handler(http.server.BaseHTTPRequestHandler):
    responses = {
        "/robots.txt": (200, {}, b"User-agent: *\nAllow: /\n"),
        "/ok": (200, {"Content-Type": "text/plain"}, b"hello from the fixture server"),
        "/gzip": (
            200,
            {"Content-Type": "text/plain", "Content-Encoding": "gzip"},
            gzip.compress(b"decoded fixture response"),
        ),
        "/missing": (404, {}, b"not found"),
        "/empty": (200, {}, b""),
    }

    def do_GET(self):  # noqa: N802 - http.server's own naming convention
        status, headers, body = self.responses.get(self.path, (404, {}, b"unmapped path"))
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence the default stderr access log
        pass


class _DisallowingHandler(_Handler):
    responses = {
        **_Handler.responses,
        "/robots.txt": (200, {}, b"User-agent: *\nDisallow: /secret\n"),
        "/secret": (200, {}, b"should never be fetched"),
    }


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
def robots_disallowing_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _DisallowingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def scrapy_settings(tmp_path: Path) -> Settings:
    """Settings for the Scrapy transport only — this runner takes no database
    connection in Phase 1 unless a robots override actually fires (see
    `test_robots_override_writes_a_review_item`, which uses the Postgres-backed
    `settings`/`conn` fixtures instead), so unlike those this does not need the
    warehouse at all. `raw_archive_dir` is the only writable path involved,
    and it is under `tmp_path`.
    """
    return Settings(
        contact_email="test@example.com",
        raw_archive_dir=tmp_path / "raw",
        scrapy_enabled=True,
        # No politeness delay against a fixture on loopback — parallels why
        # the shared `settings` fixture zeroes `default_rate_limit_seconds`.
        scrapy_download_delay_seconds=0.0,
        scrapy_download_timeout_seconds=5.0,
        scrapy_runner_timeout_seconds=30.0,
        # One attempt, no retries: tests of a genuine, permanent failure
        # (connection refused, a hung server) care about the *classification*,
        # not about sitting through RetryWithBackoffMiddleware's backoff
        # first. The retry tests below override this explicitly.
        scrapy_retry_max_attempts=1,
        _env_file=None,
    )


def _make_flaky_handler(fail_times: int):
    """A handler that answers `/flaky` with 503 `fail_times` times, then 200.

    State lives in a plain dict closed over by the class, not a class
    attribute, so two tests using this factory never share a counter.
    """
    state = {"count": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path == "/robots.txt":
                status, body = 200, b"User-agent: *\nAllow: /\n"
            elif self.path == "/flaky":
                state["count"] += 1
                status, body = ((503, b"try again") if state["count"] <= fail_times
                                 else (200, b"third time lucky"))
            else:
                status, body = 404, b"unmapped path"
            self.send_response(status)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler, state


@pytest.fixture
def flaky_server():
    """`(base_url, state)` for a server whose `/flaky` path fails twice then
    succeeds. `state["count"]` is readable after the crawl: the server runs
    on a thread in this test process, and only the Scrapy crawl itself runs
    in the spawned subprocess, so the parent process's view of `state` is
    exactly what the subprocess's requests produced.
    """
    handler_cls, state = _make_flaky_handler(fail_times=2)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def always_failing_server():
    """`(base_url, state)` for a server whose `/flaky` path always fails —
    for proving retries give up rather than looping forever.
    """
    handler_cls, state = _make_flaky_handler(fail_times=10_000)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        thread.join(timeout=5)


# --- feature-flag / installation gates ---------------------------------------

def test_disabled_by_default():
    """`Settings()` defaults to `scrapy_enabled=False` — this is the
    off-by-default guarantee the whole feature rests on, checked without
    even touching the runner's other machinery.
    """
    settings = Settings(contact_email="test@example.com", _env_file=None)
    assert settings.scrapy_enabled is False


def test_fetch_refuses_to_run_while_disabled(tmp_path):
    settings = Settings(contact_email="test@example.com",
                         raw_archive_dir=tmp_path / "raw", _env_file=None)
    assert settings.scrapy_enabled is False
    with pytest.raises(ScrapyDisabled):
        fetch_via_scrapy(["https://example.com/"], source_system="test", settings=settings)


def test_fetch_refuses_to_run_when_scrapy_is_not_installed(scrapy_settings, monkeypatch):
    from pipeline.transports import scrapy_transport

    monkeypatch.setattr(scrapy_transport, "available", lambda: False)
    with pytest.raises(ScrapyNotInstalled):
        fetch_via_scrapy(["https://example.com/"], source_system="test",
                          settings=scrapy_settings)


def test_available_reflects_whether_the_package_imports():
    # This whole file is skipped via importorskip when it does not, so by the
    # time this line runs the answer must be True.
    assert available() is True


def test_module_never_imports_scrapy_or_playwright_at_top_level():
    """`uv sync` (no `--extra scrapy`) must still leave this file importable
    — it is not wired into any code path a normal install exercises, but
    nothing should stop `import pipeline.transports.scrapy_transport` from
    working if some future caller imports it defensively. A module-level
    `import scrapy` would break that; a `scrapy_playwright` import anywhere
    would pull in a browser-automation dependency this phase never asked
    for.
    """
    import ast

    from pipeline.transports import scrapy_transport

    source = Path(scrapy_transport.__file__).read_text()
    assert "playwright" not in source.lower()

    tree = ast.parse(source)
    for node in tree.body:  # module-level statements only, not inside functions
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
            assert "scrapy" not in names, "scrapy must only be imported lazily"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "scrapy" and not (node.module or "").startswith("scrapy.")


# --- the bounded runner: a real crawl against the fixture server -------------

def test_fixture_fetch_records_full_provenance(fixture_server, scrapy_settings):
    url = f"{fixture_server}/ok"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings,
                                 module="test_module")

    assert result.transport == "scrapy"
    assert result.ok is True
    assert result.failure_class is FailureClass.NONE
    assert result.requested_url == url
    assert result.final_url == url
    assert result.status_code == 200
    assert result.retrieved_at is not None
    assert result.body == b"hello from the fixture server"
    assert result.payload_sha256 == hashlib.sha256(result.body).hexdigest()
    assert result.raw_archive_ref == f"data/raw/test_scrapy/{result.payload_sha256}.txt"
    result.require_provenance()  # must not raise

    archived_path = scrapy_settings.raw_archive_dir / "test_scrapy" / f"{result.payload_sha256}.txt"
    assert archived_path.read_bytes() == result.body


def test_compressed_response_is_decoded_before_provenance(
        fixture_server, scrapy_settings):
    """Scrapy's body contract matches HTTPX's decoded ``response.content``.

    Provenance must run after HttpCompressionMiddleware; otherwise the wire
    gzip bytes receive a different hash and are archived as though they were
    the source payload returned to parsers.
    """
    url = f"{fixture_server}/gzip"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings)

    expected = b"decoded fixture response"
    assert result.ok is True
    assert result.body == expected
    assert result.payload_sha256 == hashlib.sha256(expected).hexdigest()
    archived_path = scrapy_settings.raw_archive_dir / "test_scrapy" / (
        f"{result.payload_sha256}.txt")
    assert archived_path.read_bytes() == expected


def test_http_error_is_an_explicit_failure_not_an_empty_success(fixture_server, scrapy_settings):
    url = f"{fixture_server}/missing"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.HTTP_ERROR
    assert result.status_code == 404
    # Archived exactly as a 200 body would be, matching the HTTPX path.
    assert result.payload_sha256
    assert result.raw_archive_ref
    result.require_provenance()


def test_empty_response_is_an_explicit_failure(fixture_server, scrapy_settings):
    url = f"{fixture_server}/empty"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.EMPTY_RESPONSE
    result.require_provenance()


def test_robots_disallowed_is_an_explicit_failure_and_nothing_is_archived(
        robots_disallowing_server, scrapy_settings):
    url = f"{robots_disallowing_server}/secret"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.ROBOTS_DISALLOWED
    assert result.body == b""
    assert result.raw_archive_ref is None
    result.require_provenance()  # no body was received, so this still passes

    # And nothing was written to the archive for a page that was refused.
    assert not (scrapy_settings.raw_archive_dir / "test_scrapy").exists()


def test_destination_guard_blocks_a_loopback_target_when_enabled(fixture_server, scrapy_settings):
    """Off by default (see the next test); a caller that turns it on gets
    the same refusal `PipelineHTTPClient(guard_destination=True)` would give
    for the same address — here, the fixture server's own loopback address.
    """
    url = f"{fixture_server}/ok"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings,
                                 guard_destination=True)

    assert result.ok is False
    assert result.failure_class is FailureClass.BLOCKED_DESTINATION
    result.require_provenance()


def test_destination_guard_is_off_by_default(fixture_server, scrapy_settings):
    url = f"{fixture_server}/ok"
    [result] = fetch_via_scrapy([url], source_system="test_scrapy", settings=scrapy_settings)
    assert result.ok is True


def test_connection_refused_is_an_explicit_failure(scrapy_settings):
    """Nothing is listening on this port — a genuine transport-level failure,
    not a status code. Must still produce exactly one labelled result, never
    an empty queue.
    """
    import socket

    # A bound-then-closed socket's port is very likely free for the moment
    # this test needs it, without guessing at a fixed number.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    [result] = fetch_via_scrapy([f"http://127.0.0.1:{port}/nothing-listens-here"],
                                 source_system="test_scrapy", settings=scrapy_settings)

    assert result.ok is False
    assert result.failure_class in (FailureClass.TRANSPORT_ERROR, FailureClass.UNRECOGNISED)
    result.require_provenance()


def test_timeout_is_an_explicit_failure(scrapy_settings):
    """A server that accepts the connection and then never answers must
    become `FailureClass.TIMEOUT`, not an empty result the caller could read
    as a source that published nothing.
    """
    import socket

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]

    def accept_and_hang():
        try:
            conn, _ = listener.accept()
            conn.settimeout(10)
            conn.recv(4096)  # read the request; never reply
        except OSError:
            pass

    thread = threading.Thread(target=accept_and_hang, daemon=True)
    thread.start()
    try:
        scrapy_settings.scrapy_download_timeout_seconds = 1.0
        [result] = fetch_via_scrapy([f"http://127.0.0.1:{port}/never-answers"],
                                     source_system="test_scrapy", settings=scrapy_settings)
    finally:
        listener.close()
        thread.join(timeout=5)

    assert result.ok is False
    assert result.failure_class is FailureClass.TIMEOUT
    result.require_provenance()


def test_runner_produces_a_result_for_every_requested_url(fixture_server, scrapy_settings):
    urls = [f"{fixture_server}/ok", f"{fixture_server}/missing", f"{fixture_server}/empty"]
    results = fetch_via_scrapy(urls, source_system="test_scrapy", settings=scrapy_settings)
    assert {r.requested_url for r in results} == set(urls)
    for result in results:
        result.require_provenance()


def test_no_urls_returns_no_results(scrapy_settings):
    assert fetch_via_scrapy([], source_system="test_scrapy", settings=scrapy_settings) == []


def test_source_module_metadata_travels_with_every_result(fixture_server, scrapy_settings):
    [result] = fetch_via_scrapy([f"{fixture_server}/ok"], source_system="a_source_system",
                                 settings=scrapy_settings, module="m99_example")
    assert result.source_system == "a_source_system"
    assert result.module == "m99_example"


def test_retries_recover_from_a_transient_5xx(flaky_server, scrapy_settings):
    """End-to-end proof that RetryWithBackoffMiddleware is actually wired
    into the crawl, not just correct in isolation: two 503s and then a 200
    must come back as one successful result, with the retried attempts never
    archived.
    """
    base_url, state = flaky_server
    scrapy_settings.scrapy_retry_max_attempts = 5
    scrapy_settings.scrapy_retry_backoff_min_seconds = 0.02
    scrapy_settings.scrapy_retry_backoff_max_seconds = 0.05

    [result] = fetch_via_scrapy([f"{base_url}/flaky"], source_system="test_scrapy",
                                 settings=scrapy_settings)

    assert result.ok is True
    assert result.status_code == 200
    assert result.body == b"third time lucky"
    assert state["count"] == 3, "two failures plus the succeeding attempt"
    result.require_provenance()

    # Only the final, successful body was archived — not either 503 attempt.
    archive_dir = scrapy_settings.raw_archive_dir / "test_scrapy"
    assert [p.name for p in archive_dir.iterdir()] == [f"{result.payload_sha256}.txt"]


def test_retries_give_up_after_the_configured_maximum(always_failing_server, scrapy_settings):
    base_url, state = always_failing_server
    scrapy_settings.scrapy_retry_max_attempts = 3
    scrapy_settings.scrapy_retry_backoff_min_seconds = 0.02
    scrapy_settings.scrapy_retry_backoff_max_seconds = 0.05

    [result] = fetch_via_scrapy([f"{base_url}/flaky"], source_system="test_scrapy",
                                 settings=scrapy_settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.HTTP_ERROR
    assert result.status_code == 503
    assert state["count"] == 3, "exactly scrapy_retry_max_attempts attempts, then give up"
    result.require_provenance()  # the final failed attempt's body is still archived


# --- middleware unit tests: decision logic in isolation, no reactor ---------
#
# `pipeline.http.RobotsRules` already has its own wildcard-parsing test suite
# (tests/test_http.py) — these only check that this middleware calls it and
# reacts correctly, not that the parser is correct.

class _FakeSpider:
    source_system = "test_source"
    module = "test_module"


def test_robots_middleware_allows_a_request_with_no_robots_txt(scrapy_settings, monkeypatch):
    import httpx as httpx_lib

    async def no_robots_txt(self, url, headers=None):
        raise httpx_lib.ConnectError("no such host")

    monkeypatch.setattr(httpx_lib.AsyncClient, "get", no_robots_txt)

    mw = RobotsComplianceMiddleware(scrapy_settings)
    request = _FakeRequest("https://example.invalid/page")
    assert _run(mw.process_request(request, _FakeSpider())) is None


def test_robots_middleware_raises_ignore_request_when_disallowed(scrapy_settings, monkeypatch):
    import httpx as httpx_lib
    from scrapy.exceptions import IgnoreRequest

    class _Resp:
        status_code = 200
        text = "User-agent: *\nDisallow: /blocked\n"

    async def fake_get(self, url, headers=None):
        return _Resp()

    monkeypatch.setattr(httpx_lib.AsyncClient, "get", fake_get)

    mw = RobotsComplianceMiddleware(scrapy_settings)
    request = _FakeRequest("https://example.invalid/blocked/page")
    with pytest.raises(IgnoreRequest):
        _run(mw.process_request(request, _FakeSpider()))
    assert request.meta["failure_class"] is FailureClass.ROBOTS_DISALLOWED


def test_robots_override_is_honoured_and_logged(scrapy_settings, monkeypatch):
    import httpx as httpx_lib

    class _Resp:
        status_code = 200
        text = "User-agent: *\nDisallow: /feed/\n"

    async def fake_get(self, url, headers=None):
        return _Resp()

    monkeypatch.setattr(httpx_lib.AsyncClient, "get", fake_get)
    scrapy_settings.robots_exceptions = ("https://example.invalid/feed/",)

    mw = RobotsComplianceMiddleware(scrapy_settings)
    request = _FakeRequest("https://example.invalid/feed/search.json")
    # No DATABASE_URL on `scrapy_settings`, so the review-item write this
    # override triggers fails and is swallowed (logged, not raised) — see
    # test_robots_override_writes_a_review_item below for the write itself.
    assert _run(mw.process_request(request, _FakeSpider())) is None


def test_robots_override_writes_a_review_item(settings, conn, monkeypatch):
    """The Postgres-backed path: an override must land in `review_queue`,
    the same table (and the same shape) `PipelineHTTPClient.get()` writes
    to — not a new one.
    """
    import httpx as httpx_lib

    class _Resp:
        status_code = 200
        text = "User-agent: *\nDisallow: /feed/\n"

    async def fake_get(self, url, headers=None):
        return _Resp()

    monkeypatch.setattr(httpx_lib.AsyncClient, "get", fake_get)
    settings.robots_exceptions = ("https://example.invalid/feed/",)

    mw = RobotsComplianceMiddleware(settings)
    request = _FakeRequest("https://example.invalid/feed/search.json")
    spider = _FakeSpider()
    assert _run(mw.process_request(request, spider)) is None
    _run(mw._closed(spider))

    rows = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'robots_override_in_use'").fetchall()
    assert len(rows) == 1
    assert rows[0]["raw_value"] == "https://example.invalid/feed/"
    assert rows[0]["module"] == _FakeSpider.module


def test_robots_override_is_recorded_once_per_module_and_prefix(settings, conn, monkeypatch):
    """A second request past the same override must not duplicate the
    review item — the natural key is (module, prefix), not one row per
    fetch.
    """
    import httpx as httpx_lib

    class _Resp:
        status_code = 200
        text = "User-agent: *\nDisallow: /feed/\n"

    async def fake_get(self, url, headers=None):
        return _Resp()

    monkeypatch.setattr(httpx_lib.AsyncClient, "get", fake_get)
    settings.robots_exceptions = ("https://example.invalid/feed/",)

    mw = RobotsComplianceMiddleware(settings)
    spider = _FakeSpider()
    _run(mw.process_request(_FakeRequest("https://example.invalid/feed/a"), spider))
    _run(mw.process_request(_FakeRequest("https://example.invalid/feed/b"), spider))
    _run(mw._closed(spider))

    rows = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'robots_override_in_use'").fetchall()
    assert len(rows) == 1


def test_destination_guard_middleware_off_by_default():
    mw = DestinationGuardMiddleware(guard_destination=False, resolver=None)
    request = _FakeRequest("http://127.0.0.1/anything")
    assert mw.process_request(request, _FakeSpider()) is None


def test_destination_guard_middleware_blocks_private_space_when_enabled():
    from scrapy.exceptions import IgnoreRequest

    mw = DestinationGuardMiddleware(guard_destination=True, resolver=None)
    request = _FakeRequest("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(IgnoreRequest):
        mw.process_request(request, _FakeSpider())
    assert request.meta["failure_class"] is FailureClass.BLOCKED_DESTINATION


def test_destination_guard_middleware_allows_a_public_literal_when_enabled():
    mw = DestinationGuardMiddleware(guard_destination=True, resolver=None)
    request = _FakeRequest("http://93.184.216.34/")
    assert mw.process_request(request, _FakeSpider()) is None


def test_provenance_middleware_archives_and_stamps_meta(scrapy_settings):
    mw = ProvenanceArchiveMiddleware(scrapy_settings)
    request = _FakeRequest("https://example.invalid/page")
    response = _FakeResponse(request, status=200, body=b"payload bytes",
                              headers={b"Content-Type": b"text/plain"})

    returned = mw.process_response(request, response, _FakeSpider())

    assert returned is response
    sha256 = hashlib.sha256(b"payload bytes").hexdigest()
    assert request.meta["payload_sha256"] == sha256
    assert request.meta["raw_archive_ref"] == f"data/raw/test_source/{sha256}.txt"
    assert request.meta["retrieved_at"] is not None
    archived = scrapy_settings.raw_archive_dir / "test_source" / f"{sha256}.txt"
    assert archived.read_bytes() == b"payload bytes"


def test_provenance_middleware_does_not_archive_an_empty_body(scrapy_settings):
    mw = ProvenanceArchiveMiddleware(scrapy_settings)
    request = _FakeRequest("https://example.invalid/empty")
    response = _FakeResponse(request, status=200, body=b"", headers={})

    mw.process_response(request, response, _FakeSpider())

    assert request.meta["payload_sha256"] == ""
    assert request.meta["raw_archive_ref"] is None
    assert not (scrapy_settings.raw_archive_dir / "test_source").exists()


def _retry_settings(**overrides) -> Settings:
    fields = dict(contact_email="test@example.com", scrapy_retry_max_attempts=3,
                  scrapy_retry_backoff_min_seconds=1.0, scrapy_retry_backoff_max_seconds=8.0,
                  _env_file=None)
    fields.update(overrides)
    return Settings(**fields)


def test_delay_seconds_backs_off_exponentially_within_its_bounds():
    mw = RetryWithBackoffMiddleware(_retry_settings())
    assert mw._delay_seconds(1, None) == 1.0
    assert mw._delay_seconds(2, None) == 2.0
    assert mw._delay_seconds(3, None) == 4.0
    assert mw._delay_seconds(4, None) == 8.0
    assert mw._delay_seconds(5, None) == 8.0  # clamped at the maximum


def test_delay_seconds_honours_a_numeric_retry_after_header():
    # Backoff bounds deliberately far from the header value, so the
    # assertion can only pass if Retry-After actually took precedence.
    mw = RetryWithBackoffMiddleware(_retry_settings(scrapy_retry_backoff_min_seconds=10.0,
                                                      scrapy_retry_backoff_max_seconds=20.0))
    assert mw._delay_seconds(1, "0.5") == 0.5


def test_delay_seconds_falls_back_to_backoff_for_an_unparseable_retry_after():
    mw = RetryWithBackoffMiddleware(_retry_settings())
    assert mw._delay_seconds(1, "Wed, 21 Oct 2026 07:28:00 GMT") == 1.0


def test_retry_middleware_retries_a_retryable_status():
    import scrapy

    mw = RetryWithBackoffMiddleware(_retry_settings(scrapy_retry_backoff_min_seconds=0.01,
                                                      scrapy_retry_backoff_max_seconds=0.02))
    request = _FakeRequest("https://example.invalid/flaky")
    response = _FakeResponse(request, status=503, body=b"try again", headers={})

    result = _run(mw.process_response(request, response, _FakeSpider()))

    assert isinstance(result, scrapy.Request)
    assert result.meta["retry_times"] == 1


def test_retry_middleware_ignores_a_non_retryable_status():
    mw = RetryWithBackoffMiddleware(_retry_settings())
    request = _FakeRequest("https://example.invalid/missing")
    response = _FakeResponse(request, status=404, body=b"not found", headers={})

    result = _run(mw.process_response(request, response, _FakeSpider()))

    assert result is response


def test_retry_middleware_gives_up_once_attempts_are_exhausted():
    mw = RetryWithBackoffMiddleware(_retry_settings(scrapy_retry_max_attempts=2))
    request = _FakeRequest("https://example.invalid/flaky")
    request.meta["retry_times"] = 1  # one retry already made; max_attempts=2 allows no more
    response = _FakeResponse(request, status=503, body=b"still failing", headers={})

    result = _run(mw.process_response(request, response, _FakeSpider()))

    assert result is response


def test_retry_middleware_process_exception_retries_a_transport_error():
    import scrapy
    from twisted.internet.error import ConnectError

    mw = RetryWithBackoffMiddleware(_retry_settings(scrapy_retry_backoff_min_seconds=0.01,
                                                      scrapy_retry_backoff_max_seconds=0.02))
    request = _FakeRequest("https://example.invalid/flaky")

    result = _run(mw.process_exception(request, ConnectError("refused"), _FakeSpider()))

    assert isinstance(result, scrapy.Request)
    assert result.meta["retry_times"] == 1


def test_retry_middleware_process_exception_does_not_retry_a_robots_refusal():
    from scrapy.exceptions import IgnoreRequest

    mw = RetryWithBackoffMiddleware(_retry_settings())
    request = _FakeRequest("https://example.invalid/blocked")

    result = _run(mw.process_exception(request, IgnoreRequest("nope"), _FakeSpider()))

    assert result is None


def test_retry_middleware_process_exception_ignores_an_unrecognised_exception():
    mw = RetryWithBackoffMiddleware(_retry_settings())
    request = _FakeRequest("https://example.invalid/odd")

    result = _run(mw.process_exception(request, ValueError("not a network error"), _FakeSpider()))

    assert result is None


# --- minimal request/response doubles for the middleware unit tests ---------
#
# Real `scrapy.http.Request`/`Response` objects, not ad hoc stand-ins: a
# fake that drifted from Scrapy's actual `.meta`/`.headers` behaviour would
# validate nothing. `Response.meta` in particular proxies to `request.meta`
# (see ProvenanceArchiveMiddleware's docstring) — using the real classes is
# what makes that proxying part of what these tests check.

def _FakeRequest(url: str):
    import scrapy

    return scrapy.Request(url, meta={})


def _FakeResponse(request, *, status: int, body: bytes, headers: dict):
    import scrapy

    return scrapy.http.Response(request.url, status=status, body=body,
                                 headers=headers, request=request)
