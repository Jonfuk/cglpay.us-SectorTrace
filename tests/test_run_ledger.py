"""The durable run ledger (BETA-058).

`runner.run_waves` is the one choke point every entry point goes through, so
one ledger row is written there per run — CLI, admin or scheduled. A ledger
write that fails must never fail the collection.
"""
from __future__ import annotations

import threading

import httpx
import pytest

from pipeline import console as ui
from pipeline import db, run_ledger, runner
from pipeline.registry import MODULE_REGISTRY, discover_modules
from pipeline.web.server import build_server


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    # So MODULE_REGISTRY holds the real module set and the "all" heuristic in
    # run_waves does not misfire on a two-module test run.
    discover_modules()


def _fake_module(name, *, fail=False):
    def run(ctx):
        ctx.conn.execute(
            "CREATE TABLE IF NOT EXISTS _probe (module TEXT)")
        ctx.conn.execute("INSERT INTO _probe (module) VALUES (?)", (name,))
        if fail:
            raise RuntimeError("boom")
    return run


def _run(settings, waves, monkeypatch, *, origin="cli", dry_run=False):
    for wave in waves:
        for name in wave:
            monkeypatch.setitem(MODULE_REGISTRY, name, _fake_module(name))
    with ui.progress():
        from pipeline.runner import RunObserver
        return runner.run_waves(waves, 1, settings, None, dry_run, None,
                                 RunObserver(), origin=origin)


def _ledger(settings):
    conn = db.get_connection(settings)
    try:
        return run_ledger.recent(conn)
    finally:
        conn.close()


def test_start_and_finish_write_one_row(settings):
    run_id = run_ledger.start(settings, origin="cli", module_selector="m_x",
                              dry_run=False, modules_total=1)
    assert run_id
    run_ledger.finish(settings, run_id, [
        {"module": "m_x", "status": "ok", "rows": 3, "review": 0,
         "failures": 0, "elapsed": 0.12}])

    rows = _ledger(settings)
    assert len(rows) == 1
    row = rows[0]
    assert row["origin"] == "cli"
    assert row["status"] == "ok"
    assert row["finished_at"]
    assert row["results"][0] == {"module": "m_x", "status": "ok", "rows": 3,
                                  "review": 0, "failures": 0, "elapsed_ms": 120}


def test_run_waves_records_the_origin(settings, monkeypatch):
    _run(settings, [["m_alpha", "m_beta"]], monkeypatch, origin="admin")
    rows = _ledger(settings)
    assert len(rows) == 1
    assert rows[0]["origin"] == "admin"
    assert rows[0]["status"] == "ok"
    assert rows[0]["modules_ok"] == 2
    assert rows[0]["module_selector"] == "m_alpha, m_beta"


def test_a_partial_run_is_recorded_as_partial(settings, monkeypatch):
    monkeypatch.setitem(MODULE_REGISTRY, "m_ok", _fake_module("m_ok"))
    monkeypatch.setitem(MODULE_REGISTRY, "m_bad", _fake_module("m_bad", fail=True))
    with ui.progress():
        from pipeline.runner import RunObserver
        runner.run_waves([["m_ok", "m_bad"]], 1, settings, None, False, None,
                          RunObserver(), origin="cli")
    row = _ledger(settings)[0]
    assert row["status"] == "partial"
    assert row["modules_ok"] == 1 and row["modules_failed"] == 1


def test_a_ledger_failure_never_breaks_the_run(settings, monkeypatch):
    """The collection is the job. Drop the ledger table and the run still
    completes and returns its summary."""
    conn = db.get_connection(settings)
    conn.execute("DROP TABLE run_ledger")
    conn.commit()
    conn.close()

    summary = _run(settings, [["m_solo"]], monkeypatch)
    assert [r["module"] for r in summary] == ["m_solo"]
    assert summary[0]["status"] == "ok"


def _insert_run(settings, run_id, *, started, finished, status, results,
                origin="cli", selector="all"):
    import json
    ok = sum(1 for r in results if r.get("status") == "ok")
    failed = sum(1 for r in results if r.get("status") == "failed")
    conn = db.get_connection(settings)
    try:
        conn.execute(
            "INSERT INTO run_ledger (run_id, origin, revision, environment, "
            " module_selector, dry_run, started_at, finished_at, status, "
            " modules_total, modules_ok, modules_failed, results_json) VALUES "
            "(?, ?, 'abc123', 'test', ?, 0, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, origin, selector, started, finished, status,
             len(results), ok, failed, json.dumps(results)))
        conn.commit()
    finally:
        conn.close()


def _compare(settings, a=None, b=None):
    conn = db.get_connection(settings)
    try:
        return run_ledger.compare(conn, a, b)
    finally:
        conn.close()


def test_compare_defaults_to_the_two_most_recent_runs(settings):
    _insert_run(settings, "r1", started="2026-08-01T00:00:00+00:00",
                finished="2026-08-01T00:10:00+00:00", status="ok",
                results=[{"module": "m1", "status": "ok", "rows": 1,
                          "review": 0, "failures": 0, "elapsed_ms": 100}])
    _insert_run(settings, "r2", started="2026-08-02T00:00:00+00:00",
                finished="2026-08-02T00:10:00+00:00", status="ok",
                results=[{"module": "m1", "status": "ok", "rows": 2,
                          "review": 0, "failures": 0, "elapsed_ms": 100}])
    _insert_run(settings, "r3", started="2026-08-03T00:00:00+00:00",
                finished="2026-08-03T00:10:00+00:00", status="ok",
                results=[{"module": "m1", "status": "ok", "rows": 9,
                          "review": 0, "failures": 0, "elapsed_ms": 100}])
    out = _compare(settings)
    assert out["run_a"]["run_id"] == "r2"   # second newest is the baseline
    assert out["run_b"]["run_id"] == "r3"   # newest is B
    m1 = next(m for m in out["modules"] if m["module"] == "m1")
    assert m1["rows_delta"] == 7 and m1["change"] == "rows-changed"


def test_compare_reports_deltas_added_removed_and_freshness(settings):
    _insert_run(settings, "a", started="2026-08-01T00:00:00+00:00",
                finished="2026-08-01T00:20:00+00:00", status="ok",
                results=[
                    {"module": "m_keep", "status": "ok", "rows": 10,
                     "review": 1, "failures": 0, "elapsed_ms": 1000},
                    {"module": "m_gone", "status": "ok", "rows": 5,
                     "review": 0, "failures": 0, "elapsed_ms": 500}])
    _insert_run(settings, "b", started="2026-08-02T00:00:00+00:00",
                finished="2026-08-02T00:30:00+00:00", status="partial",
                results=[
                    {"module": "m_keep", "status": "failed", "rows": 0,
                     "review": 3, "failures": 2, "elapsed_ms": 1000},
                    {"module": "m_new", "status": "ok", "rows": 4,
                     "review": 0, "failures": 0, "elapsed_ms": 200}])
    out = _compare(settings, "a", "b")
    by = {m["module"]: m for m in out["modules"]}
    assert by["m_keep"]["change"] == "regressed"
    assert by["m_keep"]["freshness_effect"] == "no successful run in B"
    assert by["m_gone"]["change"] == "removed"
    assert by["m_new"]["change"] == "added"
    assert by["m_new"]["freshness_effect"] == "advanced — wrote rows in B"
    # an added module has no comparable row count — its delta is undefined,
    # not a spurious "+4" against an absent baseline
    assert by["m_new"]["rows_delta"] is None and by["m_new"]["rows_b"] == 4
    t = out["totals"]
    assert t["status_regressions"] == 1
    assert t["modules_only_in_a"] == 1 and t["modules_only_in_b"] == 1
    assert t["rows_removed"] == 10       # m_keep fell 10 -> 0
    assert t["rows_added"] == 0
    assert t["review_delta_total"] == 2  # m_keep 1 -> 3
    assert t["duration_delta_ms"] == 600_000  # 30 min vs 20 min


def test_compare_rejects_a_missing_run_and_too_few_runs(settings):
    with pytest.raises(ValueError):
        _compare(settings)  # no runs at all
    _insert_run(settings, "only", started="2026-08-01T00:00:00+00:00",
                finished="2026-08-01T00:05:00+00:00", status="ok",
                results=[{"module": "m1", "status": "ok", "rows": 1,
                          "review": 0, "failures": 0, "elapsed_ms": 10}])
    with pytest.raises(ValueError):
        _compare(settings)  # only one run
    _insert_run(settings, "two", started="2026-08-02T00:00:00+00:00",
                finished="2026-08-02T00:05:00+00:00", status="ok",
                results=[{"module": "m1", "status": "ok", "rows": 1,
                          "review": 0, "failures": 0, "elapsed_ms": 10}])
    with pytest.raises(ValueError):
        _compare(settings, "two", "nope")


def test_compare_writes_nothing(settings):
    for rid, day in (("x", "01"), ("y", "02")):
        _insert_run(settings, rid, started=f"2026-08-{day}T00:00:00+00:00",
                    finished=f"2026-08-{day}T00:05:00+00:00", status="ok",
                    results=[{"module": "m1", "status": "ok", "rows": 1,
                              "review": 0, "failures": 0, "elapsed_ms": 10}])
    conn = db.get_connection(settings)
    try:
        before = conn.execute("SELECT COUNT(*) FROM run_ledger").fetchone()[0]
        out = run_ledger.compare(conn, None, None)
        after = conn.execute("SELECT COUNT(*) FROM run_ledger").fetchone()[0]
    finally:
        conn.close()
    assert before == after == 2
    assert "nothing is written" in out["note"].lower()


def test_run_comparison_route(settings):
    for rid, day, rows in (("p", "01", 3), ("q", "02", 8)):
        _insert_run(settings, rid, started=f"2026-08-{day}T00:00:00+00:00",
                    finished=f"2026-08-{day}T00:05:00+00:00", status="ok",
                    results=[{"module": "m1", "status": "ok", "rows": rows,
                              "review": 0, "failures": 0, "elapsed_ms": 10}])
    conn = db.get_connection(settings)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            out = http.get("/api/admin/run-comparison").json()
            assert out["run_a"]["run_id"] == "p"
            assert out["run_b"]["run_id"] == "q"
            m1 = out["modules"][0]
            assert m1["rows_delta"] == 5
            missing = http.get("/api/admin/run-comparison?a=nope&b=q")
            assert missing.status_code == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_meta_exposes_the_last_run(settings, monkeypatch):
    _run(settings, [["m_meta"]], monkeypatch, origin="scheduled")

    conn = db.get_connection(settings)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            meta = http.get("/api/v1/meta").json()
            last = meta["data"]["last_run"]
            assert last["origin"] == "scheduled"
            assert last["status"] == "ok"
            ledger = http.get("/api/admin/run-ledger").json()
            assert ledger["runs"][0]["origin"] == "scheduled"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
