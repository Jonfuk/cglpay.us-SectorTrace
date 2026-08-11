# England-wide Substance Misuse Sector Evidence Pipeline

A reproducible, auditable pipeline that collects **public-domain evidence** about
the drug and alcohol treatment sector across every commissioning area in England,
for use as a trade union pay campaign evidence base.

The guiding principle is that a smaller dataset which can be defended line by
line is worth more than a large one that cannot. Every row carries the URL it
came from, when it was fetched, and the SHA-256 of the exact bytes, which are
archived under `data/raw/`. Nothing is inferred, interpolated or defaulted: a
field that cannot be parsed is written as `NULL` and logged to `parse_failures`,
and anything needing human judgement goes to `review_queue`.

## Quick start

```bash
./start.sh
```

The startup scripts bootstrap everything before handing off to the CLI: they
create the directories the pipeline writes to, make sure a `.env` exists, check
`uv` is installed, and sync dependencies.

| Platform | Script |
| --- | --- |
| Linux / macOS / WSL / Git Bash | `./start.sh` |
| Windows (cmd, PowerShell) | `start.cmd` |

Both take the same arguments and pass them straight through to the CLI. With no
arguments they show the help menu.

```bash
./start.sh                                            # show CLI help
./start.sh list-modules                               # list registered modules
./start.sh run m00_geography                          # run one module
./start.sh run all                                    # run every module
./start.sh run m01_procurement --since 2024-01-01     # only recent records
./start.sh run m02_tribunals --limit 5                # smoke test
./start.sh run m03_charity_finance --dry-run          # fetch/parse, write nothing
./start.sh export all                                 # generate every export
./start.sh web                                        # browse the warehouse, clear the review queue
```

```cmd
start.cmd run m00_geography
start.cmd run m01_procurement --since 2024-01-01 --limit 100
start.cmd export all
```

The scripts run from the repository root regardless of where you invoke them
from, and exit with the CLI's own exit code, so they are safe to use from cron,
Task Scheduler or CI.

### What the scripts set up

| Path | Purpose |
| --- | --- |
| `data/raw/` | Raw response bytes, addressed by SHA-256 — the audit trail behind every figure |
| `data/warehouse.db` | The canonical SQLite warehouse |
| `logs/` | Structured JSON logs, one file per module |
| `docs/verification/` | Human-review markdown (census value checks, document candidates) |
| `exports/output/` | Generated exports, each with a `.provenance.json` |
| `.env` | Configuration and API keys — never committed |

If `.env` is missing, the scripts copy `.env.example`. If neither exists, they
write a template. In both cases they warn you to fill it in: `CONTACT_EMAIL` is
required, and the pipeline refuses to start without it because it is sent in the
`User-Agent` of every request.

## Running without the scripts

The scripts are a convenience wrapper, not a requirement. These are equivalent:

```bash
uv run python -m pipeline run m00_geography
uv run pipeline run m00_geography          # console entry point
```

## Requirements

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — manages the
  Python environment and dependencies. The scripts fail with install
  instructions if it is not on `PATH`.
- Python — provisioned by `uv` from `pyproject.toml`.

### API keys

Free registration; only needed for the modules that use them. Set them in
`.env`:

| Variable | Used by | Source |
| --- | --- | --- |
| `CONTACT_EMAIL` | **all modules** | your own address |
| `CHARITY_COMMISSION_API_KEY` | `m03_charity_finance` | Charity Commission register API |
| `COMPANIES_HOUSE_API_KEY` | `m04_companies` | Companies House public API |
| `CQC_SUBSCRIPTION_KEY` | `m05_cqc` | CQC public API |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Sheets export | **path** to a credential file, not the JSON itself |

Modules that need a key fail immediately with a message naming the missing
variable, rather than part-way through a run.

Keep credentials out of the repository: `.env`, `secrets/` and
`*-service-account.json` are all gitignored. `.env.example` is committed and
contains no values.

## Modules

Each writes to its own tables and can be run independently. Re-runs are
idempotent (natural-key upserts) and resumable (per-module cursors), so an
interrupted crawl continues rather than restarting.

Modules join on two stable entities: **authorities** (ONS code, from `m00`)
and **providers** (from `pipeline/providers.py`). Everything else hangs off
one or both.

| Module | Source | Evidence |
| --- | --- | --- |
| `m00_geography` | ONS Open Geography Portal | Local authority spine, boundaries, reorganisation successors |
| `m01_procurement` | Find a Tender, Contracts Finder | Contract notices, values, suppliers, direct awards |
| `m02_tribunals` | GOV.UK employment tribunal decisions | Judgments against providers (pseudonymised) |
| `m03_charity_finance` | Charity Commission + filed accounts | Income, wages, employee numbers, agency spend, pay bands |
| `m04_companies` | Companies House | Group structure, former names, filings, officer churn, insolvency cases, disqualified-director check |
| `m05_cqc` | CQC public API | Registered locations, ratings, inspection reports |
| `m06_workforce_census` | NHS Benchmarking Network | Vacancy, turnover, WTE, volunteer and contract-type metrics |
| `m07_ndtms` | OHID via GOV.UK | Published treatment statistics; LA-level tables where they exist |
| `m08_pfd_reports` | Courts and Tribunals Judiciary | Coroners' Prevention of Future Deaths reports, workforce concerns |
| `m09_cdp_documents` | Local authority websites | Combating Drugs Partnership document **candidates** (needs verification) |
| `m10_committee_papers` | Council committee systems | Committee paper **candidates** (needs verification) |
| `m11_public_health_grant` | DHSC | Public Health Grant allocations, incl. drug/alcohol ring-fence |
| `m12_fingertips` | OHID Fingertips | LA-level treatment numbers, completions, waiting times, prevalence |
| `m13_la_budgets` | MHCLG | Local authority budgeted revenue expenditure, incl. the Public Health line |
| `m14_annual_reports` | Provider annual reports | Workforce narrative and disclosure gaps, read from PDFs `m03` already archived |
| `m15_foi` | mySociety register + WhatDoTheyKnow search feed + council disclosure logs | **Discovery of** publicly published FOI requests (never their response text), and an authoritative website URL per authority |
| `m16_nhs_jobs` | NHS Jobs | Advertised pay bands, contract type and closing dates per provider — the only **direct** pay evidence here, and a floor rather than a total |

### Run order

`run all` orders modules by what they read, not alphabetically, and prints the
order it chose before starting:

```bash
./start.sh run all
```

Each module declares the modules whose output it uses, and the CLI resolves
those into a run order (alphabetical among equals, so the sequence is
deterministic and two logs are comparable). Three orderings matter:

| Module | Runs after | Why |
| --- | --- | --- |
| everything | `m00_geography` | every source joins to the authorities table |
| `m04_companies` | `m03_charity_finance`, `m05_cqc` | both publish company numbers; without them every company name match stays unconfirmed |
| `m09`, `m10` | `m15_foi` | supplies an authoritative website for each authority — without it only the hand-verified handful can be searched |
| `m14_annual_reports` | `m03_charity_finance` | reads the accounts PDFs `m03` archives |

Alphabetical order breaks the second and third of these. Neither failed
loudly when it did — `m04` simply confirmed nothing, and `m09`/`m10` searched
one council instead of 315.

Running a single module still works, and the CLI says what it will be missing:

```console
$ ./start.sh run m04_companies
note: m04_companies normally runs after m03_charity_finance, m05_cqc.
      It will still run, using whatever those modules left behind.
```

### Running several APIs at once

The pipeline talks to eleven independent backends, so most modules have no
reason to wait for each other:

```bash
./start.sh run all --jobs 4
```

`run all` groups modules into **waves** by dependency. Every module in a wave
has its inputs satisfied by an earlier wave, so a wave runs concurrently and
the next only begins once it has finished — `m04` still never starts before
`m03`/`m05`, and `m09`/`m10` never before `m15`.

| Wave | Modules | Backends |
| --- | --- | --- |
| 1 | `m00`, `m02`, `m03`, `m06`, `m08` | ArcGIS, GOV.UK, Charity Commission, NHS, Judiciary — all different |
| 2 | `m01`, `m05`, `m07`, `m11`, `m12`, `m13`, `m14`, `m15` | FTS/CF, CQC, GOV.UK ×3, Fingertips, local, WDTK |
| 3 | `m04`, `m09`, `m10` | Companies House, council sites |

This is safe because the per-host rate limit is enforced **process-wide**. The
four modules that share `www.gov.uk` queue behind each other on that host and
nowhere else, so no source sees a faster request rate than it would have if it
were the only thing running.

Each module gets **its own database connection**. That is required for
concurrency, and better serially too: a module that fails rolls back only its
own writes. A failing module no longer aborts the run — the others finish,
everything is reported in the summary, and the exit code is still non-zero.

**The default is `--jobs 1`** (unchanged behaviour). The parallel path is
newer and less exercised than the serial one, and a long crawl is not where
you want to discover that; raise it deliberately once you trust it.

### Modules that need a human

`m06`, `m09` and `m10` produce material for review rather than finished
evidence:

- **`m06`** writes `docs/verification/census_{year}_tables.md`, pairing every
  parsed value with the source line it came from. Metrics stay
  `verified = 0` until you say otherwise.
- **`m09`** writes `docs/verification/cdp_candidates.md`, grouped by region.
  Nothing reaches `cdp_documents` unverified.
- **`m10`** finds committee papers the same way. Nothing reaches
  `committee_papers` unverified.

`m09` and `m10` are also **coverage-limited**: they need each council's
publication URL, which cannot be derived, so `pipeline/authority_websites.py`
holds only entries verified by request. `m10` will additionally accept a
committee-system link published on the council's own home page, provided the
target then answers a ModernGov signature path — two confirmations from the
source, recorded as `url_source = 'homepage_link'` so it stays distinguishable
from a hand-verified entry. Authorities with neither are queued:

```sql
SELECT COUNT(*) FROM review_queue WHERE item_type = 'authority_website_unknown';
SELECT COUNT(*) FROM review_queue WHERE item_type = 'committee_url_unknown';
```

`m10` searches ModernGov systems for real (a GET on `/ieSearchResults2.aspx`).
Other committee systems are detected and then recorded as
`committee_system_unsupported` — no adapter exists, so their absence of
candidates is an absence of coverage, not an absence of papers. Four review
item types keep those apart: `committee_search_no_matches` (the system
searched and reported nothing), `committee_search_blocked` (403, usually bot
protection), `moderngov_results_unrecognised` (the page is no longer the shape
the parser understands) and `committee_system_unsupported`.

## Exports

```bash
./start.sh export all        # sheets, geojson, echarts, docs
./start.sh export sheets     # nine CSV tabs
./start.sh export geojson    # four Leaflet layers
./start.sh export echarts    # dashboard series
./start.sh export docs       # regenerate DATA_DICTIONARY.md
./start.sh export sheets --push   # also push to Google Sheets (needs credentials)
```

Output goes to `exports/output/` (gitignored — regenerate any time).

| Target | Output |
| --- | --- |
| `sheets` | Nine CSV tabs of human-readable evidence, caveats above the header row |
| `geojson` | `contracts`, `cqc_locations`, `treatment_numbers`, `pfd_reports` — separate FeatureCollections so a map can toggle them independently |
| `echarts` | Pre-shaped series, each with a `meta` block carrying source, retrieval date and caveats |
| `docs` | `docs/DATA_DICTIONARY.md`, generated from the live schema |

**Every export file is written with a companion `.provenance.json`** listing
contributing tables, source systems, retrieval window and row counts. A test
asserts none can be produced without one.

The treatment statistics (~40,000 rows) are deliberately *not* a Sheets tab —
they are map and chart data, and go to the GeoJSON and ECharts targets. A tab
nobody can scroll is not evidence anyone can check.

## Data handling

**Personal data is segregated.** Named individuals — tribunal claimants, company
officers, CQC registered managers — are stored only in tables prefixed
`restricted_`. These are excluded from all exports, and
`pipeline/exports.guard_columns()` raises if one is ever referenced. Public
tables expose a stable pseudonym derived from a public case number instead.

**Evidence layers are kept separate.** Sector census figures, charity accounts,
tribunal counts and contract values come from different sources with different
collection methods and populations. The pipeline does not combine them into
composite scores or ratios; if a downstream consumer wants to, that is their
decision to document.

**Collection is polite.** `robots.txt` is respected, requests are rate-limited
per host (default one per 2 seconds), `Retry-After` is honoured, and conditional
requests avoid re-fetching unchanged documents. The `User-Agent` identifies the
pipeline and includes `CONTACT_EMAIL`.

The per-host interval is enforced **process-wide**, not per HTTP client, so it
holds no matter how many modules or threads are running. It used to live on
each client, which made it a description of the schedule rather than a
guarantee.

### Fetching several councils at once

`m09`, `m10` and `m15` each visit a few hundred *different* councils. Serially
that is hours of waiting between hosts that have never heard of each other, so
they fetch concurrently:

```bash
MAX_FETCH_WORKERS=8    # default; set 1 for fully serial collection
```

This is not a rate limit and does not replace one. It only decides how many
**different** councils are in flight — workers that land on the same host queue
behind each other on the shared clock, so no council sees a faster request rate
than it would have. Measured on the three verified ModernGov councils, `m10`
produced identical output (191 candidates, 124 snippets, zero review items,
zero parse failures) in 64s against 156s serial.

Workers fetch and parse; the **main thread does all the writing**, so
commit-per-module and rollback-on-failure are unchanged. A council that fails
now costs one council rather than aborting the module, and is recorded rather
than passing as a council with nothing to publish.

See [`docs/CAVEATS.md`](docs/CAVEATS.md) for known limitations that must travel
with any published figure. It leads with the things you must **not** compute —
no claims-per-employee rate, no dividing treatment numbers by workforce
figures, no differencing workforce census years.

## Checking what a run actually produced

Nothing is inferred or defaulted. A field that could not be parsed is `NULL`
with a row in `parse_failures`; anything needing human judgement is in
`review_queue`. Both are worth reading after a run — an empty cell with a
logged reason is the correct output, not a failure to hide.

```bash
sqlite3 data/warehouse.db "SELECT module, reason, COUNT(*) FROM parse_failures GROUP BY 1,2;"
sqlite3 data/warehouse.db "SELECT module, item_type, COUNT(*) FROM review_queue WHERE status='pending' GROUP BY 1,2;"
```

Both tables deduplicate on a natural key, so re-running a module does not
inflate the counts.

## The review UI

`review_queue` is where every judgement call the pipeline refused to make on
its own ends up, and it does not empty itself. The web UI reads the warehouse
and writes decisions back:

```bash
./start.sh web                 # http://127.0.0.1:1801
./start.sh web --port 8080 --no-open
```

```cmd
start.cmd web
```

Four screens: an overview of what is pending by module and item type; the
queue itself, filterable and searchable, with approve/reject/reset per item or
across a selection; a browser for every table and view; and a SQL box.

**Deciding records a judgement — it does not promote anything.** Approving an
`unmatched_buyer_name` does not bind that name to an authority, and approving
a `possible_group_company` does not add a company to `companies`. Those are
per-module operations with their own evidence thresholds, and the UI does not
invent a generic one. What it guarantees is that the judgement is kept: every
decision writes a row to `review_decisions` recording who made it, when, what
the status was before, any note, and the item's context as it read at the
time. An item can be reset to pending, and that reset is recorded too.

A decided item stays decided. `record_review_item()` only refreshes an item
that is still pending, so a later run of the same module will not reopen it or
overwrite the context a decision was taken against.

Three things are worth knowing before pointing anyone else at it:

- **Reading cannot write.** The browser and the SQL box run on a connection
  opened `mode=ro` with `query_only`, so nothing typed into either can modify
  the warehouse. Decisions go through a separate writable connection that
  touches two tables and nothing else.
- **There is no authentication.** It binds to `127.0.0.1` for that reason.
  `--host` will widen it and warns when it does; the warehouse holds
  `restricted_` tables of personal data, so a wider bind is a decision about
  the network you are on.
- **`restricted_` tables need a second click.** Opening one in the browser
  returns a refusal until you confirm. That is a guard against opening one by
  accident — the SQL box reads them like any other table, as does `sqlite3`.

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | Every table and column, generated from the live schema — never hand-edited |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Each source's URL, licence, key requirement and applied rate limit |
| [`docs/CAVEATS.md`](docs/CAVEATS.md) | Known limitations, and what must not be computed |
| `docs/verification/` | Per-run review worklists produced by `m06`, `m09` and `m10` |

## Development

```bash
uv run python -m pytest                  # full suite (offline, fixture-backed)
uv run python -m pytest -m integration   # live-source smoke tests (skipped by default)
```

Parsers are tested against fixtures in `tests/fixtures/` captured from real
responses. Fixtures containing personal data are anonymised: the underlying
judgments are public record, but this repository is public and the pipeline
treats claimant names as restricted.

### Live smoke tests

Fixtures cannot notice the failure this project is most exposed to: a source
quietly changing shape. `tests/test_integration_smoke.py` runs every module
against its real source with a small `--limit` and asks three things:

1. does it run without raising?
2. did it write anything?
3. do the rows carry **evidence**, not just provenance and NULLs?

The third is the one that matters. A parser whose column headings no longer
match writes a row per record with every value NULL, logs a pile of
`parse_failures`, and exits zero — which looks like a successful run. Each
module declares the columns that go blank when that happens.

The modules share one temporary warehouse and run in dependency order, so `m04`
sees the company numbers `m03`/`m05` publish and `m09`/`m10` see the websites
`m15` registers. Where a small `--limit` leaves a downstream module nothing to
work on, it skips with a reason naming the upstream table rather than passing
over zero rows. Modules whose credentials are absent skip by name.

These make real requests at the normal one-per-two-seconds-per-host rate, and
the run takes a while (`m05` alone pages the full CQC provider index before it
can filter). Do not run them in a loop. A final test sweeps the working
warehouse — not a temporary one — for any row that lost its provenance.

The coverage guards run offline with the default suite: a new module without a
smoke spec, or a spec naming a column that does not exist, fails immediately.
