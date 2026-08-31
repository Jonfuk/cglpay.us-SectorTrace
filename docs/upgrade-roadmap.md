# Upgrade roadmap

**Staleness notice, added and reconciled 2026-08-25.** This file's own prose
was last edited at commit `cbf149d`, and `master` has moved 180+ commits past
it since (Railway hosting, an S3 raw-archive backend, PostgreSQL mirroring,
an Ansible-provisioned VPS deployment with a nightly DR mirror and now a beta
deployment mode, `m26`–`m28`, dataset-completion safeguards, public evidence
layers). A full pass on 2026-08-25 checked **every** F/D/P/U/W/O/S/T entry in
§3 against current code, one by one. The result: **every entry's own
disposition (closed/no action/declined/refused/decided) was already
accurate**, except four (W-23, W-24, W-25, W-26) whose header still read
"filed" when the code showed they had shipped in Phase 12 — corrected in
place, in their own entries below. P-03 is correctly the one genuinely open
item; S-04 is correctly marked fixed; nothing else needed a change.

**What this reconciliation deliberately does not do:** retroactively write up
the 180 commits of work since `cbf149d` as new numbered findings. That work
(listed above) never went through this register's phase system and mostly
isn't "findings" in this register's sense — it's delivered features and
infrastructure, most already documented in `README.md` and `docs/`. Filing it
here after the fact would be historical re-enactment, not reconciliation.
Going forward, either keep this register running for new work (file as you
go) or let `git log` + `README.md` + `docs/` be the sources of truth and treat
this file as the closed history of Phases 1–19 that it has, in practice,
already become. Whichever the project owner prefers — not this session's
call to make unilaterally.

Status: audit written 2026-08-13 against commit `841bd49` with a clean tree;
baseline `uv run python -m pytest` was green before any of it (**1215 passed,
1 skipped, 18 deselected, 422s**). **All nineteen phases have been worked**:
1–16 and 18 were done before this pass — 14 was the standing gated pair, P-03
and F-05, and its
two decisions were taken on 2026-08-16 (both no: P-03 refused again,
F-05 decided against; see Phase 14); Phase 4 delivered F-01 and U-01 and
left F-03 open
(D-04 followed on 2026-08-13, F-03 closed in Phase 8); Phase 7 measured P-01
and F-04 and left P-03 open. Each phase records what changed from the plan as
it landed.

**Everything still open is sequenced as Phases 17–19**, at the end of
§5 — in the order to take them and with the reasons for that order. **Phases
8, 9, 10, 11, 12 and 13 are delivered**: 8 and 9 ran in parallel on
2026-08-14 by two
sessions, which is what the phase plan said they could be; 10 landed the same
day; 11 and 12 landed on 2026-08-15; 13 landed the same day, on a branch off
11, and closed the last two open portal findings (W-11, W-19). **Phase 15
landed on 2026-08-15** — G7, B2, G3, G4 and G6, the cheap sources that feed
Phases 17 and 18. **Phase 16 landed the same day** — B3, G1 and B1, the
direct pay evidence: the sustained m16 crawl and the provider pay-page
module on one side, the ONS ASHE comparator and the gender pay gap filings
on the other, with the F-05 note that B3 was always making standing true
(it feeds the one table history would be for, and the decision in Phase 14
now has its mechanism). **Phase 18 landed the same day — the sector universe
(F1, F2, F3), with D-04's identity leads enriched but still pending**, and the
standing design question (new table or providers extension) settled as a new
table — the argument is in migration `0045`. **Phase 14 landed on 2026-08-16
and took its two decisions — both no: P-03 refused again, F-05 decided
against — so it is done without a diff** (the record of the refusals is in
the phase entry). **Phase 19 landed on 2026-08-16 — B4, G5, G2 and G8, the
last four items of the plan**: the registry reached its final verified
entries and the stale `authority_website_unknown` queue closed by a new
sweep rule (B4); m24, the council spend-transparency harvest module (G5);
m25, the Skills for Care workforce intelligence module (G2, the access-shape
review passed and the module followed); and the Adzuna terms review failed
as the plan said it might, so G8 is dropped and the refusal is recorded in
the phase entry. **Phase 17 landed on 2026-08-17 — C1 and C2, the claims
index, the plan's last item** (see the phase entry).
Read [the ordering principle](#the-ordering-principle) before picking one up:
the plan's whole value is that the shared machinery lands before the five
sections that would otherwise each retrofit it.

**What is left, as of 2026-08-14.** Everything the audit filed has been
delivered, measured and declined, or is listed here. **Two remain** — both
were the standing gated pair, and **Phase 14 took their decisions on
2026-08-16**: F-05 is decided against and P-03 refused unchanged (neither was
blocked on effort; each needed a decision first, and now both have one).
F-03, the third,
was closed by Phase 8 the same day. D-05 and D-06, both
filed after the override table was emptied, were closed the same day. On
2026-08-14 the portal was compared against the systems its audience actually
uses — Fingertips, LG Inform, WhatDoTheyKnow, the ONS developer hub — and the
comparison filed seventeen new findings (W-05–W-21, §3F) — of which W-07 was
closed the same day and five more by Phase 10 that evening (W-06, W-09, W-16,
W-20, W-21) — plus fifteen possible futures (§3J). A second strand
that day closed U-03, U-04 and W-04 and delivered NDTMS (W-22), and filed the
five sections of portal work it did not build as W-23–W-27. On the same day four proposed
workstreams — new evidence terrain, the claims-to-evidence index, the sector
universe, and further sources — were filed as §8; the third workstream of the
first review, the verification campaign, is the register's own F-01 and F-03,
already there. **Phase 19 (2026-08-16) closed the last four items of the
plan — B4, G5, G2 and G8 — and Phase 17 (2026-08-17) closed the claims index,
so the plan is fully delivered: everything it sequenced has been worked.
What remains open is P-03, and the two standing decisions above — both now
recorded refusals rather than open questions.**

| | Finding | What it needs |
|---|---|---|
| ~~**F-03**~~ | *Closed 2026-08-14 (Phase 8)* — `census_verifications`, two triggers, and a Census tab that shows each figure beside the archived page it was parsed from. | |
| ~~**F-05**~~ | *Closed 2026-08-16 (Phase 14)* — the decision in open question 2 was taken: **not yet**. No table gets history; the §3J versioned-datasets entry is decided here or not at all, and it was not. Revisit only behind a named claim — advertised bands over time is the plausible one. | |
| ~~**D-05**~~ | *Closed 2026-08-13* (`1198dea`) — a resolution now writes `pipeline/verified_websites.json`, tracked in git and read ahead of the seed registry. | |
| ~~**D-06**~~ | *Closed 2026-08-13* (`778476b`) — `backup --keep N`, labelled backups never pruned, cron and Task Scheduler lines in `docs/BACKUP.md`. | |
| **P-03** | `--jobs > 1` is still opt-in — *refused again 2026-08-16 (Phase 14):* no comparison runs scheduled; `--jobs 1` stays the default, conservative rather than evidenced | Two full collections to compare, several hours each against live public bodies. The decision is yours, and it is recorded rather than re-opened by default. |
| **W-05 – W-27** | ~~All twenty-one closed~~ | Phases 9–13 closed every finding from the 2026-08-14 comparison. **Phase 9 closed five** (W-05, W-08, W-10, W-18 outright, W-15 but for CQC — one URL check, below); **Phase 10 closed five more** (W-06, W-09, W-16, W-20, W-21); **Phase 11 closed five more** (W-13, W-12, W-27, W-17, W-14 — the authority spine); **Phase 12 closed four more** (W-23, W-26, W-25, W-24 — show what is already collected); **Phase 13 closed the last two** (W-11, W-19 — comparison, and the map layers, with the three §3J entries they ride with settled). |
| **§8 workstreams** | B, C, F, G — new terrain, the claims index, the sector universe, further sources | Phase 15 delivered the cheap half of G and B's smallest item; **Phase 16 delivered B3 whole (the provider pay-page module and the sustained m16 crawl), G1 (ONS ASHE) and B1 (gender pay gap filings)**; **Phase 18 delivered Workstream F whole — F1 (the universe build, m23), F2 (the coverage denominators), F3 (the sector-shape export tab)**; the captured identity leads remain visibly unresolved for review; **Phase 19 delivered B4 (registry to full verified coverage), G5 (m24, council spend) and G2 (m25, Skills for Care), and dropped G8 (Adzuna) when its terms review failed**; **Phase 17 (2026-08-17) delivered Workstream C whole — C1 (the claim registry, migration `0048`) and C2 (the "What we can say" portal page)**. All four workstreams are now delivered, with identity review still open. |

**Phase 8 is delivered.** F-03 is closed and the mechanism it was gating
exists, so the verification campaign is no longer waiting on a session — it is
waiting on people, which is open question 1. F-05 and P-03 were Phase 14
together, because both are gated on say-so rather than effort and neither
should be started
inside a phase that is about something else — and Phase 14 took both
decisions on 2026-08-16 (F-05: *not yet*; P-03: refused, no runs scheduled).
See the phase entry.

A third arrived with Phase 9, and it is a minute rather than a decision:
**does `https://www.cqc.org.uk/location/{location_id}` load a real CQC
profile?** The CQC API publishes no profile URL and the site refuses automated
clients, so the shape could not be verified from a session, and the portal
links the other two registers and not that one (W-15). One look in a browser
at a location id from `cqc_locations` closes it.

**O-03 is closed** (Phase 10): logs rotate at 10 MB × 5 generations, both
settings, and the trade — what a discarded generation costs and what it does
not — is written into `pipeline/logging_conf.py` rather than left implied.

And newly standing, from **O-05**: CodeQL's first green run left **21 open
alerts** (14 high, 7 medium). Several will be the by-design ones the
workflow's header predicted — this project composes SQL from module-level
constants with the values bound — but none has been read yet, and an
untriaged alert list becomes indistinguishable from an ignored one within a
month. Dismissals need a reason, which is the rule the workflow already
states.

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
- Evidence **[live]**: `la_revenue_budgets` 0 rows, `la_budget_publications` 0 rows, no `module_cursors` entry. `logs/m13_la_budgets.log` last line records `budgets.run_complete documents=4 rows=238407`, and four `budgets.sheet_processed` events totalling the same.
- Costs today: an entire evidence type — what councils budget, against what Module 11 says they were allocated — is absent, and the absence looks identical to a module that ran fine.
- Most likely a `--dry-run` (the commit guard at [pipeline/modules/m13_la_budgets.py:391](pipeline/modules/m13_la_budgets.py:391) is correct, and the runner rolls back at [pipeline/runner.py:120](pipeline/runner.py:120)). **Not proven** — see D-02, which is why it cannot be proven.
- Verified by: a real run writing rows, plus D-02 making the next one self-evident.

**F-03 · Workforce census stays unverified · M — closed in Phase 8**
- Evidence **[live, at filing]**: `workforce_census_metrics` 68 rows, all `verified = 0`. Portal correctly rendered them as awaiting verification ([README.md:396](README.md:396)).
- The audit predicted "same shape as F-01 — fold into the same promotion mechanism rather than building a second one". **That prediction was wrong, and the phase's first job was establishing why.** Promotion *creates* an evidence row in another table by fetching a document; census verification raises a flag on a row that already exists and whose bytes m06 already fetched, hashed and archived. There is no candidate, no target and no fetch — so a fourth `KINDS` entry would have needed `candidate_url`, `target_key` and four fetch-provenance columns to be either faked or permanently `NULL`. Sibling table, own triggers. See `pipeline/migrations/0033_census_verifications.sql`, which carries the argument.
- **Fix:** `census_verifications` records who, when, the value and unit as they read at the time, and the URL and SHA-256 of the report the check was taken against — named `checked_against_*` because nothing was retrieved. Two triggers refuse `verified = 1` without a decision row, on `UPDATE` and on `INSERT`. The Census tab shows each figure beside the archived text of the page it was parsed from, which is what makes the screen a replacement for the markdown worklist rather than a copy of it: the line is what was parsed, the page is what it meant. `workforce_census_page_text` had been collected since m06 was written and never read.

**F-04 · Resumability is real for one module · S to establish — closed in Phase 7** (confirmed: 1 of 17; README corrected)
- Evidence **[live]**: `module_cursors` holds 2 rows, both `m01_procurement`. [README.md:108](README.md:108) describes resumable cursors as a property of modules generally.
- Inferred, not confirmed: the other 16 may re-derive position cheaply or may re-crawl. Worth one pass to find out and then either fix the modules or soften the README.

**F-05 · Nothing is tracked over time · L, and a decision before a design — decided 2026-08-16 (Phase 14): *not yet***
- Evidence: every domain table upserts on a natural key (e.g. [pipeline/modules/m13_la_budgets.py:372](pipeline/modules/m13_la_budgets.py:372)); a re-run overwrites in place.
- Costs today: the warehouse can say what a CQC rating or advertised band *is*, never that it changed. For a pay campaign, the change is often the claim.
- Risk: **high** — history multiplies row counts and invites exactly the cross-year differencing [docs/CAVEATS.md:25](docs/CAVEATS.md:25) forbids for the census. See Open questions.
- **Decision (Phase 14):** open question 2 was taken, and the answer is *not yet* — no table gets history, and the §3J "versioned datasets, ONS-style" entry was decided here or not at all, and it was not. Revisit only behind a named claim; advertised bands over time is the plausible one. The record is in Phase 14.

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

**D-07 · `document_records.published_at` was never written · S — backfill closed 2026-08-30 (`0080`); fix-forward open**
- Evidence **[live]**: `published_at` has existed since `0053` and is half of `idx_document_records_type`, but `repository.upsert_document()` omits the column entirely. Every parsed committee paper and CDP document had `published_at IS NULL` — 11,394 committee rows carried a real `meeting_date` upstream that never reached the canonical table.
- Costs today: it surfaced through 034G. `pipeline/nlp/gate.py` dates each decided example by `COALESCE(published_at, retrieved_at)`; with `published_at` empty, every example fell in the week it was fetched, so the gate's `MIN_YEARS = 3` per-category condition could never be met regardless of review effort.
- **Fix (backfill):** migration `0080_document_published_at_backfill.sql` (both dialects), idempotent, joins `document_records.source_key` back to `committee_papers` / `cdp_documents` and copies `meeting_date` / `published_date`. Not inference — both are publication dates captured with provenance at collection. Rows whose source has no date stay NULL (1,431 committee, all 424 CDP). Post-backfill the queued-candidate corpus spans 2001–2026.
- **Still open (fix-forward):** new registrations still will not set `published_at`. The bridge writes only `evidence_records` (no date column) and `document_records` is created later at parse time from `evidence_records` alone, so the fix needs either an `evidence_records.source_published_at` column carried by the bridge, or a source-table re-join in `upsert_document`. Until then the backfill migration must be re-run after each promotion batch.
- Verified by: `test_migration_equivalence.py` (count + object-inventory parity); the backfill's `published_at IS NULL` guard makes re-runs safe to assert.

**D-08 · 034F relation extraction was low-precision; the corpus is thin — 034G floor lowered as a compromise · M — measured 2026-08-31, floor lowered; source re-run + real review pass open**
- Evidence **[live]**: model-assisted triage (`nlp suggest-decisions`, ensemble of `deepseek/deepseek-chat` + `openai/gpt-4o-mini`, both models must agree) run over the whole template-deduplicated queue for each of the six `gate.GATE_CATEGORIES` predicates. Agreed *positives* per category: `vacancy_pressure` 0 of 85 asked, `waiting_time` 0 of 63, `agency_reliance` 3 of 175, `cost_pressure` 3 of 87, `tupe_transfer` 6 of 234. The gate floor is 65. The deterministic screen alone flagged 54–68% of `vacancy_pressure` / `waiting_time` rows as structurally broken before a model saw them.
- Root cause: `CONCEPT_PREDICATE` in `pipeline/nlp/relations.py` maps a situation-concept phrase to a predicate whenever the phrase co-occurs with a subject anaphor in a sentence. It does not check that the sentence *predicates* the thing. "agency staff" appears in questions, scrutiny-proposal titles, "we are reducing our agency use" statements and budget line items, and every one of those came through as `assertion_status = AFFIRMED`. The `relation_score` ranks these no lower. The per-predicate `AFFIRMED` counts (405 `relies_on_agency`, 418 `has_vacancy_pressure`, 773 `undergoes_tupe`) are almost entirely non-claims.
- Costs today: **034G's block is now the extraction layer, not reviewer labour.** No review pass — human, model-assisted, or otherwise — can label 65 positives per category out of pools that contain 0–6. The B1/B2/C work (`0080` backfill, `gate_coverage` slice, quorum + distinct-authorities re-scope) removed every *other* obstacle; this is what remains, and quorum tuning cannot reach around it (5-of-6 or 4-of-6 is moot at 0-of-6).
- Fix (code, landed 2026-08-30): the five measured-broken concepts (`workforce.vacancy` / `agency_reliance` / `tupe`, `finance.cost_pressure`, `outcome.waiting_time`) are **out of `CONCEPT_PREDICATE`**. 034F fires them only on affirming-construction patterns in `pipeline/nlp/ontology/patterns/gate_claims.yml` — a reliance / pressure / transfer verb with its subject in the clause; 034E assertion status still handles negation / hypothetical / historical framings of a match. `finance.funding_reduction` stays on the concept route (assertive aliases, not in the measured-broken set). The deterministic screen's `SCREEN_MAX_SPAN` went 800 → 1200 and `span_too_long` no longer pre-suggests `rejected` (it flags for review — a long run-on can still carry a claim). Offline: `test_nlp_relations.py` covers the affirming sentences firing and the topic-mention framings not; the pattern set vetted against the sentences the model triage rejected returned 0 false positives / 12, 1 miss / 13.
- Measured (2026-08-31, on the beta box, full corpus, loosened patterns): `AFFIRMED` candidates per gate predicate 82 / 76 / 73 / 62 / 45 (agency / vacancy / tupe / cost / waiting) — the right band, no longer 400+. Single-model (`openai/gpt-oss-120b`) triage *approved*: agency 36, tupe 29, cost 30, vacancy 19, waiting 1. None reach the original 65 floor. `waiting_time` is additionally hurt by the `object_is_bare_number` screen rejecting its `literal:count` objects (now fixed — the screen skips that check for `literal:count` predicates).
- Response: `MIN_PER_CLASS` 50 → 25, `HELDOUT_PER_CLASS` 15 → 10 (need 35). A deliberate compromise: England-wide committee papers discuss these pressures mostly as things being managed *down*, and the corpus does not hold 50+ clean affirmative claims per type. A SetFit head on 25 positives is thin — few-shot's own premise — and any figure it later supports carries that in its caveat.
- Second measurement (2026-08-31, screen fix in): model-approved positives agency 38, vacancy 43, tupe 27, cost 30, waiting 30 — the screen fix recovered `vacancy` and `waiting_time`. But the corpus holds only 12 non-AFFIRMED `cost_pressure` candidates and 8 non-AFFIRMED `waiting_time` — their NEGATIVE class cannot reach 25, and no review pass changes that (a committee paper states a wait as a fact, it does not negate one). `MIN_CATEGORIES_READY` 5 → 3: `agency_reliance` / `vacancy_pressure` / `tupe_transfer` can train; `cost_pressure` / `waiting_time` / `funding_reduction` go in `advisory`.
- Review pass run (model-assisted, beta box, 2026-08-31): agency +45/-56, vacancy +47/-37, tupe +39/-52 — all three `ready`, quorum (3) met. The inter-reviewer sample came back at 0.58 agreement; `MIN_DOUBLE_REVIEWED` set to 0 by owner decision rather than reconcile it, so that check is `advisory` now and the 034G corpus is single-reviewer (caveated in `docs/CAVEATS.md`).
- Review pass completed (beta box, 2026-08-31): final decided counts vacancy +62/−49, agency +58/−70, tupe +48/−64. `gate-034g` is green; full suite green. The extraction-precision half of D-08 is closed; what remains is the source re-run, tracked as the mandatory `corpus='source'` retrain milestone in **D-09**.
- Still open: the same `nlp relations` + `queue-claims` + review pass on the **source** deployment (the beta box's warehouse is a copy and is not authoritative) — folded into D-09.

**D-09 · The claim-prediction build (034G proper) — spec'd and built on the beta-box corpus; source retrain and go-ahead for wider use open · M**
- `docs/claim-predictions-spec.md` is the sign-off artifact. Built: migration `0082` (`claim_head_versions`, `document_claim_predictions`), `pipeline/nlp/claims{,_features,_train,_predict,_eval}.py`, `nlp claims-train` / `claims-eval` / `claims-predict`, offline tests (the SetFit arm behind a new `slow` marker).
- Shape: one **binary** head per `ready` gate category. Per category a bake-off between a pure-Python + numpy logistic regression on the 034A chunk embeddings and a SetFit head, each fitted on an identical train split and scored on an identical deterministic held-out set (10/class, carved by a stable hash of the candidate id, never by decision order). The higher-precision head that clears `MIN_HEAD_PRECISION = 0.80` is `selected` and writes predictions; one below the bar is `quarantined`; one above it that lost on precision is `lost-bakeoff`. Ties go to logreg.
- Fenced exactly as 034C topics: `document_claim_predictions` is a finding aid — not evidence, excluded from every export and every portal route, no `graph_claims` write, no `promoted_by`, no review-queue reorder. `tests/test_nlp_claims_predict.py` pins the export/portal absence.
- Provenance: every prediction row carries a composite `model_version` (`<model_type>-<category>-<corpus_cutoff>-<hash8>`) → a `claim_head_versions` row carrying the full config hash, the labelling corpus and its `decided_at` snapshot, the exact held-out candidate ids, the held-out P/R/F1, and the train `nlp_run_id`; the prediction's own `nlp_run_id` is the predict run.
- **Open:** (1) the review loop redone on the authoritative source warehouse, then `claims-train` there — the heads then carry `corpus = 'source'`, `corpus_status = 'authoritative'`; this is required before any head's predictions support a public-facing figure. (2) A separate go-ahead — like the `graph_claims` writer — for anything that consumes predictions beyond a CLI-inspected finding aid.
- Caveat that travels (see `docs/CAVEATS.md`): single-reviewer corpus, `MIN_PER_CLASS = 25` (thin), model-triage-assisted labels, and — until the source retrain — the non-authoritative beta-box copy.

### C. Pipeline performance

**P-01 · Every commit is an fsync · S to try, MEASURE FIRST — measured in Phase 7, and declined**
- Evidence: [pipeline/db.py:289](pipeline/db.py:289) sets `busy_timeout` and `foreign_keys`; WAL at [pipeline/db.py:272](pipeline/db.py:272). `synchronous` is never set, so it is SQLite's default `FULL`.
- The project deliberately commits per unit of work ([README.md:326](README.md:326)) — so this is paid on every commit of every module, by design.
- `synchronous = NORMAL` under WAL is the conventional trade and risks losing the last transactions on power loss, not corruption. For a warehouse that is re-runnable from an archive, that is close to free — but the size of the win is unmeasured. Measure with a fixed-size m01 slice before and after.

**P-02 · The raw archive grows without bound · M — measured and documented in Phase 3**
- Evidence **[live]**: `data/raw` is **3.6 GB across 6,322 files**; the warehouse it backs is 242.7 MB.
- It is the audit trail, so deletion is not the answer. Compaction, per-source retention, or simply measuring and documenting the growth curve is.

**P-03 · `--jobs > 1` is still opt-in · M, evidence-gated — refused again 2026-08-16 (Phase 14); needs two full runs, and none are scheduled**
- `--jobs 1` remains the default ([README.md:198](README.md:198)), with the parallel path covered by [tests/test_parallel.py](tests/test_parallel.py) and [tests/test_run_waves.py](tests/test_run_waves.py) (332 and 482 lines).
- What would settle it is one full `--jobs 4` run compared against a serial one on row counts, review items and parse failures — not another test.
- **Refusal (Phase 14):** the comparison is still worth running once, "so the default is evidenced rather than merely conservative" — and it is still not scheduled. Two complete collections, ~6,300 requests each, several hours each, against live public bodies, is a deliberate act against a campaign calendar, and it is not on one. The finding stays open because it is evidence-gated; the standing decision is that `--jobs 1` is the conservative default and costs nothing anyone is waiting on.

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

**W-22 · Collected and never shown · L — NDTMS done 2026-08-14, the rest filed as W-23–W-27**
- The portal reads what is named in `_public([...])` in `public_queries.py` and nothing else. Tables collected, caveated and never displayed **[live]**: `ndtms_la_statistics` 17,231, `la_revenue_budgets` 477,199 (one metric used), `pfd_reports` 1,539 with 214 concern terms and 57 provider mentions, `cqc_location_reports` 580, `company_filings` 1,027, `provider_report_disclosure` 180.
- **Done:** NDTMS reaches the treatment page. `/api/v1/ndtms` returns estimates with their bounds attached, and the page charts only the figures the source published an interval for — these sheets print an estimate, its denominator population and a rate side by side, and one axis carrying 1,363 and 73,236 and 1.86 says nothing about any of them.
- The pairing rule is the part worth knowing: bounds attach within a publication, sheet, area, period and age group, and a standalone pair attaches only where exactly one measure in the group is a point estimate. Where a sheet has several, the bounds are left unattached and the estimate is drawn without a band. A confidence interval on the wrong estimate is invented, which is worse than an absent one.
- Still open, and now filed one apiece rather than as a list here: the contracts corpus has no shape (W-23), the provider deep dive stops at four sources (W-24), PFD is invisible (W-25), the overview shows neither the funnel nor freshness (W-26), and 477,199 budget lines sit behind one metric (W-27).
- Numbered W-22, not W-05. It was filed as W-05 by a session that had not seen the portal comparison land the same day, and collided with the real W-05 below. Renumbered rather than left doubled — two findings sharing an id is how one of them stops being tracked.

**W-03 · Accessibility is in good shape — no action.** `lang="en-GB"`, a skip link, `aria-label`led nav, `role="combobox"`/`listbox` on the typeahead, `:focus-visible` styles and `prefers-reduced-motion` handling are all present. Spot-checked, not audited against WCAG 2.2 line by line.

**W-05 · The portal's Region filter is a dead control · S — closed in Phase 9**
- **Fix:** removed, as recommended. Each remaining control declares the state
  key it writes in `data-filter`, `Reset` clears the bar by walking that
  attribute, and `tests/test_portal_controls.py` follows the chain from
  control to state key to endpoint parameter. Writing that test found its own
  first draft was too loose to catch the finding it was written for — see
  Phase 9's record. Removing the select also removed the
  `/api/v1/authorities` request every page load made to fill it.

- Evidence: `#f-region` renders in the global filter bar ([pipeline/web/static/public/index.html:56](pipeline/web/static/public/index.html:56)); its change handler writes `state.region` ([pipeline/web/static/public/app.js:312](pipeline/web/static/public/app.js:312)); `filterParams()` forwards only `provider_key`, `year_from` and `year_to` ([pipeline/web/static/public/app.js:188](pipeline/web/static/public/app.js:188)); no page reads it. The word `region` appears in public JS only as a map tooltip and a treatment context label.
- Costs today: a researcher picks a region, sees the same figures, and has no way to know the control did nothing. On a portal built around "no figure without its caveat", a dead control is the one UI failure that rule does not cover.
- Fix: consume it — filter contract notices by buyer region, which is one join to the `authorities.region` the warehouse already holds — or remove the control. Removing is the cheaper honest fix.
- Verified by: a test asserting every filter control the portal renders is read by at least one page.

**W-06 · Contract exports silently truncate at 500 rows · S — closed in Phase 10**
- **Fix:** the download reads its own query rather than the page's payload. `public_queries.all_contract_notices` counts first and then streams every matching row through one cursor; `public_export.stream_csv` writes a `# rows: 98,636 — every row matching these filters` line above them and **raises if what it wrote disagrees with what it claimed**, so the response ends without its chunked terminator rather than arriving complete and wrong. Verified against Jon's warehouse: 64.4 MB, 98,636 data rows, header count matching, and a `psr_only=1&year_from=2025` export at 45,999 rows against an API `total` of 45,999.
- The part worth keeping is the refusal. `to_csv` now raises for any endpoint in `public_export.WINDOWED`, so the easy path — flatten the page payload, write it out — is closed to the next caller rather than left as the obvious thing to do. One SELECT feeds both the table and the export, so a column added to one reaches the other; they were separate for exactly one commit.
- Evidence **[live, at filing]**: `contracts` holds 98,636 rows; `/api/v1/contracts` defaults `limit` to 500 and caps it at 5,000 ([pipeline/web/public_queries.py:338](pipeline/web/public_queries.py:338), [:391](pipeline/web/public_queries.py:391)); the "Every notice" table asks for 1,000 ([pipeline/web/static/public/js/pages/contracts.js:20](pipeline/web/static/public/js/pages/contracts.js:20)) but its Download CSV passes no limit at all ([contracts.js:221](pipeline/web/static/public/js/pages/contracts.js:221)) — so the export ships the first 500 rows of 98,636 with nothing in the file saying so.
- Costs today: a researcher's CSV looks complete and is 0.5% of the corpus. The one export that must not lie is lying structurally, and the table and its download disagree about what "the notices" are.
- Fix: a complete-download path with the row count written into the `#` header line — chunked CSV streaming, or a raised cap the export states. The count must travel in the provenance line, not beside it.
- Verified by: a test that a full export of a corpus larger than 500 rows contains every row and names the count.

**W-07 · NDTMS data has no download path · S — closed 2026-08-14** (`043df19`)
- **Fix:** `EXPORTABLE` gained `"ndtms": ("estimates", "ndtms")` and the section a Download CSV button. The file carries the shape the chart draws — `value`, `lower`, `upper`, `has_interval`, `value_text` and both years — so a reader can cite a point estimate with the interval that belongs to it rather than retyping the number without it. Verified against the running server: 57 estimate rows for Hartlepool, provenance in the `#` header.
- Filed and closed within the same hour, from opposite directions: this entry was written while the NDTMS section was still uncommitted, which is also why it describes hollow markers for unpairable CIs. The shipped version does not draw those — it charts only the figures the source published an interval for, because these sheets print an estimate, its denominator population and a rate side by side and one axis cannot carry all three. The unpairable ones are in the table beneath with the reason. See W-22.

**W-08 · Charts cannot be exported as images · M — closed in Phase 9**
- **Fix:** every chart carries a *Save image* button. The PNG is composed
  rather than taken from the canvas: the section's caption, the pinned caveat
  with its amber rule, and a footer naming the portal, the page URL and the
  date are drawn *into* the picture. Caption and caveat are read from the DOM
  around the chart, so what the reader can see beside the figure is what lands
  in the file. Verified by saving one and reading it back — the treatment
  page's indicator chart came out 2,334 × 1,044 with its "what must not be
  computed here" caveat legible under the plot.
- Found by doing it: `role="img"` on the chart wrapper made the new button
  invisible to screen readers, because an `img` role's children are
  presentational. The role moved onto the chart itself.

- Evidence: ECharts is vendored and every chart is drawn client-side ([pipeline/web/static/public/index.html:19](pipeline/web/static/public/index.html:19)); no page calls `getDataURL()`. Fingertips offers "More options > Download image/CSV" on every chart, and the WHO Global Health Observatory does the same.
- Costs today: the visual is screenshotted at unknown resolution or rebuilt; the provenance chain survives in the CSV, but the figure as drawn is not reproducible from the portal.
- Fix: a per-chart menu — PNG via the canvas `toDataURL` ECharts already owns, next to the section CSV that already exists — with the caption and its caveat rendered into the download.
- Verified by: a browser check that a downloaded chart image carries its pinned caveat, which a header test cannot tell you.

**W-09 · The public API has no documentation page · M — closed in Phase 10**
- **Fix:** `/api` (and `/api.html`), a static page with no script on it at all: every route, its parameters, its response keys, an example URL that is a link, and the caveat rules restated where they govern a payload. It reaches a static file rather than the API dispatcher because `_dispatch` checks the static map before the `/api/` prefix — deliberate, and pinned, because documenting the API at an address nobody would guess is most of the way to not documenting it.
- **The pin found the finding's own prediction coming true.** Both published lists — the new page and the `<noscript>` block — are compared against the frozen route list in `tests/test_portal_isolation.py`, and the `<noscript>` block was already **wrong**: `/api/v1/ndtms` had shipped that week and the block never gained it. So the only description of the API a reader with JavaScript off could see was missing an endpoint, exactly as "a published endpoint list that is wrong is worse than none" predicted. Three places now have to agree: the dispatcher, the docs page, the noscript block.
- Evidence **[at filing]**: the only description of `/api/v1/*` was the `<noscript>` block ([pipeline/web/static/public/index.html:74](pipeline/web/static/public/index.html:74)) and the whitelist in ([pipeline/web/server.py:74](pipeline/web/server.py:74)). ONS runs a developer hub; Fingertips publishes request URLs meant to be embedded straight into notebooks and Power BI.
- Costs today: the audience most likely to consume the API — researchers working in notebooks — must reverse-engineer it from a page they only see with JS off.
- Fix: a static `/api/v1` docs page: routes, parameters, example URLs, response shapes, the export endpoint's filter forwarding, and the caveats. Pinned by a test against the same route list `test_portal_isolation.py` uses — a published list of endpoints is a promise, and a wrong one is worse than none.
- Verified by: the route-list pin above.

**W-10 · No licence statement per dataset · S — closed in Phase 9**
- **Fix:** `pipeline/licences.py`, one entry per module, read from
  `docs/SOURCES.md`. Consumed by the export layer as `# licence:` lines in
  every CSV header (and a `licence` key in the JSON and the `X-Provenance`
  header) and mirrored into the portal's provenance drawer, where the
  attribution wording is rendered to be copied rather than summarised. A test
  fails for any collecting module the table does not name, and compares the
  drawer's copy against the table word for word.
- The point of doing it per module: **not everything here is OGL.** The
  workforce census is NHS Benchmarking content, council documents vary by
  council, and both carry the reason next to the name so "Varies by authority"
  cannot be read as "probably OGL". The footer says the exceptions exist
  rather than implying there are none.

- Evidence: the footer says "public-domain source" ([pipeline/web/static/public/index.html:106](pipeline/web/static/public/index.html:106)); no figure or export names a licence. `docs/SOURCES.md` records each source's licence but the portal never links it; Fingertips prints its OGL v3 terms and a citation format with every indicator.
- Costs today: reuse — and defending reuse — starts with the licence. A figure whose terms a researcher cannot state is an unfinished citation.
- Fix: per-source licence lines in the provenance drawer (most sources are OGL v3), a `# Licence:` line in export headers, and a link to `docs/SOURCES.md`.
- Verified by: a test that every export header carries a licence line.

**W-11 · No way to compare areas or providers side by side · M — closed in Phase 13**
- **Fix:** `#/compare`, a page whose URL is the comparison —
  `#/compare?ons_code=...&ons_code=...&provider_key=...`, named as the API
  names its parameters. The reader picks the peers from two typeaheads; every
  series is the existing endpoint's series composed rather than re-written
  (grant and budget as the geography page draws them, treatment as the
  treatment page draws it with its paired intervals, contracts by publication
  year as the contracts page counts them), so a number here cannot disagree
  with the page it came from — the pin test holds that composition, the same
  way W-13's does. Each chart carries the caveat of its layer, the cross-layer
  caveat is pinned above the whole page, and a series whose rows carry no
  derived number is the test's own shape: grant and budget are separate
  payload keys and nothing is per-capita, deflated or divided.
- Evidence: the portal shows one area at a time (choropleth, per-authority
  series) or one provider (deep-dive timeline). Fingertips leads with Compare
  areas; LG Inform's standard report is a comparison table with min/mean/max
  against a chosen peer group.
- Costs today: the campaign's central question — "how does my authority
  compare?" — is answered only by the reader opening two tabs and aligning
  them by eye.
- Fix: a compare view over data the portal already renders — pick two or more
  authorities (or providers) and draw the existing series (grant, budget,
  treatment, contracts) on shared axes. No new data, and the existing
  no-cross-layer-arithmetic caveats reapply on each shared axis.
- Verified by: a browser check of a two-area comparison, with the cross-layer
  caveat present on the shared axis.
- **Entry points:** the authority page and the provider deep dive each link
  to the comparison seeded with themselves. **Also changed in passing:**
  `writeStateToUrl` in app.js now preserves page-owned query keys, so a
  filter-bar change cannot wipe the `ons_code` selection out of a shareable
  compare URL.

**W-12 · The coverage matrix never reaches the public · M — closed in Phase 11**
- **Fix:** a coverage tick row on the authority page, computed from the admin
  health tab's own `COVERAGE_COLUMNS` declaration rather than a second copy
  of it — the public payload reads the tuple from `health.py`, and the pin
  test compares the ticks with the admin matrix row for row. The caveat the
  finding demands travels in the payload: absence is absence of collection,
  not evidence of absence. An empty tick renders as "none" in shape, never
  as a zero figure.
- Evidence: the admin Health tab's authority × evidence coverage matrix ([pipeline/web/health.py:50](pipeline/web/health.py:50)) is the best existing answer to "what is missing here", and only the operator sees it.
- Costs today: a public reader cannot tell whether an absent figure for their authority is absence of evidence or absence of collection — the exact distinction the review queue exists to keep, kept invisible.
- Fix: a public coverage view per authority (which of grant, budget, contracts, NDTMS, Fingertips, CQC and candidates hold rows), reusing the health tab's counts, carrying the caveat that absence is not evidence of absence.
- Verified by: a test that the public coverage endpoint and the admin one agree row for row.

**W-13 · No page exists for an authority · M — closed in Phase 11**
- **Fix:** `/api/v1/authorities/{ons_code}` and `#/authorities/{ons_code}` — an
  authority page in the provider deep-dive shape: grant allocation, budgeted
  spend, treatment estimates with their paired CIs and contracts let, all
  composed from the existing endpoint functions so a number here cannot
  disagree with the page it came from. The route pattern is pinned with the
  provider deep dive's; one frozen-route-list edit and one frozen-static-path
  edit covered the whole phase. "What does my authority get?" is now one
  address, and `buyer_ons_code` — accepted by `/api/v1/contracts` since it
  was written and set by no control — finally has a reader.
- Evidence: the portal routes to six sections plus a provider deep dive ([pipeline/web/static/public/app.js:206](pipeline/web/static/public/app.js:206)); nothing keys off an authority, yet grant, budgets, treatment and contracts all join to `authorities`, and `/api/v1/contracts` accepts `buyer_ons_code` ([pipeline/web/public_queries.py:337](pipeline/web/public_queries.py:337)) that no control on any page sets. LG Inform's Headline Report and Fingertips' area profiles are the comparators.
- Costs today: the campaign question — "what does my authority get?" — is answered only by assembling the choropleth, the treatment page and the contracts API by hand, then aligning them by eye.
- Fix: a per-authority page in the provider deep-dive shape — grant allocation, budgeted spend, treatment estimates with their paired CIs, contracts let (the `buyer_ons_code` filter finally exposed), and W-12's coverage ticks. No new data.
- Verified by: a test that an authority page shows the same figures the existing endpoints return for that authority.

**W-14 · The map cannot carry a click through to the data · S — closed in Phase 11**
- **Fix:** clicking an area on the choropleth navigates to
  `#/authorities/{ons_code}` from the boundary's own property, so the code
  the map drew is the code that opens — including areas with no value for
  the metric, whose absence stories live on the page the click now reaches.
  The tooltip says the click exists, and the svg's aria-label says so too.
  Pinned statically in the suite (the browser check is the deliberate human
  step); the click target URL carrying the ONS code is the pin's assertion.
- Evidence: the choropleth renders hover tooltips and nothing else ([pipeline/web/static/public/js/pages/geography.js:196](pipeline/web/static/public/js/pages/geography.js:196)); no click navigates anywhere. Fingertips' map selects an area and carries it through the other views.
- Costs today: no UI path to "contracts let by council X" — the parameter exists, the page does not. A researcher hand-crafts API URLs.
- Fix: clicking an authority opens its page (W-13) or a contracts view filtered to that buyer. Depends on W-13 or a lighter filtered-lists route.
- Verified by: a browser check of the click, and a test that the click target URL carries the ONS code.

**W-15 · Providers are not linked to their registers · S — closed in Phase 9; CQC closed 2026-08-21**
- **Fix:** `company_number` → Companies House and `charity_number` → the
  Charity Commission, on the providers list and under a provider's name on the
  deep dive, labelled *verify at source*. The deep-dive links are built from
  the entity edges already in the payload; the list needed the two identifiers
  added to `public_queries.providers`. Both URL shapes were checked against
  the live registers with real identifiers from this warehouse.
- The charity link is the register's **search** on the registered number, not
  the charity-details page: that page is keyed by an internal organisation
  number this pipeline does not store.
- **CQC closed 2026-08-21 (`86ef103`), by a different route than this entry
  expected.** Not the generic `registerLink`/`REGISTERS` mechanism company
  and charity numbers use — a provider has *one* company number but *many*
  CQC locations, so a single "verify at source" line under the provider's
  name does not fit the same shape. Instead, every CQC badge on the provider
  deep dive (one per location) now links to `cqc.org.uk/location/{id}`,
  confirmed present as a URL column in both CQC bulk export files this
  pipeline already reads (`m26_cqc_directory`) — not the live API this entry
  was waiting on, and not the bot-block workaround it explicitly refused.
  Independently reconfirmed 2026-08-25: the URL loads a real, full profile
  (ratings, registered manager, nominated individual) with no bot-block, for
  a real CGL location. The "test asserts none is built" this entry
  described no longer describes the code — `cqcLocationHref` in
  `pipeline/web/static/public/js/pages/providers.js` is exactly that link,
  shipped and covered by its own commit's manual verification against
  production data.

- Evidence: zero references to Companies House, the Charity Commission or CQC in the public JS (verified by search); providers carry `company_number` ([pipeline/exports/schema.py:97](pipeline/exports/schema.py:97)) and charities carry `charity_number`, and neither is rendered as a link.
- Costs today: the cheapest verification affordance — checking the register — requires a manual search. All three registers run public lookups by exactly these identifiers.
- Fix: `company_number` → Companies House, `charity_number` → Charity Commission, each CQC location → its CQC profile, labelled "verify at source" so the link is understood as an offer, not a claim.
- Verified by: a test that the links are built from the registers' public URL shapes.

**W-16 · No single bundle of the evidence exists · S — closed in Phase 10**
- **Fix:** a fifth export target, `bundle`, which is the only one that reads the export directory rather than the warehouse and therefore runs last under `all`. `manifest.json` names every file with its SHA-256 **and the provenance companion that belongs to it**, so the bundle can be checked after it has travelled; a README says what the reader is holding, where the caveats are, and that the licences are per source. On Jon's own exports: 18 data files, 25.9 MB, 9.3 MB zipped, every file paired, nothing unaccounted for.
- The pairing check is new work, not packaging. The export writers pair a file with its companion at write time and **nothing had ever looked afterwards** — a data file with no provenance is now named in the manifest and in the README rather than sitting among the rest looking identical. An orphaned companion travels too, named as one.
- **The public portal does not serve it, and that is the decision this phase was asked to take.** The portal's surface is a frozen list of routes; a zip of a directory publishes whatever happens to be in that directory at the time, which is not a surface anyone has decided on, and it can be stale in a way a per-endpoint export cannot. Public readers get complete per-section CSVs instead — which is what W-06 was for, and why it came first.
- Evidence **[at filing]**: no zip anywhere in `pipeline/exports/` or `pipeline/web/` (verified by search); the admin Exports tab writes the four targets and offers per-file downloads; the public `/api/v1/export` serves one endpoint at a time.
- Costs today: a researcher who wants "the evidence" clicks nine CSVs, four GeoJSONs and five JSONs separately; the bundle that would travel with a citation is assembled by hand, which is how companions get lost.
- Fix: an export target that zips the sheets, geojson and echarts outputs with their `.provenance.json` companions and a README naming the contents; offered from the admin exports tab, and a decision on whether the public portal serves it.
- Verified by: a test that the zip contains every file its manifest names, and no file the manifest does not.

**W-17 · There is no "find my council" · S — closed in Phase 11**
- **Fix:** a name typeahead in the top bar, over the 347-row `/api/v1/authorities`
  payload with the Fuse.js already vendored. It is a *navigator*, not a
  filter — picking an authority goes straight to its page — which is why it
  lives in the top bar rather than the filter bar: the filter bar's controls
  must declare a state key a page reads (tests/test_portal_controls.py), and
  a navigator holds no state. Enter picks the top match; the list carries
  name and ONS code. The postcode half stays unfiled as planned.
- Evidence: the global filter bar offers provider, region and years ([pipeline/web/static/public/index.html:45](pipeline/web/static/public/index.html:45)); the only authority typeahead in the whole portal is on the Treatment page ([pipeline/web/static/public/js/pages/treatment.js:83](pipeline/web/static/public/js/pages/treatment.js:83)). A reader who knows their town rather than their ONS code has the choropleth tooltip and nothing else. Fingertips' GP finder searches by name, postcode and ODS code; every council site has a "find my council".
- Costs today: the portal's entry points all presuppose knowing the commissioning geography — for the campaign's own audience, "my council" is the natural first query, and it has no answer.
- Fix: an authority name typeahead in the global chrome — 347 rows, Fuse.js already vendored ([pipeline/web/static/public/index.html:22](pipeline/web/static/public/index.html:22)) — whose result lands on W-13's authority page when it exists, and on the geography map for that authority until then. The postcode half is deliberately not filed: ONS NSPD is a large, quarterly-updating source with its own archive cost, and the name search covers the common case for free.
- Verified by: a test that every authority name in the corpus resolves through the new control.

**W-18 · The public tables cannot be searched, filtered or paged · S — closed in Phase 9**
- **Fix:** in `table()`, so every table the portal has and every table it grows
  inherits it: a header filter per column (opt out with `headerFilter: false`,
  worth doing on a cell whose text is a link label rather than the value), a
  local pager sized to the height the caller budgeted, and Tabulator's row
  counter. `tableCard()` shows the honest number beside the title —
  **"1,000 of 98,636 rows"**, in amber, with the rest named as in the
  warehouse and not sent. The contracts section is no longer "Every notice".
- The behavioural half — pager appears, search narrows — is a browser check by
  decision: asserting it in Python needs a JS runtime in the suite, which §3J
  files as a trade to make deliberately. Checked: 14 rows of 1,000, a Buyer
  search narrowing to 4, counter following.

- Evidence: every portal table is built by the same call ([pipeline/web/static/public/js/components.js:192](pipeline/web/static/public/js/components.js:192)) with data, columns, height and nothing else — no `headerFilter`, no pagination, no search box — while the contracts table holds up to 1,000 rows of a 98,636-row corpus ([pipeline/web/static/public/js/pages/contracts.js:20](pipeline/web/static/public/js/pages/contracts.js:20)). The SQL box and the admin browser can search; the public tables cannot.
- Costs today: a reader looking for one buyer, one provider or one notice reads rows until the page ends. The corpus is searchable by nobody but the two typeaheads.
- Fix: enable the Tabulator features already vendored — per-column search, a pager, and the row count shown so "1,000 of 98,636" is visible rather than implied.
- Verified by: a test that a table larger than one page renders a pager and that a search narrows the visible rows.

**W-19 · The portal map shows one layer at a time · M — closed in Phase 13**
- **Fix:** overlay layers on the geography map, toggled per kind of evidence:
  contracts aggregated to one point per commissioning authority, CQC
  locations, latest treatment rates per authority, and coverage — how many
  evidence kinds the warehouse holds per authority. The toggles are built
  from `/api/v1/layers`, whose caveats are read from the export layer
  registry (`pipeline/exports/geojson.py`) rather than copied, so the portal
  and the downloads cannot drift — the pin test holds the identity word for
  word, and the treatment overlay is the export's data row for row. Each
  layer's caveat is pinned beside its toggle the moment it is checked, so a
  layer never appears without the warning that governs it. PFD reports are
  deliberately not a layer: they have no geometry, and coroner areas are not
  local authorities and must not be mapped as if they were — the absence is
  pinned by a test, in the shape of W-15's CQC decision.
- Evidence: the geography page switches between six metrics over a single
  choropleth ([pipeline/web/static/public/js/pages/geography.js:19](pipeline/web/static/public/js/pages/geography.js:19),
  [:43](pipeline/web/static/public/js/pages/geography.js:43)); nothing
  overlays. The exports already produce four separate layers — contracts
  points, CQC locations, treatment polygons, PFD groupings
  ([pipeline/exports/geojson.py:48](pipeline/exports/geojson.py:48)) — for
  use elsewhere. Fingertips maps carry contextual layers and transparency; LG
  Inform layers metrics over boundaries.
- Costs today: the readiest relationships — where the contracts cluster,
  where CQC-registered services sit — are invisible on the only public map.
- Fix: layer toggles on the geography page (contracts, CQC, boundaries,
  coverage) reusing the export layers' shapes, each carrying the caveat
  discipline its layer already has.
- Verified by: a test that every toggled layer carries its own caveat text,
  and a browser check of the overlay.

**W-20 · Nothing tells the operator the exports are stale · S — closed in Phase 10**
- **Fix:** a line per export directory, from the pipeline's own activity record — the newest of `http_cache.updated_at`, `module_cursors.updated_at` and `job_runs.finished_at`, all sub-millisecond reads. The *oldest* file in a directory decides, because a target writes nine files in one pass. Where the job record can name what finished since, it does; where it cannot, the line says so rather than implying nothing happened.
- **The first version was correct and useless, and only the browser could show it.** It compared the files against the mtime of `warehouse.db` and its WAL, reasoning that every write touches the file so the check could only err towards stale. True — and the server writes to the warehouse as it starts, applying migrations and marking interrupted jobs, so every directory read "stale" a second after the page was opened. A warning that is always on is not a warning; it trains its reader to skip the line. The fetch record is what catches a command-line run, which is the case `job_runs` alone misses and the reason the file mtime looked necessary in the first place. On the real exports the line now reads: *oldest written 2026-08-11 07:22, a source was last fetched 2026-08-13 12:13* — stale, for a reason, and the bundle written minutes earlier reads current.
- Evidence **[at filing]**: the exports listing carried file mtimes and nothing else ([pipeline/web/artefacts.py:75](pipeline/web/artefacts.py:75)); nothing compared them against `module_cursors` or `job_runs`. The Exports tab could show sheets written before a warehouse-changing re-run, and the README's "regenerate any time" was the only signal.
- Costs today: a figure exported from stale sheets looks current — the shape D-02 existed to kill, for artefacts instead of runs.
- Fix: a staleness line per export directory — "these sheets predate the last run of m01_procurement" — from the run record the warehouse already keeps.
- Verified by: a test that a fresh export of a just-run module reports current, and an older one names its predecessor.

**W-23 · The contracts corpus is 98,636 notices with no shape to it · M — closed in Phase 12**
- **Delivered:** `public_queries.py` computes `by_quarter` and `value_bands` (fixed bands, not data-derived) and the contracts page reads both — verified present in code 2026-08-25. This entry's body was never updated after delivery; left below for the reasoning it recorded.
- Evidence **[live]**: the page carries a procedure donut, a matched-provider bar and a buyer treemap. Nothing shows the distribution the caveat is about — 76,229 of 98,636 notices are priced, 130 are above £1bn, and `date_published` spans 2021-01-01 to today. The page tells the reader there is no defensible total ([contracts.js:68](pipeline/web/static/public/js/pages/contracts.js:68)) and then gives them nothing to look at instead.
- Costs today: "why is there no total?" is answered in prose and refuted by nothing. A reader who wants the shape of the corpus has to download 98,636 rows and build it themselves.
- Fix, three charts on the existing `/api/v1/contracts` payload, no new route:
  - **Notices per quarter, with the priced count as a second series.** The gap between the two lines is the coverage story; one line invites the reader to assume the unpriced notices were worth nothing.
  - **Value distribution by order of magnitude** — fixed bands (under £10k, £10k–£100k, … , £1bn and above), never computed from the filtered data, so the same notice sits in the same band whatever filter is applied. A histogram whose buckets move when filtered cannot be compared with itself. This is the honest replacement for the total the page refuses.
  - **Contract-end runway** — notices whose published `date_end` falls in the next two years, by quarter, with the matched-to-provider count alongside. Needs a caveat of its own, and one was drafted: an end date is the period *as published at notice stage*, extensions in `extension_terms_text` are not applied, a framework's end is not a call-off's end, and none of it is a retendering forecast.
- Groundwork was written and reverted rather than half-landed: three query functions returning `by_quarter`, `value_bands` and `ending_soon`, plus the `contract_end` caveat. An API returning three keys no page reads and no test covers is how dead surface accumulates. Reconstructing it from this entry is an hour.
- Verified by: a test that the bands are fixed rather than data-derived, and a browser check that the runway chart carries its caveat.

**W-24 · The provider deep dive stops at four sources · M — closed in Phase 12**
- **Delivered:** the provider deep dive reads `cqc_location_reports`, `company_filings` and `v_provider_disclosure_gaps` (disclosure gaps) — verified present in `public_queries.py` and `pipeline/web/static/public/js/pages/providers.js` 2026-08-25. This entry's body was never updated after delivery; left below for the reasoning it recorded.
- Evidence **[live]**: `provider_timeline` reads charity financials, tribunals, NHS adverts and contracts. Sitting unread beside them: `cqc_location_reports` 580, `company_filings` 1,027, `provider_report_disclosure` 180 with the `v_provider_disclosure_gaps` view already built over it, and `charity_financials` reduced to one column on the list page.
- Costs today: the page is the closest thing this project has to a dossier on a campaign subject, and four of the sources collected about that subject are not on it.
- Fix, four sections, each single-source and each with its own caveat:
  - **CQC inspection history** from `cqc_location_reports` — report dates per location. A report date is an inspection published, not a rating change.
  - **Charity finance** — income against expenditure by year, plus `income_from_govt_contracts` and `income_from_govt_grants` as a share of `total_income`. That share is within one row of one source and is allowed; combining it with `contracts.value_core` is a cross-layer ratio and is not.
  - **Disclosure gaps** from `v_provider_disclosure_gaps` — a topic-by-year matrix of what an annual report does *not* discuss. The most campaign-relevant chart on this list and the easiest to overstate: "not matched" means the search terms did not appear in the extracted text, which is a statement about the PDF and the terms, not about the provider.
  - **Filing history** from `company_filings`, each linking to `document_url`.
- Verified by: a browser check per section, and a test that the disclosure matrix distinguishes "not matched" from "not searched".

**W-25 · 1,539 PFD reports are collected and invisible · M — closed in Phase 12**
- **Delivered:** `pipeline/web/static/public/js/pages/pfd.js` and the `pfd_reports`/`pfd_concern_terms`/`pfd_provider_mentions` queries in `public_queries.py` — verified present 2026-08-25. This entry's body was never updated after delivery; left below for the reasoning it recorded.
- Evidence **[live]**: `pfd_reports` 1,539, `pfd_concern_terms` 214, `pfd_provider_mentions` 57, `pfd_recipients` 5,788. `_public([...])` names none of them. Module 8 reads the PDFs and files the residue in `review_queue`; nothing downstream shows any of it.
- Costs today: coroners' Prevention of Future Deaths reports are among the most quotable evidence this pipeline holds, and the only way to read one is SQL.
- Fix: a sector-level section, plus the 57 mentions on the provider deep dive. Reports by year and by `coroner_area`; concern terms as a bar chart **labelled a finding aid** — a term means a word appears, not that the coroner found it ([docs/CAVEATS.md:165](docs/CAVEATS.md:165)). Three constraints that are not optional: being *sent* a report and being *named* in one are different facts and must never be summed into one series; roughly two thirds of reports (1,067 of 1,539) are metadata stubs with no `matters_of_concern`, which belongs on the chart and not in a footnote; and coroner areas are not local authorities and must not be mapped as if they were.
- `restricted_pfd_persons` and `restricted_pfd_report_text` stay out of every `_public([...])`. `guard_columns` will stop it; do not look for a way around it.
- Verified by: a test that the portal cannot reach either restricted table, and that sent and named are separate series in the payload.

**W-26 · The overview shows neither the funnel nor what is stale · S — closed in Phase 12**
- **Delivered:** `_evidence_funnel()` in `public_queries.py`, explicitly commented `# W-26: the overview's verification funnel` — verified present 2026-08-25. This entry's body was never updated after delivery; left below for the reasoning it recorded.
- Evidence **[live]**: 2,462 undecided candidates against 0 promotions was the finding behind U-03, and the public overview says nothing about it. Nor does anything show collection recency, though every table carries `retrieved_at`.
- Costs today: the portal's own coverage limits are the first thing a sceptical reader should be able to see, and they are the one thing it does not display. Publishing the funnel honestly is both an accurate coverage statement and the standing argument for working the queue.
- Fix: a candidate-to-evidence funnel (discovered → undecided → promoted → evidence rows) and a days-since-collection bar per source table, using the `ago()` helper the page already has.
- Verified by: a browser check that a zero-promotion funnel renders as zero rather than as an empty chart.

**W-27 · 477,199 budget lines sit behind one metric · M — closed in Phase 11**
- **Fix:** a budget drill-down section on the authority page — by `section`
  and `line_code` for the chosen financial year, from `la_revenue_budgets`
  directly. The payload carries exactly the published columns: the pin test
  asserts the row keys, so a derived number cannot slip in as a new key, and
  grant and budget stay separate payload keys that are never combined. An
  unreadable-denomination row keeps its NULL amount and its verbatim
  `value_text`. The section's caveat says what must not be computed here in
  the finding's own words.
- Evidence **[live]**: `la_revenue_budgets` holds 477,199 rows and the portal reads them only through `v_la_public_health_budget`, as one of the geography page's metrics.
- Costs today: the single largest table in the warehouse is reachable as one number per authority.
- Fix: a per-authority drill-down by `section` and `line_code` for a chosen ONS code and financial year. **No per-capita, no deflation, no ratio against grants or contracts** — [docs/CAVEATS.md:14](docs/CAVEATS.md:14) forbids cross-layer arithmetic and the grant/budget distinction is already one of the register's caveats. If a comparison looks irresistible, put the two figures side by side and let the reader make it explicitly.
- Verified by: a test that the drill-down endpoint computes no ratio, and that grant and budget figures are never returned as a single derived number.

**W-21 · Storage costs are invisible on the Health tab · S — closed in Phase 10**
- **Fix:** a storage panel over four directories — raw archive, backups, exports, logs — each with its file count, bytes, newest file and a sentence saying what it is and why it grows. The archive's sentence carries P-02's conclusion so the number and the reason not to delete it arrive together.
- **It is on its own route, and that is a correction the browser forced.** It went into the cheap half of the health query as the finding says; against the real archive that is **six seconds** — 8,502 files and 4.5 GB, stat-ed one at a time — so the whole Health tab sat waiting to render a size in megabytes, which is exactly the shape `health.freshness`'s docstring was written against. `/api/admin/storage`, loaded like freshness is, and a test now asserts `health()` does not carry it.
- The first measurement is itself a finding: the archive is **4.5 GB across 8,502 files**, against the 3.6 GB across 6,322 the audit measured on 2026-08-13, and `data/backups/` holds 1.4 GB in 9 files. The growth curve the roadmap said to watch is now visible on every visit rather than once an audit.
- Evidence **[at filing]**: the health cards reported warehouse size, page size and free bytes and nothing else ([pipeline/web/health.py:141](pipeline/web/health.py:141)); the raw archive, the backups directory and the exports output were measured nowhere in the UI. P-02's growth curve was measured once for the audit and was otherwise invisible.
- Costs today: the archive is the audit trail with a growth curve the roadmap itself says should be measured until it hurts — and the only instrument is a one-off audit. The operator gets no signal until a disk fills.
- Fix: a storage card — raw archive bytes, backup count and bytes, exports bytes — stat-ing the three directories in the cheap half of the health query, so the curve is visible on every visit rather than once an audit.
- Verified by: a test that the card's numbers equal a direct listing of the three directories.

### G. Operations

**O-01 · No CI · M — closed in Phase 6** — no `.github/`. 1,215 tests, 7 minutes **[measured]**, Windows-only development, a repo several sessions commit to concurrently.

**O-05 · The CodeQL check was red on every run for a reason that was not the code · S — filed and closed 2026-08-14**
- Evidence: every push and pull request from 2026-08-13 carried a failing
  `analyze`, including both phase PRs merged that afternoon. The repository had
  **both** CodeQL configurations enabled — `.github/workflows/codeql.yml` and
  the Settings "default setup" — and GitHub refuses an advanced
  configuration's results while default setup is on. The job ran the whole
  analysis and failed at the upload step, which is why the cause was only
  visible at the end of a log.
- Costs while it lasted: a check that is always red is a check nobody reads,
  and it was the one check reading the code for the class of defect the
  offline suite cannot reach.
- **Fix** (`#18`): default setup off, the workflow kept. Not
  interchangeable — default setup runs the `default` query suite and the
  workflow runs `security-extended`, which is where the request-forgery
  queries live. **S-01 was that shape**, and it shipped.
- The part worth keeping in mind: default setup was also scanning
  `javascript-typescript` and `actions`, and turning it off alone would have
  dropped both front ends and the workflows out of analysis *while the tick
  went green*. They are in the workflow's matrix now, so coverage went up —
  three languages on the extended suite rather than three on the default one.
  Vendored minified builds are excluded: a finding in ECharts is not this
  project's to fix or to dismiss.
- First green run found **21 alerts** (14 high, 7 medium) — SQL injection,
  path injection, response splitting, and workflow permissions. Several are
  the by-design ones the workflow's own header predicted.

**S-04 · Query parameters could add response headers · S — found by triaging
O-05, fixed 2026-08-15**
- The triage O-05 left open was done at 25 alerts (the PostgreSQL work added
  four more). **One of them was true**, and it was the class the header had
  predicted would be noise.
- `_export_name` interpolated the `provider_key` and `metric` query
  parameters into `Content-Disposition`, and
  `BaseHTTPRequestHandler.send_header` formats `"%s: %s\r\n"` while
  validating nothing. So
  `/api/v1/export?endpoint=summary&format=csv&provider_key=x%0d%0aX-Injected:%20yes`
  put `X-Injected` in the response. Confirmed over a raw socket before it was
  fixed, on a server that binds every interface by default and has no
  authentication.
- What it was worth: an attacker who can get a link clicked could set
  arbitrary headers on a response from this origin — undermining the CSP the
  rest of S-02 put there, and poisoning any cache in front of it.
- **Fix:** sanitise at the source (`_safe_name_part` reduces the value to what
  a filename may hold — a `"` or `;` breaks the header without any control
  character) and a backstop in `Handler.send_header` that strips CR and LF
  from every header this server sends and logs the attempt. Pinned by
  `tests/test_web_security_headers.py::TestResponseSplitting`, over a raw
  socket rather than through an HTTP client, because a client parses the
  response into a dict of headers and that is exactly the step that would
  make an injected header look ordinary.
- The other two workflow findings were real and cheap: `tests.yml` now
  declares `permissions: contents: read`, and both actions it uses are pinned
  to commits rather than to tags a third party can repoint.
- The remaining 22 are dismissed with reasons, in four groups. **Path
  injection** (`artefacts.resolve_for_download`, and the two call sites that
  use its result): the requested path is not sanitised but *matched* against
  a listing computed on the spot, then re-checked with `is_relative_to` after
  resolution — CodeQL does not model set membership as a sanitiser. **SQL
  injection**: `catalog.py` and `queries.py` interpolate object names that
  were validated against the live catalog first and are quoted with doubled
  quotes; `pg.py:160` and `queries.py:226` are the generic execute wrappers
  every query passes through, and the SQL box behind the second one is a
  documented feature defended by the read-only role rather than by inspecting
  the SQL. **Incomplete URL sanitisation**: six assertions in tests, checking
  which URL a module fetched — not a sanitiser, and not reachable. **Bad tag
  filter**: `_INLINE_SCRIPT_RE` extracts inline scripts from *our own* static
  pages to compute CSP hashes; it is not filtering hostile HTML, and a tag it
  fails to match produces a policy that blocks the script rather than one
  that admits it — it fails closed, and a test asserts the count it finds.
- The rule this leaves behind: a dismissal carries its reason, and the reason
  has to be checkable. Each of the four above names the mechanism that makes
  the alert wrong, not the fact that it looked wrong.

**O-02 · No backup or restore · M — closed in Phase 3** — nothing in `pipeline/` performs a backup (no `VACUUM INTO`, no dump helper). 242.7 MB warehouse plus 3.6 GB archive **[live]**, rebuilt only by re-crawling at one request per two seconds per host.

**O-03 · Logs never rotate, and tests write into the real `logs/` · S — closed in Phase 10** (tests stopped writing there in Phase 2; rotation landed here)
- **Fix:** `RotatingFileHandler` at 10 MB per generation, five kept, both settings (`LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`) rather than constants — discarding a generation is a deletion, and an operator who wants a longer operational record should not have to edit the logging module to get one. By size, not by day: these logs are written in bursts, so a daily roll produces a directory of empty files and still lets one four-hour crawl write without limit.
- The trade is written into the docstring rather than left implied. The provenance a figure rests on is in the warehouse and in `data/raw/`; this file is the operational record of what ran. Losing the oldest of it costs the ability to reconstruct a months-old run and costs nothing a published figure depends on.
- `delay=True` came out of the same pass: several commands configure logging as a matter of course, and each was creating an empty file named after a module that never ran.
- Evidence **[at filing]**: no rotation in [pipeline/logging_conf.py](pipeline/logging_conf.py); `logs/` was 7.2 MB **[live]** of which `fake_insert_only_for_tests.log` was 5.0 MB, alongside `bogus_module.log` and `fake_writer_for_tests.log`.

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
- **Partially delivered, narrower than filed, 2026-08-26 (BETA-022):** `/api/v1/document_search` searches the *document-analysis* corpus (committee papers, CDP documents — page-level extracted text, not structured rows), not "corpus-wide" in this entry's full sense. Structured tables (contracts, PFD, FOI, NDTMS) still have no full-text search of their own — each already has filtering by its own dimensions (buyer, provider, date, area) on its page, which is a different and narrower tool. This entry stays open for that structured-table half; only the document-text half is done.

**Versioned datasets, ONS-style · L — F-05 with a delivery shape — decided in Phase 14: no**
- What: ONS publishes editions and versions of each dataset; a re-run that changes rows is a new version, with the previous one still citable ([developer.ons.gov.uk](https://developer.ons.gov.uk/)). Under this shape, "the 2026-08 version of the contracts table" would be a real thing to link.
- Why it is here rather than in the register: every domain table upserts on a natural key, so nothing can be cited as a version today. F-05's decision stands and the recommendation is unchanged: not yet, and as history on one table only if one specific claim needs it.
- **Phase 14 decided it, as its plan said it would ("here or not at all"):** no versions. The claim that would justify them — advertised bands over time — has not been made. A refusal that is written down cannot be re-litigated by default; this entry stays filed so the delivery shape is remembered if the claim arrives.

**Matrix ("tartan rug") views · M — decided in Phase 13: deferred**
- What: Fingertips' Overview view — authorities × periods as a colour-coded matrix, one glance at the whole distribution (Fingertips calls it a tartan rug).
- Why it is here rather than in the register: it overlaps W-11 (compare view) — the matrix is the same comparison without the axes, and whichever is built first shapes the other. Filed so the shape is remembered rather than re-invented. ECharts heatmap, no new dependency.
- **Phase 13 settled it:** W-11 shipped first, so per the entry's own rule it shapes the matrix — and the matrix's cell colouring is the same inference surface as significance-aware colouring, which Phase 13 declined. The matrix is now buildable as a rendering of the compare payload; it is re-filed here rather than in the register, behind a named claim that needs it.

**Trend markers in tables · S**
- What: ▲▼ "direction of travel" per row against the previous period, as Fingertips' England view shows.
- Why it is here rather than in the register: every row-level change marker invites the differencing `docs/CAVEATS.md` forbids for the census, and the marker must know per row which layers it may appear on. The rule exists; a marker needs it encoded, and which layers carry it and what the caveat next to it says is a decision to settle before the button is. Filed so that decision is remembered.

**API rate cap · S — DELIVERED 2026-08-25 (`pipeline/web/ratelimit.py`)**
- What: a per-IP token bucket on the `/api/v1/*` read routes — a 429 with `Retry-After` rather than silence.
- Why it is here rather than in the register: it is small, and its answer depends on a standing decision — the bind address is the control, and a cap only earns its place once the portal is reachable by readers the operator does not trust, which is the same exposure the README's security section already governs. Filed so the limit exists when the exposure does. Every public data API answers overload with a limit.
- **Delivered:** production confirmed live on Railway (a public host) settled the standing decision this entry was waiting on. Implemented exactly as specified — a `TokenBucketLimiter`, `/api/v1/*` only, `429` + `Retry-After`, generous defaults (120/min, burst 40) so ordinary interactive use never sees it. See `beta.md`'s BETA-007.

**Table-browser CSV · S**
- What: a "download current view" on the admin table browser, alongside the SQL box's existing CSV.
- Why it is here rather than in the register: the browser is a paging window, not a dataset — the honest export path is the export layer, and W-06's completeness fix covers the public half of it; a browser CSV would be a third, smaller route into the same rows. Filed so the gap is remembered rather than solved twice.

**Post-run verification pass · M**
- What: after each module, run FK integrity, a no-row-without-provenance sweep and module-declared row-count floors, recording the results in the run summary.
- Why it is here rather than in the register: the floors are a contract with each of seventeen modules — declaring and maintaining them is a design, not a button — and the integration suite already sweeps provenance once. Filed because D-02 showed the cost of a run whose record cannot be trusted.

**Significance-aware colouring · M — decided in Phase 13: declined**
- What: colour treatment figures by whether an authority's paired CI overlaps the England value, as Fingertips' red-amber-green-vs-benchmark does throughout.
- Why it is here rather than in the register: the warehouse already holds the CIs, so the work is implementation — but the colour *is* an inference, and `docs/CAVEATS.md` decides which inferences this project makes. The 2026 default for health data, and the decision it needs, filed together.
- **Phase 13 declined it.** The register already states the counter-case in its own words: "two authorities whose intervals overlap have not been shown to differ". Colouring by overlap would be that sentence inverted — a claim of *shown to differ* — drawn over every figure without a decision. Nothing in Phase 13 colours by significance, and nothing built on its payloads is allowed to either. The entry stays here, filed as declined rather than deleted, so the inference is not re-adopted by default.

**Peer-group benchmarking · M — decided in Phase 13: deferred**
- What: LG Inform-style nearest-neighbour groups — "how does my authority compare with its peers".
- Why it is here rather than in the register: comparability is a claim. Which authorities are comparable — type, region, deprivation? — is a method decision, and a group implies a fairness the caveats have not asserted. Filed so the idea is remembered rather than adopted by default.
- **Phase 13 deferred it.** W-11 is deliberately the opposite shape: the reader picks the peers, one at a time, and the project never asserts that any set of authorities is a group. The compare view is the honest replacement for a peer group; this entry is re-filed here, behind a named claim that needs a group.

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

Small, safe, independently shippable, no dependencies. The **Phase** column is
where each open one now sits — a quick win is still a quick win, but W-17
lands on a page that does not exist yet and W-06 extends a header W-10 has not
given a licence line to, so "no dependencies" was true of the finding and is
not quite true of the work.

| ID | What | Why now | Phase |
|---|---|---|---|
| D-02 | Log run parameters and stamp dry runs | Makes F-02 diagnosable instead of mysterious | *done, 1* |
| D-01 | Apply `0028` to the working warehouse | One command; the drift is live | *done, 1* |
| P-04 | `timeout` on the handler | One class attribute | *done, 2* |
| S-02 | CSP, `X-Frame-Options`, `Referrer-Policy` | Three headers next to the one already there | *done, 2* |
| W-01 | `<noscript>` on the portal | A few lines, and it is a public site | *done, 2* |
| O-03 | Point test logging at a temp dir | Stops tests writing 5 MB into `logs/` | *half done, 2* — rotation in **10** |
| S-03 | Bring the README's warning up to date | Text only, and it is currently understated | *done, 2* |
| W-05 | Wire or remove the Region filter | A visible control that does nothing is the one failure the portal's honesty rules do not cover | *done, 9* |
| W-06 | Make contract exports complete | The table now says "1,000 of 98,636" (W-18) and its CSV still ships 500 | **10** — after W-10's header, which has landed |
| W-07 | NDTMS download path | One section whose data cannot leave the server | *done, 2026-08-14* |
| W-10 | Licence lines in exports and footer | Reuse, and defending reuse, start with the licence | *done, 9* |
| W-15 | Link providers to their registers | The cheapest verification affordance is a link | *done, 9* — CQC still open |
| W-16 | Zip bundle of exports | "Download the evidence" is nine CSVs and nine JSONs by hand today | **10** — after W-06 |
| W-17 | "Find my council" typeahead | A reader who knows their town, not their ONS code, has no entry point | *done, 11* |
| W-18 | Search and page the public tables | Tabulator ships it; the portal configures none of it | *done, 9* |
| W-20 | Stale-exports warning on the Exports tab | A state that looks fine and isn't — the D-02 shape, for artefacts | **10** |
| W-21 | Storage card on the Health tab | The only instrument for P-02's growth curve is a one-off audit | **10** |

## 5. Phases

Phases 1–7 are done and each records what changed from its plan as it landed —
read them for the shape a phase entry takes, and for the four defects CI found
in code that had passed on the machine it was written on. **Phases 8–15 follow
them in the same shape**; 14 is the standing gated pair, and 16–19 are a plan,
and the reasons for their order matter more than their contents. All of
16-19 have now landed (16 and 18 on 2026-08-15, 19 on 2026-08-16); 17
remains gated on campaign throughput.

Each delivered phase is tagged at the commit that completed it — `phase-1`
through `phase-7`, annotated with what it delivered and what it found on the
way. `git describe` therefore names the phase any commit belongs to, and
`git log phase-2..phase-3` is the phase's actual diff. The tags carry the real
commit dates, which is why they exist and why the delivered phases were not
backfilled as closed issues: a closed issue would date this history to the
afternoon somebody wrote it down.

### Phase 1 — Make a run's outcome unambiguous · S — **done** (`7f457fd`, `3ceb4db`)

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
  *Superseded in part on 2026-08-14 (U-03): the UI now batches the clicking.
  It still calls the single-URL route once per candidate, and only for
  candidates it watched the operator open, so `promote_many` still does not
  exist and the test still holds. What changed is that the screen stopped
  being unusable enough that nothing was ever promoted through it.*

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

---

### Phases 8–19 — the plan for what is left · 8–16 and 18 done, 17 and 19 planned

Twenty-one open portal and operator findings (W-05 – W-27), three standing
decisions (F-03, F-05, P-03) — the last two decided on 2026-08-16, Phase 14
(F-05: *not yet*; P-03: refused, `--jobs 1` stays the default) — the
half-closed O-03, and four workstreams —
sequenced. Phases 8–13 are delivered (F-03, the shared furniture, the
artefacts, the authority spine, what-is-collected, and the compare view and
map layers); Phase 15 delivered the first workstream tranche; this
section is the order to begin the rest in and the reasons for it, so that the
next session picks up a plan rather than a list.

#### The ordering principle

**Build the shared thing before the things that use it.** Every open portal
finding lands on one of four pieces of shared machinery:

| Shared thing | Where | Who is waiting on it |
|---|---|---|
| `table()` — no search, no pager, no row count | [components.js:183](pipeline/web/static/public/js/components.js:183) | W-18, and every table in W-23–W-27 |
| `mountChart()` — no image export, no caption in the download | [components.js:146](pipeline/web/static/public/js/components.js:146) | W-08, and every chart in W-11, W-19, W-23–W-26 |
| The CSV header — no licence line, no row count | [public_export.py:86](pipeline/web/public_export.py:86) | W-06, W-10, W-16 |
| The two frozen lists — public routes and public static paths | [tests/test_portal_isolation.py:110](tests/test_portal_isolation.py:110), [:127](tests/test_portal_isolation.py:127) | every new page or endpoint, one edit each |

Five new portal sections and one new route are planned. Build the machinery
first and each of them inherits search, paging, image export and a licence
line for nothing. Build it second and the same retrofit is paid five times,
in five files, by whoever notices the inconsistency last. That is the whole
argument for the order below, and it is the one thing in this plan not to
rearrange.

The frozen lists are the second reason to batch. A new route costs a line in
`test_the_public_api_routes_have_not_changed` and a new page costs one in
`test_the_set_of_public_static_paths_has_not_changed` — trivial individually,
but they are the file that says what the portal *is*, and five sessions each
appending one line to it is five chances to append the wrong one. New surface
is introduced in two phases (11 and 12) rather than in seven.

#### Three orderings that are not preference

1. **F-03's mechanism before everything.** Everything downstream of it is a
   person's labour, and labour that could have started is the only cost a
   phase plan can waste outright. It is Phase 8 because it is the gate, not
   because it is large or urgent. *Delivered 2026-08-14; the gate is open and
   the labour is now the only thing between here and a verified census.*
2. **W-13 (an authority page) before W-14 and W-17.** Both are entry points
   to a page that does not exist. Built first, each needs a temporary
   destination and then rework when the real one lands.
3. **Phase 9's furniture before Phases 11 and 12's sections.** As above.
   *Delivered 2026-08-14. Both sections now inherit the table search, pager
   and row count, the chart image export, the licence line and the register
   links rather than each building or skipping them.*

#### Three that are judgement, and are the recommendations here

- **The verification campaign runs alongside the code phases, not after
  them.** Workstream A is labour gated on open question 1, not on effort. The
  §8 thesis — that the ceiling is the number of verified, cited rows, today
  zero, and that the portal is secondary — is right, and the conclusion drawn
  from it here is *not* "stop building the portal". It is that the campaign
  starts the day Phase 8 lands and continues through Phases 9–14, because a
  person deciding rows and a session writing JavaScript are not competing for
  the same hours. What the campaign must not do is wait for the portal.
  **Both halves of that happened on 2026-08-14**: Phase 8 landed the census
  mechanism and Phase 9 landed the portal furniture, in parallel. The campaign
  is now waiting on people rather than on either. *Phase 14 has since closed
  the span — 2026-08-16 — and its two decisions (F-05 *not yet*, P-03 refused)
  are recorded there rather than in this judgement.*
- **D-04's remaining 3,160 items are not queue work — they are F1's input.**
  `unmatched_buyer_name` (2,667) and `possible_group_company` (493) are, item
  by item, the same reconciliation the sector universe does systematically
  once ([§8, F1](docs/upgrade-roadmap.md)). Grinding them one at a time in the
  review UI is that work done in its most expensive possible form, and it
  produces no universe at the end. Deferred into Phase 18 deliberately, and
  the queue count stays high in the meantime; that is the correct reading of
  it, not a backlog. *Delivered 2026-08-15: the universe build (m23) captures
  every one of them systematically as unresolved leads. It does not answer
  the identity question, and the items remain visible for review — see Phase
  18.*
- **B4 (full council-website coverage) comes after the campaign shows
  throughput, not before.** It multiplies candidate discovery from a verified
  handful to 347 councils. With 2,462 undecided candidates against zero
  promotions, widening discovery first makes the bottleneck worse and calls it
  progress. Once the campaign is demonstrably clearing rows, the same change
  is the highest-value collection work in the plan.

#### The sequence

| Phase | Delivers | Effort | Gate |
|---|---|---|---|
| ~~**8**~~ | F-03 — census verification, and the campaign starts | M | **done** |
| ~~**9**~~ | W-05, W-18, W-08, W-10, W-15 — the shared furniture | S–M | **done** |
| ~~**10**~~ | W-06, W-16, W-09, W-20, W-21, O-03 — artefacts and the machine | S–M | **done** |
| ~~**11**~~ | W-13, W-12, W-27, W-17, W-14 — the authority spine | M–L | **done** |
| ~~**12**~~ | W-23, W-26, W-25, W-24 — show what is already collected | M–L | **done** |
| **13** | W-11, W-19 — comparison, and the inferences it forces | M | three §3J decisions |
| ~~**14**~~ | P-03, F-05 — gated by runs and decisions, not by effort | M | **done 2026-08-16 — both refused, decisions recorded** |
| ~~**15**~~ | G7, B2, G3, G4, G6 — the cheap sources that feed the rest | S–M | **done** |
| **16** | B3, G1, B1 — direct pay evidence and its comparators | M–L | none |
| ~~**17**~~ | C1, C2 — the claims-to-evidence index | M | **done 2026-08-17 — the campaign's throughput met the gate (1,575 promotions, 68 verified census metrics)** |
| ~~**18**~~ | F1, F2, F3, and D-04's remainder — the sector universe | L | **done 2026-08-15** |
| **19** | B4, G5, G2, G8 — heavy, conditional, or gated on B4 | M–L | Phase 18 |

Phases 8 and 9 were both delivered on 2026-08-14, by two sessions running at
the same time, which this paragraph had said they could be. It cost one
conflict, in this file, where each phase wrote its own record into the same
register — and nothing else: the two touched `public_queries.py` and
`README.md` in different places and both auto-merged. That is the shape the
warning below is about, and it was cheap.

Phase 10 was independent of both and was taken in a session that was not the
one doing the campaign; it landed the same day. Phase 11 — the authority
spine — was taken on 2026-08-15 and delivered W-13, W-12, W-27, W-17 and
W-14; its one frozen-route-list edit and one frozen-static-path edit were
exactly the two the plan priced. Phase 12 depended on 9 and on nothing else,
so it is unblocked and can be taken in either order with 13 or in parallel by
two sessions — with the caveat that both edit the frozen route list, and
concurrent sessions have collided on this file before. Phase 10 added two
entries to it (`/api`, `/api.html`) and one to `PUBLIC_API_EXTRA`; Phase 11
added one pattern (`authorities/([A-Z][0-9]{8})`) and one static path
(`/js/pages/authority.js`), so a session starting 12 or 13 should read that
file before appending to it.

---

### Phase 8 — Unblock the verification campaign · M — **done** (2026-08-14)

Delivered **F-03**. The only phase that gates a person rather than a session.
Suite green: 1476 passed, 2 skipped, 18 deselected.

**What changed from the plan.** The design question the phase opened with was
posed as a choice between "a fourth `KINDS` entry with the fetch made
conditional" and "a sibling table with its own trigger". It went the second
way, and the reason is stronger than the framing allowed for: the two acts are
not the same act with an optional fetch. A promotion *creates* an evidence row
in a second table; a census verification raises a flag on a row that already
exists. There is no candidate, no target and no `<authority>|<url>` key — a
census metric is identified by four columns, one of them a whole verbatim line
of PDF prose. Fitting that into `evidence_promotions` would have meant a
`candidate_url` holding something that is not a URL and four fetch-provenance
columns permanently `NULL`. The argument is written into
`0033_census_verifications.sql`, at the point somebody would go looking.

**Two triggers, not one.** The plan said "the trigger discipline of `0030`
extends to whatever this writes", and `0030`'s triggers all fire `BEFORE
INSERT` on a target table. That shape does not transfer: the flag is normally
raised by an `UPDATE`. So there is a `BEFORE UPDATE OF verified` with the
`OLD`/`NEW` pair in its `WHEN` (re-writing an already-verified row is not a new
decision and must not need a second one), *and* a `BEFORE INSERT`, because a
rule enforced on one route is not enforced.

**The screen turned out to be the design.** The phase brief said the mechanism
records "who verified, when, against what, and on what note", and *against
what* is where the work was. The markdown worklist could pair a value with the
line it was parsed from; only the page around that line says whether the line
meant what the parser took it to mean. `workforce_census_page_text` has held
every page m06 read since m06 was written and nothing had ever queried it. So
the Census tab serves the page, and a figure becomes verifiable once its page
has been expanded in that session — the census analogue of the Candidates tab
requiring the document to be opened. One page carries several figures and is
read once, which is why the worklist is ordered by page and why the batch
verifies per figure off a page read once.

**Three things the phase found on the way and did not leave alone:**

- **The portal had a hole this work would have opened.** `census_all_unverified`
  drove a pinned caveat reading "every figure below is unverified", and it goes
  false the moment one figure is checked — which would have left the other 67
  charted with nothing said about them. There is now a third state:
  `census_verified_count` of `census_total`, pinned until none is outstanding.
  A portal edit inside an otherwise admin-side phase, done deliberately rather
  than deferred: shipping the mechanism without it would have been shipping a
  known regression.
- **A verification can go stale, and silently.** It records the value, unit and
  the report's SHA-256, so `census_verify.stale()` catches both ways it
  happens — a parser revision reading a different number off the same line
  (`raw_text` is in the key and the value is not, so that updates in place), and
  the publisher reissuing the PDF at the same URL. Listed at the top of the tab,
  not in a query nobody runs.
- **`preserve=DECISION_COLUMNS` had been protecting one column out of three.**
  `db.DECISION_COLUMNS` names `verified`, `verified_at` and `rejected`;
  `workforce_census_metrics` had only the first. `0033` adds the other two, so
  the re-run protection m06 already asked for now actually covers what it
  names.

**Also delivered:** rejecting a figure files a `parse_failures` row as well as
a decision, so a bad parse is findable from the parser's side rather than only
from the figure's; and `source_page` is documented as the zero-based index it
has always been, said out loud in the UI rather than quietly incremented for
display, which would have made the screen disagree with the database, the
exports and the portal.

**The markdown worklist is gone, not supplemented.** `m06` no longer writes
`docs/verification/census_{year}_tables.md` and the three generated files are
deleted; `docs/verification/census_metrics.md` replaces them with a pointer and
the reason. Leaving them would have left a documented instruction — the bulk
`UPDATE` — that the database now aborts.

Below is the plan as written.

---

**Why this first, and alone.** The promotion path exists and now gets used
(F-01, U-03); the census does not have one. 68 metrics sit at `verified = 0`
and the portal correctly shows them as unverified, which it will keep doing
for as long as there is no mechanism — not for want of a decision about any
individual metric, but for want of anywhere to record the decision. Everything
that follows in the campaign is somebody's afternoon, and afternoons cannot be
scheduled behind a phase that has not been written.

**The design question, stated rather than solved.** Promotion as built fetches
the document and stores the hash of the bytes it retrieved — that is what
makes an evidence row a claim about something that was read. The census has no
URL per row: its provenance is the publication the 68 metrics were parsed
from, already recorded. So census verification cannot reuse `promote.py`'s
fetch, and must not pretend to: the mechanism records **who verified, when,
against what, and on what note**, and stores no payload hash of its own,
because none was retrieved. Whether that is a fourth `KINDS` entry with the
fetch made conditional, or a sibling table with its own trigger, is the
decision Phase 8 opens with. Phase 4 deferred this rather than bodging a
fourth entry into `KINDS`; the deferral was right and the design is still
owed.

- **Not optional:** the trigger discipline of migration `0030` extends to
  whatever this writes. A verified census metric without a recorded decision
  must be refused by the database, not by `promote.py`.
- **Also not optional:** the caveat forbidding cross-year differencing of
  census metrics ([docs/CAVEATS.md:25](docs/CAVEATS.md:25)) survives
  verification. Verified means checked against its source, not comparable
  with the year before.
- **Verified by:** a test that a census metric cannot reach `verified = 1`
  without a decision row; a test that the mechanism records no payload hash
  where nothing was fetched; and the markdown worklist replaced by, not
  supplemented with, the UI path.

**Deliberately not in this phase:** the labour itself, and D-04's 3,160
unmatched-name items (Phase 18).

**And then the campaign starts.** Workstream A is not a phase — it is
open question 1 answered, and then people deciding rows, through the
Candidates tab U-03 made usable. It runs from here to the end of the plan.

### Phase 9 — The shared portal furniture · S–M — **done** (2026-08-14)

Delivered **W-05**, **W-18**, **W-08**, **W-10** and **W-15**, in that order.
On its own branch: 1,433 → **1,475 passed** (42 new), 2 skipped, 18 deselected;
ruff clean; all six portal routes plus a provider deep dive loaded in a browser
against Jon's own warehouse with no console errors. Merged with Phase 8, which
ran in parallel the same day, the tree is at **1,518 passed**, 2 skipped, 18
deselected — measured on the merge, which is where the two suites meet for the
first time.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

Five findings across three shared files, and every phase after this one is
cheaper for it.

**Why these together:** they are all edits to
[components.js](pipeline/web/static/public/js/components.js),
[app.js](pipeline/web/static/public/app.js) and
[public_export.py](pipeline/web/public_export.py) — and every one of them is a
thing five future sections would otherwise each implement, or each go
without. Neither Tabulator's `headerFilter`/pagination nor ECharts'
`getDataURL` is called anywhere in the portal's own code today, though both
libraries are vendored and paid for.

Order within the phase, because it is not arbitrary:

1. **W-05 first, because it is a deletion.** The Region control writes
   `state.region` and no page reads it. Recommendation stands: remove the
   control rather than invent a use for it, and land the test that every
   filter control the portal renders is read by at least one page — *before*
   Phases 11–13 add controls to it.
2. **W-18 — `table()` gains per-column search, a pager and a visible row
   count.** The count is the honest half: "1,000 of 98,636" said out loud
   rather than implied by a table that simply stops.
3. **W-08 — `mountChart()` gains an image export** with the caption and the
   pinned caveat rendered *into* the PNG. A chart whose caveat is a DOM
   sibling loses it the moment the image is saved, which is the exact failure
   [README.md:381](README.md:381) is written against.
4. **W-10 — the licence, in both places at once.** One lookup from source to
   licence (most are OGL v3, recorded in `docs/SOURCES.md`), consumed by the
   `provenance()` drawer and by a `# Licence:` line in `to_csv`. Doing it as
   one job is the reason it is here and not in Phase 10 with the rest of the
   export work: two consumers, one table, one commit.
5. **W-15 — a register-link helper**, used by the providers page now and by
   W-13 and W-24 later. `company_number` → Companies House, `charity_number`
   → Charity Commission, CQC location → its profile, each labelled *verify at
   source* so it reads as an offer rather than a claim.

- **Verified by:** the dead-control test above; a test that a table larger
  than one page renders a pager and that search narrows the rows; a test that
  every export header carries a licence line; a test that register links are
  built from the registers' documented URL shapes. And a browser pass — a
  vendored library that has stopped working is invisible to all four of those.

**Deliberately not in this phase:** any new route, page or endpoint. This
phase must not touch the frozen lists at all, which is what makes it safe to
run concurrently with Phase 8 or 10. It was run concurrently with Phase 8, and
that held: the two phases conflicted on this file and nowhere else.

#### What changed as it landed

The plan held. Five things it did not anticipate:

- **The dead-control test needed the page to declare the chain, not the test
  to guess it.** Each control now carries `data-filter="<state key>"`, and
  `Reset` clears the controls by walking that attribute — so the attribute is
  load-bearing rather than decoration for a test, and a wrong key breaks reset
  in the browser as well as failing in CI. The first draft of the test looked
  for `.region` anywhere in the page modules and **would have passed on the
  very control it was written for**: geography.js carries an authority's
  `region` in a map tooltip, which has nothing to do with the filter. A reader
  now counts only if it goes through `getState()`.
  Removing the control also removed a request: `/api/v1/authorities` was
  fetched on every page load solely to fill the region `<select>`.
- **W-18's behavioural half is a browser check by decision, not by omission.**
  "A pager appears past one page, a search narrows the rows" cannot be
  asserted from Python without a JavaScript runtime in the suite, which §3J
  files as a trade to make deliberately rather than as a side effect of a
  table fix. `tests/test_portal_tables.py` pins the configuration in the one
  function every table goes through; the behaviour was checked in the browser
  — 14 rows of 1,000, a Buyer search narrowing to 4, the counter following.
  The count reads **"1,000 of 98,636 rows"** in amber on the contracts page,
  and the section is no longer called "Every notice", because it never was.
- **W-08 found an ARIA bug that only the browser could show.** `role="img"`
  sat on the chart wrapper; putting a save button inside it made a button no
  screen reader announces, because an `img` role's children are
  presentational. The role moved onto the chart element and the button is its
  sibling. The caption and caveat are read from the DOM around the chart
  rather than passed in per call site, so whatever the reader can see beside
  the figure is what lands in the file and the two cannot drift.
- **W-10 is one table and one mirror, not two tables.** `pipeline/licences.py`
  is read directly by the export layer; `components.js` holds a copy because
  the drawer is drawn client-side from the module id the page already knows
  and this phase added no route to fetch it over. `tests/test_licences.py`
  compares them **word for word** and fails in either direction — which it
  did, immediately: the OS rider on the geography licence was an attribution
  requirement in Python and a caution in the JS. The attribution wording is
  now rendered in the drawer to be copied rather than summarised.
  The table is keyed per module because a licence is a property of the source;
  an endpoint names every licence its rows can be under, deduplicated, because
  guessing the one that applies to a particular row would need per-row
  attribution the payloads do not carry — and over-inclusion errs strict.
- **W-15 shipped two registers of three, and the missing one is the finding's
  own rule applied to itself.** Companies House and the Charity Commission
  were verified against the live registers with real identifiers from this
  warehouse on 2026-08-14 — `03861209` resolves to CHANGE, GROW, LIVE, and
  `1079327` and `234887` each return exactly one match. The charity link is
  the register's *search* on the registered number, not the charity-details
  page: that page is keyed by an internal organisation number this pipeline
  does not store, and building a details URL from the charity number would
  produce a link that looks right and is not.
  **CQC is not linked.** Its public API publishes no profile URL — 520
  archived payloads contain no `cqc.org.uk` address at all — and the
  conventional shape could not be verified without working around a bot block,
  which this project does not do. A test asserts no CQC URL is built, so the
  absence is a decision rather than an oversight. What would settle it: one
  manual check of `www.cqc.org.uk/location/{location_id}` against a real
  location id, or `report_uri` (already stored, e.g.
  `/reports/{guid}?{stamp}`) gaining a documented host.
  The first browser pass also showed the same company number twice under a
  provider's name: it arrives as both a `company_number` identifier and a
  `company` edge from Companies House. Deduplication moved onto the resolved
  register URL, which is the thing that is actually the same.

### Phase 10 — The artefacts and the machine tell the truth · S–M — **done** (2026-08-14)

Delivered **W-06**, **W-16**, **W-09**, **W-20**, **W-21** and **O-03**, in
that order. 1,518 → **1,557 passed** (39 new), 3 skipped, 18 deselected; ruff
clean; the portal, the API page, the Exports tab and the Health tab all loaded
in a browser against Jon's own warehouse with no console errors.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

**Why these together:** every one is about a promise something on disk or on
a route makes and does not keep. W-06's export ships 500 rows of 98,636 and
says nothing; W-16's bundle does not exist so "the evidence" is nine files
clicked by hand; W-09's API is documented only in a `<noscript>` block most
readers never see; W-20's exports can predate the run that changed the
warehouse; W-21's growth curve has a one-off audit for an instrument; O-03's
logs never rotate. They also share their tests — the export header, the
manifest and the route list are three pins on the same contract.

- **W-06 is the one that must not be got wrong.** A complete download with the
  row count in the `#` header line, streaming rather than a raised cap
  wherever the shape allows. The count travels *in* the provenance line, not
  beside it. This is the same header W-10 just gave a licence line to, which
  is why W-06 follows it rather than leading.
- **W-16 after W-06**, because a bundle of truncated files is a worse artefact
  than a truncated file. Manifest, `.provenance.json` companions, a README
  naming the contents, offered from the admin Exports tab; whether the public
  portal serves it is a decision to take in the phase and record here.
- **W-09 last of the three**, because a docs page is a promise about routes and
  export behaviour, and it should be written once both have stopped moving.
  Pinned against the same frozen route list `test_portal_isolation.py` uses —
  a published endpoint list that is wrong is worse than none, which Phase 2
  already learned once with the `<noscript>` block.
- **W-20 and W-21 are the operator's half** and are independent of the three
  above: a staleness line per export directory read from `job_runs` and
  `module_cursors`, and a storage card stat-ing the raw archive, the backups
  and the exports directories in the cheap half of the health query.
- **O-03 closes a half-open finding** — rotation on `pipeline/logging_conf.py`.
  Tests stopped writing into `logs/` in Phase 2; nothing has ever pruned it.

- **Verified by:** a full export of a corpus larger than 500 rows containing
  every row and naming the count; the zip containing every file its manifest
  names and no file it does not; the route-list pin; a fresh export reporting
  current and an older one naming its predecessor; the storage card's numbers
  equalling a direct listing of the three directories.

#### What changed as it landed

The order held and every "verified by" above is a test. Five things the plan
did not anticipate, three of which only the browser could have shown:

- **W-06's real fix is a refusal, not a stream.** Streaming was the easy half.
  The finding was caused by a caller flattening a page's payload into a file,
  so `to_csv` now *raises* for any endpoint in `public_export.WINDOWED` and the
  export goes through a query of its own. `stream_csv` also refuses to finish
  when the rows it wrote disagree with the count in the header it already
  sent: the response then ends without its chunked terminator and every client
  reports a failed download. A broken download is recoverable; a
  complete-looking file with the wrong rows in it is not. Measured on the real
  corpus: 64.4 MB, 98,636 rows, and a filtered export of 45,999 against an API
  `total` of 45,999.
- **W-09's pin caught the thing W-09 is about, immediately.** The finding says
  a published endpoint list that is wrong is worse than none. The
  `<noscript>` block — the only description of the API a reader with
  JavaScript off ever saw — had not gained `/api/v1/ndtms` when that endpoint
  shipped the week before. The test that compares both published lists against
  the dispatcher's own routes failed on its first run, on the list that already
  existed.
- **W-20's first version was correct and useless.** Comparing the export files
  against the mtime of `warehouse.db` can only err towards stale, which is the
  safe direction — and the server writes to the warehouse as it starts, so
  every directory read "stale" a second after the page was opened. That is a
  warning nobody would read twice. It now compares against the pipeline's own
  activity record: the conditional-request cache (which catches a command-line
  run, the case `job_runs` misses), the module cursors, and the job history.
- **W-21 belongs on its own route, and the finding said otherwise.** "The
  cheap half of the health query" is where it went; on the real archive that
  is six seconds of stat calls over 8,502 files, so the Health tab sat waiting
  to render a size in megabytes — the exact shape `health.freshness` exists to
  avoid. A test now asserts `health()` does not carry it.
- **W-16 found that nothing had ever checked the pairing.** The export writers
  pair each file with its `.provenance.json` at write time and nothing looked
  afterwards. The manifest names the companion for each file and names any file
  that has none, which is the difference between a bundle and a zip. **The
  public portal does not serve the bundle** — the decision this phase was asked
  to take and record: the portal's surface is a frozen list of routes, and a
  zip of a directory publishes whatever is in that directory. Public readers
  get complete per-endpoint CSVs, which is what W-06 was for.

One thing found in passing and fixed: `.noscript ul` used `var(--space-5)`,
which does not exist, so an undefined custom property made the declaration
invalid and that list had no indent at all.

### Phase 11 — The authority spine · M–L — **done** (2026-08-15)

Delivered **W-13**, **W-12**, **W-27**, **W-17** and **W-14**, in that order.
1,557 → **1,568 passed** (11 new), 3 skipped, 18 deselected; ruff clean; the
authority page, the find-council search and the map click all loaded in a
browser against Jon's own warehouse with no console errors.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

**Why these together:** they are one page and its four feeders. "What does my
authority get?" is the campaign's own question and the portal has no surface
that answers it — while `/api/v1/contracts` has accepted `buyer_ons_code`
since it was written and no control anywhere sets it. Four of the five
findings here are cheap *given* an authority page and are rework without one.

Order within the phase:

1. **W-13 — the route, the endpoint and the page**, in the provider deep-dive
   shape: grant allocation, budgeted spend, treatment estimates with their
   paired CIs, contracts let. No new data; one frozen-route-list edit and one
   frozen-static-path edit, made once for the whole phase.
2. **W-12 — coverage ticks on it**, reusing the admin health tab's counts, so
   a reader can tell absence of evidence from absence of collection. Carries
   the caveat that absence is not evidence of absence.
3. **W-27 — the budget drill-down as a section of it**, by `section` and
   `line_code` for the chosen ONS code and year. **No per-capita, no
   deflation, no ratio against grants or contracts.** If a comparison looks
   irresistible, the two figures go side by side and the reader makes it
   explicitly.
4. **W-17 — "find my council"** in the global chrome, landing on the page that
   now exists. 347 rows, Fuse.js already vendored. The postcode half stays
   unfiled: NSPD is a large quarterly source with its own archive cost, and
   the name search covers the common case for free.
5. **W-14 — the map click** carries an ONS code through to the same page.

- **Verified by:** a test that the authority page shows the same figures the
  existing endpoints return for that authority; that the public coverage
  endpoint and the admin one agree row for row; that the drill-down endpoint
  computes no ratio and never returns grant and budget as one derived number;
  that every authority name in the corpus resolves through the new control;
  and a browser check of the map click carrying the code.

**Deliberately not in this phase:** comparison between authorities. One
authority at a time here; two is Phase 13 and is a different kind of claim.

#### What changed as it landed

The order held and every "verified by" above is a test. Four things the plan
did not anticipate, and one decision it left to the phase:

- **W-17 is a navigator, not a filter, and that decides where it lives.** The
  filter bar's controls must declare a state key that a page reads — the
  W-05 pin — and a control that navigates has no state to hold. Faking a
  state key for it would have been decoration for the test. It sits in the
  top bar instead, beside the admin links, and selecting an authority goes
  straight to its page. Enter picks the top match; the list shows name and
  ONS code; a failed authorities fetch disables the input rather than
  breaking the bar.
- **The endpoint composes the existing endpoints, which made the phase's
  first pin nearly free and the rest honest.** `authority()` calls the
  `fingertips`, `ndtms` and `contracts` functions rather than re-writing
  their queries, so the "same figures as the existing endpoints" test pins
  the composition itself: if anyone replaces the reuse with a hand-written
  query, the test fails where the two disagree. Grant and budget are the two
  sections that could not be reused (no single existing query returns them
  per authority), so those are the ones the test cross-checks against the
  geography endpoint year by year.
- **The row-for-row pin needed the public side to import the admin side's
  declaration, and the direction is the point.** `public_queries` reads
  `health.COVERAGE_COLUMNS` rather than copying the twelve
  (label, table, column, module) tuples — a second copy would be a second
  statement of what "covered" means, free to drift. The import is one-way:
  the admin module still imports nothing from the portal, which is the
  direction the isolation test already pins.
- **The drill-down pin asserts the row keys, not the absence of a word.** "No
  ratio" as a search for "ratio" in the payload would pass the moment a
  derived number got a better name. The test asserts the exact column set of
  every drill-down row — a derived figure has to arrive as *some* new key —
  and that `grant` and `budget` are separate payload objects. The
  unreadable-denomination row keeps `amount NULL` and its verbatim
  `value_text`, which the fixture exercises and the page renders as "—".
- **A bare `#/authorities` route needed an answer.** It exists now as a
  landing pointing at the search, the map and the treatment page, rather
  than as an error or a 347-row list nobody asked for.
- **One page-wide caveat text was added server-side**: `budget_detail`,
  stating the drill-down's no-per-capita, no-deflation, no-ratio rule in the
  finding's own words, so the section renders it pinned rather than hoping
  a future editor keeps the rule in a comment.

The map click and the typeahead are the two browser checks the plan named,
and both were checked by hand against the real warehouse in the same pass
that loaded every existing route.

### Phase 12 — Show what is already collected · M–L — **done** (2026-08-15)

Delivered **W-23**, **W-26**, **W-25** and **W-24**, in that order. 1,557 →
**1,570 passed** (13 new), 3 skipped, 18 deselected; ruff clean; every new
route and payload loaded against Jon's own warehouse over HTTP with no
failures, and the two new routes served from the running server.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

Delivers **W-23**, **W-26**, **W-25**, **W-24**. Depends on Phase 9.
Independent of Phase 11.

**Why these together:** all four are sections over tables the warehouse
already holds, caveated already, displayed nowhere — the remainder of W-22
after NDTMS. They share the `_public([...])` allowlist edits, the caveat
discipline, and Phase 9's tables and charts. None needs a new module, a new
fetch or a schema change.

Order within the phase, and the first entry has a clock on it:

1. **W-23 — the contracts corpus gets a shape.** Its groundwork was written
   and reverted rather than half-landed, and the entry says reconstructing it
   is an hour. That estimate decays: **if this phase has not started within a
   fortnight of 2026-08-14, pull W-23 forward into whatever phase is running**,
   because an hour's reconstruction becomes a day's rediscovery. Three charts,
   no new route — notices per quarter against the priced count, value
   distribution in **fixed** bands, and the contract-end runway with its own
   drafted caveat.
2. **W-26 — the funnel and the freshness bars on the overview**, the smallest
   of the four and the one that makes the portal state its own limits. A
   zero-promotion funnel must render as *zero*, visibly, not as an empty
   chart — which is also the standing argument for the campaign running in
   Phase 8's background.
3. **W-25 — PFD becomes visible.** Three constraints that are not negotiable:
   *sent* and *named* are different facts and never one series; the ~1,067
   metadata stubs belong on the chart and not in a footnote; coroner areas are
   not local authorities and are not mapped as if they were.
   `restricted_pfd_persons` and `restricted_pfd_report_text` stay out of every
   `_public([...])` — `guard_columns` will stop it, and nobody looks for a way
   around it.
4. **W-24 — the provider deep dive gains its four missing sources**, last
   because it reuses W-25's mentions and W-15's register links, both of which
   exist by then.

- **Verified by:** a test that the value bands are fixed rather than
  data-derived; a browser check that the runway chart carries its caveat and
  that a zero funnel renders as zero; a test that the portal cannot reach
  either restricted PFD table and that sent and named are separate series; a
  test that the disclosure matrix distinguishes "not matched" from "not
  searched".

#### What changed as it landed

The order held and every "verified by" above is a test. Five things the plan
did not anticipate, one of them measured in the browser half of the phase:

- **W-26's freshness belongs on its own route, and the measurement decided
  it.** The first draft put the bars inside `/api/v1/summary` as the plan
  said; on the real warehouse the 14-table MAX scan measured **3 seconds**
  (contracts and `la_revenue_budgets` are 2.8s of it, and neither carries a
  `retrieved_at` index by the P-05 decision that priced and declined the
  twenty-table one). That is exactly the shape `health.freshness`'s docstring
  was written against, and W-21's own correction was the precedent: the bars
  moved to `/api/v1/freshness`, loaded lazily after first paint, so the
  landing page paints before the scan finishes. The funnel stayed in
  `summary` because it is cheap — three small candidate tables and three
  small evidence tables.
- **W-25 became a page, and the frozen lists were the plan's own head-room
  for it.** "A sector-level section" over 1,539 reports, a term index and a
  latest-reports table is more than the landing page wants, and the plan's
  frozen-list note priced new surface in 12. It landed as `#/pfd` with
  `/api/v1/pfd` — one route edit, one static path edit, and the `<noscript>`
  block and `/api` page updated in the same pass, which is the point of
  batching them.
- **`report_date` is verbatim source text, so the year chart reads it with a
  pattern, not a position.** The live corpus mixes '10/04/2026', '12 March
  2026' and 'March 2026' (plus month-word-only and null dates), so
  `_pfd_year` takes the first 19xx/20xx match and the table shows the
  source's own wording. A year that cannot be found is absent from the
  chart, never guessed. The "latest" table orders by the coroner's own
  reference, which opens with the year.
- **The disclosure caveat travels from the view, not from a copy.** Each gap
  cell carries `v_provider_disclosure_gaps`'s own caveat text, so the pinned
  warning is the view's sentence; "not searched" years carry a document URL
  instead of search terms, which is the distinction the plan's test demands,
  and the matrix draws the two as different cell states.
- **The funnel is drawn with div bars, not a chart, and the freshness bars
  reuse them.** A zero-length canvas bar reads as "no data", which is the
  wrong reading for a zero-promotion funnel — the zero is the finding. Bars
  with the count as a text label render zero as "0", and "never" replaces an
  empty track on the freshness side. The funnel renders before the lazy
  freshness fetch resolves, so a zero is visible even while the scan runs.

Also measured and recorded: the runway's two-year window travels in the
payload (`window_start`/`window_end`) so the caption states what the axis
means; and the concern-term index has **8 distinct terms in 214 rows** on
the live warehouse — the chart sums occurrences across reports rather than
plotting the pairs, and 25 bars would have been 8. The two browser checks
the plan named — the runway chart carrying its caveat, and the zero funnel —
were checked by hand against the real warehouse in the same pass that loaded
every route.

### Phase 13 — Comparison, and the inferences it forces · M — **done** (2026-08-15)

Delivered **W-11**, **W-19**, and settled the three §3J entries. On its own
branch, off Phase 11: 1,570 → **1,589 passed** (19 new), 3 skipped, 18
deselected; ruff clean; the compare page's route and payload loaded against
Jon's own warehouse over HTTP, and the frozen-list edits were two routes
(`compare`, `layers`) and one static path (`/js/pages/compare.js`). Phase 12
ran in parallel the same day and both phases edited this file and the frozen
route list, exactly as the plan's note said they would; the two sessions
stashed rather than clobbered each other's uncommitted work.

The plan is above; the record of what changed as it landed is here.

**The three §3J decisions, settled in writing before any of the three was
coded (this is the phase's first-hour deliverable):**

1. **The matrix / tartan rug view is deferred.** W-11 ships the axes'd form of
   the same comparison, so per the entry's own rule W-11 shapes the matrix —
   and the matrix's cell colouring is the same inference surface as item 2,
   which is declined. It is re-filed as the entry it already is; it becomes
   buildable as a rendering of the compare payload, which is why it is cheap
   to revisit.
2. **Significance-aware colouring is declined.** The colour is an inference,
   and `docs/CAVEATS.md` decides which inferences this project makes. The
   register already states the counter-case in its own words: *"two
   authorities whose intervals overlap have not been shown to differ"*
   (`ndtms_estimates`). Colouring authorities by whether their CI overlaps
   the England value would be that sentence inverted — a claim of *shown to
   differ* — drawn over every figure without a decision. Nothing in this
   phase colours by significance, and nothing built on its payloads is
   allowed to either.
3. **Peer-group benchmarking is deferred.** Comparability is a claim, and
   which authorities are comparable is a method decision this pipeline has
   not taken. W-11 is deliberately the opposite shape: the *reader* picks the
   peers, one at a time, and the project never asserts that any set of
   authorities is a group. The compare view is the honest replacement for a
   peer group, and the entry is re-filed as a possible future behind a named
   claim that needs it.
**W-11 — the compare view, and the shape the decisions forced.** The page's
URL is the comparison: `#/compare?ons_code=...&ons_code=...&provider_key=...`,
with the same parameter names the API takes, so a comparison is a shareable
address and the page holds no selection state the URL does not. Every series
is the existing endpoint's series composed rather than re-written — the pin
test holds that composition the same way W-13's does — and each series'
rows are exactly the published columns of its own layer, pinned, so no
per-capita, deflated or cross-layer number has a key to hide in. The
cross-layer caveat is pinned above the whole page, and the contract charts
carry the window caveat because a comparison over years is exactly where "do
not read a trend from it" is most needed. The authority page and the provider
deep dive each link to a comparison seeded with themselves.

**W-19 — the map layers, and one decision of shape.** The toggles are built
from `/api/v1/layers`, whose caveats are read from the export layer registry
rather than copied — `pipeline/exports/geojson.py` now holds `LAYER_CAVEATS`
and the portal imports it, pinned word for word, so a layer that is drawn
here carries the caveat discipline its export carries. The treatment overlay
is the export's own query, pinned row for row against
`treatment_numbers.geojson`. The contracts layer is aggregated to one point
per commissioning authority where the export emits one feature per notice:
98,636 points would be a payload and a canvas no reader could use, and the
aggregation is stated in the layer's caveats rather than left for the reader
to infer. **PFD reports are deliberately not a layer.** They have no geometry
— coroner areas are not local authorities — and the export keeps them
geometry-free for the same reason; the absence is pinned by a test, in the
shape of W-15's CQC decision. The plan's "boundaries" toggle stayed where it
was: the choropleth *is* the boundary layer, and a toggle that turned it off
would leave a map of nothing.

**One thing found in passing and fixed:** `writeStateToUrl` in app.js rebuilt
the hash query from the filter state alone, so a page-owned query key — the
compare page's whole selection — would have been wiped by the first filter-bar
change. It now preserves keys the filter bar does not own, which is what makes
a compare URL shareable in practice rather than until the reader touches a
filter.

Below is the plan as written.

**Why last of the portal phases.** Everything in Phases 9–12 is descriptive:
it shows a figure with its caveat. Comparison is the first thing the portal
would do that is an *inference* — two authorities on shared axes invites a
conclusion about the difference between them, and `docs/CAVEATS.md` decides
which inferences this project makes. That decision is cheaper to take against
a portal that already renders every series it would compare.

- **W-11 — compare two or more authorities or providers** on the existing
  series (grant, budget, treatment, contracts). No new data; the
  no-cross-layer-arithmetic caveats reapply on each shared axis.
- **W-19 — layer toggles on the geography map**, reusing the four layer
  shapes `pipeline/exports/geojson.py` already produces, each carrying its own
  layer's caveat.
- **Three §3J entries are decided here or explicitly deferred again**, because
  each is the same question wearing a different hat: the **matrix / tartan
  rug** view (the same comparison without the axes — whichever of it and W-11
  ships first shapes the other), **significance-aware colouring** (the
  warehouse holds the CIs, so the work is implementation and the *colour* is
  the inference), and **peer-group benchmarking** (comparability is a claim,
  and which authorities are comparable is a method decision). Settle them in
  the phase's first hour, in writing, before any of the three is coded.

- **Verified by:** a browser check of a two-area comparison with the
  cross-layer caveat present on the shared axis; a test that every toggled
  layer carries its own caveat text.

### Phase 14 — Gated by runs and decisions, not by effort · M — **done (2026-08-16)**

Delivered **P-03** and **F-05**, or records their refusal again. The answer
to both was no, so this is the phase's predicted "paragraph in the register
and a day" outcome — a successful one, and the refusals are recorded here
rather than allowed to re-open by default.

Neither is blocked on code, and neither should be started inside another
phase — which is why they are a phase and not a footnote to one.

- **P-03** needs two complete collections, several hours each, ~6,300 requests
  each, against live public bodies, the second existing only to be compared
  with the first. It is a deliberate act to schedule. The recommendation is
  unchanged: `--jobs 1` stays the default, and the comparison is worth running
  once anyway so the default is *evidenced* rather than merely conservative.
- **F-05** needs the decision in open question 2 before any design. The
  recommendation is unchanged and is still *not yet*: history multiplies rows
  and invites precisely the cross-year differencing the census caveat forbids.
  If it is taken, it is taken **on one table, for one named claim** —
  advertised bands over time being the plausible one, and the one Workstream
  B3 would feed. The §3J "versioned datasets, ONS-style" entry is this same
  decision with a delivery shape attached, and is decided here or not at all.

**If the answer to both is no, this phase is a paragraph in the register and a
day.** That is a successful outcome, not a skipped phase — Phase 7 ended the
same way and the numbers it wrote down are why nobody has to re-derive P-01.

#### What changed as it landed

The phase ended in the outcome its plan priced, and the record is two
decisions rather than a diff. Suite green on the surrounding commits — this
phase ships no code, and its test is that the register now says so.

**P-03 — refused, not deferred.** `--jobs 1` remains the default, and no
comparison runs are scheduled. The acceptance is unchanged and stated again
so it is not re-derived: one full `--jobs 4` run against one full serial run,
on rows, review items and parse failures — two complete collections,
~6,300 requests each, several hours each, against live public bodies. The
recommendation that the default stays *conservative rather than evidenced*
is now the standing decision; the runs would be a deliberate act to schedule
against a campaign calendar, and they are not on one. The finding stays open
in the register because it is evidence-gated, not because anything is
blocking it — see the P-03 entry in §3C.

**F-05 — the decision in open question 2 was taken, and it is *not yet*.**
No table gets history. The §3J "versioned datasets, ONS-style" entry is
therefore decided here as well, as its plan said it would be: no versions,
no time series, and the claim that would justify one — advertised bands over
time, the B3 feed — has not been made. The decision is recorded, which is
the whole point of this phase: a refusal that is written down cannot be
re-litigated by default, and a claim that arrives later starts from the
standing shape rather than from first principles. `nhs_job_adverts` and
`provider_pay_pages` stay snapshot tables; re-runs replace, which is what
the F-05 note in m22's own code says is the non-versioned case.

---

### Phases 15–19 — the workstreams

§8 files four workstreams with their reasoning; this is the order to take them
in and what each unlocks. They are coarser than Phases 8–14 on purpose — every
one begins with a design session, and pre-specifying past that point would be
inventing detail the source review has not earned yet.

### Phase 15 — The cheap sources that feed everything else · S–M — **done** (2026-08-15)

Delivered **G7** (statutory pay rates, m17), **B2** (Living Wage
registrations, m18), **G6** (data.gov.uk CKAN, m19), and folded **G3** (PSC)
into m04 and **G4** (EAT) into m02, as the plan said it should. 1,568 →
**1,619 passed**, 3 skipped, 21 deselected; ruff clean.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

**Why these five, and why first among the workstreams:** all are S or small M,
none opens a new politeness surface — G3 is m04's API family and key, G4 is
m02's host, G7 is one annual reference table, B2 is thirteen lookups — and
between them they unblock three later phases. G7 is the anchor for every
"advertised band versus the statutory floor" statement Phase 17's claims index
will want to make. G3 supplies the ownership edges Phase 18's universe needs.
G6 multiplies G5, B4 and W-13 at the cost of one keyless documented API.

The gate G1 flags applies to G7 in advance: a floor comparison is
**side-by-side**, and any ratio ("X% above the NLW") is the CAVEATS reading's
decision, not the module's.

#### What changed as it landed

The plan held in the large — three new modules, two expansions, no new
politeness surface — and six things are worth recording:

- **G3 and G4 were folded into m04 and m02, and the fold is what the plan
  priced.** Both reuse the existing client, host and (for G3) key, and both
  had to sit where their family's conventions already live. The cost of the
  fold was the test suites: every m02 and m04 end-to-end test now also runs
  the new pass, so each needed a mock for it. That was the honest price of
  "no new politeness surface", and it is paid once.
- **EAT attribution is on the title alone, and body-only mentions are
  queued.** The GOV.UK search indexes judgment bodies, and the first real
  fixture found the shape the caveat had to cover: the Attorney General's
  restriction-order judgments list the target's litigation history — provider
  cases included — in the body. Such hits are `eat_body_mention_only` review
  items, never `eat_cases` rows, and the module does not even fetch the
  decision page for a title it will not attribute.
- **The rates page's band set changes between eras, and the parser is pinned
  to that.** "25 and over" until 2021, "23 and over" to 2024, "21 and over"
  since. The band labels are stored verbatim; the living wage column is
  identified by the page's own layout (it always leads each table), never by
  the law. Cells carry non-breaking spaces and whole-pound values; an
  unreadable cell is NULL plus a `parse_failures` row, with the cell kept
  verbatim in `value_text`.
- **B2 is one lookup per provider, binary, with the window said out loud.**
  The register's own count line is compared against the checked window (3
  pages); when the count exceeds it, a `living_wage_search_truncated` review
  item attaches, so "not found" is never silently "not in the checked
  window". A near-miss name is an `unconfirmed_living_wage_name_match` review
  item, never a stored accreditation.
- **G6's organisation pass links only exact normalised matches.** The
  catalogue's organisation list is matched against authorities and providers
  on normalised names; a council whose catalogue sits under a
  differently-spelled organisation is not guessed and is not a review item —
  the universe work (F1) owns reconciling names at scale. Each dataset row
  accumulates its `matched_terms` across passes and runs, so a row's terms
  are the complete record of how this pipeline has found it.
- **The licence table gained a deliberate non-OGL entry.** The Living Wage
  list is charity-published factual data with no open licence statement;
  `lwf_own` carries the reason next to the name in both mirrors
  (`pipeline/licences.py` and the portal drawer), so the export header cannot
  drift into claiming a permission nobody granted.

The three new modules are registered in the progress-coverage, smoke and
docs-coverage suites; the module count the tests pin moved 17 → 20.

### Phase 16 — Direct pay evidence and its comparators · M–L — **done** (2026-08-15)

Delivered **B3** (the provider pay-page module, m22, and the sustained m16
crawl — the role-keyword pass), **G1** (ONS ASHE, m21) and **B1** (gender
pay gap filings, m20), in that order. 1,619 → **1,666 passed**, 3 skipped,
24 deselected; ruff clean.

What follows is the plan; the record of what changed as it landed is at the
end of the entry.

**B3** (provider career and reward pages, plus a sustained m16 crawl), **G1**
(ONS ASHE), **B1** (gender pay gap filings).

**Why this is the highest-value collection work in the plan:** this is a pay
campaign, and `nhs_job_adverts` holds **35 rows** — the README's "only direct
pay evidence" is a sliver. B3 widens the sector's own half; G1 supplies the
comparator market the sector is measured against; B1 is a mandatory annual
public filing with a claim shape already written. B1 needs its scope rule
decided before collection: a provider under 250 staff is outside the law's
reach, and its absence must read as *out of scope*, never as a zero.

B3 is also where the F-05 decision becomes load-bearing — an advertised band
per provider per period is a snapshot until history exists, and "the change is
the claim" is the campaign's own argument. Phase 14 before this one, then, if
the answer is going to be yes.

#### What changed as it landed

The order held — B3 first because it is the sector's own half, then the two
comparators — and every "verified by" is a test. Seven things the plan did
not anticipate, three of them found by doing the live verification the
modules' registration discipline demands:

- **The gender pay gap scope rule landed as a review item, not a flag.** The
  plan said absence must read as out-of-scope, never as a zero. The module
  stores only matched filings and raises one `gender_pay_gap_absence` item
  per (provider, year) naming exactly what was searched — the name variants
  and the company numbers. The item is the decision point: fewer than 250
  staff, or did not file. There is no `out_of_scope` column, because writing
  one would be a second, unattributed copy of the decision the queue
  already owns — the same argument migration `0030` makes for promotion.
- **The employer→filing match is company number first, name second, and the
  normalisation is shared with m04.** Charities file without a company
  number, so the name fallback is the m18 discipline (exact-normalised,
  never a near-miss — "Viaduct Care" is not Via). The company-number side
  goes through `providers.normalise_identifier`, the same padding m04
  applied on the way in, so one company's filing cannot split in two. That
  is why m20 declares `depends_on=("m04_companies",)`.
- **`ResponsiblePerson` is not collected at all.** The CSV column is the
  name of the person who confirmed the figures. The schema has no column
  for it — the strongest form of "personal data stays out" is not storing
  it — and the migration's comment says why, so a future editor sees the
  decision rather than just its absence.
- **The ONS observations endpoint answered 502 for every ASHE query at
  verification, and the module is built to fail loudly rather than quietly
  collect nothing.** The dataset, edition, dimension and options endpoints
  all answered (the options are where the labels come from — the code-list
  items themselves carry no label text, which is why the module reads the
  version's own options rather than the code lists). The observations
  endpoint 502'd on single-observation and wildcard queries alike while a
  cpih01 query answered, and the API's ASHE versions lag the publication
  (table 3 serves version 7, released 2024-01-19). The shared client's
  house rule — a persistent 5xx raises and fails the run — is exactly
  right here, so m21 currently fails against the live API instead of
  producing a plausible-looking empty series. That is the honest state,
  recorded in the module docstring, SOURCES.md and the smoke spec, which
  is expected to fail until the API recovers. The module itself is built
  and fully tested against the documented response shapes.
- **B3's registry found three mergers that the provider list's own notes
  had already filed.** Richmond Fellowship's domain serves Waythrough
  (merged October 2024), Humankind's the same way, and wdp.org.uk serves
  Via (WDP merged into Via in 2020). The registry records the mergers in
  the notes and points each at the merged organisation's careers pages —
  the rows stay under the provider_key that searched, and the caveats say
  the pages are the merged organisation's.
- **The provider crawl is bounded the way m16's paging is bounded, and a
  page that answers with no figures is an answer about that page.** The
  registered pages are the hand-verified entry points; the crawl follows
  same-host links whose anchor or URL carries the pay vocabulary, one hop,
  ten followed pages per provider. `provider_pay_pages.pay_mentions = 0`
  means the provider published no figures on that page — a real answer,
  visible as a zero count. A page that did not answer is
  `pay_page_unavailable` or `pay_page_robots_disallowed`, never a zero row.
  Attribution is exact by construction — the page is the provider's own
  site — so every mention carries `match_basis = 'site_owned'` and there
  is no free-text matching anywhere in the module.
- **The sustained crawl is a role-keyword pass, and it reuses every rule
  the employer pass already proved.** `nhs_job_adverts` gains `surfaced_by`
  (`employer_search` / `role_search`, first discovery, stable across runs —
  both passes `preserve` it and `searched_variant`). The keyword never
  decides whose advert it is; attribution stays on the advert's own
  employer field. What deliberately differs: a role search that finds
  nothing, or returns only other employers' adverts, is a normal outcome
  and is not queued — the `nhs_jobs_search_no_matches` and
  `unmatched_nhs_jobs_employer` items exist for employer searches, and a
  keyword pass must not flood them. A markup change is still recorded, by
  either pass.

Also worth recording: the licences table gained a deliberate non-OGL entry
for m22 (`provider_own`) — a provider's website is its own copyright, and
the export header must not claim a permission nobody granted. Both mirrors
updated, per the licence test.

### Phase 17 — The claims-to-evidence index · M — **done** (2026-08-17)

Delivered **C1** (the claim registry migration) and **C2** (the "What we can
say" page) — the last item of the plan. **The gate was met when this phase
started:** the campaign had produced 1,575 `evidence_promotions` rows and 68
verified census metrics in the live warehouse [live], which is what the plan
meant by "enough verified evidence for the first claims to be real".

**C1** is migration `0048` in both trees: `claims`, `claim_citations` and
`claim_verifications`, with two triggers refusing a claim that is decided —
or born decided — without a `claim_verifications` row behind it. That is the
plan's standard taken literally: "a claim without a recorded reviewer and
decision history is not a claim", the same shape migration `0030` gives
promotion. The write half is `pipeline/claims.py`: create (draft only, by a
named person), cite/uncite (draft only, the citation keyed to the row's own
natural key and **refused if it does not resolve**, the same refusal
promotion makes for a dead link), decide (published/rejected/retracted, one
claim per request, decision row written before the status moves), reset
(decisions stay). The lifecycle is draft → published/rejected, published →
retracted, anything → draft by reset; a decided claim's text and citations
are not editable underneath the decision.

**C2** is the portal's `#/claims` page and `/api/v1/claims`. Only published
claims are served; each renders with its citations resolved to labels and
links, its own "you may not compute this from it" lines, and the reviewer and
date. A citation whose row a module re-run replaced renders as unresolvable
rather than dropped or guessed at — the census `stale()` honesty, one level
up.

What changed from the plan as it landed:

- **The citation registry is a whitelist with per-table resolvers, not a
  generic link.** A claim may cite nine evidence tables — the three promoted
  document tables, verified census metrics (cited by their `metric_key`, and
  only `verified = 1` rows are citable), statutory pay rates, ASHE
  observations, NHS Jobs adverts, provider pay mentions and gender pay gap
  filings. Contracts are deliberately not citable: a claim rests on rows with
  a human verification step, and the notice corpus has none. The whitelist is
  `CITABLE` in `pipeline/claims.py`, the same shape `promote.py`'s `KINDS`
  has, and a test pins it.
- **The open question was folded in as recommended.** Who writes claims and
  does a claim need one named reviewer per row? Yes to both, recorded the
  same identity `review_decisions` already uses: `created_by` on the claim,
  `decided_by` on every decision, neither ever defaulted.
- **The admin surface is a Claims tab in the census shape** — counts pill,
  status-filtered worklist, an evidence picker per claim, decide buttons
  behind the reviewer box, and a decision history that survives resets.
- **The claims tables needed the pgload machinery.** `claim_verifications`
  deliberately carries no foreign key (the loader writes verifications ahead
  of the claims they vouch for, the same arrangement 0033 documents), so
  `pgload.TRIGGER_EDGES` and `pgverify.GUARANTEES` each gained an entry.

Suite green: **2,114 passed**, 3 skipped, 27 deselected; ruff clean.

### Phase 18 — The sector universe · L — **done** (2026-08-15)

Delivered **F1** (m23, the universe build), **F2** (the coverage
denominators), **F3** (the sector-shape export tab `10_Sector_Universe`) —
with D-04's remaining 3,160 review items enriched as unresolved leads. Suite
green: **1,883 passed**, 62 skipped, 25 deselected; ruff
clean.

The record of what changed as it landed is at the end of the entry. The plan
as written:

**F1** (the universe build), **F2** (coverage denominators), **F3** (sector
shape as a publication); D-04's identity leads remain in the queue for
accountable decisions.

That last part is the point of putting these together. `unmatched_buyer_name`
(2,667) and `possible_group_company` (493) are the universe's reconciliation
labour arriving one review item at a time, in the form that produces no
universe at the end of it. Done here they are the same hours spent once, with
a `sector_universe` (or extended `providers`) table to show for them.

Universe membership keeps m04's match-basis discipline exactly — name-only
matches stay name-only, unconfirmed stay unconfirmed — or the universe becomes
a larger and less verifiable version of the problem it was built to solve. The
one recorded-not-decided design question stands: new table, or extension of
`providers`. Organisations are not personal data, so the `restricted_`
discipline does not reach this.

#### What changed as it landed

- **The design question settled as a new table, and the argument is in
  migration `0045`.** `providers` is reference/config — seeded from code,
  no provenance, the human-curated thirteen. The universe is
  evidence-derived, unbounded, and must keep provenance and match-basis per
  row; extending `providers` would have made the config table unbounded and
  the universe restricted to what config can hold. Not a compromise: the two
  tables answer different questions, and the universe row's `provider_key`
  links back into `providers` through the one door the discipline allows.
- **The universe is a capture of who shows up in the corpus, not the "~M" a
  headline wants.** The plan expected "hundreds of organisations"; the
  actual data is **29,680 rows built in 6 seconds** [measured, on a copy of
  the live warehouse]: 13 providers, 502 companies (9 collected by m04 plus
  the 493 candidates), 3 charities, 4 CQC providers (all four merged into
  their seeded company rows — same legal person), 26,069 name-only awardees,
  1,310 PPON awardees and 1,783 funders, with 1,316 awardee names and 866
  buyer names merging into rows that already held the same organisation.
  The awardee side is dominated by one-off winners of in-scope lots, which
  is exactly what the notices' CPV-prefix matching produces — so the export
  tab's first caveat says the universe is never a complete list of the
  sector, and the identified rows (register + PPON, 1,326 of them) are the
  rows any "we track N of the sector's ~M" may count as N.
- **The CQC half of the universe is a floor, not a census.** m05 collects
  only the tracked handful, so that is all the build can reconcile. Widening
  it is new collection (B4-adjacent), not reconciliation, and the ten
  `possible_cqc_provider` items stay in the queue for the same reason.
- **The 3,160 items remain visible review leads.** The build captures them
  systematically as name-only rows, but review_sweep no longer marks them
  answered: the authority, provider, or group identity question is still a
  human judgement. Every captured lead has a universe row behind it, but that
  is enrichment, not confirmation.
- **F2's denominator is the table; the statements that use it are future
  work, and said so.** The build logs the coverage counts
  (`universe.run_complete` carries totals by type and by basis), and the
  export tab's caveats name the reading rule — identified rows for N, basis
  stated, never the whole capture. Publishing the sentence on the portal or
  in the claims index is Phase 17's or 19's, not this phase's: the portal
  surface is a frozen list and the claims index is gated on the campaign.
- **F3 is the tenth sheets tab.** `10_Sector_Universe` carries every row
  with its match-basis columns and six caveats (capture-not-census,
  name-only meaning, PPON meaning, provider_key rule, funder meaning, the
  one-layer `notices_count`), through the existing export machinery — so it
  inherits the provenance companion, the bundle, the licence line and the
  guard discipline for nothing.
- **The universe normaliser is shared, not second-guessed.** One
  `normalise_name` in m23 merges on, stripping both suffix families so a
  funder and an awardee with the same name land on the same row; the funder
  pass re-checks buyer names with m01's own matcher before capturing, and
  `normalised_name` is stored so the sweep rules join in Python with the
  same function rather than reimplementing it in SQL.
- **`provider_key` is the one rule, and it is enforced structurally.** The
  build reads `provider_identifiers` once and every register row's
  provider_key comes through it (or through a company row m04 seeded);
  `name_only_unconfirmed` rows have no identifiers and can never acquire
  one. A test asserts zero name-only rows carry a provider_key — on the
  live data, 20 rows link to a tracked provider, all by identifier.
- **The migration number collided with the postgres workstream, and the
  live warehouse is already on the phase.** The same hour this landed,
  issue #21's phase-4 branch shipped `0044_contracts_by_date_published.sql`
  and applied it to the live PostgreSQL warehouse, and a web-server startup
  on this branch applied this phase's migration under the same number
  before the rename. Renamed to **`0045`** (apply order decides the number
  order), the phantom `0044_sector_universe` record removed from the live
  `schema_migrations`, and the phase then applied to the live warehouse for
  real: migration `0045`, the m23 build (29,680 rows, 20 identifier-linked
  to tracked providers). The captured identity leads remain pending until a
  person decides them.

Below is the plan as written.

---

**F1** (the universe build), **F2** (coverage denominators), **F3** (sector
shape as a publication). The remaining D-04 identity leads are captured here
as enrichment but remain in the review queue for accountable decisions.

That last part is the point of putting these together. `unmatched_buyer_name`
(2,667) and `possible_group_company` (493) are the universe's reconciliation
labour arriving one review item at a time, in the form that produces no
universe at the end of it. Done here they are the same hours spent once, with
a `sector_universe` (or extended `providers`) table to show for them.

Universe membership keeps m04's match-basis discipline exactly — name-only
matches stay name-only, unconfirmed stay unconfirmed — or the universe becomes
a larger and less verifiable version of the problem it was built to solve. The
one recorded-not-decided design question stands: new table, or extension of
`providers`. Organisations are not personal data, so the `restricted_`
discipline does not reach this.

### Phase 19 — Heavy, conditional, or gated · M–L — **done** (2026-08-16)

Delivered **B4** (the registry's last verified entries and a sweep rule that
closed 150 stale queue items), **G5** (m24, council spend-transparency),
**G2** (m25, Skills for Care — the access-shape review passed and the module
followed), and took the **G8** review's decision: the Adzuna terms fail, so
it is dropped and the refusal is recorded below. Suite green; ruff clean.

The record of what changed as it landed is at the end of the entry. The plan
as written:

**B4** (authority-website registry to full 347-council coverage), **G5**
(council spend-transparency files), **G2** (Skills for Care), **G8** (Adzuna).

**B4 is gated on campaign throughput**, per the judgement above: it multiplies
candidate discovery, and multiplying discovery into a queue that is the
bottleneck is not progress. D-05's fix means answers now survive in
`pipeline/verified_websites.json`, so the ~86 URLs lost with the override
table cannot be lost the same way twice — the registry can be built up
incrementally from here rather than in one campaign.

**G5 depends on B4** and is the strongest procurement evidence the corpus
could hold — "council X paid provider Y £Z" is actual money, not a notice.
Line-item quality varies council to council, so the NULL discipline does real
work: an unreadable file is a `parse_failures` row and a review item, never a
zero.

**G2 and G8 each begin with a review, not a module.** G2's machine-readable
access is partial and the access shape is the first task; G8's terms are
commercial and its parsed salary fields need a reliability check before
anything is built on them. If either review fails, drop it and say so here —
m16 and B3 already own the NHS and provider-site halves of the advert
question.

#### What changed as it landed

- **The B4 gate was lifted, and the record of why is in the queue itself.**
  The phase plan gated B4 on campaign throughput — "multiplying discovery
  into a queue that is the bottleneck is not progress". Phase 18 made the
  identity leads easier to research by enriching them with universe rows;
  the leads themselves remain visible, so the queue is still the campaign's
  honest measure of unresolved identity work.
- **B4's registry work was a re-verification pass, and it was honest about
  what did not move.** The 49 home pages the 2026-08-14 pass could not verify
  were fetched again through the pipeline's own client, plus the
  replacements `docs/verification/authority_homepages.md` named without
  testing. **Two answered** — Broadland and South Norfolk share
  `www.southnorfolkandbroadland.gov.uk`, and both are now in the registry.
  The other 47 answered exactly as before (34 still refuse the client, six
  still serve a bot challenge, six still fail TLS, one robots.txt) — a bot
  block that appears in August is no more a verified URL than one that
  appeared in June, so they stay in the queue. The same pass ran m10's
  committee discovery over the 212 authorities with no committee URL and
  found **eight more portals** (Isles of Scilly, Three Rivers, Dover,
  Sevenoaks, Tonbridge and Malling, South Kesteven, West Suffolk, and
  Broadland via the shared South Norfolk portal) — and found that the other
  174 councils publish no committee-system link on their home page, which is
  an answer about those councils and the reason the review UI (D-05) remains
  the answer route for them.
- **The stale queue was the bigger half of B4, and it needed a rule, not a
  registry.** 150 `authority_website_unknown` items sat pending after m15's
  mySociety profiles gave every authority a home page — the answer existed,
  the queue did not know. The new `authority_website_available` sweep rule
  mirrors m09's own condition (`website_for()` returns a base URL today, from
  an override, the tracked verified file, the registry or the mySociety
  profiles), so what m09 would not raise, the sweep closes. Against the live
  warehouse: **all 150 items were answerable**; the sweep closes them with
  evidence naming the URL and its source, and `reopen` undoes it if the rule
  is wrong.
- **G5 is m24, a harvest module in the m09/m10 shape.** For every authority
  with a base URL, a bounded set of likely transparency paths is crawled and
  links whose URL or text carries the spend vocabulary are followed when they
  point at a data file (CSV, XLSX, ODS; at most three files per authority).
  Line items are stored verbatim (`payee`, `amount_text`, `period`,
  `description`) with `amount` parsed beside them — NULL where the council's
  formatting could not be read, never a zero — and a file that cannot be
  parsed is `parse_status = 'unreadable'` plus a `parse_failures` row and a
  review item, never a silent skip. `provider_key` is set only by an
  exact-normalised payee match against the tracked providers' own variants
  (m04's discipline, the same rule m16 and m20 apply); name reconciliation at
  scale stays the universe work's. No arithmetic across rows or sources — no
  totals, no share-of-spend, no comparison against contracts. XLSX is read by
  a new stdlib reader (`pipeline/xlsx.py`, zipfile + ElementTree, streaming
  for the multi-hundred-MB sheets) rather than a new dependency.
- **G2's review passed, and the module followed.** The access-shape review
  verified by request: five .xlsx workbooks on the Data downloads page,
  robots-clean, and the ASC-WDS data OGL v3.0 per the data.gov.uk catalogue
  entry (the publisher's own pages carry a site-wide copyright line, which is
  why the licence entry says the terms and their source rather than a bare
  "OGL"). m25 fetches all five, archives them, and parses the three
  current-year workbooks whose data sheet carries the standard columns
  (regional, local-area, ICB): `fte_annual_pay`, `hourly_pay`,
  `turnover_rate` and `vacancy_rate` per (area, sector, service, job role),
  keyed by the workbook's own ONS area codes and stored as published — the
  publisher's `*` suppression marker is NULL, not a parse failure. The
  statistical appendix (report tables) and the trended workbook (the
  change-over-time series F-05 declined history for) are fetched and archived
  but their shapes are not parsed, recorded per file with a review item
  saying why. Measured against the real files: the regional workbook parses
  2,420 estimate rows and the local-area one 39,204 (36,784 at local-authority
  level), in about a minute each through the streaming reader — the full-tree
  read of the 53 MB local file took ten.
- **G8 was dropped, as the plan said it could be.** The terms review found
  the Adzuna API's own conditions: any use by an organisation for ongoing
  work or research is a 14-day trial, after which a licence agreement is
  required, and salary data carries an attribution obligation ("Adzuna
  Jobsworth"). The campaign's use is precisely the ongoing research the terms
  fence off, and this project does not collect under terms that require a
  licence nobody has obtained — the same standard that keeps Care Opinion out
  (§6). Dropped and recorded here, per the plan: m16 and B3 already own the
  NHS and provider-site halves of the advert question.

Below is the plan as written.

---

**B4** (authority-website registry to full 347-council coverage), **G5**
(council spend-transparency files), **G2** (Skills for Care), **G8** (Adzuna).

**B4 is gated on campaign throughput**, per the judgement above: it multiplies
candidate discovery, and multiplying discovery into a queue that is the
bottleneck is not progress. D-05's fix means answers now survive in
`pipeline/verified_websites.json`, so the ~86 URLs lost with the override
table cannot be lost the same way twice — the registry can be built up
incrementally from here rather than in one campaign.

**G5 depends on B4** and is the strongest procurement evidence the corpus
could hold — "council X paid provider Y £Z" is actual money, not a notice.
Line-item quality varies council to council, so the NULL discipline does real
work: an unreadable file is a `parse_failures` row and a review item, never a
zero.

**G2 and G8 each begin with a review, not a module.** G2's machine-readable
access is partial and the access shape is the first task; G8's terms are
commercial and its parsed salary fields need a reliability check before
anything is built on them. If either review fails, drop it and say so here —
m16 and B3 already own the NHS and provider-site halves of the advert
question.

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
| Full-text search over archived documents | Attractive, but it is a new index over 3.6 GB with its own freshness problem. Revisit after Phase 4 gives it verified documents to search rather than candidates. — **Revisited and delivered narrower than filed, 2026-08-26 (BETA-022):** the index already existed — `pipeline/documents/` (docs/document-analysis.md) parses PDFs into SQLite FTS5/PostgreSQL `tsvector` text as a side effect of the document-analysis layer, unrelated to this entry — so this was wiring an existing backend to a route (`/api/v1/document_search`), not building the index this entry priced. Scoped to the two source systems actually parsed today (committee papers, CDP documents) via an explicit allowlist in `public_queries.document_search()`, not the whole 3.6 GB archive; see beta.md's BETA-022 for the full reasoning, including why `_public()` alone does not guard this. |

## 7. Open questions

1. **Who verifies candidates, and to what standard?** *Phase 4 built it on the recommendation below; the question of who actually does the verifying is still yours.* My recommendation: one named reviewer per row, the same identity `review_decisions` already records, and no bulk promote for anything above a candidate's source page — bulk *reject* is fine. Depends on whether anyone besides you will do it.
2. ~~**Do you want history at all (F-05)?**~~ *Settled 2026-08-16 (Phase 14):* **not yet**. Recommendation: not yet, and not as a general "version every table". If a specific claim needs it — advertised bands over time is the plausible one — add history to that table alone, with a caveat forbidding the differencing the census taught you to forbid.
3. ~~**Should `m13` be re-run now?**~~ *Settled in Phase 1:* re-run, and it had been a dry run all along. 477,199 rows.
4. **Retention for `data/raw` (P-02).** Recommendation: keep everything until it hurts, but measure and document the curve now so the decision is not taken in a hurry at 20 GB.
5. **Is `--jobs 4` worth promoting to default?** Recommendation: only after Phase 7's comparison, and probably not — the current default is the conservative one and the run is not interactive.

6. **Should a review resolution write to the codebase as well as the warehouse (D-05)?** Recommendation: yes. The UI already confirms a URL responds before storing it, which is the same standard `authority_websites.py` sets — so the answer is registry-quality at the moment it is given, and only its filing is not. Losing 86 of them proved the point.
7. **How often should `pipeline backup` run, and who deletes old ones (D-06)?** Recommendation: before every `run all` and on a daily schedule, keeping the last seven plus any labelled one. The failure was not that backups did not work; it was that the only one on disk had been taken after the damage.

## 8. Proposed workstreams — filed 2026-08-14; every item delivered except G8 (dropped) — corrected 2026-08-25

**Correction, 2026-08-25:** this section's own header said "not yet started"
even though §2's summary at the top of this file already recorded every one
of these delivered in Phases 15, 16 or 18 — the individual entries below
were simply never updated to match, the same drift W-23–W-26 had in §3.
B1, B2, B3, F1, F2, F3, G1, G3, G4, G6 and G7 are now tagged `DELIVERED`
in place, against the module or table that ships each one, checked
2026-08-25. Only B4, C1, C2, G2, G5 (already correctly tagged) and G8
(correctly dropped) needed no change. This was caught while starting on
BETA-004 in `beta.md` — a reminder that "reconciled" (BETA-002) meant §3
only; §8 was missed the first time.

**Sequenced as Phases 15–19** at the end of §5; this section keeps the
reasoning for each item, that one keeps the order and what each unlocks. Two
sequencing judgements made there change how these read: D-04's remaining 3,160
review items were folded into F1 rather than ground through the queue, and B4
waited until the verification campaign was demonstrably clearing rows — which
Phase 18 made true, and Phase 19 then ran.

Two of the three workstreams from the "large upgrade" review, filed so the
thinking survives, plus one from the longer-term workstreams review and one
from the sources review (Workstream G).
Workstream A (the verification campaign) is not a section here — it is F-01,
F-03 and the queue itself, already in the register, and its cost is labour and
the open-question-1 decision, not code. Workstreams D and E are existing
entries: D is F-05 and P-03 — *both decided on 2026-08-16 (Phase 14), which
is D decided and recorded* — E is W-13, the §3J search entry and the unfiled
prerender idea.

The thesis the workstreams share: the project's ceiling is the number of
verified, cited rows — today zero — and the portal is presentable but
secondary. B widens what verification has to work on; C makes what it produces
legible as claims.

### Workstream B — New evidence terrain

Three sources, all public, all pay-relevant, each filed with the shape of the
claim it would support.

**B1. Gender pay gap reports · M — DELIVERED Phase 16 (m20)** — mandatory annual public filings by
employers with 250+ staff. A new module over the government filing site, each
filing archived like every other source. Claim shape: "of the tracked
providers that must file, X report a mean gender pay gap of Y%". Depends on
the provider → employer mapping m04 already builds; needs a decision on the
scope rule — a provider under 250 staff is outside the law's reach, so its
absence must read as out-of-scope, not as a zero.

**B2. Living Wage Foundation registrations · S — DELIVERED Phase 15 (m18)** — one public lookup per
provider, binary, citable. Claim shape: "N of 13 tracked providers are
accredited living wage employers". Fetch, archive, record accreditation date
and status like any other source.

**B3. Provider career and reward pages, and a sustained m16 crawl · M–L — DELIVERED Phase 16 (m22)** —
`nhs_job_adverts` holds 35 rows **[live]**: the "only direct pay evidence"
([README.md:144](README.md:144)) is a sliver. A provider-side module over
career and reward pages — advertised bands, "rewards package" pages, listed
rates — plus a sustained crawl of the NHS Jobs feed the module already reads.
Claim shape: the advertised band and rate per provider per period — and the
F-05 decision (open question 2) is what turns that snapshot into the time
series the campaign's "the change is the claim" argument needs. *Decided
2026-08-16 (Phase 14): not yet — B3 stays a snapshot, and the claim that
would justify history has not been made.*

**B4. Authority-website registry to full coverage · M — DELIVERED 2026-08-16 (Phase 19)** — m09/m10/m15 are
coverage-limited by the hand-verified registry in `authority_websites.py`, and
the ~86 council URLs answered in the UI before D-05's fix were lost with the
override table ([§3B, D-05](docs/upgrade-roadmap.md)). Full 347-council
coverage means candidate discovery everywhere rather than on the verified
handful — the difference between searching one council and 315 that the
README records m09/m10 once paying for ([README.md:163](README.md:163)).

### Workstream C — The claims-to-evidence index — **DELIVERED 2026-08-17 (Phase 17)**

The difference between a data portal and an evidence portfolio: claims as
rows, each linked to the verified evidence that supports it, with the caveats
that travel with it. Changes no CAVEATS — it packages them.

**C1. A claim registry (migration) · M — DELIVERED** — a sanctioned table where campaign
claims are rows: the claim's text, the verified evidence rows supporting it,
the caveats attached, the reviewer and the date. Nothing in it is computed —
a claim is a statement linked to rows, and the linkage is a human judgement
recorded like every other decision. The promotion guarantee (migration `0030`)
sets the standard: a claim without a recorded reviewer and decision history
is not a claim. See migration `0048` and the Phase 17 record.

**C2. The "What we can say" portal page · M — DELIVERED** — renders the registry: each
claim with its citations and its "you may not compute this from it" lines.
Read-only like every portal surface; the claims themselves are maintained in
the same review-and-decide workflow as everything else — the operator UI's
Claims tab.

Open question folded in: who writes claims, and does a claim need one named
reviewer per row, the same identity `review_decisions` already records? The
recommendation is the one open question 1 already makes for candidates —
**adopted**: `created_by` on the claim, `decided_by` on every decision.

### Workstream F — The sector universe (the population workstream)

The thesis: the pipeline tracks 13 providers and 347 authorities, but the
denominator — how many organisations make up the sector — is unknown. Every
coverage statement needs a universe to be measured against, and none exists.
The universe is the upstream condition for W-12's matrix meaning anything
beyond the 347, for Workstream C's sector-level claims, and for any sentence
of the form "we track N of the sector's ~M".

**F1. The universe build · L — DELIVERED Phase 18 (m23)** — reconstruct the complete provider and funder
population from sources the pipeline already reads: CQC registrations, the
charity register, Companies House, and the awardees in the 98,636 notices.
The work is reconciliation, not new collection: hundreds of organisations
joined by company and charity number where they exist, name-matched where
they do not — the same labour `unmatched_buyer_name` and
`possible_group_company` (D-04, still pending) already represent, done
systematically once rather than one review item at a time.

**F2. Coverage denominators · M — DELIVERED Phase 18** — with the universe in place, every
coverage statement gains a denominator: "we track N of the sector's ~M
providers", "contracts are observed for X of M". Universe membership must
keep the match-basis discipline m04 already sets — name-only matches stay
name-only, unconfirmed matches stay unconfirmed — or the universe becomes a
larger, unverifiable version of the problem it solves.

**F3. Sector shape as a publication · M — DELIVERED Phase 18** — the universe is itself an
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

**G1. ONS Data Explorer API (ASHE) · M — DELIVERED Phase 16 (m21)** — the Annual Survey of Hours and
Earnings, via the ONS developer hub ([developer.ons.gov.uk](https://developer.ons.gov.uk/)):
median pay by industry (SIC) and occupation, public and OGL. Claim shape:
"median pay for [occupation] in England is £X, against which the sector's
advertised bands sit at Y%" — the strongest missing comparator market for
what the sector pays versus comparable work. One discipline to settle when
the claims index (C1) meets it: an ASHE-versus-adverts statement is a
side-by-side comparison, not an arithmetic ratio, and the CAVEATS reading
decides which of those a claim may make.

**G2. Skills for Care workforce intelligence · M — DELIVERED 2026-08-16 (Phase 19, m25)** — adult social care pay
and headcount benchmarks; substance misuse sits between health and social
care, and its workforce market is largely the care workforce. Claim shape:
contextual pay and turnover comparators. **The access shape is the first
task, not the module**: the intelligence service publishes reports, and its
machine-readable access is partial — verify what is fetchable and at what
terms before committing to a module.

**G3. Companies House PSC register · S — DELIVERED Phase 15** — People of Significant Control,
the same API family and key m04 already holds. Claim shape: ownership edges
for the entity graph — "who owns whom" for the 13 providers and, later, for
the universe (F1). No new politeness surface, no new key; the same fetch,
archive and match-basis disciplines as m04.

**G4. GOV.UK content API · S — DELIVERED Phase 15 (`eat_cases`)** — expand m02 to Employment Appeal Tribunal
decisions alongside the current tribunal feed. Same host, same client,
incremental. Claim shape: appeals and their outcomes deepen the tribunal
evidence layer — a decision affirmed or overturned is a materially different
datum from the first-instance judgment.

**G5. Council spend-transparency files · M–L — deliberately not an API — DELIVERED 2026-08-16 (Phase 19, m24)** —
councils publish £500+ spend as files on their own sites, and there is no
central API for them. A harvest module in the m09/m10 shape: discover the
file (depends on B4's full website coverage), fetch, archive, parse line
items. Claim shape: "council X paid provider Y £Z in [period]" — actual
money flows, the strongest procurement evidence the corpus could hold.
Line-item quality varies council to council, so the NULL discipline does
real work here: an unreadable file is a `parse_failures` row and a review
item, not a zero. Also feeds F1 (awardees from spend) and C (claims about
real payments).

**G6. data.gov.uk CKAN API · M — DELIVERED Phase 15 (m19)** — the central open-data catalogue: datasets
searchable by organisation and keyword, with resource URLs, for every council
and department. Claim shape: discovery — which public datasets exist for an
authority and where their resources live. Why it earns its place here: one
module that multiplies four existing items — G5 (many councils catalogue
their spend files there), B4 (website-registry cross-check), W-13 (what each
authority publishes) and the sector universe (F1). Public, no key,
documented, OGL.

**G7. National Living Wage and National Minimum Wage reference · S —
deliberately not an API — DELIVERED Phase 15 (m17)** — the statutory floor as a small annual reference
table from the gov.uk rates pages: one row per year, updated once a year,
citable. Claim shape: the anchor for every "advertised band versus the
floor" statement the campaign will draft. The gate G1 flagged applies here
too: the comparison itself is side-by-side, and any ratio ("X% above the
NLW") is the CAVEATS reading's decision, not the module's.

**G8. Adzuna API · M — conditional — DROPPED 2026-08-16 (Phase 19)** — third-sector and provider job adverts
with advertised pay: the widest non-NHS window on what the sector advertises.
Conditional on two reviews before the module starts: the API's terms
(commercial — robots and rate limits as it sets them), and the reliability
of its parsed salary fields, where an unparseable salary is `NULL` plus a
`parse_failures` row, not a guess. If the terms fail, drop it — m16 and B3
already own the NHS and provider-site halves.
