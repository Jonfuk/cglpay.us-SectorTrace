@echo off
setlocal enabledelayedexpansion
REM ---------------------------------------------------------------------------
REM Bootstrap and run the England-wide substance misuse sector evidence
REM pipeline (Windows).
REM
REM Creates the directories the pipeline writes to, makes sure a .env exists,
REM checks uv is available, syncs dependencies, then passes every argument
REM straight through to the Typer CLI:
REM
REM   start.cmd                     -^> --help
REM   start.cmd list-modules
REM
REM   Collect ^(16 modules^). "run all" resolves dependency order itself and
REM   prints it before starting - m00_geography first, m04 after m03/m05,
REM   m09/m10 after m15:
REM   start.cmd run m00_geography
REM   start.cmd run all
REM   start.cmd run m01_procurement --since 2024-01-01 --limit 100
REM   start.cmd run m03_charity_finance --dry-run
REM
REM   "run all" groups modules into dependency waves. By default each wave runs
REM   one module at a time; --jobs runs a wave's modules together, which is safe
REM   because they mostly target different APIs and the per-host rate limit is
REM   enforced across the whole process:
REM   start.cmd run all --jobs 4
REM
REM   Export ^(each file gets a companion .provenance.json^):
REM   start.cmd export all          - sheets, geojson, echarts, docs
REM   start.cmd export sheets --push
REM
REM m06, m09 and m10 produce review worklists in docs\verification\ rather than
REM finished evidence - nothing they find is promoted without human confirmation.
REM ---------------------------------------------------------------------------

REM Run from the repo root regardless of the caller's working directory.
pushd "%~dp0"

REM --- required directories --------------------------------------------------
REM Kept in step with pipeline\config.py: raw response archive, warehouse
REM location, structured logs, and the human-review markdown emitted by the
REM PDF-extracting modules.
echo ==^> Checking directories
for %%D in ("data\raw" "logs" "docs\verification") do (
    if exist "%%~D\" (
        echo   ok %%~D
    ) else (
        mkdir "%%~D" 2>nul
        if errorlevel 1 (
            echo error: could not create %%~D 1>&2
            popd
            exit /b 1
        )
        echo   ok created %%~D
    )
)

REM --- environment file -------------------------------------------------------
echo ==^> Checking .env
if exist ".env" (
    echo   ok .env present
) else (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul
        echo   ! No .env found - copied .env.example to .env. 1>&2
        echo   ! Edit .env and set CONTACT_EMAIL plus any API keys before running modules that need them. 1>&2
    ) else (
        REM Key names must match what pipeline\config.py actually reads, or the
        REM generated file would look correct and be silently ignored.
        > ".env" echo # Required: sent in the User-Agent of every request, and the contact point a
        >>".env" echo # site operator can use to reach you about this pipeline's traffic.
        >>".env" echo CONTACT_EMAIL=
        >>".env" echo.
        >>".env" echo # Seconds between requests to a single host.
        >>".env" echo DEFAULT_RATE_LIMIT_SECONDS=2.0
        >>".env" echo.
        >>".env" echo # Storage paths ^(relative to the repo root^).
        >>".env" echo DATABASE_PATH=data/warehouse.db
        >>".env" echo RAW_ARCHIVE_DIR=data/raw
        >>".env" echo.
        >>".env" echo # Module 3 - Charity Commission register API ^(free key^).
        >>".env" echo CHARITY_COMMISSION_API_KEY=
        >>".env" echo.
        >>".env" echo # Module 4 - Companies House public API ^(free key^).
        >>".env" echo COMPANIES_HOUSE_API_KEY=
        >>".env" echo.
        >>".env" echo # Module 5 - CQC public API ^(subscription key^).
        >>".env" echo CQC_SUBSCRIPTION_KEY=
        >>".env" echo.
        >>".env" echo # Exports - PATH to a service-account JSON file, not the JSON itself.
        >>".env" echo GOOGLE_SERVICE_ACCOUNT_JSON=
        >>".env" echo GOOGLE_SHEETS_SPREADSHEET_ID=
        echo   ! No .env or .env.example found - wrote a .env template. 1>&2
        echo   ! CONTACT_EMAIL is required; the pipeline will refuse to run until it is set. 1>&2
    )
)

REM --- tooling -----------------------------------------------------------------
echo ==^> Checking uv
where uv >nul 2>nul
if errorlevel 1 (
    echo error: uv is not on PATH. 1>&2
    echo   uv manages this project's Python environment and dependencies. 1>&2
    echo   Install it with one of: 1>&2
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex" 1>&2
    echo     winget install --id=astral-sh.uv -e 1>&2
    echo     pip install uv 1>&2
    echo   Docs: https://docs.astral.sh/uv/getting-started/installation/ 1>&2
    popd
    exit /b 1
)
echo   ok uv found

REM --- dependencies --------------------------------------------------------------
echo ==^> Syncing dependencies
uv sync --quiet
if errorlevel 1 (
    echo error: uv sync failed. Run "uv sync" without --quiet to see the full output. 1>&2
    popd
    exit /b 1
)
echo   ok dependencies in sync

REM --- run -------------------------------------------------------------------------
REM Batch has no exec, so the CLI's exit code is captured and re-raised after
REM popd to keep it visible to the caller (CI, schedulers).
if "%~1"=="" (
    echo ==^> No arguments given - showing CLI help
    echo.
    uv run python -m pipeline --help
) else (
    uv run python -m pipeline %*
)
set "PIPELINE_EXIT=%ERRORLEVEL%"

popd
endlocal & exit /b %PIPELINE_EXIT%
