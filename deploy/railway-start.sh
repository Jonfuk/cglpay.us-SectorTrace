#!/bin/sh
set -eu

# Railway may start a new web process while the previous release is still
# draining. The migration ledger makes this idempotent, and PostgreSQL takes
# care of transactional DDL for each migration. Keep this step in the same
# release that serves traffic so schema and application code cannot drift.
python -m pipeline migrate

# Release identity for GET /api/v1/meta and the portal footer (BETA-039).
# Railway injects RAILWAY_GIT_COMMIT_SHA for every deploy; the rest of the
# app only reads GIT_REVISION, so map it here. BUILD_TIME is stamped at
# process start, which is close enough to deploy time for an audit line.
# Each is only set if the operator has not already provided it.
export ENVIRONMENT="${ENVIRONMENT:-production}"
export GIT_REVISION="${GIT_REVISION:-${RAILWAY_GIT_COMMIT_SHA:-}}"
export BUILD_TIME="${BUILD_TIME:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"

exec python -m pipeline web --host 0.0.0.0 --port "${PORT:-1801}" --no-open
