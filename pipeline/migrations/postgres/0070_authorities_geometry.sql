-- Authority boundary geometry, PostgreSQL dialect of
-- ../0070_authorities_geometry.sql.
--
-- `authorities.geom` is a *derived* column: `geometry_geojson` (WGS84 GeoJSON
-- text, written by m00_geography for currently-active codes) parsed into a
-- PostGIS MultiPolygon. It carries no fact of its own — `geometry_geojson`
-- stays the source of truth and the only geometry the SQLite mirror holds —
-- so `pgverify` never looks at it (it iterates SQLite's columns) and `pgsync`
-- / `pgload` skip it (pipeline/pgload.py PG_DERIVED_COLUMNS). It is rebuilt on
-- this side by `pipeline/geo.py:refresh_authority_geometry`, called after a
-- migration, after a bulk load, and after m00 writes boundaries.
--
-- What it buys: a GiST index, so ST_Contains point-in-polygon ("which
-- authority contains this CQC location") and ST_PointOnSurface centroids are
-- an index scan rather than a full-table shapely pass. Postcode -> authority
-- stays a separate decision — it is gated on the archive cost of an ONS
-- postcode-directory source, which PostGIS does not change.
--
-- Guarded like migration 0069's trigram indexes: on a server without PostGIS
-- the column and index are skipped and the geojson exports keep using
-- shapely. `db.ensure_extensions()` has already tried `CREATE EXTENSION` by
-- the time this runs; `refresh_authority_geometry` adds the column and index
-- if a later PostGIS install left this migration unable to.
--
-- ST_CollectionExtract(..., 3) after ST_MakeValid: a repaired invalid polygon
-- can come back as a GeometryCollection, and only its polygonal parts belong
-- in a MultiPolygon column.

DO $$
DECLARE
    postgis_schema name;
    application_schema name;
BEGIN
    SELECT n.nspname
      INTO postgis_schema
      FROM pg_extension e
      JOIN pg_namespace n ON n.oid = e.extnamespace
     WHERE e.extname = 'postgis';

    IF postgis_schema IS NOT NULL THEN
        -- Scratch benchmark schemas intentionally exclude `public` from
        -- search_path so unqualified DROP/CREATE statements cannot touch the
        -- real warehouse. Make the extension's own schema visible only for
        -- this guarded block; PostGIS is installed in a schema selected by
        -- the cluster rather than guaranteed to be public.
        SELECT current_schema() INTO application_schema;
        PERFORM set_config(
            'search_path',
            format('%I,%I,pg_catalog', application_schema, postgis_schema),
            true
        );
        ALTER TABLE authorities ADD COLUMN IF NOT EXISTS geom geometry(MultiPolygon, 4326);
        CREATE INDEX IF NOT EXISTS idx_authorities_geom ON authorities USING gist (geom);
        UPDATE authorities
           SET geom = ST_Multi(ST_CollectionExtract(
                   ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(geometry_geojson), 4326)), 3))
         WHERE geometry_geojson IS NOT NULL;
    ELSE
        RAISE NOTICE 'postgis not installed - authorities.geom skipped; geojson exports will use shapely';
    END IF;
END $$;
