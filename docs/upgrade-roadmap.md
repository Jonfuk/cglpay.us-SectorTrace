# Upgrade roadmap

Status: audit written 2026-08-13 against commit `841bd49` with a clean tree;
baseline `uv run python -m pytest` was green before any of it (**1215 passed,
1 skipped, 18 deselected, 422s**). **Phases 1–3 and 5 are done, Phase 4 is
partly done** (F-01 and U-01 closed; F-03 and D-04 open); Phases 6–7 are not
built. Each phase records what changed from the plan as it lands.

Numbers marked **[live]** come from Jon's own `data/warehouse.db`, read
read-only. Numbers marked **[measured]** were timed here. Everything else is
inferred from the code and says so.

## 1. What this project optimises for

It optimises for a figure that can still be defended a year later in a room
where someone disputes it. Every design choice that looks like a limitation —
`NULL` over a guess, candidates that never auto-promote, no arithmetic across
evidence layers, no headline contract total — is that same trade taken again:
a smaller defensible dataset over a larger plausible one. Its second priority
is that the pipeline stay welcome at its sources, which is why the rate limit
is process-wide and concurrency only ever spans different hosts. Its third is
that a human can check any of it, which is what the raw archive, the
provenance companions, the caveats and the review queue are all for. Speed,
coverage and polish are pursued only where they cost none of the above.

## 2. Headline

| | Finding | Why it leads |
|---|---|---|
| 1 | ~~**F-01**~~ *(closed, Phase 4)* — 1,941 candidates, zero promoted to evidence **[live]** | Three modules collect and nothing crosses into the evidence base. The gap between "collected" and "usable" is the project's biggest. |
| 2 | ~~**D-02**~~ *(closed, Phase 1)* — a dry run and a real run were indistinguishable afterwards | `m13` logged `run_complete, rows: 238,407` and wrote nothing. Nothing in the log or warehouse says which it was. |
| 3 | ~~**O-02**~~ *(closed, Phase 3)* — no backup of a 242 MB warehouse and a 3.6 GB archive **[live]** | Hours of deliberately slow crawling, reconstructible only by redoing it. |
| 4 | ~~**S-01**~~ *(closed, Phase 5)* — `check-url` would fetch any host and report whether it answered | Unauthenticated, binds `0.0.0.0` by default, follows redirects. |
| 5 | ~~**D-01**~~ *(closed, Phase 1)* — this warehouse was one migration behind the checkout **[live]** | `0028` is on disk, not in `schema_migrations`. The condition the health tab exists to catch, currently true. |

## 3. Findings register

Effort: S = under a day, M = a few days, L = a week or more.

### A. Feature and coverage

**F-01 · Candidates never become evidence · L — closed in Phase 4**
- Evidence **[live]**: `cdp_document_candidates` 406 → `cdp_documents` 0; `committee_paper_candidates` 694 → `committee_papers` 0; `foi_request_candidates` 841 → `foi_requests` 0. `verified = 1` count across all candidate tables: **zero**.
- Costs today: 1,941 collected rows sit outside the evidence base. The only documented promotion path is hand-written SQL ([docs/verification/cdp_candidates.md:7](docs/verification/cdp_candidates.md:7)), and the review UI deliberately does not promote ([README.md:445](README.md:445)).
- Changes for: the researcher — this is the difference between "we found council papers" and "we can cite one".
- Risk: **high**. Promotion is exactly the judgement the project refuses to automate. Any design must keep a human deciding each row and record who and when, like `review_decisions` already does.
- Depends on: nothing. Verified by: a test that promotion writes both the evidence row and its decision record, and that nothing reaches an evidence table without one.

**F-02 · `m13_la_budgets` has never landed in this warehouse · S — closed in Phase 1**
- Evidence **[live]**: `la_revenue_budgets` 0 rows, `la_budget_publications` 0 rows, no `module_cursors` entry. [logs/m13_la_budgets.log](logs/m13_la_budgets.log) last line records `budgets.run_complete documents=4 rows=238407`, and four `budgets.sheet_processed` events totalling the same.
- Costs today: an entire evidence type — what councils budget, against what Module 11 says they were allocated — is absent, and the absence looks identical to a module that ran fine.
- Most likely a `--dry-run` (the commit guard at [pipeline/modules/m13_la_budgets.py:391](pipeline/modules/m13_la_budgets.py:391) is correct, and the runner rolls back at [pipeline/runner.py:120](pipeline/runner.py:120)). **Not proven** — see D-02, which is why it cannot be proven.
- Verified by: a real run writing rows, plus D-02 making the next one self-evident.

**F-03 · Workforce census stays unverified · M — still open; deferred from Phase 4**
- Evidence **[live]**: `workforce_census_metrics` 68 rows, all `verified = 0`. Portal correctly renders them as awaiting verification ([README.md:396](README.md:396)).
- Same shape as F-01 — a markdown worklist and manual SQL. Fold into the same promotion mechanism rather than building a second one.

**F-04 · Resumability is real for one module · S to establish**
- Evidence **[live]**: `module_cursors` holds 2 rows, both `m01_procurement`. [README.md:108](README.md:108) describes resumable cursors as a property of modules generally.
- Inferred, not confirmed: the other 16 may re-derive position cheaply or may re-crawl. Worth one pass to find out and then either fix the modules or soften the README.

**F-05 · Nothing is tracked over time · L, and a decision before a design**
- Evidence: every domain table upserts on a natural key (e.g. [pipeline/modules/m13_la_budgets.py:372](pipeline/modules/m13_la_budgets.py:372)); a re-run overwrites in place.
- Costs today: the warehouse can say what a CQC rating or advertised band *is*, never that it changed. For a pay campaign, the change is often the claim.
- Risk: **high** — history multiplies row counts and invites exactly the cross-year differencing [docs/CAVEATS.md:25](docs/CAVEATS.md:25) forbids for the census. See Open questions.

### B. Data quality and provenance

**D-01 · Warehouse is a migration behind · S — closed in Phase 1**
- Evidence **[live]**: `schema_migrations` holds 27 filenames, newest `0027_authority_url_overrides.sql`; `pipeline/migrations/` holds 28, including `0028_pfd_concerns_source.sql` (added in `847a937`).
- The health tab was built to make this visible ([docs/admin-ui-plan.md:257](docs/admin-ui-plan.md:257)). The finding is not that it is invisible — it is that the condition is live right now and unremarked, so the panel is either unread or not loud enough.

**D-02 · A dry run leaves no trace that it was one · S — closed in Phase 1**
- Evidence: [pipeline/runner.py:120](pipeline/runner.py:120) rolls back and returns `status: ok`; no log event carries `dry_run`; `grep -c dry_run logs/m13_la_budgets.log` → 0.
- Costs today: F-02 cannot be diagnosed from the record. A module reporting `run_complete` with 238,407 rows and an empty table is the single most misleading state this pipeline can be in, and it contradicts the property [README.md:345](README.md:345) claims.
- Fix is small: log the run parameters at module start and stamp the outcome `dry_run: true`; make the CLI and job summary say "wrote nothing (dry run)".
- Verified by: a test asserting a dry run's summary and log distinguish it.

**D-03 · Parse failures are healthy — no action**
- **[live]** 22 rows: 20 are one m08 reason (`no 'Ref :' field found`), plus one m03 pension-costs line and one m11 amount. That is a source-shape note and two singletons, not a parser problem.

**D-04 · 88% of the queue is three item types, and one may be obsolete · M**
- Evidence **[live]**: `unmatched_buyer_name` 2,667, `pfd_concerns_in_pdf_only` 1,067, `possible_group_company` 493, of 4,815 total.
- `pfd_concerns_in_pdf_only` was filed because the concerns were PDF-only ([docs/CAVEATS.md:159](docs/CAVEATS.md:159)); commits `c17eaf1` and `847a937` taught m08 to read those PDFs. So up to 1,067 items may now be answerable by re-running rather than by a human — but they will not clear themselves, because a decided item stays decided and a pending one is only refreshed ([README.md:470](README.md:470)).
- Costs today: a queue whose bulk is undecidable one-at-a-time trains its operator to ignore it.

**D-05 · "Approved" on an unknown-URL item does not mean it was answered · S**
- Evidence **[live]**: 132 `authority_website_unknown` and 53 `committee_url_unknown` are `approved`, while `authority_url_overrides` holds 191 rows. Approval records a judgement; answering writes an override ([README.md:445](README.md:445)). The two counts are close enough to look equivalent and are not.
- Worth one query to confirm they correspond, and a UI distinction if they do not.

### C. Pipeline performance

**P-01 · Every commit is an fsync · S to try, MEASURE FIRST**
- Evidence: [pipeline/db.py:289](pipeline/db.py:289) sets `busy_timeout` and `foreign_keys`; WAL at [pipeline/db.py:272](pipeline/db.py:272). `synchronous` is never set, so it is SQLite's default `FULL`.
- The project deliberately commits per unit of work ([README.md:326](README.md:326)) — so this is paid on every commit of every module, by design.
- `synchronous = NORMAL` under WAL is the conventional trade and risks losing the last transactions on power loss, not corruption. For a warehouse that is re-runnable from an archive, that is close to free — but the size of the win is unmeasured. Measure with a fixed-size m01 slice before and after.

**P-02 · The raw archive grows without bound · M — measured and documented in Phase 3**
- Evidence **[live]**: `data/raw` is **3.6 GB across 6,322 files**; the warehouse it backs is 242.7 MB.
- It is the audit trail, so deletion is not the answer. Compaction, per-source retention, or simply measuring and documenting the growth curve is.

**P-03 · `--jobs > 1` is still opt-in · M, evidence-gated**
- `--jobs 1` remains the default ([README.md:198](README.md:198)), with the parallel path covered by [tests/test_parallel.py](tests/test_parallel.py) and [tests/test_run_waves.py](tests/test_run_waves.py) (332 and 482 lines).
- What would settle it is one full `--jobs 4` run compared against a serial one on row counts, review items and parse failures — not another test.

### D. Web server performance

**P-04 · No read timeout; a stalled client keeps its thread · S — closed in Phase 2**
- Evidence: [pipeline/web/server.py:882](pipeline/web/server.py:882) builds a `ThreadingHTTPServer` with `daemon_threads = True` and `protocol_version = "HTTP/1.1"`; no `timeout` is set on the handler, so `BaseHTTPRequestHandler.timeout` stays `None`.
- Thread-per-connection is unbounded. On a trusted LAN this is a nuisance rather than a risk, and one class attribute fixes it.

**P-05 · Phase 5's conclusions still hold — no action**
- ETag/304 and gzip are in place ([pipeline/web/server.py:406](pipeline/web/server.py:406), [:219](pipeline/web/server.py:219)) with query plans pinned in [tests/test_web_performance.py](tests/test_web_performance.py). The freshness scan remains the shape Phase 5 priced: 20 tables carry `retrieved_at`, the largest 98,588 rows **[live]**. Nothing here to revisit without a cheaper approach than the twenty-table index it already declined.

### E. Admin UI

**U-01 · No bulk path for the queue's bulk · M — closed in Phase 4** — the operational half of F-01/D-04. Deciding a filtered set exists ([README.md:440](README.md:440)); *answering* one does not.

**U-02 · Job history dies with the process · S — closed in Phase 1**
- Evidence: [pipeline/web/jobs.py:192](pipeline/web/jobs.py:192) — the registry is in-memory, log lines in a ring buffer.
- After a restart there is no record that a run happened; `logs/` has the lines but nothing ties them to a job. A row per job in the warehouse would close it.

### F. Public portal

**W-01 · No `<noscript>`, and the page is entirely JS-rendered · S — closed in Phase 2**
- Evidence: [pipeline/web/static/public/index.html](pipeline/web/static/public/index.html) ships a header, nav and filter bar; the sections render from `/api/v1/*`. `grep -c '<noscript>'` → 0.
- With JS off or broken, a public evidence site meant to be cited shows chrome and nothing else. A `<noscript>` naming the API and the exports is a few lines.

**W-02 · No print stylesheet · S — closed in Phase 2**
- Evidence: `@media print` appears zero times in either [pipeline/web/static/public/styles.css](pipeline/web/static/public/styles.css) or the admin sheet. This evidence gets printed and taken into rooms; a caveat that does not survive printing is a caveat that got separated from its figure, which is the failure [README.md:381](README.md:381) is written against.

**W-03 · Accessibility is in good shape — no action.** `lang="en-GB"`, a skip link, `aria-label`led nav, `role="combobox"`/`listbox` on the typeahead, `:focus-visible` styles and `prefers-reduced-motion` handling are all present. Spot-checked, not audited against WCAG 2.2 line by line.

### G. Operations

**O-01 · No CI · M** — no `.github/`. 1,215 tests, 7 minutes **[measured]**, Windows-only development, a repo several sessions commit to concurrently.

**O-02 · No backup or restore · M — closed in Phase 3** — nothing in `pipeline/` performs a backup (no `VACUUM INTO`, no dump helper). 242.7 MB warehouse plus 3.6 GB archive **[live]**, rebuilt only by re-crawling at one request per two seconds per host.

**O-03 · Logs never rotate, and tests write into the real `logs/` · S — half closed in Phase 2** (tests no longer write there; rotation is still absent)
- Evidence: no rotation in [pipeline/logging_conf.py](pipeline/logging_conf.py); `logs/` is 7.2 MB **[live]** of which `fake_insert_only_for_tests.log` is 5.0 MB, alongside `bogus_module.log` and `fake_writer_for_tests.log`.
- A test run polluting the operator's log directory is the kind of thing that erodes trust in the directory.

**O-04 · No root `CLAUDE.md` · S** — the conventions are real, enforced and currently learned by reading `docs/admin-ui-plan.md` §2 and this file. Several sessions a day re-derive them.

### H. Security and privacy

**S-01 · `check-url` is an unauthenticated fetcher · M — closed in Phase 5**
- Evidence: [pipeline/web/resolve.py:75](pipeline/web/resolve.py:75) accepts any `http`/`https` URL whose netloc contains a dot — which admits `192.168.1.1`, `10.0.0.5` and any internal name — and the client follows redirects ([pipeline/http.py:373](pipeline/http.py:373)). The server binds every interface by default ([README.md:483](README.md:483)).
- It is bounded: robots is respected, the rate limit is shared, and the response is not returned verbatim. What it does return is whether a host answered and what it looked like, which is a port-scan primitive on the operator's LAN.
- Fix without breaking the feature: refuse non-public IP literals and resolved addresses before fetching, and log refusals. The legitimate input is a council's public website.

**S-02 · No CSP, `X-Frame-Options` or `Referrer-Policy` · S — closed in Phase 2**
- Evidence: [pipeline/web/server.py:255](pipeline/web/server.py:255) sets `X-Content-Type-Options` and nothing else.
- DOM discipline is the real XSS defence and it is enforced; this is the cheap second layer, and a `frame-ancestors`/`X-Frame-Options` pair also stops a page on the LAN framing `/admin` and driving it.

**S-03 · The README's security section predates what `/admin` can now do · S — closed in Phase 2**
- [README.md:483](README.md:483) warns that anyone reachable can read the warehouse and decide items. Since Phases 2–4 they can also start pipeline runs against live sources under this project's contact email, write exports and download files. [docs/admin-ui-plan.md:24](docs/admin-ui-plan.md:24) records that consequence; the README a new operator reads does not.

### I. Testing and developer experience

**T-01 · No lint or typecheck · S** — no ruff, mypy, black or pre-commit in [pyproject.toml](pyproject.toml). With 1,215 passing tests the marginal value is real but modest; the argument for ruff is consistency across concurrent sessions, not defect-finding.

**T-02 · A 7-minute suite is a suite people skip · M** — 422s **[measured]**. Worth profiling for the slow minority before optimising, and `-p no:cacheprovider`/parallelism are cheaper than restructuring.

**T-03 · Per-module coverage is complete — no action.** Every `m00`–`m16` has a matching `tests/test_m*.py`, plus route, guard, concurrency, provenance and portal-isolation suites.

## 4. Quick wins

Small, safe, independently shippable, no dependencies:

| ID | What | Why now |
|---|---|---|
| D-02 | Log run parameters and stamp dry runs | Makes F-02 diagnosable instead of mysterious |
| D-01 | Apply `0028` to the working warehouse | One command; the drift is live |
| P-04 | `timeout` on the handler | One class attribute |
| S-02 | CSP, `X-Frame-Options`, `Referrer-Policy` | Three headers next to the one already there |
| W-01 | `<noscript>` on the portal | A few lines, and it is a public site |
| O-03 | Point test logging at a temp dir | Stops tests writing 5 MB into `logs/` |
| S-03 | Bring the README's warning up to date | Text only, and it is currently understated |

## 5. Phases

### Phase 1 — Make a run's outcome unambiguous · S — **done** (`7f457fd` and this commit)

Delivered D-02, D-01, F-02, U-02. Suite green throughout: 1215 → **1229
passed**, 1 skipped.

- **Every run says what it was asked and what it did.** `module.starting`
  carries `dry_run`, `since` and `limit` before the work begins;
  `module.finished` carries `dry_run` and `wrote` after it. Both land in the
  module's own log file, which is where the question gets asked six months
  later.
- **The summary table disowns its own numbers on a dry run** — retitled, and
  the column renamed to "Rows not written". The count is still shown, because
  what a run *would* have written is the useful part; it just must never
  appear bare. The table gets screenshotted, and the terminal warning
  underneath it does not travel with the screenshot.
- **`job_runs`** (migration `0029`) keeps the fact of a job, not its log. A row
  still saying `running` at startup is corrected to `interrupted`. Ids continue
  from the highest persisted one, so a job id means one job for the life of the
  warehouse. The store swallows its own failures — there is a test that runs a
  job against a warehouse with no schema, because bookkeeping that can refuse a
  run is worse than bookkeeping that is missing a row.
- **`0028` and `0029` applied** to the working warehouse: 27 → 29. D-01 closed.
- **F-02 settled, and it was a dry run.** `m13_la_budgets` re-run for real
  wrote **477,199 budget rows** across 2023-24 to 2026-27 and 10 publication
  rows in 119s, including 13,184 rows in the Public Health section, which
  populates `v_la_public_health_budget` for the first time. 319 of the 421 ONS
  codes join to `authorities`; the remaining 102 are police, fire, park and
  combined authorities whose absence the module documents as correct.
- **What the re-run recorded alongside the rows:** 5 `budget_no_ra_attachment`
  review items, and 2 `amounts_multiplier` parse failures where a sheet's
  denomination could not be read, leaving those amounts NULL rather than
  assumed — the module behaving as designed. 15,572 of 477,199 amounts are
  NULL for that reason.

**Found on the way:** the previous run had discovered 4 publications; this one
found 10, so the earlier `rows=238407` was also a smaller crawl than today's.
Nothing was lost — but it is a second reason the old log could not be read as
a measurement of anything.

### Phase 2 — Housekeeping that should not wait · S — **done** (`fb238ee`, `530b9cc`)

Delivered P-04, S-02, S-03, W-01, W-02, O-03. Suite 1229 → **1256 passed**, 1
skipped. Committed as server work and portal work separately, as planned.

- **CSP is computed per surface, not shared.** The portal has no inline script,
  so it gets `script-src 'self'` with nothing added. The operator page has
  exactly one — the theme guard that must run before the stylesheet paints —
  allowed by a hash read from the file being served, so editing that script
  cannot silently break the page. A test recomputes the hash from the file
  rather than pinning a literal. `style-src` keeps `'unsafe-inline'` on both:
  the operator page has five style attributes and the vendored libraries set
  styles at runtime, and styles are a defacement vector rather than an
  exfiltration one.
- **`frame-ancestors 'none'` plus `X-Frame-Options: DENY`** is the part that
  earns its place today, given no authentication by design.
- **`Referrer-Policy: same-origin`**, because warehouse state travels in the
  URL hash — `#review?module=…`, `#database?table=…`.
- **Verified in a browser, not only in tests.** Both pages were loaded against
  the real warehouse on a scratch port: no console errors, no CSP violations,
  charts and tables intact. Header tests cannot tell you a vendored library
  still works.
- **Read timeout on the handler** (P-04): 30s, since `ThreadingHTTPServer`
  starts a thread per connection with no ceiling and the base class blocks on
  read forever.
- **`<noscript>`** naming the eight read-only routes, the export endpoint, and
  the caveats.
- **Print stylesheet** forcing collapsed caveat bodies open, writing link
  targets out beside their text, dropping controls and inverting the palette.
- **The suite stopped writing into `logs/`** (O-03) via an autouse fixture, and
  the three test-debris files were deleted: 7.2 MB → 2.4 MB of real module
  logs. A full run now leaves the directory untouched, asserted by a test.

**Found on the way:** the first draft of the `<noscript>` block advertised
`/api/v1/overview` and `/api/v1/treatment`. Neither has ever existed — the real
routes are `summary`, `pay`, `contracts`, `providers`, `authorities`,
`geography`, `boundaries`, `fingertips`. Caught before commit by checking, and
now pinned by a test that validates every route the page names against the same
frozen list `test_portal_isolation.py` uses. A published list of endpoints is a
promise, and a wrong one is worse than none.

### Phase 3 — Do not lose what was collected · M — **done** (`7baaf55`)

Delivered O-02 and P-02. Suite 1256 → **1279 passed**, 1 skipped.
Documented in [`docs/BACKUP.md`](BACKUP.md).

- **`pipeline backup`** copies with `VACUUM INTO` — a read transaction, so the
  snapshot is consistent while a module commits, with no WAL sidecar to forget
  — then reopens the copy, integrity-checks it and compares it table by table
  against its source before calling it a backup. A count that moved *while*
  copying is reported, not raised on: the warehouse is live.
- **First real backup [measured]:** 645,482 rows, 66 tables, 473.5 MiB from a
  483.8 MiB source, `integrity ok`, 30 seconds.
- **`pipeline restore`** refuses a backup that fails integrity or cannot be
  read as a database, requires `--force` over an existing warehouse, never
  deletes what it replaces, and clears stale WAL/shm sidecars first.
- **The archive is inventoried, not copied.** Content-addressing means a
  listing of names and sizes answers "what did I lose", and every surviving
  file verifies against its own filename. `missing_from_archive()` is that
  question as a function.
- **P-02 measured [live]:** 6,344 files, 3.50 GiB, 23 sources — and
  `find_a_tender` alone is 3.14 GiB of it, at ~1 MiB per paged JSON response.
  Growth is driven by *changed* documents rather than by runs, since
  `pipeline/http.py` checks for an existing copy by hash before archiving. No
  retention policy, deliberately: at this size that is the right amount of
  machinery.

**Found on the way — three, two of them mine:**

1. A corrupt backup raised `sqlite3.DatabaseError` rather than a refusal, so
   `pipeline restore` would have shown a traceback where it should say why it
   stopped. Caught by the corrupt-file test, fixed in both `restore` and
   `verify_copy`.
2. Two backups inside one second collided on a second-resolution filename.
   Generated names now take the next free suffix; an explicit path someone
   typed is still refused, which is the opposite rule on purpose.
3. **The test suite wrote 7.7 MB of backups into the repo's `data/backups/`**
   before `backup_dir` was added to the test settings — the same failure as
   O-03's logs, from the same cause: a `Settings` default that reaches back
   into the repository. There is now a test asserting every writable path the
   fixture hands out resolves outside the repo, which is the general fix both
   incidents needed.

### Phase 4 — Turn candidates into evidence · L — **F-01 and U-01 done** (`1b699ff`, `a8b1d4c`); F-03 and D-04 not done

Suite 1303 → **1324 passed**, 1 skipped. The audit trail was built before the
convenience, as planned.

**Done — F-01, the promotion path:**

- `evidence_promotions` (migration `0030`) records who promoted what, when, on
  what note, and the candidate as it read at the time.
- **The guarantee is structural.** Triggers on `cdp_documents`,
  `committee_papers` and `foi_requests` refuse any insert without a matching
  promotion row, so it holds for a module, the SQL box, and an author who has
  not read the file — not only for `promote.py`.
- **Promotion fetches the document.** A candidate's `payload_sha256` is the
  hash of the *listing page the link was found on*; putting that on an
  evidence row would claim the document had been retrieved when it had not.
  The fetch goes through the same client the modules use, and a URL that does
  not answer is refused rather than saved.
- **Per row, attributed, no bulk.** There is no `promote_many` and a test
  asserts there is not. Rejection *is* bulk — deciding a link is not what it
  looked like is reachable from the listing, and being wrong leaves a
  candidate a candidate.

**Done — U-01, the Candidates tab:** counts per kind, filters by authority and
status, the document URL as the most prominent thing in each row, the
confirmed-type field beside Promote, and a promotions log. Confidence and
match quality are displayed and never sorted on, because ordering a worklist
by ModernGov's textual ranking turns a triage aid into a recommendation.

**Not done — F-03 (workforce census verification).** The promotion mechanism
covers the three candidate *tables*; the census is a different shape — 68
metrics with a `verified` flag and a markdown worklist, no URL per row — and
folding it in properly is its own piece of work rather than a fourth entry in
`KINDS`. Deferred rather than bodged.

**Not done — D-04, and it is bigger than this plan assumed [live]:**

| | |
|---|---|
| PFD reports | 1,539 |
| …with `matters_of_concern` | 472 |
| Pending `pfd_concerns_in_pdf_only` | 1,067 |
| …already answerable from the warehouse | **0** |
| `pfd_reports` last retrieved | 2026-08-11T17:29, *before* the PDF-reading commits `c17eaf1` and `847a937` |
| `pfd_documents` rows | 22 |

So the items are exactly as stale as suspected, and **a re-run is necessary
but not sufficient**. Two things follow:

1. Answering them means fetching ~1,067 PDFs from a single host,
   `judiciary.uk`, at one request per two seconds — over half an hour of
   rate-limited waiting before download and text extraction, so realistically
   one to two hours against one government server. That is a deliberate act to
   schedule, not a thing to slip into a phase.
2. **Even then the queue would not clear.** `record_review_item` refreshes a
   pending item; nothing resolves one. Something has to mark an item answered
   when the pipeline itself answers it — which is a new concept, distinct from
   a human decision, and needs designing rather than assuming.

Recommendation: do both in one small phase of their own — the resolution
concept first, the crawl second, so the crawl's result is visible when it
lands.

### Phase 5 — Close the fetcher · M — **done** (`d4ad49e`)

Delivered S-01. Suite 1324 → **1357 passed**, 1 skipped. Every acceptance
criterion met, and the scope grew by one caller on the way.

- **`pipeline/netguard.py`** refuses loopback, private, link-local, multicast,
  reserved and unspecified addresses, on the **resolved address** rather than
  the hostname — so `localhost`, `127.0.0.1`, `127.0.0.1.nip.io` and a name
  whose owner points it inward are one answer, not four rules.
- **A name resolving to both a public and a private address is refused.**
  Which one gets connected to is not this code's decision.
- **Applied as an httpx request hook, so redirects are covered.** A public URL
  that 302s into private space is a request the caller never made, and it has
  its own test.
- **Two callers, not one.** The plan named `check-url`; promotion also fetches,
  and a candidate URL is a link copied off a council's page, so anyone able to
  publish there chooses it. Both are guarded.
- **Off by default for modules**, which fetch addresses found on published
  pages rather than typed by a person — and switching it on for them would
  make every offline test do a real DNS lookup.
- **Council URLs still resolve**, asserted over the real shapes the pipeline
  fetches (http, odd ports, the WDTK feed) plus the existing
  `test_web_resolve.py` flow, which now runs with the guard live.

**Documented limits rather than papered over:** the resolve-then-connect gap
means DNS rebinding is not caught (fixing it means pinning the connection to
the checked address, a custom transport), and this is not a firewall — it stops
the pipeline being *used* to reach private space, not the machine from
reaching it.

**Found on the way:** the first test fixture patched `socket.getaddrinfo`,
which is the socket module for the whole process — so httpx resolved the test
server's own `127.0.0.1` to somewhere public and three web tests timed out at
30 s. `netguard.DEFAULT_RESOLVER` now exists precisely so a test can substitute
a resolver without reaching into a shared module. The guard stays *active* in
every test rather than disabled: names resolve to a public stub, so the code
still resolves, inspects and decides.

### Phase 6 — CI and conventions · M

- **Goal:** the constraints stop depending on each session re-reading them.
- **Delivers:** O-01, O-04, T-01, T-02.
- **Acceptance:** CI runs the offline suite on push; `CLAUDE.md` carries the hard constraints; ruff configured and clean; suite time reported before and after any change made to reduce it.
- **Risk:** low, but ruff across 37k lines will want a formatting commit kept separate from behaviour.

### Phase 7 — Measured performance · M, gated

- **Goal:** take the two performance levers that are real, having measured them.
- **Delivers:** P-01, P-03, F-04.
- **Acceptance:** before/after on the same machine and warehouse for `synchronous = NORMAL`; a `--jobs 4` full run compared with serial on rows, review items and failures; cursor behaviour established per module and the README corrected if it overclaims.
- **Risk:** low to try, and every part of it may correctly end in "leave it alone" — which Phase 5 of the admin plan already showed is the useful outcome.

## 6. Rejected

| Idea | Why not |
|---|---|
| Authentication on `/admin` | Settled project decision. The bind address is the control. |
| A web framework, ASGI, or a build step | Would buy nothing the stdlib server is failing at, and costs the "renders with the cable unplugged" property. |
| Auto-promoting high-confidence candidates | `match_quality` is ModernGov's own ranking, not this pipeline's judgement ([docs/CAVEATS.md:185](docs/CAVEATS.md:185)); an "excellent match" for `public health grant` is frequently a COVID grant report. Confidence is a triage aid and must not become a threshold. |
| Deriving unmet need, caseload-per-worker, or any cross-layer ratio | [docs/CAVEATS.md:14](docs/CAVEATS.md:14) forbids these by name. |
| SSE or WebSockets for the job log | Polling was chosen deliberately and works; this is a rewrite for no user-visible gain. |
| `retrieved_at` index across twenty tables for the freshness panel | Priced and declined by Phase 5; paid on every insert by every module for one panel. |
| Mark-as-noted on `parse_failures` | Declined before, and **[live]** there are 22 failures across three reasons — the grouping answers it. |
| An ORM, or replacing SQLite | The write-slot discipline is hard-won and specific to this engine. |
| Full-text search over archived documents | Attractive, but it is a new index over 3.6 GB with its own freshness problem. Revisit after Phase 4 gives it verified documents to search rather than candidates. |

## 7. Open questions

1. **Who verifies candidates, and to what standard?** Phase 4 needs the rule before it needs the UI. My recommendation: one named reviewer per row, the same identity `review_decisions` already records, and no bulk promote for anything above a candidate's source page — bulk *reject* is fine. Depends on whether anyone besides you will do it.
2. **Do you want history at all (F-05)?** Recommendation: not yet, and not as a general "version every table". If a specific claim needs it — advertised bands over time is the plausible one — add history to that table alone, with a caveat forbidding the differencing the census taught you to forbid.
3. **Should `m13` be re-run now?** Recommendation: yes, in Phase 1, because an empty budget table is currently indistinguishable from a broken parser and one run settles it.
4. **Retention for `data/raw` (P-02).** Recommendation: keep everything until it hurts, but measure and document the curve now so the decision is not taken in a hurry at 20 GB.
5. **Is `--jobs 4` worth promoting to default?** Recommendation: only after Phase 7's comparison, and probably not — the current default is the conservative one and the run is not interactive.
