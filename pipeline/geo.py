"""Derived geometry on the PostgreSQL warehouse.

`authorities.geom` (migration 0070) is a PostGIS MultiPolygon rebuilt from
`authorities.geometry_geojson`, which stays the source of truth. This module
keeps the two in step. Everything here is a no-op unless the connection is
PostgreSQL with PostGIS installed — SQLite and a Postgres server without the
extension keep using `geometry_geojson` and shapely
(`pipeline/exports/geojson.py`).
"""
from __future__ import annotations

import structlog

log = structlog.get_logger()

# geometry_geojson -> geom. ST_MakeValid can hand back a GeometryCollection
# for a self-intersecting boundary; ST_CollectionExtract(..., 3) keeps only
# its polygonal parts, which is what the geometry(MultiPolygon) column will
# accept. Kept as one string so the migration and this module cannot drift.
_GEOM_FROM_GEOJSON = (
    "ST_Multi(ST_CollectionExtract("
    "ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326)), 3))"
)


def refresh_authority_geometry(conn) -> int:
    """Rebuild `authorities.geom` from `geometry_geojson`. Returns rows touched.

    Idempotent, and cheap — the geometry is held only for currently-active
    codes, a few hundred rows. Called after `apply_migrations` applies
    something, after a bulk load (`pgload`, `pgsync`), and after m00 writes
    boundaries, so the derived column tracks its source whichever path changed
    it.

    Also (re)creates the column and its GiST index: migration 0070 guards that
    DDL on PostGIS being present when it runs, so a cluster that gains PostGIS
    later would otherwise never get the column. PostGIS is a required extension
    now, so the former no-op-without-it guard is gone.
    """
    extension = conn.execute(
        "SELECT current_schema() AS application_schema, n.nspname AS "
        "postgis_schema FROM pg_extension e "
        "JOIN pg_namespace n ON n.oid = e.extnamespace "
        "WHERE e.extname = 'postgis'").fetchone()
    if not extension:
        return 0

    with conn:
        conn.execute(
            "SELECT set_config('search_path', %s, true)",
            (f"{extension['application_schema']},"
             f"{extension['postgis_schema']},pg_catalog",))
        conn.execute("ALTER TABLE authorities ADD COLUMN IF NOT EXISTS "
                     "geom geometry(MultiPolygon, 4326)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_authorities_geom "
                     "ON authorities USING gist (geom)")
        cursor = conn.execute(
            f"UPDATE authorities SET geom = {_GEOM_FROM_GEOJSON} "
            "WHERE geometry_geojson IS NOT NULL")
        touched = cursor.rowcount or 0

    if touched:
        log.info("geo.authority_geometry_refreshed", rows=touched)
    return touched
