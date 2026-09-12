# Reproducible agent environment profiles

Inspection baseline: `62b4d161cf13cd00a21caf45c23317c7deef08a5`, 9 September 2026. These are source-checked recipes, not a claim that an environment or test ran in the planning session. Capture the actual task revision before use. Shell examples require Bash. Runtime preflight is still required.

## Common preflight

Use an agent-owned clean checkout/worktree plus a disposable container/VM for service isolation. Capture `git rev-parse HEAD`, `git status --short` and actual tool versions. Do not source a shared or production `.env`. Require an isolated configuration; stop if its destination cannot be established. Do not print credentials. Prepare an external evidence directory with `export EVIDENCE_DIR=$(mktemp -d)` and retain its reports before teardown. Dependency/browser/image downloads belong to explicitly permitted setup; test execution stays offline except for the named disposable local services.

Record profile, execution ID, source SHA, installed versions/image digests, network policy, test database identity and approved mode. Never disable test safety guards. A topic worktree alone does not isolate server ports, database schemas, container names or output directories. Do not delete or reuse another agent's resources.

## F - frontend verification

Authoritative files: each app's `package.json`, committed package lock, `.npmrc`, Playwright configuration and the applicable workflow under `.github/workflows`. Resolve the actual frontend workflow before calling a run CI-equivalent; `.github/workflows/tests.yml` is the Python/PostgreSQL workflow, not the frontend build recipe. Use the version required by the selected frontend workflow and record it. The root Dockerfile explicitly uses Node 22 in its build stage, which is a separate production-build profile.

Current public fixtures and Playwright use `http://localhost:4173`. Use one isolated network namespace/container per concurrent agent. `CI=1` prevents server reuse, but does not isolate ports. Keep public/admin builds and outputs separate. No opportunistic dependency upgrades are part of acceptance.

From repository root, after approved setup-network and browser installation preflight:

```bash
set -euo pipefail
: "${EVIDENCE_DIR:?set an external execution-specific evidence directory}"
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
# Only during permitted setup, when matching browser binaries are absent:
# npx playwright install --with-deps chromium firefox webkit
npm run test:e2e -- --project=chromium e2e/document-tables.spec.ts --workers=1 --trace=retain-on-failure
```

The last command is the JON-109 focused example, not the entire release browser matrix. Use the task's resolved existing spec for another route; final JON-77 acceptance includes the required real Chromium/Firefox/WebKit projects. Capture command output and exit codes. `npm run build` includes SPA fallback generation; `npm run generate` alone is different. Inspect the chosen fixture's off-origin request guard. Compare source-derived text and downloads with independent expected outputs, not screenshots alone.

Resolve current bundle/Lighthouse scripts and their exact flags from the committed workflow/configuration before running them; do not guess a script name. Repeat the appropriate setup in the separate admin app when required. Automated browser tests do not certify manual assistive-technology acceptance.

## P - offline PostgreSQL verification

Authoritative files: `.github/workflows/tests.yml`, `deploy/postgres/Dockerfile`, `deploy/postgres/initdb`, `tests/conftest.py`, `pyproject.toml` and `uv.lock`. Use the task revision's Python requirement and actual workflow/tool versions. The inspected workflow installs the `maps` and `otel` extras; test tooling is in the default `dev` dependency group, not a `dev` extra or a `test` group. Add `--locked` during preparation to detect lock drift rather than silently rewriting it.

`tests/conftest.py` reads `POSTGRES_TEST_URL`, not `TEST_DATABASE_URL`, and may fall back to `.env` if it is missing. Its autouse fixtures create/drop worker schemas and truncate tables. Therefore use a new dedicated database/container for this execution, never the working warehouse. A second agent cannot safely share it merely because pytest uses per-worker schemas: separate pytest sessions reuse names such as `pgtest_main`/`pgtest_gw0`.

The following adapts the actual workflow to a unique, loopback-bound ephemeral port. Run only in a verified disposable environment with setup/Docker authority. Its credentials are public example credentials for this new local test container only.

```bash
set -euo pipefail
: "${RUN_ID:?set a unique execution ID using letters, digits or hyphens}"
: "${EVIDENCE_DIR:?set an external execution-specific evidence directory}"
: "${SECTORTRACE_DISPOSABLE_ENV:?set only after verifying the environment is disposable}"
test "$SECTORTRACE_DISPOSABLE_ENV" = 1
case "$RUN_ID" in *[!A-Za-z0-9-]*|'') echo 'Invalid RUN_ID' >&2; exit 1;; esac
PG_CONTAINER="sectortrace-agent-$RUN_ID"
PG_IMAGE="sectortrace-postgres-agent:$RUN_ID"
docker build --tag "$PG_IMAGE" deploy/postgres
docker run --detach --name "$PG_CONTAINER" --label "sectortrace.agent=$RUN_ID" \
  --publish 127.0.0.1::5432 \
  --env POSTGRES_USER=sectortrace_app \
  --env POSTGRES_PASSWORD=sectortrace_app_dev \
  --env POSTGRES_DB=postgres \
  --volume "$PWD/deploy/postgres/initdb:/docker-entrypoint-initdb.d:ro" \
  "$PG_IMAGE"
for attempt in $(seq 1 60); do
  if docker exec "$PG_CONTAINER" pg_isready -U sectortrace_app -d postgres; then break; fi
  sleep 1
done
docker exec "$PG_CONTAINER" pg_isready -U sectortrace_app -d postgres
PGPORT=$(docker port "$PG_CONTAINER" 5432/tcp | head -n 1 | awk -F: '{print $NF}')
export POSTGRES_TEST_URL="postgresql://sectortrace_app:sectortrace_app_dev@127.0.0.1:$PGPORT/sectortrace"
export DATABASE_URL="$POSTGRES_TEST_URL"
export DATABASE_RO_URL=''
export POSTGRES_TEST_RO_URL=''
export CONTACT_EMAIL=agent@example.invalid
# Verify the init scripts created the expected disposable DB/extensions.
docker exec "$PG_CONTAINER" psql -U sectortrace_app -d sectortrace -v ON_ERROR_STOP=1 \
  -c "SELECT extname FROM pg_extension WHERE extname IN ('vector','pg_trgm','postgis') ORDER BY extname;"
# Stop if any required extension is missing; do not convert this into a skip.
uv sync --locked --extra maps --extra otel
uv run --no-sync ruff check pipeline tests
uv run --no-sync python -m pipeline docs-check
parallel_status=0
uv run --no-sync python -m pytest -q --tb=short -m 'not serial and not integration' \
  -n auto --dist loadscope --durations=50 --junitxml="$EVIDENCE_DIR/pytest-parallel.xml" \
  > "$EVIDENCE_DIR/pytest-parallel.log" 2>&1 || parallel_status=$?
serial_status=0
uv run --no-sync python -m pytest -q --tb=short -m 'serial and not integration' \
  --durations=50 --junitxml="$EVIDENCE_DIR/pytest-serial.xml" \
  > "$EVIDENCE_DIR/pytest-serial.log" 2>&1 || serial_status=$?
cat "$EVIDENCE_DIR/pytest-parallel.log" "$EVIDENCE_DIR/pytest-serial.log"
printf 'parallel_exit=%s serial_exit=%s\n' "$parallel_status" "$serial_status"
test "$parallel_status" -eq 0 && test "$serial_status" -eq 0
```

This is a local verification recipe, not a replacement for every qualifying CI job. The workflow also checks the beta queue, generated documentation and optional NLP/Mojo boundaries; use its actual commands and required job matrix for JON-76/JON-77. The `--no-sync` calls retain the explicitly installed locked environment. Record that choice and actual versions. A selected task can use a focused pytest path during iteration; the final required matrix still applies.

The extension query must return all three named extensions before tests. Record the query output and actual database identity. Stop on any unexpected destination or missing init state. On completion/failure, retain logs and then remove only this named execution-labelled container if teardown is authorised; never use broad prune. Tests must not fetch live sources, import production snapshots without approval, or write into repository evidence directories.

## C - build and approved staging rehearsal

JON-82 supplies the source/configuration lock. JON-78 owns the immutable build manifest and basic serving acceptance. The inspected Dockerfile uses Node 22 only in the frontend build stage and a Python 3.12 uv runtime image. It builds each app from its own lockfile. Do not substitute locally built assets and call them the same artefact.

```bash
set -euo pipefail
: "${RUN_ID:?set a unique safe execution ID}"
docker build --build-arg INSTALL_ASSISTANT=false --build-arg INSTALL_SCRAPY=false \
  --build-arg INSTALL_OPEN_JOBS=false -t "sectortrace-agent:$RUN_ID" .
docker image inspect "sectortrace-agent:$RUN_ID" --format '{{.Id}}'
```

This is the disabled-optional example, not authority to override approved candidate flags. Record source SHA, exact base image digests, lockfiles, build arguments, resulting image ID/registry digest where available, static-output hashes and redacted configuration. Building an image does not start it. The default `deploy/railway-start.sh` path may migrate or start workers; inspect it and approve an isolated runtime command before any run. Do not inherit production credentials or start live collection.

Use the same image bytes for final serving/browser/recovery checks. JON-79/JON-86 additionally require approved disposable inventory, target identity, backup/archive manifest, recovery-time/data-loss tolerances and permitted restore/rollback commands. Check mode alone is not proof of no side effects. Missing inputs stop dependent execution, not safe inspection. Record measured results; do not invent recovery targets or human approval. Production launch remains JON-84 after JON-83.

## Failure classification

Distinguish missing input, environment/tool/network setup failure, test failure, known baseline defect and human acceptance pending. Keep raw results and report omitted checks. A skipped browser, unavailable database, cancelled CI run or unrun recipe is not a pass. No application tests or runtime preflight were executed during authoring of these profiles.
