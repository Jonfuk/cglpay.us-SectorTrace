# Whole-project upgrade audit — prompt

Paste everything below the rule into a fresh Claude Code session opened in
`C:\Users\Jon\cglpay.us`. Nothing above the rule is part of the prompt.

Recommended: start the session in plan mode, and add one line at the end
naming what you want first, e.g. "Do the audit only — stop at the roadmap"
or "Audit, then implement Phase 1 once I approve it."

---

You are working in `C:\Users\Jon\cglpay.us`: an England-wide substance misuse
sector evidence pipeline (Python 3.10+, `uv`-managed, developed on Windows)
that collects public-domain evidence for a trade union pay campaign, plus a
stdlib-only `ThreadingHTTPServer` that serves a public evidence portal at `/`
and an operator/admin UI at `/admin`.

Your task is a **complete upgrade audit followed by a phased implementation
plan**. I want every worthwhile improvement across features, data quality,
performance, web UI, operations, security and testing found, evidenced,
argued for or against, and then arranged into phases I can review before any
code is written.

## Part 0 — Read before you form any opinion

Read these in full. Do not skim, and do not start proposing until you have:

- `README.md` — the project's own account of what it collects, what it
  refuses to compute, the module dependency waves, the write-slot discipline,
  the portal and the review UI.
- `docs/admin-ui-plan.md` — the phased plan for `/admin`, **now complete:
  Phases 0–5 are all done and committed.** Read it as a design record rather
  than a backlog. Two things in it matter more than the feature list: each
  phase records what it found on the way and what it *deliberately did not
  build*, and Phase 5 measured before changing anything and concluded "leave
  it alone" for most of what it looked at. Your roadmap starts where that
  document stops. Do not re-propose anything it delivered, and do not
  re-propose what it explicitly declined — schema-aware SQL autocomplete,
  hide/show columns, the long-value cell drawer, copy-row-as-JSON, saved
  filter presets, the `parse_failures` mark-as-noted column — unless you have
  evidence it did not have. Saying "the plan rejected X and was right" is a
  finding; silently re-listing X is noise.
- `docs/CAVEATS.md`, `docs/SOURCES.md`, `docs/DATA_DICTIONARY.md`.
- `pipeline/` in whatever depth each area needs: `registry.py`, `runner.py`,
  `parallel.py`, `db.py`, `http.py`, `config.py`, `cli.py`, `console.py`,
  `meters.py`, `exports/`, `web/` (`server.py`, `admin.py`, `queries.py`,
  `public_queries.py`, `health.py`, `jobs.py`, `resolve.py`, `artefacts.py`),
  `web/static/` (both the admin bundle and `static/public/`), all 17 modules
  `m00`–`m16`, and `migrations/0001`–`0027`.
- `tests/` — what is covered, and more importantly what is not.
- `git log --oneline -40` and the current `git status`/`git diff`. Commit
  messages in this repo say *why*; they are part of the design record.

Then state, in five sentences or fewer, what this project is optimising for.
If your understanding of that is wrong, every proposal after it is wrong too,
so I want it on the record before the findings.

## Part 1 — Constraints your proposals must respect

These are settled decisions, not defaults to be re-litigated. A proposal that
violates one is only acceptable if you flag it explicitly as
constraint-breaking and argue the case; do not smuggle it in.

1. **Evidential integrity above all.** Every row carries source URL, fetch
   time and SHA-256 of the exact bytes archived under `data/raw/`. Nothing is
   inferred, interpolated or defaulted; unparseable is `NULL` plus a
   `parse_failures` row; anything needing judgement goes to `review_queue`.
   No proposal may weaken this to gain coverage, speed or polish.
2. **Evidence layers stay separate.** No composite scores, ratios or
   cross-source arithmetic that `docs/CAVEATS.md` forbids.
3. **Personal data is segregated** in `restricted_` tables, excluded from
   every export and every portal-reachable response, enforced by
   `guard_columns()` and the reveal gate — not by intention.
4. **Collection stays polite.** robots.txt respected, process-wide per-host
   rate limiting, `Retry-After` honoured, conditional requests, identifying
   User-Agent with `CONTACT_EMAIL`. Any performance idea that raises request
   rate against a source is out of scope; concurrency across *different*
   hosts is the only lever.
5. **Stdlib web server. No framework, no ASGI, no build step, no CDN, no
   external runtime requests.** Both front ends must render with the network
   cable unplugged. New runtime dependencies need a strong argument.
6. **Portal isolation contract** (`docs/admin-ui-plan.md` §3, pinned by
   `tests/test_portal_isolation.py`): admin work never edits
   `pipeline/web/static/public/**`, `public_queries.py`, `public_export.py`,
   or any `/api/v1/*` route. New admin endpoints live under `/api/admin/*`,
   new admin assets under `/admin/*`. Portal *improvements* are in scope for
   this audit — but they are portal work, proposed and phased separately from
   admin work, never as a side effect of it.
7. **No authentication.** Explicit project decision. The security model is the
   JSON content-type + same-origin `Origin` guard on writes, plus `--host
   127.0.0.1` when the LAN is not trusted. Do not propose an auth system; *do*
   report anything that makes the no-auth posture more dangerous than the
   README claims.
8. **DOM discipline.** Warehouse values reach the page as text nodes or
   DOM-set attributes, never concatenated HTML.
9. **SQLite discipline.** Connection per request/module, `readonly_connection`
   with `query_only` for reads, `db.get_connection` for writes, closed in
   `finally`, process-wide write slot in arrival order, commit per unit of
   work rather than once at the end.
10. **House style.** Comments explain constraints and reasoning, not
    mechanics. Structured logging (`log.info("web.<event>", ...)`), never
    `print`. Tests are pytest, offline and fixture-backed by default; live
    tests sit behind the `integration` marker. Paths are `Path`-based —
    development is Windows.
11. **Repo hygiene.** Parallel Claude sessions share this checkout: stage
    explicit paths, never `git commit -a`. Commit when a phase is green and
    push to origin.

## Part 2 — The audit

Sweep every axis below. For each, I want what is *actually there* — cited as
`path:line` — not what a project like this usually has. Where you assert a
performance problem, measure it or say plainly that you have not.

**A. Feature and coverage (`F-nn`).** Gaps in the evidence base itself: source
coverage vs. the 159 public-health authorities, sources not yet collected,
modules that produce candidates but never confirmed rows (`m09`, `m10`, `m15`),
the unverified workforce census, entity resolution between providers /
companies / charities / CQC locations, change-over-time (is anything tracked
longitudinally, and should it be?), the verification workflow that turns
candidates into evidence, FOI follow-through, and what a union researcher can
*ask* this warehouse that it currently cannot answer.

**B. Data quality and provenance (`D-nn`).** `parse_failures` by module and
reason and what each says about a parser, caveat coverage vs. `_note` columns,
`review_queue` composition and what would actually clear it, migration and
schema drift, the data dictionary's fidelity, dedupe keys, idempotency of
re-runs, and any place where an empty result is indistinguishable from a
failed one.

**C. Pipeline performance (`P-nn`).** HTTP layer: cache hit rate, conditional
request coverage, connection reuse, timeouts, retry/backoff behaviour.
Concurrency: wave composition, `MAX_FETCH_WORKERS`, whether `--jobs > 1` is
actually safe to make default and what evidence would prove it. SQLite:
pragma settings, index coverage against real query plans (`EXPLAIN QUERY
PLAN`), transaction granularity, batch insert patterns, write-slot hold times.
PDF parsing cost. Memory on the large modules. Resumability after a kill.
Give expected magnitudes, and say which claims are measured and which are
inferred.

**D. Web server performance (`P-nn` continued).** Phase 5 already landed
ETag/304 on static assets (weak tags keyed on mtime+size), gzip above 4 KB for
text types with `Vary`, and query-plan assertions in
`tests/test_web_performance.py`. So: check those hold rather than propose them
— is the gzip threshold right, are the cache headers correct per surface, do
the pinned query plans cover the endpoints that actually hurt? Then the ground
Phase 5 did not cover: per-endpoint query cost and N+1 patterns beyond the
coverage aggregates, payload sizes and pagination, what the server does under a
slow client or a browser left open on a polling tab, and the freshness panel —
Phase 5 measured it at 1.6 s on contracts, declined the twenty-table
`retrieved_at` index as too expensive on every insert, and moved it to its own
route. Revisit only with an approach that does not pay that cost.

**E. Admin UI (`U-nn`).** The tabs exist and Phase 5 shipped undo on the last
decision, jump-links between related tables, table search in the URL, and SQL
history / EXPLAIN / CSV. Look for what the operator still cannot do: review
queue throughput at the size the queue actually is, per-item decision history,
keyboard coverage across every screen, empty and error states, what happens
when a job fails or the browser is closed mid-run, and what an operator today
still has to leave the browser and open a terminal for. Ground every finding in
the real queue composition, not in what an admin UI usually has.

**F. Public portal UX (`W-nn`).** Accessibility against WCAG 2.2 AA — keyboard
paths, focus management, contrast, chart and map alternatives for screen
readers, motion. Performance budget and first-paint on a cold cache. Mobile
layout. Print and PDF output, since this evidence gets printed. Deep-linking
and shareable state. Citation and provenance ergonomics. The no-JS story. Page
metadata. How a caveat that must not be dismissed behaves at every breakpoint.
Anything the portal currently draws that the data does not support, or refuses
to draw where it now could.

**G. Operations and reliability (`O-nn`).** Warehouse backup and restore,
migration safety and reversibility, crash recovery mid-run, job history
persistence across restarts, log rotation and retention, scheduled/unattended
runs, run summaries and diffs between runs, CI, the absence of a root
`CLAUDE.md`, packaging, and what a second person would need to run this from
scratch.

**H. Security and privacy posture (`S-nn`).** Given no-auth is settled: SSRF
surface on the URL-check/resolve path, path traversal on any file-serving
route, the SQL box's blast radius, DoS through run/export endpoints, response
headers and CSP, `restricted_` leakage paths including via exports, logs,
error messages and job output, secrets handling, and whether the README's
security warnings still match the code now that the admin UI can start
pipeline runs, write exports and serve file downloads.

**I. Testing and developer experience (`T-nn`).** Coverage gaps by module and
by route, fixture staleness vs. live sources, contract tests for source shape,
performance regression tests, absence of lint/typecheck tooling (ruff, mypy)
and whether adding it is worth the churn here, test runtime, and flakiness.

For every finding, record: **ID · title · evidence (`path:line`) · what it
costs today · what changes for a user (operator, researcher, or the union) ·
effort S/M/L · risk to the constraints in Part 1 · dependencies on other
findings · how it will be verified.**

## Part 3 — Judgement, not a wish list

This project's culture is to record what was deliberately *not* built and why
(see the "Not built, deliberately" notes in `docs/admin-ui-plan.md`). Match it:

- Include a **Rejected** section listing ideas you considered and dismissed,
  each with the reason. An idea that is obvious and wrong is worth a line so
  nobody proposes it again in three months.
- Do not pad. If an axis is in good shape, say so in one sentence and move on.
- Flag anything where the honest answer is "measure first", and say what
  measurement would settle it.
- Where two findings are the same underlying defect, merge them.

## Part 4 — The deliverable

Write `docs/upgrade-roadmap.md`. Structure it exactly like this:

1. **What this project optimises for** — your five sentences from Part 0.
2. **Headline** — the five findings that matter most, one line each, with IDs.
3. **Findings register** — every finding, grouped by axis, in the field format
   from Part 2. This is the reference the phases point at.
4. **Quick wins** — findings that are small, safe and independently
   shippable, ready to be done in an afternoon.
5. **Phases.** Each phase gets: a one-line goal, the finding IDs it delivers,
   explicit out-of-scope, the acceptance criteria (including which tests must
   exist and pass), the risk and the rollback, and its commit plan. Phases must
   be ordered so each is shippable alone and leaves the tree green, and so no
   phase depends on a later one. Say roughly how much work each is.
6. **Rejected** — from Part 3.
7. **Open questions for me** — decisions that are mine, not yours, each with
   your recommendation and what it depends on.

Cite `path:line` throughout. Do not write prose where a table is clearer, and
do not write a table where one sentence would do.

## Part 5 — Rules for the audit itself

- **The audit is read-only.** No production code changes, no migrations, no
  writes to `data/warehouse.db` before I approve the plan. Read the warehouse
  read-only for statistics — row counts, `parse_failures` groupings,
  `review_queue` composition, query plans — and say so when a number comes
  from my live data.
- **Do not run live-source integration tests** (`-m integration`) or any full
  crawl. The offline suite (`uv run python -m pytest`) is fine and you should
  run it to establish the baseline is green before you propose anything.
- Anything you learn from running the server locally, run it on a non-default
  port bound to `127.0.0.1` and stop it when done.
- **Parallel sessions share this checkout**, so the working tree may not be
  clean and what is in it may not be yours. Check `git status` before you
  start and again before you stage. Touch nothing you did not write. The only
  file this stage produces is `docs/upgrade-roadmap.md`, and it is the only
  path you stage.

## Part 6 — After I review

Stop when the roadmap is written and hand it to me with a short summary. Do
not start implementing.

When I approve phases, then:

- Implement **one phase at a time**, in order, in full. No partial phases and
  no wandering into the next one.
- Tests first where the phase is behavioural: every new route gets a happy
  path plus its guard paths (bad JSON, wrong content type, cross-origin
  `Origin`, restricted table without `reveal`). `tests/test_portal_isolation.py`
  must pass in every phase.
- Run `uv run python -m pytest` before you call a phase done, and tell me the
  result honestly — including which tests you did not run.
- For performance phases, report before/after numbers on the same machine and
  the same warehouse, and say when a difference is inside the noise.
- Update `docs/upgrade-roadmap.md` as each phase lands: mark it done, record
  what changed from the plan and what you found on the way, in the same voice
  as the existing plan document. The roadmap is a living record, not a
  historical artefact.
- Update `README.md` and `docs/` where behaviour a user relies on has changed.
- Commit per phase with explicit paths (never `git commit -a`), a message that
  explains why in this repo's style, and push to origin.
- If a phase turns out to be wrong once you are inside it, stop and tell me
  rather than redesigning it silently.
