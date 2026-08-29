"""The coverage completion action board (BETA-059).

One reason code + one non-destructive next step per catalogued dataset.
Nothing on the board runs a module, decides a review item, or deletes
anything — the tests pin that.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import completeness_board, datasets
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    # Procurement: has rows AND a pending review item -> review_needed.
    conn.execute(
        "INSERT INTO contracts (notice_id, ocid, buyer_name, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        " ('n1', 'o1', 'A Council', 'https://x', '2026-08-01T00:00:00Z', 200, "
        " 'fts', 's1')")
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, status, "
        "created_at) VALUES ('m01_procurement', 'unmatched_buyer_name', "
        "'A Council', 'pending', '2026-08-01T00:00:00Z')")
    # HSE: has rows, no pending -> source_blocked (it is in _SOURCE_BLOCKED).
    conn.execute(
        "INSERT INTO hse_enforcement_notices (notice_number, recipient_name, "
        " provider_key, notice_type, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) VALUES ('301', 'X Ltd', 'x', "
        " 'Improvement', 'https://h', '2026-08-01T00:00:00Z', 200, 'hse', 'h')")
    conn.commit()
    return conn


def test_one_row_per_catalogued_dataset(warehouse):
    board = completeness_board.board(warehouse)
    assert len(board["datasets"]) == len(datasets.DATASETS)
    assert {d["dataset_id"] for d in board["datasets"]} == \
        {d.dataset_id for d in datasets.DATASETS}


def test_every_row_has_one_reason_and_one_permitted_action(warehouse):
    board = completeness_board.board(warehouse)
    for row in board["datasets"]:
        assert row["reason"] in completeness_board.REASONS
        assert row["action"]["kind"] in ("run", "review", "dataset")
        assert row["action"]["label"] and row["action"]["target"]


def test_the_reason_codes_are_derived_as_documented(warehouse):
    by_id = {d["dataset_id"]: d for d in completeness_board.board(warehouse)["datasets"]}

    # No rows, module never run here -> run_needed, and the action is a run.
    empty = by_id["rough-sleeping"]
    assert empty["reason"] == "run_needed"
    assert empty["action"]["kind"] == "run"

    # Rows + pending review items -> review_needed.
    procurement = by_id["procurement-notices"]
    assert procurement["reason"] == "review_needed"
    assert procurement["action"]["kind"] == "review"
    assert procurement["pending_review"] == 1

    # Rows, no pending, a documented source gap -> source_blocked with a note.
    hse = by_id["hse-enforcement-notices"]
    assert hse["reason"] == "source_blocked"
    assert hse["reason_note"] and "HSE" in hse["reason_note"]


def test_the_summary_counts_add_up(warehouse):
    board = completeness_board.board(warehouse)
    assert sum(board["by_reason"].values()) == len(board["datasets"])


def test_the_caveat_says_nothing_runs_or_deletes(warehouse):
    caveat = completeness_board.board(warehouse)["caveat"].lower()
    for phrase in ("runs a module", "decides a review item", "deletes"):
        assert phrase in caveat


def test_the_board_never_writes_or_runs():
    source = inspect.getsource(completeness_board)
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "run_waves", "commit("):
        assert forbidden not in source, f"{forbidden!r} in the completeness board"


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
    assert client.get("/api/admin/completeness").status_code == 200
    assert client.get("/api/v1/admin/completeness").status_code == 404
    assert client.get("/api/v1/completeness").status_code == 404
