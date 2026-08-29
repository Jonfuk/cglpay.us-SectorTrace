"""PostgreSQL extension readiness report (BETA-063).

The SQLite branch, the CLI, the admin route, and the consistency of the
hand-maintained matrix against the migration text. The PostgreSQL behaviour
itself is in `test_pg_capabilities_live.py`, which needs a real server.
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from pipeline import cli as cli_module
from pipeline import db, pg_capabilities
from pipeline.web.server import build_server

POSTGRES_MIGRATIONS = (
    Path(__file__).resolve().parent.parent / "pipeline" / "migrations" / "postgres")


def test_on_sqlite_the_gate_does_not_apply(conn: sqlite3.Connection):
    result = pg_capabilities.report(conn)
    assert result["backend"] == "sqlite"
    assert result["applies"] is False
    assert result["ready"] is True
    assert "SQLite" in result["note"]
    assert result["indexes"] == [] and result["active_fallbacks"] == []


def test_every_matrix_row_names_a_warehouse_extension():
    for backed in pg_capabilities.BACKED_INDEXES:
        assert backed.extension in db.WAREHOUSE_EXTENSIONS


def test_every_matrix_index_is_declared_in_the_postgres_tree():
    """The matrix asserts an intended shape; if a migration stopped creating
    one of these indexes the matrix must still point at something real."""
    tree = "\n".join(p.read_text(encoding="utf-8")
                     for p in POSTGRES_MIGRATIONS.glob("*.sql"))
    for backed in pg_capabilities.BACKED_INDEXES:
        pattern = re.compile(
            rf"CREATE INDEX IF NOT EXISTS {re.escape(backed.index)}\b.*?"
            rf"USING {backed.method}\b", re.DOTALL)
        assert pattern.search(tree), f"{backed.index} USING {backed.method} not in the pg tree"
        if backed.opclass:
            assert backed.opclass in tree, f"{backed.opclass} not in the pg tree"


def test_the_cli_reports_and_stays_zero_on_sqlite(conn, settings, monkeypatch):
    monkeypatch.setattr(cli_module, "get_settings", lambda: settings)
    result = CliRunner().invoke(cli_module.app, ["pg-capabilities"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["applies"] is False

    # --strict cannot fail a SQLite warehouse: there is nothing to be ready for.
    strict = CliRunner().invoke(cli_module.app, ["pg-capabilities", "--strict"])
    assert strict.exit_code == 0


@pytest.fixture
def client(conn, settings):
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


def test_the_route_is_admin_only(client):
    ok = client.get("/api/admin/pg-capabilities")
    assert ok.status_code == 200
    assert ok.json()["applies"] is False
    assert client.get("/api/v1/pg-capabilities").status_code == 404
