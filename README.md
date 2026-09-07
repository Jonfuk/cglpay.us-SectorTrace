<a id="readme-top"></a>

<!--
*** This README uses the structure and conventions of the Best-README-Template
*** (https://github.com/othneildrew/Best-README-Template), adapted for a
*** single-maintainer evidence pipeline rather than an open-contribution
*** project. Sections that template assumes (open PR contributions, a demo
*** GIF) are trimmed or reworded where they don't apply — nothing below is
*** invented to fill a section shape.
-->

[![Tests][tests-shield]][tests-url]
[![Docs][docs-shield]][docs-url]
[![License: MIT][license-shield]][license-url]
[![Live portal][portal-shield]][portal-url]

<br />
<div align="center">
  <h3 align="center">SectorTrace</h3>

  <p align="center">
    An England-wide, provenance-first evidence pipeline for the drug and
    alcohol treatment sector — built as the evidence base for a trade union
    pay campaign.
    <br />
    <a href="https://jonfuk.github.io/cglpay.us-SectorTrace/"><strong>Explore the docs »</strong></a>
    <br />
    <br />
    <a href="https://trace.cglpay.us">View the live portal</a>
    &middot;
    <a href="https://cglpay.us">The campaign this evidence supports</a>
    &middot;
    <a href="docs/CAVEATS.md">Caveats — read before using any figure</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
        <li><a href="#design-principles">Design principles</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#modules">Modules</a></li>
    <li><a href="#how-it-works">How It Works</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#development">Development</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
## About The Project

SectorTrace collects public-domain evidence — procurement, pay, provider
finances, treatment activity, regulation, safeguarding — from around 30
official sources across every commissioning area in England. It stores what
it collects in a PostgreSQL warehouse with full provenance, and serves that
warehouse as a public evidence portal (`/`) and an operator review UI
(`/admin`) from one stdlib HTTP server. It exists to be a trade union pay
campaign's evidence base: a figure that can still be defended a year later in
a room where someone disputes it.

**[trace.cglpay.us](https://trace.cglpay.us)** is the public portal — pay
evidence, contracts, treatment demand, a page per authority and per provider,
the claims index and the map. Every figure links to its source, retrieval
date, licence and caveats; every section exports CSV or JSON with that
provenance written into the file.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Design principles

The guiding principle is that a smaller dataset which can be defended line by
line is worth more than a large one that cannot. This is enforced, not just
stated:

* **Provenance or `NULL`.** Every row carries the URL it came from, when it
  was fetched, and the SHA-256 of the exact bytes, archived under
  `data/raw/`. Nothing is inferred, interpolated or defaulted — an
  unparseable field is `NULL` with a `parse_failures` row, and anything
  needing judgement goes to `review_queue`.
* **Evidence layers stay separate.** Census figures, charity accounts,
  tribunal counts and contract values are never combined into composite
  scores or cross-source ratios.
* **Nothing becomes evidence without a person.** Database triggers enforce
  it; candidate documents and machine-extracted claims stay findings until a
  named reviewer promotes them.
* **Personal data lives only in `restricted_` tables**, excluded from every
  export and every portal response by a column guard, not by intention.
* **No authentication, by design.** The security model is a JSON
  content-type plus same-origin write guard, an SSRF destination guard, and
  `--host 127.0.0.1` when the network is not trusted — see
  [How It Works](#how-it-works).

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

* [![Python][python-shield]][python-url] — stdlib only for the web server: no framework, no ASGI, no build step, no CDN
* [![PostgreSQL][postgres-shield]][postgres-url] with `pgvector`, `pg_trgm` and PostGIS
* [![uv][uv-shield]][uv-url] for dependency and environment management
* Vanilla JavaScript front ends (`pipeline/web/static/`, `frontend/`) — both render with the network cable unplugged

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

### Prerequisites

* [uv](https://docs.astral.sh/uv/getting-started/installation/)
* PostgreSQL 18, with the `pgvector`, `pg_trgm` and PostGIS extensions
  available — `deploy/docker-compose.postgres.yml` provides a local one
* `CONTACT_EMAIL` set before any run that fetches: it is sent in the
  `User-Agent` of every request and the pipeline refuses to start without it
* A few modules need a free API key (Charity Commission, Companies House,
  CQC); each fails immediately naming the variable it is missing

### Installation

```bash
git clone https://github.com/Jonfuk/cglpay.us-SectorTrace.git
cd cglpay.us-SectorTrace
./start.sh            # Linux / macOS / WSL / Git Bash — start.cmd on Windows
```

`./start.sh` creates the writable directories, copies `.env.example` to
`.env` if it is missing, checks `uv` is installed, and syncs dependencies.
Credentials stay out of the repository (`.env`, `secrets/`,
`*-service-account.json` are all gitignored). `DATABASE_URL` is mandatory —
point it at the Compose PostgreSQL instance or your own.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- USAGE -->
## Usage

```bash
./start.sh                        # show CLI help
./start.sh tui                    # interactive terminal UI for the CLI
./start.sh sync                   # backup / sync cockpit
./start.sh containers             # Docker Compose management cockpit
./start.sh run-all                # complete run cockpit (--jobs 14 default)
./start.sh run all                # collect from every source, in dependency order
./start.sh run m01_procurement    # run one module
./start.sh run all --jobs 4       # collect concurrently across different hosts
./start.sh web --host 127.0.0.1   # portal on /, operator review UI on /admin
./start.sh backup --label pre-change
```

`./start.sh tui` presents the same complete command tree in an interactive
terminal form, including nested commands and their options. Use `Ctrl+S` to
search, `Ctrl+T` to return to the command tree, `Ctrl+O` for command help, and
`Ctrl+R` to close the form and run the selected command. Commands that are
not on the small read-only inspection allowlist first show the exact command
and ask for confirmation; this includes warehouse, archive, export and
service operations.

For the operator landing view, use `./start.sh dashboard`. It shows warehouse
health, parse-failure pressure, and an oldest-first pending review worklist;
select a row to inspect its stored provenance. Press `f` to focus the queue
filter, press Enter to apply it, and use Ctrl+X to clear it. `d` opens recent
review decisions and `p` opens grouped parse failures. Enter a reviewer name
and optional note to approve, reject or reset an item. Every decision is
confirmed and recorded through the same audited review workflow as the web
UI; it does not promote evidence or edit a canonical table. This is
deliberately a fast backup for triage when the browser UI is inconvenient,
not a replacement for its bulk review, pipeline controls, database browser or
exports.

For backup and transfer work, use `./start.sh sync`. The separate screen can
preview and confirm additive raw-archive transfers between local disk and
`ARCHIVE_S3_*`, additive warehouse-snapshot transfers between `data/backups`
and `BACKUP_S3_*`, and verified PostgreSQL replacement in either direction
between `DATABASE_URL` and `DATABASE_SOURCE_URL`. PostgreSQL replacement
backs up the populated target first; no operation merges two writable
warehouses or deletes remote/local files.

For administration of the local Compose stacks, use `./start.sh containers`.
It can inspect status and recent logs, or start, stop, and restart a selected
Compose stack/service after confirmation. It does not offer `down -v`, volume
deletion, or arbitrary container removal.

For the full collection, use `./start.sh run-all`. It shows the dependency
waves before starting and defaults to `--jobs 14`; the form also exposes
`--since`, `--limit`, the m01 source channel, and `--dry-run`. It uses the
same runner and durable run ledger as the CLI and web operator UI.

```bash
./start.sh export all        # sheets, geojson, echarts, docs, then a zipped bundle
./start.sh export sheets     # ten CSV tabs of human-readable evidence, caveats above each header
./start.sh export geojson    # contracts / CQC locations / treatment / PFD as separate layers
./start.sh export echarts    # pre-shaped dashboard series, each carrying source and caveats
./start.sh export docs       # regenerate docs/DATA_DICTIONARY.md from the live schema
./start.sh export ndtms      # stream Power BI, ViewIt archive, and monthly evidence
```

Without the wrapper scripts: `uv run python -m pipeline run m00_geography`.

_For the full command reference and generated API docs, see the
[Documentation][docs-url]._

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MODULES -->
## Modules

Each module owns its tables, upserts on a natural key so re-runs are
idempotent, and declares what it reads so `run all` resolves a dependency
order (everything joins to **authorities**, from `m00`; provider evidence
joins to **providers**). Collection is polite: `robots.txt` respected, one
request per two seconds per host enforced process-wide, conditional
requests, `Retry-After` honoured.

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

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- HOW IT WORKS -->
## How It Works

* **A stdlib web server** (`pipeline/web/`) — no framework, no build step, no
  CDN — serves a read-only `/api/v1/` portal at `/` and the review UI at
  `/admin`. Every figure's caveat travels with it in the payload; every
  section exports CSV/JSON and a `.provenance.json` companion; a download is
  the whole dataset, not the page's window. The API is self-documented at
  `/api`.
* **No authentication, by design.** The security model is a JSON
  content-type plus same-origin write guard, an SSRF destination guard
  (`pipeline/netguard.py`), and `--host 127.0.0.1` when the network is not
  trusted. Anyone who can reach the port can read the whole warehouse and
  start a run — do not expose it.
* **PostgreSQL** behind `DATABASE_URL`, with `pgvector`, `pg_trgm` and
  PostGIS as required extensions. Production runs on Railway. Back up before
  anything that rewrites the warehouse: `./start.sh backup`.
* **The review UI** writes decisions back through a separate writable
  connection; the table browser and SQL box are read-only. Every decision is
  recorded with who made it, when, and the context it was taken against.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ROADMAP -->
## Roadmap

Findings and phase status live in
[`docs/upgrade-roadmap.md`](docs/upgrade-roadmap.md), not here, so there is
one place tracking it rather than two that can drift apart.

See the [open issues](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues)
for individually tracked items.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

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

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTRIBUTING -->
## Contributing

This is a single-maintainer evidence base built for a specific campaign, not
an open-contribution project — there is no CONTRIBUTING guide or issue
template set up here. If you've spotted a factual problem with a published
figure, a source SectorTrace should be tracking, or a bug, please
[open an issue](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues)
describing it; that is the right channel before any pull request.

Read [`CLAUDE.md`](CLAUDE.md) before touching anything that produces a
figure — it records the settled decisions the codebase is built around, and
they are not defaults to re-litigate in a PR. **This README is one of
them**: it is maintained by hand and is not to be rewritten, restructured or
"improved" by an AI coding assistant on its own initiative — see the note at
the top of `CLAUDE.md`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- LICENSE -->
## License

Distributed under the MIT License for the code — see [`LICENSE`](LICENSE).

The evidence itself is public-domain; each source's own licence is listed in
[Sources](docs/SOURCES.md) — most is OGL v3, some is not, and the portal
labels each figure accordingly.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- CONTACT -->
## Contact

Jon Fuk — [jon@jonf.uk](mailto:jon@jonf.uk)

Project link: [https://github.com/Jonfuk/cglpay.us-SectorTrace](https://github.com/Jonfuk/cglpay.us-SectorTrace)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

* Every source SectorTrace collects from is credited, licensed and dated in
  [`docs/SOURCES.md`](docs/SOURCES.md) — the pipeline exists only because
  these bodies publish the underlying data.
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template),
  whose structure this document follows.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[tests-shield]: https://img.shields.io/github/actions/workflow/status/Jonfuk/cglpay.us-SectorTrace/tests.yml?label=tests&style=for-the-badge
[tests-url]: https://github.com/Jonfuk/cglpay.us-SectorTrace/actions/workflows/tests.yml
[docs-shield]: https://img.shields.io/github/actions/workflow/status/Jonfuk/cglpay.us-SectorTrace/docs.yml?label=docs&style=for-the-badge
[docs-url]: https://jonfuk.github.io/cglpay.us-SectorTrace/
[license-shield]: https://img.shields.io/github/license/Jonfuk/cglpay.us-SectorTrace.svg?style=for-the-badge
[license-url]: https://github.com/Jonfuk/cglpay.us-SectorTrace/blob/master/LICENSE
[portal-shield]: https://img.shields.io/badge/live_portal-trace.cglpay.us-blue?style=for-the-badge
[portal-url]: https://trace.cglpay.us
[python-shield]: https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org/
[postgres-shield]: https://img.shields.io/badge/postgresql-18-4169E1?style=for-the-badge&logo=postgresql&logoColor=white
[postgres-url]: https://www.postgresql.org/
[uv-shield]: https://img.shields.io/badge/uv-package_manager-DE5FE9?style=for-the-badge
[uv-url]: https://docs.astral.sh/uv/
