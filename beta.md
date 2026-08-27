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
  directly, not `beta`). `beta` is now at `583476d` — eight out-of-queue
  commits after BETA-033: five on the provider entity model (`9b3fe06`,
  `eb1799f`, `fc97e66`, `b64ff10`, `583476d` — identifiers verified, then
  the set expanded 13→21→28→32 with renamed/merged/dissolved status on the
  portal) and three beta.md records (`2b264c2`, `2ca03a6`, next); all
  project-owner-directed, see Dataset Additions and Recent Commits —
  going into BETA-028.
- Twenty-nine items completed across this session and its predecessors:
  BETA-001 through BETA-027, plus BETA-032 and BETA-033 (BETA-001 on
  `master`). BETA-032 and BETA-033 are out-of-band: the project owner
  gave UI requests directly in an interactive session, then asked to be
  interviewed for further design refinement of the same two pages, rather
  than going through this queue — see their DONE entries below. The
  queue's own BETA-028 through BETA-031 were not displaced by either and
  remain exactly where the §52 reassessment left them. The §52 strategic
  reassessment below was run 2026-08-26 after four consecutive narrow
  front-end items, and the queue was re-aimed at high-impact front-end
  work per the project owner's direct steer ("prioritise improvements for
  the front end web ui… mind blowing").
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

## Comparable Product Research (2026-08-26, per the project owner's request)

Asked directly to "explore competing products to ensure my project is
competitive." Before researching externally, re-read `docs/upgrade-roadmap.md`
§3J ("Possible future") and §6 ("Rejected") in full — this project already
ran a comparable-product review (explicitly against WhatDoTheyKnow, LG
Inform, and Fingertips) and filed the results with reasoning, several
already declined or deferred for principled reasons (peer-group
benchmarking, significance-aware colouring, trend markers, tartan-rug
matrix views). Re-proposing any of those without new evidence would be
re-litigating a settled call, which the brief itself warns against. What
follows is additive to that, not a repeat of it.

**OCCRP Aleph** (investigative data platform, ~250 datasets, entity-based
cross-referencing across leaks/registries/financial records — [GIJN
tutorial](https://gijn.org/stories/aleph-pro-tutorial-occrp-updated-investigative-data-platform/)):
its two headline features are entity cross-referencing and document search.
This project already does the first, deterministically and conservatively
(the relationship explorer, BETA-010; `docs/CAVEATS.md`'s own
`name_only_unconfirmed` discipline is stricter than Aleph's own matching,
by design). It did not do the second — **this was the finding that led to
BETA-022** (see its DONE entry): the search backend already existed
(`pipeline/documents/`), unexposed.

**Tussell** (UK public-procurement intelligence — tenders, frameworks,
spend, supplier risk): most of its differentiators are either already
covered by this project's own caveats (the framework/call-off ceiling-value
warning `contracts.js` already pins) or are exactly the kind of inference
this project has already declined for principled reasons — peer
benchmarking (Phase 13: deferred, "the compare view is the honest
replacement for a peer group"), market alerts (SSE/WebSockets rejected,
§6). Nothing here changed a decision; it confirmed the existing ones are
not naive.

**A union-specific comparator** (Unite's own "Work, Voice, Pay Monthly" —
the closest thing to a direct competitor, published by the same union
whose deck this project's demographic pay data was verified against) was
bot-blocked from fetching, the same wall LittleSis and OpenSecrets hit
earlier in this session and OpenSanctions/LittleSis hit in an earlier one.
Not investigated further — a pattern worth noting (three of four attempted
fetches this cycle were blocked), not a finding in itself.

**Conclusion:** no new feature category emerged that this project has not
already considered and either built, deferred, or declined with reasoning.
The one concrete, evidenced gap — document search — was not a "which
comparable product should I copy" finding so much as "this project already
has the infrastructure a comparable product would need, and never exposed
it." That is the more valuable kind of finding this exercise could produce,
and it is why BETA-022 is the direct result of this research rather than a
coincidence.

## Strategic Reassessment (§52, run 2026-08-26 — the reassessment BETA-026's close-out flagged as owed)

Run after four consecutive narrow front-end items (BETA-023–026), i.e. the
top of §52's own 3–6-item window. Each §52 question was checked against the
actual code this cycle, not against memory:

1. **Is the roadmap still sensible?** The *discipline* is sound (every item
   shipped vertical, tested, documented), but item *selection* had drifted
   narrow: impacts ran 4 → 2 → 3 → 1. The project owner then removed the
   ambiguity directly: front-end web UI improvements are the priority, and
   the release needs to "really amaze end users". Correction applied: the
   queue below is repopulated with impact ≥ 3 front-end items only.
2. **Has the architecture changed what is now possible?** Yes, twice.
   Document full-text search (BETA-022–026) exists behind one public
   endpoint, and the portal already fetches the full authorities and
   providers lists at boot (`initFindCouncil`/`initFilterBar`, both cached
   by `fetchJSON`). A unified search surface — the one thing comparable
   platforms (Aleph above all) treat as the front door — is now nearly
   free in data terms. It did not exist as an option before this cycle.
3. **Over-investing in one subsystem?** Yes — four items in a row on
   document search. Search is now the portal's most-polished surface;
   every other surface got nothing this cycle.
4. **Neglected high-value part?** Two, both checked in code:
   - The **map page is the one page that half-breaks settled decision 6**
     ("both front ends must render with the network cable unplugged").
     `geography.js:25` loads the basemap style from
     `basemaps.cartocdn.com` — a *deliberate, documented* exception (CSP
     allowlists it in `server.py:183-185`; `tests/test_web_layers.py:253`
     pins the URLs), not an oversight. But with no network the style fetch
     fails, MapLibre never fires `load`, and the choropleth layers are
     never added: the reader gets the text alternative only, not a map.
     index.html's own header comment ("makes no external requests") is
     true of every asset and false of this one page's basemap. A local
     fallback style would honour the promise without taking the basemap
     away from online readers. Queued as BETA-028.
   - The **homepage downloads 500 notice rows to draw a 10-bar chart**
     (`overview.js` calls `contracts?limit=500`; `value_concentration` is
     computed server-side over the whole corpus; `provenance()` dedupes and
     shows at most 6 URLs). The payload is the page's single biggest
     transfer and 98% of it is unused. Queued as BETA-029 — also the first
     performance-section entry in three cycles.
   - The admin UI remains untouched this whole session — real, but
     deliberately deferred *again* by the owner's explicit "end users
     first" steer. Kept visible in the backlog, not forgotten.
5. **Comparable systems revealing a major gap?** No new category emerged
   beyond what the 2026-08-26 research recorded. The applicable
   un-emulated pattern is unified search as the front door — see (2).
6. **Technical debt constraining?** No new constraint found. The deferred
   nits (inline hex literals in map/graph code, claims-page filter) remain
   as recorded in Deferred Ideas.
7. **Users able to actually discover functionality?** Re-checked the way
   BETA-017 did: document search (nav + homepage tile + noscript + /api),
   comparators (authority page), relationships (nav) — all discoverable.
   The remaining gap is *between* surfaces: three separate search boxes
   (find-council, provider filter, document page) and no way to search
   across them. That is a discoverability finding, not just a feature
   request, and it is what BETA-027 addresses.
8. **Data additions outpacing understanding?** No — no new datasets this
   cycle; coverage and health surfaces keep pace.
9. **Queue dominated by low-impact work?** Yes — see (1). This
   reassessment's main correction.

**Direction set for the next cycle:** front-end, high-impact, end-user
facing, within the settled constraints (no build step, no new vendor
dependencies, text-node DOM discipline, caveats discipline). BETA-027 is
the flagship; BETA-028/029 make the portal's own documented promises true;
BETA-030 is the first researcher-delight item; BETA-031 researches the
homepage's first impression with a live browser before touching it.

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

### IN_PROGRESS

- [IN_PROGRESS] BETA-028 | The map renders with the network cable unplugged
  - started: 2026-08-26T17:45:00Z
  - priority: P1
  - impact: 4
  - effort: 2
  - confidence: 4
  - risk: 2
  - area: ui/geography
  - depends_on: none
  - files: pipeline/web/static/public/js/pages/geography.js, tests (see below)
  - branch: beta
  - last_commit: none yet
  - objective: When the CARTO basemap style is unreachable, fall back to a
    locally-defined MapLibre style (background colour, no sources) so the
    choropleth still draws and settled decision 6 holds on the one page
    that currently half-breaks it.
  - current_state: Scoped, not yet implemented. The external basemap is a
    deliberate, CSP-allowlisted, test-pinned exception
    (server.py:183-185, tests/test_web_layers.py:253) — the fix must keep
    those pins true (basemap stays for online readers) and only add the
    offline path.
  - next_action: In geography.js, move the layer-adding code out of the
    `map.on('load')` closure into a named function; listen for 'error'
    before first successful style load and on it call
    `map.setStyle(localStyle)` and re-add layers on the next 'load'. Guard
    against tile-error noise (fallback only fires if the style itself never
    loaded). Pin the behaviour source-wise in a test.
  - validation_remaining: ruff; portal suites; live check with the style
    URL blocked if a browser is available (this checkout has none).
  - notes: Local style = `{version: 8, sources: {}, layers: [{background}]}`
    with the theme's background colour; dark/light aware via the existing
    `isDark()`. test_web_layers.py's assertion that the carto URLs are
    present in geography.js must keep passing — do not remove the basemap.

- [IN_PROGRESS] BETA-034 | Semantic-analysis layer (pipeline/nlp): evidence-intelligence over the archive
  - started: 2026-08-27
  - priority: P2
  - impact: 5
  - effort: 5
  - confidence: 3
  - risk: 3
  - area: nlp/pipeline
  - depends_on: pipeline/documents (document_elements), pipeline/graph (graph_claims)
  - origin: **Not drawn from this queue.** Project owner via `/plan` on
    2026-08-27, after two rounds of steering (clinical-NLP vs
    evidence-intelligence framing; then a detailed pre-implementation
    review). The approved plan and the authoritative design live in
    `docs/semantic-analysis.md`; the plan file is
    `~/.claude/plans/tranquil-riding-reddy.md`.
  - objective: A downstream, local-only, non-collecting stage that makes the
    ~27k-document archive semantically searchable and connects extracted
    claims into the Evidence Graph — every derived statement a finding aid
    or a machine candidate until a person promotes it through the existing
    review queue → `graph_claims` path. Staged A–H; ship and stop per
    letter.
  - current_state: **034A foundation landed on `beta`.** Migration `0065`
    (`nlp_runs`, `nlp_model_registry`, `document_chunks`,
    `document_embeddings` — embedding is a dialect-neutral float32 blob in
    both trees, pgvector deferred to a later Postgres-only migration).
    `pipeline/nlp/{runs,models,chunk}.py`, `pipeline nlp chunk` CLI,
    `nlp_*` settings, `docs/semantic-analysis.md`. `tests/test_nlp_chunk.py`
    + migration-count bump green. Embeddings model, `/api/admin/search`
    hybrid search, the retrieval eval harness and the `nlp` optional-deps
    extra are the rest of 034A and are **not** landed — they cross the
    "heavy dependency + new network surface + browser-verify" line and
    want a checkpoint.
  - next_action: 034A remainder — `pipeline/nlp/embeddings.py` with a
    deterministic `stub` embedder (CI default, no download) and
    sentence-transformers behind an `nlp` extra; `semantic_search.py`
    (FTS + vector + metadata, RRF); `/api/admin/search?mode=…`;
    `tests/fixtures/nlp/retrieval_queries.yml` + `pipeline nlp eval-retrieval`.
    Then 034B (ontology) before 034D (GLiNER), per the plan's reorder.
  - validation_remaining: `uv run python -m pytest` full suite; `ruff`;
    once embeddings land, `uv sync --extra nlp` and the browser-verify pass
    on `/api/admin/search` with `/api/v1/*` unchanged.

### NEXT

- [NEXT] BETA-029 | Overview stops downloading 500 notices to draw 10 bars
  - priority: P2
  - impact: 3
  - effort: 1
  - confidence: 5
  - risk: 1
  - area: performance/ui
  - depends_on: none
  - objective: overview.js's top-contracts section requests
    `contracts?limit=500` but uses only `value_concentration.largest`
    (server-computed, top 10) and at most 6 provenance URLs. Request
    `limit=10` instead; same chart, ~98% less payload on the homepage's
    biggest transfer.
  - rationale: §52 finding 4 — the performance section has read "none"
    for three cycles; this is the cheapest real win in it, found by
    reading the code, not by guessing.
  - suggested_first_action: One-line change in overview.js plus a
    source-pinned assertion (in test_portal_navigation.py's style) that
    the overview page's contracts call passes a bounded limit.

### READY

- [READY] BETA-030 | Copy-citation button in the provenance drawer
  - priority: P2
  - impact: 4
  - effort: 2
  - confidence: 4
  - risk: 1
  - area: ui
  - depends_on: none
  - objective: A "copy citation" control beside the provenance drawer's
    source links, putting title, source URL, retrieval date and licence
    on the clipboard in one action — the researcher's most common manual
    step, made one click. Uses navigator.clipboard with a fallback;
    degrades to invisible when neither is available.

### RESEARCH

- [RESEARCH] BETA-031 | Homepage first impression: is the hero earning its place?
  - priority: P2
  - question: The overview hero is deliberately conservative (its own
    header comment explains why two requested headline numbers are
    refused). Within that discipline, would a compact England coverage
    visual (boundaries payload, reusing the geography page's palette) in
    the hero measurably improve a first-time reader's understanding of
    what this portal is — or is it decoration? Needs eyeballing live in
    a browser before building; static review cannot answer it.
  - research_needed: A live look at the current homepage at desktop and
    mobile widths, then a judgement call on whether a data visual in the
    hero adds comprehension or just pixels. The "mind blowing" steer is
    satisfied by clarity plus speed, not by animation; count-up numbers
    on evidence figures were considered and rejected as theatre.

### DONE

- [DONE] BETA-033 | Overview hero region map, orchestrated page-load and scroll-reveal motion; fixed a dead section found along the way
  - completed: 2026-08-26T23:32:47Z
  - commits: `5adc5e6` (`beta`)
  - origin: **Not drawn from this queue**, same as BETA-032 immediately
    below. After BETA-032 shipped, the project owner asked to be
    interviewed for further design refinement of the Overview and Pay
    pages specifically — an explicit "perfect the design" ask, answered
    with several rounds of `AskUserQuestion` before any code was written
    (ambition level, hero treatment, motion appetite, palette direction,
    then the specific hero-visual concept, Pay page's own role, motion
    style, and finally a technical-cost finding that changed the hero
    visual's shape mid-conversation — see the "conflicts" note below).
  - result: the Overview hero now carries a real, if simplified,
    silhouette of England's nine regions, shaded by the same
    "authorities appearing as a contract buyer" coverage signal already
    reported nationally on the snapshot cards — darker regions have more
    of their authorities showing contract evidence, which is drawn from
    a new `authorities.regions` breakdown in `summary()`
    (`public_queries.py`), not a second measure invented for the map.
    Both the Overview and Pay heroes now play a staggered page-load
    reveal (`.hero-animated`, pure CSS, no JS), and every `.section` on
    both pages reveals as the reader scrolls to it
    (`components.js`'s new `revealOnScroll`, IntersectionObserver-based,
    one-shot per element). The Pay page did not get its own dedicated
    visual signature this round — the project owner chose to decide that
    after seeing the Overview result rather than commit to it upfront;
    it stays a plausible BETA-034+ candidate.
  - **The hero map's shape changed twice during the interview, each time
    for a concrete technical reason surfaced before committing to code,
    not a taste reversal:** (1) the project owner's first choice was to
    reuse the `/geography` page's real interactive map; researching that
    found it depends on a live CDN basemap (`cartocdn.com`) and a 14MB
    full-resolution boundary payload (`/api/v1/boundaries`) — a
    reasonable cost for a page a reader chose to visit, a bad one for
    the homepage's first paint, and a direct, undisclosed-at-the-time
    conflict with the settled "both front ends render with the network
    cable unplugged" rule (CLAUDE.md decision 6). Flagged before
    building anything. (2) Presented with that cost, the owner's next
    choice was still the literal map, accepting the tradeoff — then,
    once told the concrete 14MB figure specifically (not just the
    abstract policy conflict), chose a third option instead: dissolve
    the same already-collected, already-provenanced authority polygons
    (`authorities.geometry_geojson`) into their 9 real regions, once,
    server-side, and ship that as a small static asset. This is what
    shipped: `scripts/generate_region_outline.py` (a one-off, run by
    hand, not part of the pipeline's own module registry — regenerate
    only if Module 0 re-collects boundaries from a new ONS vintage) uses
    `shapely.ops.unary_union` per region, then drops sliver polygons
    below 0.05% of each region's dissolved area (adjacent authority
    polygons rarely share byte-identical edges, so the raw union left
    hundreds of sub-square-metre artefacts at every near-miss seam —
    East of England alone dissolved to 490 sub-polygons before this
    filter, 441 of them under 1e-5 sq degrees; after it, every region is
    1-5 real landmasses), then simplifies at 0.04 degrees. Output:
    `pipeline/web/static/public/assets/england-regions.json`, 9
    features, ~64KB on disk / ~28KB over the wire, day-cached. No
    MapLibre, no CDN request, no settled-decision conflict, and the
    resulting silhouette is real England geometry rather than an
    abstract cartogram — checked by eye against the computed bounding
    box (-5.72 to 1.76°E, 49.96 to 55.79°N, which is genuinely
    Cornwall-to-Berwick) since this session could not render a
    screenshot (see Verified, below). The frontend projects the GeoJSON
    to SVG itself (`overview.js`'s `projectRing`/`pathForGeometry`/
    `viewBoxFor`, a new `svgEl()` DOM helper in `app.js` alongside
    `el()` — `document.createElement` cannot produce real SVG elements,
    only `document.createElementNS` can), with a longitude/latitude
    aspect correction so England is drawn at roughly its true
    proportions rather than the wider-and-squatter shape a naive
    equirectangular plot would give it this far from the equator.
  - **Found and fixed in passing, unrelated to anything asked for**: the
    Overview page's "Current snapshot" section — the coverage /
    evidence-quality / sector-context cards (local authorities tracked,
    procurement notices indexed, providers tracked, human-verified
    evidence rows, contract value, sector vacancy/turnover) — has never
    actually rendered on the live site. `render()` built a `snapshot`
    div with `el('div', {})`, filled it via `renderCards(snapshot, ...)`,
    and never inserted that div into the page tree at all; a *separate*,
    permanently-empty `<div id="snapshot">` sat in its place. Confirmed
    present as far back as `HEAD~2` (well before this session), so this
    predates both BETA-032 and BETA-033 — not something either
    introduced. One-line fix: `renderCards(page.querySelector('#snapshot'), summary)`,
    matching every other section's own call pattern. No test caught it
    because no test exercises the rendered DOM of this page; the offline
    suite is fixture-backed against the Python API layer, not JS
    wiring.
  - validation: full offline suite — 2469 passed, 106 skipped, 33
    deselected, 2 failed (`test_documents.py`, the same pre-existing,
    disclosed, environment-caused failures as BETA-032's baseline — a
    third failure BETA-032 saw in `test_m04_companies.py` did not
    reproduce this run, consistent with it being the live-network
    integration test flakiness that file already carries, not a
    regression). `ruff check pipeline scripts` clean.
    `tests/test_portal_isolation.py` updated and passing: the new
    `/assets/england-regions.json` static path is registered in
    `server.py`'s `STATIC_FILES` (guarded by the same directory-origin
    and public-surface-pinning tests every other static asset is) and
    added to that test's `PUBLIC_STATIC_PATHS`.
  - **Verified live against the dev server, with one disclosed gap**:
    confirmed via DOM/network inspection (not screenshot — this
    session's browser pane reported `document.hidden: true` /
    `visibilityState: "hidden"` throughout and could not composite a
    frame) that the region map fetches and renders 9 `<path>` elements
    with correct `aria-label` (computed highest/lowest region from real
    data — London 100%, East of England 72%, on the live warehouse), the
    static asset serves at 200 with a day-long cache header, and the
    "Current snapshot" fix produces the expected 4 section headings
    where 3 showed before. **Not verified**: whether the page-load
    animation and scroll-reveal are visually correct in a real,
    foregrounded browser tab. Direct testing of raw
    `requestAnimationFrame` and `IntersectionObserver` in this same
    hidden tab showed neither ever fires — a session-specific rendering
    limitation also seen verifying BETA-032's count-up animation, not
    something diagnosable from here. The CSS itself was checked in
    isolation (a freshly-created probe element with the `.reveal` class
    correctly computed `opacity: 0`), so the mechanism is sound, but a
    live-browser eyeball of the actual motion is still owed, same as
    BETA-024's and BETA-027's carried-forward caveat.
  - possible follow-up: Pay page's own signature visual (deferred, see
    "result" above); a live-browser check of the motion work once a
    session has a compositing browser; `docs/CAVEATS.md` and CLAUDE.md's
    settled-decision list could note the `/geography` page's existing
    CDN/basemap dependency explicitly, since this conversation surfaced
    it as an undocumented exception to decision 6 rather than a written
    one — not changed this round because it was a pre-existing condition
    being worked around, not something this work touched.

- [DONE] BETA-032 | Overview & Pay page polish: count-up metrics, provider-matched highlights, statutory/gender-pay-gap cleanup, census removal
  - completed: 2026-08-26T22:45:46Z
  - commits: `ef1a4c4` (`beta`)
  - origin: **Not drawn from this queue.** The project owner gave ten
    specific UI requests directly in an interactive session (not the
    autonomous work loop), covering the Overview and Pay pages. Recorded
    here after the fact so a later session has the full picture; the
    queue's IN_PROGRESS/NEXT/READY/RESEARCH items above were not displaced
    by it.
  - result (Overview): the four "campaign view, at a glance" metrics count
    up on load; "active evidence signals" (a count of how many layers
    happened to be non-zero) replaced with the same "matched to a known
    provider" measure already shown on the Contracts page (new
    `summary()["contracts"]["matched_to_provider"]` in
    `public_queries.py`); the 8 explore cards carry a lens-coloured accent
    (money/workforce/access/safety/accountability, reusing app.js's
    existing route-lens categorisation) instead of a flat uniform style;
    Freshness now lists rough sleeping, statutory homelessness and
    temporary accommodation — missing from `FRESHNESS_TABLES` since
    Modules 29-31 shipped (BETA-014/015/016), so those three source
    tables were being collected but never shown as collected; "largest
    notices in the corpus" narrowed from the top 10 overall to the top 5
    matched to a tracked provider (new `largest_matched_to_provider`
    query in `contracts()`), since the unmatched top 10 is dominated by
    anonymous cross-government framework notices with no provider
    attached — not a useful "biggest deal we found" list for the
    campaign.
  - result (Pay): charity accounts table now sorts newest-report-first;
    statutory minimum rates table restricted to the current period (April
    2026), the incorrect "Rate (hourly)" column dropped, and the Under-18
    row excluded (not legally recruitable into a CQC-regulated adult
    substance misuse service, per the project owner directly); gender pay
    gap filings render as a grouped bar chart (median/mean hourly gap %)
    instead of a table; the workforce census section (indicators + metrics
    table, all rows unverified) removed from the page entirely per direct
    instruction, with its nav link — the `pay()` query and its
    `workforce_census`/`census_*` fields are untouched server-side, only
    the page's own rendering of them was removed; Skills for Care
    "National estimates" hides rows with no hourly-pay figure (188 of 500
    rows on the live warehouse).
  - **Conflicts with BETA-031's own research note above**, which
    considered a count-up animation on evidence figures and rejected it as
    "theatre." The project owner asked for this one directly and
    specifically, which is a different footing than the §52 research
    judgement call it overrides — noted here rather than quietly
    overwritten, in case a later session re-reads BETA-031 and wonders why
    the counters exist. The implementation respects
    `prefers-reduced-motion` (jumps straight to the final value) and is
    presentation-only — no value is altered, only how it arrives on
    screen.
  - validation: full offline suite — 2468 passed, 106 skipped, 33
    deselected, 3 failed, all three pre-existing and unrelated (documents/
    Companies House parsing, nothing this session touched — same
    disclosed category as BETA-007's baseline). `ruff check pipeline
    tests` clean. Verified live against the dev server (`./start.sh web`):
    sort order, filtered rows/columns, removed sections, the
    `matched_to_provider`/count-up wiring, and the explore-card accents
    read back via computed style rather than just class presence — an
    earlier draft put `.lens-money`/`.lens-accountability` classes
    directly on the cards, which collided with the *existing*,
    differently-scoped `.lens-accountability` rule the hero-kicker badge
    uses (components.js's `lensBadge()`), and would have silently
    mis-coloured two of the five accents; fixed by setting `--lens` as an
    inline custom property instead of a class. Could not screenshot — this
    session's browser pane did not composite frames — so visual
    confirmation used `get_page_text` and DOM/computed-style reads instead.
  - possible follow-up: the project owner has asked to be interviewed for
    further design refinement of these same two pages next. Expect a
    BETA-033+ entry, either landing directly from that conversation or
    queued here first.

- [DONE] BETA-027 | Command palette: unified search across pages, authorities, providers and documents
  - completed: 2026-08-26T17:40:00Z
  - commits: (this commit; `beta`)
  - result: One search box for the whole portal, opened from a topbar
    button beside the council search, Ctrl/Cmd-K, or "/". It finds portal
    pages, councils, providers and document text, and every choice
    navigates by hash change exactly as the existing per-surface searches
    do — the "front door" pattern the §52 reassessment identified as the
    portal's remaining discoverability gap (three separate search boxes,
    no way to search across them).
  - **Architecture is the operator UI's own palette wearing public
    clothes**, because that pattern is proven in this codebase
    (`static/js/palette.js`): lazily-built dialog, score-ranked flat list
    with inline kind labels (same `score()` — direct match beats
    subsequence — so the two palettes feel identical to anyone who uses
    both), hash-only navigation, focus restored on close, no state of its
    own. New here: the councils and providers lists come from the API
    payloads app.js already fetches and caches at boot (opening the
    palette costs no extra request), and document results arrive live
    from the BETA-022 endpoint — debounced 200ms, minimum 3 characters,
    bounded, and stale-guarded so a response for an abandoned query can
    never paint over the current one.
  - **Two data-shape findings from verifying against the live warehouse:**
    (1) document `title`s in this corpus are usually content-hash
    filenames — a palette of hashes would teach a reader nothing, and the
    documents page itself shows the same hashes (pre-existing, out of
    scope, flagged below). The palette's document rows therefore show the
    *snippet* — real match-centred evidence text, exactly why the row
    matched — with a readable document-type label as detail. (2) One
    document matches on several pages, so 12 raw rows for "recruitment"
    collapse to 4 unique documents; results are deduped by
    source_url+page and the fetch window widened (12) so five *unique*
    documents still fit the display cap.
  - Accessibility follows BETA-021's portal standard rather than the
    operator palette's lighter one: the input declares role=combobox with
    aria-expanded/aria-controls/aria-autocomplete, options carry
    aria-selected with the input's aria-activedescendant pointing at the
    roving highlight, Enter picks, Escape closes, Tab stays inside the
    aria-modal dialog. Values reach the DOM as text nodes (settled
    decision 9): document snippets are scraped council PDFs, and the
    matched-span highlighting is built from element/text nodes, never
    innerHTML.
  - Wired through the frozen surfaces the house rule requires:
    `server.py`'s module list (STATIC_FILES), `PUBLIC_STATIC_PATHS` in
    tests/test_portal_isolation.py, and a new
    tests/test_portal_palette.py pinning: every destination is a real
    route *with the router's own title* (drift fails in both directions),
    the visible trigger exists, app.js boots it, it navigates and never
    filters (no data-filter, no setState), text-node discipline, the
    debounce/bounds/stale-guard, navigation to `#/documents?q=…`, no
    external requests, the keyboard contract, focus restore (including
    the isConnected guard), and the platform-adaptive kbd hint (⌘K on a
    Mac). 104 tests across palette+isolation+navigation+controls+public+
    documents suites pass; ruff clean.
  - **Live smoke test against the dev server** (this checkout's real
    warehouse, GET-only per the Environment Note): `/js/palette.js`
    serves (200), the homepage carries the trigger, `/api/v1/authorities`
    returns 347 rows with the name/ons_code/region fields the palette
    reads, and `/api/v1/document_search` returns match-centred snippets.
    In-browser interaction (overlay opens, arrows move, Enter navigates)
    could not be exercised — no browser or node in this checkout, the
    same caveat BETA-024 carried; a structural balance check stood in for
    a syntax check. Next live session should eyeball it.
  - possible follow-up: readable display titles for committee papers on
    the documents page itself (the palette worked around the hash-title
    problem; the page still shows hashes) — a document-layer
    improvement, not a palette one. Flagged, not queued.

- [DONE] BETA-026 | Quoted phrases anchor snippets and highlight as a unit
  - completed: 2026-08-26T14:50:00Z
  - commits: `538095f` (`beta`)
  - result: `_search_terms` keeps quoted spans whole and lists them first,
    and `_match_snippet` anchors the window on a phrase occurrence before
    considering bare words — which exposed a real bug, not just polish: the
    original `min()` over every term's position let an early single word
    ("sleeping" at char 770) drag the window away from the passage that
    matched as a phrase ("sleeping duty" at char 971), leaving the phrase
    outside the snippet entirely. documents.js's highlighter mirrors the
    same tokenisation (phrases-first alternation), so where the phrase
    occurs contiguously it is marked as one unit. Unmatched lone quotes
    degrade to word behaviour identically on both sides.
  - validation: tests/test_web_documents.py now 13 (phrase anchoring pinned
    with a distractor word placed beyond one snippet radius); 93 combined
    passes across document-search + portal suites; ruff clean.

- [DONE] BETA-025 | "Show more" pagination for document search
  - completed: 2026-08-26T14:20:00Z
  - commits: `6db979a` (`beta`)
  - result: `document_search()` takes a clamped `offset` (negative clamps to
    0 rather than PostgreSQL raising / SQLite walking backwards) threaded
    through both backends' SQL and server.py's route; documents.js grows an
    accumulating "Show N more" control under the results. The button lives
    in its own slot so a failed fetch never touches the pages already on
    screen, is replaced with "Loading…" while in flight (no double-click
    duplicate windows), and the count line stays truthful as the list grows.
    Offset is deliberately *not* URL state — the shareable address stays
    `#/documents?q=…`; how far one reader has paged is transient view state.
  - validation: tests/test_web_documents.py now 12 tests (window tiling
    without overlap against an unpaged reference, offset past end empty-not-
    error, negative clamp); combined run with portal navigation/isolation/
    controls/public suites = 92 passed; ruff clean across pipeline+tests;
    live read-only PG check confirmed disjoint windows and clamping.

- [DONE] BETA-024 | Per-route document titles and focus management on navigation
  - completed: 2026-08-26T13:40:00Z
  - commits: `f2115d7` (`beta`)
  - result: app.js's router now sets a per-route `document.title`
    (ROUTE_TITLES, kept in lockstep with ROUTES by test — drift in either
    direction fails), and moves focus to `#main` with preventScroll when the
    base route changes. The move is gated on an actual route change, not on
    every render: filter edits re-render the whole page through the state
    subscription and must not yank focus out of the control being typed in,
    and first load keeps the reader's own starting point. Pinned by
    tests/test_portal_navigation.py (static-source assertions, this suite's
    offline style), including that index.html's `<main tabindex="-1">` — the
    precondition for the handoff landing anywhere at all — stays put.
  - validation: tests/test_portal_navigation.py (5) + test_portal_controls.py
    + test_portal_isolation.py pass (36 total); ruff clean. Browser check not
    possible from this checkout (no node/browser tooling; see Environment
    Note) — behaviour is deliberately simple and source-pinned; next live
    session should eyeball a nav click announcing/retitling correctly.

- [DONE] BETA-023 | Document search results that show why they matched
  - completed: 2026-08-26T13:05:00Z
  - commits: `cb4781b` (`beta`)
  - result: `document_search()` now returns, per result, a `snippet` windowed
    onto the passage that matched (computed in Python so SQLite FTS5 and
    PostgreSQL return byte-identical snippets — the two engines' native
    headline functions differ in splitting rules and a snippet that changes
    shape with the backend cannot be pinned by test), plus a route-level
    `total` counting every allowlisted match. documents.js renders the
    snippet with `<mark>` highlighting built as element/text nodes (never
    innerHTML — settled decision 9; the text is scraped council PDFs), says
    "showing N of M matching pages" when the list is cut (the client now
    asks for the server ceiling of 50 rather than silently stopping at 25),
    and degrades gracefully against an older cached API response without a
    snippet. Allowlist semantics untouched: `total` counts through the same
    WHERE clause, so excluded source systems are invisible to the count too
    (pinned by test). Full page `text` still ships per result.
  - validation: tests/test_web_documents.py extended to 9 tests (snippet
    centring, short-text whole-return, total vs limit, allowlist-aware
    count) — all pass; test_portal_isolation.py + test_portal_controls.py +
    test_web_public.py pass (76); ruff clean. PostgreSQL path confirmed live
    read-only against this checkout's configured warehouse (`total: 5652`
    for "recovery", short texts returned whole, count query instant at this
    corpus size) — see Environment Note re production data; GET-equivalent,
    nothing written.

- [DONE] BETA-022 | Public document search over committee papers and CDP documents
  - completed: 2026-08-26T02:00:00Z
  - commits: `3f8c74d` (`beta`)
  - result: `pipeline/documents/` (docs/document-analysis.md) has parsed PDFs
    into page-aware, SQLite-FTS5/PostgreSQL-tsvector-searchable text since
    before this session, and `pipeline documents search` has worked at the
    CLI the whole time — nothing before this put it behind a web route.
    `docs/upgrade-roadmap.md`'s own "Corpus-wide search" and "Full-text
    search over archived documents" entries both said to revisit "once the
    promotion work has given it verified documents to search rather than
    candidates" (§3J, §6) — confirmed against the live warehouse before
    writing anything: 13,249 documents parsed, exactly as beta.md's own
    Health-tab note already said. This was wiring an existing backend to a
    route, not building search infrastructure.
  - **The safety question beta.md's own "Questions Requiring Human Input
    #3" left open — "is a document-search UI worth building, and where,
    given some sources have restricted_ personal-data counterparts" — is
    answered by checking rather than guessing:** queried the live warehouse
    directly (`SELECT DISTINCT e.source_system FROM document_records d JOIN
    evidence_records e ...`) and found exactly two source systems bridged
    into this schema today — `committee_paper_promotion` (12,825 docs) and
    `cdp_document_promotion` (424 docs) — both public council/partnership
    governance papers, neither with a restricted_ counterpart. PFD reports
    and tribunal judgments, the two sources docs/CAVEATS.md's "Personal
    data" section actually restricts, are not bridged into this pipeline at
    all (`pipeline/documents/bridge.py` only supports committee_papers,
    cdp_documents, annual_reports, and only the first two have ever been
    run). So: safe to build, scoped tightly.
  - `pipeline/web/public_queries.py::document_search()` reads from an
    explicit `DOCUMENT_SEARCH_SOURCES` allowlist in its SQL, not "everything
    in `document_records`" — this, not `_public()` alone, is the real
    safety boundary, because `document_records`/`document_elements` are not
    `restricted_`-prefixed tables and hold a generic `text` column no export
    guard recognises as personal data. If a future session ever bridges PFD
    report bodies or tribunal judgment text into this same schema, it must
    not become searchable here just by existing in the table — fail closed,
    documented at length in the function's own comment so a future session
    does not have to rediscover the reasoning. `tests/test_web_documents.py`
    pins this with a seeded fixture: a document from an unlisted source
    system, matching the query exactly, is asserted to never come back.
  - New route `/api/v1/document_search` (`q`, `limit`, max 50), new public
    page `/js/pages/documents.js` (search box, URL-carries-query like
    `compare.js`'s own convention, result cards reusing the `.claim` card
    style rather than inventing one), a nav link, an "Explore the evidence"
    tile on the homepage, and matching entries in `api.html` and the
    `<noscript>` block (both pinned by `tests/test_portal_isolation.py`,
    updated in the same commit — the brief's own house rule).
  - Verified against real production data via `./start.sh web`: searching
    "recruitment" returns genuine council committee-paper excerpts (a
    Haringey workforce report, a Staffing and Remuneration Committee
    discussion of a recruitment-and-retention offer) with correct
    provenance links and retrieval dates; an unbalanced-quote and a
    trailing-operator query both degrade gracefully (FTS5 tokenized them
    rather than raising, so the `QueryError` wrapper around
    `sqlite3.OperationalError` was not exercised live, but stays as the
    documented failure path); a no-match query renders the existing
    `noData()` empty state. Zero console errors throughout.
  - Testing: `tests/test_web_documents.py` (5 new tests — finds committee
    paper text, finds CDP document text, **excludes an out-of-allowlist
    source system on an exact text match**, rejects an empty query, clamps
    an oversized `limit`), `tests/test_portal_isolation.py` (21, including
    the new route/page in the frozen public-surface lists),
    `tests/test_web_public.py` + `test_portal_controls.py` +
    `test_documents.py` + `test_licences.py` (86 passed, 2 pre-existing
    unrelated failures — the same `transformers` cache corruption noted in
    Current Beta Status), `tests/test_docs_coverage.py` +
    `test_register_links.py` (21, after updating two
    `docs/upgrade-roadmap.md` entries to record this as delivered). Full
    `uv run python -m pytest` run once more as a final check given this
    touches a new public route and a personal-data safety boundary — see
    below.
  - note: This is the first session-cycle item genuinely prompted by the
    "explore competing products" half of the brief rather than by
    re-checking this project's own prior audits. Comparable-product research
    (OCCRP Aleph, Tussell — see the new "Comparable Product Research" note
    below) confirmed document/full-text search is the headline feature of
    every investigative-evidence platform; this project already had the
    hard part built and unexposed.

- [DONE] BETA-021 | Arrow-key navigation and aria-activedescendant for every typeahead
  - completed: 2026-08-26T00:30:00Z
  - commits: `a28b010` (`beta`)
  - result: The other lower-confidence finding from BETA-018's frontend
    audit (see Deferred Ideas) that was actually still there on re-check.
    The audit named three call sites; re-checking found **six**, not three
    — `relationships.js`'s `entityPicker` (explicitly commented as
    "generalised from compare.js") was missed. Of the six, only two
    (`#find-council`, `#f-provider` in `index.html`) actually declared
    `role="combobox"` — `compare.js`/`treatment.js`/`relationships.js`'s
    pickers only had `role="listbox"` on the `<ul>`, and `treatment.js`'s
    had no role or keyboard handling at all. So the audit's framing
    ("overpromising ARIA") was more true of two widgets than five, but the
    underlying gap — no arrow-key nav, `aria-selected` never set — was real
    everywhere.
  - Added one shared `typeaheadKeyboard(input, list)` export in `app.js`
    (`ArrowDown`/`ArrowUp` move a roving highlight, `Escape` clears it,
    `Enter` picks the highlighted option or the first if none is
    highlighted — the existing behaviour, unchanged) rather than writing
    the same logic six times. `styles.css` already had a
    `li[aria-selected="true"]` rule waiting for this, unused, since before
    this session. Brought all six to the same `role="combobox"` +
    `aria-expanded` + `aria-controls` contract and removed each site's own
    ad-hoc "Enter picks first match" listener in favour of the shared one.
  - note on verification method: the in-app browser tool's synthetic key
    press does not populate `KeyboardEvent.key`/`.code`/`.keyCode` — caught
    by instrumenting a listener before assuming the fix was broken.
    Switched to `dispatchEvent(new KeyboardEvent(...))` with real `key`
    values for all in-browser verification instead; this is what actually
    exercised the arrow-key/Enter/Escape paths on all six widgets. No JS
    test runner exists in this project (no build step, by design — see
    `CLAUDE.md` settled decision 6), so `tests/test_portal_controls.py` +
    `test_web_public.py` + `test_portal_isolation.py` (76 tests) were run
    as a backend-contract/isolation smoke check only, not as proof of this
    change — the in-browser `dispatchEvent` checks are the real evidence.

- [DONE] BETA-020 | Data tables under every Compare-page chart
  - completed: 2026-08-26T00:00:00Z
  - commits: `fb5974e` (rebased to `f566c79` on push; `beta`)
  - result: One of the three lower-confidence findings BETA-018's frontend
    audit deferred (see Deferred Ideas): `compare.js` drew four
    chart-bearing sections (grant, budget, treatment, contracts, plus
    charity/provider-contracts once a provider is selected — six sections
    total) with no accompanying data table, unlike every other
    chart-bearing page in the portal. Re-checked against current code
    before acting, per this file's own discipline — the gap was still
    there. Added a `tableCard` beneath each chart, reusing the exact
    component every other page already uses rather than inventing a new
    one: `renderYearsChart` (shared by grant/budget/contracts/provider
    contracts) gets a `yearsTableColumns()` helper that derives columns
    from `opts` and the rows themselves, since the same function draws four
    differently-shaped series; `renderTreatment` gets one table per
    indicator chart (mirroring `treatment.js`'s own `drawTable`, England
    rows included with `authority_name: 'England'`); `renderCharity` gets a
    static Provider/Year end/Income/Expenditure table. No `exportEndpoint`
    on any of them — `compare` is not in `public_export.py`'s `EXPORTABLE`
    registry and adding one was out of scope for a UI-gap fix.
  - Verified in-browser (`./start.sh web`, not the beta deployment — this
    dev checkout's `DATABASE_URL` is live Railway production, GET-only, see
    Environment Note): selected Adur (authority) and Turning Point
    (provider), all six sections rendered with correct columns and
    GBP-formatted values (including a real negative budget figure,
    `-£411,000`, rendering correctly), zero console errors. No test file
    covers the JS frontend directly (no build step, no JS test runner in
    this project); ran `tests/test_web_compare.py` +
    `tests/test_portal_isolation.py` (31 tests) as the backend-contract and
    isolation smoke check since the endpoint itself was untouched — both
    green.
  - note: A concurrent session pushed `419171f` ("mirror: add explicit
    local PostgreSQL reset", `deploy/ansible-mirror/`) to `origin/beta`
    between this item starting and finishing — rebased cleanly, no file
    overlap. Per `CLAUDE.md`'s "several sessions share this checkout"
    warning, this is expected, not a conflict to resolve further.

- [DONE] BETA-019 | Complete-corpus CSV/JSON export for PFD reports
  - completed: 2026-08-26T00:35:00Z
  - commits: `ece19ae` (`beta`)
  - result: BETA-018's own flagged follow-up, built this cycle. `pfd.js`'s
    "Latest reports" table had no CSV export, unlike every comparable
    "recent records" table elsewhere in the portal — confirmed as a real
    backend gap, not a one-line frontend fix: `pfd()`'s `recent` array is
    `LIMIT 50`, and `public_export.py`'s `EXPORTABLE` registry had no
    `"pfd"` entry, so naively wiring one up would have silently exported
    only the 50 newest of 1,539+ reports as if it were the whole corpus —
    exactly the failure `WINDOWED = {"contracts"}` exists to refuse.
  - Mirrored the existing `contracts` complete-export pattern exactly,
    end to end: `public_queries.all_pfd_reports(conn)` (count first,
    then a streaming cursor over the unlimited query — no `deadline()`
    guard, same reasoning as `all_contract_notices`'s own docstring: a
    complete export of a six-figure-adjacent corpus is meant to take as
    long as it takes); `"pfd"` added to both `EXPORTABLE` (`recent` →
    label `"pfd"`) and `WINDOWED` in `public_export.py`; a new `elif
    endpoint == "pfd"` branch in `server.py`'s `_export_complete`
    (previously a hardcoded `if endpoint != "contracts": raise`, one
    endpoint deep); `exportEndpoint: 'pfd'` added to the frontend table.
    Also found and fixed a smaller adjacent gap while wiring this up:
    `licences.ENDPOINT_MODULES` had no `"pfd"` entry either, so the
    export's licence line would have read "not recorded for this
    endpoint" instead of the correct OGL v3.0 — added, scoped to
    `m08_pfd_reports` only (not `m28_sar_reports`, a different licence,
    since SAR data isn't part of this export).
  - **SAR's own "Latest SAR documents" table deliberately not addressed**
    — flagged as a separate, harder question in BETA-019's own queue entry
    before implementation started: it shares the same `/api/v1/pfd`
    endpoint but is a different sub-array (`data.sar.recent`), and
    `EXPORTABLE`'s one-key-per-endpoint design has no natural slot for a
    second exportable table under one endpoint. Not solved here; would
    need its own design decision, not a bent version of this fix.
  - note: **Verified against real production data, not just the fixture**
    — the live corpus is exactly 1,539 PFD reports (matching the page's
    own hero text); fetched both `/api/v1/export?endpoint=pfd&format=csv`
    and `&format=json` directly against the dev server and confirmed both
    returned all 1,539 rows with a correctly-populated OGL licence line,
    not the 50-row page window. 14 tests in `tests/test_export_completeness.py`
    (extended, not a new file — this is exactly the file `contracts`' own
    complete-export tests live in, the natural home): row-count and
    header-count agreement, licence presence, column-shape agreement
    between the windowed and complete queries (the same "one SELECT feeds
    both" discipline `all_contract_notices` established), JSON
    completeness, and the pre-existing generic guard
    (`test_every_windowed_endpoint_has_a_complete_reader`, which iterates
    `WINDOWED` and would have caught a missing `_export_complete` branch
    automatically). Full suite run clean and uninterrupted: 2441 passed,
    106 skipped, 33 deselected, 2 pre-existing unrelated failures
    (confirmed a sixth time).
  - possible follow-up: SAR export, if wanted, needs its own design
    decision on how `EXPORTABLE` should handle a second exportable table
    under one endpoint — not queued, flagged only.

- [DONE] BETA-018 | Frontend UI audit: theme-aware chart colours, mobile theme switcher, dead vendor file
  - completed: 2026-08-25T23:10:00Z
  - commits: `087c1c6` (`beta`)
  - result: Project owner asked directly to continue exploring frontend
    UI improvements (§27/§28 of the original brief), the area flagged as
    untouched since BETA-010 in this file's own Next Recommended Actions.
    Surveyed all 12 portal pages plus `styles.css` for concrete, evidenced
    gaps (not a speculative wishlist) and found two real bugs, verified and
    fixed, plus one piece of confirmed dead code:
  - **Bug 1 — five ECharts titles and one graph-node label hardcoded
    `color: '#e6edf3'` (a near-white), which overrides the registered
    per-theme colour entirely.** In light mode this made chart titles on
    `authority.js` (3), `compare.js` (1) and `treatment.js` (1), plus
    `providers.js`'s entity-relationship graph node labels, render pale
    grey on a white background. Confirmed by reading `mountChart`'s theme
    selection in `components.js` and `theme.js`'s `sectorTraceLight`
    registration (title colour `#132238`, correctly dark-on-light) — an
    inline option colour always wins over a registered theme's default, so
    these titles never picked it up. Fixed by removing the hardcoded
    colour from title `textStyle` objects (letting the theme supply it)
    and adding a new exported `chartLabelColor()` helper in `theme.js` for
    the one case (the graph label) that sets colour on something other
    than a title, so future series-label colours have a theme-aware helper
    to reach for instead of a literal. **Two similar-looking occurrences
    were deliberately left alone** after checking their context: a
    treemap segment label (`contracts.js`) and a heatmap emphasis border
    (`providers.js`) both sit on saturated fill colours from the shared
    palette, not the page background, so their contrast requirement is
    against the fill, not the theme — not the same bug, and "fixing" them
    blind without a visual check would have been a guess, not a fix.
  - **Bug 2 — the theme switcher was completely unreachable below 900px
    viewport width, with nothing replacing it.** `.theme-control` was a
    topbar-level sibling of the nav, so the mobile offcanvas (which
    relocates only nav items) never carried it, and `styles.css` set
    `.theme-control { display: none; }` outright in both sub-900px media
    queries. A phone reader had no way to override "system" theme at all.
    **First fix attempt (moving the single control into the nav) surfaced
    a second, genuinely pre-existing bug while verifying live in-browser**:
    `.mainnav`'s base rule (`flex-wrap: wrap`, unconditional) was never
    reset to `nowrap` for the mobile `flex-direction: column` layout, so
    once the offcanvas nav's vertical content got tall enough it wrapped
    into a second *column* instead of scrolling — pushing the last item
    far off-screen to the right (confirmed via `getBoundingClientRect()`
    showing x≈1309 in a 375px viewport). This is not new — it was latent
    before this session and would affect any sufficiently long nav list —
    my own addition was just enough content to trigger it for the first
    time. Fixed at the root (`flex-wrap: nowrap` added to both mobile
    `.portal-nav .mainnav` rules) independently of the theme-control fix,
    since it's a correctness issue in its own right. **Final theme-switcher
    design, after reconsidering the first attempt's desktop side-effect**
    (embedding the control in the wrapping nav-links row pushed the whole
    row over the topbar's available width at common desktop sizes,
    wrapping the nav onto two visual rows — caught by comparing
    `getBoundingClientRect()` y-coordinates before and after, not by eye):
    a second, mobile-only duplicate control (`#theme-select-mobile`,
    class `.theme-select` shared with the original) inside the offcanvas
    nav, hidden on desktop; the original stays exactly where and how it
    was. `theme.js` now applies a theme choice and binds change listeners
    to every `.theme-select` element rather than one hardcoded id, so both
    stay in sync regardless of which one a reader used — verified live by
    changing theme from the mobile control and confirming the desktop
    control's value, `<html data-bs-theme>`, and both charts' rendered
    colours all updated together.
  - **Dead code**: `vendor/leaflet.js` and `vendor/leaflet.css` (162 KB)
    were committed but referenced nowhere in any HTML or JS file, and were
    never listed in `vendor/README.md`'s own table — which the README
    itself calls "the only record of what is actually in the tree,"
    meaning their absence from it was itself evidence they didn't belong.
    Confirmed via grep across the whole frontend before deleting; likely a
    leftover from before the map moved to MapLibre. Also removed the
    matching dead `.nav-tools`/`.nav-tools a` CSS rules found while fixing
    the theme switcher — styled a class that appeared nowhere in
    `index.html` at all.
  - note: **Verified every change live in-browser, not from source reading
    alone** — this cycle hit two bugs (the desktop nav-wrap regression, the
    pre-existing flex-wrap column bug) that source inspection alone would
    not have caught, both found by checking actual computed
    `getBoundingClientRect()`/`getComputedStyle()` values against expected
    viewport bounds after the Browser pane's screenshot tool turned out to
    be unavailable in this environment (no visual compositing) — every
    check in this entry substitutes an equivalent programmatic assertion
    for what would normally be a screenshot comparison. Confirmed: desktop
    nav layout unchanged from before this session (topbar row order and
    y-coordinates match); mobile and tablet (375px, 800px) theme switcher
    reachable, functional, and correctly positioned within the viewport;
    both ECharts fixes produce the theme-correct colour in both light and
    dark mode via `chart.getOption()`, not just source inspection; no
    console errors on any of the five pages touched. No Python changed, so
    the offline suite (`test_portal_isolation.py`, `test_portal_controls.py`,
    `test_web_public.py`, `test_web_authority.py`, docs-coverage tests —
    111 tests) served only as a regression check that nothing server-side
    was affected; it was not expected to catch frontend-only bugs and did
    not need to.
  - possible follow-up: three further findings from the same audit were
    scoped and deliberately deferred rather than rushed — see BETA-019 and
    the two smaller notes in Questions/Deferred below.

- [DONE] BETA-017 | Surface Modules 29-31 as a "Comparators" section on the authority page
  - completed: 2026-08-25T22:30:00Z
  - commits: `a2b4796` (`beta`)
  - result: Direct outcome of the project owner's requested strategic
    reassessment (§52) after BETA-015/016. The reassessment's first check —
    "are users able to actually discover the new functionality" — found a
    real gap immediately: `grep`-ing `pipeline/web/` for the three tables
    Modules 29-31 built this cycle (`rough_sleeping_snapshot`,
    `statutory_homelessness_snapshot`, `temporary_accommodation_snapshot`)
    returned nothing. Three real, requested-as-comparator datasets existed
    only in the database with no way for a portal reader to ever see them —
    exactly the "data additions have outpaced the ability to understand the
    data" failure mode §52 asks a reassessment to check for, and exactly
    the same pattern BETA-009/013 found and fixed for the evidence graph
    and document-analysis subsystems (built, working, entirely invisible).
  - **Scoped to the natural home for a comparator**: the per-authority page
    (`#/authorities/<code>`), where a reader already sees that authority's
    own substance-misuse evidence — adding the comparator datasets there,
    not a new standalone page, keeps the "look at them side by side"
    framing the project owner originally requested these datasets for.
    `public_queries.authority()` gained three new row-fetches (filtered by
    `ons_code`, one per comparator table) and a `comparators` payload key;
    three new `CAVEATS` entries (one per dataset, each independently
    stating the never-combine rule — not one shared caveat, because a
    reader should not have to infer that three differently-limited
    datasets share one limitation). `authority.js` gained a `Comparators`
    section with one small table per dataset, each with its own pinned
    caveat and provenance line, following the exact existing pattern every
    other section on the page already uses (`section`/`pinnedCaveat`/
    `tableCard`/`provenanceFromRows`) — no new component, no new pattern.
  - note: **Verified live in-browser in both states**, not only via tests.
    Against this checkout's real production data (Birmingham, via the
    normal dev server), the empty state renders correctly — an honest "no
    comparators yet" message naming all three modules to run, the same
    convention every other section on this page already uses for absent
    data, since production has never actually run these modules (writing
    to it was never authorised — see the Environment Note). To verify the
    **populated** path, which production cannot currently exercise, built a
    throwaway local SQLite warehouse (`DATABASE_URL= DATABASE_RO_URL=
    DATABASE_SOURCE_URL= DATABASE_PATH=<scratch> pipeline migrate`, the
    override pattern `pipeline/config.py` itself documents), seeded one
    authority and one row per comparator table, and confirmed all three
    tables render correctly with real figures, correct captions, correct
    provenance links, and no console errors — then stopped that server and
    discarded the scratch database. 4 new backend tests (`pytest tests/
    test_web_authority.py`): payload correctness, that all three caveats
    say "never"/"not" in words (not just in code comments — the actual
    reader-facing text), and that an authority with none of this data gets
    an empty list rather than a missing key or an error. Existing authority
    tests (14 total) all still pass.
  - possible follow-up: none identified — this closes the specific gap the
    reassessment found. A future reassessment should check the same
    question again once more datasets accumulate.

- [DONE] BETA-016 | Module 31: H-CLIC temporary accommodation (TA1)
  - completed: 2026-08-25T22:05:00Z
  - commits: `1336770` (`beta`)
  - result: BETA-015's own flagged follow-up, built this cycle. Reads Table
    TA1 (households in temporary accommodation) from the same quarterly
    workbook Module 30 already reads Table A1 from. **Deliberately shares
    Module 30's discovery and file-reading code by direct import rather
    than duplicating it** — both modules read the same evergreen page, the
    same per-quarter attachment list, and the same revision-preference
    rule, which is a genuinely different situation from Modules 13/29's own
    independent `sheet_rows` copies (unrelated sources, coincidentally
    similar code). To make that sharing clean, three of Module 30's
    previously-private helpers (`_to_int`, `_to_float`,
    `_discover_publications`) and one already-touched function
    (`_read_sheet`, renamed `read_workbook_sheet` and parametrised by sheet
    name) were made module-public — a deliberate, documented API surface
    change to an already-shipped module, not an accidental one.
  - **v1 scoped to the top-level figures only**: total households in TA,
    households with children, children in TA, households in area —
    dropping the bed-and-breakfast sub-breakdown (and its own further
    "6 weeks"/"pending review"/"16-17yo" nesting within that), the same
    smallest-coherent-slice discipline Modules 29 and 30 both applied.
  - **Two real bugs found and fixed while verifying against the real
    downloaded workbooks, before either was written into a test**:
    1. A column-matching regex required a word boundary immediately after
       "ta" (`households? in ta\b`). The real source appends footnote
       digits directly with no separating space ("...in TA1,2,3,4"), and
       `\b` does not fire between two word characters — a letter and a
       digit both count. This silently failed to match the true total
       column and let the per-1,000 rate column (whose header text also
       contains "households in ta", just further right) win the claim
       instead — caught only by checking the resolved value (3.78, a rate)
       against the real published England total (88,310), not by the
       regex looking wrong in isolation. Fixed by dropping the trailing
       `\b` from both affected patterns.
    2. A real edition (January–March 2023) publishes Table TA1 under the
       sheet name `TA1_` (trailing underscore) while every other sheet in
       the same workbook, including Table A1, is named normally —
       `read_workbook_sheet` (the shared function) now resolves a single
       unambiguous trailing-underscore variant when the exact name isn't
       found, and still refuses to guess if more than one candidate would
       match after stripping.
  - Follows the established conventions: migration `0061` (SQLite +
    PostgreSQL), licence registration (OGL v3.0, two places), README's
    module table and Wave 1 (alongside Module 30, same `m00` dependency),
    `docs/SOURCES.md`, and a `docs/CAVEATS.md` entry that cross-references
    Module 30's revision/placeholder caveats rather than restating them,
    plus its own notes on the B&B scope boundary and the misnamed-sheet
    fix. Also corrected a line in Module 30's own caveat entry that had
    become stale the moment this module started existing ("temporary
    accommodation ... none of them are in this pipeline").
  - note: **Verified against five real downloaded workbooks directly**,
    not only hand-built fixtures — all five source-file eras/formats this
    cycle has now collected (2019 Q4 ods, 2023 Q1 ods with the misnamed
    sheet, 2023 Q4 ods, 2024 Q1 xlsx, 2026 Q1 ods) resolved every column
    correctly and matched MHCLG's own published England totals exactly
    after both bugs were fixed. 10 new unit tests, including regression
    tests for both bugs found (one exercises `read_workbook_sheet`'s
    fallback directly via an in-memory ODS document built with odfpy, not
    a downloaded file, so it doesn't depend on the scratch directory
    surviving a session boundary). 43 tests across both m30 and m31 pass
    together (the shared-function rename required updating two of m30's
    own existing tests, caught immediately by running them together rather
    than assuming the rename was safe). All five cross-cutting coverage
    guards updated again. Full suite, run clean and uninterrupted (no
    concurrent file edits this time — see BETA-015's own note on why that
    matters): **2434 passed, 106 skipped, 33 deselected, 2 failed** — the
    same pre-existing `transformers`/docling issue, confirmed a fifth time.
  - **What this session could not verify**: an actual live fetch-parse-
    write run, same constraint as every dataset addition this cycle
    (`.env` points at live Railway production).
  - possible follow-up: the B&B breakdown (Modules 30/31 both dropped
    sub-breakdowns this cycle) is a plausible smaller addition to this
    same module later, not a new module — flagged, not queued.

- [DONE] BETA-015 | Module 30: statutory homelessness (H-CLIC) snapshot
  - completed: 2026-08-25T21:40:00Z
  - commits: `5855ac7` (`beta`)
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
  - commits: `47cf21c` (`beta`)
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
| P3 | Module 31: H-CLIC temporary accommodation, TA1 (dataset) | 3 | 3 | 4 | DONE (BETA-016) |
| P2 | Surface Modules 29-31 as a Comparators section on the authority page | 4 | 2 | 5 | DONE (BETA-017) |
| P2 | Frontend UI audit: theme-aware chart colours, mobile theme switcher, dead vendor file | 4 | 3 | 5 | DONE (BETA-018) |
| P3 | Complete-corpus CSV export for PFD reports | 3 | 3 | 4 | DONE (BETA-019) |
| P3 | Compare-page data tables under every chart | 3 | 2 | 5 | DONE (BETA-020) |
| P3 | Typeahead arrow-key nav + aria-activedescendant (6 widgets) | 3 | 3 | 5 | DONE (BETA-021) |
| P2 | Public document search (committee papers + CDP documents) | 4 | 3 | 5 | DONE (BETA-022) |
| P2 | Document search: match-centred snippets, highlighting, result counts | 4 | 2 | 5 | DONE (BETA-023) |
| P3 | Per-route document titles + SPA focus management | 3 | 1 | 5 | DONE (BETA-024) |
| P3 | Document search "show more" pagination (offset through both backends) | 2 | 2 | 4 | DONE (BETA-025) |
| P4 | Quoted-phrase awareness in search snippets/highlights | 1 | 1 | 5 | DONE (BETA-026) |
| P1 | Command palette: unified search (Ctrl-K) | 5 | 3 | 4 | DONE (BETA-027) |
| P1 | Map renders with the network cable unplugged | 4 | 2 | 4 | NEXT (BETA-028) |
| P2 | Overview payload: stop shipping 500 notices for 10 bars | 3 | 1 | 5 | NEXT (BETA-029) |
| P2 | Copy-citation button in provenance drawer | 4 | 2 | 4 | READY (BETA-030) |
| P2 | Homepage first-impression visual | 3 | 3 | 3 | RESEARCH (BETA-031) |

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

- BETA-001, BETA-007, BETA-009, BETA-017 (see DONE above).

## Dataset Additions

**BETA-016: Module 31, temporary accommodation (H-CLIC, MHCLG)** —
BETA-015's own flagged follow-up, built this cycle. Table TA1 from the same
quarterly workbook Module 30 reads, sharing that module's discovery/file-
reading code by direct import. See its DONE entry for the full research,
including two real bugs found and fixed (a regex word-boundary bug, and a
real edition's misnamed `TA1_` sheet).

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

### Provider identifiers hand-verified (`9b3fe06`, `eb1799f`, 2026-08-27)

Project-owner-directed, out of queue. `pipeline/providers.py` (the
reference-config seed for `providers` / `provider_identifiers`) previously
carried exactly one verified identifier — CGL's charity number, from the
brief — with everything else left for Modules 3/4/5 to discover as
`'unverified'`. The owner asked for the details of all 13 tracked
providers to be researched and verified. Now seeded as `'verified'`:

- **Charity numbers** (E&W register) for the 8 comparators that are
  registered charities, and **company numbers** (Companies House,
  8-char form) for those 8 plus Delphi Medical Limited. Every number
  checked against the primary register itself, with the full
  previous-name history read so a rename could not be mistaken for a
  different legal entity.
- **CQC provider IDs** for all 10 distinct entities (including
  `inclusion` = Midlands Partnership University NHS FT, whose CQC id is
  its ODS trust code `RRE`), each checked against the provider's current
  page on cqc.org.uk.

Findings recorded in `PROVIDER_NOTES` and the module docstring:

- Three `provider_key`s are historical names of an entity that also has a
  current-name key — `addaction`→`with_you`, `humankind`→`waythrough`,
  `westminster_drug_project`→`via`. Identifiers live on the current key;
  the historical key stays a bare name variant so a notice bearing the
  old name still resolves to its own row.
- `richmond_fellowship` remains a separately registered charity/company
  but its **CQC** registration was archived 2024-06-04 (services moved to
  Waythrough). `delphi_medical` resolved by the owner to Delphi Medical
  Limited (`06944767` / CQC `1-2448282802`); the predecessor "Delphi
  Medical Consultants Limited" CQC registration was archived 2024-11-15.
- `inclusion` is a service brand of an NHS trust — no Companies House or
  Charity Commission registration.

**Behaviour change this locks in:** `m03` and `m04` seed from
`provider_identifiers`, so they now fetch and fully walk every seeded
entity (Companies House profile / officers / filings / PSC, charity
financials) rather than only what name-search and cross-references turn
up. `tests/test_m04_companies.py` and `tests/test_m04_viability.py` gained
a fixture that scopes which companies each `ch.run()` walks; the
`test_m20` `_add_company_number` helper became `INSERT OR IGNORE` (CGL's
company number is now a seeded row). Full offline suite after both
commits: **2469 passed, 106 skipped**, unchanged 2 pre-existing
`test_documents.py` failures (the corrupted `transformers` cache, see
BETA-007).

**Follow-up flagged:** a scan for substance-misuse providers still
missing from the tracked 13 — Cranstoun (charity 1061582), Changing Lives
(500640, a Collective Voice sponsor), The Alcohol & Drug Service / ADS
Hull (1108595), Spectrum Community Health CIC (07300133), and the
group/NHS-trust and merged-entity long tail. See Questions Requiring
Human Input.

### Provider set expanded to 21; lifecycle status on the portal (`fc97e66`, 2026-08-27)

Project-owner-directed follow-up to the two commits above ("add tiers
1-3", "where a provider has merged / dissolved / renamed make this clear
on the web UI"). Eight `provider_key`s added to
`keywords.SUPPLIER_NAME_VARIANTS` and `pipeline/providers.py`, with the
same hand-verification (primary registers + each provider's current CQC
page):

- **Active national peers:** `cranstoun` (charity 1061582, company
  03306337, CQC 1-101678209), `changing_lives` (500640 / 00995799 / CQC
  1-144519557 — registered as "The Cyrenians Ltd"; a Collective Voice
  member), `alcohol_and_drug_service` (ADS Hull — 1108595 / 05375809 /
  CQC 1-152340136), `spectrum_community_health` (CIC, company 07300133 /
  CQC 1-183173152).
- **Merged, still-registered:** `aquarius` (into the Waythrough group),
  `action_on_addiction` (into The Forward Trust, 2021 — corrected from
  the earlier assumption of With You), `swanswell` (into Cranstoun,
  2022).
- **Dissolved:** `lifeline_project` (administration 2017, company
  dissolved 25 Jan 2024; already an `m04_viability` fixture).

Name collisions checked and documented in `PROVIDER_NOTES`: the Hull ADS
vs Greater Manchester's "ADS (Addiction Dependency Solutions)" (charity
702559, dissolved 2026); "Changing Lives" the charity vs unrelated
"Changing Lives UK Quality Care Limited" at CQC.

Migration `0062` (see Database / Migration Changes) adds
`providers.status` + `providers.superseded_by`, seeded from a new
`PROVIDER_STATUS` map that also formalises the three renames already
tracked (`addaction`, `humankind`, `westminster_drug_project`) and
`richmond_fellowship`. `public_queries.providers()` and
`provider_timeline()` return the status and the successor's display name;
`js/pages/providers.js` renders a lifecycle badge in the provider heading
and a one-line note linking the successor, and a **Status** column in the
provider list ("MERGED → Waythrough"). Verified in a browser against the
running portal. Evidence is never re-pointed onto the successor key — the
note states this.

Full offline suite after the change: **2469 passed, 106 skipped**,
unchanged 2 pre-existing `test_documents.py` failures.

Still open (Questions Requiring Human Input #4): Tier 4, the NHS-trust
comparators beyond `inclusion`/MPFT (CNTW, RDaSH, GMMH, Surrey &
Borders, Humber) — a deliberate scope call, not taken.

### Second expansion — set now 28 (`b64ff10`, 2026-08-27)

Project-owner-directed follow-up ("add 1, 2 except The Nelson Trust, 3,
5"; "continue exploring"). Seven more `provider_key`s, same hand
verification:

- **Absorbed into the Humankind/Waythrough line:** `blenheim_cdp` (large
  London charity, charity 293959 / company 01694712 dissolved 2022 / CQC
  1-516591398; merged 2019) and `edp_drug_alcohol` (Devon/Dorset, charity
  297370 / company 02145656 / CQC 1-587977840; fully merged 1 Jul 2023).
  That line now swallows five prior identities — DISC, Blenheim, EDP,
  Richmond Fellowship, Aquarius — noted in the `waythrough` note and the
  module docstring.
- **Active independent peers:** `bristol_drugs_project` (291714 / 01902326
  / CQC 1-126776288; delivers Bristol ROADS), `developing_health_
  independence` ('DHI', 1078154 / 03830311 / CQC 1-927177975),
  `neca` (North East Council on Addictions, 516516 / 01828287 / CQC
  1-126776368).
- **Subsidiary:** `ley_community` (Oxford residential rehab, charity
  1074874 / company 03736193 / CQC 1-101610029; wholly-owned by Phoenix
  House → `phoenix_futures`).
- **For-profit prison healthcare:** `practice_plus_group` (Health in
  Justice arm, company 10498997 / CQC 1-3757899473; no charity).

Corrections made during verification: KCA merged into **Addaction** (not
CGL); NECA is **independent** (the earlier "merged into Humankind" was
Blenheim). No schema or portal change — 0062's columns and
`js/pages/providers.js` already handle the new merged keys. Full offline
suite: **2469 passed, 106 skipped**, unchanged 2 pre-existing failures.

Further exploration handed back to the project owner (see Questions
Requiring Human Input #4): NHS trusts (Tier 4, still open); `compass`
(York YP + adult charity, 518048 / 02054594); `kca` (Kent Council on
Addictions → `with_you`, historical); residential-rehab charities
(Broadway Lodge, Yeldall Manor, Kenward Trust, Bosence Farm, Trevi, The
Amber Foundation); recovery-support CICs (Emerging Futures, The Well
Communities); historical group brands (Recovery Focus → Waythrough line,
Blue Sky → Forward Trust).

### Third batch — set now 32 (`583476d`, 2026-08-27)

Compass, KCA, Blue Sky and Recovery Focus, from the further-exploration
list above:

- `compass` — active national charity (York, est. 1986; YP-specialist +
  adult substance misuse + wider health), charity 518048 / company
  02054594 / CQC 1-126775082 (CQC name 'Compass - Services To Improve
  Health And Wellbeing').
- `kca` — Kent Council on Addictions (registered 'Kent Council on
  Alcoholism', charity 270532 / company 01955497 'KCA (UK)'). Became a
  wholly-owned subsidiary of Addaction on 1 Jan 2015; company dissolved
  25 Apr 2017. `merged` → `with_you`.
- `blue_sky` — Blue Sky Development and Regeneration (ex-offender
  employment social enterprise, charity 1118372 / company 05639379).
  Merged into The Forward Trust 2017, now 'Blue Sky Services'; company
  dissolved 7 Feb 2023. `merged` → `forward_trust`.
- `recovery_focus` — **not a legal entity**: the group brand for Richmond
  Fellowship + Aquarius (and formerly DViP, 2Care, CAN, Croftlands Trust,
  My Time) from 2015 until the 2024 merger renamed the group 'Waythrough'.
  No registration of its own; seeded with no identifiers. `renamed` →
  `waythrough`. Appears on pre-2024 contracts and CQC quality accounts.

More verification corrections: NECA is independent (not merged into
Humankind — that was **Blenheim CDP**); Recovery Focus, not Aquarius, was
the pre-2024 group brand. `with_you` / `forward_trust` /
`richmond_fellowship` notes updated. No schema or portal change.

**How the reference data lands:** `seed_providers()` runs at the start of
`run()` in m02/m03/m04/m05/m08/m14/m16/m19/m20/m23/m28 — any module run
upserts the new `providers` / `provider_identifiers` rows and the portal
then shows them. `pipeline web` / `pipeline migrate` apply 0062's columns
but do **not** seed. Collecting evidence *for* the new providers (their
Companies House filings, charity accounts, CQC locations, re-matched
notices) needs the collection modules rerun — `m04` walks each
newly-seeded company number, `m03` the charity numbers, `m05` re-matches
by name, `m01`/`m02` re-filter/re-match. `./start.sh backup` then
`./start.sh run all` against the PostgreSQL warehouse (per `.env`). The
LAN Postgres was hand-seeded at the 21-provider stage and will catch up
on the next module run.

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

**Decision: Module 31 imports Module 30's discovery/parsing helpers
directly rather than duplicating them, and four of Module 30's functions
were made module-public (renamed off their leading underscore) to support
that.** Reasoning: unlike Modules 13/29's `sheet_rows` copies — genuinely
independent code that happens to look similar because both read ODS files
— Modules 30 and 31 read the *same* evergreen page, the *same* per-quarter
attachment, and need the *same* revision-preference rule; duplicating that
would create two copies that must be kept in sync by hand, which is a real
maintenance and correctness risk this project's house style (`CLAUDE.md`:
"don't add abstractions beyond what the task requires") doesn't actually
argue against — the task here *is* one shared source. See BETA-016.

## Database / Migration Changes

BETA-014: migration `0059` adds `rough_sleeping_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

BETA-015: migration `0060` adds `statutory_homelessness_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

BETA-016: migration `0061` adds `temporary_accommodation_snapshot` (SQLite +
PostgreSQL dialect trees, kept in sync). Purely additive; no existing table
touched.

Provider-set expansion (`fc97e66`, out of queue, 2026-08-27): migration
`0062` adds two columns to the reference-config `providers` table —
`status` (`'active'` default, or `'renamed'` / `'merged'` / `'dissolved'`)
and `superseded_by` (the surviving entity's `provider_key`, where there is
one). Both dialect trees, kept in sync; `ALTER TABLE ADD COLUMN` with a
default, non-destructive. Seeded from a new `PROVIDER_STATUS` map in
`pipeline/providers.py`. Note: applied to the LAN PostgreSQL warehouse
during this session (a seed script run under `.env`, which sets
`DATABASE_URL`), so that database already carries `0062` + the re-seed —
consistent with the committed code, but done a step ahead of a normal
post-merge run.

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
- BETA-017: a new "Comparators" section on every authority page — three
  small tables (rough sleeping, statutory homelessness, temporary
  accommodation), each with its own pinned caveat and provenance line,
  surfacing Modules 29-31's data for the first time anywhere in the portal.
- BETA-018: chart titles/labels now correctly follow the light/dark theme
  instead of hardcoding a colour that only worked in dark mode; the theme
  switcher is reachable on mobile/tablet for the first time (a second,
  synced control inside the offcanvas nav); a pre-existing flex-wrap bug
  that could push the last offcanvas nav item off-screen is fixed at the
  root, independent of the theme-switcher fix that surfaced it.
- BETA-020: every chart-bearing section on the Compare page (grant, budget,
  treatment × N indicators, contracts, charity, provider contracts) now has
  a `tableCard` data table beneath its chart, matching every other
  chart-bearing page in the portal.
- BETA-021: all six typeahead widgets (council search, provider filter,
  compare's two pickers, treatment's area picker, relationships' two
  pickers) now support arrow-key navigation with `aria-activedescendant`/
  `aria-selected`, not just "Enter picks the first match".
- BETA-022: a new "Document search" page and nav entry — full-text search
  over committee papers and CDP documents, the first search surface over
  document *text* anywhere in the portal (every other search is over
  structured rows).
- BETA-023: document-search results now show the passage that matched,
  highlighted, instead of the top of the page — and say "showing N of M
  matching pages" when the result list is cut. A mid-page match used to be
  invisible: the client truncated from character 0 with no indication the
  page matched anywhere else.
- BETA-024: every route names itself in the browser tab (history entries and
  bookmarks are distinguishable for the first time), and navigating between
  sections hands focus to the page content so screen readers announce the
  change instead of silence. Filter edits deliberately do not move focus.
- BETA-025: document search results longer than one window are reachable —
  an accumulating "Show N more" button under the list, with the count line
  kept truthful as it grows and failures confined to the button's own slot.
- BETA-026: quoted phrases in a search anchor the result snippet and are
  highlighted as one unit. Fixing this properly exposed a real bug: an
  early lone word could drag the snippet window away from the passage that
  matched as a phrase, leaving the phrase outside what the reader saw.
- BETA-027: the command palette — one search box (topbar button, Ctrl-K,
  or "/") across pages, councils, providers and document text, with live
  match-centred document snippets in the results and full keyboard
  navigation. The portal's front door.

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

- BETA-019: extended `tests/test_export_completeness.py` rather than
  writing a new file — it is already the contracts complete-export tests'
  home, and the whole point of this change was "do the same thing again
  for a second endpoint." 14 tests total (10 pre-existing plus 4 new),
  including one pre-existing generic guard
  (`test_every_windowed_endpoint_has_a_complete_reader`) that would have
  failed automatically had `_export_complete` not gained a `pfd` branch.
  Verified against real production data as well as the fixture (the live
  corpus is exactly 1,539 reports) — HIGH end of the brief's own §22 scale
  for touching the export/download path, tested accordingly.
- BETA-018: no Python changed, so the offline suite served only as a
  regression check (111 tests across portal isolation/controls/public/
  authority/docs-coverage — it could not have caught any of this cycle's
  actual bugs, which were frontend-only). All real verification was live
  in-browser: computed `getBoundingClientRect()`/`getComputedStyle()` and
  `chart.getOption()` assertions substituting for screenshot comparison,
  since the Browser pane's screenshot tool was unavailable in this
  environment (no visual compositing). Checked both light and dark theme,
  and three viewport widths (375px, 800px, desktop), for every change.
- BETA-017: 4 new backend tests plus a full live-browser check in both the
  empty and populated states — the populated state needed a throwaway local
  SQLite warehouse since production has never run Modules 29-31 for real
  (see its DONE entry for the exact override commands). MEDIUM risk per
  the brief's own §22 scale: new public API payload fields and a new portal
  section, but reusing existing, already-tested components rather than a
  new rendering pattern.
- BETA-016: 10 new unit tests, two of them regression tests for real bugs
  caught during verification (a regex word-boundary bug, a real misnamed
  sheet). Both m30 and m31's test files run together (43 tests) to catch
  the cross-module breakage the shared-function rename could otherwise have
  caused silently — and did, once, before the two affected m30 tests were
  updated to the new names. Full suite run clean and uninterrupted (no
  concurrent edits, learning from BETA-015's own race artifact): 2434
  passed, 2 pre-existing unrelated failures, confirmed a fifth time.
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
- **From BETA-018's frontend audit, found but not fixed this cycle** (lower
  confidence or bigger scope than the two bugs that were fixed and
  verified; a future session should re-check each against current code
  before acting, the same discipline this file applies everywhere else):
  - ~~The Compare page (`compare.js`) draws charts with no accompanying
    data table~~ — **done, see BETA-020.**
  - The Claims page (`claims.js`) has no search/filter/sort control,
    unlike the Tabulator-backed directory tables elsewhere; only a concern
    if the claims registry is expected to grow past what browser
    find-in-page comfortably handles.
  - ~~The typeahead widgets ... declare full `role="combobox"`/
    `role="listbox"` ARIA but only implement "Enter selects the first
    match"~~ — **done, see BETA-021** (which also found three more
    instances than this note named).
  - Some map/graph JS (`geography.js`'s MapLibre layer paints,
    `providers.js`'s entity-graph colours) uses inline hex literals rather
    than the `--accent-*` CSS custom properties the rest of the stylesheet
    disciplines itself to. Functionally harmless today (the literals match
    the palette); a maintainability nit, not a bug.

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

- **2026-08-26: `refs/heads/beta` was found corrupted** (a file of spaces,
  not a SHA) immediately after the BETA-027 commit, blocking `git push`,
  `git log` and `git status` ("your current branch appears to be broken";
  every file reported as newly staged). Repaired non-destructively by
  rewriting the ref to the verified commit `8da06a6` (chain checked against
  its parent and `origin/beta` before writing); nothing was lost and the
  push then succeeded. Cause unknown — this checkout is shared by several
  sessions (CLAUDE.md), and the corruption happened between a successful
  commit and a push seconds later. If it recurs: verify the commit still
  exists with `git cat-file -p <sha>` before touching anything, fix the
  ref, never re-commit over a broken ref blind.
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
3. ~~**Is a document-search UI (BETA-013's follow-up) worth building, and
   where?**~~ **Answered and delivered, 2026-08-26 (BETA-022):** checked
   rather than guessed — only two source systems are actually bridged into
   the document-analysis schema (committee papers, CDP documents), neither
   with a restricted_ personal-data counterpart; PFD reports and tribunal
   judgments are not in this pipeline at all. Public, scoped to those two
   sources via an explicit allowlist. See its DONE entry for the full
   reasoning and how the allowlist is enforced and tested.
4. ~~**Which further substance-misuse providers should be added to the
   tracked set?**~~ **Tiers 1-3 added, 2026-08-27 (`fc97e66`, see Dataset
   Additions → "Provider set expanded to 21").** Cranstoun, Changing
   Lives, ADS (Hull) and Spectrum Community Health CIC as active peers;
   Aquarius, Action on Addiction, Swanswell and Lifeline Project as
   merged/dissolved entities that still surface in older evidence. Two
   assumptions in the original scan were wrong and were corrected during
   verification: Action on Addiction merged into **The Forward Trust**
   (not With You), and Swanswell into **Cranstoun** in 2022 (not CGL in
   2017). A second batch (`b64ff10`) added Blenheim CDP, EDP, Bristol
   Drugs Project, DHI, NECA, The Ley Community and Practice Plus Group —
   set now 28. **Still open — Tier 4:** NHS-trust comparators beyond
   `inclusion`/MPFT (CNTW, RDaSH, GMMH, Surrey & Borders, Humber, CNWL,
   SLaM, Nottinghamshire Healthcare). The project has one NHS provider as
   the pattern; adding more widens the entity model deliberately and was
   left for the project owner's steer. A third batch (`583476d`) added
   Compass, KCA, Blue Sky and Recovery Focus — set now 32. Still not
   taken: the NHS trusts, the residential-rehab charity sub-sector,
   recovery-support CICs, and the private residential-rehab groups (a
   private-vs-third-sector pay contrast, a separate decision).

## Recent Commits

- `583476d` — add Compass, KCA, Blue Sky, Recovery Focus (set now 32):
  Compass an active charity, the other three merged/renamed into With You
  / Forward Trust / the Waythrough line (out-of-queue,
  project-owner-directed; `beta`). See Dataset Additions.
- `fd82152` — beta.md: record the second provider expansion (`b64ff10`)
  (`beta`).
- `b64ff10` — add 7 more providers (set now 28): Blenheim CDP + EDP as
  merged→waythrough, Bristol Drugs Project / DHI / NECA as active peers,
  The Ley Community as a phoenix_futures subsidiary, Practice Plus Group
  (for-profit prison healthcare) (out-of-queue, project-owner-directed;
  `beta`). See Dataset Additions.
- `2ca03a6` — beta.md: record the provider-set expansion (`fc97e66`) and
  migration 0062 (`beta`).
- `fc97e66` — add 8 more substance-misuse providers (tiers 1-3); portal
  shows renamed / merged / dissolved status with a link to the successor;
  migration 0062 adds `providers.status` / `providers.superseded_by`
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `2b264c2` — beta.md: record the two provider-identifier commits
  (`beta`).
- `eb1799f` — seed hand-verified CQC provider IDs for all 13 providers
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `9b3fe06` — seed hand-verified charity + company numbers for all 13
  providers; scope m04 tests to the companies each run walks
  (out-of-queue, project-owner-directed; `beta`). See Dataset Additions.
- `5adc5e6` — BETA-033: overview hero region map, orchestrated motion,
  scroll reveals; fixed a dead "Current snapshot" section found along the
  way (out-of-queue, project-owner-directed; `beta`).
- `d1f1f43` — beta.md: record BETA-032, fix stale queue notes (`beta`).
- `ef1a4c4` — BETA-032: overview and pay page polish — count-up metrics,
  provider-matched highlights, census removal (out-of-queue,
  project-owner-directed; `beta`).
- `8da06a6` — BETA-027: command palette — unified search across pages,
  councils, providers and documents (`beta`).
- `538095f` — BETA-026: quoted phrases anchor snippets and highlight as a
  unit (`beta`).
- `6db979a` — BETA-025: show-more pagination for document search via offset
  windows (`beta`).
- `f2115d7` — BETA-024: per-route titles and focus handoff on portal
  navigation (`beta`).
- `e8b6ed4` — beta.md: record BETA-023, queue BETA-024 (`beta`).
- `cb4781b` — BETA-023: match-centred snippets and honest result counts in
  document search (`beta`).
- `3f8c74d` — BETA-022: public full-text search over committee papers and
  CDP documents (`beta`).
- `a28b010` — BETA-021: arrow-key navigation and aria-activedescendant for
  every typeahead (`beta`).
- `f566c79` — BETA-020: data tables under every Compare-page chart
  (`beta`).
- `419171f` — mirror: add explicit local PostgreSQL reset (concurrent
  session, `beta`).
- `ece19ae` — BETA-019: complete-corpus CSV/JSON export for PFD reports
  (`beta`).
- `087c1c6` — BETA-018: theme-aware chart colours, mobile theme switcher,
  dead vendor file (`beta`).
- `a2b4796` — BETA-017: surface Modules 29-31 as a Comparators section on
  the authority page (`beta`).
- `1336770` — BETA-016: Module 31, temporary accommodation (H-CLIC)
  snapshot (`beta`).
- `5855ac7` — BETA-015: Module 30, statutory homelessness (H-CLIC) snapshot
  (`beta`).
- `47cf21c` — BETA-014: Module 29, rough sleeping snapshot (`beta`).
- (BETA-010–013 commits landed between `f2b727a` and `47cf21c`; see their
  own DONE entries above for detail — this list was not kept current for
  every intermediate commit, the same disclosed gap as the Candidate
  Feature Backlog table above.)
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

*(Revision after the §52 reassessment, 2026-08-26T16:30Z. Five questions,
answerable without conversational history.)*

**What is currently being worked on?** This paragraph was written before
BETA-027 finished and was not updated at the time — BETA-027 is now DONE
(see above; not re-verified live by this note). Per the queue markers
above, BETA-028 (offline map fallback) is the item marked IN_PROGRESS;
this session did not touch it and cannot confirm how far it got.

**What was the last successful change?** BETA-033 (`5adc5e6`,
2026-08-26T23:32Z): the Overview hero's England region map, orchestrated
page-load and scroll-reveal motion on the Overview and Pay pages, and a
pre-existing dead-section bug fixed along the way — out-of-band from this
queue, the same interactive session's follow-up to BETA-032. See its DONE
entry above, in particular the settled-decision-6 finding: reusing
`/geography`'s live map for the hero was rejected specifically because it
depends on a CDN basemap and a 14MB boundary payload, the exact gap
BETA-028 below exists to close. Whoever picks up BETA-028 may find
`scripts/generate_region_outline.py`'s dissolve-and-simplify approach (or
its output asset) directly useful for an offline fallback, rather than
something to re-derive. Before BETA-033: BETA-032 (`ef1a4c4`); before
that, BETA-027 (`8da06a6`), the command palette.

**What should happen next?** Whichever of BETA-028/029/030/031 the queue
above still shows as not DONE, in that order — this note cannot confirm
which, only that neither BETA-032 nor BETA-033 touched any of them. The
project owner may continue interviewing for further Overview/Pay design
work (BETA-033's own possible follow-up notes a deferred Pay-page
signature visual) — that could land directly as further commits rather
than through this queue, the same way BETA-032/033 did — check `git log`
for anything after `5adc5e6` before assuming the queue below is still the
single source of truth. A live-browser eyeball of BETA-033's motion work
(count-up, page-load sequence, scroll reveal) is still owed — this
session's browser pane could not composite frames for any of the three
sessions that have now hit this same limitation (BETA-024, BETA-027,
BETA-032/033).

**What is blocked and why?**
1. BETA-011 (AI-authored evidence promotion) — waiting on the project
   owner to specify which candidate type it applies to first.
2. BETA-005 (WDTK robots.txt exception) — time-boxed to 2026-09-10 or an
   earlier mySociety reply.
3. BETA-006 (`--jobs 4` re-evaluation) — refused twice for operational/
   scheduling reasons; do not restart without new scheduling information.

**What are the highest-value upcoming items?** BETA-027 (the front door),
BETA-028 (make decision 6 true on the map page), BETA-029 (homepage
payload), BETA-030 (copy citation). A project-owner decision on BETA-011's
candidate type would unblock the queue's most sensitive item.

Do not touch the `m15-web-unlocker`/`zenrows`/`wdtk-html-fallback` branches
without asking — see BETA-004's notes. `docs/upgrade-roadmap.md` claims
should still be checked against actual code before being trusted (BETA-008's
DONE entry records this as a recurring pattern).
