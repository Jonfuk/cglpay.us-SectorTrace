<a id="readme-top"></a>

<!--
*** Structure follows the Best-README-Template
*** (https://github.com/othneildrew/Best-README-Template).
*** This file is hand-maintained. See CLAUDE.md and AGENTS.md before editing.
-->

[![Tests][tests-shield]][tests-url]
[![Docs][docs-shield]][docs-url]
[![Licence: MIT][license-shield]][license-url]
[![Live portal][portal-shield]][portal-url]

<br />
<div align="center">
  <h3 align="center">SectorTrace</h3>

  <p align="center">
    An England-wide evidence pipeline for the drug and alcohol treatment
    sector, built so that every published figure can be traced back to the
    document it came from.
    <br />
    <a href="https://jonfuk.github.io/cglpay.us-SectorTrace/"><strong>Read the documentation »</strong></a>
    <br />
    <br />
    <a href="https://trace.cglpay.us">Live portal</a>
    &middot;
    <a href="https://cglpay.us">The campaign it supports</a>
    &middot;
    <a href="docs/CAVEATS.md">Caveats</a>
  </p>
</div>

<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About the project</a>
      <ul>
        <li><a href="#what-makes-it-defensible">What makes it defensible</a></li>
        <li><a href="#built-with">Built with</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting started</a></li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#what-it-collects">What it collects</a></li>
    <li><a href="#documentation">Documentation</a></li>
    <li><a href="#development">Development</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#licence">Licence</a></li>
    <li><a href="#acknowledgements">Acknowledgements</a></li>
  </ol>
</details>

## About the project

SectorTrace is the evidence base behind a trade union pay campaign in the
drug and alcohol treatment sector. It answers one question properly: when
somebody in a negotiating room disputes a number, can you show where it came
from, when it was collected, and what it does not prove?

Most work of this kind ends as a spreadsheet nobody can audit six months
later. This is built the other way round. Thirty-five collection modules pull
public-domain evidence from around thirty official sources covering every
commissioning area in England, land it in a PostgreSQL warehouse where every
single row keeps its own provenance, and serve it through a public evidence
portal at `/` and an operator review interface at `/admin`, both from one
standard-library HTTP server.

Nothing is estimated, interpolated or filled in. Nothing becomes evidence
because a script decided it should.

|  |  |
| --- | --- |
| Collection modules | 35, across roughly 30 official sources |
| Geographic coverage | Every commissioning area in England |
| Schema | 110 ordered PostgreSQL migrations, applied and recorded |
| Test suite | Around 3,400 tests, entirely offline, about two and a half minutes |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### What makes it defensible

The design consistently trades size for the ability to stand behind a
figure a year after publishing it.

* **Provenance or nothing.** Every row carries the URL it came from, the time
  it was fetched, and the SHA-256 of the exact bytes, which stay archived
  under `data/raw/`. A field that cannot be parsed is stored as `NULL` with a
  `parse_failures` row against it, never as a plausible guess.
* **No arithmetic across evidence layers.** Charity accounts, tribunal
  counts, census returns and contract values are kept apart. There is no
  composite score and no headline total, because neither would survive being
  asked how it was built.
* **A named person promotes evidence, or nobody does.** Candidate documents
  and machine-extracted claims stay findings until a reviewer accepts them,
  and database triggers enforce that rather than convention.
* **Personal data cannot leak by accident.** It lives only in `restricted_`
  tables, and a column guard strips it from every export and every response
  the portal can reach. The rule is enforced in code, not by remembering.
* **Collection that will not get anybody blocked.** robots.txt is respected,
  one request every two seconds per host is enforced across the whole
  process, `Retry-After` is honoured, and requests are conditional.
  Concurrency only ever spans different hosts. Nothing in CI or the test
  suite touches a real source.
* **Caveats travel with the numbers.** The caveat rides with the value in the
  API payload, sits above the header in the CSV, and lands in a
  `.provenance.json` companion beside every download. A download is the whole
  dataset, not the page somebody happened to be looking at.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built with

| Layer | What it uses |
| --- | --- |
| Serving | Python 3.10+ standard-library HTTP server. No framework, no ASGI, no runtime build step, no CDN. Both front ends render with the network cable unplugged. |
| Warehouse | PostgreSQL 18 with pgvector, pg_trgm and PostGIS, driven by psycopg 3. Reads go through a pooled, SELECT-only role, writes through their own connection. |
| Collection | httpx and tenacity behind a shared client that owns rate limiting, robots.txt and conditional requests. An optional Scrapy and scrapy-playwright transport exists and is off by default. |
| Document parsing | pdfplumber for text and position-based extraction, odfpy for spreadsheets, PyMuPDF and Docling in the optional document worker, OnnxTR OCR for coroner reports that arrive as paper scans. |
| CLI and TUI | Typer for the command tree, Trogon for the interactive form over it, Rich for progress and run summaries. |
| Configuration and logging | Pydantic v2 with pydantic-settings for typed configuration, structlog for structured events, python-dotenv. |
| Analysis | NetworkX for the evidence graph, with sentence-transformers, GLiNER and SetFit behind an opt-in extra, and Neo4j as an optional service. |
| Front ends | Two independent Nuxt 4 applications compiled to static output, alongside the vanilla JavaScript portal. Node is a build-time dependency only, so the production image never runs it. |
| Maps | PMTiles built offline from ONS boundaries using mapbox-vector-tile and mercantile, then served as plain bytes. |
| Optional assistant | An OpenAI-compatible client pointed at OpenRouter, disabled by default and never in the path of a stored figure. |
| Documentation | MkDocs with MaterialX, mkdocstrings and Pagefind, built with `--strict` so a renamed file or a missing nav entry fails CI. |
| Deployment | Docker Compose for local PostgreSQL and the graph service, Ansible for mirror and worker hosts, Railway in production, boto3 for S3-compatible archive transfers. |
| Observability | OpenTelemetry traces and metrics over OTLP HTTP, inert unless it is switched on. |
| Testing and lint | pytest with xdist, pytest-httpx for fixture-backed transport, ruff. |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting started

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and a
PostgreSQL 18 instance with pgvector, pg_trgm and PostGIS available.
`deploy/docker-compose.postgres.yml` provides a local one.

```bash
git clone https://github.com/Jonfuk/cglpay.us-SectorTrace.git
cd cglpay.us-SectorTrace
./start.sh
```

The start script creates the writable directories, copies `.env.example` to
`.env` if it is missing, checks `uv` is installed and syncs dependencies. Two
settings matter before a first run:

* `DATABASE_URL` is mandatory.
* `CONTACT_EMAIL` is mandatory. It goes out in the `User-Agent` of every
  request, and the pipeline refuses to start without it.

A few modules need a free API key (Charity Commission, Companies House,
CQC). Each fails immediately, naming the variable it wants. Credentials stay out of
the repository, as `.env`, `secrets/` and `*-service-account.json` are all
ignored by git.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

```bash
./start.sh                        # CLI help
./start.sh run all                # collect from every source, in dependency order
./start.sh run m01_procurement    # collect from one source
./start.sh run all --jobs 4       # run waves concurrently, never against one host
./start.sh web --host 127.0.0.1   # portal on /, operator tools on /admin
./start.sh backup --label pre-change
```

Five interactive screens cover the work that benefits from confirmation
before it runs. Each shows the exact command first, and none of them offers a
destructive operation.

| Screen | What it is for |
| --- | --- |
| `./start.sh tui` | The whole command tree as a searchable form, including nested options |
| `./start.sh dashboard` | Warehouse health, parse-failure pressure and an oldest-first review worklist |
| `./start.sh run-all` | The full collection, showing its dependency waves before starting |
| `./start.sh sync` | Additive archive and snapshot transfers, and verified PostgreSQL replacement |
| `./start.sh containers` | Status, logs, start, stop and restart for the local Compose stacks |

Exports carry provenance into the file rather than leaving it behind:

```bash
./start.sh export all        # everything below, then a zipped bundle
./start.sh export sheets     # 11 CSV tabs, caveats written in above each header
./start.sh export geojson    # contracts, CQC locations, treatment and PFD as separate layers
./start.sh export echarts    # pre-shaped dashboard series, each carrying source and caveats
./start.sh export docs       # regenerate the data dictionary from the live schema
./start.sh export ndtms      # Power BI, ViewIt archive and monthly evidence
```

`./start.sh` on Linux, macOS, WSL and Git Bash, and `start.cmd` on Windows,
take identical arguments and pass them straight to the CLI. Without the
wrappers, use `uv run python -m pipeline run m00_geography`.

There is no authentication, by explicit decision. The security model is a
JSON content-type and same-origin guard on writes, a destination guard
against SSRF in `pipeline/netguard.py`, and binding to `127.0.0.1` when the
network is not trusted. Anybody who can reach the port can read the warehouse
and start a run, so do not expose it.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## What it collects

Each module owns its tables, upserts on a natural key so re-runs are
idempotent, and declares what it reads, which is how `run all` works out a
dependency order. Everything joins back to authorities from `m00_geography`,
and provider evidence joins to providers. Full source detail, licensing and
rate limits are in [Sources](docs/SOURCES.md).

| Evidence area | Modules |
| --- | --- |
| Spine and denominator | `m00_geography` (authority spine, boundaries, reorganisation successors), `m23_sector_universe` (the sector population behind every "N of about M" statement, and it fetches nothing) |
| Money in | `m01_procurement` (Find a Tender and Contracts Finder), `m11_public_health_grant`, `m13_la_budgets`, `m24_council_spend` (transparency files over £500, money actually paid rather than notices) |
| Provider finances and structure | `m03_charity_finance`, `m04_companies`, `m14_annual_reports` |
| Pay | `m16_nhs_jobs` (the only direct pay evidence here, and a floor rather than a total), `m17_statutory_pay_rates`, `m18_living_wage`, `m20_gender_pay_gap`, `m21_ons_ashe`, `m22_provider_pay_pages`, `m25_skills_for_care` |
| Treatment activity and demand | `m07_ndtms`, `m12_fingertips`, `m27_ndtms_monthly` |
| Regulation, safety and harm | `m05_cqc`, `m26_cqc_directory`, `m02_tribunals`, `m08_pfd_reports`, `m28_sar_reports`, `m32_sab_site_reviews`, `m33_hse_notices` |
| Comparators | `m29_rough_sleeping`, `m30_statutory_homelessness`, `m31_temporary_accommodation` |
| Discovery, pending verification | `m06_workforce_census`, `m09_cdp_documents`, `m10_committee_papers`, `m15_foi`, `m19_data_gov_uk`, `m34_icb_board_papers` |

The last row is deliberate. Those modules produce worklists for a human
reviewer, not finished evidence, and the operator interface exists to work
through them.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Documentation

The full site is at
**[jonfuk.github.io/cglpay.us-SectorTrace](https://jonfuk.github.io/cglpay.us-SectorTrace/)**,
rebuilt from `master` on every push, and it carries generated API reference
for every module in `pipeline/`. Start with
[Caveats](docs/CAVEATS.md), which leads with the things that must not be
computed, then [Sources](docs/SOURCES.md) and the
[Data dictionary](docs/DATA_DICTIONARY.md), which is generated from the live
schema. [`CLAUDE.md`](CLAUDE.md) records the settled decisions the codebase
is built around.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Development

```bash
uv run python -m pytest                # offline, fixture-backed, about 2.5 minutes
uv run ruff check pipeline tests
uv run python -m pipeline docs-check   # generated doc blocks against the registries
```

Tests never touch a real source. Live-source smoke tests sit behind the
`integration` marker and are deselected by default, and they exist only
because a fixture cannot notice a source quietly changing shape. Fixtures
containing personal data are anonymised, because the underlying records may
be public but this repository is public too.

Parts of `docs/` are projections of an in-code registry. `docs-check` fails
CI when one goes stale and `docs-sync` rewrites it, with only the text
between the generated markers being machine-owned.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

This is a single-maintainer evidence base built for a specific campaign
rather than an open-contribution project. If you have found a problem with a
published figure, or a source that should be tracked, please
[open an issue](https://github.com/Jonfuk/cglpay.us-SectorTrace/issues)
before any pull request.

Read [`CLAUDE.md`](CLAUDE.md) first if you are changing anything that
produces a figure. It records decisions that are settled rather than open,
and this README is one of them. It is hand-maintained, and no AI coding
assistant should rewrite, restructure or refresh it on its own initiative.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Licence

MIT for the code. See [`LICENSE`](LICENSE).

The evidence is public domain, and each source keeps its own licence, listed
in [Sources](docs/SOURCES.md). Most of it is OGL v3 and some of it is not, so
the portal labels every figure accordingly.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgements

* Every source is credited, licensed and dated in
  [`docs/SOURCES.md`](docs/SOURCES.md). This pipeline exists because those
  bodies publish the underlying data.
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template),
  whose structure this file follows.

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
