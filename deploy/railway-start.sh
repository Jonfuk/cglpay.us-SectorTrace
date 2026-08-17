#!/bin/sh
set -eu

# Railway may start a new web process while the previous release is still
# draining. The migration ledger makes this idempotent, and PostgreSQL takes
# care of transactional DDL for each migration. Keep this step in the same
# release that serves traffic so schema and application code cannot drift.
python -m pipeline migrate

exec python -m pipeline web --host 0.0.0.0 --port "${PORT:-1801}" --no-open
