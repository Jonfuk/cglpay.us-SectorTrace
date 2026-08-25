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
an optional PostgreSQL backend (`DATABASE_URL`), 31 collection modules
(`m00`–`m30`) each writing their own tables, a public evidence portal at `/`
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

- [DONE] BETA-015 | Module 30: statutory homelessness (H-CLIC) snapshot
  - completed: 2026-08-25T21:40:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: BETA-014's own flagged follow-up, built this cycle. Source
    researched directly against the live GOV.UK page
    (`live-tables-on-homelessness`), not assumed from docs — one evergreen
    page attaching one file per quarter (closer to m29's single-page
    discovery than m13's per-publication search). Only Table A1 (households
    by initial-assessment outcome — the flagship "statutory homelessness"
    count) is read, out of 40+ tables in the workbook, the same
    one-table-done-properly discipline m29 applied.
  - **Found and fixed a real parsing bug while verifying against actually
    downloaded files, before writing the parser**: the `sheet_rows()`
    pattern this pipeline's other ODS modules (m13, m29) use walks only
    `<table:table-cell>` elements, silently skipping
    `<table:covered-table-cell>` elements — invisible in m13/m29's own
    sources, which have no genuine multi-column-spanning merged cells, but
    H-CLIC's older-era files do (merged group-header cells), and skipping
    them shifts every later column in that row left by however many columns
    the merge spanned. Fixed locally in the new module only — not touched in
    m13/m29, whose own inputs never hit it.
  - **The sheet layout is not stable across the 2017–2026 series** — an
    older multi-row merged-header block and a newer flat single-header-row
    form both appear. `locate_a1_columns` resolves either by keyword
    (concatenating each column's own header text across all header rows,
    excluding prose rows like the title by requiring ≥2 populated cells),
    claiming fields in a specific order (relief and prevention before the
    total, which is claimed before its own "of which" sub-breakdowns can be)
    so a parent total's own sub-columns — which repeat the parent's
    group-label text as a prefix in the modern shape — cannot steal its
    claim. Verified by hand against **four real downloaded quarters**
    spanning both shapes and both file formats (2019 Q4 ods, 2023 Q1 ods,
    2024 Q1 xlsx, 2026 Q1 ods) before any test was written: every column
    position resolved correctly and matched MHCLG's own published
    England-level totals exactly.
  - **A second real finding from that same verification, not anticipated
    going in**: region (`E12…`) and England (`E92…`) aggregate rows in this
    source carry genuine ONS codes in the authority-code column, unlike
    m29's source, which marks them with a `[z]` placeholder instead. m29's
    own `^E\d{8}$` filter would have silently mis-stored a region as if it
    were a local authority here; tightened to the local-authority prefix set
    only (`E06`–`E10`, m13's own `local_authority` classification) for this
    module. A third finding, documented as its own `docs/CAVEATS.md` bullet
    rather than silently handled: in the older table layout,
    `not_threatened_no_duty` is the sole combined "no duty owed" total (no
    separate withdrew/not-eligible breakdown existed yet), while in the
    newer layout it is only the "not threatened" reason, one of three
    additive columns — confirmed against real published totals from both
    eras (72,290 − 68,520 = 3,770 exactly for Oct–Dec 2019; 4,130 + 3,600 +
    610 ≈ 92,200 − 83,850 for Jan–Mar 2026, the small remainder being
    MHCLG's own rounding).
  - Follows the established module conventions exactly:
    `pipeline/modules/m30_statutory_homelessness.py` (registered,
    auto-discovered), migration `0060` (SQLite + PostgreSQL),
    `pipeline/licences.py` + `components.js`'s mirrored copy (OGL v3.0),
    `docs/SOURCES.md`, `README.md`'s module table and Wave 1, and a
    `docs/CAVEATS.md` entry covering: the comparator-only rule (same as
    m29), the single-table scope boundary, silent overwrite on revision (a
    "(revised)" edition replaces the earlier figures on the natural-key
    upsert `(ons_code, quarter_start)` — this pipeline always prefers a
    revised edition where both are attached), `[x]`/`[z]`/`[n]`/`[c]`
    placeholder handling (`[c]` — data suppression — is new; m29's source
    does not use it), the pre-2017 `.xls` coverage gap (no reader without a
    new dependency, a bounded and documented boundary not a silent one), and
    the `not_threatened_no_duty` dual-meaning finding above. Also fixed the
    now-stale line in m29's own caveat entry that said statutory
    homelessness was "a separate MHCLG collection this pipeline does not yet
    read" — cross-references Module 30 now.
  - note: **Verified as thoroughly as this session safely could, including
    against real full downloaded workbooks, not only hand-built fixtures.**
    33 new unit tests on the pure parsing functions (fixtures built from the
    real header/data text of both shapes, locked to the exact column
    positions confirmed against the real files; title-regex inclusion and
    exclusion for every distinct attachment title pattern actually seen on
    the live page — financial-year summaries, Multiple Disadvantage tables,
    and "- Accessible" duplicates all correctly excluded; all four
    placeholder values null out; region/England/`-` rows correctly excluded
    from extraction). Separately re-ran the locator directly against all
    four downloaded real workbooks (not just fixtures) and confirmed every
    resolved value against MHCLG's own published England totals by hand.
    All five cross-cutting coverage guards BETA-014 found were touched again
    here and all caught something real: `tests/test_since_handling.py`,
    `tests/test_integration_smoke.py`, `tests/test_migration_equivalence.py`
    (migration count), `tests/test_progress_coverage.py` (module count *and*
    the progress-reporting/registration-correctness checks — see below),
    `README.md`'s module table. Full suite, run clean and uninterrupted:
    **2419 passed, 106 skipped, 32 deselected, 2 failed** — both the same
    pre-existing `transformers`/docling `UnicodeDecodeError` BETA-014
    already confirmed unrelated (reproduced again in isolation to be sure).
  - **A genuine false alarm worth recording, not because it affected the
    result but because it could confuse a future session**: an earlier full-suite
    run (started before a comment-only docstring edit) showed two spurious
    failures — `MODULE_REGISTRY['m30_statutory_homelessness']` appearing to
    resolve to a helper function rather than `run`. Root cause: editing the
    module's source file while a long-running background pytest process was
    mid-suite shifts line numbers on disk after Python has already cached
    the function's old `co_firstlineno` at import time; `inspect.getsource`
    re-reads the file from disk on each call, so it briefly read the wrong
    function's text at the old line offset. Confirmed as an artifact, not a
    real bug, by re-running those two tests in isolation (passed) and then a
    second full suite with no concurrent edits (clean). Lesson for future
    sessions: do not edit a module's source while a background test run
    covering it is still in flight.
  - **What this session could not verify**: an actual live fetch-parse-write
    run, for the same reason as every dataset addition this cycle — this
    checkout's `.env` points at live Railway production (see Environment
    Note).
  - possible follow-up: other H-CLIC tables (temporary accommodation in
    particular — TA1 — is arguably as substance-misuse-relevant as A1, and
    was seen and understood during this module's own research) are a
    plausible Module 31, not started. Not requested by the project owner;
    flagged as a discovered opportunity only.

- [DONE] BETA-014 | Module 29: rough sleeping snapshot (new dataset)
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: Project owner asked for homelessness/rough-sleeping/crime data
    as local-authority-level comparators, given the well-documented overlap
    with substance misuse. Researched all three properly before building
    anything (§16 of the original brief's Dataset Expansion Authority
    checklist): confirmed real, current, official sources —
    - **Rough sleeping snapshot** (MHCLG): annual, LA-level, one evergreen
      GOV.UK page whose single ODS republishes the *entire* 2010-to-current
      series every edition (verified by downloading and parsing the real
      file: 296 authorities × 16 years, 4,736 rows). Cleanest shape, most
      direct substance-misuse link — **built this cycle**.
    - **Statutory homelessness (H-CLIC)**: official, quarterly, LA-level
      ("Live tables on homelessness") — same shape family as `m13`'s MHCLG
      budgets. Confirmed viable, **not built this cycle** — one module per
      cycle done properly beats two done fast; queued as a natural
      follow-up, not started.
    - **Crime data** (`data.police.uk`): the only real option found is
      street-level/LSOA, not local-authority-level — using it as an LA
      comparator would need this pipeline's own LSOA→ONS-code crosswalk, a
      materially bigger and more sensitive undertaking (small-area crime
      data carries its own care-in-handling questions this project hasn't
      had to face yet). **Deliberately not built** — flagged as a real
      finding, not a task, in Questions Requiring Human Input.
  - **Module 29** follows the established module conventions exactly:
    `pipeline/modules/m29_rough_sleeping.py` (registered, auto-discovered),
    migration `0059` (SQLite + PostgreSQL), `pipeline/licences.py` +
    `components.js`'s mirrored copy (OGL v3.0), `docs/SOURCES.md`,
    `README.md`'s module table and Wave 1, and a `docs/CAVEATS.md` entry
    that leads with the caveat the project owner's own framing needed most:
    **methodology is not standardised between authorities** (each chooses
    its own counting approach and date), so a raw comparison between two
    authorities' figures may reflect a difference in method, not only a
    difference on the street — and, per this project's first rule, **never
    combined or computed against the sector's own substance-misuse
    evidence**, comparator only, side by side.
  - note: **Verified as thoroughly as this session safely could.** Real
    MHCLG file downloaded and parsed directly to confirm the actual sheet
    shape (`Table_1_Total`, `Table_5_Rates`, header row, year columns,
    `[x]`/`[z]`/`[n]` placeholders, region/England aggregate rows correctly
    excluded) before a line of the parser was written — not guessed at from
    documentation. 21 new tests on the parsing functions (the same
    "test the pure functions, not the odfpy I/O layer" convention `m13`
    already established), all passing against realistic fixture rows.
    Five separate offline coverage guards this addition touched (migration
    count, README module list, per-module licence in two mirrored places,
    the integration-smoke module-coverage spec, the progress-reporting and
    `--since`-declaration guards) all found and fixed — each caught a real
    doc/registration gap the way it's designed to. Full suite: 2384 passed,
    2 pre-existing unrelated failures (confirmed for the third time now).
  - **What this session could not verify**: an actual live fetch-parse-write
    run. This checkout's own `.env` has `DATABASE_URL` pointing at the live
    Railway production database (see Environment Note) — running
    `./start.sh run m29_rough_sleeping` for real would both make a live
    request under the project's identity and write to production without
    explicit authorisation for either. Not done. The parsing logic is
    verified against the real source file directly; the fetch-and-write
    integration (HTTP client wiring, `db.upsert`, commit behaviour) is
    exercised by the same code paths `m13`/`m18` already use in production,
    but a first real run of *this* module specifically should be watched,
    ideally against a local SQLite warehouse or `--dry-run`, not assumed
    correct from unit tests alone.
  - possible follow-up: statutory homelessness (H-CLIC) as Module 30, same
    shape family as this one and `m13`. Crime data needs a scoping decision
    first (see Questions Requiring Human Input) — not a next action yet.

- [DONE] BETA-013 | Health tab: surface the document-analysis layer's own status
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: The "CLI-only capability with no UI" pattern that found the
    evidence graph (BETA-009) found a second, larger subsystem on the same
    scan: `pipeline/documents/` — inspection, OCR (OCRmyPDF), parsing
    (Docling), classification and quality scoring, documented in
    `docs/document-analysis.md` (migration `0053`) — with a working
    `pipeline documents search` command and zero UI exposure anywhere,
    public or admin. Explicitly scoped in its own doc as *not* creating
    claims, promoting evidence, or calling an AI service — a genuinely safe
    subsystem to surface status for, unlike the AI-promotion question.
  - **Scoped to the same safe slice as BETA-009, deliberately not more**:
    a Health tab card (`health.document_status()` — registered, parsed,
    failed, and total document counts, all cheap `COUNT(*)` reads), not a
    document search UI. **Explicitly did not build search exposure this
    cycle**: `pipeline documents search` reads parsed text from raw archived
    documents, which can include PFD reports and other sources with
    `restricted_` personal-data counterparts — unlike the relationship
    explorer's deterministic contract-award data, a search surface here
    needs its own careful check of what a search result could reveal before
    any UI is built around it, admin or public. Flagged as a discovered
    opportunity, not built.
  - note: **Verified against real production data** — this checkout's own
    warehouse shows "13,248 documents parsed of 13,283" (99.7% success),
    confirming the subsystem is in heavy real use, not dormant. 3 new tests
    (empty state, counts by parse outcome, graceful handling of a
    pre-migration warehouse); 86-test regression pass (health, security
    headers, portal isolation) green; live-browser confirmation, no console
    errors beyond the same unrelated environmental noise seen throughout
    this session.
  - possible follow-up: a document-search UI (admin first) is plausible and
    the backend already exists, but needs an explicit answer to "what could
    a search result surface" before any UI work — queued as a question, not
    a task, in Questions Requiring Human Input.

- [DONE] BETA-012 | Entry-point links into the relationship explorer
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: BETA-010's own follow-up note, done same cycle rather than
    deferred. The authority page's hero now links "Who it commissions →" to
    `#/relationships?ons_code=...`; the provider deep dive's hero links
    "Who commissions it →" to `#/relationships?provider_key=...` — the same
    entry-point pattern W-11's compare view already uses from both pages
    (`#/compare?ons_code=...` / `#/compare?provider_key=...`), placed
    directly alongside it.
  - note: Verified live against real production data (this checkout's
    `DATABASE_URL`, see Environment Note) — both links carry the correct
    query parameter (`ons_code=E08000025`, `provider_key=change_grow_live`),
    and a direct navigation to each resulting URL renders "Showing:
    Birmingham" / the relationships page centred correctly. 76 existing
    tests (authority, public, portal isolation) unaffected — no test pins
    the exact entry-point link text, so none needed updating.

- [DONE] BETA-010 | Public relationship explorer over the evidence graph
  - completed: 2026-08-25T00:00:00Z
  - commits: (pending push — see the commit immediately following this
    entry in `git log beta`)
  - result: New dedicated portal section (`#/relationships`), scoped
    exactly as decided in the project owner's interview: provider↔authority
    commissioning relationships only, a one-hop neighbourhood centred on
    whichever entity the reader picks — not a whole-corpus map, which would
    invite exactly the size/importance/centrality reading this pipeline
    never asserts. New `public_queries.relationships()` reads only
    `entities`/`entity_relationships`/`evidence_records` (never Neo4j,
    which is an explicitly disposable projection of the same rows) filtered
    to `predicate = 'AWARDED_TO'` and `derivation_type IN ('SOURCE_FACT',
    'DERIVED_RELATIONSHIP')` — `REGISTERED_AS` (ownership) and
    `EXTRACTED_CLAIM`/`ANALYTICAL_SIGNAL` (BETA-009's not-yet-built
    extraction pipeline) explicitly excluded, not by their current absence.
    New frontend page (`relationships.js`) with typeahead pickers (reusing
    the compare page's pattern), an ECharts `graph`-series force diagram
    (already-vendored, no new dependency), and — because a force diagram
    has no accessible text equivalent — a citable table beneath it with
    per-edge provenance (source URL, retrieval date, licence), matching
    "everything is citable" exactly as every other page does. New caveat
    (`commissioning_relationship`) pinned above the diagram. Wired into the
    frozen route/asset lists in `tests/test_portal_isolation.py`, the `/api`
    documentation page, and the `<noscript>` block — also fixed that page's
    stale "nothing here is rate-limited" line left over from before
    BETA-007.
  - note: **Verified against real production data end-to-end, not just
    fixtures** — live in-browser, Nottinghamshire's real commissioning
    relationships to Change Grow Live and Turning Point rendered correctly
    as both the force diagram and the citable table, with real Find a
    Tender provenance and OGL licensing, no console errors. 9 new backend
    tests (both direction of lookup, an entity with no matched relationship
    returns an empty neighbourhood rather than a 404, an unknown entity is
    a clean 400, ownership and unreviewed-extraction edges are excluded
    even when present in the data, graceful handling of a warehouse that
    predates the graph tables). Full suite: 2358 passed, 2 pre-existing
    failures unrelated to this change (confirmed twice now, see BETA-007's
    entry for the first confirmation).
  - follow-up delivered same cycle: see BETA-012.

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

### NEXT

- [NEXT] BETA-016 | Module 31: H-CLIC temporary accommodation (TA1)
  - priority: P3
  - impact: 3
  - effort: 3
  - confidence: 4
  - risk: 2
  - area: data
  - depends_on: none (same infrastructure as BETA-015 — same source page,
    same discovery/dedup logic, same `sheet_rows`/anchor-row pattern)
  - objective: Table TA1 ("households in temporary accommodation") is on the
    same evergreen `live-tables-on-homelessness` page BETA-015 already reads,
    seen and understood during that module's own research but deliberately
    not built — one table done properly beats two done fast, the same
    discipline BETA-014/015 both applied. TA numbers are arguably as
    substance-misuse-relevant a comparator as A1's headline duty count.
  - rationale: Lowest-effort next dataset candidate in the queue — the
    discovery/dedup/format-handling machinery already exists in
    `m30_statutory_homelessness.py` (`_discover_publications`,
    `find_anchor_row`, the ODS/XLSX dual-format reading), so this is mostly
    a second `locate_ta1_columns`/`extract_ta1_rows` pair plus its own
    migration — not a from-scratch research cycle. Whether TA1's own column
    layout is as stable across the series as A1's turned out to be (it may
    not be — this was not checked) is the first thing to verify before
    assuming the same approach transfers cleanly.
  - suggested_first_action: Download 2-3 real TA1 sheets spanning both
    shapes (reuse BETA-015's already-downloaded scratch files if the
    session recovers them, else re-download from the same content-API URL)
    and confirm the column layout by hand before writing any code — do not
    assume A1's column-locator keywords transfer; TA1's own header text is
    different ("Households in TA", "B&Bs", etc., seen briefly during
    BETA-015's own research but not verified in depth).

### BLOCKED

- [BLOCKED] BETA-011 | Wire up AI-authored evidence promotion
  - priority: P1
  - blocked_by: Candidate type/use case — asked directly of the project
    owner in this session, answer pending (see Questions Requiring Human
    Input #0).
  - resume_when: The project owner specifies which candidates this should
    apply to.
  - alternative_work_available: yes (BETA-010 is done; more discovery
    ongoing)
  - decided_so_far: Wire it up for real use (not remove, not
    document-as-inactive). Review requirement: one AI pass plus the
    existing human review-queue decision counts as the second independent
    review — so this does *not* need two separate AI passes, just the AI
    check plus whatever a human reviewer already decides in the normal
    queue. Project owner's decision, 2026-08-25 interview.
  - notes: This is the most sensitive item in the whole queue — it touches
    `CLAUDE.md` settled decision 4 directly. Do not start implementation
    speculatively before the candidate type is known; the predicates
    (official source, exact identity, document type, dated, archived, no
    conflicts) mean very different things depending on which candidate
    table this reads from.

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
| P2 | Module 29: rough sleeping snapshot (dataset) | 4 | 3 | 5 | DONE (BETA-014) |
| P2 | Module 30: statutory homelessness / H-CLIC (dataset) | 4 | 4 | 4 | DONE (BETA-015) |
| P3 | Module 31: H-CLIC temporary accommodation, TA1 (dataset) | 3 | 3 | 4 | NEXT (BETA-016) |

This table is not kept current for every cycle's smaller items — see the
note on `docs/upgrade-roadmap.md`'s own staleness pattern (Questions
Requiring Human Input #2/BETA-002/BETA-008) for why that's a deliberate,
disclosed gap rather than an oversight. The Autonomous Work Queue above is
authoritative; this table is for skimming only, and BLOCKED/RESEARCH items
in the queue are the reliable source for what's actually pending.

## Features Under Investigation

None currently — BETA-002/003/004 above are investigation-shaped but not yet
started.

## Implemented Features

- BETA-001, BETA-007, BETA-009 (see DONE above).

## Dataset Additions

**BETA-015: Module 30, statutory homelessness (H-CLIC, MHCLG)** — BETA-014's
own flagged follow-up, built this cycle. Quarterly, LA-level, Table A1 only
(the flagship "households assessed / duty owed" count). See its DONE entry
for the full research, including a real parsing bug found and fixed
(covered-table-cell alignment), a region/England-code filtering fix m29's
own pattern would have gotten wrong on this source, and a documented
dual-meaning finding in one field across the series' two table layouts.

**BETA-014: Module 29, rough sleeping snapshot (MHCLG)** — requested
directly by the project owner as a local-authority-level comparator against
the sector's own substance-misuse evidence, given the documented overlap
between the two populations. Annual, 2010-to-current, one evergreen source.
See its DONE entry for the full research (homelessness H-CLIC confirmed
viable but not built this cycle; crime data researched and deliberately not
built — flagged in Questions Requiring Human Input instead).

Earlier in the session (before this request): no new dataset was proposed
autonomously, on the reasoning that this project's existing modules and the
roadmap's own "Rejected"/"Open questions" already covered the obvious
candidates and inventing one without a specific need would be speculative.
That reasoning held until asked directly — this entry is the difference
between inventing a dataset and building one that was actually requested.

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

BETA-014: migration `0059` adds `rough_sleeping_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

BETA-015: migration `0060` adds `statutory_homelessness_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

## Deployment / Infrastructure Changes

BETA-003: `deploy/ansible-mirror/` now builds a beta deployment as well as a
disaster-recovery mirror. See its DONE entry and Architectural Summary above.
Not yet run against a real VPS.

## Wording Pass (per project owner's mid-session request)

Asked to explore front-end wording, taking inspiration from comparable
projects while researching BETA-010/BETA-009. Findings:

- **Comparable products' copy was not a source of improvement.** LittleSis
  is bot-blocked from automated fetching; OpenSanctions' actual page copy is
  thin on caveats and sourcing detail compared to what this portal already
  does on every page. Adopting their tone would be a downgrade, not an
  upgrade — this portal's existing caveat/citation discipline is already
  more rigorous than either comparator's public-facing language.
- **A systematic scan for typos and repeated words across all public JS
  pages and `index.html` found none.** The existing copy is already clean.
- **One genuine, concrete inconsistency found and fixed**: every other
  page's `<h1>` is a descriptive phrase ("Where public money is going",
  "Find provider evidence", "Understand treatment data") — the new
  relationships page's was a bare single word, "Relationships". Retitled to
  "Who commissions whom", matching house style, plus a tightened lede.
- No broader rewording done. The existing copy's caveat language is
  precisely calibrated (several lines exist because of a specific incident
  — see `docs/CAVEATS.md` and multiple roadmap entries) and a wholesale
  pass risks introducing an error into wording that has been deliberately
  refined, for a return this scan did not find evidence of needing.

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

- BETA-009: the evidence graph subsystem (`docs/evidence-graph.md`,
  migration `0050`) had no answer anywhere in the UI to "has this ever run,
  how stale is it" before a CLI-only `pipeline graph status`. Now on the
  Health tab.
- BETA-013: same pattern, the document-analysis subsystem
  (`docs/document-analysis.md`, migration `0053`). Now on the Health tab
  too — 13,248 of 13,283 documents parsed in this checkout's real warehouse.

## Security Improvements

BETA-007: a per-IP token bucket on `/api/v1/*`, `429` + `Retry-After`.
See its DONE entry. Does not touch `/api/admin/*`'s security model (network
trust / bind address), which is unchanged and out of scope here.

## Testing Decisions

- BETA-015: 33 new unit tests on the pure parsing functions, using fixtures
  built from the real header/data text of both source-file eras (not
  invented text), plus the locator re-run directly against four full real
  downloaded workbooks and cross-checked by hand against MHCLG's own
  published totals — HIGH end of the brief's own §22 scale for a new
  parser reading two genuinely different real-world file shapes. All five
  coverage guards BETA-014 found were exercised again and each caught
  something real for this module too. Full suite run twice: once
  concurrently with a docstring edit (produced two spurious failures from
  editing a file while pytest was importing it mid-run — see the DONE
  entry's note on this), then once clean — 2419 passed, 2 pre-existing
  unrelated failures, confirmed a fourth time now.
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

## Environment Note

**This dev checkout's `.env` has `DATABASE_URL` pointing at the live Railway
production PostgreSQL database**, not a local sample warehouse — discovered
incidentally from `./start.sh web`'s own startup log ("warehouse:
postgresql://postgres:***@altaria.proxy.rlwy.net:20580/railway") while
verifying BETA-010 in-browser. Every live-browser check this session
(BETA-001, BETA-009, BETA-010) therefore ran against real production data,
not a fixture — which is *why* it looked so real (Nottinghamshire, CGL,
Turning Point are genuine). All requests made were `GET` (public portal
pages, admin health reads) — nothing this session wrote to it. Flagged
because it changes the risk profile of "start the dev server and click
around" for any future session: it is not a sandbox, and a future session
should not assume otherwise, especially before testing anything that writes
(a POST route, a review-queue decision, a module run).

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

## Decisions (from the project owner's interview, 2026-08-25)

- **`deploy/ansible/` is the maintained DR/host-migration path** — kept and
  maintained going forward, confirming BETA-003's approach was correct in
  spirit. **`deploy/ansible-mirror` is specifically for building beta and
  mirror environments away from production** — exactly BETA-003's design.
  No code change needed; this closes former Question 1.
- **`docs/upgrade-roadmap.md` stays, but only for major work.** Lighter
  discipline than the F/D/P/U/W/O-for-everything approach that visibly
  lapsed — file findings/phases for significant initiatives, not every
  small fix. This closes former Question 2. (Not yet written down as an
  explicit rule anywhere else — worth a one-line note at the top of the
  roadmap itself if a future session has a spare minute.)
- **Relationship explorer: yes, public-facing.** New dedicated portal
  section. First version scoped to provider↔authority commissioning
  relationships only (the deterministic data `graph backfill` already
  produces) — not company/PSC ownership edges yet. See BETA-010 below.
- **AI-authored promotion: yes, wire it up.** Review requirement: one AI
  pass plus the existing human review-queue decision as the second
  independent review. Candidate type/use case: **awaiting the project
  owner's explanation** — asked directly rather than via multiple choice,
  since this is a "let me explain" case, not a pick-from-a-list one.

## Questions Requiring Human Input

0. **Which candidates should AI-authored promotion apply to first?**
   `pipeline/ai_promotion.py`/`docs/AI_PROMOTION_POLICY.md` exist, are
   carefully guarded (objective predicates, sampling audits, a
   quarantine-on-false-promotion breaker), and the project owner has
   confirmed: wire it up, with one AI pass plus the existing human
   review-queue decision as the second independent review. What's still
   needed before implementation starts: which candidate type/backlog this
   should actually apply to — asked directly of the project owner, answer
   pending. See BETA-011.
1. **WDTK robots.txt exception** (BETA-005) — time-boxed to 2026-09-10,
   already tracked, not this session's call.
2. **Is crime data (BETA-014's research) worth pursuing given the real
   effort involved?** `data.police.uk` is the only real public source found
   and it is street-level/LSOA, not local-authority-level — using it as an
   authority comparator needs this pipeline's own LSOA→ONS-code crosswalk
   (ONS does publish an official lookup, so it's buildable, but it is a
   materially bigger module than rough sleeping or homelessness, and
   small-area crime data raises its own care-in-handling questions —
   whether aggregating up to LA level is enough distance from individual
   incidents, what a defensible comparator shape even looks like here —
   that this project has not had to answer for any existing source. Worth
   the project owner's view on whether the value justifies that effort
   before any code gets written, not a default yes.
3. **Is a document-search UI (BETA-013's follow-up) worth building, and
   where?** The backend already exists and works (`pipeline documents
   search`), but a search surface over raw parsed document text is a
   different risk shape from the relationship explorer's deterministic
   contract data — some sources it covers (PFD reports) have
   `restricted_`-table personal-data counterparts, so "what could a search
   result reveal" needs answering before any UI, admin or public. Not
   investigated further this cycle; flagged rather than guessed at.

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

*(Superseded revision — the previous version of this section, referencing a
"relationship-explorer question," was written before BETA-010/012 built
exactly that and before BETA-013/014/015 landed. Per §13 of the original
brief, this section must answer five questions without conversational
history; the version below does, as of 2026-08-25T21:40Z.)*

**What is currently being worked on?** Nothing — BETA-015 (Module 30) just
completed and pushed. No `IN_PROGRESS` item.

**What was the last successful change?** BETA-015: Module 30, statutory
homelessness (H-CLIC), Table A1. See its DONE entry above for the full
result, including two real bugs found and fixed during verification (a
covered-cell ODS alignment bug, and a region/England-code filtering gap
m29's own pattern would have gotten wrong on this source).

**What should happen next?** BETA-016 (Module 31, H-CLIC temporary
accommodation / TA1) is queued `NEXT` — the lowest-effort dataset candidate
available, since BETA-015 already built the discovery/dedup/dual-format
machinery this would reuse. Its own `suggested_first_action` says to verify
TA1's column layout by hand before assuming A1's approach transfers. Beyond
that, the queue is otherwise `BLOCKED`/`RESEARCH` only (see below) — per
§58 of the original brief, that is a signal to do a fresh strategic
reassessment (comparable-product research, technical debt scan, a look at
whether recently-added datasets have outpaced their own discoverability),
not a signal to stop. This session has now completed 16 queue items since
`beta` was created; a reassessment is due either way.

**What is blocked and why?**
1. BETA-011 (AI-authored evidence promotion) — waiting on the project
   owner to specify which candidate type it applies to first. See
   Questions Requiring Human Input #0.
2. BETA-005 (WDTK robots.txt exception) — time-boxed to 2026-09-10 or an
   earlier mySociety reply. Not this project's call to make sooner.
3. BETA-006 (`--jobs 4` re-evaluation) — refused twice already for an
   operational/scheduling reason, not a code-quality one; do not restart
   without new information about collection-calendar availability.

**What are the highest-value upcoming items?** In rough priority order:
BETA-016 (Module 31, ready and well-scoped); a decision from the project
owner on BETA-011's candidate type (would unblock the single most
sensitive item in the queue); Questions Requiring Human Input #2 (crime
data LSOA crosswalk — a real, bigger undertaking flagged during BETA-014's
research, not started) and #3 (document-search UI scoping) if the project
owner has a view; BETA-003's ansible-mirror changes still have never been
run against a real VPS, which remains the highest-value *unverifiable*
lever in the queue — nothing further to do on it from this dev checkout.

Do not touch the `m15-web-unlocker`/`zenrows`/`wdtk-html-fallback` branches
without asking — see BETA-004's notes. `docs/upgrade-roadmap.md` claims
should still be checked against actual code before being trusted for
anything not touched since BETA-002's reconciliation — BETA-008's DONE
entry records this as a recurring pattern (three separate stale claims
found across the session), not a one-off worth assuming fixed.
