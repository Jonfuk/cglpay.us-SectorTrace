# The warehouse PostgreSQL image: stock postgres:18 plus the three extensions
# the pipeline uses where they are present.
#
# Why a custom image rather than the stock one: `pg_trgm` ships in the stock
# image's contrib set, but `vector` (pgvector) and `postgis` do not, and the
# combine of semantic-search ANN + fuzzy name matching + spatial joins needs
# all three on the self-host box. Railway's managed PostgreSQL carries the
# same three behind an env-var toggle, so this image is the self-host and
# mirror equivalent of that.
#
# Both packages come from the PGDG apt repository, which the base image
# already has configured. Pinned to the major version only, on purpose: a
# PostgreSQL minor bump should carry the matching extension build with it, and
# `pipeline migrate` re-runs `CREATE EXTENSION IF NOT EXISTS` on every start,
# so a rebuilt image with a newer extension is picked up without a manual step.
#
# Build context is this directory:
#   docker build -t sectortrace-postgres:18 deploy/postgres
FROM postgres:18

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        postgresql-18-pgvector \
        postgresql-18-postgis-3; \
    rm -rf /var/lib/apt/lists/*
