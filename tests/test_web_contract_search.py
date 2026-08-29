"""Contract search and pagination on /api/v1/contracts (BETA-040).

`q` (case-insensitive buyer/supplier name), `since_retrieved_at`, and
`limit`/`offset` windowing, with the guarantee that the CSV download carries
every filter the table does *except* the pagination — an export is always the
complete matching set.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.web import public_export, public_queries, queries
from pipeline.web.server import build_server

# buyer, supplier, retrieved_at
_ROWS = [
    ("Birmingham City Council", "Change Grow Live", "2026-08-01T00:00:00Z"),
    ("Leeds City Council", "CHANGE GROW LIVE LTD", "2026-08-10T00:00:00Z"),
    ("Kent County Council", "Turning Point", "2026-07-01T00:00:00Z"),
    ("Change Borough Council", "We Are With You", "2026-06-01T00:00:00Z"),
    ("Surrey County Council", "Cranstoun", "2026-05-01T00:00:00Z"),
]


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    for i, (buyer, supplier, retrieved) in enumerate(_ROWS):
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, ?, 'E08000025', ?, 'Treatment services', ?, 'GBP', "
            " ?, 'open', 'psr', 'https://find.example/n', ?, 200, "
            " 'find_a_tender', ?)",
            (f"n{i}", f"ocds-n{i}", buyer, supplier, 1_000_000 * (i + 1),
             f"2026-0{i + 1}-01", retrieved, f"sha{i}"))
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, canonical_name) "
                 "VALUES ('Change Grow Live', 'change_grow_live', 'Change Grow Live')")
    conn.commit()
    return conn


@pytest.fixture
def client(warehouse, settings):
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


def _notice_ids(payload) -> set[str]:
    return {n["notice_id"] for n in payload["notices"]}


# --- q: case-insensitive buyer / supplier name ---------------------------


def test_q_matches_supplier_name_case_insensitively(warehouse):
    data = public_queries.contracts(warehouse, q="change grow live")
    assert _notice_ids(data) == {"n0", "n1"}
    assert data["total"] == 2
    assert data["page"]["q"] == "change grow live"


def test_q_matches_buyer_name(warehouse):
    data = public_queries.contracts(warehouse, q="CHANGE BOROUGH")
    assert _notice_ids(data) == {"n3"}


def test_q_wildcard_characters_are_escaped(warehouse):
    # A bare LIKE pattern of "%" would match every row; escaped, it matches
    # only a name that literally contains a percent sign (none do).
    data = public_queries.contracts(warehouse, q="%")
    assert data["total"] == 0


def test_q_narrows_the_charts_too(warehouse):
    data = public_queries.contracts(warehouse, q="change grow live")
    # by_provider is computed over the same filter, so it only sees the
    # matched supplier.
    assert {row["provider_key"] for row in data["by_provider"]} == {"change_grow_live"}
    assert data["date_range"]["earliest"] == "2026-01-01"
    assert data["date_range"]["latest"] == "2026-02-01"


# --- since_retrieved_at -------------------------------------------------


def test_since_retrieved_at_filters_on_collection_time(warehouse):
    data = public_queries.contracts(warehouse, since_retrieved_at="2026-08-01T00:00:00Z")
    assert _notice_ids(data) == {"n0", "n1"}
    assert data["page"]["since_retrieved_at"] == "2026-08-01T00:00:00Z"


# --- limit / offset windowing -----------------------------------------


def test_limit_and_offset_window_the_notices_but_not_the_total(warehouse):
    first = public_queries.contracts(warehouse, limit=2, offset=0)
    second = public_queries.contracts(warehouse, limit=2, offset=2)
    assert first["total"] == 5 and second["total"] == 5
    assert first["page"] == {
        "limit": 2, "offset": 0, "returned": 2, "q": None, "since_retrieved_at": None,
    }
    assert len(first["notices"]) == 2
    assert len(second["notices"]) == 2
    assert _notice_ids(first).isdisjoint(_notice_ids(second))


def test_offset_past_the_end_returns_no_rows_but_the_real_total(warehouse):
    data = public_queries.contracts(warehouse, limit=10, offset=99)
    assert data["notices"] == []
    assert data["total"] == 5
    assert data["page"]["returned"] == 0


def test_negative_offset_is_clamped(warehouse):
    data = public_queries.contracts(warehouse, limit=2, offset=-5)
    assert data["page"]["offset"] == 0


# --- export parity ----------------------------------------------------


def test_export_honours_q_and_ignores_pagination(warehouse):
    total, rows = public_queries.all_contract_notices(
        warehouse, q="change grow live")
    materialised = list(rows)
    assert total == 2
    assert {r["notice_id"] for r in materialised} == {"n0", "n1"}


def test_export_stream_is_complete_regardless_of_a_limit(warehouse):
    # all_contract_notices takes no limit/offset at all — the download is the
    # whole matching set by construction.
    total, rows = public_queries.all_contract_notices(warehouse)
    assert total == 5
    assert len(list(rows)) == 5


# --- the HTTP surface -----------------------------------------------


def test_route_accepts_q_limit_and_offset(client: httpx.Client):
    body = client.get("/api/v1/contracts", params={"q": "change grow live",
                                                   "limit": 1, "offset": 1}).json()
    assert body["total"] == 2
    assert body["page"] == {
        "limit": 1, "offset": 1, "returned": 1, "q": "change grow live",
        "since_retrieved_at": None,
    }
    assert len(body["notices"]) == 1


def test_csv_export_matches_the_searched_table_and_drops_pagination(client: httpx.Client):
    csv = client.get("/api/v1/export", params={
        "endpoint": "contracts", "format": "csv",
        "q": "change grow live", "limit": 1, "offset": 0,
    }).text
    assert "# rows: 2 — every row matching these filters" in csv
    assert "q=change grow live" in csv
    # The pagination parameters are not filters and must not appear as ones.
    assert "limit=" not in csv
    assert "offset=" not in csv


def test_export_and_table_agree_on_the_matching_count(client: httpx.Client, settings):
    table = client.get("/api/v1/contracts", params={"q": "council"}).json()
    ro = queries.readonly_connection(settings)
    try:
        export_total, _ = public_queries.all_contract_notices(ro, q="council")
    finally:
        ro.close()
    assert table["total"] == export_total == 5  # every buyer name contains "Council"


def test_contracts_stays_a_windowed_export_target():
    assert "contracts" in public_export.WINDOWED
