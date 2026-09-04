# Extensive Project Performance Optimisation Sweep

## Summary

This is an evidence-led roadmap for a substantial performance optimisation sweep across the project.

The highest-priority findings are:

1. Narrative analysis currently materialises roughly 1.4 million passages and can schedule model work for every passage.
2. `analysis_windows` occupies approximately 3.9 GB despite not being consumed after processing.
3. NLP stages repeatedly reprocess unchanged chunks and contain several per-chunk and per-mention query patterns.
4. Cross-domain analysis linking performs an O(n²) comparison over more than 100,000 signals.
5. Large HTTP responses, CSVs, workbooks, and archive objects are repeatedly materialised or reread.
6. The project contains 222 explicit commit sites and several row-at-a-time persistence paths.
7. PostgreSQL stores embeddings twice, as both `bytea` and pgvector.
8. Graph projection uses offset pagination and commits queue items individually.
9. The web server can create more request threads than its eight-connection read pool can service.
10. CI runs the entire offline suite serially.
11. Supporting SQLite and PostgreSQL in parallel now carries measurable complexity: two migration
    trees, runtime SQL translation, compatibility row wrappers, backend branches, transfer tools,
    and schemas constrained to SQLite-compatible representations even though the principal
    deployment uses PostgreSQL.
12. PostgreSQL migrations currently retain many timestamps, dates, booleans, and JSON values in
    compatibility-oriented columns instead of native PostgreSQL types, limiting validation,
    indexing, statistics, and server-side operators.
13. The public portal globally loads roughly 815 KiB of gzip-compressed vendor JavaScript before
    route-specific code. D3 is unused, Fuse serves small typeaheads, Bootstrap JavaScript only
    drives drawers, and MapLibre and Tabulator are loaded on routes that do not use them.
14. The public map can transfer roughly 14 MB of full-resolution boundary GeoJSON even though a
    reader initially needs only the tiles visible at the current zoom.
15. Long-running jobs execute in a daemon thread inside the web process, sharing its CPU, memory,
    connection budget, and failure domain.
16. The hand-written public and admin DOM applications have grown large enough that duplicated
    lifecycle, routing, state, cleanup, and component logic now impedes consistent optimisation.

Python remains the correctness baseline. Mojo remains an optional accelerator for deterministic, CPU-bound kernels. Public API output shapes and exact analytical link semantics must remain unchanged.

## Architecture Decision Review

The following decisions replace earlier project assumptions. They are recorded explicitly so the
performance sweep does not silently discard the reasoning behind either the old or new design.

| Previous choice | Decision for this sweep | Performance consequence |
|---|---|---|
| SQLite by default, PostgreSQL optional | **Reverse: PostgreSQL 18 is the only application database.** | Removes runtime SQL translation, duplicate migrations, backend fallbacks, SQLite writer serialization, and compatibility schema constraints. Tiny operations must be batched or pooled because a network round trip remains slower than a local file operation. |
| pgvector, pg_trgm, and PostGIS optional | **Reverse: require all three extensions.** | Removes sequential-scan and Python fallbacks and makes vector, fuzzy-search, and spatial plans predictable. |
| PostgreSQL-to-SQLite mirror as a recovery path | **Reverse: use verified PostgreSQL-native backup and restore.** | Avoids duplicate storage and full mirror maintenance. Recovery must be proved by restore drills rather than assumed. |
| No frontend framework or build step | **Reverse: adopt Nuxt 4, Vue 3, TypeScript, Nuxt UI, Tailwind CSS, and Vite.** | Adds file-based pages, layouts, accessible components, production template compilation, module tree shaking, route chunks, typed contracts, and consistent lifecycle cleanup. Static/client rendering preserves the Python-only runtime, but Nuxt UI/Tailwind overhead must earn its place against explicit bundle, reactivity, and memory budgets. |
| All browser dependencies loaded globally | **Reverse: import dependencies at the route/component boundary.** | Removes unused D3/date-fns, replaces Fuse and Bootstrap JavaScript, and confines ECharts, Tabulator, MapLibre, and PMTiles to routes that use them. |
| Neo4j is a derived graph projection | **Retain.** PostgreSQL remains canonical and Neo4j remains the deployed, rebuildable projection. | Preserve the original keyset, `UNWIND`, batching, queue, retry, and exact-parity improvements; do not make Neo4j authoritative. |
| Pipeline jobs run in a web-process thread | **Reverse: use a dedicated worker process with PostgreSQL-backed job state.** | Removes CPU/memory/failure contention from the serving process while retaining one-at-a-time pipeline safeguards. |
| Standard-library HTTP server, no ASGI | **Retain initially, then gate.** | Bound and tune the current server first. Consider ASGI only if a same-resource prototype improves p95 by at least 20% after query/cache work. |
| No CDN | **Retain.** | Serve immutable assets efficiently from Caddy or the application origin; no edge dependency is introduced. |
| Provenance, evidence-layer separation, human promotion, restricted-data boundaries, polite collection, and exact analytics | **Retain without qualification.** | Performance work may change execution shape, not evidential meaning or safety boundaries. |

Removing SQLite is not expected to make every individual statement faster. Existing same-data
benchmarks show PostgreSQL winning the expensive portal queries by roughly 3–9x while tiny queries
and row-at-a-time commits can lose to network latency. The transition earns its place by enabling
set-based execution, concurrent writers, native types, mandatory extensions, one schema, and one
test target. Pooling, batching, query consolidation, and co-locating the application and database
therefore become requirements rather than optional refinements.

## Implementation Roadmap

### Implementation status — beta baseline

The roadmap below remains the complete target. This status records only what is
currently landed in beta; **partial** means that a supporting slice exists, not
that the phase is complete. Items not listed as implemented remain unchanged
and outstanding.

| Phase | Status | Landed so far |
|---|---|---|
| Phase 0 — Measurement and safety | **Partial** | `pipeline performance` exposes the named suite interface and deterministic JSON metadata for wall time, CPU time, and digests; the existing web/write benchmark is wired into the `web` and `writes` suites. Full telemetry, browser measurements, mixed-load runs, PostgreSQL/Neo4j instrumentation, and the seven-day baseline remain outstanding. |
| Phase 1 — PostgreSQL-only transition | **Complete** | PostgreSQL 18 is now the sole application/test warehouse: startup requires `DATABASE_URL`, the PostgreSQL migration tree is authoritative, psycopg/psycopg_pool/pgvector are core dependencies, required pgvector/pg_trgm/PostGIS extensions are enforced, SQL uses psycopg-native parameters, psycopg named rows replace the SQLite row wrapper, and SQLite backend/mirror/backup selection has been removed from the application path. The clean PostgreSQL suite, lint, and compilation gates pass. |
| Phase 2 — Analysis and model-call reduction | **Partial — implementation pending acceptance gates** | Stable keyset traversal now feeds PostgreSQL-backed incremental theme counts with bounded ordered evidence, compact resumable input manifests, and an active-only candidate queue; completed detail is digest-validated and removed, while failed detail has a seven-day purge. Model reuse is content-addressed across releases and model workers reuse clients while one database writer batches cache/audit/verifier/signal/cost writes. Exact links use a keyset-batched indexed SQL candidate join, health counts reuse deduplicated operational snapshots, and append-only lineage/final release manifests are exposed to admin diagnostics. Suppression remains disabled until a real adjudicated corpus is recorded and passes the 99%/100% gate; representative human adjudication, same-dataset before/after parity, and a production-sized analysis memory/call/SQL benchmark remain required. The complete PostgreSQL suite, lint, and compilation gates pass on `beta`. |
| Phase 3 — Incremental NLP and semantic search | **Complete** | Stage-state/checkpoint/failure schema and bounded keyset stage wiring, explicit invalidation/`--force`, three-path PostgreSQL retrieval with deterministic RRF, the central pgvector repository, streamed 2,000-row prediction writes, bitemporal/source-change and orthogonal quality schema, the versioned token trie, reproducible parity/latency harness, and the packed Mojo ontology/context ABI with Python fallback are landed. PostgreSQL fixture execution, isolated populated PostgreSQL 18 backup/restore and compaction proof, legacy-column removal, measured semantic parity, and exact ontology/context parity gates are complete. |
| Phase 4 — Shared writes and ingestion memory | **Partial** | `BatchWriter`, batch upserts with unchanged-write suppression, streamed archive interfaces, one-pass HTTP archiving, and a streaming XLSX iterator are implemented. Full adoption across every ingestion/document path and the PDF/CSV/prediction batch flows remain outstanding. |
| Phase 5 — Archive, graph, PostgreSQL, and backend | **Partial** | Graph projection uses keyset pagination and projected columns; relationship writes use grouped `UNWIND`; the web server has bounded workers/queue rejection; public cache misses use single-flight coordination; operational snapshot and durable worker-queue primitives exist. Full archive audits, PostgreSQL maintenance, cross-process invalidation, worker cutover, and all listed operational gates remain outstanding. |
| Phase 6 — Nuxt frontend delivery | **Partial** | The `frontend/` workspace exists with two independent Nuxt 4 apps (public `/`, admin `/admin/`) on Nuxt UI v4/Tailwind v4 and Vue 3.6-rc.6 with `vue.vapor: true` enabled and one Vapor component proving interop. Each app has isolated config/pages/layouts/composables/CSS, a pinned lockfile with reproducible `npm ci`, static `nuxt generate` output with `200.html`/`404.html` SPA fallbacks, hash-history bookmark compatibility, a typed same-origin API client (canonical keys, in-flight dedup, `AbortController` cancellation), URL-authoritative filter state, and versioned browser storage. The public app covers every standalone list route plus the provider/authority entity-detail flows; the admin app has its read-only views and the promote/reject/decide/verify write flows behind the same-origin write guard with a required reviewer identity. A gated deployment cutover seam is in place: a Docker `node:22` build stage compiles both apps and the runtime image copies the static output into `pipeline/web/static_nuxt/` (Node never enters the runtime image), and `SERVE_NUXT` makes the Python server serve the Nuxt apps (public at `/`, admin at `/admin`, `/api` never intercepted) with immutable-asset caching, `200.html` SPA fallback, and a per-page hashed-inline-script CSP — off by default so the legacy portals keep serving as oracles. The public surface now covers every route including the niche ones (pathfinder, timeline, and the notebook/saved/journey reader library over versioned storage), plus a lazy, lifecycle-safe MapLibre choropleth confined to the Places route (markRaw, explicit dispose, origin-only blank-ground rendering). The admin app adds the read consoles (pipeline/exports/search) and the claim-review adjudication write flow. Bundle-budget compliance is now enforced by `frontend/scripts/check-budgets.mjs` (public shared JS ~118 KiB/120, CSS/overview/admin all within budget, MapLibre confined to a lazy chunk and within the 400 KiB map budget, public bundle proven to contain no admin code); Vitest unit tests (transport dedup/cancellation, StLink validation, StStat null-safety) and a Playwright browser smoke gate (shell boot, routing, lazy-MapLibre — fails on any console/hydration/interop error) run in a path-filtered `frontend` CI workflow (typecheck → unit → build → budgets → browser). Remaining: PMTiles vector-tile generation to replace the full-resolution boundary GeoJSON (needs the offline tiling pipeline; the map's GeoJSON source is the seam), the full claims authoring editor (create/update/cite), and pinned Lighthouse LCP/CLS/TBT runs. |
| Phase 7 — CI and regression protection | **Partial** | The new paths have regression coverage and the beta branch has passed the complete PostgreSQL suite plus lint/compile checks. PostgreSQL-native CI, xdist/serial partitioning, browser/build budgets, CodeQL, and repeated clean-run gates remain outstanding. |

**Phase 6 implementation update — 2026-09-04.** The three items listed as
remaining above now have implementation paths in the repository: the admin
claims page is a create/update/cite/decide editor over the existing guarded
claims API; `pipeline pmtiles` derives a deterministic, content-addressed
PMTiles v3 archive and manifest from the canonical authority rows; the public
map reads those archives through bounded HTTP Range requests and the Python
asset server supports immutable caching plus 206 responses. A static frontend
preview server, Lighthouse runner, and budget assertion are also wired into
the frontend CI workflow for pinned LCP/CLS/TBT checks. Acceptance still needs
the normal frontend build/browser/Lighthouse run and an operational deployment
step that generates the archive before the Nuxt static assets are cut over.

This table is descriptive only: it does not remove, reorder, or weaken any
unimplemented requirement in the roadmap or rollout sequence.

### Phase 0 — Measurement, production telemetry, and safety

- Expand `pipeline performance` with suites for `web`, `writes`, `analysis`, `nlp`, `semantic`, `ontology`, `documents`, `archive`, `graph`, `postgres`, `ci`, and `all`.
- Capture wall time, p50/p95 latency, CPU time, peak RSS, rows and bytes processed, SQL statement and transaction counts, cache behaviour, temporary-file usage, model-call counts/cost, accelerator selected, and deterministic output digests.
- Extend the `web` suite with compressed and uncompressed asset sizes, request waterfalls, parse and
  evaluation time, long tasks, Vue component render/update counts, detached nodes, retained heap,
  route-change cleanup, LCP, CLS, total blocking time, and interaction latency.
- Measure complete public/admin page loads as well as individual endpoints: API request count,
  database checkout count, SQL count, JSON serialization/compression time, static bytes, API bytes,
  and time from navigation to meaningful content.
- Add a mixed-load benchmark that holds representative web traffic constant while analysis,
  ingestion, document processing, and Neo4j projection jobs run separately. Record web p95/p99,
  worker CPU/RSS, pool waits, queue delay, and failures.
- Record PostgreSQL round-trip latency and application/database placement with every report so a
  network change cannot be mistaken for a query optimisation.
- Record Neo4j queue depth, projection lag, `UNWIND` batch size/latency, JVM heap/page-cache use, and
  full rebuild throughput without treating projection speed as evidence correctness.
- Use read-only production `SELECT` and `EXPLAIN` for representative plans. Run `EXPLAIN ANALYZE`, write benchmarks, migrations, and destructive experiments only on an isolated production-sized clone.
- Configure a genuine `DATABASE_RO_URL`/reader role for portal, health, benchmark, and inspection connections.
- Enable bounded PostgreSQL telemetry:
  - preload and install `pg_stat_statements`;
  - enable `track_io_timing`;
  - use `compute_query_id=auto` and `pg_stat_statements.track=top`;
  - set subsystem/run-specific `application_name` values;
  - expose only aggregated statement fingerprints and metrics, never bind values or credentials.
- Capture at least seven days of portal traffic and one representative full pipeline/analysis cycle before changing indexes or global PostgreSQL settings.
- Investigate the observed 425 GB of cumulative temporary-file writes by query fingerprint. Fix query shapes first; use per-job `SET LOCAL work_mem` only where measured, rather than raising global `work_mem`.
- Accept an optimisation only when outputs match, repeated alternating A/B runs beat measurement noise, and unrelated benchmark suites show no material regression.

### Phase 1 — PostgreSQL-only platform transition

- Make PostgreSQL 18 the sole supported application database in development, CI, production,
  inspection, and recovery environments.
- Add a pinned Docker Compose development/test service built from the same PostgreSQL image family
  as production, with pgvector, pg_trgm, and PostGIS installed.
- Make `psycopg`, `psycopg_pool`, and the Python `pgvector` adapter normal dependencies rather than
  optional extras.
- Require `DATABASE_URL` at startup. Require a genuine `DATABASE_RO_URL` for deployed portal,
  health, benchmark, and inspection processes; never derive a supposedly read-only connection from
  an owner role in production.
- Fail startup and migration clearly if pgvector, pg_trgm, or PostGIS is unavailable. Remove the
  slow extension-absent production branches only after the capability check and deployment images
  are in place.
- Port all application SQL to psycopg's native `%s` and `%(name)s` parameter styles and remove
  runtime SQL rewriting from `sqldialect.py`.
- Replace the SQLite-compatible custom row wrapper with named psycopg rows. Convert positional row
  access to explicit column names and alias duplicate selected names so result interpretation no
  longer depends on SQLite behaviour.
- Collapse the migration system to the PostgreSQL tree. Remove SQLite connections, PRAGMAs, FTS5
  paths, `sqlite_master` branches, `rowid` ordering, write-slot serialization, SQLite migrations,
  backend selection, and SQLite-specific exception compatibility after cutover validation.
- Remove `pgload`, `pgsync`, `pgmirror`, and SQLite backup/mirror workflows. No SQLite importer will
  be retained: verify that PostgreSQL contains every retained evidence row and archive reference
  before the clean break.
- Replace mirror-based recovery with the project's verified PostgreSQL backup path and a restore
  drill that proves schema, row counts, hashes, extensions, vector indexes, and application reads on
  an isolated server.
- Convert compatibility-oriented columns in stages:
  1. add native `timestamptz`, `date`, `boolean`, `numeric`, `jsonb`, geometry, and vector columns
     where source values can be validated deterministically;
  2. backfill and record invalid/unparseable values without inventing replacements;
  3. compare source and native representations and add constraints/indexes;
  4. switch writers, then readers, while preserving current API serialization;
  5. remove compatibility columns one release later so the previous application image remains a
     rollback option during the transition.
- Preserve verbatim source date/value text beside a native analytical column wherever ambiguity is
  evidentially meaningful.
- Use a stored/generated `tsvector` with GIN for PostgreSQL document search, pg_trgm for fuzzy name
  matching, PostGIS for spatial operations, and pgvector/HNSW for semantic retrieval.
- Use named server-side cursors for large bounded-memory reads. Keep everyday small result sets on
  ordinary cursors because server cursors have their own round trips and transaction lifetime.
- Use psycopg `executemany` for ordinary repeated statements; psycopg already pipelines it, so do
  not wrap a single call in redundant explicit pipeline mode. Use `COPY` separately for measured
  bulk-load paths because COPY is not supported inside pipeline mode. See the
  [psycopg pipeline documentation](https://www.psycopg.org/psycopg3/docs/advanced/pipeline.html)
  and [COPY documentation](https://www.psycopg.org/psycopg3/docs/basic/copy.html).
- Let long-lived pooled connections use psycopg's bounded automatic prepared-statement cache.
  Force preparation for a statement only when repeated-execution benchmarks show a gain, and
  revalidate the setting before introducing a transaction-pooling proxy.
- Prefer `COPY` into temporary or unlogged staging tables followed by set-based merge/validation for
  very large imports. Keep transactions recoverable and checkpoints atomic with the target merge.
- Evaluate BRIN indexes for large physically ordered append-only tables, partial/covering indexes
  for current-row portal queries, and materialized/snapshot tables for expensive canonical
  aggregates only after telemetry identifies a qualifying query.
- Do not introduce declarative partitioning merely because a table is large. Require a demonstrated
  pruning key used by important queries and include vacuum, index, backup, and operational costs in
  the benchmark.
- Treat application/database co-location as the preferred production topology. Where a managed or
  remote PostgreSQL service is used, record round-trip latency and make SQL statement counts an
  acceptance metric.

#### Phase 1 implementation record — beta baseline

The PostgreSQL-only cutover is complete on `beta` and is the frozen starting
point for Phase 2. The application no longer selects a backend at runtime:
`DATABASE_URL` is mandatory, PostgreSQL migrations are applied and recorded in
the live schema, and production read paths require a separate
`DATABASE_RO_URL` SELECT-only role. The local/test compose service and the
documented PostgreSQL image family provision PostgreSQL 18 with pgvector,
pg_trgm, and PostGIS; migration startup checks all three before applying DDL.

The cutover also removed the runtime SQL dialect translator, the custom SQLite
row wrapper, positional database-row interpretation, SQLite aggregate and
backup/mirror paths, and the SQLite writer slot. Production SQL now uses
psycopg-native `%s`/`%(name)s` parameters, named rows, PostgreSQL-native
`string_agg`, `ON CONFLICT`, and PostgreSQL backup/restore verification.

The configured benchmark was recorded as:

```text
sectortrace-mirror performance all --output beta-performance.json
web          measured                     60.648s
writes       measured                     23.499s
analysis     measurement_not_configured    0.000s
nlp          measurement_not_configured    0.000s
semantic     measurement_not_configured    0.000s
ontology     measurement_not_configured    0.000s
documents    measurement_not_configured    0.000s
archive      measurement_not_configured    0.000s
graph        measurement_not_configured    0.000s
postgres     measurement_not_configured    0.000s
ci           measurement_not_configured    0.000s
```

Acceptance evidence on 2026-09-03: `uv run pytest --cache-clear -q`
reported **3,146 passed, 8 skipped, 37 deselected** in 35m24s;
`uv run ruff check pipeline tests` passed; and
`uv run python -m compileall -q pipeline tests` passed. No new Phase 2 work is
included in this cutover; the next implementation boundary is the existing
Phase 2 analysis/model-call reduction section below.

The additions from Phase 2 onward below are additive requirements for reproducibility, evidence
state, and operational visibility. They do not alter, reorder, or expand the existing Phase 0 or
Phase 1 work.

#### Development concurrency and integration

- Phase 0 and Phase 1 are strictly serial. Do not begin Phase 2+ implementation against the
  pre-Phase-1 architecture. Start parallel development only after the PostgreSQL-only baseline has
  passed its gates and has been captured as a frozen integration commit.
- After that baseline, independent Phase 2–7 workstreams may develop concurrently from the same
  validated commit in isolated branches, worktrees, or environments. Parallel development does
  not permit out-of-order integration or deployment; the dependency-aware rollout below remains
  authoritative.
- “Isolated” includes mutable infrastructure, not only Git state. Each workstream receives
  disposable state derived from the frozen baseline: its own PostgreSQL database or schema, archive
  and cache namespace, temporary filesystem, Neo4j test database where needed, generated frontend
  output directory, and benchmark-result namespace. Workers must not share mutable development
  databases, Neo4j projections, archive/cache namespaces, generated outputs, or benchmark folders;
  only the integration lane operates against the shared integration environment.
- Use these workstream boundaries:

| Workstream | May develop concurrently after Phase 1 | Required coordination |
|---|---|---|
| Analysis and release | Phase 2 bounded analysis, prefilter, model cache, window retirement, exact linking, lineage, and release manifests | Establishes lineage, release, document-version, and claim-version identities consumed by later streams. |
| NLP and retrieval | Phase 3 pgvector/HNSW repository, hybrid retrieval, batching, N+1 removal, ontology trie, and Mojo parity infrastructure | Integrate temporal state, lineage references, release identities, and claim-level change tracking only after the Phase 2 contracts are fixed. |
| Ingestion | Phase 4 writer adoption, streaming HTTP/CSV/workbooks, procurement, document persistence, and PDF fallback | Consumes centrally coordinated write, collection-attempt, and quarantine/replay contracts. |
| Archive and graph | Phase 5 archive/cache and Neo4j projection work, separately if useful | PostgreSQL remains canonical; shared archive interfaces and migration changes go through integration. |
| Frontend | Phase 6 public, admin, and specialist map/table work against stable API fixtures and OpenAPI contracts | Keep public/admin isolation and the final legacy replacement as one gated cutover. |
| CI and integration | Phase 7 PostgreSQL fixtures, xdist/serial partitioning, contract checks, CodeQL, browser, Lighthouse, and bundle gates | The integration lane owns rebases, dependency-aware merges, parity reports, and final acceptance. |

- Prefer roughly five to seven active engineering streams at once. Add another stream only when its
  files, contracts, fixtures, and acceptance gates are sufficiently isolated to keep integration
  overhead below the time saved by parallel work.
- Publish versioned contract snapshots from the integration lane for lineage, analytical release,
  document-version, claim-version, and public OpenAPI shapes. Downstream streams consume a named
  snapshot rather than inferring an unfinished contract; changes are reviewed as additive,
  compatible, deprecated, or breaking before dependent work adopts them.
- Assign one integration owner for migration numbering, canonical schemas, shared repository and
  API models, configuration, entity/lineage contracts, output-digest parity, and merge order. No
  parallel worker may independently allocate a migration number or redefine a shared identity.
- Keep final frontend cutover, production deployment, and embedding-table compaction serial. A
  failed or incomplete stream returns to its own branch for correction; it does not force dependent
  streams to consume an unstable contract.

### Phase 2 — Analysis architecture and model-call reduction

#### Evidence lineage and analytical release manifests

- Add a queryable, append-only lineage model covering source, retrieval, archive object, document
  version, element, NLP output, claim, entity, relationship, analysis, and published output. Keep
  PostgreSQL canonical and make any Neo4j representation a rebuildable derived projection. The
  model should be conceptually compatible with the [W3C PROV family](https://www.w3.org/TR/prov-overview/)
  without requiring a separate provenance store.
- Give every analytical and published release an immutable whole-system manifest containing the
  release ID, Git commit, schema and warehouse-data versions, source/archive snapshot and manifest
  hashes, NLP/ontology/rule versions, embedding model and dimensions, entity-resolution and graph
  projection versions, model provider/configuration digest, creation time, and output digest.
- Make release manifests and lineage references available to diagnostics and evidence views so a
  displayed result can be traced back to exact bytes, processing versions, and the output that was
  published. Do not weaken the existing provenance-or-`NULL` rule or restricted-data boundary.

- Replace the exhaustive narrative path with a keyset-paginated, bounded-memory pipeline:
  1. stream active document elements in stable document/sequence order;
  2. feed every passage into an incremental theme accumulator;
  3. apply the versioned deterministic candidate prefilter;
  4. persist only candidate identifiers and checkpoints;
  5. process accepted candidates through bounded model workers;
  6. write results through one bounded database writer.
- Do not hold the full source result set or a duplicate passage list in memory.
- Preserve current theme counts, document counts, subject counts, evidence-sampling order, and output ordering.
- Establish an adjudicated prefilter corpus before suppression is enabled. Require:
  - at least 99% recall across all positive examples;
  - 100% recall for designated rare or critical signal categories;
  - versioned corpus, rules, thresholds, and result digest;
  - shadow-only scoring until the gate passes.
- Replace release-scoped model caching with content-addressed reuse keyed by the exact request identity: role, system and prompt hashes, requested model and fallback chain, generation parameters, provider policy, schema, and cache version.
- Keep immutable per-run audit rows referencing the shared cached response. A cache hit must still count toward run diagnostics but not model cost.
- Reuse one model client and its HTTP connection pool per worker. Model threads return results to a single writer instead of opening and committing private database connections per passage.
- Batch model audit rows, verifier rows, signals, and cost updates. Preserve the existing strict single-worker behaviour when a hard cost ceiling is active.
- Replace `analysis_windows` as a permanent passage ledger:
  - keep run/domain input count, ordered-input hash, configuration hash, prefilter version, progress checkpoint, and output digest;
  - retain detailed candidate/failure records only for active or failed runs;
  - delete completed-run detail immediately after digest validation;
  - purge failed-run detail after seven days while retaining errors, counts, hashes, and checkpoints.
- Before migrating, allow active analysis work to finish or stop it cleanly at a committed checkpoint. Remove existing completed-run window rows and rebuild the reduced indexes.
- Replace `_link_run`’s global pair scan with an indexed SQL candidate join constrained by release, canonical subject, differing domain, relationship rules, and date window. Pass candidates through the existing validation contract and retain every currently eligible link.
- Batch link inserts and use stable left/right ordering to prevent duplicate candidate generation. Do not reduce links to nearest or aggregate relationships.
- Deduplicate analysis health source tables and reuse operational row-count snapshots instead of issuing repeated exact counts.

#### Phase 2 implementation record — beta candidate

Migrations `0094`, `0095`, and the centrally coordinated `0101` contract add
operational snapshots, compact analysis state, content-addressed response
reuse, append-only lineage, and immutable final analytical/published release
manifests. `analysis_windows` remains only as a compatibility/detail table for
work that was active or failed at migration time; new narrative runs persist
candidate identifiers and checkpoints instead of passage rows. Terminal detail
is deleted only after the output digest is recomputed and matches, and the
worker purges failed detail after `FAILED_ANALYSIS_DETAIL_RETENTION_DAYS`.

`pipeline analysis prefilter-eval CORPUS --corpus-version VERSION
--adjudicated-by REVIEWER --record` records an immutable gate result. The
committed offline regression fixture exercises the mechanism and currently
scores 12/12 positive examples (100% overall) and 4/4 critical examples
(100% critical), but it is deliberately not represented as the production
adjudicated corpus. `ANALYSIS_PREFILTER_SUPPRESSION_ENABLED` defaults to false;
even an explicit true value cannot suppress passages unless the persisted
result for the exact rule digest meets both recall bars.

This record does **not** mark Phase 2 complete. Acceptance still requires a
representative human-adjudicated corpus, same-dataset before/after parity for
themes/signals/verifiers/links/audits, and a production-sized memory/call/SQL
benchmark. The complete PostgreSQL offline suite now passes on `beta`.

The reproducible acceptance procedure is documented in
`docs/analysis-phase2-acceptance.md`. `pipeline analysis benchmark-once`
instruments one queued run, `acceptance-capture` records stable semantic
counts/set/order digests and exact model-call diagnostics, and
`acceptance-compare` fails unless both captures use the same ordered inputs and
the correctness outputs retain count, set, and order parity. Measurement names
explicitly distinguish Python allocator/RSS high-water observations and
client-side SQL calls from unavailable server-side telemetry.

### Phase 3 — Incremental NLP, semantic search, and Mojo

#### Phase 3 implementation and acceptance record — 2026-09-04

The populated PostgreSQL 18 acceptance database was backed up, restored into
an isolated target, and verified before and after the embedding compaction
cutover. The target contained 167,779 vectors; the legacy embedding column was
removed only after the restore, row, vector, and audit checks passed. The
populated semantic benchmark exercised eight retrieval cases with exact ID,
order, and score parity (maximum score delta `0.0`); the committed report is
`docs/benchmarks/20260904T045212Z-postgres-semantic.json`. The production
warehouse was not modified. The Linux build gate now verifies exact parity for
both the packed ontology matcher and the deterministic context reduction; the
hand-maintained context regexes remain Python-owned by design.

#### Retrieval, temporal semantics, and source-change intelligence

- Implement hybrid retrieval as separate lexical PostgreSQL full-text, `pg_trgm` fuzzy, and
  pgvector semantic candidates, combined with a documented reciprocal-rank-fusion or equivalent
  reranking policy. Preserve stable IDs, provenance, and deterministic tie-breaking; a retrieval
  rank is not an evidence-quality or truth score. See the [pgvector hybrid-search guidance](https://github.com/pgvector/pgvector#hybrid-search).
- Add explicit bitemporal evidence semantics: source-validity intervals where known, observed or
  effective dates, retrieval timestamps, supersession links, and current/historical state. Preserve
  prior evidence rather than overwriting it when a source changes.
- Detect source changes at the archived-byte, document-version, paragraph/table, entity, and claim
  levels where deterministically possible. Record new, unchanged, modified, removed, redirected,
  and superseded states with hashes and provenance; never interpret a missing source or removed
  passage as proof that the underlying fact no longer exists.
- Add orthogonal evidence-quality assertions such as source authority, extraction quality,
  corroboration state, temporal completeness, and review state. Keep each assertion separately
  queryable and explainable; do not collapse them into a composite score or use them to override
  evidence-layer separation.

- Add a stage-state ledger keyed by stage, input identity/hash, processor version, model or ontology version, and configuration hash.
- Make stages incremental with explicit invalidation:
  - chunking depends on active document-version content and chunker version;
  - labels depend on chunk hash and ontology version;
  - spans depend on chunk hash and extractor/model configuration;
  - context depends on chunk, mention, and cue-rule hashes;
  - relations depend on chunk, span, assertion, and relation-rule hashes;
  - entity resolution reruns only changed or unresolved inputs.
- Cascade invalidation only to downstream state affected by a changed input. Retain explicit `--force` full-rebuild support.
- Process stage inputs with server-side/keyset batches and checkpoint only after each committed batch.
- Remove NLP N+1 persistence:
  - bulk-load mentions/spans/assertions for a chunk batch;
  - resolve entity mention IDs in one query;
  - batch deletes and inserts;
  - preserve per-input rollback and failure attribution.
- In claim prediction, use `executemany` batches of 2,000 per prediction head. Prototype PostgreSQL staging/COPY only if this remains a measured bottleneck.
- Compile ontology aliases into a versioned token trie and process batches of text.
- Pilot the Mojo boundary as packed UTF-8 texts plus offsets to packed concept IDs, spans, counts, and text ordinals. Keep ontology loading, sentence splitting, provenance, orchestration, and persistence in Python.
- Add deterministic context cue scanning to Mojo only after ontology parity succeeds. Regex-only rules remain in Python until exact parity is demonstrated.
- Retain `NLP_ACCELERATOR=auto|python|mojo`; `auto` falls back once with a clear diagnostic, while forced Mojo fails clearly on incompatibility.
- Build Mojo only in supported Linux CI/deployment images. Windows and installations without the extension remain fully supported through Python.
- Make PostgreSQL pgvector/HNSW the only active semantic-search implementation. Query through the
  vector index with stable chunk-ID tie-breaking and preserve exact result IDs/order with score
  tolerance `1e-6`.
- Do not add a Mojo semantic-search kernel to the active PostgreSQL path unless future profiling
  finds a separate deterministic CPU kernel outside pgvector that dominates end-to-end latency.

#### Superseded SQLite semantic-search contingency

The measured SQLite opportunity is retained here because it motivated the original work and remains
the correct contingency if the PostgreSQL-only decision is ever reversed. It is not part of the
active implementation roadmap while SQLite is removed:

- Fetch packed vectors in batches of 4,096.
- Score contiguous float32 matrices rather than unpacking one Python list at a time.
- Retain only bounded top-k candidates and avoid a full result sort.
- Use stable chunk-ID tie-breaking.
- Enable a Mojo semantic kernel only when end-to-end timings, including packing and marshalling,
  beat the improved Python implementation.
- Keep the approximately 30-second/167,779-embedding measurement as the historical baseline rather
  than deleting it when the SQLite implementation is removed.

#### Single-copy PostgreSQL embeddings

- Keep pgvector as PostgreSQL's sole canonical embedding representation. The previous packed
  float32 SQLite representation remains documented only in the contingency above.
- Make the Python `pgvector` adapter a normal dependency and centralise vector conversion behind a
  PostgreSQL embedding repository interface.
- Ensure classifiers, semantic search, and verification code consume the repository interface
  rather than accessing the vector column directly. Remove `pgload` and `pgsync` consumers as part
  of the PostgreSQL-only transition.
- During a maintenance window:
  - pause embedding, NLP, and analysis writers;
  - create a compact replacement PostgreSQL table containing metadata and one pgvector value;
  - copy and validate every row;
  - rebuild the model lookup and HNSW indexes;
  - verify exact row/model/dimension counts, sampled float32 values, semantic result parity, and
    successful reconstruction from the verified PostgreSQL backup;
  - perform a short table swap and resume writers.
- Take the project's normal verified pre-change PostgreSQL backup and complete an isolated restore
  before the table swap. Do not introduce a second embedding copy into the backup format.

### Phase 4 — Shared write path and ingestion memory control

#### Expected evidence and universal quarantine/replay

- Record explicit collection attempts with scope, query or source identity, start/end timestamps,
  result counts, failure class, and coverage state. Distinguish “no matching evidence returned” from
  “the source was not searched, unavailable, or failed”; absence must never be promoted to a claim of
  non-existence.
- Unify parse failures, rejected candidates, failed stage inputs, archive mismatches, and other
  irreducible bad items behind a quarantine/replay contract. Retain item identity, source/run/stage,
  failure class, input/output hashes, first/last-seen timestamps, retry state, and relevant release
  and lineage references. Provide list, inspect, and bounded retry semantics without auto-promotion;
  replay must preserve the original bytes and failure history.

- Introduce a shared `BatchWriter`:
  - commit after 1,000 rows or five seconds, whichever comes first;
  - write the durable checkpoint in the same transaction;
  - flush at clean shutdown;
  - roll back only the current batch on failure;
  - isolate a bad batch by progressively subdividing it and recording irreducible row failures.
- Add cached-shape `upsert_many` support and suppress conflict updates when all stored values are
  unchanged using PostgreSQL `IS DISTINCT FROM` checks.
- Preserve updates where provenance, retrieval timestamps, hashes, or canonical values actually changed.
- Seed static provider reference data once per pipeline run, tracked by a seed-content hash. Keep individual module commands self-sufficient.
- Adopt the shared writer first in measured high-volume paths: document persistence, analysis outputs, NLP outputs, claim prediction, procurement, graph metrics, and HTTP-cache writes.
- Audit remaining explicit commits individually. The old requirement to preserve commits solely to
  release SQLite's writer is superseded; retain a boundary only when it protects checkpoint
  durability, bounds rollback, releases locks before network/CPU work, or is measurably beneficial
  on PostgreSQL.

#### Large downloads and procurement

- Add a context-managed streaming HTTP result for large bodies while retaining the existing byte-based `FetchResult` API for small callers.
- Stream large responses into a spooled temporary file while calculating SHA-256 and byte count once.
- Parse large CSVs directly from the spool with an incremental text decoder; do not construct both complete byte and decoded-string copies.
- Process procurement rows in stable batches of 1,000, bulk-fetch existing OCIDs, and batch sightings, failures, and review items through one writer.
- Keep `CSV_PARSE_WORKERS=1` by default. Permit a bounded producer/consumer parser only when the full archive benchmark demonstrates a gain while preserving source-order checkpointing.
- Turn `xlsx.iter_sheet` into a real iterator under a new streaming API. Preserve the current list-returning API as a compatibility wrapper.
- Update council-spend and Skills for Care imports to inspect and consume one sheet at a time, retain only required columns, and avoid whole-workbook dictionaries.
- Batch document repository deletes/inserts, FTS rows, topic matches, tables, links, and parent updates. Compute hashes and topic matches in the same traversal.
- Batch document title backfills rather than querying and committing one document at a time.

#### PDF extraction

- Benchmark PyMuPDF against pdfplumber on a representative fixture corpus.
- Switch eligible documents to PyMuPDF only when:
  - every document still parses;
  - document, page, element, table, identifier, amount, and date outputs remain equivalent;
  - concept, span, assertion, and relation outputs match;
  - any text differences are limited to formatting that does not change downstream outputs.
- Route failing document classes to pdfplumber automatically and record parser selection/fallback reason.
- Keep the existing content-hash extraction cache. OCR-engine replacement and quality changes remain outside scope.

### Phase 5 — Archive, graph, PostgreSQL, and backend serving

#### Archive and HTTP cache

- Add a stream/file archive-put API returning the exact `ArchiveObject`; callers must not perform a second lookup.
- Store exact archive reference, content type, and content length in the HTTP cache so a 304 retrieves by key rather than prefix listing.
- For S3-compatible storage, capability-test checksum support and send the SHA-256 transport checksum when available. Validate response metadata with an exact HEAD request.
- If the endpoint cannot prove checksum support, fall back to synchronous full verification for that endpoint.
- For filesystem storage, hash during spooling, write to a temporary file, flush, and atomically rename without an immediate full reread.
- Add durable archive-audit results and deployment schedules:
  - daily deterministic 1% sample, with at least 100 objects;
  - complete full-content verification quarterly;
  - alert and quarantine references on mismatch without deleting evidence.
- Batch HTTP-cache writes at 500 entries or worker completion. Cache loss may cause revalidation but must never lose evidence.

#### Graph and exact analytics

- Retain Neo4j as the deployed, derived graph projection. PostgreSQL remains authoritative for
  entities, relationships, claims, evidence, and projection-queue state; Neo4j must remain fully
  rebuildable from those canonical rows.
- Replace graph rebuild `LIMIT/OFFSET` pagination with primary-key keyset pagination and select only projected columns.
- Bulk-fetch graph projection source rows by entity/operation type, use Neo4j `UNWIND` batches, and mark queue results in bounded transactions.
- Preserve retry information for individual failures by subdividing failed batches.
- Group graph-store inputs once by type instead of repeatedly filtering full lists.
- Batch network metric persistence.
- Preserve exact centrality and relationship semantics. Approximate graph algorithms are excluded unless separately approved after a measured benchmark.
- Benchmark Neo4j projection lag, queue depth, rows and bytes per `UNWIND`, transaction time, JVM
  heap/page-cache use, and rebuild throughput without moving public evidence authority into Neo4j.
- Verify exact node, edge, relationship type/property, evidence-reference, path, and metric parity
  after every projector redesign.

#### PostgreSQL maintenance

- Add table-specific autovacuum/analyze thresholds for high-churn derived tables after telemetry establishes update rates.
- Run explicit `ANALYZE` at safe boundaries after major bulk loads.
- Review indexes only after the telemetry observation period. Add or remove indexes based on execution counts, total time, I/O, plans, constraint roles, and rare operational jobs.
- Do not make global memory or planner changes solely from configuration heuristics.
- Re-measure warehouse and index sizes after analysis-window cleanup and embedding compaction before considering surrogate-key or JSON storage redesigns.

#### Backend serving

- Retain and tune the current server architecture first. ASGI is not part of the initial sweep, but
  may be prototyped after the changes below if the server still misses its load targets. Adopt an
  ASGI replacement only when a same-resource A/B test improves p95 by at least 20% without changing
  handlers, queries, payloads, cache policy, or worker counts in the same comparison.
- Replace unbounded request-thread creation with a bounded executor:
  - default eight active workers, aligned with the PostgreSQL read pool;
  - bounded queue of 32 requests;
  - controlled `503` plus `Retry-After` when saturated;
  - configurable independently from pipeline writer concurrency.
- Check route caches before borrowing a database connection.
- Cache serialized identity and gzip response bytes by route, canonical parameters, data version, and content encoding. Do not rerun JSON serialization/compression on a cache hit.
- Add per-key single-flight behaviour and metrics for hits, misses, waiters, queue delay, compute time, serialization time, evictions, and failures.
- Persist expensive operational health calculations in `operational_snapshots`. Serve the latest successful snapshot with age and stale metadata; failed refreshes retain the previous successful value.
- Prototype persisted canonical public summary/contract payloads only if cold-query benchmarks remain dominant. Filtered requests continue through queries and the in-process cache.
- Retain the in-process public response cache for the selected single-web-instance deployment. Do
  not introduce a distributed cache unless horizontal scaling is separately approved.
- Move long-running pipeline jobs out of the web process and into a dedicated worker service:
  - enqueue job identity, arguments, state, and checkpoint durably in PostgreSQL;
  - claim work using `FOR UPDATE SKIP LOCKED`;
  - use a PostgreSQL advisory lock to preserve the current one-overlapping-pipeline-run rule;
  - write bounded, sequenced job events so the existing admin polling experience keeps working;
  - mark or resume interrupted jobs only from committed checkpoints;
  - increment a durable warehouse data version after successful writes so the web cache invalidates
    without sharing process memory with the worker.
- Keep source politeness and source-specific fetch concurrency independent from PostgreSQL writer
  concurrency.
- Benchmark `orjson` only after query, connection, and response-cache improvements. Adopt it only if
  serialization remains at least 20% of request time and byte/shape compatibility tests pass.
- Frontend assets, rendering, and browser performance move into Phase 6 rather than remaining out of
  scope.

#### Pipeline observability

- After worker separation, add OpenTelemetry traces and metrics for pipeline runs, jobs, stages,
  database batches, model calls, archive operations, and graph projection. Correlate spans with
  release, lineage, checkpoint, and quarantine identifiers while keeping structured logs as the
  human-readable event record. See the [OpenTelemetry Python documentation](https://opentelemetry.io/docs/languages/python/).
- Measure queue delay, stage duration, rows/bytes, retries, failures, model cost, archive latency,
  projection lag, and checkpoint age without placing source content or restricted data in telemetry
  attributes.

### Phase 6 — Nuxt 4, Vue 3.6 Vapor, Nuxt UI, Tailwind, and frontend delivery

The framework transition applies to both browser surfaces in one coordinated release and includes
Vue 3.6 Vapor from the first Nuxt prototype. Nuxt is not assumed to be faster merely because it
replaces hand-written DOM code: the production static build must earn the change against explicit
transfer, rendering, interaction, cleanup, memory, and SEO budgets. The detailed product and
migration plan is in `vue-plan.md`; this phase records the performance and delivery contract.

#### Application and package structure

- Create one frontend workspace containing two independent Nuxt 4 applications:
  - a public evidence-atlas application;
  - an admin operations-control-room application.
- Give each application independent Nuxt configuration, entry point, pages, layouts, middleware,
  TypeScript types, components, composables, CSS, and dependency graph.
- Use Nuxt 4, Vue 3.6 Single-File Components, TypeScript, `<script setup lang="ts">`, the
  Composition API, Nuxt UI v4, and Tailwind CSS. Do not use Nuxt 3.
- Enable `vue.vapor: true` in both Nuxt applications from the first prototype. Use
  `<script setup vapor>` or `<template vapor>` for components selected by the compatibility and
  performance gates; this is part of the initial migration, not a later rewrite.
- Use Nuxt's VDOM/Vapor interop mode. Do not use `createVaporApp()`: Nuxt remains the application
  root and the full application continues to use the VDOM runtime where interop requires it.
- Make the Nuxt 4 VDOM migration, route parity, and static delivery the Phase 6 completion gate;
  Vapor is an enabled but non-critical optimization track within that migration. If the pinned
  Vue 3.6/Vapor combination or an interop dependency is unstable, retain the intended component
  boundary and implement the affected components with VDOM so frontend delivery is not delayed.
  Revisit Vapor only through the same measured gate; do not create a second frontend migration.
- Use Nuxt file-based pages and layouts for route organization. Preserve existing hash URLs and
  deep links initially with hash history or an explicit compatibility redirect layer; do not break
  existing `#/route?filters` bookmarks during cutover.
- Keep public and admin runtime imports isolated. The public bundle must not contain admin routes,
  restricted schemas, privileged clients, or operator-only components.
- Retain the legacy applications as test oracles during migration. Switch each surface only after
  parity and performance gates pass.
- Do not use Nuxt server routes as a second backend. The Python standard-library server remains the
  only production runtime authority for APIs, security headers, evidence, writes, and restricted
  data.

#### Vapor and VDOM component boundary

- Use Vapor for simple, performance-sensitive evidence cards, bounded result lists, filters, and
  review rows where direct DOM updates and lower component memory use can be measured.
- Retain VDOM components for Nuxt UI/Reka controls, third-party components, and any component that
  depends on VNodes, the component public-instance proxy, Options API behavior, or another feature
  unsupported by Vapor.
- Keep the public and admin boundaries unchanged across both rendering modes. A Vapor component
  must not import restricted schemas, privileged clients, or operator-only components.
- Treat ECharts, Tabulator, MapLibre, and PMTiles as imperative integrations in lifecycle-safe
  wrappers; rendering mode does not remove the requirement to instantiate, resize, cancel, and
  dispose each instance explicitly.
- Do not place Nuxt UI components inside Vapor components until the actual pinned dependency
  versions pass the browser interop tests.

#### Static rendering and deployment

- Use Nuxt static generation/client-side data loading in the initial deployment. The Python image
  must not run a Node/Nitro server.
- Prerender stable shell, landing, API documentation, catalogue metadata, and selected content that
  is safe to generate at build time.
- Client-load changing warehouse-backed provider, authority, contract, treatment, claims, and
  admin data. Never prerender restricted admin data or embed restricted responses in static assets.
- Render stable titles, descriptions, canonical URLs, navigation, and evidence-state structure for
  dynamic public pages, then fetch current values in the browser. This provides progressive SEO
  without treating mutable warehouse data as static.
- Generate and serve `200.html` and `404.html` SPA fallbacks for dynamic routes. Verify fallback
  behavior through the existing Python server and Railway deployment.
- Add a Node build stage to the Docker image, copy the two Nuxt static outputs into explicit public
  and admin static namespaces, and keep Node out of the final runtime image.
- Serve immutable content-hashed assets with one-year caching and HTML entry points with
  `no-cache`. Keep delivery origin-only and retain the Python static-file fallback.
- Require a reproducible frozen build through `npm ci` or the selected package-manager equivalent.

#### State, data, and lifecycle rules

- Keep URL query parameters authoritative for shareable filters. Preserve current names,
  normalization, defaults, ordering, reset behavior, and deep-link semantics.
- Preserve theme, notebook, saved-search, recent-page, reviewer-preference, and scroll-restoration
  behavior. Version persisted structures and explicitly migrate or discard incompatible state.
- Add separate typed public and admin API clients over a low-level same-origin transport. Verify
  response types against representative API fixtures and `/api/openapi.json`.
- Canonicalize request keys, deduplicate identical requests, and cancel stale route/filter requests
  with `AbortController`.
- Keep any client cache bounded and subordinate to URL and server data-version identity. Nuxt or a
  data library must never become a second source of truth.
- Store large immutable response arrays in `shallowRef`/`shallowReactive` structures and replace
  the root rather than deep-proxying tens of thousands of nested values.
- Wrap ECharts, Tabulator, MapLibre, and PMTiles objects with `markRaw`. Instantiate on mount and
  dispose instances, observers, resize handlers, global listeners, timers, and outstanding fetches
  before unmount.
- Do not render unbounded lists directly through Vue. Keep server pagination and use Tabulator or
  a separately benchmarked virtual list for viewport-scale rendering.
- Use stable props and computed values. Apply `v-once`, `v-memo` in VDOM components, or component
  flattening only where Vue profiling identifies avoidable updates or excessive component
  instances; do not use unsupported directives in Vapor components.
- Add Pinia, VueUse, or TanStack Query only when profiling or demonstrated complexity justifies it;
  do not add them to every route by default.
- Follow [Vue performance guidance](https://vuejs.org/guide/best-practices/performance) for tree
  shaking, lazy chunks, large lists, and deep-reactivity control.

#### Components and redesign

- Use Nuxt UI and its Reka UI primitives for accessible buttons, cards, badges, alerts, skeletons,
  tabs, accordions, drawers, dialogs, popovers, menus, tooltips, selects, comboboxes, command
  palettes, pagination, breadcrumbs, date controls, progress, and toast behavior.
- Use Tailwind for layout and utility styling, but keep SectorTrace-specific tokens and components
  in project source rather than adopting an unchanged dashboard template.
- Build public components for evidence cards, evidence states, provenance, caveats, citations,
  freshness, filters, comparisons, research journeys, saved searches, notebooks, charts, maps,
  tables, exports, and unavailable/no-data states.
- Build admin components for review queues, list/detail panes, decisions, bulk actions, evidence
  sidecars, restricted gates, job status, analysis releases, lineage, schema browsing, SQL, command
  palette, toasts, and keyboard help.
- Expose evidence-quality assertions, temporal/supersession state, source-change findings,
  collection-attempt coverage, release manifests, and lineage explanations as explicit UI states;
  never imply that a missing or unreviewed item is false or absent.
- Keep large table/list components coarse. Avoid replacing one table row with a deep tree of wrapper
  components that increases update and memory cost.
- Preserve route titles, headings, labels, focus movement, keyboard navigation, live regions, mobile
  controls, scroll restoration, browser history, and export/share links.
- Prohibit `v-html` for warehouse or source-derived values. Use escaped interpolation/text bindings
  and a link component that accepts only validated HTTP(S) destinations.
- Preserve the existing rule that public content cannot query or render `restricted_` data.

#### Asset delivery and specialist libraries

- Configure separate Nuxt inputs, CSS splitting, route-level dynamic imports, content hashes, and
  generated manifests. See [Vite backend integration](https://vite.dev/guide/backend-integration.html).
- Lazy-load routes and keep chart, table, map, and admin code out of unrelated common chunks.
- Remove unused D3 and date-fns production assets after parity verification.
- Remove Bootstrap JavaScript and replace drawers with Nuxt UI/Reka-based accessible components.
- Retain Bootstrap CSS only for classes still used, or remove it after the Tailwind redesign passes
  visual and responsive parity checks.
- Replace the complete ECharts build with modular imports for the chart series and renderer actually
  used.
- Import Tabulator only through table components and register only the modules used by current
  filtering, sorting, pagination, responsive, download, and clipboard behavior.
- Import MapLibre, PMTiles support, and map CSS only from geography and CQC route chunks.
- Keep specialist libraries wrapped in lifecycle-safe Vue components rather than rewriting them
  merely to make them “native Vue”.
- Commit package manifests, the lockfile, TypeScript/Nuxt source, verified build manifests, and
  production output if the deployment continues to consume committed static assets.
- Disable production source maps and generate deterministic gzip and Brotli variants for immutable
  text assets.

#### Versioned PMTiles boundaries

- Preserve `/api/v1/boundaries` and its response shape for external API users and exports.
- Generate a topology-preserving PMTiles archive whenever canonical authority boundaries change.
- Record source digest, boundary/data version, generator version, feature count, bounds, zoom range,
  and output digest in a manifest.
- Name the archive by content digest and serve it with byte-range and immutable-cache support.
- Configure the Nuxt MapLibre component to request visible vector tiles rather than downloading the
  roughly 14 MB full-resolution national GeoJSON at map startup.
- Verify feature identifiers/properties, national coverage, adjacency, absence of visible gaps or
  overlaps at representative zooms, and deterministic regeneration.

#### Frontend performance budgets

- Public shared JavaScript, including Nuxt/Vue and routing: at most 120 KiB gzip.
- Shared CSS, including Tailwind/Nuxt UI output: at most 50 KiB gzip.
- Default overview-route JavaScript and CSS before API data: at most 375 KiB gzip.
- Admin initial-route JavaScript and CSS: at most 200 KiB gzip.
- Incremental MapLibre/PMTiles route payload: at most 400 KiB gzip.
- No non-map route may request MapLibre or PMTiles; no non-table route may request Tabulator; no
  non-chart route may request ECharts.
- Preload no more than two above-the-fold font files.
- Under one pinned Lighthouse mobile profile require LCP at most 2.5 seconds, CLS at most 0.1, and
  total blocking time at most 200 ms. Retain the pinned local profile for comparable CI results.
- Compare legacy vanilla routes, VDOM components, and Vapor components after ten repeated
  navigation and interaction cycles. The migrated application must not show monotonic retained-heap
  growth or leave detached chart/map/table nodes, active fetches, timers, observers, or global
  listeners.
- Require Vapor to show a measured benefit on its selected components, or to remain no worse than
  the VDOM baseline within measurement noise. A Vapor result that fails the gate remains VDOM while
  the rest of the coordinated migration proceeds.
- Require route interaction and filter-update latency to beat measurement noise and show no material
  regression on unrelated routes.

### Phase 7 — CI and regression protection

- Record pytest duration data and publish slowest-test and per-module timing artifacts.
- Add `pytest-xdist` and run parallel-safe tests on the single GitHub runner using `--dist loadscope -n auto`.
- Mark tests that share ports, process-global state, fixed paths, databases, or environment mutation as `serial`; run that group in a separate non-xdist step.
- Replace SQLite-backed tests with PostgreSQL behavioural tests rather than deleting their
  coverage. Bootstrap one fully migrated template database and clone isolated databases for xdist
  workers and the separate serial group.
- The previous requirement to retain a small PostgreSQL-driver-only step is superseded when psycopg
  becomes a normal dependency. Run the complete suite once against PostgreSQL rather than running a
  SQLite suite followed by a partial driver suite.
- Eliminate avoidable repeated migrations, model setup, and fixture construction with session-scoped immutable fixtures.
- Run the parallel suite repeatedly before adoption and require ten consecutive clean runs without ordering-dependent failures.
- Keep wall-clock assertions out of ordinary CI. CI performance tests enforce output digests, bounded memory structures, SQL/transaction counts, and complexity-sensitive operation counts; full timing comparisons remain controlled benchmarks.
- Add TypeScript checking and Vue-aware linting over source files.
- Add API contract tests that classify changes as additive, compatible, deprecated, or breaking.
  Preserve existing `/api/v1` shapes and require an explicit compatibility decision before any
  breaking change reaches either Nuxt client.
- Add Vitest and Vue Test Utils coverage for components/composables and Playwright coverage for
  current Chromium, Firefox, and WebKit across both public and admin applications.
- Add browser tests that exercise VDOM-to-Vapor and Vapor-to-VDOM composition, Nuxt UI controls
  around Vapor components, and fail on console errors, hydration/interop warnings, or undisposed
  third-party instances.
- Add pinned Lighthouse runs, bundle-composition reports, compressed-size budgets, route-waterfall
  assertions, lifecycle/memory checks, and tests proving public bundles contain no admin or
  restricted-data modules.
- Verify the committed Vite build with `npm ci && npm run build` followed by a clean-tree comparison
  of the generated manifest and `dist` directory.
- Scan Vue/TypeScript source with CodeQL while excluding generated `dist` and third-party package
  code from project-source findings.
- Keep Mojo verification in supported Linux jobs; PostgreSQL and Python remain sufficient for
  Windows development and non-Mojo runs.

## Interfaces, Schema, and Configuration

- Migration `0094_operational_snapshots`: latest-success payload, capture time, duration, source version, stale state, and refresh error metadata.
- Migration `0095_analysis_performance_state`: input manifests, stage checkpoints, candidate queue, shared model-response cache, model-call cache references, and retention metadata.
- Migration `0096_nlp_stage_state`: stage/input/version/hash state and output digests.
- Migration `0097_archive_refs_and_audits`: exact HTTP-cache archive metadata and durable audit results.
- Migration `0098_postgres_embedding_canonicalisation`: PostgreSQL-only canonical pgvector schema
  and removal of the duplicate PostgreSQL embedding blob after validation.
- Migration `0099_postgres_native_types`: staged native timestamp/date/boolean/numeric/JSON/spatial
  columns, validation state, and compatibility views needed during cutover.
- Migration `0100_job_worker_state`: durable job queue, sequenced events, leases/checkpoints, and
  warehouse data-version state used by the separate worker and web cache.
- Schema ownership is coordinated through the integration lane; do not create or redefine these
  migrations independently in parallel branches:
  - `0101_evidence_lineage_and_releases` is now owned and implemented by the Phase 2 integration
    contract for canonical lineage edges and immutable analytical/published-release manifests;
  - `0102_temporal_change_and_evidence_state` for validity/observation periods, supersession,
    source-change records, and orthogonal evidence-quality assertions;
  - `0103_collection_attempts_and_quarantine` for expected/negative collection outcomes and
    quarantine/replay state.
  The exact split may be revised during schema review, but numbering, identity definitions, and
  compatibility views remain centrally coordinated.
- New internal interfaces:
  - PostgreSQL-native connection/repository API using named rows and psycopg parameters;
  - `BatchWriter.write/flush/checkpoint`;
  - `upsert_many`;
  - context-managed streamed HTTP result;
  - archive put-from-stream/file returning `ArchiveObject`;
  - streaming workbook-row iterator;
  - PostgreSQL pgvector embedding repository;
  - lineage and immutable analytical-release-manifest repository;
  - hybrid lexical/fuzzy/semantic retrieval contract with deterministic rank fusion;
  - collection-attempt and quarantine/replay interfaces;
  - separate typed public and admin API clients;
  - Nuxt route/layout/middleware and filter/storage composables;
  - Nuxt UI/Tailwind-based chart, table, map, typeahead, provenance, evidence, and error-state
    component contracts;
  - separate public/admin Nuxt manifests and immutable-asset resolver;
  - PMTiles build manifest and range-serving contract;
  - PostgreSQL-backed job queue and worker claim/checkpoint interface.
- Principal settings:
  - `BATCH_WRITE_ROWS=1000`
  - `BATCH_WRITE_SECONDS=5`
  - `HTTP_CACHE_WRITE_BATCH_SIZE=500`
  - `CSV_PARSE_WORKERS=1`
  - `PREDICTION_WRITE_BATCH_SIZE=2000`
  - `NLP_ACCELERATOR=auto`
  - `FAILED_ANALYSIS_DETAIL_RETENTION_DAYS=7`
  - `WEB_WORKERS=8`
  - `WEB_QUEUE_SIZE=32`
  - `OPERATIONAL_SNAPSHOT_MAX_AGE_SECONDS=900`
  - `ARCHIVE_AUDIT_SAMPLE_PERCENT=1`
  - `ARCHIVE_AUDIT_MIN_OBJECTS=100`
  - `JOB_WORKERS=1`
  - `JOB_EVENT_RETENTION_LINES=4000`
- Remove SQLite database-path/backend-selection, mirror, and SQLite write-slot settings after the
  final cutover. Remove no Neo4j setting: Neo4j remains the deployed derived projection.
- Frontend package/build configuration belongs in the Nuxt/Vite/TypeScript files and lockfile rather
  than environment variables. Runtime configuration is limited to resolving the committed asset
  manifest, current PMTiles digest, and public/admin base URLs.
- Public `/api/v1` success response shapes remain unchanged. Admin health responses may add performance, snapshot-age, staleness, and refresh-error fields.

## Verification and Rollout

- Develop independent Phase 2–7 streams concurrently only after the frozen Phase 1 baseline, but
  integrate and deploy them through dependency-aware gates while capturing before/after reports
  against the same commit-adjacent dataset. The rollout order below remains serial where it changes
  shared schemas, contracts, production assets, or runtime ownership.
- Before removing SQLite, run the existing SQLite/PostgreSQL equivalence and migration checks one
  final time against the retained dataset and record the digest as the cutover baseline. After the
  clean break, require PostgreSQL migration/restore equivalence, rollback behaviour, dry-run
  guarantees, cancellation at batch boundaries, and interruption/resume coverage.
- Compare analysis manifests, themes, signals, verifier results, cross-source link sets, and model-audit records before and after the redesign.
- Assert the narrative prefilter’s 99% overall and 100% critical-category recall before enabling suppression.
- Require exact semantic-search IDs/order with score tolerance `1e-6`.
- Verify hybrid retrieval candidate provenance, deterministic rank fusion, stable result IDs/order,
  and no contamination of evidence-quality or truth semantics by retrieval ranking.
- Verify lineage is complete for representative source-to-published-output paths and that an
  analytical release can be reproduced from its manifest, hashes, and pinned processing versions.
- Verify temporal/supersession state and source-change classifications across unchanged, modified,
  removed, redirected, and unavailable-source fixtures without converting absence into a claim.
- Verify collection-attempt coverage and quarantine list/inspect/retry behavior, including original
  byte preservation, bounded retries, failure history, and the no-auto-promotion rule.
- Require row-for-row ontology/context outputs, including Unicode, punctuation, overlapping aliases, plural folding, negation, and termination cues.
- Verify incremental NLP reruns perform no derived writes for unchanged inputs and correctly invalidate every affected downstream stage after controlled changes.
- Test large-download interruption, archive checksum capability fallback, 304 restoration, audit mismatch handling, CSV resume, and workbook/PDF fallback.
- Test web cold/warm paths, concurrent cache misses, saturation, queue rejection, database-pool exhaustion, compression variants, and cache invalidation.
- Test worker crash/restart, advisory-lock exclusion, `SKIP LOCKED` claims, sequenced log polling,
  checkpoint resume, and cross-process cache-version invalidation.
- Verify every parallel workstream uses isolated mutable databases, archive/cache namespaces,
  generated outputs, and benchmark results, while only the integration lane uses shared state.
- Verify versioned lineage, release-manifest, document-version, claim-version, and public-API
  contract snapshots are reproducible and that dependent streams do not consume unstable contracts.
- Validate Neo4j projection restartability, exact node/edge/link/path/property parity, projection lag,
  and individual error recovery from failed `UNWIND` batches.
- Test every existing public/admin route, hash URL, query parameter, bookmark, browser-storage
  structure, keyboard interaction, focus transition, loading/error state, and export link against
  the legacy interface before the coordinated Vue cutover.
- Test Nuxt static generation, `200.html`/`404.html` fallbacks, stable public metadata, dynamic
  client-loaded evidence pages, admin client-only data, and absence of a Node/Nitro runtime in the
  production image.
- Assert that route network waterfalls obey the ECharts/Tabulator/MapLibre/PMTiles boundaries and
  all compressed bundle budgets.
- Test PMTiles byte ranges, cache headers, deterministic regeneration, map feature/property parity,
  representative zooms, and fallback behaviour while retaining `/api/v1/boundaries` unchanged.
- Run ten repeated Vue navigation cycles under heap and detached-node observation and fail on
  monotonic retained-memory growth or undisposed third-party instances.
- Verify Phase 6 can complete its Nuxt/VDOM parity and static-delivery gates with selected components
  held in VDOM when Vapor or an interop dependency fails its compatibility or measured-benefit gate;
  this fallback must not create a second frontend migration.
- Deploy in this order:
  1. PostgreSQL/frontend telemetry and PostgreSQL test infrastructure;
  2. PostgreSQL-only application path and mandatory extension checks;
  3. staged native PostgreSQL columns and final SQLite/PostgreSQL parity capture;
  4. SQLite runtime/migration/mirror removal;
  5. analysis architecture and model-call changes;
  6. ingestion, NLP, archive, Neo4j projection, and write-path changes;
  7. complete both Vue applications and run legacy parity/browser/performance gates;
  8. atomically cut over public/admin assets with PMTiles and origin static serving;
  9. move jobs to the dedicated worker and perform final PostgreSQL tuning;
  10. compact embeddings during a maintenance window only after conversion, semantic-parity, and
      restore tests pass.

## Assumptions and Boundaries

- PostgreSQL 18 with pgvector, pg_trgm, and PostGIS is available in development, CI, production,
  and recovery. PostgreSQL/pgvector HNSW is the sole active semantic-search path.
- Existing SQLite-only data does not require import. The former SQLite semantic/Mojo design remains
  documented as contingency history rather than active scope.
- Neo4j remains the production derived graph projection; PostgreSQL remains its canonical source.
- Python remains mandatory and authoritative; Mojo is optional, rollback-safe, and limited to
  deterministic kernels that pass exact parity gates.
- Nuxt 4, Vue 3.6 with Vapor, TypeScript, Nuxt UI, Tailwind CSS, and Vite replace both browser
  applications in one coordinated release. Nuxt uses static/client rendering with VDOM/Vapor
  interop initially; full SSR/Nitro remains a separately approved future deployment option.
- Node is required for frontend development and reproducible builds only. The final production
  container and ordinary Python startup remain independent of Node.
- Deployment remains one public web instance plus separate worker processes. Assets remain
  origin-served; CDN and edge caching are excluded.
- Exact analytical links, deterministic NLP outputs, provenance, idempotency, public/admin and
  restricted-data isolation, human review, and source politeness limits are non-negotiable.
- Production inspection is read-only; all write experiments use an isolated clone.
- Completed analysis-window detail is discarded; failed detail is retained for seven days.
- Archive verification uses immediate checksums plus daily sampling and quarterly full audits.
- The standard-library server is tuned first. ASGI remains a conditional, separately benchmarked
  replacement rather than an assumed improvement.
- Approximate graph algorithms, OCR-engine replacement, evidence semantics, public API redesign,
  and geometry/name-matching quality rewrites remain excluded unless separately approved. PMTiles
  changes delivery and display geometry only; it does not replace canonical boundaries.
- Evidence lineage, release manifests, temporal state, source-change intelligence, expected-evidence
  records, quarantine/replay, and OpenTelemetry are additive operational/evidence controls; they do
  not authorize composite evidence scoring, automatic promotion, or a new public API shape.

## Original-Plan Traceability

This section is the preservation audit for the roadmap that existed before the PostgreSQL/Vue
expansion. An implementation must not treat “expanded” or “superseded” as permission to drop the
underlying measurement or acceptance rationale.

| Original requirement group | Disposition | Destination |
|---|---|---|
| Performance suites; wall/CPU/RSS/row/byte/SQL/transaction/cache/temp/model/accelerator/digest telemetry | **Expanded** | Phase 0 adds browser, bundle, worker, page-level checkout, Neo4j lag, and PostgreSQL round-trip metrics. |
| Read-only production inspection; clone-only writes; seven-day telemetry; query-fingerprint temp-file investigation; A/B acceptance | **Retained** | Phase 0. |
| Bounded narrative streaming and incremental themes | **Retained** | Phase 2. |
| Candidate prefilter corpus, 99% overall recall, 100% critical recall, versioning, shadow gate | **Retained** | Phase 2. |
| Content-addressed model cache, immutable audit references, client reuse, one writer, batching, hard-ceiling serial mode | **Retained** | Phase 2. |
| `analysis_windows` manifests/checkpoints/digests, completed-detail deletion, seven-day failed retention | **Retained** | Phase 2. |
| Indexed exact cross-domain linking, stable pair order, batched inserts, deduplicated health counts | **Retained** | Phase 2. |
| NLP stage ledger and complete dependency/invalidation graph | **Retained** | Phase 3. |
| Server/keyset batches, committed checkpoints, N+1 removal, per-input rollback, 2,000-row prediction batches | **Retained** | Phase 3. |
| Token trie and packed Mojo ontology/context boundary with Python fallback and parity gates | **Retained** | Phase 3. |
| SQLite batch/top-k/Mojo semantic kernel | **Superseded, rationale preserved** | Phase 3 contingency; active path is mandatory pgvector/HNSW. |
| Single-copy embedding storage and maintenance-window validation | **Expanded** | Phase 3 uses one pgvector value and PostgreSQL restore validation. |
| `BatchWriter`, 1,000-row/five-second flush, atomic checkpoint, batch subdivision | **Retained** | Phase 4. |
| Cached-shape upserts and unchanged-write suppression | **Expanded** | Phase 4 uses PostgreSQL `IS DISTINCT FROM`. |
| Seed hashing, high-volume adoption order, and explicit commit audit | **Expanded** | Phase 4; SQLite-only release boundaries are replaced by PostgreSQL transaction criteria. |
| Streamed HTTP/spooling, one-pass hash, incremental CSV, procurement batches, source-order checkpointing | **Retained** | Phase 4. |
| Streaming workbook API, sheet-at-a-time imports, batched document writes/backfills | **Retained** | Phase 4. |
| PyMuPDF/pdfplumber corpus, full downstream parity, automatic fallback, extraction cache | **Retained** | Phase 4. |
| Exact archive put result, 304-by-key, transport checksum capability, HEAD validation, filesystem atomic rename | **Retained** | Phase 5. |
| Daily 1%/minimum-100 audit, quarterly full audit, mismatch quarantine, 500-entry cache writes | **Retained** | Phase 5. |
| Neo4j keyset projection, projected columns, bulk fetch, `UNWIND`, bounded transactions, failed-batch subdivision | **Retained and expanded** | Phase 5 keeps Neo4j deployed and adds lag/heap/rebuild measurements. |
| One-time graph grouping, metric batches, exact centrality/relationship semantics, no approximation | **Retained** | Phase 5. |
| Table-specific autovacuum/analyze, bulk-load `ANALYZE`, evidence-led indexes, no heuristic global tuning | **Retained** | Phase 5 plus PostgreSQL-native opportunities in Phase 1. |
| Eight web workers, queue 32, controlled 503, cache-before-connection, serialized/gzip cache, single flight | **Retained** | Phase 5. |
| Operational snapshots and conditional persisted public payloads | **Retained** | Phase 5. |
| Frontend/browser exclusion | **Superseded** | Phase 6 supplies the Nuxt 4/Vue 3/Nuxt UI/Tailwind/Vite/PMTiles implementation and budgets. |
| Serial CI timing, xdist/loadscope, serial group, fixture reuse, ten clean runs, structural performance assertions | **Retained and expanded** | Phase 7 adds PostgreSQL isolation and Vue/browser/build gates. |
| PostgreSQL-driver-only follow-up test step | **Superseded** | Phase 7 runs the complete suite once with PostgreSQL as the normal dependency. |
| Migrations 0094–0098 and original internal interfaces/settings | **Retained and expanded** | Interfaces section preserves them, adapts 0098 to PostgreSQL-only, and adds 0099–0100 plus centrally owned future 0101–0103 schema slots and frontend/worker interfaces. |
| SQLite/PostgreSQL equivalence | **Superseded after one final gate** | Verification records the final cutover digest; subsequent regression testing is PostgreSQL-only. |
| Analysis/NLP/semantic/download/archive/web/graph verification matrix | **Retained and expanded** | Verification adds worker, Vue, bundle, memory, PMTiles, PostgreSQL restore, and detailed Neo4j parity tests. |

## Post-roadmap platform and package upgrade candidates

This is an additive, non-blocking register for upgrades considered after the existing Phase 0–7
roadmap. It does not create a new phase, reorder delivery, replace the PostgreSQL 18 baseline, or
repeat the Vue/Vapor decision already made in Phase 6. Version numbers are a review-time snapshot;
recheck the lockfile and release status before implementation.

### PostgreSQL 19

PostgreSQL 19 is a later candidate against the PostgreSQL 18 platform target. Potential benefits
for this project include:

- planner improvements for anti-joins, aggregation before joins, incremental sorts, and nullable
  comparison expressions;
- improved asynchronous I/O and automatic I/O-worker scaling for large scans;
- parallel autovacuum and improved maintenance prioritisation;
- concurrent `REPACK` for reclaiming bloat without blocking ordinary reads and writes;
- faster text/CSV `COPY` ingestion and foreign-key checks;
- lock, recovery, progress, and `EXPLAIN` I/O observability useful to the Phase 0 telemetry;
- `WAIT FOR LSN` if read replicas are introduced and read-your-writes behavior is required.

These are workload-dependent improvements, not guaranteed multipliers. SQL/PGQ does not replace
Neo4j, which remains the derived graph projection. Test PostgreSQL 19 only on an isolated
production-sized clone and accept it only after row-count, hash, API-output, analytical-link,
semantic-search, backup/restore, web, ingestion, and worker parity checks pass. PostgreSQL 19 must
not delay the PostgreSQL 18 cutover.

See the official [PostgreSQL 19 release notes](https://www.postgresql.org/docs/release/19.0/).

### Suggested package updates

The following candidates were identified from the current `uv.lock` and should be handled as
separate, reviewable maintenance changes:

| Package | Review-time candidate | Benefit and gate |
|---|---|---|
| `psycopg` | 3.3.4 → 3.3.5 | Low-risk correctness fixes for prepared statements, `COPY`, JSONB/data errors, and duplicate named rows; run the PostgreSQL suite. |
| `pydantic` | 2.13.4 → 2.13.5 | Patch-level reliability update; no performance claim; run settings and API validation tests. |
| `python-dotenv` | 1.2.2 → 1.2.3 | Patch-level maintenance update; run startup/configuration tests. |
| `boto3` | 1.43.72 → 1.43.87 | Storage-extra maintenance/security refresh; run archive backend tests. |
| `ruff` | 0.16.2 → 0.16.5 | Development-only refresh; run lint without rewriting unrelated files. |
| `google-auth` | 2.56.3 → 2.57.0 | Sheets-extra maintenance refresh; run the offline sheets tests. |
| `pypdfium2` | 5.12.1 → 5.13.0 | OCR-extra maintenance refresh; run OCR/document fixture tests. |
| `neo4j` | 6.2.0 → 6.3.0 | Measured upgrade; require exact projection parity, restartability, and failed-batch recovery. |
| `docling` | 2.120.3 → 2.124.0 | Measured document-worker upgrade against the representative corpus and PyMuPDF/pdfplumber. |

Hold the following versions or upgrade paths until their compatibility gates are resolved:

- keep `httpx` on the 0.28.x line and add an eventual `<1` upper bound before HTTPX 1.0 becomes
  stable;
- keep the OpenAI client below 2 while the assistant remains an optional OpenRouter-compatible
  feature;
- do not move to `sentence-transformers` 6 or `transformers` 5 until the SetFit compatibility
  constraint is replaced or removed;
- do not move ONNX Runtime beyond the Python 3.10-compatible ceiling unless OCR moves to a
  separately tested Python 3.11+ worker;
- retain `odfpy` and the project’s streamed XML ODS reader because no newer `odfpy` release solves
  the large-document memory problem.

When the frontend lockfile is introduced, pin Vue 3.6, Nuxt 4, Nuxt UI, Tailwind CSS, and their
Vapor-compatible toolchain as one tested version matrix, as required by Phase 6.
