"""Live smoke tests: does each module still understand its source?

Every other test in this suite runs against fixtures captured from real
responses. That is the right default — it is fast, offline and deterministic —
but it cannot notice the failure this project is most exposed to: a source
quietly changing shape. A renamed spreadsheet column, a restructured PDF
heading, an API that starts paginating differently. The fixture keeps passing
because the fixture is a photograph of how the source used to look.

These tests hit the real sources, with `--limit` set small, and ask three
questions per module:

  1. does it run without raising?
  2. did it write anything?
  3. do the rows it wrote carry actual evidence, not just provenance and NULLs?

Question 3 is the one that catches drift. A parser whose column headings no
longer match will happily write a row per record with every value NULL, log a
pile of parse_failures, and exit zero. That looks like a successful run.

Skipped by default (`addopts = -m 'not integration'`). To run them:

    uv run python -m pytest -m integration

Expect this to take a while and to make real requests at the pipeline's normal
one-per-two-seconds-per-host rate. Do not run it in a loop.

The modules share one temporary warehouse and run in dependency order, so
m04 sees the company numbers m03/m05 publish and m09/m10 see the authority
websites m15 registers. Where a small `--limit` upstream leaves a downstream
module with nothing to work on, that module skips with a reason naming the
upstream table — a skip that says why is honest; a pass over zero rows is not.

With `DATABASE_URL` configured, that temporary warehouse is a **schema of its
own** on the PostgreSQL server, built by the PostgreSQL migration tree and
dropped at the end. This is the one place in the project where real modules
write into a migrated schema, which the migration plan asked for deliberately;
it is also the only way "temporary" can stay true on that backend, because
`database_path` selects nothing once a URL is set.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import catalog, db
from pipeline.config import get_settings
from pipeline.registry import (
    MODULE_REGISTRY,
    ModuleContext,
    discover_modules,
    resolve_run_order,
)

discover_modules()

# review_queue and parse_failures are shared by every module, so "did this run
# write anything" has to be asked per module for them.
_SHARED_TABLES = {"review_queue", "parse_failures"}


@dataclass(frozen=True)
class Smoke:
    """What a live run of one module must produce to count as working."""

    module: str
    # At least one of these must gain rows.
    produces: tuple[str, ...]
    # (table, column) pairs carrying the actual evidence — the values that go
    # blank when a source changes shape. Asserted only on tables that gained
    # rows, and at least one pair must end up asserted.
    signal: tuple[tuple[str, str], ...]
    # Settings attribute that must be set, or the test skips rather than
    # failing on a credential the checkout was never given.
    requires_key: str | None = None
    # SQL COUNT that must be non-zero for the run to be meaningful. Zero means
    # an upstream module produced nothing to work from, which is a skip.
    precondition: str | None = None
    precondition_note: str = ""
    limit: int | None = 5
    note: str = ""


SMOKE_SPECS: dict[str, Smoke] = {spec.module: spec for spec in (
    Smoke(
        module="m00_geography",
        produces=("authorities",),
        signal=(("authorities", "name"), ("authorities", "region"),
                ("authorities", "geometry_geojson")),
        limit=None,
        note="Ignores --limit: the authority spine is one bulk fetch and a "
              "partial spine would make every downstream module meaningless.",
    ),
    Smoke(
        module="m01_procurement",
        produces=("contracts",),
        signal=(("contracts", "title"), ("contracts", "buyer_name"),
                ("contracts", "date_published")),
        note="value_core is deliberately not a signal column — plenty of real "
              "notices publish no value, and asserting on it would fail honestly "
              "empty rows.",
    ),
    Smoke(
        module="m02_tribunals",
        produces=("tribunal_cases",),
        signal=(("tribunal_cases", "respondent_normalised"),
                ("tribunal_cases", "decision_date")),
    ),
    Smoke(
        module="m03_charity_finance",
        produces=("charity_financials", "charity_accounts_documents"),
        signal=(("charity_financials", "total_income"),
                ("charity_accounts_documents", "document_url")),
        requires_key="charity_commission_api_key",
        note="charity_accounts_extracts is not required: whether a given PDF "
              "yields a staff-costs note is a property of that PDF, not of the "
              "parser working.",
    ),
    Smoke(
        module="m04_companies",
        produces=("companies",),
        signal=(("companies", "company_name"), ("companies", "company_status")),
        requires_key="companies_house_api_key",
        precondition="SELECT COUNT(*) FROM provider_identifiers WHERE scheme = 'company_number'",
        precondition_note="m03/m05 published no company numbers at this --limit, "
                           "so there is nothing to look up",
    ),
    Smoke(
        module="m05_cqc",
        produces=("cqc_locations", "cqc_providers"),
        signal=(("cqc_locations", "location_name"), ("cqc_locations", "postal_code"),
                ("cqc_providers", "provider_name")),
        requires_key="cqc_subscription_key",
        note="Slow regardless of --limit: the CQC API has no name filter, so "
              "the full provider index is paged before anything is filtered.",
    ),
    Smoke(
        module="m06_workforce_census",
        produces=("workforce_census_reports", "workforce_census_metrics"),
        signal=(("workforce_census_reports", "document_url"),
                ("workforce_census_metrics", "value")),
        limit=None,
        note="Ignores --limit: one census PDF per year, parsed whole.",
    ),
    Smoke(
        module="m07_ndtms",
        produces=("ndtms_publications", "ndtms_la_statistics"),
        signal=(("ndtms_publications", "document_url"),
                ("ndtms_la_statistics", "value"),
                ("ndtms_la_statistics", "ons_code")),
        limit=1,
        note="--limit counts publications, and one publication is already "
              "thousands of rows.",
    ),
    Smoke(
        module="m08_pfd_reports",
        produces=("pfd_reports",),
        signal=(("pfd_reports", "report_date"), ("pfd_reports", "coroner_area"),
                ("pfd_reports", "matters_of_concern")),
    ),
    Smoke(
        module="m09_cdp_documents",
        produces=("cdp_document_candidates", "review_queue"),
        signal=(("cdp_document_candidates", "candidate_url"),),
        precondition="SELECT COUNT(*) FROM authority_foi_profiles WHERE home_page_url IS NOT NULL",
        precondition_note="m15 registered no authority websites, so there is "
                           "nowhere to search",
        note="A discovery module: finding no candidate is a real outcome, and "
              "lands in review_queue. What must not happen is finding neither.",
    ),
    Smoke(
        module="m10_committee_papers",
        produces=("committee_paper_candidates", "authority_committee_systems", "review_queue"),
        signal=(("committee_paper_candidates", "document_url"),),
        precondition="SELECT COUNT(*) FROM authority_foi_profiles WHERE home_page_url IS NOT NULL",
        precondition_note="m15 registered no authority websites, so there is "
                           "nowhere to search",
        note="Same discovery caveat as m09.",
    ),
    Smoke(
        module="m11_public_health_grant",
        produces=("public_health_grants",),
        signal=(("public_health_grants", "amount"),
                ("public_health_grants", "financial_year"),
                ("public_health_grants", "grant_type")),
        limit=None,
        note="Ignores --limit. grant_type is a signal column because the "
              "drug and alcohol line is the reason this module exists, and a "
              "column-span change silently dropped it once already.",
    ),
    Smoke(
        module="m12_fingertips",
        produces=("fingertips_indicators", "fingertips_la_values"),
        signal=(("fingertips_indicators", "indicator_name"),
                ("fingertips_la_values", "value"),
                ("fingertips_la_values", "ons_code")),
    ),
    Smoke(
        module="m13_la_budgets",
        produces=("la_budget_publications", "la_revenue_budgets"),
        signal=(("la_budget_publications", "document_url"),
                ("la_revenue_budgets", "amount"),
                ("la_revenue_budgets", "ons_code")),
        limit=1,
        note="--limit counts publications; one is already ~50k rows.",
    ),
    Smoke(
        module="m14_annual_reports",
        produces=("provider_annual_reports", "provider_report_disclosure"),
        signal=(("provider_annual_reports", "page_count"),
                ("provider_report_disclosure", "topic")),
        precondition="SELECT COUNT(*) FROM charity_accounts_documents",
        precondition_note="m03 archived no accounts PDFs at this --limit, so "
                           "there is nothing to read",
        note="provider_report_passages is not required — a report that "
              "discloses nothing is exactly the finding this module records, "
              "and it records it in provider_report_disclosure.",
    ),
    Smoke(
        module="m15_foi",
        produces=("authority_foi_profiles",),
        signal=(("authority_foi_profiles", "authority_name"),
                ("authority_foi_profiles", "wdtk_body_slug")),
        precondition="SELECT COUNT(*) FROM authorities",
        precondition_note="m00 produced no authorities to match bodies against",
        note="home_page_url is not a signal column: mySociety publish a home "
              "page for most bodies but not all, and a missing one is recorded "
              "rather than invented.",
    ),
    Smoke(
        module="m16_nhs_jobs",
        produces=("nhs_job_adverts",),
        signal=(("nhs_job_adverts", "employer_name_raw"),
                ("nhs_job_adverts", "job_title"),
                ("nhs_job_adverts", "posted_date")),
        note="salary_min is deliberately NOT a signal column. Plenty of real "
              "adverts publish 'Depends on experience', and asserting on it "
              "would fail an advert that is honestly recorded as stating no "
              "figure. employer_name_raw is the one that matters: it is what "
              "attribution rests on, and it is what goes blank if the results "
              "markup changes shape.",
    ),
)}

# Dependency order, so the shared warehouse is built up the same way `run all`
# builds it. pytest executes parametrised cases in the order given.
SMOKE_ORDER: list[Smoke] = [SMOKE_SPECS[name] for name in resolve_run_order(list(SMOKE_SPECS))]


# --- helpers -------------------------------------------------------------------

def _count(conn: sqlite3.Connection, table: str, module: str) -> int:
    if table in _SHARED_TABLES:
        return conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE module = ?", (module,)).fetchone()[0]
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _columns(conn, table: str) -> set[str]:
    # Through the catalog rather than `PRAGMA table_info`: with DATABASE_URL
    # set, this suite runs against PostgreSQL, which has no such pragma.
    return {column["name"] for column in catalog.columns_of(conn, table)}


# --- fixtures ------------------------------------------------------------------

@dataclass
class Warehouse:
    """sqlite3.Connection is a C type and takes no extra attributes, so the
    settings the modules need travel alongside it rather than on it.
    """
    conn: sqlite3.Connection
    settings: object


def _configured_backend_settings():
    """The operator's real settings, including `DATABASE_URL` from `.env`.

    `tests/conftest.py` blanks `DATABASE_URL` in the environment for every
    test, and that is right: an offline test that found a real server would
    write to it. This file is the one place in the suite that is *meant* to
    run against the working configuration — it uses the real API keys and the
    real politeness delay for the same reason — so it reads the value back out
    of `.env`, which is where the environment variable was hiding.

    Safe only because of the schema isolation below. Before that existed this
    would have pointed sixteen live modules at the working warehouse.
    """
    settings = get_settings()
    if settings.database_url:
        return settings
    from dotenv import dotenv_values

    from pipeline.config import REPO_ROOT

    url = (dotenv_values(REPO_ROOT / ".env") or {}).get("DATABASE_URL")
    if not url or not url.strip():
        return settings
    return settings.model_copy(update={"database_url": url.strip()})


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory) -> Warehouse:
    """One throwaway warehouse shared by every module in this file.

    Real settings (so API keys and the real politeness delay apply), temporary
    paths (so a smoke run never writes into data/warehouse.db or mixes test
    bytes into the raw evidence archive).

    Throwaway has to mean throwaway on either backend. With `DATABASE_URL`
    set, `database_path` stops selecting anything — `db.get_connection` reads
    the URL — so overriding the path alone would have pointed every module in
    this file at the working PostgreSQL warehouse and written live-crawl rows
    into it. That is the opposite of what the docstring above promises, and it
    would be silent. So the PostgreSQL run gets a schema of its own, built by
    the PostgreSQL migration tree and dropped afterwards, which is also what
    the migration plan asked this run to prove: that real modules can write
    into a migrated schema.
    """
    base = tmp_path_factory.mktemp("integration")
    settings = _configured_backend_settings().model_copy(update={
        "database_path": base / "warehouse.db",
        "raw_archive_dir": base / "raw",
        "logs_dir": base / "logs",
    })

    schema = None
    if settings.database_backend == "postgres":
        from pipeline import pg

        schema = f"smoke_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
        admin = pg.connect(settings.database_url)
        try:
            admin.execute(f"CREATE SCHEMA {catalog.quote(schema)}")
            admin.commit()
        finally:
            admin.close()
        settings = settings.model_copy(update={
            "database_url": pg.with_schema(settings.database_url, schema),
            # The read-only URL is not scoped and is not used by any module;
            # dropped so nothing in a fixture reaches for it and lands in the
            # working warehouse by accident.
            "database_ro_url": None,
        })

    conn = db.get_connection(settings)
    # migrations_dir_for, not settings.migrations_dir: the latter is always the
    # SQLite tree, and naming it here applied SQLite DDL to PostgreSQL. It
    # happened to be a no-op only because both trees hold the same filenames
    # and the target was already migrated.
    db.apply_migrations(conn, db.migrations_dir_for(settings))
    conn.commit()
    yield Warehouse(conn=conn, settings=settings)
    conn.close()

    if schema:
        from pipeline import pg

        admin = pg.connect(_configured_backend_settings().database_url)
        try:
            admin.execute(f"DROP SCHEMA {catalog.quote(schema)} CASCADE")
            admin.commit()
        finally:
            admin.close()


# --- the smoke tests ------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.parametrize("spec", SMOKE_ORDER, ids=lambda s: s.module)
def test_module_still_reads_its_source(spec: Smoke, warehouse: Warehouse) -> None:
    conn, settings = warehouse.conn, warehouse.settings

    if spec.requires_key and not getattr(settings, spec.requires_key):
        pytest.skip(f"{spec.requires_key.upper()} is not set — {spec.module} cannot run")

    if spec.precondition:
        if conn.execute(spec.precondition).fetchone()[0] == 0:
            pytest.skip(f"{spec.module}: {spec.precondition_note}")

    before = {table: _count(conn, table, spec.module) for table in spec.produces}

    ctx = ModuleContext(conn=conn, settings=settings, since=None,
                        dry_run=False, limit=spec.limit)
    MODULE_REGISTRY[spec.module](ctx)
    conn.commit()

    after = {table: _count(conn, table, spec.module) for table in spec.produces}
    gained = {table for table in spec.produces if after[table] > before[table]}
    assert gained, (
        f"{spec.module} ran against its live source and wrote nothing to "
        f"{', '.join(spec.produces)}. Row counts unchanged: {before}. "
        "Either the source moved or its shape changed."
    )

    # 2. The rows carry evidence, not just provenance.
    asserted = 0
    for table, column in spec.signal:
        if table not in gained:
            continue
        populated = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL").fetchone()[0]
        assert populated > 0, (
            f"{spec.module} wrote {after[table]} rows to {table} but "
            f"{column} is NULL in every one of them — the classic shape-change "
            "signature: the rows arrive, the values do not."
        )
        asserted += 1
    assert asserted, (
        f"{spec.module} gained rows only in {sorted(gained)}, none of which "
        "carry a signal column. The run proves nothing; add a signal column "
        "for that table."
    )

    # 3. Provenance, on the tables that are supposed to carry it.
    for table in gained:
        if table in _SHARED_TABLES:
            continue
        if not {"source_url", "retrieved_at"} <= _columns(conn, table):
            continue
        missing = db.rows_missing_provenance(conn, table)
        assert not missing, (
            f"{spec.module} wrote {len(missing)} rows to {table} without a "
            "source_url or retrieved_at."
        )


@pytest.mark.integration
def test_the_real_warehouse_carries_provenance_throughout() -> None:
    """Sweep the working warehouse, not a test one.

    The per-module checks above only see rows written during this run. This
    catches a table that lost provenance at some point in the warehouse's
    history — including from a module version that has since been fixed.
    """
    settings = _configured_backend_settings()
    if (settings.database_backend == "sqlite"
            and not Path(settings.database_path).exists()):
        pytest.skip(f"no warehouse at {settings.database_path} — nothing to sweep")

    conn = db.get_connection(settings)
    try:
        # Through the catalog, so this sweeps whichever warehouse is
        # configured. It was `sqlite_master`, which is the one table a
        # PostgreSQL warehouse does not have — so the check that exists to
        # sweep the *working* warehouse would have failed to run against it.
        tables = [name for name in catalog.table_names(conn)
                   if not name.startswith(db.RESTRICTED_PREFIX)]
        offenders: dict[str, int] = {}
        for table in tables:
            if not {"source_url", "retrieved_at"} <= _columns(conn, table):
                continue
            missing = db.rows_missing_provenance(conn, table)
            if missing:
                offenders[table] = len(missing)
        assert not offenders, f"rows without provenance: {offenders}"
    finally:
        conn.close()


# --- coverage guards (these run by default) ---------------------------------------

def test_every_registered_module_has_a_smoke_test() -> None:
    """Otherwise a new module joins the pipeline with no live coverage and
    nothing says so.
    """
    real = {n for n in MODULE_REGISTRY if n.startswith("m") and n[1:3].isdigit()}
    assert sorted(real - set(SMOKE_SPECS)) == []


def test_every_smoke_test_names_a_real_module() -> None:
    assert sorted(set(SMOKE_SPECS) - set(MODULE_REGISTRY)) == []


def test_smoke_tests_run_in_dependency_order() -> None:
    ordered = [spec.module for spec in SMOKE_ORDER]
    assert ordered == resolve_run_order(list(SMOKE_SPECS))


def test_every_spec_table_and_column_exists(conn: sqlite3.Connection) -> None:
    """A typo in a table or column name would turn an integration failure into
    an OperationalError months later, on the one run nobody wants noise from.
    Checked here against the migrated schema, offline.
    """
    for spec in SMOKE_ORDER:
        for table in spec.produces:
            assert _columns(conn, table), f"{spec.module} produces unknown table {table}"
        for table, column in spec.signal:
            assert table in spec.produces, \
                f"{spec.module} has a signal column on {table}, which it does not declare"
            assert column in _columns(conn, table), \
                f"{spec.module}: {table}.{column} does not exist"


def test_every_precondition_is_valid_sql(conn: sqlite3.Connection) -> None:
    for spec in SMOKE_ORDER:
        if spec.precondition:
            conn.execute(spec.precondition).fetchone()
            assert spec.precondition_note.strip(), \
                f"{spec.module} skips on a precondition without saying why"


def test_modules_that_ignore_limit_say_so() -> None:
    """`--limit` is the only thing keeping this suite polite. A module that
    silently ignores it should be visible in the spec, not a surprise.
    """
    for spec in SMOKE_ORDER:
        if spec.limit is None:
            assert "limit" in spec.note.lower(), \
                f"{spec.module} sets no --limit and does not explain why"
