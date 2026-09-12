"""The transport contract, proved against the existing HTTPX path.

Every case here maps an already-tested `PipelineHTTPClient` behaviour (see
tests/test_http.py) onto a `TransportResult` — it does not re-test
`PipelineHTTPClient` itself, only that wrapping it loses none of the
provenance or failure information the contract requires.
"""
from __future__ import annotations

import httpx

from pipeline.transports.httpx import fetch_via_httpx
from pipeline.transports.types import FailureClass


def _allow_all_robots(httpx_mock, origin: str = "https://example.com") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="")


def test_successful_fetch_carries_full_provenance(httpx_mock, settings):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url="https://example.com/page", status_code=200,
                             content=b"hello world", headers={"Content-Type": "text/plain"})

    result = fetch_via_httpx("https://example.com/page", source_system="test_source",
                              settings=settings)

    assert result.ok is True
    assert result.failure_class is FailureClass.NONE
    assert result.status_code == 200
    assert result.body == b"hello world"
    assert result.payload_sha256
    assert result.raw_archive_ref
    assert result.requested_url == "https://example.com/page"
    assert result.final_url == "https://example.com/page"
    result.require_provenance()  # must not raise


def test_http_error_is_an_explicit_failure_not_an_empty_success(httpx_mock, settings):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url="https://example.com/missing", status_code=404,
                             content=b"not found")

    result = fetch_via_httpx("https://example.com/missing", source_system="test_source",
                              settings=settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.HTTP_ERROR
    assert result.status_code == 404
    # A 404 body is archived exactly as a 200's is — PipelineHTTPClient
    # archives whatever bytes came back regardless of status.
    assert result.payload_sha256
    assert result.raw_archive_ref
    result.require_provenance()


def test_empty_response_is_an_explicit_failure(httpx_mock, settings):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url="https://example.com/empty", status_code=200, content=b"")

    result = fetch_via_httpx("https://example.com/empty", source_system="test_source",
                              settings=settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.EMPTY_RESPONSE
    result.require_provenance()  # no body, so no hash/archive is required


def test_robots_disallowed_is_an_explicit_failure(httpx_mock, settings):
    httpx_mock.add_response(url="https://example.com/robots.txt", status_code=200,
                             text="User-agent: *\nDisallow: /\n")

    result = fetch_via_httpx("https://example.com/secret", source_system="test_source",
                              settings=settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.ROBOTS_DISALLOWED
    assert result.requested_url == "https://example.com/secret"
    result.require_provenance()


def test_blocked_destination_is_an_explicit_failure_when_guarded(settings):
    # A literal loopback address needs no resolver and no httpx_mock: the
    # destination guard refuses it before any request (even the robots.txt
    # fetch) leaves the client.
    result = fetch_via_httpx("http://127.0.0.1/secret", source_system="test_source",
                              settings=settings, guard_destination=True)

    assert result.ok is False
    assert result.failure_class is FailureClass.BLOCKED_DESTINATION
    result.require_provenance()


def test_destination_guard_is_off_by_default(httpx_mock, settings):
    # Ordinary module collection never turns this on — the same default as
    # PipelineHTTPClient itself.
    _allow_all_robots(httpx_mock, origin="http://127.0.0.1")
    httpx_mock.add_response(url="http://127.0.0.1/page", status_code=200, content=b"hi")

    result = fetch_via_httpx("http://127.0.0.1/page", source_system="test_source",
                              settings=settings)

    assert result.ok is True


def test_timeout_is_an_explicit_failure(httpx_mock, settings, monkeypatch):
    """A real timeout retries several times with backoff (see
    `pipeline.http._is_retryable`) before `_do_request` gives up — not
    something worth waiting out in a unit test. Replacing `_do_request`
    itself (rather than mocking six requests through it) exercises exactly
    the mapping this wrapper is responsible for: whatever eventually comes
    out of `PipelineHTTPClient.get()` becomes `FailureClass.TIMEOUT`.
    """
    from pipeline.http import PipelineHTTPClient

    _allow_all_robots(httpx_mock)

    def immediate_timeout(self, method, url, **kwargs):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(PipelineHTTPClient, "_do_request", immediate_timeout)

    result = fetch_via_httpx("https://example.com/slow", source_system="test_source",
                              settings=settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.TIMEOUT
    result.require_provenance()


def test_unrecognised_failure_is_never_a_silent_empty_success(httpx_mock, settings, monkeypatch):
    """Something this pipeline has not been taught to recognise must still
    come back as a labelled failure — never as `ok=True` with nothing in it.
    """
    from pipeline.transports import httpx as httpx_transport

    class WeirdError(Exception):
        pass

    def explode(self, url):
        raise WeirdError("a response shape nobody has seen before")

    monkeypatch.setattr(httpx_transport.PipelineHTTPClient, "get", explode)

    result = fetch_via_httpx("https://example.com/odd", source_system="test_source",
                              settings=settings)

    assert result.ok is False
    assert result.failure_class is FailureClass.UNRECOGNISED
    assert "WeirdError" in result.failure_detail
    result.require_provenance()
