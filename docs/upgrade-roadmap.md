# Upgrade roadmap

Status: audit written 2026-08-13 against commit `841bd49` with a clean tree;
baseline `uv run python -m pytest` was green before any of it (**1215 passed,
1 skipped, 18 deselected, 422s**). **All seven phases have been worked**:
1–3, 5 and 6 are done; Phase 4 delivered F-01 and U-01 and left F-03 open
(D-04 followed on 2026-08-13); Phase 7 measured P-01 and F-04 and left P-03
open. Each phase records what changed from the plan as it landed.

**What is left, as of 2026-08-14.** Everything the audit filed has been
delivered, measured and declined, or is listed here. **Three remain**, and
none is blocked on effort — each needs a decision first. D-05 and D-06, both
filed after the override table was emptied, were closed the same day. On
2026-08-14 the portal was compared against the systems its audience actually
uses — Fingertips, LG Inform, WhatDoTheyKnow, the ONS developer hub — and the
comparison filed seventeen new findings (W-05–W-21, §3F), none yet worked,
plus fifteen possible futures (§3J). On the same day four proposed
workstreams — new evidence terrain, the claims-to-evidence index, the sector
universe, and further sources — were filed as §8; the third workstream of the
first review, the verification campaign, is the register's own F-01 and F-03,
already there.

| | Finding | What it needs |
|---|---|---|
| **F-03** | Workforce census stays unverified — 68 metrics, all `verified = 0` | A design. The census is a different shape from candidate promotion: no URL per row, a markdown worklist, and a caveat forbidding cross-year differencing. |
| **F-05** | Nothing is tracked over time | A decision before a design, and my recommendation is still *not yet* — history invites exactly the differencing `docs/CAVEATS.md` forbids. Add it to one table if one specific claim needs it. |
| ~~**D-05**~~ | *Closed 2026-08-13* (`1198dea`) — a resolution now writes `pipeline/verified_websites.json`, tracked in git and read ahead of the seed registry. | |
| ~~**D-06**~~ | *Closed 2026-08-13* (`778476b`) — `backup --keep N`, labelled backups never pruned, cron and Task Scheduler lines in `docs/BACKUP.md`. | |
| **P-03** | `--jobs > 1` is still opt-in | Two full collections to compare, several hours each against live public bodies. Your say-so, not a phase. |

Also standing, and deliberately: **O-03** is half done — tests no longer write
into `logs/`, but nothing rotates them.

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

**F-04 · Resumability is real for one module · S to establish — closed in Phase 7** (confirmed: 1 of 17; README corrected)
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

**D-04 · 88% of the queue is three item types, and one may be obsolete · M — closed 2026-08-13** (`64d309e`, `4d25beb`)
- **Outcome:** 459 `pfd_concerns_in_pdf_only` closed once m08 had read the PDFs (`pfd_documents` 22 → 2,312), and 53 `committee_url_unknown` closed once the verified URLs were committed to the registry. 608 PFD items remain pending and are *correct* — the PDF was read and still yielded no concerns, which is the source limitation `docs/CAVEATS.md` describes.
- The missing concept the audit predicted turned out to be the whole job: `review_queue.status` gains `answered`, meaning the pipeline went and got what the item was waiting for. Deliberately not a `review_decision` — see `pipeline/review_sweep.py` and migration `0031`.
- `unmatched_buyer_name` (2,667) and `possible_group_company` (493) are untouched and still need people. Neither is answerable by anything the pipeline holds.
- Evidence **[live]**: `unmatched_buyer_name` 2,667, `pfd_concerns_in_pdf_only` 1,067, `possible_group_company` 493, of 4,815 total.
- `pfd_concerns_in_pdf_only` was filed because the concerns were PDF-only ([docs/CAVEATS.md:159](docs/CAVEATS.md:159)); commits `c17eaf1` and `847a937` taught m08 to read those PDFs. So up to 1,067 items may now be answerable by re-running rather than by a human — but they will not clear themselves, because a decided item stays decided and a pending one is only refreshed ([README.md:470](README.md:470)).
- Costs today: a queue whose bulk is undecidable one-at-a-time trains its operator to ignore it.

**D-05 · "Approved" on an unknown-URL item does not mean it was answered · S — closed 2026-08-13** (`1198dea`)
- **Fix:** `resolve_authority_url` writes `pipeline/verified_websites.json` as well as the override row. Tracked in git, read by `website_for()` ahead of the seed registry, hand-editable, and sorted so a diff shows the answer added rather than the whole file moving. The answer was already registry-quality when given — the server confirms the URL responds before storing it — so only its filing was missing.
- Evidence **[live, superseded]**: 132 `authority_website_unknown` and 53 `committee_url_unknown` were `approved` while `authority_url_overrides` held 191 rows. Approval records a judgement; answering writes an override ([README.md:445](README.md:445)).
- **What happened since:** the override table was emptied and all 191 URLs went with it. The 105 committee URLs were recovered from `docs/verification/issue1_committee_urls.md` into the code registry; the ~86 council base URLs answered in the UI were **not recoverable**, because the answer only ever existed in that table.
- So the finding is no longer "these two counts might not correspond". It is that **an answer given in the UI has no home outside the warehouse**. The fix is for a resolution to produce a registry-shaped record — a committed entry, or at minimum a line in a verification document — at the moment it is given, rather than relying on somebody later getting round to a commit.

**D-06 · Nothing takes a backup unless a person remembers · S — closed 2026-08-13** (`778476b`)
- **Fix:** `backup --keep N` prunes after copying, a labelled backup is never pruned, and `docs/BACKUP.md` carries the cron and Task Scheduler lines. Writing the test found the bug that made pruning dangerous: `listing()` sorted by filename and called it "newest first", but the same-second uniquifier means `warehouse-…Z.db` sorts *after* `warehouse-…Z-5.db`, so prune would have kept the oldest of a run and deleted the four taken after it. Sorted by mtime now.
- Evidence: `pipeline/backup.py` exists and works (Phase 3), and on the day the override table was emptied the only backup on disk had been taken *after* the loss. An earlier one taken the same afternoon was no longer there.
- A backup you have to remember is a backup you take too late. Worth a scheduled or pre-destructive-operation hook, and a retention rule so that clearing the directory of test debris cannot take the real snapshots with it.

### C. Pipeline performance

**P-01 · Every commit is an fsync · S to try, MEASURE FIRST — measured in Phase 7, and declined**
- Evidence: [pipeline/db.py:289](pipeline/db.py:289) sets `busy_timeout` and `foreign_keys`; WAL at [pipeline/db.py:272](pipeline/db.py:272). `synchronous` is never set, so it is SQLite's default `FULL`.
- The project deliberately commits per unit of work ([README.md:326](README.md:326)) — so this is paid on every commit of every module, by design.
- `synchronous = NORMAL` under WAL is the conventional trade and risks losing the last transactions on power loss, not corruption. For a warehouse that is re-runnable from an archive, that is close to free — but the size of the win is unmeasured. Measure with a fixed-size m01 slice before and after.

**P-02 · The raw archive grows without bound · M — measured and documented in Phase 3**
- Evidence **[live]**: `data/raw` is **3.6 GB across 6,322 files**; the warehouse it backs is 242.7 MB.
- It is the audit trail, so deletion is not the answer. Compaction, per-source retention, or simply measuring and documenting the growth curve is.

**P-03 · `--jobs > 1` is still opt-in · M, evidence-gated — still open after Phase 7; needs two full runs**
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

**U-03 · Promotion works and is never used · M — closed 2026-08-14** (`1a84e69`)
- Evidence **[live, at filing]**: 2,462 undecided candidates (423 CDP, 1,194 committee papers, 845 FOI) and **zero** rows in `evidence_promotions`, `cdp_documents`, `committee_papers` and `foi_requests`. Phase 4 built the path across and nothing had ever crossed it.
- Cause: the screen offered one row, one form, one click, 2,462 times. The rule that promotion needs a person was doing no protecting — it was keeping the evidence base empty.
- **Fix:** batch the clicking, not the deciding. Only candidates opened in this session are eligible; excluded rows are named with the reason and there is no override; requests go one at a time through the unchanged single-URL route, so there is still one fetch, one archived payload and one `evidence_promotions` row per document. A failure is recorded and the run continues.
- Verified by: three tests pinning the shipped script (one URL per request, the opened-check present, no `Promise.all` in the loop), and a stubbed-transport run in the browser where item 2 fails and items 1 and 3 still promote.

**U-04 · No link from the operator UI to the portal · S — closed 2026-08-14** (`859cf2e`)
- The portal has linked to `/admin` since it was built ([pipeline/web/static/public/index.html:42](pipeline/web/static/public/index.html:42)); nothing linked back. Also closed: the undecided candidate count now reaches the tab strip on load, and a candidate is linkable.

**U-02 · Job history dies with the process · S — closed in Phase 1**
- Evidence: [pipeline/web/jobs.py:192](pipeline/web/jobs.py:192) — the registry is in-memory, log lines in a ring buffer.
- After a restart there is no record that a run happened; `logs/` has the lines but nothing ties them to a job. A row per job in the warehouse would close it.

### F. Public portal

**W-01 · No `<noscript>`, and the page is entirely JS-rendered · S — closed in Phase 2**
- Evidence: [pipeline/web/static/public/index.html](pipeline/web/static/public/index.html) ships a header, nav and filter bar; the sections render from `/api/v1/*`. `grep -c '<noscript>'` → 0.
- With JS off or broken, a public evidence site meant to be cited shows chrome and nothing else. A `<noscript>` naming the API and the exports is a few lines.

**W-02 · No print stylesheet · S — closed in Phase 2**
- Evidence: `@media print` appears zero times in either [pipeline/web/static/public/styles.css](pipeline/web/static/public/styles.css) or the admin sheet. This evidence gets printed and taken into rooms; a caveat that does not survive printing is a caveat that got separated from its figure, which is the failure [README.md:381](README.md:381) is written against.

**W-04 · Every "open the source" link went to a paginated API cursor · M — closed 2026-08-14**
- Evidence **[live, at filing]**: all 98,636 `contracts.source_url` values are OCDS API request URLs — `…/ocdsReleasePackages?updatedFrom=…&cursor=dXBkYXRlZEZyb…`. Following one re-runs a page of a bulk feed, and after the window moves it does not return the same releases. This was the only link the contracts table and the provider timeline offered.
- Not a storage bug: `source_url` is provenance for the exact bytes, and rewriting it to make an anchor work would trade the thing the warehouse is for.
- **Fix:** migration `0032` adds `contracts.notice_web_url` for the address *the release published*; m01 fills it going forward and a one-shot filled 15,736 rows from bytes already in `data/raw/`, fetching nothing. Where a release published none, the portal constructs the link at read time from the notice id and says that it did. Both link kinds now appear next to the API link rather than instead of it.
- The construction rule was verified against every archived page, not assumed: 117,317 of 117,365 published notice URLs follow it, and every exception is an attachment path or a release citing a different notice.

**W-05 · Collected and never shown · L — NDTMS done 2026-08-14, the rest open**
- The portal reads what is named in `_public([...])` in `public_queries.py` and nothing else. Tables collected, caveated and never displayed **[live]**: `ndtms_la_statistics` 17,231, `la_revenue_budgets` 477,199 (one metric used), `pfd_reports` 1,539 with 214 concern terms and 57 provider mentions, `cqc_location_reports` 580, `company_filings` 1,027, `provider_report_disclosure` 180.
- **Done:** NDTMS reaches the treatment page. `/api/v1/ndtms` returns estimates with their bounds attached, and the page charts only the figures the source published an interval for — these sheets print an estimate, its denominator population and a rate side by side, and one axis carrying 1,363 and 73,236 and 1.86 says nothing about any of them.
- The pairing rule is the part worth knowing: bounds attach within a publication, sheet, area, period and age group, and a standalone pair attaches only where exactly one measure in the group is a point estimate. Where a sheet has several, the bounds are left unattached and the estimate is drawn without a band. A confidence interval on the wrong estimate is invented, which is worse than an absent one.
- Still open: PFD, budget lines, CQC inspection history, filings, disclosure gaps, and the candidate-to-evidence funnel on the overview.

**W-03 · Accessibility is in good shape — no action.** `lang="en-GB"`, a skip link, `aria-label`led nav, `role="combobox"`/`listbox` on the typeahead, `:focus-visible` styles and `prefers-reduced-motion` handling are all present. Spot-checked, not audited against WCAG 2.2 line by line.

**W-05 · The portal's Region filter is a dead control · S — filed 2026-08-14**
- Evidence: `#f-region` renders in the global filter bar ([pipeline/web/static/public/index.html:56](pipeline/web/static/public/index.html:56)); its change handler writes `state.region` ([pipeline/web/static/public/app.js:312](pipeline/web/static/public/app.js:312)); `filterParams()` forwards only `provider_key`, `year_from` and `year_to` ([pipeline/web/static/public/app.js:188](pipeline/web/static/public/app.js:188)); no page reads it. The word `region` appears in public JS only as a map tooltip and a treatment context label.
- Costs today: a researcher picks a region, sees the same figures, and has no way to know the control did nothing. On a portal built around "no figure without its caveat", a dead control is the one UI failure that rule does not cover.
- Fix: consume it — filter contract notices by buyer region, which is one join to the `authorities.region` the warehouse already holds — or remove the control. Removing is the cheaper honest fix.
- Verified by: a test asserting every filter control the portal renders is read by at least one page.

**W-06 · Contract exports silently truncate at 500 rows · S — filed 2026-08-14**
- Evidence **[live]**: `contracts` holds 98,636 rows; `/api/v1/contracts` defaults `limit` to 500 and caps it at 5,000 ([pipeline/web/public_queries.py:338](pipeline/web/public_queries.py:338), [:391](pipeline/web/public_queries.py:391)); the "Every notice" table asks for 1,000 ([pipeline/web/static/public/js/pages/contracts.js:20](pipeline/web/static/public/js/pages/contracts.js:20)) but its Download CSV passes no limit at all ([contracts.js:221](pipeline/web/static/public/js/pages/contracts.js:221)) — so the export ships the first 500 rows of 98,636 with nothing in the file saying so.
- Costs today: a researcher's CSV looks complete and is 0.5% of the corpus. The one export that must not lie is lying structurally, and the table and its download disagree about what "the notices" are.
- Fix: a complete-download path with the row count written into the `#` header line — chunked CSV streaming, or a raised cap the export states. The count must travel in the provenance line, not beside it.
- Verified by: a test that a full export of a corpus larger than 500 rows contains every row and names the count.

**W-07 · NDTMS data has no download path · S — filed 2026-08-14**
- Evidence: `EXPORTABLE` has no `ndtms` entry ([pipeline/web/public_export.py:26](pipeline/web/public_export.py:26)), so `/api/v1/export` refuses it, while the treatment page renders NDTMS estimates with paired 95% CIs and hollow markers where a CI could not be paired ([pipeline/web/static/public/js/pages/treatment.js:264](pipeline/web/static/public/js/pages/treatment.js:264)). The Fingertips card next to it has a Download CSV button; the NDTMS card has none.
- Costs today: the section with the most careful visualisation is the only one whose data cannot leave the server — a reader who wants to cite a point estimate must retype it.
- Fix: add `ndtms` to `EXPORTABLE`, exporting the row shape the page renders (estimate, `lower`/`upper`, `has_interval`, `value_text`), with the "why some points are hollow" note in the file header.
- Verified by: the export tests gaining the new endpoint, and a test that its rows carry the same paired-CI fields the page draws.

**W-08 · Charts cannot be exported as images · M — filed 2026-08-14**
- Evidence: ECharts is vendored and every chart is drawn client-side ([pipeline/web/static/public/index.html:19](pipeline/web/static/public/index.html:19)); no page calls `getDataURL()`. Fingertips offers "More options > Download image/CSV" on every chart, and the WHO Global Health Observatory does the same.
- Costs today: the visual is screenshotted at unknown resolution or rebuilt; the provenance chain survives in the CSV, but the figure as drawn is not reproducible from the portal.
- Fix: a per-chart menu — PNG via the canvas `toDataURL` ECharts already owns, next to the section CSV that already exists — with the caption and its caveat rendered into the download.
- Verified by: a browser check that a downloaded chart image carries its pinned caveat, which a header test cannot tell you.

**W-09 · The public API has no documentation page · M — filed 2026-08-14**
- Evidence: the only description of `/api/v1/*` is the `<noscript>` block ([pipeline/web/static/public/index.html:74](pipeline/web/static/public/index.html:74)) and the whitelist in ([pipeline/web/server.py:74](pipeline/web/server.py:74)). ONS runs a developer hub; Fingertips publishes request URLs meant to be embedded straight into notebooks and Power BI.
- Costs today: the audience most likely to consume the API — researchers working in notebooks — must reverse-engineer it from a page they only see with JS off.
- Fix: a static `/api/v1` docs page: routes, parameters, example URLs, response shapes, the export endpoint's filter forwarding, and the caveats. Pinned by a test against the same route list `test_portal_isolation.py` uses — a published list of endpoints is a promise, and a wrong one is worse than none.
- Verified by: the route-list pin above.

**W-10 · No licence statement per dataset · S — filed 2026-08-14**
- Evidence: the footer says "public-domain source" ([pipeline/web/static/public/index.html:106](pipeline/web/static/public/index.html:106)); no figure or export names a licence. `docs/SOURCES.md` records each source's licence but the portal never links it; Fingertips prints its OGL v3 terms and a citation format with every indicator.
- Costs today: reuse — and defending reuse — starts with the licence. A figure whose terms a researcher cannot state is an unfinished citation.
- Fix: per-source licence lines in the provenance drawer (most sources are OGL v3), a `# Licence:` line in export headers, and a link to `docs/SOURCES.md`.
- Verified by: a test that every export header carries a licence line.

**W-11 · No way to compare areas or providers side by side · M — filed 2026-08-14**
- Evidence: the portal shows one area at a time (choropleth, per-authority series) or one provider (deep-dive timeline). Fingertips leads with Compare areas; LG Inform's standard report is a comparison table with min/mean/max against a chosen peer group.
- Costs today: the campaign's central question — "how does my authority compare?" — is answered only by the reader opening two tabs and aligning them by eye.
- Fix: a compare view over data the portal already renders — pick two or more authorities (or providers) and draw the existing series (grant, budget, treatment, contracts) on shared axes. No new data, and the existing no-cross-layer-arithmetic caveats reapply on each shared axis.
- Verified by: a browser check of a two-area comparison, with the cross-layer caveat present on the shared axis.

**W-12 · The coverage matrix never reaches the public · M — filed 2026-08-14**
- Evidence: the admin Health tab's authority × evidence coverage matrix ([pipeline/web/health.py:50](pipeline/web/health.py:50)) is the best existing answer to "what is missing here", and only the operator sees it.
- Costs today: a public reader cannot tell whether an absent figure for their authority is absence of evidence or absence of collection — the exact distinction the review queue exists to keep, kept invisible.
- Fix: a public coverage view per authority (which of grant, budget, contracts, NDTMS, Fingertips, CQC and candidates hold rows), reusing the health tab's counts, carrying the caveat that absence is not evidence of absence.
- Verified by: a test that the public coverage endpoint and the admin one agree row for row.

**W-13 · No page exists for an authority · M — filed 2026-08-14**
- Evidence: the portal routes to six sections plus a provider deep dive ([pipeline/web/static/public/app.js:206](pipeline/web/static/public/app.js:206)); nothing keys off an authority, yet grant, budgets, treatment and contracts all join to `authorities`, and `/api/v1/contracts` accepts `buyer_ons_code` ([pipeline/web/public_queries.py:337](pipeline/web/public_queries.py:337)) that no control on any page sets. LG Inform's Headline Report and Fingertips' area profiles are the comparators.
- Costs today: the campaign question — "what does my authority get?" — is answered only by assembling the choropleth, the treatment page and the contracts API by hand, then aligning them by eye.
- Fix: a per-authority page in the provider deep-dive shape — grant allocation, budgeted spend, treatment estimates with their paired CIs, contracts let (the `buyer_ons_code` filter finally exposed), and W-12's coverage ticks. No new data.
- Verified by: a test that an authority page shows the same figures the existing endpoints return for that authority.

**W-14 · The map cannot carry a click through to the data · S — filed 2026-08-14**
- Evidence: the choropleth renders hover tooltips and nothing else ([pipeline/web/static/public/js/pages/geography.js:196](pipeline/web/static/public/js/pages/geography.js:196)); no click navigates anywhere. Fingertips' map selects an area and carries it through the other views.
- Costs today: no UI path to "contracts let by council X" — the parameter exists, the page does not. A researcher hand-crafts API URLs.
- Fix: clicking an authority opens its page (W-13) or a contracts view filtered to that buyer. Depends on W-13 or a lighter filtered-lists route.
- Verified by: a browser check of the click, and a test that the click target URL carries the ONS code.

**W-15 · Providers are not linked to their registers · S — filed 2026-08-14**
- Evidence: zero references to Companies House, the Charity Commission or CQC in the public JS (verified by search); providers carry `company_number` ([pipeline/exports/schema.py:97](pipeline/exports/schema.py:97)) and charities carry `charity_number`, and neither is rendered as a link.
- Costs today: the cheapest verification affordance — checking the register — requires a manual search. All three registers run public lookups by exactly these identifiers.
- Fix: `company_number` → Companies House, `charity_number` → Charity Commission, each CQC location → its CQC profile, labelled "verify at source" so the link is understood as an offer, not a claim.
- Verified by: a test that the links are built from the registers' public URL shapes.

**W-16 · No single bundle of the evidence exists · S — filed 2026-08-14**
- Evidence: no zip anywhere in `pipeline/exports/` or `pipeline/web/` (verified by search); the admin Exports tab writes the four targets and offers per-file downloads; the public `/api/v1/export` serves one endpoint at a time.
- Costs today: a researcher who wants "the evidence" clicks nine CSVs, four GeoJSONs and five JSONs separately; the bundle that would travel with a citation is assembled by hand, which is how companions get lost.
- Fix: an export target that zips the sheets, geojson and echarts outputs with their `.provenance.json` companions and a README naming the contents; offered from the admin exports tab, and a decision on whether the public portal serves it.
- Verified by: a test that the zip contains every file its manifest names, and no file the manifest does not.

**W-17 · There is no "find my council" · S — filed 2026-08-14**
- Evidence: the global filter bar offers provider, region and years ([pipeline/web/static/public/index.html:45](pipeline/web/static/public/index.html:45)); the only authority typeahead in the whole portal is on the Treatment page ([pipeline/web/static/public/js/pages/treatment.js:83](pipeline/web/static/public/js/pages/treatment.js:83)). A reader who knows their town rather than their ONS code has the choropleth tooltip and nothing else. Fingertips' GP finder searches by name, postcode and ODS code; every council site has a "find my council".
- Costs today: the portal's entry points all presuppose knowing the commissioning geography — for the campaign's own audience, "my council" is the natural first query, and it has no answer.
- Fix: an authority name typeahead in the global chrome — 347 rows, Fuse.js already vendored ([pipeline/web/static/public/index.html:22](pipeline/web/static/public/index.html:22)) — whose result lands on W-13's authority page when it exists, and on the geography map for that authority until then. The postcode half is deliberately not filed: ONS NSPD is a large, quarterly-updating source with its own archive cost, and the name search covers the common case for free.
- Verified by: a test that every authority name in the corpus resolves through the new control.

**W-18 · The public tables cannot be searched, filtered or paged · S — filed 2026-08-14**
- Evidence: every portal table is built by the same call ([pipeline/web/static/public/js/components.js:192](pipeline/web/static/public/js/components.js:192)) with data, columns, height and nothing else — no `headerFilter`, no pagination, no search box — while the contracts table holds up to 1,000 rows of a 98,636-row corpus ([pipeline/web/static/public/js/pages/contracts.js:20](pipeline/web/static/public/js/pages/contracts.js:20)). The SQL box and the admin browser can search; the public tables cannot.
- Costs today: a reader looking for one buyer, one provider or one notice reads rows until the page ends. The corpus is searchable by nobody but the two typeaheads.
- Fix: enable the Tabulator features already vendored — per-column search, a pager, and the row count shown so "1,000 of 98,636" is visible rather than implied.
- Verified by: a test that a table larger than one page renders a pager and that a search narrows the visible rows.

**W-19 · The portal map shows one layer at a time · M — filed 2026-08-14**
- Evidence: the geography page switches between six metrics over a single choropleth ([pipeline/web/static/public/js/pages/geography.js:19](pipeline/web/static/public/js/pages/geography.js:19), [:43](pipeline/web/static/public/js/pages/geography.js:43)); nothing overlays. The exports already produce four separate layers — contracts points, CQC locations, treatment polygons, PFD groupings ([pipeline/exports/geojson.py:48](pipeline/exports/geojson.py:48)) — for use elsewhere. Fingertips maps carry contextual layers and transparency; LG Inform layers metrics over boundaries.
- Costs today: the readiest relationships — where the contracts cluster, where CQC-registered services sit — are invisible on the only public map.
- Fix: layer toggles on the geography page (contracts, CQC, boundaries, coverage) reusing the export layers' shapes, each carrying the caveat discipline its layer already has.
- Verified by: a test that every toggled layer carries its own caveat text, and a browser check of the overlay.

**W-20 · Nothing tells the operator the exports are stale · S — filed 2026-08-14**
- Evidence: the exports listing carries file mtimes and nothing else ([pipeline/web/artefacts.py:75](pipeline/web/artefacts.py:75)); nothing compares them against `module_cursors` or `job_runs`. The Exports tab can show sheets written before a warehouse-changing re-run, and the README's "regenerate any time" is the only signal.
- Costs today: a figure exported from stale sheets looks current — the shape D-02 existed to kill, for artefacts instead of runs.
- Fix: a staleness line per export directory — "these sheets predate the last run of m01_procurement" — from the run record the warehouse already keeps.
- Verified by: a test that a fresh export of a just-run module reports current, and an older one names its predecessor.

**W-21 · Storage costs are invisible on the Health tab · S — filed 2026-08-14**
- Evidence: the health cards report warehouse size, page size and free bytes and nothing else ([pipeline/web/health.py:141](pipeline/web/health.py:141)); the 3.5 GiB raw archive, the backups directory and the exports output are measured nowhere in the UI. P-02's growth curve was measured once for the audit ([docs/upgrade-roadmap.md §C](docs/upgrade-roadmap.md)) and is otherwise invisible.
- Costs today: the archive is the audit trail with a growth curve the roadmap itself says should be measured until it hurts — and the only instrument is a one-off audit. The operator gets no signal until a disk fills.
- Fix: a storage card — raw archive bytes, backup count and bytes, exports bytes — stat-ing the three directories in the cheap half of the health query, so the curve is visible on every visit rather than once an audit.
- Verified by: a test that the card's numbers equal a direct listing of the three directories.

### G. Operations

**O-01 · No CI · M — closed in Phase 6** — no `.github/`. 1,215 tests, 7 minutes **[measured]**, Windows-only development, a repo several sessions commit to concurrently.

**O-02 · No backup or restore · M — closed in Phase 3** — nothing in `pipeline/` performs a backup (no `VACUUM INTO`, no dump helper). 242.7 MB warehouse plus 3.6 GB archive **[live]**, rebuilt only by re-crawling at one request per two seconds per host.

**O-03 · Logs never rotate, and tests write into the real `logs/` · S — half closed in Phase 2** (tests no longer write there; rotation is still absent)
- Evidence: no rotation in [pipeline/logging_conf.py](pipeline/logging_conf.py); `logs/` is 7.2 MB **[live]** of which `fake_insert_only_for_tests.log` is 5.0 MB, alongside `bogus_module.log` and `fake_writer_for_tests.log`.
- A test run polluting the operator's log directory is the kind of thing that erodes trust in the directory.

**O-04 · No root `CLAUDE.md` · S — closed in Phase 6** — the conventions are real, enforced and currently learned by reading `docs/admin-ui-plan.md` §2 and this file. Several sessions a day re-derive them.

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

**T-01 · No lint or typecheck · S — closed in Phase 6** (ruff; a typechecker is still absent, deliberately) — no ruff, mypy, black or pre-commit in [pyproject.toml](pyproject.toml). With 1,215 passing tests the marginal value is real but modest; the argument for ruff is consistency across concurrent sessions, not defect-finding.

**T-02 · A 7-minute suite is a suite people skip · M — closed in Phase 6** (400.6s → 145.95s) — 422s **[measured]**. Worth profiling for the slow minority before optimising, and `-p no:cacheprovider`/parallelism are cheaper than restructuring.

**T-03 · Per-module coverage is complete — no action.** Every `m00`–`m16` has a matching `tests/test_m*.py`, plus route, guard, concurrency, provenance and portal-isolation suites.

### J. Possible future — filed 2026-08-14, deliberately not findings

Ideas from the same comparison that are not findings yet. Each has a reason
it is not in the register above — a schema decision, an inference question, a
contract with seventeen modules, or a solution that duplicates a planned
one — and each is filed so that "we thought about this" is written down
somewhere it survives.

**Corpus-wide search · L**
- What: full-text search across contract titles, buyers and suppliers, PFD reports, committee and CDP candidates, FOI requests and NDTMS rows — the search every comparable portal leads with (WhatDoTheyKnow is search-first, LG Inform has advanced operators, Fingertips searches indicators by keyword).
- Why it is here rather than in the register: a client-side index over 98,636 notices is a payload and a freshness problem, and a server-side one is SQLite FTS5 — a schema decision carrying the same maintenance burden the roadmap has already declined once for the archived documents (Section 6, "Full-text search over archived documents"). The difference: warehouse tables are ~520 MB against the 3.5 GiB archive, so this is the cheaper half of that rejection. Revisit once the promotion work has given it verified documents to search rather than candidates.

**Versioned datasets, ONS-style · L — F-05 with a delivery shape**
- What: ONS publishes editions and versions of each dataset; a re-run that changes rows is a new version, with the previous one still citable ([developer.ons.gov.uk](https://developer.ons.gov.uk/)). Under this shape, "the 2026-08 version of the contracts table" would be a real thing to link.
- Why it is here rather than in the register: every domain table upserts on a natural key, so nothing can be cited as a version today. F-05's decision stands and the recommendation is unchanged: not yet, and as history on one table only if one specific claim needs it.

**Matrix ("tartan rug") views · M**
- What: Fingertips' Overview view — authorities × periods as a colour-coded matrix, one glance at the whole distribution (Fingertips calls it a tartan rug).
- Why it is here rather than in the register: it overlaps W-11 (compare view) — the matrix is the same comparison without the axes, and whichever is built first shapes the other. Filed so the shape is remembered rather than re-invented. ECharts heatmap, no new dependency.

**Trend markers in tables · S**
- What: ▲▼ "direction of travel" per row against the previous period, as Fingertips' England view shows.
- Why it is here rather than in the register: every row-level change marker invites the differencing `docs/CAVEATS.md` forbids for the census, and the marker must know per row which layers it may appear on. The rule exists; a marker needs it encoded, and which layers carry it and what the caveat next to it says is a decision to settle before the button is. Filed so that decision is remembered.

**API rate cap · S**
- What: a per-IP token bucket on the `/api/v1/*` read routes — a 429 with `Retry-After` rather than silence.
- Why it is here rather than in the register: it is small, and its answer depends on a standing decision — the bind address is the control, and a cap only earns its place once the portal is reachable by readers the operator does not trust, which is the same exposure the README's security section already governs. Filed so the limit exists when the exposure does. Every public data API answers overload with a limit.

**Table-browser CSV · S**
- What: a "download current view" on the admin table browser, alongside the SQL box's existing CSV.
- Why it is here rather than in the register: the browser is a paging window, not a dataset — the honest export path is the export layer, and W-06's completeness fix covers the public half of it; a browser CSV would be a third, smaller route into the same rows. Filed so the gap is remembered rather than solved twice.

**Post-run verification pass · M**
- What: after each module, run FK integrity, a no-row-without-provenance sweep and module-declared row-count floors, recording the results in the run summary.
- Why it is here rather than in the register: the floors are a contract with each of seventeen modules — declaring and maintaining them is a design, not a button — and the integration suite already sweeps provenance once. Filed because D-02 showed the cost of a run whose record cannot be trusted.

**Significance-aware colouring · M — needs a decision**
- What: colour treatment figures by whether an authority's paired CI overlaps the England value, as Fingertips' red-amber-green-vs-benchmark does throughout.
- Why it is here rather than in the register: the warehouse already holds the CIs, so the work is implementation — but the colour *is* an inference, and `docs/CAVEATS.md` decides which inferences this project makes. The 2026 default for health data, and the decision it needs, filed together.

**Peer-group benchmarking · M — needs a decision**
- What: LG Inform-style nearest-neighbour groups — "how does my authority compare with its peers".
- Why it is here rather than in the register: comparability is a claim. Which authorities are comparable — type, region, deprivation? — is a method decision, and a group implies a fairness the caveats have not asserted. Filed so the idea is remembered rather than adopted by default.

**Browser-level regression tests · M**
- What: a headless pass that loads each portal route and asserts it renders without console errors or vendor-library failures — the manual "verify in a browser" the house rules already demand, automated.
- Why it is here rather than in the register: it costs a dev-only browser dependency, which is a trade to make explicitly against the "no build step" decision — runtime is unaffected, but the repository gains a test tool with its own maintenance. Filed because every CI-running portal closes this gap, and the manual check is per-session by design.

**Distribution views (box plots) · S–M**
- What: Fingertips' box plot — the range and interquartile spread of treatment numbers across authorities, over time.
- Why it is here rather than in the register: it is descriptive and single-layer, but it is a statistical shape with a threshold question — what the whiskers invite a reader to conclude — and the project's rule is to settle the inference question before shipping the visual.

**Module run record visible to the operator UI · S–M**
- What: a per-module "last run" panel on the Pipeline tab reading `logs/` — file mtimes plus the tail `module.finished` events — and a read-only viewer for the log files themselves.
- Why it is here rather than in the register: `job_runs` deliberately records only runs started from the browser, `module_cursors` only m01's, and the server serves only the in-memory job ring buffer ([pipeline/web/server.py:761](pipeline/web/server.py:761)); the durable record is the log files, and nothing reads them in the UI. The fix is display-only over files that exist, but it decides a boundary — how much of the operator's record belongs in the browser — that no decision has covered. Filed so the boundary is chosen rather than assumed.

**Cross-table duplicate candidates · M**
- What: a flag when the same document URL already appears in another candidate table — a URL found by m09 (CDP), m10 (committee papers) and m15 (FOI) is currently three unconnected rows.
- Why it is here rather than in the register: each table dedupes internally on its natural key, but "duplicate" across tables *is* a judgement here — the same URL found in two roles may be two evidence rows. What counts as a duplicate is a decision to make before a flag means anything. Filed so the definition is settled before the button is.

**Real-terms pay analysis (CPIH via the ONS API) · S–M — needs a decision**
- What: deflating pay figures with the consumer price index to ask whether sector pay has kept pace.
- Why it is here rather than in the register: deflation is arithmetic across evidence layers, which `docs/CAVEATS.md` governs, and the census-differencing lesson is the house rule in miniature — settle the inference before the visual. Filed together with the decision it needs: whether real-terms statements are ever claims this corpus may make.

**NHS England workforce data products · S — needs a claim**
- What: the workforce statistics data products behind NHS England's publications, for an NHS-workforce denominator.
- Why it is here rather than in the register: it overlaps m06 (benchmarking) and m16 (NHS Jobs) context, and its value depends entirely on a claim that needs an NHS denominator — no claim, no module. Filed so the conditional is remembered rather than re-derived.

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
| W-05 | Wire or remove the Region filter | A visible control that does nothing is the one failure the portal's honesty rules do not cover |
| W-06 | Make contract exports complete | The table shows 1,000 rows, its CSV ships 500 of 98,636, and nothing says so |
| W-07 | NDTMS download path | One section whose data cannot leave the server |
| W-10 | Licence lines in exports and footer | Reuse, and defending reuse, start with the licence |
| W-15 | Link providers to their registers | The cheapest verification affordance is a link |
| W-16 | Zip bundle of exports | "Download the evidence" is nine CSVs and nine JSONs by hand today |
| W-17 | "Find my council" typeahead | A reader who knows their town, not their ONS code, has no entry point |
| W-18 | Search and page the public tables | Tabulator ships it; the portal configures none of it |
| W-20 | Stale-exports warning on the Exports tab | A state that looks fine and isn't — the D-02 shape, for artefacts |
| W-21 | Storage card on the Health tab | The only instrument for P-02's growth curve is a one-off audit |

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

### Phase 6 — CI and conventions · M — **done** (`f1a2dbe`, `6c2a9b7`, `3f1a668`, `3511399`, `8f4ea2e`, `0cc180c`)

Delivered O-01, O-04, T-01, T-02. Suite **1358 passed**, 1 skipped, and CI is
green on Ubuntu.

- **Ruff**, configured narrowly (`E4`, `E7`, `E9`, `F`, `I`) with four rule
  families excluded and the reason for each written into `pyproject.toml`.
  E501 chief among them: the comments here are the documentation, and
  reflowing prose to satisfy a linter is the tail wagging the dog. 41 real
  violations fixed — 37 automatically, 7 by hand.
- **`CLAUDE.md`** carries the ten settled decisions, the house style, and the
  two rules this repo learned the hard way.
- **CI** runs the offline suite and ruff on every push, on Ubuntu while
  development is Windows. The `integration` marker stays deselected — the
  politeness commitment has no exception for CI.
- **T-02 [measured]: 400.6s → 145.95s**, same tests. Applying the 30
  migrations costs 0.31s and the `conn` fixture did it per test; it is now
  built once per session and copied. The template is checkpointed first,
  because a copy taken with pages still in the WAL is missing whatever the
  last migrations added.

**What CI found on its first run — four failures, and none of them what was
expected:**

1. **`restore` could lose committed data.** It renames `warehouse.db` aside so
   nothing is thrown away, but sidecars are named after the file rather than
   carried with it, so `warehouse.db-wal` stayed behind to be deleted. Windows
   hid it by refusing to rename a file another connection holds open. Fixed by
   checkpointing before the rename, with a regression test.
2. **Five `with sqlite3.connect(...)` in `backup.py` never closed.** That form
   commits on exit and does not close — a leak everywhere, and on Windows an
   open handle that blocks the rename above.
3. **The suite depended on the developer's `.env`.** `CONTACT_EMAIL` has no
   default, and a bare `Settings()` — reached through
   `db.apply_migrations(conn)` falling back to `get_settings()` — reads the
   environment and `.env`. Every machine it had ever run on had one, so a
   fresh checkout failed four tests. Now set in `conftest`, and verified by
   running the whole suite with `.env` moved out of the way.
4. **A test whose failure message was empty.** `assert result.exit_code == 0,
   result.output` says nothing when the failure was an exception, which is
   exactly when you need it. It now falls back to `result.exception`.

The first three are real defects in code shipped earlier this week, two of
them in Phase 3. **None was reachable from the machine the code was written
on**, which is the entire argument for O-01 and better than any of the reasons
originally given for it.

**Also added, not planned:** a red build now emits `::error::` annotations, so
the failing test names are readable without a repository token. Raw Actions
logs are not public; annotations are. A build that is red with no readable
reason is one people learn to ignore.

### Phase 7 — Measured performance · M, gated — **P-01 and F-04 done** (`11e5088`); P-03 not run

The phase anticipated ending in "leave it alone", and for the part that could
be measured here, it did. Suite unchanged at **1358 passed**.

**P-01 — measured, and declined. [measured]**

| | 200 commits of 10 rows |
|---|---|
| `synchronous = FULL` (current) | 0.189s median |
| `synchronous = NORMAL` | 0.020s median |

9.5×, about 0.85 ms a commit — a real difference, and an irrelevant one.
Commits happen per fetched unit (a page, a council, a document), so a full
collection is on the order of 10,000 of them: **eight seconds**. That same
collection makes ~6,300 requests at one per two seconds per host — **three and
a half hours** of deliberate waiting. The lever buys 0.07% of a run in
exchange for the guarantee that a committed row survives the power failing
mid-crawl. Left at FULL, with the numbers written into `pipeline/db.py` so the
next person to spot the lever gets to the same answer faster.

**F-04 — established, and the README was overclaiming.** Exactly one module of
seventeen records a cursor: `m01_procurement`, because Find a Tender is paged.
The README said re-runs were "resumable (per-module cursors), so an
interrupted crawl continues rather than restarting" — true of `m01` and of
nothing else. The other sixteen restart from the beginning; what makes that
acceptable is the conditional-request cache, since an unchanged document
answers `304` and is read from the archive rather than downloaded. **The
requests are still made at the same rate**, so a re-run costs time even when
it costs no bandwidth. Corrected.

**P-03 — not run, deliberately.** Its acceptance is a full `--jobs 4` run
compared against a full serial one, on rows, review items and parse failures.
That is two complete collections: ~6,300 requests each, several hours each,
against live public bodies — and the second one exists only to be compared
with the first. That is a decision to schedule, not something to start inside
a phase, for the same reason D-04's PFD crawl was not started inside Phase 4.

What is already known, and is not enough on its own: the parallel path is
covered by `tests/test_parallel.py` and `tests/test_run_waves.py`, the write
slot is handed out in arrival order and tested for starvation in
`tests/test_db_concurrency.py`, and `m10` measured 64s against 156s serial on
three councils ([README.md:302](README.md:302)). None of that answers the
question the default turns on, which is whether a concurrent full run produces
the *same evidence* as a serial one. Until someone runs both, `--jobs 1`
remains the right default — and my recommendation is still that it stays,
since the run is not interactive and the conservative default costs nothing
anyone is waiting on.

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

1. **Who verifies candidates, and to what standard?** *Phase 4 built it on the recommendation below; the question of who actually does the verifying is still yours.* My recommendation: one named reviewer per row, the same identity `review_decisions` already records, and no bulk promote for anything above a candidate's source page — bulk *reject* is fine. Depends on whether anyone besides you will do it.
2. **Do you want history at all (F-05)?** Recommendation: not yet, and not as a general "version every table". If a specific claim needs it — advertised bands over time is the plausible one — add history to that table alone, with a caveat forbidding the differencing the census taught you to forbid.
3. ~~**Should `m13` be re-run now?**~~ *Settled in Phase 1:* re-run, and it had been a dry run all along. 477,199 rows.
4. **Retention for `data/raw` (P-02).** Recommendation: keep everything until it hurts, but measure and document the curve now so the decision is not taken in a hurry at 20 GB.
5. **Is `--jobs 4` worth promoting to default?** Recommendation: only after Phase 7's comparison, and probably not — the current default is the conservative one and the run is not interactive.

6. **Should a review resolution write to the codebase as well as the warehouse (D-05)?** Recommendation: yes. The UI already confirms a URL responds before storing it, which is the same standard `authority_websites.py` sets — so the answer is registry-quality at the moment it is given, and only its filing is not. Losing 86 of them proved the point.
7. **How often should `pipeline backup` run, and who deletes old ones (D-06)?** Recommendation: before every `run all` and on a daily schedule, keeping the last seven plus any labelled one. The failure was not that backups did not work; it was that the only one on disk had been taken after the damage.

## 8. Proposed workstreams — filed 2026-08-14, not yet started

Two of the three workstreams from the "large upgrade" review, filed so the
thinking survives, plus one from the longer-term workstreams review and one
from the sources review (Workstream G).
Workstream A (the verification campaign) is not a section here — it is F-01,
F-03 and the queue itself, already in the register, and its cost is labour and
the open-question-1 decision, not code. Workstreams D and E are existing
entries: D is F-05 and P-03, E is W-13, the §3J search entry and the unfiled
prerender idea.

The thesis the workstreams share: the project's ceiling is the number of
verified, cited rows — today zero — and the portal is presentable but
secondary. B widens what verification has to work on; C makes what it produces
legible as claims.

### Workstream B — New evidence terrain

Three sources, all public, all pay-relevant, each filed with the shape of the
claim it would support.

**B1. Gender pay gap reports · M** — mandatory annual public filings by
employers with 250+ staff. A new module over the government filing site, each
filing archived like every other source. Claim shape: "of the tracked
providers that must file, X report a mean gender pay gap of Y%". Depends on
the provider → employer mapping m04 already builds; needs a decision on the
scope rule — a provider under 250 staff is outside the law's reach, so its
absence must read as out-of-scope, not as a zero.

**B2. Living Wage Foundation registrations · S** — one public lookup per
provider, binary, citable. Claim shape: "N of 13 tracked providers are
accredited living wage employers". Fetch, archive, record accreditation date
and status like any other source.

**B3. Provider career and reward pages, and a sustained m16 crawl · M–L** —
`nhs_job_adverts` holds 35 rows **[live]**: the "only direct pay evidence"
([README.md:144](README.md:144)) is a sliver. A provider-side module over
career and reward pages — advertised bands, "rewards package" pages, listed
rates — plus a sustained crawl of the NHS Jobs feed the module already reads.
Claim shape: the advertised band and rate per provider per period — and the
F-05 decision (open question 2) is what turns that snapshot into the time
series the campaign's "the change is the claim" argument needs.

**B4. Authority-website registry to full coverage · M** — m09/m10/m15 are
coverage-limited by the hand-verified registry in `authority_websites.py`, and
the ~86 council URLs answered in the UI before D-05's fix were lost with the
override table ([§3B, D-05](docs/upgrade-roadmap.md)). Full 347-council
coverage means candidate discovery everywhere rather than on the verified
handful — the difference between searching one council and 315 that the
README records m09/m10 once paying for ([README.md:163](README.md:163)).

### Workstream C — The claims-to-evidence index

The difference between a data portal and an evidence portfolio: claims as
rows, each linked to the verified evidence that supports it, with the caveats
that travel with it. Changes no CAVEATS — it packages them.

**C1. A claim registry (migration) · M** — a sanctioned table where campaign
claims are rows: the claim's text, the verified evidence rows supporting it,
the caveats attached, the reviewer and the date. Nothing in it is computed —
a claim is a statement linked to rows, and the linkage is a human judgement
recorded like every other decision. The promotion guarantee (migration `0030`)
sets the standard: a claim without a recorded reviewer and decision history
is not a claim.

**C2. The "What we can say" portal page · M** — renders the registry: each
claim with its citations and its "you may not compute this from it" lines.
Read-only like every portal surface; the claims themselves are maintained in
the same review-and-decide workflow as everything else.

Open question folded in: who writes claims, and does a claim need one named
reviewer per row, the same identity `review_decisions` already records? The
recommendation is the one open question 1 already makes for candidates.

### Workstream F — The sector universe (the population workstream)

The thesis: the pipeline tracks 13 providers and 347 authorities, but the
denominator — how many organisations make up the sector — is unknown. Every
coverage statement needs a universe to be measured against, and none exists.
The universe is the upstream condition for W-12's matrix meaning anything
beyond the 347, for Workstream C's sector-level claims, and for any sentence
of the form "we track N of the sector's ~M".

**F1. The universe build · L** — reconstruct the complete provider and funder
population from sources the pipeline already reads: CQC registrations, the
charity register, Companies House, and the awardees in the 98,636 notices.
The work is reconciliation, not new collection: hundreds of organisations
joined by company and charity number where they exist, name-matched where
they do not — the same labour `unmatched_buyer_name` and
`possible_group_company` (D-04, still pending) already represent, done
systematically once rather than one review item at a time.

**F2. Coverage denominators · M** — with the universe in place, every
coverage statement gains a denominator: "we track N of the sector's ~M
providers", "contracts are observed for X of M". Universe membership must
keep the match-basis discipline m04 already sets — name-only matches stay
name-only, unconfirmed matches stay unconfirmed — or the universe becomes a
larger, unverifiable version of the problem it solves.

**F3. Sector shape as a publication · M** — the universe is itself an
evidence product: sizes, funder→provider relationships, concentration. An
export with its own provenance and match-basis columns gives the campaign its
first whole-sector figure.

Dependencies: none blocking — every input is a source already collected. One
design question, recorded rather than decided here: whether the universe
lives in a new `sector_universe` table or extends `providers`
([README.md:122](README.md:122)); organisations are not personal data, so the
`restricted_` discipline does not touch it.

### Workstream G — Further sources and expansions

Eight additions from the sources review: two comparator markets, two
expansions of existing modules, a harvest module, a discovery API, a
statutory reference table, and an advert aggregator. Filed with the shape of
the claim each would support; each passes the same filter as every module —
public licence, robots respected, process-wide rate limit, provenance or
NULL.

**G1. ONS Data Explorer API (ASHE) · M** — the Annual Survey of Hours and
Earnings, via the ONS developer hub ([developer.ons.gov.uk](https://developer.ons.gov.uk/)):
median pay by industry (SIC) and occupation, public and OGL. Claim shape:
"median pay for [occupation] in England is £X, against which the sector's
advertised bands sit at Y%" — the strongest missing comparator market for
what the sector pays versus comparable work. One discipline to settle when
the claims index (C1) meets it: an ASHE-versus-adverts statement is a
side-by-side comparison, not an arithmetic ratio, and the CAVEATS reading
decides which of those a claim may make.

**G2. Skills for Care workforce intelligence · M** — adult social care pay
and headcount benchmarks; substance misuse sits between health and social
care, and its workforce market is largely the care workforce. Claim shape:
contextual pay and turnover comparators. **The access shape is the first
task, not the module**: the intelligence service publishes reports, and its
machine-readable access is partial — verify what is fetchable and at what
terms before committing to a module.

**G3. Companies House PSC register · S** — People of Significant Control,
the same API family and key m04 already holds. Claim shape: ownership edges
for the entity graph — "who owns whom" for the 13 providers and, later, for
the universe (F1). No new politeness surface, no new key; the same fetch,
archive and match-basis disciplines as m04.

**G4. GOV.UK content API · S** — expand m02 to Employment Appeal Tribunal
decisions alongside the current tribunal feed. Same host, same client,
incremental. Claim shape: appeals and their outcomes deepen the tribunal
evidence layer — a decision affirmed or overturned is a materially different
datum from the first-instance judgment.

**G5. Council spend-transparency files · M–L — deliberately not an API** —
councils publish £500+ spend as files on their own sites, and there is no
central API for them. A harvest module in the m09/m10 shape: discover the
file (depends on B4's full website coverage), fetch, archive, parse line
items. Claim shape: "council X paid provider Y £Z in [period]" — actual
money flows, the strongest procurement evidence the corpus could hold.
Line-item quality varies council to council, so the NULL discipline does
real work here: an unreadable file is a `parse_failures` row and a review
item, not a zero. Also feeds F1 (awardees from spend) and C (claims about
real payments).

**G6. data.gov.uk CKAN API · M** — the central open-data catalogue: datasets
searchable by organisation and keyword, with resource URLs, for every council
and department. Claim shape: discovery — which public datasets exist for an
authority and where their resources live. Why it earns its place here: one
module that multiplies four existing items — G5 (many councils catalogue
their spend files there), B4 (website-registry cross-check), W-13 (what each
authority publishes) and the sector universe (F1). Public, no key,
documented, OGL.

**G7. National Living Wage and National Minimum Wage reference · S —
deliberately not an API** — the statutory floor as a small annual reference
table from the gov.uk rates pages: one row per year, updated once a year,
citable. Claim shape: the anchor for every "advertised band versus the
floor" statement the campaign will draft. The gate G1 flagged applies here
too: the comparison itself is side-by-side, and any ratio ("X% above the
NLW") is the CAVEATS reading's decision, not the module's.

**G8. Adzuna API · M — conditional** — third-sector and provider job adverts
with advertised pay: the widest non-NHS window on what the sector advertises.
Conditional on two reviews before the module starts: the API's terms
(commercial — robots and rate limits as it sets them), and the reliability
of its parsed salary fields, where an unparseable salary is `NULL` plus a
`parse_failures` row, not a guess. If the terms fail, drop it — m16 and B3
already own the NHS and provider-site halves.
