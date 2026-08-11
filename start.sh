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
#   Collect (13 modules; run m00_geography first — everything joins to it):
#   ./start.sh run m00_geography
#   ./start.sh run all
#   ./start.sh run m01_procurement --since 2024-01-01 --limit 100
#   ./start.sh run m03_charity_finance --dry-run
#
#   Export (each file gets a companion .provenance.json):
#   ./start.sh export all          # sheets, geojson, echarts, docs
#   ./start.sh export sheets --push
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

# Storage paths (relative to the repo root).
DATABASE_PATH=data/warehouse.db
RAW_ARCHIVE_DIR=data/raw

# Module 3 — Charity Commission register API (free key).
CHARITY_COMMISSION_API_KEY=

# Module 4 — Companies House public API (free key).
COMPANIES_HOUSE_API_KEY=

# Module 5 — CQC public API (subscription key).
CQC_SUBSCRIPTION_KEY=

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
info "Syncing dependencies"
if ! uv sync --quiet; then
    error "uv sync failed. Run 'uv sync' without --quiet to see the full output."
    exit 1
fi
ok "dependencies in sync"

# --- run -------------------------------------------------------------------------
# `exec` replaces this shell so the CLI's exit code and signal handling
# (Ctrl-C during a long crawl) reach the caller unmodified.
if [[ $# -eq 0 ]]; then
    info "No arguments given — showing CLI help"
    printf '\n'
    exec uv run python -m pipeline --help
fi

exec uv run python -m pipeline "$@"
