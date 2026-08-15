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
REM   Review. Browse the warehouse and approve/reject review-queue items in a
REM   browser, on port 1801. Reading is done on a read-only connection; the
REM   only writes are the decisions themselves. It listens on every interface
REM   so other machines on the network can reach it, and there is no login:
REM   start.cmd web
REM   start.cmd web --host 127.0.0.1    - this machine only
REM   start.cmd web --port 8080 --no-open
REM
REM   PostgreSQL. Set DATABASE_URL in .env and this script syncs the "postgres"
REM   extra, and every command above reads and writes that warehouse instead of
REM   data\warehouse.db. The SQLite file is opened read-only by both:
REM   start.cmd migrate-data --dry-run   - the plan and the preflight checks
REM   start.cmd migrate-data             - load, then verify every value
REM   start.cmd verify-migration         - check the two again, later
REM   start.cmd sync-sqlite --check      - how far apart the two warehouses are
REM   start.cmd sync-sqlite              - rebuild the SQLite one from PostgreSQL
REM
REM   "backup" and "restore" follow the configured backend: a .db snapshot on
REM   SQLite, a verified .sql.gz one on PostgreSQL. See docs\BACKUP.md and
REM   docs\DEPLOYMENT.md.
REM
REM   OCR. Set OCR_ENABLED=true in .env ^(or in the environment^) and this script
REM   syncs the "ocr" extra as well, so Module 8 can read the two thirds of PFD
REM   reports that are scans rather than text. Left off, those reports are
REM   recorded as unreadable and the extra is not installed:
REM   set OCR_ENABLED=true ^&^& start.cmd run m08_pfd_reports
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
        >>".env" echo # Module 8 - read PFD reports that were scanned rather than typed.
        >>".env" echo # Roughly two thirds of the backlog is paper, and without this those
        >>".env" echo # reports are recorded as unreadable instead of contributing their
        >>".env" echo # matters of concern. Setting this true also makes start.cmd install
        >>".env" echo # the "ocr" extra. Off by default: about nine seconds a page, and the
        >>".env" echo # first run downloads ~105 MB of models.
        >>".env" echo OCR_ENABLED=false
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
REM The "ocr" extra is installed only when OCR_ENABLED asks for it, and this is
REM not merely an optimisation: uv sync removes anything the selected extras do
REM not ask for. Without this check, someone who installed the extra by hand
REM and switched OCR on in .env would have it silently uninstalled by the next
REM run of this script, and Module 8 would go back to recording scans as
REM unreadable with no indication why.
REM
REM The environment variable wins over .env, matching how pydantic-settings
REM resolves the same setting inside the pipeline.
set "OCR_EXTRA="
if defined OCR_ENABLED (
    for %%V in (1 true yes on) do (
        if /i "%OCR_ENABLED%"=="%%V" set "OCR_EXTRA=--extra ocr"
    )
) else (
    if exist ".env" (
        for %%V in (1 true yes on) do (
            findstr /i /r /c:"^ *OCR_ENABLED *= *%%V *$" ".env" >nul 2>nul && set "OCR_EXTRA=--extra ocr"
        )
    )
)

REM The "postgres" extra, on the same rule and for a sharper version of the
REM same reason. uv sync removes what the selected extras do not ask for, so
REM with DATABASE_URL set in .env and this check absent, every run of this
REM script uninstalled psycopg — and since the warehouse of record is now the
REM PostgreSQL one, the next command failed at its first connection with
REM ModuleNotFoundError. start.sh grew this check when the port landed; this
REM file did not, and Windows is where the collection actually runs.
REM
REM Presence of the URL is the selector, matching pipeline/config.py exactly:
REM there is deliberately no second switch that could disagree with it. An
REM empty value reads as unset on both sides.
set "PG_EXTRA="
if defined DATABASE_URL (
    if not "%DATABASE_URL%"=="" set "PG_EXTRA=--extra postgres"
) else (
    if exist ".env" (
        findstr /i /r /c:"^ *DATABASE_URL *= *[^ ]" ".env" >nul 2>nul && set "PG_EXTRA=--extra postgres"
    )
)

echo ==^> Syncing dependencies
uv sync --quiet %OCR_EXTRA% %PG_EXTRA%
if errorlevel 1 (
    echo error: uv sync failed. Run "uv sync" without --quiet to see the full output. 1>&2
    if defined OCR_EXTRA (
        echo   OCR_ENABLED is set, so this tried "uv sync --extra ocr". 1>&2
        echo   Unset it to start without OCR. 1>&2
    )
    if defined PG_EXTRA (
        echo   DATABASE_URL is set, so this tried "uv sync --extra postgres". 1>&2
    )
    popd
    exit /b 1
)
if defined OCR_EXTRA (
    echo   ok dependencies in sync ^(including the ocr extra^)
    echo   ! OCR is on. The first scanned report downloads ~105 MB of models, 1>&2
    echo   ! and reading one takes about nine seconds a page. 1>&2
) else (
    if defined PG_EXTRA (
        echo   ok dependencies in sync ^(including the postgres extra^)
    ) else (
        echo   ok dependencies in sync
    )
)

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
