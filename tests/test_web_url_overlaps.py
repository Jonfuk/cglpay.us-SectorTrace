"""Candidate URL overlap signals (BETA-057).

One canonical URL in more than one source table is a lead, not proof to
merge. Read-only.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import url_overlaps
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    # The same document, discovered as a contract notice page and a PFD
    # report, under two spellings that canonicalise the same.
    conn.execute(
        "INSERT INTO contracts (notice_id, ocid, buyer_name, notice_web_url, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('n1', 'o1', 'A Council', "
        " 'https://docs.gov.uk/report/7?utm_source=x#top', 'https://api/x', "
        " '2026-08-01T00:00:00Z', 200, 'fts', 's1')")
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, source_url, "
        " matters_of_concern, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('2026-1', 'https://DOCS.gov.uk/report/7/', "
        " 'https://judiciary.uk/x', 'concern', '2026-08-01T00:00:00Z', 200, "
        " 'm08', 'p1')")
    # A URL in only one table — must not be reported as an overlap.
    conn.execute(
        "INSERT INTO tribunal_cases (case_number, claim_ref, country, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('C-1', 'CR-1', 'England', 'https://council.gov.uk/lonely', "
        " '2026-08-01T00:00:00Z', 200, 'm02', 't1')")
    conn.commit()
    return conn


def test_a_url_in_two_source_tables_is_one_overlap(warehouse):
    result = url_overlaps.overlaps(warehouse)
    assert result["total"] == 1
    group = result["overlaps"][0]
    assert group["canonical_url"] == "https://docs.gov.uk/report/7"
    assert group["distinct_sources"] == 2
    tables = {o["table"] for o in group["occurrences"]}
    assert tables == {"contracts", "pfd_reports"}


def test_a_url_in_one_table_only_is_not_an_overlap(warehouse):
    result = url_overlaps.overlaps(warehouse)
    for group in result["overlaps"]:
        assert "council.gov.uk/lonely" not in group["canonical_url"]


def test_the_caveat_says_it_is_a_lead_not_proof(warehouse):
    caveat = url_overlaps.overlaps(warehouse)["caveat"].lower()
    assert "a lead" in caveat
    assert "not proof" in caveat and "merged" in caveat or "merge" in caveat


def test_it_is_read_only():
    source = inspect.getsource(url_overlaps)
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "commit("):
        assert forbidden not in source


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


def test_the_route_is_admin_only(client):
    ok = client.get("/api/admin/url-overlaps")
    assert ok.status_code == 200
    assert ok.json()["total"] == 1
    assert client.get("/api/v1/admin/url-overlaps").status_code == 404
