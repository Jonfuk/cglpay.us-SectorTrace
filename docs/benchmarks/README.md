# The benchmarks

Two phases live in this file. [Phase 3](#phase-3--the-baseline) measured both
backends and changed nothing; [Phase 4](#phase-4--what-changed-and-what-it-was-worth)
acted on it and measured again. Read Phase 4's first section before comparing
any number here with any other — the answer to "faster than what?" turned out
to be the hard part.

Measurements only. Nothing in the pipeline was changed to produce the Phase 3
numbers, and nothing should be changed on the strength of them without
re-running this and putting the second file beside the first.

```bash
./start.sh benchmark                       # measures whichever backend is configured
./start.sh benchmark --compare-to docs/benchmarks/20260815T014856Z-sqlite.json
```

Each run writes `<timestamp>-<backend>.json` here. Reads run against the
working warehouse, because the point is the real data; writes go to a scratch
warehouse — a temporary file on SQLite, a temporary schema on PostgreSQL — so
that measuring cannot change what is being measured. `pipeline/benchmark.py`
carries the reasoning for each case and for the shape of the harness.

**The comparison is only a comparison because Phase 2 proved it.** Both
backends hold the same 655,344 rows, verified value by value, and every report
records the row counts it measured so a later reader does not have to take
that on trust.

## Phase 3 — the baseline

### The baseline (2026-08-15, commit `fd31f22`)

SQLite 3.40.1 on the local disk; PostgreSQL 18.6 on the LAN. p50 of ten runs
(three for the slow cases), after a discarded warm-up. Ratio is PostgreSQL
over SQLite, so **below 1 means PostgreSQL is faster**.

| Case | SQLite | PostgreSQL | ratio |
|---|---:|---:|---:|
| portal.summary | 3,907 ms | 487 ms | **0.12** |
| portal.contracts.first_page | 6,045 ms | 648 ms | **0.11** |
| portal.contracts.full_page | 5,588 ms | 695 ms | **0.12** |
| admin.health.freshness | 944 ms | 289 ms | **0.31** |
| admin.read_table.search | 555 ms | 177 ms | **0.32** |
| admin.read_table.budgets_deep | 493 ms | 429 ms | 0.87 |
| portal.fingertips | 240 ms | 235 ms | 0.98 |
| admin.overview | 24.5 ms | 29.1 ms | 1.19 |
| portal.boundaries | 528 ms | 733 ms | 1.39 |
| admin.review_items.deep_offset | 12.4 ms | 21.1 ms | 1.70 |
| admin.read_table.contracts | 11.3 ms | 30.8 ms | 2.73 |
| portal.geography | 3.5 ms | 13.5 ms | 3.88 |
| portal.authorities | 1.0 ms | 4.5 ms | 4.38 |
| admin.review_items | 2.8 ms | 16.1 ms | 5.66 |
| admin.list_objects | 39.3 ms | 320 ms | 8.16 |
| portal.pay | 1.6 ms | 18.6 ms | 11.97 |
| portal.providers | 1.0 ms | 19.7 ms | 19.33 |

### One finding explains almost the whole table

**PostgreSQL wins where the query is the cost. SQLite wins where the
round-trip is the cost.** The LAN adds something like 5–15 ms per statement,
so the crossover sits at roughly 100 ms of SQLite time: below it the network
dominates and PostgreSQL loses, above it the server's execution wins and the
network stops mattering.

That is not a tie. The cases PostgreSQL wins are the ones an operator
actually waits for — **the portal's front page went from 3.9 seconds to half
a second, and the contracts list from 6 seconds to 0.65** — and the cases it
loses are the ones already under 40 ms, where nobody was waiting. A page that
was slow is now fast; a page that was instant is now merely quick.

The exceptions are worth naming because they are the Phase 4 list:

- **`admin.list_objects`, 39 ms → 320 ms.** The sidebar issues one `COUNT(*)`
  per table, 68 of them, on every page load of the operator UI. On a file that
  is 68 cheap reads; over a LAN it is 68 round-trips. This is the clearest
  Phase 4 target in the whole table, and the fix is not an index — it is
  asking once.
- **`portal.providers` and `portal.pay`, ~20× slower.** Both are small
  queries over small tables, so they are almost entirely round-trip. Same
  shape as above: they issue several statements each.
- **`portal.boundaries`, 528 ms → 733 ms.** 14 MB of geometry across the
  network. Nothing to optimise in SQL; it is the payload.

### Writes

| | SQLite | PostgreSQL |
|---|---:|---:|
| single writer | 1,093 rows/s | 68 rows/s |
| commit p50 | 0.82 ms | 4.32 ms |

| concurrent writers | SQLite | PostgreSQL |
|---|---|---|
| 1 | 638 rows/s (×1.00) | 60 rows/s (×1.00) |
| 2 | 619 rows/s (×0.97) | 109 rows/s (**×1.81**) |
| 4 | 562 rows/s (×0.88) | 246 rows/s (**×4.11**) |
| 8 | 520 rows/s (×0.82) | 467 rows/s (**×7.80**) |

Per writer, PostgreSQL is about 16× slower — the same round-trip, twice per
row (the upsert and the commit). But **SQLite does not scale and PostgreSQL
scales almost linearly to eight writers.** Adding writers to SQLite makes it
slightly *worse*, which is the write slot doing exactly what it was built to
do: hand the warehouse to one writer at a time, in arrival order. Adding
writers to PostgreSQL multiplies throughput nearly by the number of them.

At eight writers the two are within a factor of 1.1 of each other, from a
factor of 16 at one.

**None of this makes a collection faster**, and the plan says so in advance:
a full run is bounded by one request per two seconds per host, by settled
decision 5, and no amount of write throughput touches that. What the numbers
record is the *shape of the constraint that goes away* — the starvation
incident in the README, the 120-second busy timeout, the 900-second write-slot
deadline, and the `defer_cache_writes` dance in `pipeline/parallel.py` that
exists because worker threads could not write.

### What this says about Phase 4

Evidence-gated, in the order the evidence supports:

1. **Batch `list_objects`.** One query returning 68 counts instead of 68
   queries. Biggest measured regression, and not an index problem.
2. **Look at the multi-statement portal endpoints** (`providers`, `pay`,
   `geography`) for the same reason. The wins are milliseconds each, so this
   is second, not first.
3. **A connection pool.** Not measured here, because the harness opens one
   connection and holds it — which means the pool's benefit is *not* in these
   numbers, and neither is its cost. Phase 4 should measure per-request
   connection setup before assuming either.
4. **Keyset pagination: not yet justified.** `admin.review_items.deep_offset`
   is 21 ms and `admin.read_table.budgets_deep` is 429 ms on PostgreSQL, where
   it is the *scan* and not the offset that costs — and the portal turns out
   not to paginate with `OFFSET` at all. Revisit if the review queue grows an
   order of magnitude.
5. **`percentile_cont` for the median: not yet justified.** `portal.pay` is
   18.6 ms in total on PostgreSQL, so the Python-side median is not what is
   costing anything.
6. **Index work: not yet justified by this table.** `contracts` sorted by
   `date_published` is already 0.11× on PostgreSQL without one. Phase 4 should
   take `EXPLAIN (ANALYZE, BUFFERS)` before adding anything, as the plan says.
7. **m13 COPY staging: not justified.** The plan's gate was "DB time > ~20% of
   m13 runtime". m13's cost is parsing and fetching; nothing here suggests
   otherwise.

### What is not measured, and why

**Ingestion wall-clock and `--jobs` scaling.** A collection waits on the
network by design. Measuring it honestly needs live sources and hours;
measuring it offline would mean timing a mocked transport, which times the
mock. The part PostgreSQL genuinely changes is writer contention, and that is
measured above.

**Web request latency end to end.** These call the query functions directly,
not the HTTP server, so JSON serialisation and the server's own overhead are
excluded. That is deliberate — it isolates the backend, which is the variable
under test — but it means a page is slower than its case here.

**Run-to-run variance over the LAN is real.** `portal.fingertips` was measured
at 235 ms, 360 ms and 690 ms across three runs of this harness on the same
data. The percentiles within a run are stable; the medians between runs are
not, for the PostgreSQL cases. Two runs before believing a difference under
about 1.5×.

## Phase 4 — what changed, and what it was worth

### First: what "faster" can and cannot be measured against

Phase 4's changes were made on Phase 3's evidence, so the obvious thing to do
was re-run the harness and compare the two files. That comparison says every
case got between 1.3× and 2.4× **slower**, including several that nothing
touched.

It is not true. Two runs an hour apart agreed with each other to within
0.8–1.2× and both sat at that level, and — the check that settles it — the
*pre-Phase-4 code*, run today against the same server, is slower than
yesterday by the same factor. The machine, the link, or the server was simply
having a different day.

So the numbers below come from an A/B run back to back within twenty minutes:
the commit before this phase in one worktree, this phase's commit in another,
the same harness file copied into both, against the same warehouse.

```bash
git worktree add /tmp/before <commit-before-phase-4>
cp pipeline/benchmark.py /tmp/before/pipeline/     # same harness on both sides
(cd /tmp/before && uv run --extra postgres python -m pipeline.cli benchmark --no-writes --output-dir bench)
./start.sh benchmark --compare-to /tmp/before/bench/<file>.json
```

**Do not compare a number here with a number in the Phase 3 table.** They were
taken on different days, and the day is worth more than anything this phase
did to any case except one.

### PostgreSQL, before and after, same conditions

`20260815T131844Z-postgres.json` is the before, `20260815T132056Z-postgres.json`
the after. Ratio is after over before, so **below 1 is the improvement**.

| Case | before | after | ratio |
|---|---:|---:|---:|
| admin.list_objects | 525.4 ms | 92.3 ms | **0.18** |
| portal.authority | *did not run* | 412.8 ms | — |
| portal.layers | *did not run* | 571.3 ms | — |
| portal.authorities | 8.9 ms | 5.9 ms | 0.66 |
| portal.geography | 33.7 ms | 27.6 ms | 0.82 |
| portal.pay | 28.0 ms | 23.8 ms | 0.85 |
| admin.overview | 61.9 ms | 55.0 ms | 0.89 |
| admin.read_table.budgets_deep | 571.6 ms | 521.0 ms | 0.91 |
| admin.review_items | 29.1 ms | 26.5 ms | 0.91 |
| portal.contracts.first_page | 1,496.1 ms | 1,450.4 ms | 0.97 |
| portal.contracts.full_page | 1,530.9 ms | 1,500.1 ms | 0.98 |
| admin.read_table.search | 412.5 ms | 410.4 ms | 0.99 |
| admin.review_items.deep_offset | 39.1 ms | 38.9 ms | 0.99 |
| admin.health.freshness | 622.1 ms | 619.2 ms | 1.00 |
| portal.fingertips | 404.9 ms | 407.1 ms | 1.01 |
| admin.read_table.contracts | 50.6 ms | 51.8 ms | 1.02 |
| portal.boundaries | 804.4 ms | 823.6 ms | 1.02 |
| portal.summary | 995.2 ms | 1,029.2 ms | 1.03 |
| portal.providers | 33.1 ms | 36.0 ms | 1.09 |

One case moved and the rest are noise, which is what the changes predict.
`admin.list_objects` is the sidebar asking once instead of once per table.
Everything from 0.82 to 1.09 is inside the run-to-run variance Phase 3 already
documented, and none of it is attributable.

**`portal.authority` and `portal.layers` did not run at all before.** Both
named `sqlite_master` in their SQL, so both raised `UndefinedTable` on
PostgreSQL — two public routes, broken on the backend Phase 5 intends to
deploy, and the harness had no case for either. They have cases now.

### What the harness cannot see

Three of this phase's changes are invisible to a benchmark that opens one
connection, holds it, and calls query functions directly. Each was measured on
its own.

**The connection pool — 68 ms per request, gone.** The web layer opens a
connection per HTTP request, which the harness never does:

| | p50 |
|---|---:|
| connect + close (reader role) | 68.4 ms |
| connect + `SELECT 1` + close | 67.5 ms |
| the same, borrowed from the pool | 8.3 ms |
| `SELECT 1` on a connection already held | 4.1 ms |

Every portal and operator request was paying more to open a connection than
`portal.pay`, `portal.providers` and `admin.review_items` cost put together.

**The `date_published` index — the query, not the payload.** The A/B shows
`portal.contracts.first_page` unchanged, and that is correct rather than
disappointing: that case is `contracts()`, whose cost is its aggregates over
76,229 priced notices, not its `ORDER BY`. The index answers the notices
query, which is what the list and the CSV export are made of:

| | without the index | with it |
|---|---:|---:|
| PostgreSQL (`EXPLAIN ANALYZE`) | 83 ms, 14,728 buffers | 0.55 ms, 128 buffers |
| SQLite (same file, same cache) | 333 ms | 2.3 ms |

Both measured by building and dropping the index around the same query on the
same data, slower arm first so that a warm cache could not be mistaken for the
result. SQLite's plan goes from `SCAN c` plus `USE TEMP B-TREE FOR ORDER BY`
to `SCAN c USING INDEX idx_contracts_date_published`.

**Statement counts.** Round-trips are the cost on a LAN, so the honest unit is
sometimes the number of questions rather than milliseconds:

| | before | after |
|---|---:|---:|
| `admin.list_objects` counting statements | 82 | 1 |
| `portal.authority` statements | 40 | 29 |
| `_coverage_cells` statements | 13 | 1 |

`admin.list_objects` on SQLite is 72.7 ms per-table against 78.4 ms batched —
no round-trips to save on a local file, and nothing lost either. The change is
worth 5.4× on the LAN and free on the file.

### The SQLite half is not reported, and why

A before/after over the whole harness was run on SQLite too, on two copies of
the working warehouse. It is not here, because it cannot be trusted: the
copies were read cold and warm respectively, and cases this phase never
touched moved as much as the ones it did — `admin.health.freshness` 3,506 ms
to 972 ms, `admin.read_table.budgets_deep` 1,335 ms to 501 ms. That is the OS
page cache, measured very precisely.

The SQLite claims this phase does make are the isolated ones above, taken on a
single file with one cache state.

### Writes, on the after run

| | rows/s | vs one writer |
|---|---:|---:|
| 1 concurrent writer | 53 | ×1.00 |
| 2 | 116 | ×2.17 |
| 4 | 203 | ×3.81 |
| 8 | 323 | ×6.06 |

Same shape as Phase 3 (×7.80 at eight writers there): PostgreSQL scales with
writers and SQLite does not. Nothing in this phase was aimed at write
throughput, and nothing moved it.

### What Phase 4 refused, and on what evidence

- **`contracts(value_core)`** — the plan expected the concentration and median
  queries to want an index. They read 76,229 of 98,636 rows; at that
  selectivity the sequential scan is the right plan and the planner picks it.
- **Dropping unused indexes** — `pg_stat_user_indexes` shows four never
  scanned, all on tables that hold no rows yet, including the
  `idx_authority_url_overrides_item` the plan named as a candidate "to
  confirm, not to assume". Confirmed, and the answer is no. Nothing here is
  both large and unused.
- **Keyset pagination, `percentile_cont`, m13 `COPY` staging** — all three
  were already unjustified by the Phase 3 table, and nothing found here
  changes that. The reasoning is in "What this says about Phase 4" above and
  stands unedited.

### One harness bug, found by running it against old code

The read cases share the write connection, and on PostgreSQL a failed
statement aborts the transaction. So the first case that failed reported
itself and then made **every case after it** report "current transaction is
aborted" — the run against the pre-Phase-4 code produced two real findings and
fifteen fictional ones. `read_latency` now rolls back after a failed case, and
a test pins it. It is the same trap as `web/health.py:freshness`, which the
read path answers with autocommit; a write connection answers it with a
rollback.
