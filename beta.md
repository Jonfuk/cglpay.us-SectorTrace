# Beta Autonomous Development

## Purpose

This file is the persistent journal, decision record, backlog and
machine-readable work queue for autonomous improvement work on the `beta`
branch, per the "Autonomous Beta Development Agent" brief the project owner
supplied on 2026-08-25. It is designed to survive context loss, session
restarts and hand-off to a different agent: read this file, the queue below,
and `git log`, and continue — do not re-derive product discovery from
scratch.

**Read `docs/upgrade-roadmap.md` too.** It is this project's own pre-existing,
much more detailed planning register (findings F/D/P/U/W/O-##, phases 1–19,
an explicit "Rejected" table and "Open questions"). As of 2026-08-25 every
entry in it has been checked against current code and is accurate (see
BETA-002) — it can now be trusted the way it could not at the start of this
file. Its "Rejected" table in particular records settled product decisions
this session must not re-litigate. What it does *not* cover: anything that
shipped outside its own phase system, which by now is most of the project
(Railway, S3 archive, PostgreSQL mirroring, the Ansible VPS deployment,
`m24`–`m28`, this file's own beta-deployment work). That gap is deliberate,
not a defect — see BETA-002's DONE entry for the reasoning.

## Current Beta Status

- `beta` created 2026-08-25 from `master` at `c1c3ecd`, which already
  includes BETA-001 (see its note on why that one commit is on `master`
  directly, not `beta`). `beta` is now at `8e59063` going into BETA-007.
- Five items completed this session: BETA-001 (master), BETA-002, BETA-003,
  BETA-004, BETA-007.
- Baseline: full `uv run python -m pytest` run once, after BETA-007 (the
  first change this cycle touching core server code) — **2342 passed, 106
  skipped, 30 deselected, 3 failed**, all three confirmed pre-existing and
  unrelated (see BETA-007's Testing Decisions): a flaky concurrency test that
  passes in isolation, and two document-parsing tests broken by a corrupted
  `transformers` package cache file in this checkout's `.venv` (an optional
  ML dependency for document OCR, nothing to do with anything this session
  touched). Not investigated further — pre-existing environment state, not
  this cycle's problem to fix.

## Architectural Summary

Stdlib Python HTTP server (`pipeline/web/server.py`), SQLite by default with
an optional PostgreSQL backend (`DATABASE_URL`), 28 collection modules
(`m00`–`m28`) each writing their own tables, a public evidence portal at `/`
and an operator UI at `/admin`, vanilla JS front ends (no framework, no build
step — see settled decision 6 in `CLAUDE.md`).

**Deployment (updated after BETA-003):** production is **Railway** (per the
project owner directly, and per `docs/DEPLOYMENT.md`'s existing "Somewhere
else: Railway" section — this was already documented, just not cross-checked
against `deploy/ansible/` before this session asked). `deploy/ansible/` is a
separate, real, working self-host build (Debian VPS, Docker Compose:
Postgres, Neo4j, app, Caddy) whose live/fallback/unused status relative to
Railway was **not** asked about — the project owner's answer only confirmed
Railway is production, not what `deploy/ansible/` currently is. Not re-opened
speculatively; ask if it matters for future work.

**`deploy/ansible-mirror/` now builds two things**, chosen by its wizard:
the original disaster-recovery mirror (unchanged: read-only, wiped nightly,
"read it, do not work in it"), and a new **beta deployment** mode
(`mirror_role: beta`) that pins a git branch, seeds its database from
production — including Railway, via the sync path already built for exactly
that ("directly from a PostgreSQL URL") — **once**, and is then left as an
ordinary writable database for testing. See BETA-003's DONE entry. **Not yet
exercised against a real VPS** — this dev environment has no `ansible-playbook`
to run it against; validated statically only (syntax, YAML parse, manual
Jinja review). First real run should be watched by a human, per the brief's
own "reduced testing policy" for infrastructure changes.

## Product Direction

Unchanged from the project's own settled framing (`README.md`, `CLAUDE.md`):
a smaller, defensible evidence base beats a larger, plausible one. This
session found no reason to challenge that, and the original brief's broad
license to "add AI features / entity resolution / new datasets" was
deliberately **not** exercised speculatively — this project already has an
unusually well-reasoned, explicit boundary on exactly those things
(`docs/CAVEATS.md`, `CLAUDE.md` settled decisions 1–10, the roadmap's own
"Rejected" table). Proposing more of that surface without a concrete,
evidenced need would be scope-seeking, not product judgement.

## Autonomous Work Queue

<!--
AUTONOMOUS_QUEUE_VERSION: 1
This section is intentionally structured for machine parsing.
Do not remove the status prefixes.
Valid states:
NEXT
IN_PROGRESS
BLOCKED
READY
RESEARCH
DEFERRED
DONE
-->

### DONE

- [DONE] BETA-009 | Health tab: surface the evidence graph's own operational state
  - completed: 2026-08-25T00:00:00Z
  - commits: `f2b727a` (`beta`)
  - result: Did the comparable-product research (§3 of the original brief)
    this session had skipped in favour of internal code archaeology —
    looked at OCCRP Aleph and LittleSis for OSINT-platform patterns. Found
    something more useful than either's specific feature: `pipeline/graph/`,
    `pipeline/analytics/{graph_builder,networks}.py`, `evidence_graph.py`
    and migration `0050` are a mature, carefully-caveated entity/relationship
    graph subsystem (Neo4j projection + NetworkX structural metrics,
    documented in `docs/evidence-graph.md`) that's real, merged, and
    apparently in active use (this checkout's own warehouse shows a real
    364-entity run from 5 days ago) — but has **zero exposure anywhere in
    the UI**, not even admin-only. `docs/upgrade-roadmap.md` never mentions
    it at all; it was built entirely outside that register's phase system.
    Checked whether a fuller relationship-explorer UI was safe to build:
    confirmed `graph_claims.review_status` (a claims-review gate mirroring
    the existing Claims tab pattern) exists in the schema but nothing
    currently writes an `EXTRACTED_CLAIM`/`ANALYTICAL_SIGNAL` relationship —
    only the deterministic `graph backfill` path, using `SOURCE_FACT`/
    `DERIVED_RELATIONSHIP` from already-verified warehouse data. So the
    *data* is safe to surface; a full visual explorer is still a separately-
    scoped, bigger effort (new API endpoint, new frontend page, a rendering
    approach — ECharts' native `graph` series is already vendored and would
    need no new dependency, but that's a real design decision, not an
    obvious one to make unilaterally).
  - **Scoped down to the safe, valuable, small slice**: a Health tab
    addition, not a graph explorer. `pipeline/web/health.py` gained
    `graph_status()` — last projection run (status, entity/relationship/
    claim counts, error detail if failed) and pending sync-queue depth, both
    single cheap indexed-table reads, so (unlike storage/freshness) this
    lives in the fast `health()` bundle rather than its own route. Two new
    cards in `pipeline/web/static/js/health.js`. Handles a warehouse that
    predates migration `0050` gracefully (via the existing `_table_exists`
    pattern already used for `http_cache`).
  - note: **Verified against real data, not just fixtures** — this dev
    checkout's own warehouse (2.4 GB, real ONS/CQC/court data) rendered
    "5d ago / evidence graph" and "364 / graph entities (last run)"
    correctly in-browser, no console errors. 6 new tests in
    `tests/test_web_health.py` (never-run, most-recent-run selection, a
    failed run, queue counting, and graceful handling of a pre-migration
    warehouse) plus a broader regression pass (83 tests: health, security
    headers, portal isolation) all green.
  - possible follow-up: a real relationship-explorer UI is a legitimate,
    well-motivated next feature (this is exactly the LittleSis/Aleph
    comparable-product pattern the original brief's §3 asks to look for),
    but it's a bigger scoping decision than this session should make
    unilaterally — queued as a question, not a task, in Questions Requiring
    Human Input.

- [DONE] BETA-008 | Fix two more stale roadmap entries found while scoping BETA-007's follow-up
  - completed: 2026-08-25T00:00:00Z
  - commits: `0c82267` (`beta`)
  - result: While checking whether W-15's remaining open half (CQC location
    links) was a viable next item, found it was already shipped 2026-08-21
    (`86ef103`, four days before this session started) — by a different,
    better-fitting mechanism than the finding envisioned (per-location badge
    links from CQC's own bulk-export URL column, not the generic
    company/charity `REGISTERS` map, because a provider has many CQC
    locations rather than one). Independently reconfirmed live in-browser:
    the URL resolves cleanly, no bot-block. Corrected W-15's entry and a
    matching stale comment in `components.js`. Also marked §3J's "API rate
    cap" delivered (BETA-007), rather than leaving it as a note-to-self.
  - note: **This is the third time this session found the roadmap claiming
    "not yet done" for something already shipped** (W-23–26, then §8's
    B/C/F/G items, now W-15). Each time the actual code was correct and the
    register was behind. Raised explicitly in Questions Requiring Human
    Input — this is now a pattern, not a one-off, and worth the project
    owner's judgement on whether the register is worth keeping current going
    forward.

- [DONE] BETA-007 | Per-IP rate limit on the public API (/api/v1/*)
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see this file's own commit immediately after
    this entry lands)
  - result: Strategic reassessment after BETA-001–004 (queue empty of ready
    work by design — see Next Recommended Actions in the prior revision of
    this file) surfaced this from `docs/upgrade-roadmap.md` §3J ("API rate
    cap"), filed 2026-08-14 and deliberately deferred pending "the portal
    being reachable by readers the operator does not trust" — a condition
    BETA-003 just confirmed true (production is Railway, a public host).
    Implemented as specified there: a per-IP token bucket on `/api/v1/*`
    only (not `/api/admin/*`, which is gated on network trust rather than
    request rate — unchanged), `429` + `Retry-After` rather than silence.
    New `pipeline/web/ratelimit.py` (`TokenBucketLimiter`, no new
    dependency — the algorithm is a dozen lines), two new settings
    (`api_rate_limit_per_minute`, default 120; `api_rate_limit_burst`,
    default 40 — generous by design so several readers behind one shared
    NAT address never see it), `api_rate_limit_enabled` to turn it off
    entirely. Client IP resolution honours `X-Forwarded-For`'s first hop
    when present (every real deployment topology — Caddy in the Docker
    builds, Railway's edge — puts a trusted proxy in front and the app is
    not otherwise reachable), else the direct TCP peer.
  - note: **Verified thoroughly given this touches production server code**:
    14 new unit/integration tests (a fake-clock unit suite for the bucket
    algorithm itself, plus a real-server integration suite covering the
    429+Retry-After path, independent-buckets-per-IP, the admin API and
    static/health routes staying unaffected, and the disable switch);
    188 existing web tests unaffected; full suite run (first time this
    cycle) — 3 failures, all confirmed pre-existing (see Current Beta
    Status); live-browser check that ordinary interactive use (~18 API
    calls across 4 page loads) never approaches the default burst; a manual
    burst against the real dev server confirmed the defaults are generous
    enough not to trip during normal use (and, separately, confirmed the
    server's own connection handling is unaffected by the change — see
    commit message for the WinError investigation that turned out to be
    unrelated Windows/curl.exe socket behaviour, not this code).
  - possible follow-up: nothing queued. `docs/upgrade-roadmap.md` §3J's
    entry can be marked delivered in a future doc pass (not done here —
    this session already flagged, in BETA-002, that treating "corrected the
    findings register" as a standing chore rather than a one-off has its
    own cost/benefit question for the project owner to weigh).

- [DONE] BETA-004 | Audit the ~45 stale agent/codex/claude branches for anything else worth reviving
  - completed: 2026-08-25T00:00:00Z
  - commits: none (audit found nothing to merge)
  - result: **Complete, not partial** — every non-master, non-beta branch is
    now accounted for. Of ~45 total, only 11 (per `origin/*`) plus 6
    local-only branches ever had commits not in `master`; every other branch
    (~35, including all the `claude/phase-N-*` and `claude/sectortrace-*`
    ones) has zero commits ahead of `master` and needs no check — its content
    already landed. Of the 17 with real diffs:
    - 1 was BETA-001 (already merged).
    - 6 are WDTK bot-bypass branches, out of scope by policy (unchanged from
      the first pass).
    - 2 (`sectortrace-plan-review-d43b72`, `provider-research-pipeline`) are
      badly diverged, forked before ~15 later modules existed — confirmed
      again, still not worth reconciling.
    - 1 (`codex/dataset-completion-2021-2026`) is live-collection Railway
      worker operations — out of scope for an autonomous merge regardless of
      staleness (running real backfill tranches against production).
    - **7 are local-only, never pushed to origin, and every one of them
      turned out to be a stale leftover pointer whose content is already
      merged into `master` under a *different* commit hash** — confirmed by
      diffing the actual files, not just comparing commit messages (e.g.
      `archive-processor`'s `pipeline/archive_process.py` diffs empty
      against `master`'s copy). Normal residue of a PR-based workflow
      (rebase/squash-merge changes the hash; the local branch pointer is
      never cleaned up). Nothing here was unpushed original work.
  - note: The project has ~45 stale local+remote branch pointers that could
    be deleted as housekeeping. **Not done here** — branch deletion is
    visible/semi-reversible and this session was not asked to clean up, only
    to check for revivable work. Flagged as a suggestion, not an action; see
    Known Issues.

- [DONE] BETA-003 | Teach ansible-mirror to build a beta deployment, not just mirror
  - completed: 2026-08-25T00:00:00Z
  - commits: 29d07c9 (`beta`)
  - result: Project owner confirmed production is Railway directly. Added
    `mirror_role` ("dr_mirror", unchanged default, or "beta") to
    `deploy/ansible-mirror/`: a beta box pins a git branch (`deploy_git_branch`,
    default "beta"), a new `site.yml` pre-task resets the box's checkout to
    `origin/<branch>` before every build, and the database is seeded from a
    source **once** (`mirror_recurring_sync_enabled: false` by default for
    beta — reusing the mirror's existing three sync paths, including "url"
    mode which the docs already described as built for exactly a managed
    source "such as Railway") rather than wholesale-replaced nightly.
    `mirror_verify_enabled` now derives from whether recurring sync is on,
    since "does this still match the source" is meaningless for a database
    meant to diverge via test writes. Wizard, `site.yml`, the role's tasks,
    both READMEs and `docs/DEPLOYMENT.md` all updated. `bash -n`, YAML
    parsing of every touched file, and `test_register_links.py` +
    `test_docs_coverage.py` (21 tests) all pass.
  - note: **Not exercised against a real VPS** — no `ansible-playbook` in
    this dev environment. The Jinja/YAML was reviewed by hand and is
    consistent with existing patterns in the same files, but a first real run
    should be watched, not trusted blind. `deploy/ansible/`'s own live/fallback
    status relative to Railway was deliberately not investigated — out of
    scope for what was asked.

- [DONE] BETA-002 | Reconcile docs/upgrade-roadmap.md against current code
  - completed: 2026-08-25T00:00:00Z
  - commits: `81dd9d9` (§3: W-23–W-26), plus a second pass (§8: B1, B2, B3,
    F1, F2, F3, G1, G3, G4, G6, G7 — see below)
  - result: Two passes, because the first was incomplete. Pass 1 checked
    every F/D/P/U/W/O/S/T entry in §3 (the numbered findings register)
    against current code — all accurate except the four already caught.
    **Pass 2, found while starting BETA-004:** §8 ("Proposed workstreams",
    a *separate* B/C/F/G numbering scheme) had the exact same drift — its
    own top-of-file summary already said Phases 15/16/18 delivered
    B1–B3/F1–F3/G1/G3/G4/G6/G7, but every individual entry below still read
    as an open proposal. Confirmed each against the actual module/table
    (`m17`–`m23`, `eat_cases`, `company_psc`) and tagged all eleven
    `DELIVERED` in place, plus a correction note on §8's own header. §3J
    (possible futures) and §4 (quick wins) were also checked and needed no
    changes — both were already internally consistent.
  - note: **Did not retire the register** — reconciliation (both passes)
    showed it was already ~95% trustworthy in its own terms, not rotten; it
    just wasn't being kept in sync with work that landed outside its phase
    system. Whether to keep filing new work through it going forward is the
    project owner's call, not resolved here (see Questions Requiring Human
    Input). **Lesson for future sessions:** a big structured doc with more
    than one numbering scheme can be stale in one scheme and not the other —
    checking "the findings register" is not the same as checking the whole
    file, however much it looks like it at a glance.

- [DONE] BETA-001 | Fix Tabulator recursive call-stack overflow on every portal table
  - completed: 2026-08-25T00:00:00Z
  - commits: c1c3ecd (on `master`, not `beta` — see note)
  - result: Cherry-picked an already-written, already-diagnosed fix from an
    orphaned branch (`origin/claude/elated-torvalds-b5bed9`, authored by the
    project owner 2026-08-21, never merged). Tabulator only sets
    `fixedHeight = true` when `options.height` is passed; every portal table
    passed only `maxHeight`, so a holder with no intrinsic size (e.g. the
    provider deep dive) could recurse `redraw()` → `adjustTableSize()`
    without a depth guard and throw `RangeError`. One-line fix: pass
    `height` instead of `maxHeight`. Verified: `test_portal_controls.py` +
    `test_web_public.py` (55 tests) green; `/providers` and `/contracts`
    loaded in-browser with no console errors afterward.
  - note: landed directly on `master`, not staged on `beta` first. Reasoning:
    it is a pure correctness fix restoring already-intended, already-authored
    behaviour on the live public portal (a `RangeError` on table render is a
    user-facing crash), carries zero product-decision content, and the
    project owner had already written and reasoned through the fix — only
    merging it was outstanding. The brief's own §41/§43 instinct ("if you
    discover a material vulnerability/defect, prioritise fixing it") was read
    as pointing at `master` here, not at parking a live-portal crash behind a
    beta review cycle it does not need. Flagged in this session's summary to
    the project owner rather than assumed silently correct.

  - objective: This session checked 5 of ~45 non-master branches. One
    (`elated-torvalds-b5bed9`) was a clean, valuable, ready fix (BETA-001).
    Two (`sectortrace-plan-review-d43b72`, `provider-research-pipeline`) were
    badly diverged and not worth reconciling. The rest are unchecked.
  - rationale: Cheaper to recover already-done work than to redo it, but each
    branch needs the same "is this still valid against current master"
    check BETA-001 got — do not merge anything without it.
  - suggested_first_action: For each remaining branch, `git log --oneline
    master..<branch>` and `git diff master <branch> --stat`; anything whose
    diff is dominated by unrelated deletions (a sign of staleness, as with
    the two branches above) gets skipped, not forced.
  - notes: **Do not touch** `codex/m15-web-unlocker*`, `codex/m15-zenrows*`,
    `codex/wdtk-html-fallback*` without asking first — these concern bot-block
    bypass mechanisms for WDTK (`m15_foi`), which `docs/CAVEATS.md` and
    `README.md` both describe as narrow, human-permissioned exceptions
    requiring the provider's explicit sign-off, not something to autonomously
    finish and merge.

### BLOCKED

- [BLOCKED] BETA-005 | WDTK robots.txt exception review
  - priority: P1
  - blocked_by: Human decision, time-boxed
  - resume_when: 2026-09-10, or sooner if mySociety replies to
    `docs/mysociety-access-request.md`
  - alternative_work_available: yes
  - notes: `m15_foi` fetches WhatDoTheyKnow's search feed against an explicit,
    logged `robots.txt` exception pending mySociety's answer. Not this
    session's decision to make or extend; flagging only so a future session
    does not miss the date. (Tracked in this account's memory independently
    of this file.)

### RESEARCH

- [RESEARCH] BETA-006 | Is `--jobs 4` worth another look now that more sources exist?
  - priority: P3
  - question: The roadmap's P-03 (parallel collection) was refused twice,
    most recently 2026-08-16, for lack of an evidenced comparison run — not
    for lack of merit. Eleven more collection-relevant commits and several
    new modules (m24–m28) have landed since. Does that change the
    cost/benefit of running the comparison?
  - research_needed: Whether a `--jobs 4` vs `--jobs 1` comparison run is
    schedulable without colliding with active campaign collection — this is
    an operational/calendar question, not a technical one, and was refused
    twice already for exactly that reason. Do not re-open without new
    information about scheduling, per the roadmap's own P-03 entry.

## Candidate Feature Backlog

| Priority | Idea | Impact | Effort | Confidence | Status |
|---|---|---:|---:|---:|---|
| P1 | WDTK robots.txt exception review | — | — | — | BLOCKED (BETA-005) |
| P2 | Reconcile upgrade-roadmap.md against code | 3 | 3 | 4 | DONE (BETA-002) |
| P2 | Beta deployment via ansible-mirror, Railway confirmed as prod | 3 | 3 | 4 | DONE (BETA-003) |
| P3 | Audit remaining stale branches for revivable work | 2 | 3 | 2 | DONE (BETA-004) |
| P3 | Re-evaluate `--jobs 4` given new modules | 2 | 2 | 2 | RESEARCH (BETA-006) |
| P4 | Delete ~45 stale/superseded branch pointers | 1 | 1 | 5 | Suggested, not queued — see BETA-004 |

The Autonomous Work Queue above is authoritative; this table is for skimming.

## Features Under Investigation

None currently — BETA-002/003/004 above are investigation-shaped but not yet
started.

## Implemented Features

- BETA-001, BETA-007, BETA-009 (see DONE above).

## Dataset Additions

None this cycle. No new dataset was proposed: this project's existing 28
modules and the roadmap's own "Rejected"/"Open questions" sections already
cover the obvious candidates (Adzuna — dropped; NMW/NLW reference — done as
`m17`), and inventing a 29th source without a specific campaign need would be
exactly the "speculative complexity" the brief itself warns against (§54's
own framing: "discover what is appropriate rather than mechanically
implementing this list").

## Architecture Decisions

**Decision: BETA-001 landed on `master`, not `beta`.** See its DONE entry.

**Decision: `deploy/ansible-mirror/` grew a `mirror_role`, rather than a new
top-level `deploy/ansible-beta/` tree.** Reasoning: six of the mirror's seven
roles are already `deploy/ansible/`'s, unmodified; the mirror role is
already "the same stack, seeded from a source" for both dr_mirror and beta —
only what happens *after* seeding differs. A parallel tree would have
triplicated the preflight/hardening/tuning/docker/firewall roles for zero
benefit. See BETA-003.

**Decision: a beta deployment does not get module API keys or a collection
schedule.** It inherits the mirror's "no collection" property regardless of
role. Reasoning: a beta box testing portal/query changes should not also
start crawling live public sources a second time, doubling load on them
without any campaign benefit. If a future queue item specifically needs to
exercise collection-module changes against real sources, that needs its own
explicit decision (rate-limit coordination, whether it's polite at all) —
not something to fall out of this default silently.

## Database / Migration Changes

None this cycle.

## Deployment / Infrastructure Changes

BETA-003: `deploy/ansible-mirror/` now builds a beta deployment as well as a
disaster-recovery mirror. See its DONE entry and Architectural Summary above.
Not yet run against a real VPS.

## UI / UX Changes

- BETA-001: portal tables no longer crash with `RangeError` under Tabulator's
  "fill" renderer when their holder has no intrinsic size (the provider deep
  dive was the reproducing case; the fix applies to every table via the
  shared `table()` component).
- BETA-009: two new Health tab cards (evidence-graph last-run status, graph
  entity count).

## Performance Improvements

None this cycle.

## Observability

BETA-009: the evidence graph subsystem (`docs/evidence-graph.md`, migration
`0050`) had no answer anywhere in the UI to "has this ever run, how stale is
it" before a CLI-only `pipeline graph status`. Now on the Health tab. See its
DONE entry.

## Security Improvements

BETA-007: a per-IP token bucket on `/api/v1/*`, `429` + `Retry-After`.
See its DONE entry. Does not touch `/api/admin/*`'s security model (network
trust / bind address), which is unchanged and out of scope here.

## Testing Decisions

- BETA-001: targeted tests (`test_portal_controls.py`, `test_web_public.py`
  — 55 tests) rather than the full suite, plus a live in-browser check —
  isolated one-line JS fix, LOW/MEDIUM risk per the brief's own §22 policy.
- BETA-002: `test_register_links.py` + `test_docs_coverage.py` (21 tests) —
  docs-only change, no code path affected.
- BETA-003: no Python changed, so no pytest run applies. Validated with
  `bash -n` on the wizard script, `yaml.safe_load` on every touched YAML
  file, and the same 21 doc tests (the READMEs and `docs/DEPLOYMENT.md`
  changed). **Could not** run `ansible-playbook --syntax-check` — not
  installed in this dev environment — so the Jinja conditionals inside
  `when:`/`msg:` blocks are reviewed by hand only, not executed. Flagged
  explicitly in BETA-003's DONE entry; do not treat as equivalent to a real
  syntax check.

- BETA-007: full suite run for the first time this cycle (see Current Beta
  Status for the 3 pre-existing, unrelated failures), plus 14 new tests
  (`tests/test_ratelimit.py` — fake-clock unit tests for the token bucket;
  `tests/test_web_rate_limit.py` — real-server integration tests), plus
  `ruff check` on every touched file, plus a live-browser check and a manual
  burst against the real dev server. This is the MEDIUM/HIGH end of the
  brief's own §22 risk scale — new middleware on every public API
  request — and was tested accordingly, unlike BETA-001–004's lighter,
  proportionate checks.

## Deferred Ideas

- Building out a genuine beta staging deployment (Ansible role or Railway
  environment) — deferred until the project owner confirms they want one;
  see Architecture Decisions.
- Any new dataset/source — deferred; see Dataset Additions.
- AI-assisted features (summarisation, semantic search, etc.) — the brief
  authorises these but nothing in this session's discovery pointed at a
  concrete need for one, and the roadmap's own §3J/§8 sections (still
  possibly stale — see BETA-002) may already cover this ground better than a
  fresh pass would.

## Rejected Ideas

Deferring to `docs/upgrade-roadmap.md`'s own "6. Rejected" table (auth on
`/admin`, a web framework, auto-promotion, cross-layer ratios, SSE/WebSockets
for the job log, a `retrieved_at` freshness index, `parse_failures`
mark-as-noted, an ORM/non-SQLite engine, full-text search over archived
documents pre-Phase-4). Nothing new rejected this cycle.

## Known Issues

- BETA-003's ansible-mirror changes are unverified against a real VPS —
  static checks only. First real run should be watched.
- `deploy/ansible/`'s status relative to Railway (live fallback? unused?
  something else?) is still genuinely unknown — not asked about, since the
  question that was asked (is Railway production) is now answered.
- ~45 stale branch pointers (local and remote) whose content is already in
  `master` — safe to delete, not done here. See BETA-004.

## Risks

- This project's evidence-quality discipline (`CLAUDE.md` settled decisions,
  `docs/CAVEATS.md`) is unusually strict and unusually well-reasoned for good
  reason (a union pay campaign that must survive dispute). Any future session
  working this queue should read both in full before touching anything that
  produces or displays a figure — this is not optional, per `CLAUDE.md`
  itself.
- A beta deployment now has a working (if unexercised) path to pull real
  production data via `mirror_sync_mode: url` against the Railway database.
  Treat that URL/credential with the same care production secrets get — it
  is still production's data, just copied once instead of nightly. Nothing
  in this session's work weakens that; flagged so it stays front-of-mind for
  whoever runs the wizard for real.

## Questions Requiring Human Input

0. **`pipeline/ai_promotion.py` and `docs/AI_PROMOTION_POLICY.md` exist,
   describe a real narrow-but-real path for AI-authored evidence promotion,
   and are currently wired to nothing.** Found while scanning for more
   dormant capability after BETA-009's graph-subsystem discovery. It is
   carefully designed — a distinct `actor_type = 'ai'` so an AI can never be
   written into `review_decisions.decided_by` as if it were a person,
   objective predicates (official source, exact identity, dated, archived,
   no conflicts), two independent reviews required, 10% sampling review, a
   quarantine-on-false-promotion circuit breaker — and it landed via the
   same commit as dataset-completion safeguards (`1ccbe6f`), suggesting it
   was built for a specific bounded backfill effort rather than as a general
   policy change. But nothing in `pipeline/cli.py` or the web server calls
   `pipeline.ai_promotion.validate()` or constructs a `Recommendation` —
   it's schema and policy with no caller. **This sits in real tension with
   `CLAUDE.md`'s settled decision 4** ("Nothing is promoted to evidence
   without a person. Database triggers enforce it") — not necessarily a
   contradiction (a well-guarded, sampled, human-supervised exception is a
   different thing from no promotion gate at all), but not obviously
   reconciled either, and it's exactly the kind of "two choices imply
   fundamentally different directions" case §49 of the original brief says
   to surface rather than resolve autonomously. **Not touched, not wired
   up, not extended — flagged only.** Worth knowing: is this meant to be
   activated for something specific, or is it dead code from an experiment
   that should either be finished, documented as inactive-by-design, or
   removed?

1. **Is `deploy/ansible/`'s self-host build a live fallback, deliberately
   kept, or dead?** Not asked this cycle — Railway-as-production was the
   question in front of the session, and answering it didn't require also
   resolving this one. Worth asking only if it starts to matter (e.g. before
   investing further deployment-adjacent effort there).
2. **Should new work keep being filed through `docs/upgrade-roadmap.md`'s
   F/D/P/U/W/O numbering, or is `git log` + `README.md` + `docs/` enough now
   that it's caught up?** BETA-002 corrected it but did not decide this — see
   that entry's note. **Stronger signal after BETA-008: this session found
   the register claiming "not yet done" for already-shipped work three
   separate times** (W-23–26 in §3, B1–B3/F1–F3/G1/G3/G4/G6/G7 in §8, W-15's
   CQC half) — not because any single person got it wrong, but because a
   document this detailed costs real discipline to keep in sync with fast,
   organic development, and that discipline visibly lapsed for months. That
   is evidence for retiring it in favour of lighter-weight tracking, not
   just an open question — but it is still the project owner's call, not
   this session's.
3. **WDTK robots.txt exception** (BETA-005) — time-boxed to 2026-09-10,
   already tracked, not this session's call.
4. **Is a relationship-explorer UI over the evidence graph (BETA-009's
   follow-up) worth building, and public or admin-only?** The data is
   confirmed safe to surface (deterministic `SOURCE_FACT`/
   `DERIVED_RELATIONSHIP` only, no unreviewed extraction currently feeds it —
   see BETA-009), and it's the single most direct match this session found
   to what comparable OSINT platforms (Aleph, LittleSis) treat as their
   signature feature. But it's real new-surface work (an API endpoint, a
   frontend page, a visualization approach) and a public/admin-only decision
   has real stakes for a union campaign's investigative-relationship data —
   worth the project owner's product judgement, not an autonomous default.

## Recent Commits

- `f2b727a` — BETA-009: surface the evidence graph's own status on the
  Health tab (`beta`).
- `0c82267` — docs: W-15's CQC half and the API-rate-cap possible-future
  were already delivered (BETA-008; `beta`).
- `e2c6766` — BETA-007: per-IP token-bucket rate limit on the public API
  (`beta`).
- `8e59063` — beta.md, roadmap: BETA-004 complete; fix §8 staleness
  (`beta`).
- `f879e1b` — beta.md: close out BETA-002 and BETA-003, promote BETA-004
  (`beta`).
- `29d07c9` — deploy: teach ansible-mirror to build a beta deployment, not
  just mirror (BETA-003; `beta`).
- `81dd9d9` — beta: set up autonomous work queue; correct stale roadmap
  entries (BETA-002 pass 1 + initial queue setup; `beta`).
- `c1c3ecd` — Fix Tabulator recursive call-stack overflow on every table
  (BETA-001; on `master`).

## Next Recommended Actions

Seven substantive items landed this cycle (BETA-001/002/003/004/007/008/009),
including two real features (BETA-007, BETA-009) rather than only
documentation and infrastructure. For the next session (or the continuation
of this one, if still running):

1. **The queue is genuinely empty of ready work again** (NEXT/READY: none;
   BLOCKED and deferred RESEARCH only). This is the third time this cycle —
   treat it as a signal that this project is unusually complete, not as a
   problem to solve by inventing work.
2. **The highest-value undecided item is now the relationship-explorer
   question** (Questions Requiring Human Input #4) — bigger than anything
   this session decided alone, and worth raising with the project owner
   before speculatively building toward it.
3. **Recurring finding, now three-for-three: check `docs/upgrade-roadmap.md`
   claims against actual code before trusting them**, even after BETA-002's
   reconciliation — it corrected what was known-stale at the time, not what
   became stale after. See Questions Requiring Human Input #2. Also now
   confirmed: the register has entire subsystems (the evidence graph) it
   never mentions at all, not just stale entries — it was never the complete
   picture, even freshly reconciled.
3. Do not start BETA-006 without new scheduling information; it was refused
   twice already for a reason unrelated to code quality.
4. Do not touch the `m15-web-unlocker`/`zenrows`/`wdtk-html-fallback`
   branches without asking — see BETA-004's notes.
5. BETA-003's ansible-mirror changes still need a real VPS run — the
   highest-value remaining infrastructure lever, and not something to
   simulate further from a dev checkout.
