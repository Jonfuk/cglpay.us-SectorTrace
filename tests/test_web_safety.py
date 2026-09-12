"""`GET /api/v1/safety` — HSE enforcement notices attributed to a provider (BETA-051).

Only `provider_key IS NOT NULL` rows reach here; the register's own `result`
travels with every notice, and nothing infers a compliance outcome.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web.server import build_server


@pytest.fixture
def client(conn: sqlite3.Connection, settings: Settings):
    conn.execute("INSERT INTO providers (provider_key, canonical_name, "
                 "is_target, notes) VALUES ('change_grow_live', 'Change Grow "
                 "Live', 1, NULL)")
    common = ("'https://resources.hse.gov.uk/notices/x', "
              "'2026-08-01T00:00:00Z', 200, 'hse_enforcement_notices', 'sha'")
    conn.execute(
        "INSERT INTO hse_enforcement_notices (notice_number, recipient_name, "
        " provider_key, notice_type, issuing_body, issue_date, result, "
        " legislation, source_url, retrieved_at, http_status, source_system, "
        f" payload_sha256) VALUES ('301', 'Change Grow Live', 'change_grow_live', "
        f" 'Improvement', 'HSE', '2024-05-02', 'Complied', 'MHSWR 1999 / 3', {common})")
    conn.execute(
        "INSERT INTO hse_enforcement_notices (notice_number, recipient_name, "
        " provider_key, notice_type, issuing_body, issue_date, result, "
        " legislation, source_url, retrieved_at, http_status, source_system, "
        f" payload_sha256) VALUES ('302', 'Change Grow Live', 'change_grow_live', "
        f" 'Prohibition', 'HSE', '2023-11-14', 'Under appeal', 'HSWA 1974 / 2(1)', {common})")
    # An unattributed notice: collected, never published.
    conn.execute(
        "INSERT INTO hse_enforcement_notices (notice_number, recipient_name, "
        " provider_key, notice_type, source_url, retrieved_at, http_status, "
        f" source_system, payload_sha256) VALUES ('999', 'Some Other Ltd', NULL, "
        f" 'Improvement', {common})")
    conn.commit()
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_only_attributed_notices_are_published(client):
    body = client.get("/api/v1/safety").json()
    assert body["total"] == 2
    assert {n["notice_number"] for n in body["notices"]} == {"301", "302"}
    assert all(n["provider_name"] == "Change Grow Live" for n in body["notices"])
    # Newest issue date first.
    assert [n["notice_number"] for n in body["notices"]] == ["301", "302"]


def test_the_result_field_is_carried_verbatim(client):
    notices = {n["notice_number"]: n for n in client.get("/api/v1/safety").json()["notices"]}
    assert notices["302"]["result"] == "Under appeal"
    assert notices["301"]["result"] == "Complied"


def test_the_payload_carries_facets_and_the_caveat(client):
    body = client.get("/api/v1/safety").json()
    assert {t["notice_type"] for t in body["by_type"]} == {"Improvement", "Prohibition"}
    assert body["by_provider"][0]["notice_count"] == 2
    caveat = body["caveat"].lower()
    for phrase in ("appeal", "infer", "individual", "not a safety rating"):
        assert phrase in caveat


def test_the_route_is_on_the_frozen_public_surface():
    from tests.test_portal_isolation import PUBLIC_API_ROUTES
    assert "safety" in PUBLIC_API_ROUTES
