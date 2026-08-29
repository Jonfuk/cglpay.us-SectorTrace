"""The durable run ledger (BETA-058).

`runner.run_waves` is the one choke point every entry point goes through, so
one ledger row is written there per run — CLI, admin or scheduled. A ledger
write that fails must never fail the collection.
"""
from __future__ import annotations

import threading
from pathlib import Path

import httpx
import pytest

from pipeline import console as ui
from pipeline import db, run_ledger, runner
from pipeline.config import Settings
from pipeline.registry import MODULE_REGISTRY, discover_modules
from pipeline.web.server import build_server

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    # So MODULE_REGISTRY holds the real module set and the "all" heuristic in
    # run_waves does not misfire on a two-module test run.
    discover_modules()


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(contact_email="t@example.com", database_path=tmp_path / "w.db",
                 raw_archive_dir=tmp_path / "raw", logs_dir=tmp_path / "logs",
                 migrations_dir=MIGRATIONS, environment="test", _env_file=None)
    conn = db.get_connection(s)
    db.apply_migrations(conn, MIGRATIONS)
    conn.commit()
    conn.close()
    return s


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
