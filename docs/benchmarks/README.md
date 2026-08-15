# Phase 3 — the baseline

Measurements only. Nothing in the pipeline was changed to produce these
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

## The baseline (2026-08-15, commit `fd31f22`)

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

## What this says about Phase 4

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

## What is not measured, and why

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
