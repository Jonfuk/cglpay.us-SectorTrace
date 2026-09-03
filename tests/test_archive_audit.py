"""Append-only raw-archive audit snapshots (BETA-060).

`compute()` measures the `archive_objects` index; `record()` appends one
immutable row. Nothing deletes an object, compacts the archive, or changes
retention — the tests pin that.
"""
from __future__ import annotations

import inspect
import sqlite3
import threading

import httpx
import pytest

from pipeline import archive_audit
from pipeline.config import Settings
from pipeline.web.server import build_server


def _obj(conn, object_id, sha, source, size, path=None):
    conn.execute(
        "INSERT INTO archive_objects (object_id, source_system, payload_sha256, "
        "logical_path, mime_type, size_bytes, first_seen_at, last_seen_at) "
        "VALUES (?, ?, ?, ?, 'application/pdf', ?, '2026-08-01T00:00:00Z', "
        "'2026-08-01T00:00:00Z')",
        (object_id, source, sha, path or f"raw/{object_id}", size))


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    _obj(conn, "o1", "aaa", "find_a_tender", 100)
    _obj(conn, "o2", "bbb", "find_a_tender", 200)
    _obj(conn, "o3", "ccc", "judiciary_uk", 50)
    # Same bytes stored twice -> one duplicated hash.
    _obj(conn, "o4", "ddd", "judiciary_uk", 50, path="raw/y")
    _obj(conn, "o5", "ddd", "cdp", 50, path="raw/z")
    # An evidence reference whose bytes were never archived.
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        "retrieved_at, payload_sha256, created_at) VALUES ('e1', 'x', "
        "'https://x', '2026-08-01T00:00:00Z', 'zzz-not-archived', 'now')")
    conn.commit()
    return conn


def test_compute_measures_the_index(warehouse):
    m = archive_audit.compute(warehouse)
    assert m["object_count"] == 5
    assert m["total_bytes"] == 100 + 200 + 50 + 50 + 50
    assert m["by_source"]["find_a_tender"] == {"count": 2, "bytes": 300}
    assert m["duplicate_hashes"] == 1               # 'ddd' twice
    assert m["missing_refs"] == 1                    # 'zzz-not-archived'
    # The sample is the lexicographically smallest hashes — deterministic.
    assert [s["payload_sha256"] for s in m["sample"]][:3] == ["aaa", "bbb", "ccc"]


def test_compute_is_read_only():
    source = inspect.getsource(archive_audit.compute)
    for forbidden in ("INSERT ", "UPDATE ", "DELETE ", "commit("):
        assert forbidden not in source


def test_record_appends_an_immutable_row_and_history_reads_it(warehouse, settings):
    first = archive_audit.record(warehouse, settings)
    second = archive_audit.record(warehouse, settings)
    assert first["audit_id"] != second["audit_id"]

    rows = archive_audit.history(warehouse)
    assert len(rows) == 2
    assert rows[0]["object_count"] == 5
    assert isinstance(rows[0]["by_source"], dict)
    assert isinstance(rows[0]["sample"], list)


def test_record_only_touches_archive_audits():
    source = inspect.getsource(archive_audit.record)
    assert source.count("INSERT INTO") == 1
    assert "INSERT INTO archive_audits" in source
    assert "DELETE" not in source and "UPDATE" not in source


@pytest.fixture
def client(warehouse, settings: Settings):
    archive_audit.record(warehouse, settings)
    warehouse.commit()
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


def test_the_history_route_is_admin_only(client):
    ok = client.get("/api/admin/archive-audits")
    assert ok.status_code == 200
    assert ok.json()["audits"][0]["object_count"] == 5
    assert client.get("/api/v1/admin/archive-audits").status_code == 404


def test_the_cli_records_one_and_show_prints_without_writing(warehouse, settings, capsys):
    from typer.testing import CliRunner

    from pipeline.cli import app

    # A migrated warehouse at settings.database_path is what the CLI opens.
    warehouse.commit()
    warehouse.close()
    runner = CliRunner()

    before = _count_audits(settings)
    result = runner.invoke(app, ["archive-audit"])
    assert result.exit_code == 0
    assert _count_audits(settings) == before + 1

    result = runner.invoke(app, ["archive-audit", "--show"])
    assert result.exit_code == 0
    assert _count_audits(settings) == before + 1     # --show did not write


def _count_audits(settings) -> int:
    from pipeline import db

    conn = db.get_connection(settings)
    try:
        return conn.execute("SELECT COUNT(*) FROM archive_audits").fetchone()[0]
    finally:
        conn.close()
