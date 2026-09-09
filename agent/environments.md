# Reproducible agent environment profiles

Inspection baseline: `62b4d161cf13cd00a21caf45c23317c7deef08a5`, 9 September 2026. Commands below are execution recipes, not a claim they ran in the planning review. Recheck the actual revision before use. Shell examples require Bash with `set -euo pipefail`.

## Common preflight

Use an agent-owned clean checkout/worktree and a disposable container/VM where services cannot collide with another agent. Capture `git rev-parse HEAD`, `git status --short` and relevant tool versions. Do not source a shared/production `.env`; do not print credentials. Set an execution-specific external output directory, for example `EVIDENCE_DIR=$(mktemp -d)` and export it. Preserve the directory or upload its reports before the environment is destroyed. Dependency/browser/image downloads require the dispatch's setup network allowance; actual tests remain offline. Stop if setup is unavailable rather than silently reducing the required matrix.

Record profile, execution ID, source SHA, tool/image versions, network policy, test database identity and approval reference. Never use `TEST_ALLOW_UNSAFE_DB` to bypass safety checks. Repository instructions are not authority to inspect unrelated private data or start paid services.

## F — frontend verification

Source of truth: `frontend/public/package.json`, its lockfile, `frontend/public/playwright.config.ts`, corresponding admin files and `.github/workflows/tests.yml`. CI currently uses Node 24; the production Dockerfile's build stage uses Node 22. Record and test those profiles separately; do not silently change either version or claim they are identical.

Use one isolated network namespace/container per agent: the current public test server and fixtures use localhost:4173. `CI=1` prevents Playwright from reusing another running server, but does not itself isolate ports. Separate worktrees alone are insufficient. Keep public/admin builds separate. Use the committed package lock; do not upgrade dependencies during acceptance.

From repository root, with approved setup network access:

```bash
set -euo pipefail
export CI=1
export SECTORTRACE_E2E_OUTPUT="$EVIDENCE_DIR/playwright"
node --version
npm --version
cd frontend/public
npm ci
npm run typecheck
npm run lint
npm test
npm run build
cd ../..
node scripts/check_frontend_bundles.mjs --app public
cd frontend/public
# Install only in authorised setup, not during offline test execution.
npx playwright install --with-deps chromium firefox webkit
npx playwright test e2e/document-tables.spec.ts --project=chromium --workers=1 --trace=retain-on-failure
```

The final command is the JON-109 focused example, not a replacement for required regression/browser matrices. Use the task's resolved spec path for another route and retain command output/exit status. `npm run build` includes SPA fallback generation; `npm run generate` alone does not. Test source-derived text and downloads against fixture oracles, not screenshots alone. Confirm the chosen spec rejects external source requests. For admin use its own directory, lockfile and `scripts/check_nuxt_bundles.mjs --app admin` from the root. Do not claim manual assistive-technology acceptance from automated browser tests.

## P — offline PostgreSQL verification

Source of truth: `.github/workflows/tests.yml`, `deploy/postgres.Dockerfile`, `tests/conftest.py`, `pyproject.toml` and `uv.lock`. CI uses Python 3.12, uv 0.11.14 and PostgreSQL 18 with vector, pg_trgm and postgis. Use the exact task baseline's lock and record actual installed versions. A lock mismatch is a setup failure, not permission to update it silently.

Use a fresh database created for this execution. In an agent-owned disposable environment, with Docker setup authorised:

```bash
set -euo pipefail
: "${RUN_ID:?set a unique safe execution ID}"
: "${SECTORTRACE_DISPOSABLE_ENV:?set only after verifying this environment is disposable}"
test "$SECTORTRACE_DISPOSABLE_ENV" = 1
PG_CONTAINER="sectortrace-agent-$RUN_ID"
docker build -t "sectortrace-postgres-agent:$RUN_ID" -f deploy/postgres.Dockerfile .
docker run -d --name "$PG_CONTAINER" --label "sectortrace.agent=$RUN_ID" \
  -e POSTGRES_DB=sectortrace -e POSTGRES_USER=sectortrace -e POSTGRES_PASSWORD=sectortrace \
  -p 127.0.0.1::5432 "sectortrace-postgres-agent:$RUN_ID"
for attempt in $(seq 1 60); do
  if docker exec "$PG_CONTAINER" pg_isready -U sectortrace -d sectortrace; then break; fi
  sleep 1
done
docker exec "$PG_CONTAINER" pg_isready -U sectortrace -d sectortrace
for extension in vector pg_trgm postgis; do
  docker exec "$PG_CONTAINER" psql -U sectortrace -d sectortrace -v ON_ERROR_STOP=1 \
    -c "CREATE EXTENSION IF NOT EXISTS $extension;"
done
PGPORT=$(docker port "$PG_CONTAINER" 5432/tcp | head -n 1 | awk -F: '{print $NF}')
export DATABASE_URL="postgresql://sectortrace:sectortrace@127.0.0.1:$PGPORT/sectortrace"
export TEST_DATABASE_URL="$DATABASE_URL"
export CONTACT_EMAIL=agent@example.invalid
unset TEST_ALLOW_UNSAFE_DB
uv sync --extra dev --locked
uv run ruff check pipeline tests
uv run python -m pipeline docs-check
uv run python -m pytest -n auto -m 'not serial' --junitxml="$EVIDENCE_DIR/junit-parallel.xml"
uv run python -m pytest -n 0 -m serial --junitxml="$EVIDENCE_DIR/junit-serial.xml"
```

The displayed database credential is only for the newly created loopback-bound disposable container, never a production credential. Verify extensions and test safety preflight before running tests. Tests own fixture seeding/temporary writable paths; never replay source collection to manufacture fixtures. Destroy only the named, execution-labelled container after retaining logs/results; do not use broad Docker prune or remove another agent's database. Full suite commands can be replaced by a task's verified focused selector during iteration; final required gates still apply.

## C — container and approved staging rehearsal

JON-82 supplies source/configuration lock. JON-78 owns build/artefact identity. At the inspected baseline the Dockerfile uses Node 22 only in the build stage, then Python 3.12 serving, with optional extras off by default. Build both static apps through that Dockerfile; do not substitute a local Node 24 build and call it the same artefact.

```bash
set -euo pipefail
: "${RUN_ID:?set a unique safe execution ID}"
docker build --build-arg INSTALL_ASSISTANT=false --build-arg INSTALL_SCRAPY=false \
  --build-arg INSTALL_OPEN_JOBS=false -t "sectortrace-agent:$RUN_ID" .
docker image inspect "sectortrace-agent:$RUN_ID" --format '{{.Id}}'
```

This is the disabled-optional baseline, not an instruction to override an approved candidate configuration. Record base image digests, lockfiles, source SHA, build arguments, image ID/registry digest where available, hashes of static outputs and redacted runtime configuration. Run the same image in an isolated network against profile P data using an explicitly reviewed entrypoint and serving flags. Do not invoke the deployment startup path until its side effects, database destination and worker/collection behaviour are checked. Verify public/admin isolation, CSP, fallback assets, PMTiles Range/caching and selected variants; retain results for those exact bytes.

JON-79/JON-86 additionally require an approved disposable staging inventory, recovery-time/data-loss tolerances, backup/archive manifest, target identity, and permission for destructive restore on that target. Missing any of these stops rehearsal, not read-only preparation. Record measured results; no invented recovery targets. Use existing Ansible and backup code, inspect exact commands at the task revision, and keep production credentials/hosts out of the rehearsal. Production rollout is JON-84 only after JON-83 approval.

## Failure classification

Separate environment/tool/network setup failure, missing input, test failure, known baseline defect and human acceptance pending. Keep raw results. Do not turn a skipped browser, unavailable database, transient CI cancellation or an unrun command into a pass. Use Waiting for input for absent prerequisites and a linked defect for reproducible implementation failures.
