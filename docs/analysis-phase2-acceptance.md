# Phase 2 analysis acceptance

Phase 2 remains incomplete until the same-data parity, adjudicated-prefilter,
production-scale benchmark, and PostgreSQL test gates in `performance.md` have
all passed. The commands below create reproducible JSON evidence; they do not
turn a fixture run into production acceptance.

## Safety and isolation

Run this procedure only against a disposable PostgreSQL 18 acceptance database
copied from one frozen source snapshot. Do not point `DATABASE_URL` or
`POSTGRES_TEST_URL` at production. Keep archive objects immutable and use the
same Git commit, schema, source rows, model configuration, and source/archive
digests for the paired runs.

The worker's prefilter is shadow-only unless both conditions are true:

1. `ANALYSIS_PREFILTER_SUPPRESSION_ENABLED=true` was an explicit operator
   choice; and
2. PostgreSQL contains an immutable result for the exact corpus, rule, and
   threshold digests with at least 99% overall recall, 100% recall over all
   critical examples, and 100% recall within every named critical category.

Do not record `tests/fixtures/analysis/narrative_prefilter_regression.jsonl` as
the production adjudication. It is a transparent regression fixture, not a
representative human-reviewed corpus.

## Record the adjudicated gate

The JSONL corpus needs a unique stable `id`, source `text`, boolean `positive`
and `critical` labels, and a non-empty `category` for every critical example.
The version label is immutable: attempting to reuse it for different bytes or
results fails.

```bash
uv run pipeline analysis prefilter-eval adjudicated.jsonl \
  --corpus-version human-adjudicated-2026-09-v1 \
  --adjudicated-by "review panel name" \
  --record
```

Keep suppression false if this exits non-zero. A persisted failed evaluation
is evidence about the rules, not permission to suppress candidates.

## Same-dataset before/after run

Queue one all-domain baseline release with suppression disabled. Instrument
exactly that queued run:

```bash
uv run pipeline analysis benchmark-once \
  --batch-size 100 \
  --worker-id phase2-shadow-baseline \
  --output docs/benchmarks/phase2-shadow-baseline.json

uv run pipeline analysis acceptance-capture RELEASE_ID \
  --output docs/benchmarks/phase2-shadow-release.json
```

Restore the identical database/source snapshot, retain the same pinned model
configuration, enable suppression only after the gate above, and repeat:

```bash
uv run pipeline analysis benchmark-once \
  --batch-size 100 \
  --worker-id phase2-prefilter-candidate \
  --output docs/benchmarks/phase2-prefilter-candidate.json

uv run pipeline analysis acceptance-capture RELEASE_ID \
  --output docs/benchmarks/phase2-prefilter-release.json

uv run pipeline analysis acceptance-compare \
  docs/benchmarks/phase2-shadow-release.json \
  docs/benchmarks/phase2-prefilter-release.json \
  --output docs/benchmarks/phase2-parity.json
```

The comparison exits non-zero unless the ordered input digest matches and
signals, themes, topics, verifier results, and links have equal counts, equal
semantic sets, and equal output ordering. Model-audit and cost differences are
reported as diagnostic deltas rather than correctness equality: reducing those
calls is the intended optimization.

## Measurement meanings

`benchmark-once` records observed values only:

- wall and CPU seconds for one queued worker run;
- Python allocator peak during that command;
- process peak-RSS high-water marks before and after the run;
- client `execute`/`executemany` calls and `executemany` row counts;
- persisted run model calls, cache hits, billed calls, and model cost through
  the release capture.

Client calls are not labelled as PostgreSQL server statement executions, and
the difference between two RSS high-water marks is not labelled as allocated
memory. Capture PostgreSQL server telemetry separately when the isolated
benchmark environment provides it. Record the input-manifest counts in the
release snapshot to demonstrate that the run was genuinely production-sized;
there is no invented row-count threshold in the harness.

The PostgreSQL regression suite also checks that the candidate, link, and
health-deduplication indexes exist and captures an `EXPLAIN (FORMAT JSON)` plan
with sequential scans disabled for the small fixture. Production acceptance
must additionally retain the natural planner's plan and timing on the real
dataset.
