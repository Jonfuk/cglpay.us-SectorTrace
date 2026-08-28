-- Authority boundary geometry, SQLite dialect.
--
-- On PostgreSQL (../postgres/0070_authorities_geometry.sql) this adds
-- `authorities.geom`, a PostGIS MultiPolygon derived from `geometry_geojson`,
-- plus a GiST index — enabling ST_Contains point-in-polygon joins and
-- server-side centroids. SQLite has no geometry type: `geometry_geojson`
-- (WGS84 GeoJSON text) stays the only geometry it holds, and
-- `pipeline/exports/geojson.py` reads it with shapely as before.
--
-- This file declares only the index NAME so the two migration trees still
-- declare one object set (tests/test_migration_equivalence.py). The
-- PostgreSQL `geom` column is added with ALTER TABLE, which that test's
-- column parser does not read, so there is no SQLite column to match. The
-- btree below is inert — `ons_code` is already the primary key — and exists
-- for the name only, the same shape as `idx_document_elements_search` in the
-- SQLite tree of migration 0053.

CREATE INDEX IF NOT EXISTS idx_authorities_geom ON authorities (ons_code);
