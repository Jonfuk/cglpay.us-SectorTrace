"""Source-link resilience checker (BETA-100).

Whether an original source URL was live, redirected or gone at the last
fetch, and whether a checksum-verified archive copy is held. Derived from
collection-time metadata only — no live request is ever made.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from pipeline.web import link_check
from pipeline.web.queries import QueryError

_NOW = "2026-08-01T00:00:00Z"
_URL = "https://www.gov.uk/example/doc.pdf"


def _evidence(conn, *, status, sha="deadbeef", raw_path=None, url=_URL):
    conn.execute(
        "INSERT INTO evidence_records (evidence_id, source_system, source_url, "
        " retrieved_at, http_status, payload_sha256, raw_object_path, "
        " mime_type, content_length, created_at) VALUES "
        "(?, 'm00', ?, ?, ?, ?, ?, 'application/pdf', 10, ?)",
        (f"ev-{status}-{sha[:6]}", url, _NOW, status, sha, raw_path, _NOW))
    conn.commit()


def test_state_from_the_last_http_status(conn: sqlite3.Connection, settings) -> None:
    _evidence(conn, status=200)
    out = link_check.check(conn, settings, _URL)
    assert out["state"] == "live_at_last_check"
    assert out["last_http_status"] == 200
    assert out["last_checked"] == _NOW
    assert "no request was made" in out["note"].lower()


@pytest.mark.parametrize("status,state", [
    (301, "redirected_at_last_check"),
    (404, "gone_at_last_check"),
    (410, "gone_at_last_check"),
    (500, "error_at_last_check"),
    (None, "not_recorded"),
])
def test_each_status_maps_to_a_conservative_state(conn, settings, status, state) -> None:
    _evidence(conn, status=status, sha=f"s{status}")
    assert link_check.check(conn, settings, _URL)["state"] == state


def test_an_unknown_url_is_its_own_state(conn: sqlite3.Connection, settings) -> None:
    out = link_check.check(conn, settings, "https://nowhere.example/x")
    assert out["state"] == "unknown_url"
    assert out["archive"]["held"] is False


def test_a_non_http_url_is_refused(conn: sqlite3.Connection, settings) -> None:
    with pytest.raises(QueryError):
        link_check.check(conn, settings, "ftp://x/y")


def test_the_archive_copy_is_verified_by_rehashing_the_file(
        conn: sqlite3.Connection, settings) -> None:
    body = b"the archived bytes"
    digest = hashlib.sha256(body).hexdigest()
    archive = Path(settings.raw_archive_dir) / "m00" / "doc.pdf"
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(body)
    _evidence(conn, status=200, sha=digest, raw_path="data/raw/m00/doc.pdf")

    out = link_check.check(conn, settings, _URL)
    assert out["archive"]["held"] is True
    assert out["archive"]["verified"] is True
    assert out["archive"]["bytes"] == len(body)

    # tamper with the file: the hash no longer matches, and it says so
    archive.write_bytes(body + b"!")
    tampered = link_check.check(conn, settings, _URL)
    assert tampered["archive"]["verified"] is False


def test_a_recorded_archive_that_is_missing_on_disk(conn, settings) -> None:
    _evidence(conn, status=200, sha="x", raw_path="data/raw/m00/gone.pdf")
    out = link_check.check(conn, settings, _URL)
    assert out["archive"]["held"] is False
    assert "not on disk" in out["archive"]["note"].lower()


def test_no_live_http_client_is_imported() -> None:
    src = (Path(__file__).resolve().parent.parent / "pipeline" / "web"
           / "link_check.py").read_text(encoding="utf-8")
    for banned in ("import httpx", "import requests", "urllib.request",
                   "from pipeline.http", "import socket"):
        assert banned not in src, banned


def test_the_overview_counts_cited_rows_by_state(conn: sqlite3.Connection) -> None:
    _evidence(conn, status=200, sha="a", url="https://a")
    _evidence(conn, status=200, sha="b", url="https://b")
    _evidence(conn, status=404, sha="c", url="https://c")
    out = link_check.overview(conn)
    assert out["by_state"]["live_at_last_check"] >= 2
    assert out["by_state"]["gone_at_last_check"] >= 1
    assert "re-fetched" in out["note"].lower()


def test_the_route_is_in_the_openapi_document() -> None:
    from pipeline.web import openapi
    assert "/api/v1/source_link" in openapi.document()["paths"]
