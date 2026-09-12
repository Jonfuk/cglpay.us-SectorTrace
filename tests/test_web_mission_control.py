"""Pipeline mission control read model (BETA-082).

One read-only aggregate over the module registry, the active job and the run
ledger — dependency waves, each module's last-run status, a failure summary.
No cancellation, no streaming, no new write semantics.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx

from pipeline.web import mission_control
from pipeline.web.server import build_server


class _NoJobs:
    def running(self):
        return None

    def all(self):
        return []


def test_the_read_model_joins_the_three_sources(conn: sqlite3.Connection, settings) -> None:
    out = mission_control.overview(conn, settings, _NoJobs())
    assert out["generated_from"] == ["module registry", "active job", "run ledger"]
    assert out["wave_count"] >= 1
    assert out["waves"], "no dependency waves"
    for wave in out["waves"]:
        assert "wave" in wave and isinstance(wave["modules"], list)
        for module in wave["modules"]:
            assert set(module) >= {
                "name", "depends_on", "missing_dependencies", "pending_review",
                "parse_failures", "cursor_updated_at", "last_run",
            }
    # nothing has run in the template warehouse
    assert out["active"] is None
    assert out["history"] == []
    assert out["last_run"] is None


def test_a_failed_last_run_reaches_the_failure_summary(conn: sqlite3.Connection, settings) -> None:
    conn.execute(
        "INSERT INTO run_ledger (run_id, origin, revision, environment, "
        " module_selector, dry_run, started_at, finished_at, status, "
        " modules_total, modules_ok, modules_failed, results_json) VALUES "
        "('r1', 'cli', 'abc', 'test', 'm00_geography', 0, "
        " '2026-08-01T00:00:00Z', '2026-08-01T00:05:00Z', 'partial', 1, 0, 1, "
        " '[{\"module\": \"m00_geography\", \"status\": \"failed\", \"rows\": 0}]')")
    conn.commit()

    out = mission_control.overview(conn, settings, _NoJobs())
    assert out["last_run"]["run_id"] == "r1"
    failing = {f["module"] for f in out["failure_summary"]}
    assert "m00_geography" in failing
    m0 = next(m for wave in out["waves"] for m in wave["modules"]
              if m["name"] == "m00_geography")
    assert m0["last_run"]["status"] == "failed"


def test_it_adds_no_write_route(conn: sqlite3.Connection, settings) -> None:
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=30.0
        ) as http:
            got = http.get("/api/admin/mission-control")
            assert got.status_code == 200
            assert "waves" in got.json()
            # it is a GET-only aggregate
            assert http.post("/api/admin/mission-control",
                             json={}, headers={"Content-Type": "application/json"}
                             ).status_code in (404, 405)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_note_states_the_read_only_boundary(conn: sqlite3.Connection, settings) -> None:
    note = mission_control.overview(conn, settings, _NoJobs())["note"].lower()
    assert "no cancellation" in note and "no new" in note
