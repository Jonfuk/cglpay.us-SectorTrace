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
| `docs/verification/` | Human-review markdown (document candidates, resolved URLs) |
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

Each writes to its own tables and can be run independently. **Re-runs are
idempotent**: every write is a natural-key upsert, so running a module twice
produces the same warehouse as running it once, and an interrupted run is
safe to repeat.

**Re-runs are cheap, but only `m01_procurement` truly resumes.** It is the one
module that records a cursor (`module_cursors`), because Find a Tender is
paged and picking the page back up is the difference between minutes and
hours. The other sixteen restart from the beginning — what makes that
acceptable rather than wasteful is the conditional-request cache: a document
that has not changed answers `304` and is read from the raw archive instead of
downloaded again. The requests are still made, at the same one per two seconds
per host, so a re-run costs time even when it costs no bandwidth.

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

- **`m06`** stores every figure with the verbatim line it was parsed from and
  the full text of every page it read. Metrics stay `verified = 0` until
  somebody checks one on the **Census tab** of `/admin`, which shows the figure
  beside the archived page it came from. The database refuses `verified = 1`
  without a `census_verifications` row behind it (migration `0033`) — including
  the bulk `UPDATE` this module used to print into a generated markdown
  worklist, which set twenty flags at once and attributed them to nobody.
- **`m09`** writes `docs/verification/cdp_candidates.md`, grouped by region.
  Nothing reaches `cdp_documents` unverified.
- **`m10`** finds committee papers the same way. Nothing reaches
  `committee_papers` unverified.

**A decision survives a re-run.** These modules re-write every candidate they
find on every run, and until [#2](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues/2)
that included the verification flag — so a link re-found after somebody had
opened the document and promoted it came back round the worklist as though
nobody had. `db.upsert` now leaves the decision columns alone on a conflict.
If a run had already cleared some, the promotions themselves are still on
record and the flags can be put back:

```bash
./start.sh restore-promotion-flags          # reports; add --apply to write
```

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

### The write slot

SQLite allows one writer, and its busy handler is a backoff rather than a
queue — a blocked writer sleeps, retries, and finds the lock taken again by
whoever asked at the right moment. Nothing gives the loser a turn. Measured on
this warehouse, four modules committing every 50ms starved a fifth for the
whole of its timeout, with no holder ever keeping the lock for more than a
fiftieth of a second.

Every module in a run is a thread in one process, so the write slot is handed
out **in arrival order by a process-wide lock** (`pipeline/db.py`). A module
takes it on the first write of a transaction and releases it on commit,
rollback or close. Two modules are never inside a write transaction at once,
SQLite's busy handler is never consulted, and no module can be passed over
twice. Reads are untouched — WAL readers never queue.

That decides *who waits*. How *long* they wait is still each module's own
business: a module that writes a row and then goes off to fetch holds the slot
for the length of its crawl, so every collecting module commits per unit of
work rather than once on the way out. `tests/test_write_slot_discipline.py`
checks that across all 17 of them, because both times this went wrong it was
found by a four-hour run rather than by a test.

The lock is process-wide, not cross-process: running `./start.sh web` and
`./start.sh run all` at the same time still leaves those two processes
contending through SQLite, which is what the two-minute busy timeout is for.

See [`docs/CAVEATS.md`](docs/CAVEATS.md) for known limitations that must travel
with any published figure. It leads with the things you must **not** compute —
no claims-per-employee rate, no dividing treatment numbers by workforce
figures, no differencing workforce census years.

## Checking what a run actually produced

Nothing is inferred or defaulted. A field that could not be parsed is `NULL`
with a row in `parse_failures`; anything needing human judgement is in
`review_queue`. Both are worth reading after a run — an empty cell with a
logged reason is the correct output, not a failure to hide.

**A run says whether it wrote anything.** `--dry-run` rolls back, so it leaves
a warehouse identical to the one it started with — which also makes "parsed
238,407 rows and wrote nothing on purpose" look exactly like "the parser
silently found nothing". Every module logs `module.starting` with the
arguments it was given and `module.finished` with `dry_run` and `wrote`, and
the summary table retitles itself and renames its rows column on a dry run.
That is not a hypothetical distinction: `m13_la_budgets` spent a day reported
as complete against two empty tables.

**A run is remembered after the process ends.** Runs started from `/admin` get
a row in `job_runs` — what was asked for, when, and how it ended — which
outlives the server. Their log lines do not: those are in `logs/`, and copying
them into the warehouse would put the chattiest table in the database next to
the evidence. A job still marked running when the server starts is recorded as
`interrupted`, so a crawl killed by a crash reads as an interrupted crawl
rather than as nothing at all.

```bash
sqlite3 data/warehouse.db "SELECT module, reason, COUNT(*) FROM parse_failures GROUP BY 1,2;"
sqlite3 data/warehouse.db "SELECT module, item_type, COUNT(*) FROM review_queue WHERE status='pending' GROUP BY 1,2;"
```

Both tables deduplicate on a natural key, so re-running a module does not
inflate the counts.

## The evidence portal

`./start.sh web` serves two interfaces from one process. The public evidence
portal is at `/`, and the operator tools — the review queue and the raw
warehouse browser — moved to `/admin`, linked from the portal's header.

The portal is built for people who need to read this evidence rather than run
the pipeline: union researchers, journalists, public health analysts. Six
sections — overview, pay evidence, contracts, geography, treatment demand, and
a page per provider — over a read-only `/api/v1/` API.

Three properties it is built around:

- **No figure without its caveat.** The caveat text travels with the number in
  the API payload, from the same `_note` columns the exports use, so a chart
  cannot render without it. Figures with a documented way of being misread —
  the indicative wage, the workforce census, grant versus budget — carry a
  caveat that cannot be dismissed rather than one behind a click.
- **No personal data, enforced rather than intended.** Every function in
  `pipeline/web/public_queries.py` declares the tables it reads and they are
  checked against the same guard the export layer uses for constraint 3. A
  test asserts the guard actually refuses a `restricted_` table, so the other
  tests are worth something.
- **Everything is citable.** Each chart has a provenance drawer with source
  URL, retrieval time, payload hash and the licence its reuse is governed by,
  and each section exports CSV or JSON with all of that written *into* the
  file — a CSV gets separated from any accompanying note within a day of
  leaving the server. A chart can also be saved as an image, and the caption
  and the pinned caveat are drawn into the picture rather than left behind in
  the page.

  The licence is one table, `pipeline/licences.py`, read from
  `docs/SOURCES.md` one module at a time. Most of this material is OGL v3;
  the workforce census and council documents are not, and the portal says so
  rather than printing "public-domain source" over everything.

Every table can be searched a column at a time and pages rather than stopping,
and says how much of the corpus it is holding: the contracts list reads
"1,000 of 98,636 rows" instead of implying it is all of them. Where a provider
carries a company or charity number, it is a link to the register, labelled
*verify at source* — an offer to go and check, not a claim that the register
agrees.

Where the warehouse does not support a figure, the portal says so instead of
drawing it. Two examples from the current corpus, both decided by measuring
the data on each request rather than by a hardcoded rule:

- **Contract value has no headline total.** A handful of cross-government
  framework notices carry ceilings in the tens of billions — 130 notices above
  £1bn account for 99.7% of the total — so the sum describes those frameworks
  rather than this sector. The page leads with the median notice and shows the
  concentration. A corpus without that problem gets its total back.
- **Workforce census figures carry their verification state per figure**,
  because `docs/CAVEATS.md` says to filter on `verified` before publishing and
  a partly-checked census is the normal state. The pinned caveat says how many
  of them have been checked and stays up until none is outstanding — it does
  not disappear the moment the first figure is signed off.

The boundary geometry for the map comes from `authorities.geometry_geojson`,
which `m00_geography` already collected with provenance, rather than from a
separately fetched boundary file that could disagree with the ONS codes every
other figure is joined on.

Third-party JavaScript is committed under
`pipeline/web/static/public/vendor/` with its versions and sources recorded,
so the portal renders wherever the pipeline runs rather than only where there
is internet.

## The review UI

`review_queue` is where every judgement call the pipeline refused to make on
its own ends up, and it does not empty itself. The web UI reads the warehouse
and writes decisions back:

```bash
./start.sh web                 # portal on /, operator tools on /admin
./start.sh web --host 127.0.0.1 # this machine only
./start.sh web --port 8080 --no-open
```

It binds every interface, so another machine on the network reaches it at
`http://<this-machine>:1801` — the addresses to use are printed at startup.

```cmd
start.cmd web
```

Five screens: an overview of what is pending by module and item type; the
queue itself, filterable and searchable, with approve/reject/reset per item or
across a selection; the Candidates tab, where a document becomes evidence; the
Census tab, where a parsed figure is checked against the archived page it came
from; a browser for every table and view; and a SQL box.

Three things exist because the queue is thousands of rows and two item types
are 72% of it:

- **The filters are in the URL.** `#review?module=m10_committee_papers` is a
  worklist you can bookmark or send to someone.
- **Dense rows.** A card each is right for reading one item and wrong for
  clearing four hundred; the toggle switches the list to one row per item.
- **Deciding a whole filtered set**, without paging through it. The count the
  page was showing is sent with the request and re-checked inside the
  transaction that does the work, so if the set moved — someone else decided
  some, or a module added more — nothing happens. An unfiltered "decide
  everything" is refused outright.

**For most item types, deciding records a judgement and nothing more.**
Approving an `unmatched_buyer_name` does not bind that name to an authority,
and approving a `possible_group_company` does not add a company to
`companies`. Those are per-module operations with their own evidence
thresholds, and the UI does not invent a generic one.

**Two item types can be answered rather than just judged.**
`authority_website_unknown` and `committee_url_unknown` — 304 of the queue —
both mean "nobody has told this pipeline where this council publishes", which
a person with a browser can settle in a minute. Those items get a URL field.
Saving one writes to `authority_url_overrides`, which
`authority_websites.website_for()` reads ahead of the code registry, so the
next run of Module 9 or 10 searches an authority it previously skipped.

The URL is fetched by the server before it is stored, through the same client
the modules use — robots respected, rate limit shared, response archived — and
what it saw is recorded next to what it was told. A URL that does not answer
is refused rather than saved: a wrong one does not fail loudly at run time, it
searches an unreachable site and finds nothing, which looks exactly like a
council that publishes nothing. Committee systems are identified by probing
the same signature paths Module 10 uses, not by asking the reviewer. What it guarantees is that the judgement is kept: every
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
- **There is no authentication, and it listens on every interface.** Anyone
  who can reach the port can read the whole warehouse — including the
  `restricted_` tables of personal data — and can approve or reject items
  under whatever name they type. **They can also start a pipeline run**, which
  fetches from real public sources under your `CONTACT_EMAIL` and rate limits,
  **write exports, and download any file in `exports/output/`.** It is built
  for a LAN you control; it is not safe on an untrusted network and must never
  be port-forwarded. `--host 127.0.0.1` restricts it to the machine running
  it, and the warning prints on every start that does not.
- **It will not fetch your own network.** Two routes take a URL and go and get
  it — the review queue's Check button and promoting a candidate — and without
  a guard those answer "yes, 192.168.1.1 responded, and here is what it looked
  like" to anyone who can reach the UI. Both now refuse a URL that resolves to
  a loopback, private, link-local, multicast, reserved or unspecified address,
  before any request and again on every redirect hop. The check is on the
  resolved address, not the hostname, so `localhost`, `127.0.0.1`,
  `127.0.0.1.nip.io` and a name whose owner points it inward are all the same
  answer. It is not a firewall: it stops this pipeline being *used* to reach
  private space, and does nothing about what the machine itself can reach.
  See `pipeline/netguard.py`.
- **What the headers do and do not cover.** Every response carries
  `Content-Security-Policy`, `X-Frame-Options: DENY`, `Referrer-Policy` and
  `nosniff`, so no other page on that network can frame `/admin` and drive it
  with your browser, and neither page can load or contact anything off this
  server. None of that authenticates anybody: they protect the browser
  in front of the UI, not the UI itself.
- **`restricted_` tables need a second click.** Opening one in the browser
  returns a refusal until you confirm. That is a guard against opening one by
  accident — the SQL box reads them like any other table, as does `sqlite3`.

## Keeping what has been collected

The warehouse is the only queryable copy of hours of deliberately slow
crawling. Back it up before anything that rewrites it — a migration, a re-run
of a module you have changed, a restore:

```bash
./start.sh backup --label before-m04-rerun
./start.sh list-backups
./start.sh restore data/backups/warehouse-20260813T131334Z.db --force
```

`backup` copies the warehouse with `VACUUM INTO`, so the snapshot is
consistent even while a run is writing to it, then reopens the copy and checks
it table by table against the source before calling it a backup. The 3.5 GiB
raw archive is **inventoried rather than copied** — it is content-addressed, so
a listing is enough to say exactly which documents are missing after a partial
loss. `restore` refuses a backup that fails its own integrity check and never
deletes the warehouse it replaces.

Both directories sit on the same disk, so this covers a bad migration and not
a dead drive. See [`docs/BACKUP.md`](docs/BACKUP.md).

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | Every table and column, generated from the live schema — never hand-edited |
| [`docs/SOURCES.md`](docs/SOURCES.md) | Each source's URL, licence, key requirement and applied rate limit |
| [`docs/CAVEATS.md`](docs/CAVEATS.md) | Known limitations, and what must not be computed |
| [`docs/BACKUP.md`](docs/BACKUP.md) | Backing the warehouse up, restoring it, and how big the archive gets |
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
