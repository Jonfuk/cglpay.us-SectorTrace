from __future__ import annotations

import hashlib
import time

import httpx
import pytest

from pipeline import db
from pipeline.http import PipelineHTTPClient, RobotsDisallowed, _RateLimiter, _wait_respecting_retry_after


def _allow_all_robots(httpx_mock, origin: str = "https://example.com") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="")


def test_robots_disallowed_blocks_request(httpx_mock, settings):
    httpx_mock.add_response(
        url="https://example.com/robots.txt",
        status_code=200,
        text="User-agent: *\nDisallow: /\n",
    )
    client = PipelineHTTPClient("test_source", settings=settings)
    with pytest.raises(RobotsDisallowed):
        client.get("https://example.com/secret")
    client.close()


def test_get_captures_provenance_and_archives_body(httpx_mock, settings):
    _allow_all_robots(httpx_mock)
    body = b"hello world"
    httpx_mock.add_response(
        url="https://example.com/doc.txt",
        status_code=200,
        content=body,
        headers={"content-type": "text/plain"},
    )
    client = PipelineHTTPClient("test_source", settings=settings)
    result = client.get("https://example.com/doc.txt")
    client.close()

    assert result.status_code == 200
    assert result.payload_sha256 == hashlib.sha256(body).hexdigest()
    assert result.archived_path is not None
    assert result.archived_path.read_bytes() == body
    assert result.archived_path.parent.name == "test_source"


def test_conditional_request_sends_cached_etag(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    url = "https://example.com/doc.txt"
    db.set_http_cache(conn, url=url, host="example.com", etag="abc123", last_modified=None, payload_sha256="deadbeef")

    httpx_mock.add_response(url=url, status_code=304, match_headers={"If-None-Match": "abc123"})

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    result = client.get(url)
    client.close()

    assert result.not_modified is True
    assert result.body == b""
    assert result.payload_sha256 == "deadbeef"


def test_rate_limiter_enforces_minimum_interval(settings):
    settings.rate_limit_overrides = {"slow.example.com": 0.2}
    limiter = _RateLimiter(settings)
    start = time.perf_counter()
    limiter.wait("slow.example.com")
    limiter.wait("slow.example.com")
    elapsed = time.perf_counter() - start
    # time.sleep can wake slightly early on Windows; allow a small tolerance
    # rather than asserting an exact wall-clock floor.
    assert elapsed >= 0.2 - 0.02


class _FakeOutcome:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def exception(self):
        return self._exc


class _FakeRetryState:
    def __init__(self, exc: BaseException) -> None:
        self.outcome = _FakeOutcome(exc)
        self.attempt_number = 1


def test_wait_respecting_retry_after_honours_header():
    response = httpx.Response(429, headers={"Retry-After": "7"}, request=httpx.Request("GET", "https://example.com"))
    exc = httpx.HTTPStatusError("429", request=response.request, response=response)
    assert _wait_respecting_retry_after(_FakeRetryState(exc)) == 7.0


def test_wait_respecting_retry_after_falls_back_without_header():
    response = httpx.Response(503, request=httpx.Request("GET", "https://example.com"))
    exc = httpx.HTTPStatusError("503", request=response.request, response=response)
    # no Retry-After header -> falls back to exponential backoff, which for
    # the first attempt is small but still a real positive wait.
    assert _wait_respecting_retry_after(_FakeRetryState(exc)) > 0


def test_wait_respecting_retry_after_falls_back_for_non_http_errors():
    exc = ConnectionError("boom")
    assert _wait_respecting_retry_after(_FakeRetryState(exc)) > 0
