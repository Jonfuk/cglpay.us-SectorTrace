"""`GET /api/v1/meta` release identity, and the beta smoke gate (BETA-039).

A beta is not auditable if a reviewer cannot tell which build, schema and
optional capabilities they are exercising. `/api/v1/meta` is that identity;
`/health` stays the deliberately plain `ok` liveness probe.

The smoke gate here is read-only by construction: it only ever issues GET and
HEAD, and it asserts that the mutating verbs are refused. Nothing in it can
trigger collection or change a row.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import public_queries, queries
from pipeline.web.server import build_server

EXPECTED_TOP_LEVEL = {
    "service",
    "environment",
    "revision",
    "revision_source",
    "build_time",
    "backend",
    "schema",
    "data",
    "capabilities",
}
EXPECTED_CAPABILITIES = {
    "admin_ui",
    "api_response_cache",
    "api_rate_limit",
    "document_analysis",
    "semantic_search",
    "postgres_extensions",
}


@pytest.fixture
def client(settings: Settings, conn: sqlite3.Connection):
    # A migrated but empty warehouse is enough — meta reads only the schema
    # ledger and the (empty) http_cache table.
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=15.0
        ) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- the function ----------------------------------------------------------


def test_meta_shape_is_stable(conn: sqlite3.Connection, settings: Settings):
    meta = public_queries.meta(conn, settings)
    assert set(meta) == EXPECTED_TOP_LEVEL
    assert meta["service"] == "sectortrace"
    assert meta["backend"] == "sqlite"
    assert set(meta["schema"]) == {"latest_migration", "applied_count", "migrated_at"}
    assert meta["schema"]["applied_count"] > 0
    assert meta["schema"]["latest_migration"].endswith(".sql")
    assert set(meta["data"]) == {"last_fetch_at", "per_source"}
    assert meta["data"]["per_source"] == "/api/v1/freshness"
    assert set(meta["capabilities"]) == EXPECTED_CAPABILITIES
    # SQLite reports no PostgreSQL extensions.
    assert meta["capabilities"]["postgres_extensions"] == {}


def test_meta_reflects_settings(conn: sqlite3.Connection, tmp_path):
    tuned = Settings(
        contact_email="test@example.com",
        database_path=tmp_path / "warehouse.db",
        environment="beta",
        git_revision="0123456789abcdef",
        build_time="2026-08-29T00:00:00Z",
        admin_ui_enabled=False,
        cache_enabled=True,
        nlp_enabled=False,
        _env_file=None,
    )
    meta = public_queries.meta(conn, tuned)
    assert meta["environment"] == "beta"
    assert meta["revision"] == "0123456789abcdef"
    assert meta["revision_source"] == "deployment"
    assert meta["build_time"] == "2026-08-29T00:00:00Z"
    assert meta["capabilities"]["admin_ui"] is False
    assert meta["capabilities"]["api_response_cache"] is True
    assert meta["capabilities"]["semantic_search"] is False


def test_meta_revision_falls_back_to_the_checkout(conn: sqlite3.Connection, settings: Settings):
    # settings.git_revision is unset in the fixture, so meta reads .git/HEAD.
    meta = public_queries.meta(conn, settings)
    assert meta["revision_source"] == "checkout"
    # This repo is a git checkout, so the fallback resolves to a 40-hex sha;
    # if it somehow cannot, None is the contract, never a crash.
    assert meta["revision"] is None or len(meta["revision"]) == 40


def test_meta_is_idempotent(conn: sqlite3.Connection, settings: Settings):
    before = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    first = public_queries.meta(conn, settings)
    second = public_queries.meta(conn, settings)
    after = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    assert first == second
    assert before == after


# --- the smoke gate: read-only HTTP --------------------------------------


def test_health_is_the_plain_liveness_probe(client: httpx.Client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text.strip() == "ok"
    assert "application/json" not in response.headers.get("content-type", "")


def test_meta_endpoint_serves_the_identity(client: httpx.Client):
    response = client.get("/api/v1/meta")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == EXPECTED_TOP_LEVEL
    assert body["service"] == "sectortrace"
    assert body["environment"] == "development"
    assert set(body["capabilities"]) == EXPECTED_CAPABILITIES


def test_meta_head_request_carries_no_body(client: httpx.Client):
    response = client.head("/api/v1/meta")
    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_meta_refuses_mutating_verbs(client: httpx.Client, method: str):
    # POST falls through to "no route for POST" (404); the stdlib handler has
    # no do_PUT/do_PATCH/do_DELETE at all and answers 501. Either way the
    # endpoint is unreachable by anything that could mutate state.
    response = client.request(method, "/api/v1/meta")
    assert response.status_code >= 400
    assert response.status_code not in (200, 201, 202, 204)


def test_meta_matches_the_function_output(client: httpx.Client, settings: Settings):
    ro = queries.readonly_connection(settings)
    try:
        expected = public_queries.meta(ro, settings)
    finally:
        ro.close()
    # `build_time`/`revision` are process-stable; the whole payload should match.
    assert client.get("/api/v1/meta").json() == expected
