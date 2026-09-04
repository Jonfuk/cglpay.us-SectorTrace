#!/usr/bin/env bash
#
# Bootstrap and run the England-wide substance misuse sector evidence pipeline.
#
# Creates the directories the pipeline writes to, makes sure a .env exists,
# checks uv is available, syncs dependencies, then hands every argument
# straight through to the Typer CLI:
#
#   ./start.sh                     -> --help
#   ./start.sh list-modules
#
#   Collect (16 modules). `run all` resolves dependency order itself and
#   prints it before starting — m00_geography first, m04 after m03/m05,
#   m09/m10 after m15:
#   ./start.sh run m00_geography
#   ./start.sh run all
#   ./start.sh run m01_procurement --since 2024-01-01 --limit 100
#   ./start.sh run m03_charity_finance --dry-run
#
#   `run all` groups modules into dependency waves. By default each wave runs
#   one module at a time; --jobs runs a wave's modules together, which is safe
#   because they mostly target different APIs and the per-host rate limit is
#   enforced across the whole process:
#   ./start.sh run all --jobs 4
#
#   Export (each file gets a companion .provenance.json):
#   ./start.sh export all          # sheets, geojson, echarts, docs
#   ./start.sh export sheets --push
#
#   Review. Browse the warehouse and approve/reject review-queue items in a
#   browser, on port 1801. Reading is done on a read-only connection; the only
#   writes are the decisions themselves. It listens on every interface so
#   other machines on the network can reach it, and there is no login:
#   ./start.sh web
#   ./start.sh web --host 127.0.0.1    # this machine only
#   ./start.sh web --port 8080 --no-open
#
#   PostgreSQL. DATABASE_URL is required in .env; every command reads and
#   writes PostgreSQL 18. `backup` and `restore` use the verified PostgreSQL
#   snapshot path. See docs/BACKUP.md and docs/DEPLOYMENT.md.
#
#   Measure whichever backend is configured, and record it under
#   docs/benchmarks/ so a later change can be judged against it rather than
#   against a recollection. Changes nothing:
#   ./start.sh benchmark
#
#   OCR. Set OCR_ENABLED=true in .env (or in the environment) and this script
#   syncs the `ocr` extra as well, so Module 8 can read the two thirds of PFD
#   reports that are scans rather than text. Left off, those reports are
#   recorded as unreadable and the extra is not installed:
#   OCR_ENABLED=true ./start.sh run m08_pfd_reports
#
# m06, m09 and m10 produce review worklists in docs/verification/ rather than
# finished evidence — nothing they find is promoted without human confirmation.
#
set -euo pipefail

# Run from the repo root regardless of where the script was invoked from, so
# the relative paths below (and the pipeline's own data/ and logs/) always
# resolve to the same place.
cd "$(dirname "${BASH_SOURCE[0]}")"

# Colour only when attached to a terminal — otherwise escape codes end up in
# redirected logs and CI output.
if [[ -t 1 ]]; then
    RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[0;33m'
    BLUE=$'\033[0;34m'; BOLD=$'\033[1m'; RESET=$'\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; BOLD=''; RESET=''
fi

info()  { printf '%s\n' "${BLUE}==>${RESET} $*"; }
ok()    { printf '%s\n' "${GREEN}  ok${RESET} $*"; }
warn()  { printf '%s\n' "${YELLOW}  !${RESET} $*" >&2; }
error() { printf '%s\n' "${RED}${BOLD}error:${RESET} $*" >&2; }

# --- required directories -----------------------------------------------------
# Kept in step with pipeline/config.py: raw response archive, warehouse
# location, structured logs, and the human-review markdown the PDF-extracting
# modules emit.
info "Checking directories"
for dir in data/raw logs docs/verification; do
    if [[ -d "$dir" ]]; then
        ok "$dir"
    else
        mkdir -p "$dir"
        ok "created $dir"
    fi
done

# --- environment file ----------------------------------------------------------
info "Checking .env"
if [[ -f .env ]]; then
    ok ".env present"
elif [[ -f .env.example ]]; then
    cp .env.example .env
    warn "No .env found — copied .env.example to .env."
    warn "Edit .env and set CONTACT_EMAIL plus any API keys before running modules that need them."
else
    # Key names must match what pipeline/config.py actually reads, or the
    # generated file would look correct and be silently ignored.
    cat > .env <<'ENVEOF'
# Required: sent in the User-Agent of every request, and the contact point a
# site operator can use to reach you about this pipeline's traffic.
CONTACT_EMAIL=

# Seconds between requests to a single host.
DEFAULT_RATE_LIMIT_SECONDS=2.0

# PostgreSQL 18 is the only application warehouse.
DATABASE_URL=
RAW_ARCHIVE_DIR=data/raw

# Module 3 — Charity Commission register API (free key).
CHARITY_COMMISSION_API_KEY=

# Module 4 — Companies House public API (free key).
COMPANIES_HOUSE_API_KEY=

# Module 5 — CQC public API (subscription key).
CQC_SUBSCRIPTION_KEY=

# Module 8 — read PFD reports that were scanned rather than typed. Roughly two
# thirds of the backlog is paper, and without this those reports are recorded
# as unreadable instead of contributing their matters of concern.
#
# Setting this to true makes start.sh install the `ocr` extra as well. It is
# off by default because it is expensive: about nine seconds a page, and the
# first run downloads ~105 MB of models to ~/.cache/onnxtr.
OCR_ENABLED=false

# Exports — PATH to a service-account JSON file, not the JSON itself.
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_SHEETS_SPREADSHEET_ID=
ENVEOF
    warn "No .env or .env.example found — wrote a .env template."
    warn "CONTACT_EMAIL is required; the pipeline will refuse to run until it is set."
fi

# --- tooling -------------------------------------------------------------------
info "Checking uv"
if ! command -v uv >/dev/null 2>&1; then
    error "uv is not on PATH."
    printf '%s\n' "  uv manages this project's Python environment and dependencies." >&2
    printf '%s\n' "  Install it with one of:" >&2
    printf '%s\n' "    curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    printf '%s\n' "    brew install uv" >&2
    printf '%s\n' "    pip install uv" >&2
    printf '%s\n' "  Docs: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi
ok "uv $(uv --version 2>/dev/null | awk '{print $2}')"

# --- dependencies ---------------------------------------------------------------
# The `ocr` extra is installed only when OCR_ENABLED says it is wanted, and
# this is not merely an optimisation: `uv sync` removes anything the selected
# extras do not ask for. Without this check, someone who installed the extra by
# hand and switched OCR on in .env would have it silently uninstalled by the
# next run of this script, and m08 would go back to recording scans as
# unreadable with no indication why.
#
# The environment variable wins over .env, matching how pydantic-settings
# resolves the same setting inside the pipeline.
ocr_wanted=0
if [[ -f .env ]] && grep -Eiq '^[[:space:]]*OCR_ENABLED[[:space:]]*=[[:space:]]*(1|true|yes|on)[[:space:]]*$' .env; then
    ocr_wanted=1
fi
if [[ -n "${OCR_ENABLED:-}" ]]; then
    # `tr` rather than ${var,,}: macOS still ships bash 3.2.
    case "$(printf '%s' "$OCR_ENABLED" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) ocr_wanted=1 ;;
        *)             ocr_wanted=0 ;;
    esac
fi

# The storage extra follows the archive backend selector for the same reason:
# `uv sync` removes packages that are not named by the selected extras. Without
# this check, a local run with ARCHIVE_S3_BUCKET configured uninstalls boto3
# before the command that needs to construct the S3 archive can import it.
storage_wanted=0
if [[ -f .env ]] && grep -Eq '^[[:space:]]*(ARCHIVE|BACKUP)_S3_BUCKET[[:space:]]*=[[:space:]]*[^[:space:]#]' .env; then
    storage_wanted=1
fi
if [[ -n "${ARCHIVE_S3_BUCKET:-}" || -n "${BACKUP_S3_BUCKET:-}" ]]; then
    storage_wanted=1
elif [[ -n "${ARCHIVE_S3_BUCKET+set}" || -n "${BACKUP_S3_BUCKET+set}" ]]; then
    storage_wanted=0
fi

# Neo4j is a derived projection, but its driver is still an optional package.
# Select it from the same setting that enables graph commands so `start.sh
# graph rebuild` cannot uninstall the driver immediately before importing it.
graph_wanted=0
if [[ -f .env ]] && grep -Eiq '^[[:space:]]*NEO4J_ENABLED[[:space:]]*=[[:space:]]*(1|true|yes|on)[[:space:]]*$' .env; then
    graph_wanted=1
fi
if [[ -n "${NEO4J_ENABLED:-}" ]]; then
    case "$(printf '%s' "$NEO4J_ENABLED" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) graph_wanted=1 ;;
        *)             graph_wanted=0 ;;
    esac
fi

sync_args=(--quiet)
if (( ocr_wanted )); then
    sync_args+=(--extra ocr)
fi
if (( storage_wanted )); then
    sync_args+=(--extra storage)
fi
if (( graph_wanted )); then
    sync_args+=(--extra graph)
fi

info "Syncing dependencies"
if ! uv sync "${sync_args[@]}"; then
    error "uv sync failed. Run 'uv sync' without --quiet to see the full output."
    if (( ocr_wanted )); then
        printf '%s\n' "  OCR_ENABLED is set, so this tried 'uv sync --extra ocr'." >&2
        printf '%s\n' "  Unset it to start without OCR." >&2
    fi
    exit 1
fi
extras=""
if (( ocr_wanted )); then
    extras="${extras} ocr"
fi
if (( storage_wanted )); then
    extras="${extras} storage"
fi
if (( graph_wanted )); then
    extras="${extras} graph"
fi
if [[ -n "$extras" ]]; then
    ok "dependencies in sync (including the${extras} extra(s))"
else
    ok "dependencies in sync"
fi
if (( ocr_wanted )); then
    warn "OCR is on. The first scanned report downloads ~105 MB of models to ~/.cache/onnxtr,"
    warn "and reading one takes about nine seconds a page."
fi
if (( storage_wanted )); then
    ok "ARCHIVE_S3_BUCKET is set: the raw archive uses the S3 storage extra"
fi
if (( graph_wanted )); then
    ok "NEO4J_ENABLED is set: graph commands include the Neo4j driver"
fi

# --- run -------------------------------------------------------------------------
# `exec` replaces this shell so the CLI's exit code and signal handling
# (Ctrl-C during a long crawl) reach the caller unmodified.
if [[ $# -eq 0 ]]; then
    info "No arguments given — showing CLI help"
    printf '\n'
    exec uv run python -m pipeline --help
fi

exec uv run python -m pipeline "$@"
