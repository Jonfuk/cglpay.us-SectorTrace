"""`GET /api/v1/contracts/process/{ocid}` — the procurement lifecycle (BETA-050).

The notices that share one OCID, grouped by the lifecycle stage each notice's
own OCDS tag names. The point is what it refuses to do: a stage with no notice
is drawn as absent, never as an inferred completion, and nothing here computes
performance, renewal or continuity.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web.server import build_server

OCID = "ocds-abc123-0001"


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, "
                 "canonical_name) VALUES ('Turning Point', 'turning-point', "
                 "'Turning Point')")
    rows = [
        # notice_id, supplier_id, tag(s), title, published, value, supplier
        ("n-plan", "", "planning", "Prior information notice", "2023-01-10",
         None, None),
        ("n-tender", "", "tender", "Contract notice", "2023-03-01",
         5_000_000, None),
        ("n-award", "s1", "award", "Award notice", "2023-08-15",
         4_800_000, "Turning Point"),
        ("n-amend", "s1", "contractAmendment,contract", "Contract change notice",
         "2024-06-01", 5_200_000, "Turning Point"),
        # A second supplier on the same award notice id — one grouped notice.
        ("n-award", "s2", "award", "Award notice", "2023-08-15",
         4_800_000, "Other Supplier Ltd"),
    ]
    for notice_id, supplier_id, tag, title, published, value, supplier in rows:
        conn.execute(
            "INSERT INTO contracts (notice_id, supplier_id, ocid, notice_type, "
            " buyer_name, buyer_ons_code, supplier_name_raw, title, value_core, "
            " currency, date_published, procedure_type, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256, notice_web_url) VALUES "
            " (%s, %s, %s, %s, 'Birmingham City Council', 'E08000025', %s, %s, %s, 'GBP', "
            " %s, 'open', 'https://find.example/api', '2026-08-01T00:00:00Z', 200, "
            " 'find_a_tender', %s, %s)",
            (notice_id, supplier_id, OCID, tag, supplier, title, value, published,
             f"sha-{notice_id}-{supplier_id}",
             f"https://www.find-tender.service.gov.uk/Notice/{notice_id}"))
    # A different procurement, so the OCID filter has something to exclude.
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, notice_type, "
        " buyer_name, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('other', '', 'ocds-zzz-9999', 'tender', "
        " 'Another Council', 'https://x', '2026-08-01T00:00:00Z', 200, 'fts', 'z')")
    conn.commit()
    return conn


@pytest.fixture
def client(warehouse, settings: Settings):
    warehouse.close()
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


def test_notices_are_grouped_into_the_stages_their_tags_name(client):
    body = client.get(f"/api/v1/contracts/process/{OCID}").json()
    assert body["ocid"] == OCID
    assert body["buyer"]["name"] == "Birmingham City Council"
    assert body["notice_count"] == 4              # n-award's two rows are one notice
    assert body["date_range"] == {"earliest": "2023-01-10", "latest": "2024-06-01"}

    present = {s["stage"]: s for s in body["stages"] if s["present"]}
    assert set(present) == {"planning", "tender", "award", "amendment"}
    assert [n["notice_id"] for n in present["planning"]["notices"]] == ["n-plan"]
    # The amendment notice also carries the `contract` tag; `amendment` wins.
    assert present["amendment"]["notices"][0]["notice_id"] == "n-amend"
    assert present["amendment"]["notices"][0]["stage"] == "amendment"
    # The multi-supplier award notice keeps both suppliers, one entry.
    award = present["award"]["notices"][0]
    assert {s["name"] for s in award["suppliers"]} == {"Turning Point", "Other Supplier Ltd"}
    assert any(s["is_tracked_provider"] for s in award["suppliers"])


def test_an_absent_stage_is_marked_not_inferred(client):
    body = client.get(f"/api/v1/contracts/process/{OCID}").json()
    by_stage = {s["stage"]: s for s in body["stages"]}
    assert by_stage["contract"]["present"] is False
    assert by_stage["contract"]["notices"] == []
    assert by_stage["termination"]["present"] is False
    # Order is the fixed lifecycle order regardless of what is present.
    assert [s["stage"] for s in body["stages"]] == body["stage_order"]


def test_the_caveat_forbids_the_inferences(client):
    caveat = client.get(f"/api/v1/contracts/process/{OCID}").json()["caveat"].lower()
    for phrase in ("not evidence", "completion", "performance", "continuity"):
        assert phrase in caveat


def test_an_unknown_ocid_is_a_400(client):
    response = client.get("/api/v1/contracts/process/ocds-nope-0000")
    assert response.status_code == 400
    assert "ocds-nope-0000" in response.json()["error"]


def test_the_route_is_on_the_frozen_public_surface():
    from tests.test_portal_isolation import PUBLIC_API_PATTERNS
    assert r"contracts/process/([A-Za-z0-9_-]{1,100})" in PUBLIC_API_PATTERNS
