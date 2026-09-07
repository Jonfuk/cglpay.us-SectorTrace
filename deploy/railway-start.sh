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

# The Phase 5 worker cutover (CLAUDE.md settled decision 10) moved pipeline-
# module execution out of the web process into a separate `pipeline worker
# run` process, claiming under a PostgreSQL advisory lock rather than a
# threading.Lock this process could no longer be the only one holding.
# Railway runs one service from this image with no second container to put
# that process in, so it starts here instead, backgrounded in the same
# container -- otherwise `POST /api/admin/run` would enqueue a row that
# nothing ever claims. Co-location is a deployment-topology choice, not a
# correctness one: the advisory lock, not which container a process runs in,
# is what actually enforces one-run-at-a-time, so a genuinely separate
# worker service can replace this line later without anything else changing.
#
# Backgrounded rather than supervised: a container teardown kills every
# process in it together regardless, and the worker already handles being
# killed mid-job the same way it handles a crash -- its lease expires and the
# next worker to start resumes from the last committed per-module checkpoint
# (pipeline/worker.py's `_CheckpointingObserver`). It just does not get a
# graceful SIGTERM warning first, which is an acceptable trade for not
# writing a process supervisor into a single-process-per-container image.
python -m pipeline worker run &

exec python -m pipeline web --host 0.0.0.0 --port "${PORT:-1801}" --no-open
