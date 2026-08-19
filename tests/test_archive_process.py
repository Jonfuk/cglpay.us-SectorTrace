import hashlib
import json

from pipeline.archive import FilesystemArchive
from pipeline.archive_process import process_archive


def test_process_archive_extracts_and_is_idempotent(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    html = b"<html><body><h1>North Yorkshire</h1><p>Public evidence.</p></body></html>"
    sha = hashlib.sha256(html).hexdigest()
    logical = archive.put("council_papers", sha, "text/html", html)
    conn.execute(
        "INSERT INTO evidence_records "
        "(evidence_id, source_system, source_url, retrieved_at, payload_sha256, raw_object_path, mime_type, content_length, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("ev-1", "council_papers", "https://example.test/paper", "2026-01-01T00:00:00+00:00",
         sha, logical, "text/html", len(html), "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()

    first = process_archive(conn, settings, archive)
    assert first["processed"] == 1
    assert first["failed"] == 0
    row = conn.execute(
        "SELECT evidence_id, status, parser_name, text_storage_path, text_sha256, metadata_json "
        "FROM archive_extractions"
    ).fetchone()
    assert row["evidence_id"] == "ev-1"
    assert row["status"] == "extracted"
    assert row["parser_name"] == "html-text"
    assert "North Yorkshire" in (settings.raw_archive_dir.parent / row["text_storage_path"]).read_text()
    assert row["text_sha256"]
    assert json.loads(row["metadata_json"])["logical_path"] == logical

    second = process_archive(conn, settings, archive)
    assert second["processed"] == 0
    assert second["skipped"] == 1


def test_process_archive_records_json_as_derived_text(conn, settings):
    archive = FilesystemArchive(settings.raw_archive_dir)
    body = json.dumps({"b": 2, "a": "value"}).encode()
    sha = hashlib.sha256(body).hexdigest()
    archive.put("api", sha, "application/json", body)

    result = process_archive(conn, settings, archive, source_system="api", limit=1)
    assert result["processed"] == 1
    row = conn.execute("SELECT status, parser_name, character_count FROM archive_extractions").fetchone()
    assert row["status"] == "extracted"
    assert row["parser_name"] == "json"
    assert row["character_count"] > 0
    assert conn.execute("SELECT COUNT(*) FROM graph_claims").fetchone()[0] == 0
