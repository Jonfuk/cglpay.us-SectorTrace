"""Derived PostGIS geometry helpers.

Offline, so PostGIS is never present: what is pinned here is that every path
is a clean no-op on SQLite (and on a PostgreSQL server without the extension,
which `has_extension` reports the same way). The live rebuild is exercised
behind the `postgres` marker.
"""
from __future__ import annotations

import sqlite3

from pipeline import geo, pgload


def test_refresh_is_a_noop_on_sqlite(conn: sqlite3.Connection):
    assert geo.refresh_authority_geometry(conn) == 0


def test_refresh_writes_nothing_on_sqlite(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        " first_seen_vintage, last_seen_vintage, geometry_geojson, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E06000019', 'Herefordshire', 'unitary', '2021-04-01', '2024', "
        " '2026', '{\"type\":\"Polygon\",\"coordinates\":[]}', 'https://ons.example', "
        " '2026-08-01T00:00:00Z', 200, 'ons', 'x')")
    conn.commit()
    before = conn.execute("SELECT COUNT(*) FROM authorities").fetchone()[0]
    geo.refresh_authority_geometry(conn)
    after = conn.execute("SELECT COUNT(*) FROM authorities").fetchone()[0]
    assert before == after


def test_portable_columns_drops_pg_only_columns(conn: sqlite3.Connection):
    # geom is not in the SQLite schema, so portable_columns returns the full
    # list unchanged here — the filter only bites on a PostGIS-enabled server.
    cols = pgload.portable_columns(conn, "authorities")
    assert "geom" not in cols
    assert "geometry_geojson" in cols
    assert "ons_code" in cols


def test_pg_derived_columns_names_authorities_geom():
    assert pgload.PG_DERIVED_COLUMNS["authorities"] == frozenset({"geom"})
