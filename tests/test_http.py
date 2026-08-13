from __future__ import annotations

import hashlib
import time

import httpx
import pytest

from pipeline import db
from pipeline.http import (
    PipelineHTTPClient,
    RobotsDisallowed,
    RobotsRules,
    _RateLimiter,
    _wait_respecting_retry_after,
)


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


# --- wildcard robots rules ----------------------------------------------------------
#
# urllib.robotparser matches with `path.startswith(rule)` and so ignores every
# `*`-containing rule. These tests exist because that made this pipeline's
# "we honour robots.txt" claim untrue on any site that writes rules that way,
# mySociety's among them.

WDTK_ROBOTS = """
User-agent: *
Disallow: */search/*
Disallow: */feed/*
Allow: */request/*/response/*/attach/*
Disallow: */request/*/response/*
Disallow: *?*update_status=1*
"""

UA = "cglpay-evidence-pipeline/0.1 (+contact: x@y.uk; purpose: testing)"


@pytest.mark.parametrize("url,allowed", [
    ("https://www.whatdotheyknow.com/feed/search/x.json", False),
    ("https://www.whatdotheyknow.com/search/foo", False),
    ("https://www.whatdotheyknow.com/request/abc/response/1", False),
    # More specific Allow beats the Disallow above it.
    ("https://www.whatdotheyknow.com/request/abc/response/1/attach/2.pdf", True),
    ("https://www.whatdotheyknow.com/body/all-authorities.csv", True),
    ("https://www.whatdotheyknow.com/request/abc", True),
    # A wildcard rule that matches on the query string, not the path.
    ("https://www.whatdotheyknow.com/request/abc?update_status=1", False),
])
def test_wildcard_rules_are_honoured(url, allowed):
    assert RobotsRules(WDTK_ROBOTS, UA).can_fetch(url) is allowed


def test_stdlib_parser_would_have_missed_these():
    """Pins the reason this class exists. If a future Python implements
    wildcards in robotparser, this test fails and the class can be revisited.
    """
    from urllib import robotparser
    p = robotparser.RobotFileParser()
    p.parse(WDTK_ROBOTS.splitlines())
    url = "https://www.whatdotheyknow.com/feed/search/x.json"
    assert p.can_fetch(UA, url) is True
    assert RobotsRules(WDTK_ROBOTS, UA).can_fetch(url) is False


def test_a_group_naming_our_token_overrides_the_wildcard_group():
    text = ("User-agent: *\nDisallow: /\n\n"
            "User-agent: cglpay-evidence-pipeline\nDisallow: /private\n")
    rules = RobotsRules(text, UA)
    assert rules.can_fetch("https://x.com/anything") is True
    assert rules.can_fetch("https://x.com/private") is False


def test_empty_disallow_means_allow_all():
    assert RobotsRules("User-agent: *\nDisallow:\n", UA).can_fetch("https://x.com/a") is True


def test_dollar_anchors_the_end_of_the_path():
    rules = RobotsRules("User-agent: *\nDisallow: /*.pdf$\n", UA)
    assert rules.can_fetch("https://x.com/a/b.pdf") is False
    assert rules.can_fetch("https://x.com/a/b.pdf.html") is True


def test_path_metacharacters_are_matched_literally():
    """A '.' in a rule must not act as a regex wildcard and widen the block."""
    rules = RobotsRules("User-agent: *\nDisallow: /a.b\n", UA)
    assert rules.can_fetch("https://x.com/a.b") is False
    assert rules.can_fetch("https://x.com/axb") is True


def test_missing_robots_txt_allows_everything():
    assert RobotsRules("", UA).can_fetch("https://x.com/anything") is True


def test_configured_exception_allows_a_disallowed_path(httpx_mock, settings, conn):
    """The one sanctioned way past robots.txt. It must be prefix-scoped: an
    exception for /feed/ must not open the rest of the host.
    """
    settings.robots_exceptions = ("https://example.com/feed/",)
    httpx_mock.add_response(
        url="https://example.com/robots.txt", status_code=200,
        text="User-agent: *\nDisallow: */feed/*\nDisallow: /secret\n")
    httpx_mock.add_response(url="https://example.com/feed/search.json",
                             status_code=200, content=b"[]")

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    assert client.get("https://example.com/feed/search.json").ok
    with pytest.raises(RobotsDisallowed):
        client.get("https://example.com/secret")
    client.close()


def test_robots_override_is_recorded_for_review(httpx_mock, settings, conn):
    """An override that left no trace would be indistinguishable from the
    pipeline simply not honouring robots.txt.
    """
    settings.robots_exceptions = ("https://example.com/feed/",)
    httpx_mock.add_response(
        url="https://example.com/robots.txt", status_code=200,
        text="User-agent: *\nDisallow: */feed/*\n")
    for _ in range(2):
        httpx_mock.add_response(url="https://example.com/feed/search.json",
                                 status_code=200, content=b"[]")

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    client.get("https://example.com/feed/search.json")
    client.get("https://example.com/feed/search.json")
    client.close()

    rows = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'robots_override_in_use'").fetchall()
    assert len(rows) == 1, "the override should be recorded once per run, not once per request"
    assert rows[0]["raw_value"] == "https://example.com/feed/"


def test_no_exceptions_means_robots_is_absolute(settings):
    """Guards the default. If this list is ever empty-by-accident the rest of
    the pipeline's robots handling is unchanged, which is the intent.
    """
    settings.robots_exceptions = ()
    assert settings.robots_override_for("https://www.whatdotheyknow.com/feed/x.json") is None


def test_shipped_exceptions_are_prefix_scoped(settings):
    """Each shipped exception covers exactly its own prefix, nothing else.

    Data-driven over the shipped list so a new entry has to prove its own
    scoping rather than silently widening an existing one, and an exception
    for one host never opens the rest of the internet.
    """
    shipped = settings.robots_exceptions
    assert shipped, "shipped exceptions must not be empty-by-accident"
    for prefix in shipped:
        assert settings.robots_override_for(prefix + "x") == prefix
    for url in ("https://www.whatdotheyknow.com/request/x.json",
                 "https://www.whatdotheyknow.com/body/x.json",
                 "https://example.com/feed/x.json",
                 "https://www.liverpool.gov.uk.evil.example/x",
                 "https://democracy.eastsussex.gov.uk.evil.example/x",
                 "https://committees.scilly.gov.uk/x"):
        assert settings.robots_override_for(url) is None


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
    """A 304 must still yield the document's bytes, served from the archive.

    Regression: previously a 304 returned an empty body, so a caller that
    counted attachments in the response silently recorded zero — real data
    loss that looked like a successful run.
    """
    _allow_all_robots(httpx_mock)
    url = "https://example.com/doc.txt"
    body = b"archived content"
    sha = hashlib.sha256(body).hexdigest()

    # seed the archive as a previous run would have
    archive_dir = settings.raw_archive_dir / "test_source"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{sha}.txt").write_bytes(body)

    db.set_http_cache(conn, url=url, host="example.com", etag="abc123", last_modified=None, payload_sha256=sha)
    httpx_mock.add_response(url=url, status_code=304, match_headers={"If-None-Match": "abc123"})

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    result = client.get(url)
    client.close()

    assert result.not_modified is True
    assert result.body == body
    assert result.payload_sha256 == sha


def test_304_without_archived_body_refetches(httpx_mock, settings, conn):
    """If the cache entry exists but its archived payload is gone, the
    client must re-fetch rather than return an empty body.
    """
    _allow_all_robots(httpx_mock)
    url = "https://example.com/doc.txt"
    db.set_http_cache(conn, url=url, host="example.com", etag="abc123", last_modified=None,
                       payload_sha256="0" * 64)

    httpx_mock.add_response(url=url, status_code=304, match_headers={"If-None-Match": "abc123"})
    httpx_mock.add_response(url=url, status_code=200, content=b"refetched body",
                             headers={"content-type": "text/plain"})

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    result = client.get(url)
    client.close()

    assert result.not_modified is False
    assert result.body == b"refetched body"


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
