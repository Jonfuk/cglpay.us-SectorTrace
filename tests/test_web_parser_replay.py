"""Parser replay sandbox (BETA-103).

Replay a stdlib parser against one archived object in memory and diff the
proposed output against the stored active version. Read-only — nothing is
written; a PDF or a request for docling/pymupdf returns available:false.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.web import parser_replay
from pipeline.web.queries import QueryError
from pipeline.web.server import build_server

_NOW = "2026-08-01T00:00:00Z"
_HTML = b"<html><body><h1>Staff pay review</h1><p>The board agreed the plan.</p></body></html>"


def _seed(conn, settings, *, mime="text/html", body=_HTML, stored_text="OLD TEXT",
          write_archive=True):
    digest = hashlib.sha256(body).hexdigest()
    rel = "m10/doc.html"
    if write_archive:
        p = Path(settings.raw_archive_dir) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, mime_type, "
        " content_length, source_table, source_key, created_at) VALUES "
        "('ev1', 'committee_paper_promotion', 'https://x/1', %s, 200, %s, "
        " %s, %s, %s, 'committee_papers', 'k1', %s)",
        (_NOW, digest, f"data/raw/{rel}", mime, len(body), _NOW))
    conn.execute(
        "INSERT INTO document_records (document_id, evidence_id, source_table, "
        " source_key, document_type, mime_type, title, created_at, updated_at) "
        "VALUES ('d1', 'ev1', 'committee_papers', 'k1', 'committee_paper', %s, "
        " 'Board pack', %s, %s)", (mime, _NOW, _NOW))
    conn.execute(
        "INSERT INTO document_versions (document_version_id, document_id, "
        " parser_name, parser_version, parse_schema_version, config_hash, "
        " text_sha256, status, is_active, created_at) VALUES "
        "('v1', 'd1', 'html', 'stdlib-html-parser-1', '1', 'c', 't', "
        " 'parsed', 1, %s)", (_NOW,))
    conn.execute(
        "INSERT INTO document_elements (document_element_id, document_version_id, "
        " element_type, sequence, text, text_sha256, metadata_json) VALUES "
        "('e1', 'v1', 'PARAGRAPH', 1, %s, 'h', '{}')", (stored_text,))
    conn.commit()
    return digest


def test_replay_html_and_diff_against_the_stored_version(conn, settings) -> None:
    _seed(conn, settings)
    out = parser_replay.replay(conn, settings, "d1")
    assert out["available"] is True
    assert out["archive"]["verified"] is True
    assert out["stored"]["element_count"] == 1
    assert out["proposed"]["element_count"] == 2       # h1 + p
    d = out["diff"]["elements"]
    assert d["changed"] == 1 and d["added"] == 1       # seq 1 changed, seq 2 added
    assert "nothing was written" in out["note"].lower()
    seq1 = next(t for t in out["diff"]["text_changes"] if t["sequence"] == 1)
    assert seq1["stored"] == "OLD TEXT"
    assert "Staff pay review" in seq1["proposed"]


def test_the_replay_writes_nothing(conn: sqlite3.Connection, settings) -> None:
    _seed(conn, settings)
    before = conn.execute("SELECT COUNT(*) FROM document_elements").fetchone().values().__iter__().__next__()
    parser_replay.replay(conn, settings, "d1")
    parser_replay.replay(conn, settings, "d1")
    after = conn.execute("SELECT COUNT(*) FROM document_elements").fetchone().values().__iter__().__next__()
    assert before == after == 1


def test_a_pdf_returns_unavailable_without_importing_a_heavy_parser(conn, settings) -> None:
    _seed(conn, settings, mime="application/pdf", body=b"%PDF-1.4 ...")
    out = parser_replay.replay(conn, settings, "d1")
    assert out["available"] is False
    assert "stdlib parsers only" in out["reason"]


def test_a_missing_archive_returns_unavailable(conn, settings) -> None:
    _seed(conn, settings, write_archive=False)
    out = parser_replay.replay(conn, settings, "d1")
    assert out["available"] is False
    assert "not on disk" in out["reason"]


def test_a_tampered_archive_still_replays_but_flags_the_hash(conn, settings) -> None:
    _seed(conn, settings)
    (Path(settings.raw_archive_dir) / "m10" / "doc.html").write_bytes(_HTML + b"<!-- x -->")
    out = parser_replay.replay(conn, settings, "d1")
    assert out["available"] is True
    assert out["archive"]["verified"] is False


def test_an_unknown_document_raises(conn: sqlite3.Connection, settings) -> None:
    with pytest.raises(QueryError):
        parser_replay.replay(conn, settings, "nope")


def test_the_admin_route_serves_the_replay(settings) -> None:
    from pipeline import db

    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    _seed(conn, settings)
    server = build_server(settings, host="127.0.0.1", port=0)
    conn.close()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            out = http.get("/api/admin/parser-replay?document_id=d1").json()
            assert out["available"] is True
            assert out["proposed"]["element_count"] == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
