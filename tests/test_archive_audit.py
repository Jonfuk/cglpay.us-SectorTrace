"""Append-only raw-archive audit snapshots (BETA-060).

`compute()` measures the `archive_objects` index and, given an archive, reads
back and re-hashes what it samples (or, `full=True`, every object).
`record()` appends one immutable row and quarantines any mismatch. Nothing
here deletes an object, compacts the archive, or changes retention — the
tests pin that.
"""
from __future__ import annotations

import hashlib
import inspect
import sqlite3
import threading

import httpx
import pytest

from pipeline import archive_audit
from pipeline.archive import FilesystemArchive
from pipeline.config import Settings
from pipeline.web.server import build_server


def _obj(conn, object_id, sha, source, size, path=None):
    conn.execute(
        "INSERT INTO archive_objects (object_id, source_system, payload_sha256, "
        "logical_path, mime_type, size_bytes, first_seen_at, last_seen_at) "
        "VALUES (%s, %s, %s, %s, 'application/pdf', %s, '2026-08-01T00:00:00Z', "
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


def test_sample_size_has_a_floor_and_scales_with_the_archive():
    """performance.md's Phase 5 archive-audit gap: at least 100 objects, or
    1% of the archive when that is larger. `full=True` ignores the formula
    entirely — every object, for the quarterly pass."""
    assert archive_audit._sample_size(0, full=False) == 0
    assert archive_audit._sample_size(5, full=False) == 100        # floor dominates
    assert archive_audit._sample_size(5_000, full=False) == 100    # 1% is 50 — floor still wins
    assert archive_audit._sample_size(20_000, full=False) == 200   # 1% dominates
    assert archive_audit._sample_size(50_000, full=True) == 50_000


def _archive_and_row(conn, archive: FilesystemArchive, object_id: str, source: str, body: bytes):
    """Write a real object through the archive and the matching
    `archive_objects` row, so `get_by_ref` can find it by its exact key —
    unlike `_obj()` above, whose fabricated `raw/<id>` paths exist only to
    exercise `compute()`'s pure DB-metrics path."""
    sha = hashlib.sha256(body).hexdigest()
    logical = archive.put(source, sha, "text/plain", body)
    conn.execute(
        "INSERT INTO archive_objects (object_id, source_system, payload_sha256, "
        "logical_path, mime_type, size_bytes, first_seen_at, last_seen_at) "
        "VALUES (%s, %s, %s, %s, 'text/plain', %s, '2026-08-01T00:00:00Z', "
        "'2026-08-01T00:00:00Z')",
        (object_id, source, sha, logical, len(body)))
    return sha, logical


def test_record_verifies_the_sample_and_quarantines_a_mismatch(conn, settings):
    """The daily sample is a real read-and-rehash, not only a report of what
    `archive_objects` believes — a mismatch must be quarantined (never
    deleted), the same wiring `archive-verify` already has."""
    archive = FilesystemArchive(settings.raw_archive_dir)
    good_sha, good_logical = _archive_and_row(conn, archive, "good", "m01_test", b"good bytes")
    bad_sha, bad_logical = _archive_and_row(conn, archive, "bad", "m01_test",
                                             b"originally correct, later corrupted")
    # Simulate bit rot: the database still says `bad_sha`, but the bytes on
    # disk no longer hash to it.
    (settings.raw_archive_dir / bad_logical.removeprefix("data/raw/")).write_bytes(b"corrupted")
    conn.commit()

    row = archive_audit.record(conn, settings)

    assert row["verified_mismatches"] == 1
    statuses = {s["payload_sha256"]: s["verified_ok"] for s in row["sample"]}
    assert statuses[good_sha] is True
    assert statuses[bad_sha] is False

    quarantined = conn.execute(
        "SELECT item_identity, failure_class FROM quarantine_items "
        "WHERE module = 'archive_audit_sample'").fetchall()
    assert len(quarantined) == 1
    assert quarantined[0]["item_identity"] == bad_logical
    assert quarantined[0]["failure_class"] == "sha256_mismatch"


def test_record_full_verifies_every_object_not_a_sample(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    for i in range(5):
        _archive_and_row(conn, archive, f"o{i}", "m01_test", f"object {i}".encode())
    conn.commit()

    row = archive_audit.record(conn, settings, full=True)

    assert row["audit_kind"] == "quarterly_full"
    assert row["sample_size"] == 5
    assert len(row["sample"]) == 5
    assert row["verified_mismatches"] == 0
    assert all(s["verified_ok"] for s in row["sample"])


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


def test_the_cli_records_a_quarterly_full_audit(warehouse, settings):
    """Distinct subcommand from the daily sample (performance.md's Phase 5
    archive-audit gap wants its own scheduled job, not the daily one
    overloaded with a flag)."""
    from typer.testing import CliRunner

    from pipeline import db
    from pipeline.cli import app

    warehouse.commit()
    warehouse.close()
    runner = CliRunner()

    before = _count_audits(settings)
    result = runner.invoke(app, ["archive-audit-full"])
    assert result.exit_code == 0, result.output
    assert _count_audits(settings) == before + 1

    conn = db.get_connection(settings)
    try:
        kind = conn.execute(
            "SELECT audit_kind FROM archive_audits ORDER BY run_at DESC LIMIT 1"
        ).fetchone()["audit_kind"]
    finally:
        conn.close()
    assert kind == "quarterly_full"


def _count_audits(settings) -> int:
    from pipeline import db

    conn = db.get_connection(settings)
    try:
        return conn.execute("SELECT COUNT(*) FROM archive_audits").fetchone().values().__iter__().__next__()
    finally:
        conn.close()
