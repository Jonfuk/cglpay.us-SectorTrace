-- Local development / test initialisation for the PostgreSQL-only warehouse
-- (performance.md Phase 1). This is the un-templated dev sibling of
-- deploy/ansible/roles/sectortrace/templates/postgres-init-roles.sql.j2 — keep
-- the two in step. It runs once, automatically, only when the postgres
-- container initialises an *empty* data directory, via the image's
-- docker-entrypoint-initdb.d hook. It connects to the `postgres` maintenance
-- database (the compose sets POSTGRES_DB=postgres precisely so it can create
-- the real one below), and the image has already created the sectortrace_app
-- superuser from POSTGRES_USER/POSTGRES_PASSWORD before this runs.
--
-- The collation is the load-bearing part, and the reason the warehouse is not
-- created by the image's POSTGRES_DB. `builtin` + C.UTF-8 gives bytewise
-- ordering, so `ORDER BY name` matches SQLite's BINARY ordering and the
-- verify-migration row comparison agrees across both engines during the
-- cutover. The builtin provider is also version-stable where a libc locale is
-- not: a glibc upgrade can reorder an existing index underneath it, and a
-- project whose whole point is a figure that reproduces in a year cannot let
-- its sort order depend on the host's libc. TEMPLATE = template0 is required
-- to use a locale that differs from the cluster's. See
-- pipeline/migrations/postgres/README.md.
CREATE DATABASE sectortrace
    LOCALE_PROVIDER = builtin
    BUILTIN_LOCALE = 'C.UTF-8'
    TEMPLATE = template0;

-- The read-only role DATABASE_RO_URL points at. A role without INSERT refuses
-- at the server whatever a bug in the application does. The password is a
-- fixed dev value: this provisions a throwaway local container and is
-- meaningless anywhere else. The real reader role is created out of band with
-- a vault secret (the .j2 template above).
CREATE ROLE sectortrace_reader LOGIN PASSWORD 'sectortrace_reader_dev';
GRANT CONNECT ON DATABASE sectortrace TO sectortrace_reader;

-- The remaining grants are per-database objects, so they have to be applied
-- inside the warehouse rather than from the maintenance database.
\connect sectortrace

GRANT USAGE ON SCHEMA public TO sectortrace_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sectortrace_reader;

-- No tables exist yet — `pipeline migrate` creates them after this script
-- runs, as sectortrace_app. ALTER DEFAULT PRIVILEGES is what makes
-- sectortrace_reader keep up with every future migration without a manual
-- GRANT; pipeline/db.py grant_reader_access also re-applies the catch-up
-- grant when a migration adds a table.
ALTER DEFAULT PRIVILEGES FOR ROLE sectortrace_app IN SCHEMA public
    GRANT SELECT ON TABLES TO sectortrace_reader;

-- The three extensions the warehouse requires, created once as the
-- sectortrace_app superuser so the numbered migrations only ever reference
-- them. db.ensure_extensions() re-runs the same CREATE EXTENSION IF NOT EXISTS
-- on every `pipeline migrate` for a server this script does not own (a managed
-- Railway instance). Under the PostgreSQL-only transition these are required,
-- not optional: startup fails clearly if the server cannot provide them.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS postgis;
