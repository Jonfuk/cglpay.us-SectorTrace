# SectorTrace

An England-wide **evidence pipeline** for the drug and alcohol treatment
sector. It collects public-domain evidence — procurement, pay, provider
finances, treatment activity, regulation, safeguarding — from ~30 official
sources across every commissioning area in England, stores it in a SQLite (or
PostgreSQL) warehouse with full provenance, and serves it as a public
evidence portal and an operator review UI from one stdlib HTTP server. It
exists to be a trade union pay campaign's evidence base.

The guiding principle is that a smaller dataset which can be defended line by
line is worth more than a large one that cannot:

- **Provenance or `NULL`.** Every row carries the URL it came from, when it
  was fetched, and the SHA-256 of the exact bytes, archived under
  `data/raw/`. Nothing is inferred, interpolated or defaulted — an
  unparseable field is `NULL` with a `parse_failures` row, and anything
  needing judgement goes to `review_queue`.
- **Evidence layers stay separate.** Census figures, charity accounts,
  tribunal counts and contract values are never combined into composite
  scores or cross-source ratios.
- **Nothing becomes evidence without a person.** Database triggers enforce
  it; candidate documents and machine-extracted claims stay findings until a
  named reviewer promotes them.
- **Personal data lives only in `restricted_` tables**, excluded from every
  export and every portal response by a column guard, not by intention.

## See it live

**[trace.cglpay.us](https://trace.cglpay.us)** — the public evidence portal.
Browse pay evidence, contracts, treatment demand, a page per authority and
per provider, the claims index and the map. Every figure links to its source,
retrieval date, licence and caveats; every section exports CSV or JSON with
that provenance written into the file.

**[cglpay.us](https://cglpay.us)** — the trade union pay campaign this
evidence base supports.

## Documentation

**[jonfuk.github.io/cglpay.us-SectorTrace](https://jonfuk.github.io/cglpay.us-SectorTrace/)**
— the full documentation, rebuilt from `master` on every push. Start here:

| Page | What it covers |
| --- | --- |
| [Caveats](docs/CAVEATS.md) | Known limitations, and what must **not** be computed — read before using any figure |
| [Sources](docs/SOURCES.md) | Every source's URL, licence, API-key requirement and applied rate limit |
| [Data dictionary](docs/DATA_DICTIONARY.md) | Every table and column, generated from the live schema |
| [Deployment](docs/DEPLOYMENT.md) | The PostgreSQL backend, the cutover checklist, and dual maintenance |
| [Backups](docs/BACKUP.md) | Snapshotting and restoring the warehouse on either backend |
| [AI promotion policy](docs/AI_PROMOTION_POLICY.md) | Where machine assistance is and is not allowed near evidence |
| [Analyst assistant](docs/assistant.md) | The optional, off-by-default natural-language finding aid (inference on OpenRouter) — how it is bounded and how to enable it |

The site also carries generated API reference for every module in `pipeline/`.
[`CLAUDE.md`](CLAUDE.md) records the settled decisions the codebase is built
around.

## Quick start

```bash
./start.sh                        # show CLI help
./start.sh tui                    # interactive terminal UI for the CLI
./start.sh run all                # collect from every source, in dependency order
./start.sh run m01_procurement    # run one module
./start.sh run all --jobs 4       # collect concurrently across different hosts
./start.sh web --host 127.0.0.1   # portal on /, operator review UI on /admin
./start.sh backup --label pre-change
```

`./start.sh tui` presents the same complete command tree in an interactive
terminal form, including nested commands and their options. Use `Ctrl+S` to
search, `Ctrl+T` to return to the command tree, `Ctrl+O` for command help, and
`Ctrl+R` to close the form and run the selected command. Commands that are not
on the small read-only inspection allowlist first show the exact command and
ask for confirmation; this includes warehouse, archive, export and service
operations.

For the operator landing view, use `./start.sh dashboard`. It shows warehouse
health, parse-failure pressure, and an oldest-first pending review worklist;
select a row to inspect its stored provenance. Press `f` to focus the queue
filter, press Enter to apply it, and use Ctrl+X to clear it. `d` opens recent
review decisions and `p` opens grouped parse failures. Enter a reviewer name
and optional note to approve, reject or reset an item. Every decision is
confirmed and recorded through the same audited review workflow as the web UI;
it does not promote evidence or edit a canonical table. This is deliberately
a fast backup for triage when the browser UI is inconvenient, not a replacement
for its bulk review, pipeline controls, database browser or exports.

```bash
./start.sh export all        # sheets, geojson, echarts, docs, then a zipped bundle
./start.sh export sheets     # ten CSV tabs of human-readable evidence, caveats above each header
./start.sh export geojson    # contracts / CQC locations / treatment / PFD as separate layers
./start.sh export echarts    # pre-shaped dashboard series, each carrying source and caveats
./start.sh export docs       # regenerate docs/DATA_DICTIONARY.md from the live schema
```

`./start.sh` (Linux / macOS / WSL / Git Bash) and `start.cmd` (Windows) take
the same arguments and pass them straight to the CLI. They create the
writable directories, copy `.env.example` to `.env` if it is missing, check
[`uv`](https://docs.astral.sh/uv/getting-started/installation/) is installed,
and sync dependencies. `CONTACT_EMAIL` is **required** — it is sent in the
`User-Agent` of every request and the pipeline refuses to start without it.
A few modules need a free API key (Charity Commission, Companies House, CQC);
each fails immediately naming the variable it is missing. Credentials stay out
of the repository (`.env`, `secrets/`, `*-service-account.json` are all
gitignored).

Without the wrapper scripts: `uv run python -m pipeline run m00_geography`.

## Modules

Each module owns its tables, upserts on a natural key so re-runs are
idempotent, and declares what it reads so `run all` resolves a dependency
order (everything joins to **authorities**, from `m00`; provider evidence
joins to **providers**). Collection is polite: `robots.txt` respected, one
request per two seconds per host enforced process-wide, conditional requests,
`Retry-After` honoured.

| Module | Source | Evidence |
| --- | --- | --- |
| `m00_geography` | ONS Open Geography Portal | Local authority spine, boundaries, reorganisation successors |
| `m01_procurement` | Find a Tender, Contracts Finder | Contract notices, values, suppliers, direct awards |
| `m02_tribunals` | GOV.UK employment tribunal decisions | Judgments against providers (pseudonymised), plus EAT decisions as their own layer |
| `m03_charity_finance` | Charity Commission + filed accounts | Income, wages, employee numbers, agency spend, pay bands |
| `m04_companies` | Companies House | Group structure, former names, filings, officer churn, insolvency, PSC ownership, disqualification checks |
| `m05_cqc` | CQC public API | Registered locations, ratings, inspection reports |
| `m06_workforce_census` | NHS Benchmarking Network | Vacancy, turnover, WTE and contract-type metrics — **review material, not finished evidence** |
| `m07_ndtms` | OHID via GOV.UK | Published treatment statistics; LA-level tables where they exist |
| `m08_pfd_reports` | Courts and Tribunals Judiciary | Coroners' Prevention of Future Deaths reports, workforce concerns |
| `m09_cdp_documents` | Local authority websites | Combating Drugs Partnership document **candidates** (need verification) |
| `m10_committee_papers` | Council committee systems | Committee paper **candidates** (need verification) |
| `m11_public_health_grant` | DHSC | Public Health Grant allocations, incl. the drug/alcohol ring-fence |
| `m12_fingertips` | OHID Fingertips | LA-level treatment numbers, completions, waiting times, prevalence |
| `m13_la_budgets` | MHCLG | Local authority budgeted revenue expenditure, incl. the Public Health line |
| `m14_annual_reports` | Provider annual reports | Workforce narrative and disclosure gaps, read from PDFs `m03` archived |
| `m15_foi` | mySociety register, WhatDoTheyKnow feed, council disclosure logs | **Discovery of** published FOI requests (never their response text), and an authoritative website URL per authority |
| `m16_nhs_jobs` | NHS Jobs | Advertised pay bands, contract type and closing dates — the only **direct** pay evidence here, and a floor not a total |
| `m17_statutory_pay_rates` | GOV.UK rates page | National Minimum / Living Wage rates per period and band — the statutory floor |
| `m18_living_wage` | Living Wage Foundation | Which tracked providers are accredited living wage employers, with fetch date |
| `m19_data_gov_uk` | data.gov.uk CKAN | Dataset discovery metadata and resource URLs, by keyword and exact organisation match |
| `m20_gender_pay_gap` | Gender Pay Gap service | Statutory filings matched to tracked providers — an absent provider is a review item, never a zero |
| `m21_ons_ashe` | ONS developer API | Median gross hourly pay by occupation and industry — the comparator market, side-by-side only |
| `m22_provider_pay_pages` | The tracked providers' own websites | Pay figures published on career and reward pages, attributed to the provider's own site |
| `m23_sector_universe` | *(fetches nothing)* | The sector population reconstructed from what is collected — the denominator for every "we track N of ~M" statement |
| `m24_council_spend` | Council websites | £500+ spend-transparency files on each council's own domain — actual money paid, not notices |
| `m25_skills_for_care` | Skills for Care | ASC-WDS workforce pay and turnover comparators per area, sector, service and role |
| `m26_cqc_directory` | CQC bulk exports | Cross-checks `cqc_locations` against CQC's own bulk snapshots; writes review flags, no location rows |
| `m27_ndtms_monthly` | NDTMS monthly provisional reports | Numbers in treatment, presentations and exits per authority and substance, current month |
| `m28_sar_reports` | National SAR Library | Safeguarding Adult Reviews: board name (read from the document), workforce concern terms, provider mentions |
| `m29_rough_sleeping` | MHCLG rough sleeping snapshot | Annual LA-level estimate of people sleeping rough on one autumn night, since 2010 — a comparator |
| `m30_statutory_homelessness` | MHCLG statutory homelessness (H-CLIC) | Quarterly LA-level homelessness-duty assessments and outcomes (Table A1 only) — a comparator |
| `m31_temporary_accommodation` | MHCLG temporary accommodation (H-CLIC) | Households in temporary accommodation per quarter, with the children and bed-and-breakfast breakdowns (Table TA1) |
| `m32_sab_site_reviews` | Safeguarding Adults Boards' own websites | The bounded-crawl exception to `m28`'s one-aggregator rule: SARs a board published but never submitted |
| `m33_hse_notices` | HSE public enforcement-notices register | Improvement and prohibition notices matched to a tracked provider by exact name; individuals excluded, result kept verbatim |
| `m34_icb_board_papers` | The 42 Integrated Care Boards' own websites | Every Board and committee document, captured and text-indexed for substance-misuse and provider mentions; discovery only, an ICB is not a treatment commissioner so a mention is context not a figure |

`run all` prints the order it chose before starting, and grouping modules
into dependency **waves** (`--jobs N`) lets independent backends run at once
without any host seeing a faster request rate. `m06`, `m09`, `m10` and `m20`
produce worklists reviewed in the operator UI — see
[Caveats](docs/CAVEATS.md) and the per-module docstrings.

## How it works

- **A stdlib web server** (`pipeline/web/`) — no framework, no build step, no
  CDN — serves a read-only `/api/v1/` portal at `/` and the review UI at
  `/admin`. Every figure's caveat travels with it in the payload; every
  section exports CSV/JSON and a `.provenance.json` companion; a download is
  the whole dataset, not the page's window. The API is self-documented at
  `/api`.
- **No authentication, by design.** The security model is a JSON
  content-type plus same-origin write guard, an SSRF destination guard
  (`pipeline/netguard.py`), and `--host 127.0.0.1` when the network is not
  trusted. Anyone who can reach the port can read the whole warehouse and
  start a run — do not expose it.
- **SQLite by default; PostgreSQL** behind `DATABASE_URL`, same SQL under a
  parallel migration tree. Production runs on Railway. Back up before
  anything that rewrites the warehouse: `./start.sh backup`.
- **The review UI** writes decisions back through a separate writable
  connection; the table browser and SQL box are read-only. Every decision is
  recorded with who made it, when, and the context it was taken against.

## Development

```bash
uv run python -m pytest          # full suite — offline, fixture-backed, ~2.5 min
uv run ruff check pipeline tests
uv run python -m pipeline docs-check   # generated doc blocks vs the registries
```

Some facts in `docs/` are a projection of an in-code registry — currently the
source capability matrix in [`docs/SOURCES.md`](docs/SOURCES.md), rendered
from `pipeline/web/datasets.py` and `pipeline/licences.py`. `docs-check`
fails CI when a block is stale; `pipeline docs-sync` rewrites it. Only the
text between the `<!-- BEGIN/END GENERATED -->` markers is machine-owned.

Tests never touch a real source. Live-source smoke tests sit behind the
`integration` marker and are deselected by default; they exist because a
fixture cannot notice a source quietly changing shape. Fixtures containing
personal data are anonymised — the underlying records are public, but this
repository is public and the pipeline treats claimant names as restricted.

## Licence

MIT for the code. The evidence is public-domain; each source's own licence is
in [Sources](docs/SOURCES.md) — most is OGL v3, some is not, and the portal
labels each figure accordingly.
