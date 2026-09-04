# Optional Scrapy transport and crawler plan

Status: proposal. This is an implementation plan, not a decision to rewrite
the whole pipeline.

## Decision in brief

Add Scrapy as an optional collection transport and crawler engine. Keep the
current HTTPX modules working, and migrate only the sources that benefit from
Scrapy's scheduler, duplicate filtering, bounded link following or browser
integration.

The default two-second value is a per-host rate interval, not a timeout. It is
not a universal requirement for every future transport, but collection must
remain polite and the selected rate policy must be explicit, source-scoped and
auditable. Scrapy may use a source-specific download delay or AutoThrottle;
HTTPX keeps its current policy until a measured change is approved.

The project continues to require provenance, robots compliance, explicit
failure states, restricted-data boundaries and human promotion. Those are
transport-independent contracts, not features to discard during the migration.

## Why this is worth doing

Scrapy is most useful for the web-crawl portion of the project:

- council, SAB and ICB sites with many pages or links to walk;
- sitemap and index traversal;
- duplicate URL suppression;
- stateful pagination and form workflows;
- source-specific downloader middleware;
- selected JavaScript-dependent pages through `scrapy-playwright`.

It is unlikely to improve API, bulk-file, PDF or derived modules. Those should
remain on the simpler existing path unless profiling gives a specific reason
to move them.

The first candidates are `m09_cdp_documents`, `m10_committee_papers`,
`m24_council_spend`, `m32_sab_site_reviews` and `m34_icb_board_papers`.
`m15_foi` remains a special case: ordinary collection must continue to respect
the WhatDoTheyKnow access boundary, while ZenRows remains an explicit,
off-by-default promotion transport.

## Target architecture

```text
module or spider
        |
        v
transport selection
  |         |          |
HTTPX     Scrapy    ZenRows
                    (m15 promotion only)
              |
              +-- optional scrapy-playwright request
        |
        v
transport result / exact archive record
        |
        v
parser and candidate validation
        |
        v
Scrapy Items or existing module result objects
        |
        v
run-scoped PostgreSQL staging
        |
        v
validated finalisation, review queue and parse failures
```

The first implementation should not make every module a spider. It should
allow a Scrapy-backed module to use the same parser and finalisation code as an
existing module wherever that reduces risk.

## Transport contract

Introduce a small transport-neutral result contract. It should contain at
least:

- requested URL and final URL;
- HTTP status or a typed failure classification;
- response headers safe for storage;
- exact response bytes where a source response was received;
- retrieval timestamp;
- SHA-256 of the exact bytes;
- raw archive reference;
- transport name and relevant configuration/version metadata.

The contract should be implemented by the existing HTTPX path and by the new
Scrapy path. ZenRows can continue to return the same shape as it does today.

Do not make `PipelineHTTPClient` the contract. Make provenance and failure
recording the contract. This removes the current coupling without allowing a
new transport to bypass the evidence rules.

Suggested internal boundaries:

```text
pipeline/transports/httpx.py
pipeline/transports/scrapy.py
pipeline/transports/zenrows.py
pipeline/transports/types.py
```

The existing `pipeline/http.py` may remain as a compatibility facade during
the transition rather than being deleted immediately.

## Conventional Scrapy items and pipelines

Use conventional Scrapy Items for extracted collection results, but separate
three concerns:

### 1. Fetch records

Represent what was actually retrieved:

```text
FetchItem
  run_id
  module
  source_system
  requested_url
  final_url
  status
  retrieved_at
  payload_sha256
  raw_archive_ref
  transport
  failure_class
```

The fetch record is created by downloader middleware or the transport layer,
not by trusting a parser to remember provenance.

### 2. Candidate and finding items

Represent parser output before promotion:

```text
CandidateItem
  run_id
  module
  natural_key
  source_url
  payload_sha256
  parsed_fields
  discovery_method
  review_required
```

The item must carry the fetch record or an immutable reference to it. A parser
must not be able to emit a value without a source reference.

### 3. Review and parse-failure items

Use separate item types for `ReviewItem` and `ParseFailureItem`. A blocked
page, an unrecognised page and a genuine judgement candidate are different
states and must remain distinguishable in the warehouse.

## Persistence strategy

The item pipeline should initially write to run-scoped staging, not directly
to public evidence tables.

Recommended flow:

1. Spider starts a durable crawl run with source, transport and rate-policy
   metadata.
2. Downloader middleware archives exact response bytes and records fetches.
3. Parsers yield candidates, review items and parse failures.
4. Item pipelines validate shape, provenance and restricted-data boundaries.
5. Valid items are written to staging tables with the run ID.
6. A successful run is finalised through existing database functions and
   module-specific natural-key/upsert logic.
7. An incomplete or failed run remains incomplete and cannot present itself as
   a clean empty result.

This gives Scrapy a normal item pipeline while retaining the project's
important distinction between collection, validation and promotion. It also
prevents a process crash halfway through a large crawl from looking like a
successful crawl that found nothing.

Decision for the first pilot (2026-09-04): use the adapter-only path. The m34
pilot returns the same fetch-only crawl shape as the existing module, but does
not write existing evidence tables and does not introduce staging tables.
This keeps the comparison reversible while transport parity is being measured;
the production m34 writer remains HTTPX-backed. A staging design can still be
introduced as a separate migration if a later production cutover needs durable
run-scoped finalisation.

## Rate policy

The fixed two-second interval currently lives in the HTTPX path. Scrapy should
not silently ignore it, and Scrapy's default domain concurrency is not a
replacement for an explicit source policy.

Implement rate policy as source configuration with these fields:

```text
transport
minimum_delay_seconds
maximum_concurrency_per_host
autothrottle_enabled
autothrottle_target_concurrency
retry_after_honoured
```

Rules:

- HTTPX modules retain the current default until changed deliberately.
- A Scrapy source may opt into AutoThrottle or a different delay after a
  source-specific decision.
- The selected values are recorded in the crawl ledger and structured logs.
- A faster policy is never selected automatically because a site returned
  403, 429 or a challenge page.
- Robots restrictions remain restrictions regardless of transport.
- If Scrapy runs in another process, its host limiter must not be assumed to
  share the in-process HTTPX host clock.

For the first pilot, avoid concurrent Scrapy and HTTPX work against the same
host. A PostgreSQL-backed host-rate lease can be added later if independent
worker processes need to share slots.

## Scrapy and Playwright

Use `scrapy-playwright` only on requests that demonstrably need a browser:

```python
yield scrapy.Request(
    url,
    meta={"playwright": True},
)
```

Do not enable Playwright for every request. Browser pages are slower and more
memory-intensive, and a navigation can generate many subrequests.

The browser path needs two representations kept separate:

- the original network response bytes, where available, archived and hashed as
  the source payload;
- the rendered DOM or browser-derived response, archived as a derived
  artefact and never mislabelled as the original source bytes.

For pages whose useful data arrives through XHR or fetch, capture and archive
the relevant response directly where possible. If the endpoint can then be
called with ordinary HTTP, prefer that for subsequent production runs.

Browser execution is not an access-control guarantee. It may recover a simple
JavaScript-dependent page or basic browser challenge, but it must not become a
general Cloudflare bypass or an automatic fallback for blocked sources.

## Optional transports and explicit enablement

All alternate transports should be opt-in and allowlisted by module/source.
Possible configuration shape:

```text
SCRAPY_ENABLED=false
SCRAPY_MODULES=
SCRAPY_PLAYWRIGHT_ENABLED=false
SCRAPY_BROWSER_MODULES=
WDTK_WEB_UNLOCKER_ENABLED=false
ZENROWS_ENABLED=false
```

The exact settings names can be decided during implementation. The important
properties are:

- default behaviour remains the current HTTPX path;
- a source cannot select an alternate transport merely because a person put a
  URL into a field;
- every alternate fetch is visible in logs and the run ledger;
- ZenRows stays restricted to its existing m15 promotion boundary;
- credentials never enter URLs, raw archives or ordinary provenance fields.

## Migration sequence

### Phase 0 — freeze the boundary

- Document the transport result contract.
- Identify every current caller of `PipelineHTTPClient`.
- Separate source-independent archive/provenance code from HTTPX mechanics.
- Add tests proving that missing hashes, archive references or source URLs
  cannot become evidence.
- Record a baseline for representative module wall time, request count,
  bytes, parse failures, review items and memory.

### Phase 1 — add Scrapy without changing modules

- Add Scrapy and `scrapy-playwright` as an optional dependency group.
- Add a minimal runner that can execute a bounded list of requests.
- Add custom downloader middleware for robots, destination guards, raw
  archiving, structured logging and failure classification.
- Return transport-neutral results.
- Keep the normal suite offline and fixture-backed.

At this point, Scrapy is an experimental transport, not the default.

### Phase 2 — first crawl pilot

Port one source with clear crawl value, preferably `m34_icb_board_papers` or
`m32_sab_site_reviews`.

Status: the m34 adapter-only pilot is implemented in
`pipeline/transports/pilots/m34_icb_board_papers_pilot.py`. Offline parity and
provenance coverage are recorded in
`docs/verification/m34-scrapy-pilot-verification.md`; the normal m34 module
still uses HTTPX and no live source is called by CI. The watched Nottingham
sample passed fetch/provenance checks, but its approximately 766 MB peak
working set leaves the production cutover gate open for memory profiling.

- Reuse existing URL discovery and parsers where practical.
- Yield `FetchItem`, candidate, review and parse-failure items.
- Use a bounded scope and a source-specific rate policy.
- Compare the Scrapy result with the existing module on the same fixture set
  and a watched live sample.
- Verify exact archive hashes and deterministic item ordering.

### Phase 3 — browser pilot

Select a small number of known browser-dependent pages from m09/m10. Measure:

- page success versus HTTPX;
- rendered-content correctness;
- original-response/archive completeness;
- elapsed time and peak memory;
- request volume generated by one navigation;
- whether the page is actually JavaScript-dependent or merely bot-blocked.

Do not include WDTK bulk collection in this phase.

### Phase 4 — migrate crawl-heavy modules

Port m09, m10, m24, m32 and m34 only where the pilot shows a benefit. Keep
module-specific parsers and evidence rules, but move request scheduling,
pagination, retries and item validation into shared Scrapy components.

Leave API, bulk-file, derived and stable document modules on HTTPX.

### Phase 5 — decide whether to expand

Only consider a wider migration if the crawl-heavy modules show all of:

- lower development cost for a new source;
- equal or better provenance fidelity;
- no increase in false empty results;
- acceptable memory and operational complexity;
- measurable throughput or coverage improvement;
- passing offline parity and live watched-source checks.

## Testing and acceptance gates

The existing offline policy remains in force. No CI test may fetch a real
source.

Add:

- fake Scrapy downloader responses backed by existing fixtures;
- middleware tests for robots, redirects, destination guards and archive
  hashes;
- item validation tests for missing provenance and restricted fields;
- staging/finalisation tests for successful, failed and interrupted runs;
- Playwright tests with a local fixture server for JavaScript rendering,
  navigation timeout and browser shutdown;
- parity tests comparing HTTPX and Scrapy parser output from identical bytes;
- deterministic ordering tests for items and finalisation;
- rate-policy tests proving a source override is explicit and logged.

The first live pilot should be manually watched and its result captured in a
verification document. It should not be promoted solely because the browser
returned a page.

## Operational requirements

- Browser binaries and Python browser dependencies belong in an optional
  worker image or extra, not the ordinary portal runtime.
- Scrapy runs should have bounded page/context counts and memory monitoring.
- Browser pages must always close in success and error paths.
- A page that times out, is blocked or returns an unrecognised challenge must
  produce a visible failure state.
- Logs remain structured (`log.info("web.<event>")` style); no ad hoc prints.
- The crawl ledger records spider/module, transport, browser usage, rate
  policy, item counts, failures and completion state.
- Raw archives remain immutable and content-addressed.

## Cloud-agent implementation handoff

This document is suitable as the design brief for a later cloud-agent task,
but the agent must be given a bounded phase rather than asked to implement the
whole plan in one pass.

### First implementation task

The first agent task is Phase 0 and Phase 1 only:

- define the transport-neutral result contract;
- extract or wrap the reusable archive/provenance helpers;
- add Scrapy as an optional dependency group;
- add a bounded Scrapy runner and transport adapter;
- add downloader middleware for provenance, archive references, structured
  failure classification and the existing destination guard;
- add fixture-backed tests for the new path;
- leave all production modules on HTTPX.

The first task must not port `m09`, `m10`, `m24`, `m32` or `m34`. Porting a
module is a later task after the transport boundary has been reviewed.

### Explicit non-goals for the first task

The agent must not:

- make Scrapy the default transport;
- change the existing HTTPX rate policy;
- remove or weaken robots compliance;
- add a general 403/429 fallback to Playwright or ZenRows;
- fetch a real external source;
- add a production browser dependency to the ordinary portal image;
- add staging tables unless the transport proof of concept cannot be tested
  without them and the schema change is separately justified;
- rewrite existing modules, parsers, promotion logic or public routes;
- alter `pipeline/web/static/public/**`, `public_queries.py`,
  `public_export.py` or any `/api/v1/*` route.

The agent may add new transport code, optional dependency declarations,
fixture-server tests and focused documentation. It must not stage or modify
unrelated worktree changes.

### Repository and branch protocol

The task should start from the current `beta` branch and use a dedicated
`codex/` branch or worktree. Before editing, the agent must inspect
`git status` and preserve every pre-existing change. It must stage explicit
paths only and report the resulting commit hash.

The agent must not merge, force-push, reset, clean untracked files or modify
deployment configuration without an explicit follow-up task. A later review
task decides whether the proof of concept is ready to merge into `beta`.

### Required first-task deliverables

The agent must return:

1. the transport contract and implementation locations;
2. the feature-flag/default-off behaviour;
3. the exact archive and provenance path for a fixture response;
4. the failure classifications and rate-policy decisions made;
5. the list of files changed;
6. the test and lint commands run, with results;
7. any unresolved decision that needs owner approval.

### First-task definition of done

The phase is complete only when all of the following are true:

- the existing HTTPX path remains the default and existing modules are
  unchanged in behaviour;
- the Scrapy dependency is optional and a normal install does not require a
  browser binary;
- a local fixture server can exercise a Scrapy fetch without network access;
- a successful fixture fetch records the requested URL, final URL, status,
  retrieval time, exact payload hash and archive reference;
- a timeout, block or unrecognised response becomes an explicit failure and
  cannot be interpreted as an empty evidence result;
- missing provenance is rejected before an item can be persisted;
- no fixture or test writes into the repository's real `data/`, `logs/` or
  backup directories;
- the offline pytest suite, Ruff and compilation checks pass;
- the agent has not introduced any live-source test or production default
  change.

### Suggested prompt for the first agent

```text
Implement Phase 0 and Phase 1 of scrapy.md only. Add an optional Scrapy
transport behind a feature flag, preserve the existing HTTPX default, and do
not port production modules yet. Do not fetch live sources. Add
fixture-backed tests proving provenance, exact archive hashing, final URLs,
failure classification, disabled-by-default behaviour and repository write
isolation. Preserve robots, destination-guard and structured-logging
invariants. Inspect git status first, preserve unrelated changes, stage
explicit paths only, run the offline pytest, Ruff and compilation gates, and
stop to report any design decision that requires owner approval.
```

### Later agent tasks

Later work should be split into separate reviewable tasks:

1. approve the transport proof of concept;
2. choose staging tables or the adapter-only persistence path — decided for
   this pilot: adapter-only;
3. port one crawl-heavy module, with parity fixtures — m34 pilot complete;
4. run the watched live m34 pilot and record coverage, timing, memory and archive
   fidelity;
5. add `scrapy-playwright` only for demonstrated browser-dependent routes;
6. port additional modules only after the pilot passes its acceptance gates.

Each task should produce a separate commit or pull request. No task should
assume that a prior experimental transport is ready for public collection
until the owner has reviewed its provenance and rate-policy evidence.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Scrapy bypasses a project invariant | Keep invariants in middleware and item validation, not spider convention |
| Fixed two-second policy is removed too broadly | Make rate policy source-scoped, explicit and logged |
| Browser response is mistaken for source bytes | Archive network response and rendered DOM separately |
| Async Scrapy and PostgreSQL writes interleave unpredictably | Stage by run ID and use one controlled finaliser |
| Browser memory grows during a large crawl | Bound pages/contexts, abort unnecessary assets and monitor RSS |
| A 403 fallback becomes an access bypass | No automatic alternate-transport fallback; use allowlists |
| Full rewrite consumes time without improving coverage | Pilot one crawl-heavy module before porting more |
| Separate processes violate host-level politeness | Initially avoid same-host overlap; add shared leases only when needed |

## Initial estimate

For the optional transport and one pilot:

- 1–2 weeks for the transport contract, Scrapy runner and provenance
  middleware;
- 3–7 days for the first crawler and item pipeline adapter;
- several days for rate-policy, ledger and fixture coverage;
- 1–2 weeks for a browser pilot and operational hardening.

The likely total is 3–5 weeks for a useful, measured pilot. Porting the five
crawl-heavy modules after that is roughly another 2–5 weeks, depending on how
much existing discovery and parser code can be reused.

A full conversion of all modules remains out of scope unless the pilot shows
that Scrapy materially improves the project rather than merely replacing
working API and bulk-file code with a larger framework.
