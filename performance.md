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
| No frontend framework or build step | **Reverse: adopt Vue 3, TypeScript, Vue Router, and Vite.** | Enables production template compilation, module tree shaking, route chunks, typed contracts, and consistent lifecycle cleanup, but introduces a bundle and reactivity budget that must be measured. |
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

### Phase 2 — Analysis architecture and model-call reduction

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

### Phase 3 — Incremental NLP, semantic search, and Mojo

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

### Phase 6 — Vue 3, Vite, and frontend delivery

The framework transition applies to both browser surfaces in one coordinated release. Vue is not
assumed to be faster merely because it replaces hand-written DOM code: the production build must
earn the change against explicit transfer, rendering, interaction, cleanup, and memory budgets.

#### Application and package structure

- Create one frontend workspace with:
  - a public Vue application;
  - an admin Vue application;
  - independent entry points, routers, TypeScript configurations, and dependency graphs;
  - a deliberately small shared layer for safe transport, formatting, and presentational code.
- Use Vue 3 Single-File Components, TypeScript, `<script setup lang="ts">`, the Composition API,
  and Vue Router.
- Use the runtime-only production build so browser bundles do not contain Vue's template compiler.
- Do not add Pinia, Vue Query, Nuxt, server-side rendering, hydration, or a Vue component framework
  in this sweep. Shareable state already has a durable home in the URL; local component/composable
  state is sufficient until profiling demonstrates otherwise.
- Use `createWebHashHistory()` so all existing `#/route?filters` links, bookmarks, filter state, and
  server routing continue to work. See the
  [Vue Router hash-history API](https://router.vuejs.org/api/functions/createwebhashhistory).
- Migrate public and admin together and switch both entry points atomically. Keep the legacy
  applications as test oracles during development, not as a parallel production mode.
- Enforce the public/admin boundary at build time: the public entry and every transitive import must
  be unable to import admin routes, restricted schemas, privileged clients, or operator-only
  components.

#### State, data, and lifecycle rules

- Keep route query parameters authoritative for shareable filters and preserve their current names,
  normalization, defaults, ordering, reset behaviour, and deep-link semantics.
- Preserve existing storage behaviour for theme, notebook, saved searches, recent pages, and
  session scroll restoration. Version persisted structures and migrate or discard incompatible
  client state explicitly.
- Add separate typed public and admin API clients over a shared low-level same-origin transport.
  Define TypeScript response interfaces and verify them against representative API fixtures.
- Canonicalize request keys, deduplicate simultaneous identical requests, and cancel stale route or
  filter requests with `AbortController`.
- Keep the client response cache bounded and subordinate to URL and server data-version identity;
  never let a framework cache become a second source of truth.
- Store large immutable response arrays in `shallowRef`/`shallowReactive` structures and replace the
  root on change rather than deep-proxying or mutating tens of thousands of nested values.
- Wrap ECharts, Tabulator, MapLibre, and PMTiles objects with `markRaw`. Instantiate them on mount
  and dispose instances, observers, resize handlers, global listeners, timers, and outstanding
  fetches before unmount.
- Do not render unbounded lists directly through Vue. Keep server pagination and use Tabulator or a
  separately benchmarked virtual list when the displayed row count exceeds the viewport-scale
  component path.
- Use stable props and computed values. Apply `v-once`, `v-memo`, or component flattening only where
  Vue profiling shows avoidable updates or excessive component instances.
- Follow Vue's documented guidance for tree shaking, lazy chunks, large-list virtualization, and
  reducing deep-reactivity overhead:
  [Vue performance guidance](https://vuejs.org/guide/best-practices/performance).

#### Components and behavioural parity

- Build reusable, bounded components for:
  - public and admin shells and navigation;
  - accessible section/filter drawers;
  - filters, chips, and typeaheads;
  - evidence caveats and provenance;
  - loading, unavailable, empty, stale, and error states;
  - charts, tables, maps, exports, and pagination;
  - admin health, review, job, analysis, and database panels.
- Keep components coarse inside large tables and lists; avoid replacing one DOM row with a deep tree
  of wrapper components.
- Preserve route titles, headings, labels, focus movement, keyboard navigation, live regions,
  mobile controls, scroll restoration, browser history, and export/share links.
- Prohibit `v-html` for warehouse or source-derived values. Use escaped interpolation/text bindings
  and a link component that accepts only validated HTTP(S) destinations.
- Preserve the existing rule that public content cannot query or render `restricted_` data.

#### Vite build, tree shaking, and asset delivery

- Configure Vite with separate public and admin inputs, CSS code splitting, route-level dynamic
  imports, content hashes, and a generated manifest. Follow Vite's documented backend-manifest
  integration: [Vite backend integration](https://vite.dev/guide/backend-integration.html).
- Lazy-load every route with Vue Router dynamic imports rather than `defineAsyncComponent` at the
  route record itself. See [Vue Router lazy loading](https://router.vuejs.org/guide/advanced/lazy-loading.html).
- Preserve the useful route splitting already present in the public application. Do not create a
  large common chunk that pulls chart, table, map, or admin code into unrelated routes.
- Remove unused D3 and date-fns production assets.
- Remove Fuse and replace its small authority/provider typeaheads with a bounded normalized
  token/substring scorer that retains current keyboard and result-order tests.
- Remove Bootstrap JavaScript. Implement the section and filter drawers as accessible Vue
  components with equivalent focus, Escape, backdrop, and responsive behaviour.
- Compile only the Bootstrap Sass modules/classes still used after component migration. Retain the
  chosen visual system rather than adding a Vue UI library.
- Replace the complete ECharts build with modular imports for the series currently used: bar, line,
  pie, scatter, graph, treemap, custom series, the canvas renderer, and only the referenced chart
  components/features.
- Import Tabulator through the table component only and register only the modules used by current
  filtering, sorting, pagination, responsive layout, download, and clipboard behaviour.
- Import MapLibre, PMTiles support, and map CSS only from the geography and CQC route chunks.
- Commit `package.json`, the package lockfile, TypeScript/Vue source, Vite manifest, and verified
  production `dist` output. Pin the build runtime and package graph through the lockfile.
- Require `npm ci && npm run build` to reproduce committed `dist` without a diff. Node is a
  development/CI requirement only; ordinary Python startup and deployed application containers
  consume the committed output.
- Disable production source maps and generate deterministic gzip and Brotli variants for immutable
  text assets.
- Serve content-hashed assets with `public, max-age=31536000, immutable`; serve HTML with
  `no-cache` so it cannot retain references to deleted chunks.
- On self-hosted deployments, have Caddy serve the committed asset directory directly with range
  and precompressed-file support. Retain a Python static-file fallback with cached metadata and
  bytes for Railway/direct-app deployments.
- Keep delivery origin-only. Do not add Cloudflare or another CDN/edge cache as part of this sweep.

#### Versioned PMTiles boundaries

- Preserve `/api/v1/boundaries` and its response shape for external API users and exports.
- Generate a topology-preserving PMTiles archive whenever canonical authority boundaries change.
- Include only public properties required by the map, and record source digest, boundary/data
  version, generator version, feature count, bounds, zoom range, and output digest in a manifest.
- Name the archive by content digest and serve it with byte-range and immutable-cache support.
- Configure the Vue MapLibre component to request only visible vector tiles rather than downloading
  the roughly 14 MB full-resolution national GeoJSON at map startup.
- Verify feature identifiers/properties, national coverage, adjacency, absence of visible gaps or
  overlaps at representative zooms, and deterministic archive regeneration.

#### Frontend performance budgets

- Public shared JavaScript, including Vue and Vue Router: at most 120 KiB gzip.
- Shared CSS: at most 50 KiB gzip.
- Default overview-route JavaScript and CSS before API data: at most 375 KiB gzip.
- Admin initial-route JavaScript and CSS: at most 200 KiB gzip.
- Incremental MapLibre/PMTiles route payload: at most 400 KiB gzip.
- No non-map route may request MapLibre or PMTiles; no non-table route may request Tabulator; no
  non-chart route may request ECharts.
- Preload no more than two above-the-fold font files.
- Under one pinned Lighthouse mobile profile require LCP at most 2.5 seconds, CLS at most 0.1, and
  total blocking time at most 200 ms. Use the current
  [Core Web Vitals threshold rationale](https://web.dev/articles/defining-core-web-vitals-thresholds)
  as the external reference while retaining the pinned local profile for comparable CI results.
- Compare legacy and Vue routes after ten repeated navigation cycles. The Vue application must not
  show monotonic retained-heap growth or leave detached chart/map/table nodes, active fetches,
  timers, observers, or global listeners.
- Require measured route interaction and filter-update latency to beat noise and show no material
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
- Add Vitest and Vue Test Utils coverage for components/composables and Playwright coverage for
  current Chromium, Firefox, and WebKit across both public and admin applications.
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
- New internal interfaces:
  - PostgreSQL-native connection/repository API using named rows and psycopg parameters;
  - `BatchWriter.write/flush/checkpoint`;
  - `upsert_many`;
  - context-managed streamed HTTP result;
  - archive put-from-stream/file returning `ArchiveObject`;
  - streaming workbook-row iterator;
  - PostgreSQL pgvector embedding repository;
  - separate typed public and admin API clients;
  - Vue route/filter/storage composables;
  - Vue chart, table, map, typeahead, provenance, and error-state component contracts;
  - Vite manifest and immutable-asset resolver;
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
- Frontend package/build configuration belongs in the Vite/TypeScript files and lockfile rather
  than environment variables. Runtime configuration is limited to resolving the committed asset
  manifest and current PMTiles digest.
- Public `/api/v1` success response shapes remain unchanged. Admin health responses may add performance, snapshot-age, staleness, and refresh-error fields.

## Verification and Rollout

- Implement and merge one phase at a time, capturing before/after reports against the same commit-adjacent dataset.
- Before removing SQLite, run the existing SQLite/PostgreSQL equivalence and migration checks one
  final time against the retained dataset and record the digest as the cutover baseline. After the
  clean break, require PostgreSQL migration/restore equivalence, rollback behaviour, dry-run
  guarantees, cancellation at batch boundaries, and interruption/resume coverage.
- Compare analysis manifests, themes, signals, verifier results, cross-source link sets, and model-audit records before and after the redesign.
- Assert the narrative prefilter’s 99% overall and 100% critical-category recall before enabling suppression.
- Require exact semantic-search IDs/order with score tolerance `1e-6`.
- Require row-for-row ontology/context outputs, including Unicode, punctuation, overlapping aliases, plural folding, negation, and termination cues.
- Verify incremental NLP reruns perform no derived writes for unchanged inputs and correctly invalidate every affected downstream stage after controlled changes.
- Test large-download interruption, archive checksum capability fallback, 304 restoration, audit mismatch handling, CSV resume, and workbook/PDF fallback.
- Test web cold/warm paths, concurrent cache misses, saturation, queue rejection, database-pool exhaustion, compression variants, and cache invalidation.
- Test worker crash/restart, advisory-lock exclusion, `SKIP LOCKED` claims, sequenced log polling,
  checkpoint resume, and cross-process cache-version invalidation.
- Validate Neo4j projection restartability, exact node/edge/link/path/property parity, projection lag,
  and individual error recovery from failed `UNWIND` batches.
- Test every existing public/admin route, hash URL, query parameter, bookmark, browser-storage
  structure, keyboard interaction, focus transition, loading/error state, and export link against
  the legacy interface before the coordinated Vue cutover.
- Assert that route network waterfalls obey the ECharts/Tabulator/MapLibre/PMTiles boundaries and
  all compressed bundle budgets.
- Test PMTiles byte ranges, cache headers, deterministic regeneration, map feature/property parity,
  representative zooms, and fallback behaviour while retaining `/api/v1/boundaries` unchanged.
- Run ten repeated Vue navigation cycles under heap and detached-node observation and fail on
  monotonic retained-memory growth or undisposed third-party instances.
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
- Vue 3, TypeScript, Vue Router, and Vite replace both browser applications in one coordinated
  release. Pinia, Vue Query, Nuxt, SSR, hydration, and Vue component frameworks are excluded.
- Node is required only for frontend development and reproducible builds. Committed production
  assets keep normal Python startup and deployment independent of Node.
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
| Frontend/browser exclusion | **Superseded** | Phase 6 supplies the Vue 3/Vite/PMTiles implementation and budgets. |
| Serial CI timing, xdist/loadscope, serial group, fixture reuse, ten clean runs, structural performance assertions | **Retained and expanded** | Phase 7 adds PostgreSQL isolation and Vue/browser/build gates. |
| PostgreSQL-driver-only follow-up test step | **Superseded** | Phase 7 runs the complete suite once with PostgreSQL as the normal dependency. |
| Migrations 0094–0098 and original internal interfaces/settings | **Retained and expanded** | Interfaces section preserves them, adapts 0098 to PostgreSQL-only, and adds 0099–0100 plus frontend/worker interfaces. |
| SQLite/PostgreSQL equivalence | **Superseded after one final gate** | Verification records the final cutover digest; subsequent regression testing is PostgreSQL-only. |
| Analysis/NLP/semantic/download/archive/web/graph verification matrix | **Retained and expanded** | Verification adds worker, Vue, bundle, memory, PMTiles, PostgreSQL restore, and detailed Neo4j parity tests. |
