"""Operator action cockpit (BETA-086).

A read-only aggregate of prioritised cards over operational state — review
pressure, run health, coverage gaps, schema drift, archive health. Each card
has a deterministic reason and a link to a pre-filtered workflow. It ranks
operational states only: never evidence quality, never a review outcome, and
it decides nothing.
"""
from __future__ import annotations

import sqlite3

from pipeline.web import cockpit

_KEYS = {
    "review_pressure", "run_health", "coverage_actions", "blocked_sources",
    "schema_drift", "archive_health", "parse_failures",
}


def test_the_cards_are_operational_and_deterministically_ranked(conn: sqlite3.Connection, settings) -> None:
    out = cockpit.overview(conn, settings)
    keys = {c["key"] for c in out["cards"]}
    assert keys == _KEYS
    for card in out["cards"]:
        assert card["priority"] in (0, 1, 2, 3)
        assert card["reason"]                      # a reason, always
        assert card["link"].startswith("#")        # a link to a workflow
    # sorted by priority desc, then key
    order = [(-c["priority"], c["key"]) for c in out["cards"]]
    assert order == sorted(order)
    # nothing about evidence quality or a reviewer
    text = " ".join(c["reason"] for c in out["cards"]).lower()
    assert "reviewer" not in text and "quality" not in text
    assert "outcome" in out["note"].lower() and "never" in out["note"].lower()


def test_review_pressure_reflects_the_pending_queue(conn: sqlite3.Connection, settings) -> None:
    base = next(c for c in cockpit.overview(conn, settings)["cards"]
               if c["key"] == "review_pressure")
    assert base["metric"] == 0 and base["priority"] == 0

    for i in range(3):
        conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            " created_at) VALUES ('m10_committee_papers', 'url', ?, 'pending', "
            " '2026-01-01T00:00:00Z')", (f"https://x/{i}",))
    conn.commit()

    card = next(c for c in cockpit.overview(conn, settings)["cards"]
                if c["key"] == "review_pressure")
    assert card["metric"] == 3
    assert "3 items pending" in card["reason"]
    assert card["link"] == "#review"
    # an old oldest -> act now
    assert card["priority"] == 3


def test_a_failed_last_run_is_act_now(conn: sqlite3.Connection, settings) -> None:
    conn.execute(
        "INSERT INTO run_ledger (run_id, origin, revision, environment, "
        " module_selector, dry_run, started_at, finished_at, status, "
        " modules_total, modules_ok, modules_failed, results_json) VALUES "
        "('r1', 'cli', 'abc', 'test', 'm00', 0, '2026-08-01T00:00:00Z', "
        " '2026-08-01T00:05:00Z', 'failed', 1, 0, 1, '[]')")
    conn.commit()
    card = next(c for c in cockpit.overview(conn, settings)["cards"]
                if c["key"] == "run_health")
    assert card["priority"] == 3
    assert "failed" in card["reason"]


def test_the_route_serves_it(conn: sqlite3.Connection, settings) -> None:
    import threading

    import httpx

    from pipeline.web.server import build_server

    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=30.0
        ) as http:
            got = http.get("/api/admin/cockpit")
            assert got.status_code == 200
            body = got.json()
            assert {"cards", "priority_labels", "top_priority", "note"} <= set(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
