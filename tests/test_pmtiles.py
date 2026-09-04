"""Deterministic PMTiles generation from canonical authority geometry."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import struct

import pytest

from pipeline import pmtiles

pytestmark = pytest.mark.maps


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE authorities (ons_code TEXT, name TEXT, region TEXT, "
        "geometry_geojson TEXT, source_url TEXT, retrieved_at TEXT)")
    conn.execute(
        "INSERT INTO authorities VALUES (?, ?, ?, ?, ?, ?)",
        (
            "E00000001", "Example authority", "Example region",
            '{"type":"Polygon","coordinates":[[[-1,52],[-1,53],[0,53],[0,52],[-1,52]]]}',
            "https://example.test/boundaries", "2026-09-04T00:00:00Z",
        ),
    )
    conn.commit()
    return conn


def test_archive_is_pmtiles_v3_and_manifest_is_content_addressed(tmp_path):
    pytest.importorskip("mapbox_vector_tile")
    pytest.importorskip("mercantile")

    manifest = pmtiles.build_authority_archive(_conn(), tmp_path, max_zoom=1)
    archive = tmp_path / manifest["archive"].rsplit("/", 1)[-1]
    payload = archive.read_bytes()

    assert payload[:8] == b"PMTiles\x03"
    assert len(payload) > 127
    assert manifest["feature_count"] == 1
    assert manifest["output_digest"] == hashlib.sha256(payload).hexdigest()
    assert json.loads((tmp_path / "boundaries.json").read_text())["archive"] == (
        f"/map/{archive.name}")
    assert struct.unpack_from("<Q", payload, 8)[0] == 127


def test_same_source_bytes_produce_identical_archive(tmp_path):
    pytest.importorskip("mapbox_vector_tile")
    pytest.importorskip("mercantile")

    first = tmp_path / "one"
    second = tmp_path / "two"
    left = pmtiles.build_authority_archive(_conn(), first, max_zoom=1)
    right = pmtiles.build_authority_archive(_conn(), second, max_zoom=1)
    left_bytes = (first / left["archive"].rsplit("/", 1)[-1]).read_bytes()
    right_bytes = (second / right["archive"].rsplit("/", 1)[-1]).read_bytes()

    assert left["source_digest"] == right["source_digest"]
    assert left["output_digest"] == right["output_digest"]
    assert left_bytes == right_bytes
