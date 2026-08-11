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
| `m04_companies` | Companies House | Group structure, former names, filings, officer churn |
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
| `m15_foi` | mySociety register + council disclosure logs | **Publicly published** FOI evidence, and an authoritative website URL per authority |

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
