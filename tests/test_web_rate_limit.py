"""The per-IP token bucket on /api/v1/*, exercised through a real server.

Uses a small burst/refill so the suite does not need to make dozens of
requests or sleep to prove the limit exists — see `test_ratelimit.py` for the
token-bucket algorithm itself, tested in isolation with a fake clock.
"""
from __future__ import annotations

import threading

import httpx
import pytest

from pipeline.web.server import build_server


def _serve(settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
def limited_settings(settings):
    # Small enough that a handful of requests proves the limit without the
    # test sleeping or racing real wall-clock refill.
    return settings.model_copy(update={
        "api_rate_limit_enabled": True,
        "api_rate_limit_burst": 3.0,
        "api_rate_limit_per_minute": 60.0,
    })


@pytest.fixture
def client(conn, limited_settings):
    server, thread = _serve(limited_settings)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_requests_within_burst_all_succeed(client):
    for _ in range(3):
        assert client.get("/api/v1/summary").status_code == 200


def test_the_next_one_is_429_with_retry_after(client):
    for _ in range(3):
        client.get("/api/v1/summary")
    response = client.get("/api/v1/summary")
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) >= 1
    assert "error" in response.json()


def test_admin_api_is_not_rate_limited(client):
    """/api/admin/* is the operator's own tooling — see the comment in
    Handler._dispatch on why request rate is not its security model."""
    for _ in range(3):
        client.get("/api/v1/summary")  # exhaust the v1 bucket
    for _ in range(5):
        assert client.get("/api/overview").status_code == 200


def test_static_and_health_routes_are_never_rate_limited(client):
    for _ in range(3):
        client.get("/api/v1/summary")  # exhaust the v1 bucket
    for _ in range(5):
        assert client.get("/health").status_code == 200
        assert client.get("/").status_code == 200


def test_different_clients_have_independent_buckets(client):
    for _ in range(3):
        client.get("/api/v1/summary", headers={"X-Forwarded-For": "203.0.113.1"})
    blocked = client.get("/api/v1/summary", headers={"X-Forwarded-For": "203.0.113.1"})
    assert blocked.status_code == 429

    # A different forwarded address has never been charged.
    fresh = client.get("/api/v1/summary", headers={"X-Forwarded-For": "203.0.113.2"})
    assert fresh.status_code == 200


@pytest.fixture
def unlimited_client(conn, settings):
    disabled = settings.model_copy(update={"api_rate_limit_enabled": False})
    server, thread = _serve(disabled)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_disabled_via_settings_never_limits(unlimited_client):
    for _ in range(10):
        assert unlimited_client.get("/api/v1/summary").status_code == 200
