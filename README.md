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
```

```cmd
start.cmd run m00_geography
start.cmd run m01_procurement --since 2024-01-01 --limit 100
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
| `docs/verification/` | Human-review markdown (PDF extraction diffs, document candidates) |
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

| Module | Source | Evidence |
| --- | --- | --- |
| `m00_geography` | ONS Open Geography Portal | Local authority spine, boundaries, reorganisation successors |
| `m01_procurement` | Find a Tender, Contracts Finder | Contract notices, values, suppliers, direct awards |
| `m02_tribunals` | GOV.UK employment tribunal decisions | Judgments against providers |
| `m03_charity_finance` | Charity Commission + filed accounts | Income, wages, employee numbers, agency spend, pay bands |
| `m04_companies` | Companies House | Group structure, former names, filings, officer churn |
| `m05_cqc` | CQC public API | Registered locations, ratings, inspection reports |
| `m11_public_health_grant` | DHSC | Public Health Grant allocations, incl. drug/alcohol ring-fence |

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
with any published figure.

## Development

```bash
uv run python -m pytest              # full suite
uv run python -m pytest -m integration   # live-source smoke tests (skipped by default)
```

Parsers are tested against fixtures in `tests/fixtures/` captured from real
responses. Fixtures containing personal data are anonymised: the underlying
judgments are public record, but this repository is public and the pipeline
treats claimant names as restricted.
