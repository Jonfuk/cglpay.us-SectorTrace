# Admin interface — plan and implementation prompt

Status: proposal, 2026-08-13. Nothing in this document is built yet except
where it says "exists today".

This is two things in one file:

1. **The plan** — what to build at `/admin`, in what order, and the rules that
   guarantee the public portal at `/` is untouched.
2. **The prompt** (final section) — a self-contained brief you can paste into a
   fresh Claude Code session to implement any phase without re-deriving
   context.

No authentication is in scope, by explicit decision. The existing posture
(writes require `application/json` + a same-origin `Origin`) is the whole
security model. Do not spend effort adding auth, and do not weaken those
guards either.

## Decisions taken (2026-08-13)

Recorded here because each one closes off an alternative that would otherwise
be re-litigated every phase.

1. **Admin actions are reachable wherever the server is.** No loopback-only
   restriction on state-changing routes, and `pipeline web` keeps binding
   `0.0.0.0` by default. Note what this means once Phase 2 lands: anyone who
   can reach the UI can start a pipeline run, which fetches from real public
   sources under this project's contact email and rate limits. `--host
   127.0.0.1` remains the way to prevent that.
2. **Jobs run in-process, behind an interface.** A worker thread in the server
   process, reusing the run path factored out of `cli.py`. The execution
   strategy sits behind one seam so it can become a subprocess later if
   cancellation or crash isolation turns out to matter in practice. Do not
   design the UI around cancellation that does not exist yet.
3. **New front-end code is ES modules under `/admin/js/`.** `app.js` stays a
   classic script — it works, and reloading working review tooling differently
   buys nothing. The two halves do not call each other: the module side
   reaches the page through the DOM and the URL hash, both of which `app.js`
   already treats as outside input.
4. **Phases run in order**, each committed and pushed on its own.

---

## 1. Where things stand today

One stdlib `ThreadingHTTPServer` process (`pipeline/web/server.py`) serves:

| Surface | Path | Files | API |
|---|---|---|---|
| Public portal (SectorTrace) | `/` | `pipeline/web/static/public/` | `/api/v1/*` (read-only, no `restricted_`, cached 300s) |
| Operator UI | `/admin` | `pipeline/web/static/` (`index.html`, `app.js`, `styles.css`) | `/api/*` (overview, review, table, schema, query + POST decide/resolve/check-url) |

The operator UI already has: an Overview tab (pending counts, recent
decisions, parse failures), a Review queue (filters, bulk + decide-matching,
keyboard j/k/a/r/x, URL resolve with live `check-url` preview), a Database
browser with the `restricted_` confirmation gate, and a read-only SQL tab
(ro connection, `query_only`, 500-row cap, 20s timeout).

**Known defect (fix first):** when the operator UI moved from `/` to `/admin`,
`pipeline/web/static/index.html` kept absolute references to `/styles.css` and
`/app.js`. Those paths now serve the **portal's** files from
`static/public/`, so `/admin` loads the wrong stylesheet and the wrong script.
The correct references are `/admin/styles.css` and `/admin/app.js`, which the
`STATIC_FILES` map already serves.

Backend capabilities the admin UI can build on without new plumbing:

- `pipeline/registry.py` — module metadata (`MODULE_META`), dependency
  resolution (`resolve_run_order`, `resolve_run_waves`,
  `missing_dependencies`), 17 modules `m00`–`m16`.
- `pipeline/cli.py run` — the run path (migrations, `since`, `--dry-run`,
  `--limit`, `--jobs`), with the warehouse write slot handled in
  `pipeline/parallel.py` (single writer, arrival order).
- Warehouse tables useful for operations: `module_cursors`, `parse_failures`,
  `http_cache`, `review_queue`, `schema_migrations`, plus every domain table.
- `pipeline/exports/` + `cli.py export` — sheets / geojson / echarts / docs
  writers targeting `exports/output/`.

## 2. Hard constraints (these encode the project's philosophy — keep them)

1. **Stdlib server, no framework, no ASGI.** New routes go into `Handler` in
   `server.py` or a sibling module it delegates to. If `server.py` grows past
   comfort, split by concern (`admin_api.py`), not by adding Flask.
2. **No build step, no external requests.** Plain ES modules or a single
   classic script, assets served from disk, fonts local. The admin UI must
   render with the network cable unplugged.
3. **DOM discipline.** Values from the warehouse reach the page as text nodes
   or DOM-set attributes, never concatenated HTML. `static/app.js` already
   throws on `html:` props — keep that rule in any new code.
4. **Write-route guards stay.** Every new POST goes through `_read_json()`
   (JSON content-type + same-origin `Origin`). No new GET may mutate state.
5. **`restricted_` gate stays.** Any new table-reading route must apply
   `queries.is_restricted()` + explicit `reveal` flag, and no admin feature
   may leak `restricted_` rows into a portal-reachable response or an export.
6. **SQLite: connection per request**, `readonly_connection` for reads,
   `db.get_connection` for writes, always closed in `finally`.
7. **Structured logging only** — `log.info("web.<event>", ...)`; never print.
8. **Tests are pytest**, driving `build_server()` on an ephemeral port
   (existing pattern in `tests/`). Run with `uv run pytest`. Dev is Windows;
   keep paths `Path`-based.
9. **No authentication work.** Explicit project decision.

## 3. The isolation contract — "do not impact the existing frontend"

The portal is protected by construction, and then by test:

- **Namespaces.** Every new page lives under `/admin/*`; every new endpoint
  lives under `/api/admin/*`. Existing operator endpoints (`/api/review` etc.)
  stay where they are — they are already portal-invisible. Nothing new is
  added at `/`, `/js/*`, `/vendor/*`, or `/api/v1/*`.
- **No shared files.** Admin CSS/JS never imports from `static/public/` and
  vice versa. If both want a helper, it is duplicated, not shared — 40 lines
  of copied helper is cheaper than a coupling that lets an admin change
  restyle the portal.
- **Frozen public surface, enforced.** Add `tests/test_portal_isolation.py`:
  - every `STATIC_FILES` entry that does not start with `/admin` resolves
    into `static/public/`;
  - the set of non-admin static paths and the set of `/api/v1/*` routes match
    a literal list in the test (a new admin feature that touches either fails
    loudly);
  - `/admin` HTML references only `/admin/*` assets.
- **Git hygiene.** Admin work never edits `pipeline/web/static/public/**`,
  `public_queries.py`, or `public_export.py`. Parallel sessions share this
  repo: stage explicit paths, never `git commit -a`.
- **Caching untouched.** Portal responses keep `PUBLIC_MAX_AGE`; admin data
  responses stay `no-store` (the queue must never be stale).

## 4. Phased plan

Each phase is shippable alone and leaves the tree green.

### Phase 0 — repair and guardrails — **done** (commit `d2c2d0d`)

- Fixed `static/index.html` to reference `/admin/styles.css` and
  `/admin/app.js`.
- Added `tests/test_portal_isolation.py`: frozen literal lists of the portal's
  static paths and `/api/v1/` routes, directory checks on every `STATIC_FILES`
  entry, an assets-never-cross-but-links-may rule for both index pages, and
  end-to-end checks over HTTP.
- Found and removed a dead `/js/charts.js` route mapping a file that has never
  existed in this tree; it answered 500 to anyone who asked.

### Phase 1 — admin shell and navigation QoL — **done**

Much of this turned out to exist already: hash routing with filters in the
URL, back/forward, a persisted reviewer name and dense-row setting, and
debounced search. What was added:

- **Command palette** (`Ctrl+K`, or the button in the top bar), in
  `js/palette.js`. Tabs, actions, review worklists built from
  `/api/review/facets`, and every table and view from `/api/schema`, ranked
  with contiguous matches first and subsequence matching as a fallback.
  Navigates by setting the URL hash — it holds no application state and
  cannot decide a review item.
- **Theme toggle** (`js/theme.js`): three states, system / light / dark, with
  the manual choice applied inline in `<head>` so an override that disagrees
  with the OS does not flash on load.
- **Relative timestamps**: `<time>` elements with the exact value in `title=`
  and `datetime=`, re-ticked once a minute so a page left open stops claiming
  "2 minutes ago" an hour later.
- **Deep-linkable tables**: `#database?table=supplier_aliases`, so the table
  someone is reading is a link like a worklist already was.
- **Resume on open**: a bare `/admin` returns to the last place this browser
  was looking. Any hash at all is an instruction and wins.
- **Bug fixed on the way**: the `hashchange` path applied review filters
  before the facets had loaded, and setting a `<select>` to a value it has no
  option for silently does nothing — so a worklist link opened in an
  already-running tab landed on the unfiltered queue and then rewrote its own
  URL to match, losing what it pointed at. Only the initial-load path had the
  ordering right.

### Phase 2 — pipeline control room — **done**

- `pipeline/runner.py` now owns module execution — the dependency waves, the
  connection per module, the rollback on failure, the audit-count deltas. The
  CLI keeps its Rich display as a `RunObserver` implementation and its old
  function signatures, so every existing test of the progress display still
  drives the same entry points.
- `pipeline/web/jobs.py`: a job registry with one slot. A second run is
  refused with 409 and the running job's id, not queued — the warehouse has a
  single write slot, so queueing would only hide the wait. Execution sits
  behind `ThreadStrategy` so a subprocess version can replace it.
- The job log is captured off the root logger for the length of the run and
  filtered to the threads the run is using, so what the browser shows is the
  same audit trail that lands in `logs/`, not a parallel commentary.
- `pipeline/web/admin.py`: `/api/admin/modules` (registry, waves, cursors,
  queue and failure counts), and `/api/admin/run`, which refuses what
  `cli.run` refuses — unknown module, `limit` below 1, unparseable `since`.
- Pipeline tab (`js/pipeline.js`): module table with per-module Run and Dry
  buttons, run-all with a confirmation, live log tail polled by line index,
  a summary table, job history, and a pill in the tab strip while a run is
  going. A run started in one tab is picked up by another.
- **Two bugs found while building it.** `limit: 0` was silently becoming "no
  limit" — `0 == False` in Python, so a membership test against `(None, "",
  False)` swallowed the one value the check existed to refuse, turning "fetch
  nothing" into a full crawl. And `execute_module` renamed the running thread
  after the module but never restored it, so after any CLI run the main
  thread stayed named after the last module and every later log line was
  misattributed.

Still deliberately absent: cancellation (no cooperative stop exists in the
modules; a Stop button that lied would be worse than none) and scheduling.

### Phase 2 — original sketch, for reference

A new "Pipeline" tab that replaces "ssh in and run the CLI" for routine runs.

- `GET /api/admin/modules` — for each registered module: name, docstring
  first line, dependencies (+ unmet ones via `missing_dependencies`),
  `supports_since`, cursor from `module_cursors`, pending review count,
  parse-failure count, last-run summary.
- `POST /api/admin/run` — body `{module | "all", since?, dry_run?, limit?}`.
  Executes in **one background worker thread** owned by the server process,
  reusing the same code path as `cli.py run` (factor the shared core out of
  the CLI command rather than shelling out — same process, same settings,
  same write-slot discipline in `parallel.py`).
  - **Single-flight:** one pipeline job at a time; a second POST returns 409
    with the running job's id. The write slot makes concurrent runs pointless
    anyway; the UI should say so rather than queue silently.
  - Job record: in-memory registry `{id, module, args, state, started_at,
    finished_at, log_lines[]}` with a ring buffer (say 2,000 lines) fed by a
    structlog handler bound for the job's duration.
- `GET /api/admin/jobs` and `GET /api/admin/jobs/{id}?after=N` — polling with
  incremental log delivery (`after` = line index). Poll every 1–2 s while a
  job runs. Polling, not SSE: it is simpler, it survives proxies and laptop
  sleep, and the payloads are tiny.
- UI: module cards in dependency-wave order; Run / Dry-run buttons with
  `since` and `limit` inputs; a live log tail panel; badge in the header while
  a job runs. Dry-run is visually distinct (no scary confirm needed — it
  doesn't write).
- Deliberately out of scope: job cancellation (no cooperative cancel plumbing
  exists in modules; document as stretch, don't fake it with thread kills)
  and scheduling (this is an operator tool, not a daemon).

### Phase 3 — data health dashboard — **done**

- **Coverage matrix** measured against the 159 authorities responsible for
  public health, not all 347. The other 188 are non-metropolitan districts
  with no treatment role: counting against them turns "155 of the 159 that
  could have a grant" into "45% coverage", which is arithmetic and nonsense.
  The denominator is printed above the matrix in words, an every-authority
  view exists with its own warning, and both are pinned by tests.
- Candidate tables are shown beside their confirmed counterparts rather than
  folded in, because m09, m10 and m15 hold hundreds of candidates and zero
  confirmed rows, and hiding that would report the pipeline as more finished
  than it is.
- **Freshness** from the rows (`MAX(retrieved_at)` per table) rather than from
  cursors: a module that ran this morning and fetched nothing new leaves a
  fresh cursor and stale evidence. Plus every source host and when it was last
  asked, from the conditional-request cache.
- **Warehouse state**: size, free pages, and applied migrations against the
  files on disk, so a warehouse one schema behind the checkout is visible
  before a module fails on a missing column mid-run.
- **Parse-failure browser** grouped by (module, field, reason) — four failures
  from one broken parser are one bug — with the raw fragment and source URL.
- **Integrity check** as a job, reusing the Phase 2 registry and taking the
  same single slot as a run, since both want the whole warehouse.
- `queries.escape_like` extracted; the LIKE-escaping was inlined twice and
  this needed it a third time.

Not built, deliberately: the mark-as-noted column on `parse_failures`. It
would be state duplicating what a commit message or an issue already says, and
with 22 failures across three distinct reasons the grouping answers the
question the note was for. Worth revisiting if that number grows.

### Phase 3 — original sketch, for reference

A "Health" tab answering "is the warehouse fresh, complete, and clean?"

- **Freshness:** per-module last cursor / last successful run, HTTP cache
  entry counts and newest-fetch age per source domain (from `http_cache`).
- **Parse failures browser:** the overview shows a taste; this is the full
  view — filter by module/parser/reason, group identical reasons, link to
  the source URL, mark-as-noted (a note column, not deletion — a parse
  failure is a bug report and stays until the parser changes).
- **Coverage matrix:** authorities × evidence types (grant rows, budget rows,
  contracts, committee-paper hits…) as a dense grid, so "which councils are
  we blind on?" is one glance. Server-side aggregate endpoint
  (`GET /api/admin/coverage`), rendered as text-density cells, not a chart
  library — the admin stays vendor-free.
- **Warehouse stats:** db file size, per-table row counts
  (`GET /api/admin/warehouse`), applied migrations vs. files in
  `pipeline/migrations/`, `PRAGMA integrity_check` behind a button (it can
  take seconds — run it as a job, not inline).

### Phase 4 — exports manager and overrides

- **Exports tab:** trigger `export` targets (sheets/geojson/echarts/docs) as
  background jobs through the same job registry; list `exports/output/`
  recursively (name, size, mtime) via `GET /api/admin/exports`; download via
  `GET /api/admin/exports/file?id=N` where `id` indexes the *server-produced
  listing* — never a client-supplied path, so traversal is structurally
  impossible. The `--push` (Google Sheets) flag stays CLI-only: it needs
  credentials and an operator watching it.
- **Overrides viewer/editor:** show `resolve.overrides(conn)` (DB-backed)
  with add/revoke via existing resolve plumbing; show the *code-level*
  overrides (`buyer_name_overrides.py`, `authority_websites.py`) read-only
  with a note that those change via commit, not via UI.

### Phase 5 — performance and polish

Server:

- **Conditional requests for static files:** `ETag` (mtime+size) and
  `If-None-Match` → 304 in `_serve_static`. Benefits `/vendor/*` most but is
  applied uniformly; data endpoints keep `no-store`.
- **Optional gzip** for JSON responses > ~8 KB when `Accept-Encoding` allows
  (stdlib `gzip`). The coverage matrix and big table pages are the payloads
  that care. Measure before/after; skip if localhost makes it noise.
- **Index audit:** the health/coverage aggregates get `EXPLAIN QUERY PLAN`
  checks in tests; add indexes by migration only where a scan actually hurts.

Client (admin only):

- Debounced search inputs (250 ms) where not already; `AbortController` on
  superseded fetches so a fast typist doesn't render a stale page.
- Big-table rendering: cap DOM rows per page (the pager exists); add a cell
  drawer for long values instead of giant rows; "copy row as JSON".
- SQL tab: query history (localStorage, last 50), named snippets, schema-aware
  autocomplete from `/api/schema`, an `EXPLAIN QUERY PLAN` button, export
  results as CSV client-side.
- Database tab: hide/show columns, jump-links — a cell in a column named
  `ons_code`, `provider_key`, or `*_id` becomes a link that opens the obvious
  target table pre-filtered.
- Review queue: single-click **undo** on the last decision (it is just
  `decide(ids, "pending")`), per-item decision history, saved filter presets.

## 5. Testing strategy

- Every new `/api/admin/*` route: happy path + guard path (bad JSON, wrong
  content type, cross-origin `Origin`, restricted table without `reveal`).
- Job runner: a fake module registered in-test that emits log lines and
  sleeps briefly; assert single-flight 409, incremental `after=` delivery,
  state transitions, and that a job failure lands in the job record rather
  than killing the server.
- Portal isolation tests from Phase 0 run in every phase.
- Nothing in tests touches the real warehouse: ephemeral temp db via the
  existing settings fixture pattern.

---

## 6. The implementation prompt

Paste everything between the rules into a fresh session, plus one line naming
the phase, e.g. "Implement Phase 0 and Phase 1."

---

You are working in `C:\Users\Jon\cglpay.us` — a Python evidence pipeline
(`pipeline/` package, uv-managed, Windows) whose stdlib-only web server
(`pipeline/web/server.py`, `ThreadingHTTPServer`, no framework) serves two
front ends: a public portal at `/` from `pipeline/web/static/public/` with API
`/api/v1/*`, and an operator/admin UI at `/admin` from `pipeline/web/static/`
(`index.html`, `app.js`, `styles.css`) with API `/api/*` plus POST routes for
review decisions. Read `docs/admin-ui-plan.md` in full before writing code —
it is the plan you are executing, phase by phase, and its section 2 lists hard
constraints and section 3 the portal-isolation contract. The non-negotiables:
the public portal must be byte-for-byte unaffected (never edit
`pipeline/web/static/public/**`, `pipeline/web/public_queries.py`,
`pipeline/web/public_export.py`, or any `/api/v1/*` route; all new endpoints
under `/api/admin/*`, all new assets under `/admin/*`); no authentication
(explicit decision — the loopback-default bind plus the existing JSON
content-type + same-origin-Origin write guard is the security model, keep it
on every new POST); no web framework, no build step, no external requests, no
new runtime dependencies without strong cause; warehouse values reach the DOM
as text nodes only, never concatenated HTML (`static/app.js` enforces this —
follow it); `restricted_` tables keep their explicit-reveal gate and never
appear in admin exports; SQLite is connection-per-request
(`queries.readonly_connection` for reads, `db.get_connection` for writes,
close in `finally`); logging is structlog events named `web.*`. Reuse what
exists before building: `pipeline/registry.py` (module metadata, dependency
waves), the `run` command in `pipeline/cli.py` (factor its core out for the
job runner rather than shelling out; `pipeline/parallel.py` already
serialises the warehouse write slot), `module_cursors` / `parse_failures` /
`http_cache` tables for health data, and `pipeline/exports/` for the exports
tab. Write pytest tests alongside every route following the existing pattern
(build_server on an ephemeral port, temp warehouse), including the
portal-isolation tests described in the plan's Phase 0, and run
`uv run pytest` before declaring anything done. Match the house code style:
comments explain constraints and reasoning, not mechanics. This repo is
shared by parallel sessions: stage explicit paths only, never `git commit -a`;
commit when a phase is green and push after committing.

---
