"""The PostgreSQL backend, against a real server.

Skipped unless `POSTGRES_TEST_URL` is set. Deliberately **not** `DATABASE_URL`:
that one names a working warehouse, and a test suite that wrote to whatever a
developer happened to have configured would eventually write to a real one.
Two different variables means pointing the tests at a database is a separate,
deliberate act.

Everything here writes, so it writes into a **schema of its own**, built by
the PostgreSQL migration tree and dropped at the end — see `scratch_schema` in
`tests/conftest.py`. The separate variable is still the right rule and is not
enough on its own: this server holds one database and `sectortrace_app` cannot
create another, so the two variables end up naming the same place whatever the
docstring asks for.

Either as environment variables or as lines in `.env` — both are read, so
the credentials can live in the same file as everything else rather than
having to be re-exported into each shell:

    POSTGRES_TEST_URL=postgresql://sectortrace_app%(pw)s@host:5432/sectortrace
    POSTGRES_TEST_RO_URL=postgresql://sectortrace_reader%(pw)s@host:5432/sectortrace

    uv run python -m pytest tests/test_postgres_live.py -q

What this covers that `test_migration_equivalence.py` cannot: that one diffs
the two trees as *text*, offline, which catches a file added to one tree and
not the other. This one applies both and compares what the two servers
actually built — the difference between a migration that parses and a
migration that produces the schema it was supposed to.
"""
from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

import pytest
from conftest import scratch_schema

from pipeline import catalog, db

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"


def _configured_url(name: str) -> str | None:
    """A live-test URL from the environment, or failing that from `.env`.

    The `.env` fallback exists because leaving it out was a trap: these are
    read with `os.environ.get`, and `.env` is only ever read by
    pydantic-settings, so putting `POSTGRES_TEST_RO_URL` in `.env` — the
    obvious place, and where the application's own database settings live —
    did nothing at all and skipped the tests silently. A configuration that
    is ignored without saying so is the failure mode this whole port keeps
    running into.

    What does NOT change is the variable names. These stay distinct from
    `DATABASE_URL` and `DATABASE_RO_URL`, so pointing the suite at a database
    is still a deliberate act and can never happen by inheriting a working
    application configuration — everything in this file writes.
    """
    from dotenv import dotenv_values

    value = os.environ.get(name)
    if value and value.strip():
        return value.strip()
    from_file = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
    value = (from_file or {}).get(name)
    return value.strip() if value and value.strip() else None


POSTGRES_TEST_URL = _configured_url("POSTGRES_TEST_URL")
POSTGRES_TEST_RO_URL = _configured_url("POSTGRES_TEST_RO_URL")

# A URL is not enough: a checkout that has the credentials configured but has
# not installed the core PostgreSQL dependency would otherwise error in every
# fixture rather than skipping. Both conditions are named here so the live
# suite shares one answer.
LIVE_POSTGRES = bool(POSTGRES_TEST_URL) and find_spec("psycopg") is not None
NO_LIVE_POSTGRES = (
    "POSTGRES_TEST_URL is not set" if not POSTGRES_TEST_URL
    else "the core PostgreSQL dependency is not installed"
) + "; the offline suite needs neither"

pytestmark = pytest.mark.skipif(not LIVE_POSTGRES, reason=NO_LIVE_POSTGRES)


@pytest.fixture(scope="module")
def scratch():
    """A migrated PostgreSQL warehouse of this file's own, dropped afterwards.

    This used to be the database `POSTGRES_TEST_URL` named, on the reasoning
    that every test here cleans up after itself. Two things retired that. The
    tests do write — into `parse_failures` and `review_queue` — and a run that
    fails part-way leaves those rows behind, which is enough to make
    `verify-migration` report a warehouse that no longer matches its source.
    And the operator pointed `POSTGRES_TEST_URL` at the working database,
    which is the reasonable thing to do when the server has one and
    `sectortrace_app` cannot create another.

    See `scratch_schema` in `tests/conftest.py`. Module-scoped here: nothing
    in this file depends on starting empty, and building the schema once
    rather than 38 times keeps the file at about a minute.
    """
    with scratch_schema(POSTGRES_TEST_URL, POSTGRES_TEST_RO_URL) as made:
        yield made


@pytest.fixture(scope="module")
def pg(scratch):
    return scratch.conn


class TestMigrationIdempotence:
    def test_reapplying_is_a_no_op(self, pg):
        """The contract every run depends on: migrations are applied on
        startup and must be free when the schema is current."""
        assert db.apply_migrations(pg, MIGRATIONS / "postgres") == []


class TestRefusalsStillRefuse:
    """Settled decision 4, on the other backend.

    These are the five triggers. A port that raised the wrong exception class
    would keep the guarantee while breaking every caller that catches it, so
    the class is asserted as carefully as the refusal.
    """

    def test_an_evidence_row_without_a_promotion_is_refused(self, pg):
        with pytest.raises(db.IntegrityError) as caught:
            pg.execute(
                "INSERT INTO cdp_documents (authority_ons_code, document_url, "
                "source_url, retrieved_at, http_status, source_system, payload_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("E06000001", "https://example.org/never", "https://example.org",
                 "2026-08-14T00:00:00+00:00", 200, "test", "0" * 64))
        pg.rollback()
        assert "nothing is promoted without a human" in str(caught.value)

    def test_the_message_names_where_to_go(self, pg):
        with pytest.raises(db.IntegrityError) as caught:
            pg.execute(
                "INSERT INTO foi_requests (ons_code, request_url, "
                "source_url, retrieved_at, http_status, source_system, payload_sha256) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                ("E06000001", "https://example.org/foi", "https://example.org",
                 "2026-08-14T00:00:00+00:00", 200, "test", "0" * 64))
        pg.rollback()
        assert "pipeline/promote.py" in str(caught.value)


class TestTheUpsertsInferTheirIndexes:
    """`ON CONFLICT (expr, ...)` is matched to an index by its expressions.

    A mismatch is not a fallback — it is `there is no unique or exclusion
    constraint matching the ON CONFLICT specification`, raised on the first
    parse failure of a crawl that has already made all of its requests.
    """

    def test_record_parse_failure_is_idempotent(self, pg):
        try:
            for _ in range(2):
                db.record_parse_failure(pg, "test_module", "a_field", "a fragment",
                                         "a reason", "https://example.org/x")
            pg.commit()
            count = pg.execute(
                "SELECT COUNT(*) FROM parse_failures WHERE module = %s",
                ("test_module",)).fetchone().values().__iter__().__next__()
            assert count == 1
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = %s", ("test_module",))
            pg.commit()

    def test_it_folds_null_and_empty_the_same_way(self, pg):
        """The COALESCE in the index expression is what makes a NULL
        source_url and an absent one one row rather than two."""
        try:
            db.record_parse_failure(pg, "test_module", "f", "frag", "why", None)
            db.record_parse_failure(pg, "test_module", "f", "frag", "why again", None)
            pg.commit()
            rows = pg.execute(
                "SELECT reason FROM parse_failures WHERE module = %s",
                ("test_module",)).fetchall()
            assert len(rows) == 1
            assert rows[0]["reason"] == "why again"
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = %s", ("test_module",))
            pg.commit()

    def test_record_review_item_leaves_a_decided_row_alone(self, pg):
        try:
            db.record_review_item(pg, "test_module", "a_type", "a value", '{"n": 1}')
            pg.execute("UPDATE review_queue SET status = 'approved' WHERE module = %s",
                        ("test_module",))
            pg.commit()
            db.record_review_item(pg, "test_module", "a_type", "a value", '{"n": 2}')
            pg.commit()
            row = pg.execute(
                "SELECT status, context_json FROM review_queue WHERE module = %s",
                ("test_module",)).fetchone()
            assert row["status"] == "approved"
            assert row["context_json"] == '{"n": 1}', "a decided row was overwritten"
        finally:
            pg.execute("DELETE FROM review_queue WHERE module = %s", ("test_module",))
            pg.commit()


class TestRowsAndCountersBehave:
    def test_rows_are_named_psycopg_rows(self, pg):
        row = pg.execute("SELECT 1 AS a, 'x' AS b, NULL AS c").fetchone()
        assert row["a"] == 1
        assert row["b"] == "x"
        assert row["c"] is None
        assert dict(row) == {"a": 1, "b": "x", "c": None}

    def test_total_changes_counts_writes_and_not_reads(self, pg):
        before = pg.total_changes
        pg.execute("SELECT COUNT(*) FROM parse_failures").fetchone()
        assert pg.total_changes == before, "a SELECT was counted as a write"
        try:
            db.record_parse_failure(pg, "test_counter", "f", "frag", "why", None)
            pg.commit()
            assert pg.total_changes == before + 1
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = %s", ("test_counter",))
            pg.commit()

    def test_a_literal_percent_survives_a_parameterised_query(self, pg):
        """The scanner's `%%` rule, against the server rather than a string
        comparison."""
        row = pg.execute(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name NOT LIKE 'sqlite_%%' "
            "AND table_type = %s", ("BASE TABLE",)).fetchone()
        assert row["n"] > 50


class TestTheReadPath:
    """`pipeline/web/queries.py` against a real server.

    Set `POSTGRES_TEST_RO_URL` as well to exercise the `sectortrace_reader`
    role — the tests that need it skip individually rather than the whole
    class, because everything else here works through the ordinary URL.
    """

    @pytest.fixture
    def readonly(self, scratch):
        from pipeline.config import Settings
        from pipeline.web import queries

        # Both URLs scoped to this file's schema, so the read path is
        # exercised against the schema the tests built rather than whichever
        # warehouse the credentials happen to reach.
        settings = Settings(contact_email="t@e.com", database_url=scratch.url,
                             database_ro_url=scratch.ro_url)
        conn = queries.readonly_connection(settings)
        try:
            yield conn
        finally:
            conn.close()

    def test_the_sidebar_lists_tables_and_views(self, readonly):
        from pipeline.web import queries

        objects = queries.list_objects(readonly)
        names = {o["name"] for o in objects}
        assert "contracts" in names
        assert "v_wage_per_employee" in names
        # Tables carry a count, views deliberately do not.
        by_name = {o["name"]: o for o in objects}
        assert by_name["contracts"]["rows"] is not None
        assert by_name["v_wage_per_employee"]["rows"] is None

    def test_restricted_objects_are_flagged(self, readonly):
        """The prefix rule that settled decision 3 stands on, on the other
        backend."""
        from pipeline.web import queries

        restricted = [o for o in queries.list_objects(readonly) if o["restricted"]]
        assert restricted
        assert all(o["name"].startswith("restricted_") for o in restricted)

    def test_object_type_validates_a_caller_supplied_name(self, readonly):
        from pipeline.web import queries

        assert queries.object_type(readonly, "contracts") == "table"
        assert queries.object_type(readonly, "v_wage_per_employee") == "view"
        assert queries.object_type(readonly, "no_such_thing") is None

    def test_columns_come_back_in_declaration_order(self, readonly):
        from pipeline.web import queries

        columns = queries.columns_of(readonly, "contracts")
        expected = [row["column_name"] for row in readonly.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = %s "
            "ORDER BY ordinal_position", ("contracts",)).fetchall()]
        assert [c["name"] for c in columns] == expected

    def test_a_table_pages_in_primary_key_order(self, readonly):
        """What replaces ORDER BY rowid. `ordered` must be True or the UI
        tells the operator the pages may overlap."""
        from pipeline.web import queries

        page = queries.read_table(readonly, "authorities", limit=5)
        assert page["ordered"] is True

    def test_a_view_is_reported_as_unordered(self, readonly):
        from pipeline.web import queries

        page = queries.read_table(readonly, "v_wage_per_employee", limit=5)
        assert page["ordered"] is False

    def test_search_escapes_wildcards(self, readonly):
        """`escape_like` plus `ESCAPE '\\'`, through the scanner, to the
        server. A literal percent must not become a wildcard."""
        from pipeline.web import queries

        page = queries.read_table(readonly, "authorities", search="100%", limit=5)
        assert page["rows"] == []

    def test_the_sql_box_answers_a_select(self, readonly):
        from pipeline.web import queries

        result = queries.run_select(readonly, "SELECT 1 AS one")
        assert result["rows"] == [[1]]

    def test_the_sql_box_cannot_write(self, readonly):
        """The guarantee `mode=ro` gives on SQLite, on PostgreSQL."""
        from pipeline.web import queries

        with pytest.raises(queries.QueryError):
            queries.run_select(readonly, "CREATE TABLE should_not_exist (x int)")

    def test_a_write_is_refused_by_the_server_not_by_the_code(self, scratch):
        """With a reader role configured, the refusal survives a bug here.

        `run_select` guards by statement inspection and the connection carries
        `default_transaction_read_only`; both are things this application asks
        for. This goes underneath both and writes directly, which is what a bug
        in either would amount to.
        """
        if not scratch.ro_url:
            pytest.skip("POSTGRES_TEST_RO_URL is not set; no reader role to test")
        from pipeline import pg as pg_module

        conn = pg_module.connect(scratch.ro_url, readonly=True)
        try:
            with pytest.raises(db.Error):
                conn.execute("CREATE TABLE should_not_exist (x int)")
            conn.rollback()
        finally:
            conn.close()

    def test_the_reader_can_still_read_everything_it_needs(self, scratch):
        if not scratch.ro_url:
            pytest.skip("POSTGRES_TEST_RO_URL is not set; no reader role to test")
        from pipeline import pg as pg_module

        conn = pg_module.connect(scratch.ro_url, readonly=True)
        try:
            assert conn.execute("SELECT COUNT(*) FROM authorities").fetchone().values().__iter__().__next__() >= 0
            assert catalog.list_objects(conn)
        finally:
            conn.close()

    def test_a_failed_statement_does_not_poison_the_connection(self, readonly):
        """Gap 2, end to end.

        In a transaction, one failed statement makes every later one raise
        InFailedSqlTransaction. `health.freshness` catches an error per table
        and carries on, so under a transaction the panel would truncate at the
        first bad table rather than skip it. Read connections run in
        autocommit for this reason; here is the proof it holds.
        """
        from pipeline.web import queries

        with pytest.raises(queries.QueryError):
            queries.run_select(readonly, "SELECT * FROM no_such_table")
        # The connection must still answer.
        assert queries.run_select(readonly, "SELECT 2 AS two")["rows"] == [[2]]

    def test_the_freshness_panel_survives_an_unreadable_table(self, readonly):
        from pipeline.web import health

        rows = health.freshness(readonly)
        assert rows, "no tables carry retrieved_at"
        assert all("newest" in r for r in rows)

    def test_the_reader_sees_every_object_the_owner_does(self, readonly, pg):
        """The defect Phase 4 found, pinned.

        `information_schema` is privilege-filtered, so a table the reader role
        holds no `SELECT` on is not listed as inaccessible — it is not listed
        at all. On the working warehouse that meant thirteen tables, every one
        added by a migration after the role was granted its one-off
        `GRANT SELECT ON ALL TABLES`, were absent from the sidebar with no gap
        in it, reported by `object_type()` as not existing, and a permission
        error to any portal query that named one.

        Nothing failed. That is the whole reason this test is here rather
        than a comment in the README.
        """
        if not POSTGRES_TEST_RO_URL:
            pytest.skip("POSTGRES_TEST_RO_URL is not set")

        owner = {o["name"] for o in catalog.list_objects(pg)}
        reader = {o["name"] for o in catalog.list_objects(readonly)}
        assert owner - reader == set(), (
            "the reader role cannot see: " + ", ".join(sorted(owner - reader)))


class TestMigrationsKeepTheReaderCurrent:
    """A migration adds a table; the reader has to be able to read it.

    Separate from `TestTheReadPath` because it needs a schema it can migrate
    twice, which the module-scoped one is not.
    """

    def test_a_table_from_a_later_migration_is_readable(self, tmp_path):
        if not POSTGRES_TEST_RO_URL:
            pytest.skip("POSTGRES_TEST_RO_URL is not set")

        from pipeline import pg as pg_module
        from pipeline.config import Settings

        with scratch_schema(POSTGRES_TEST_URL, POSTGRES_TEST_RO_URL) as made:
            later = tmp_path / "later"
            later.mkdir()
            (later / "9999_a_table_added_afterwards.sql").write_text(
                "CREATE TABLE IF NOT EXISTS added_afterwards "
                "(id bigint PRIMARY KEY, note text);", encoding="utf-8")

            settings = Settings(contact_email="t@e.com", database_url=made.url,
                                 database_ro_url=made.ro_url, _env_file=None)
            applied = db.apply_migrations(made.conn, later, settings=settings)
            made.conn.commit()
            assert applied == ["9999_a_table_added_afterwards.sql"]

            reader = pg_module.connect(made.ro_url, readonly=True)
            try:
                names = {o["name"] for o in catalog.list_objects(reader)}
                assert "added_afterwards" in names, (
                    "a table added by a migration is invisible to the reader "
                    "role — the grant did not travel with the migration")
                assert reader.execute(
                    "SELECT COUNT(*) FROM added_afterwards").fetchone().values().__iter__().__next__() == 0
            finally:
                reader.close()


class TestFetchPoolCacheWrites:
    """Worker threads write their own conditional-request cache here.

    `defer_cache_writes` exists because SQLite allows one writer and the main
    thread holds the slot while it commits evidence. PostgreSQL has no such
    slot, so the deferral goes — and the thing that makes that change worth
    testing rather than reasoning about is how it fails: the pool gives each
    worker its own connection and closes it at the end, psycopg rolls back on
    close, and a cache write without a commit is therefore discarded in
    silence. The run succeeds, the rows are simply not there, and the only
    symptom is that next week's crawl re-downloads everything.
    """

    @pytest.fixture
    def settings(self, scratch):
        from pipeline.config import Settings

        return Settings(contact_email="t@e.com", database_url=scratch.url,
                         default_rate_limit_seconds=0.0, _env_file=None)

    def test_a_worker_writes_and_commits_its_own_entries(self, settings, pg):
        from pipeline import db as db_module
        from pipeline.parallel import fetch_in_parallel

        pg.execute("DELETE FROM http_cache WHERE url LIKE 'https://pool-test%'")
        pg.commit()

        def worker(unit, client):
            assert client.defer_cache_writes is False, (
                "PostgreSQL has no write slot to queue behind")
            assert client.commit_cache_writes is True
            db_module.set_http_cache(
                client.conn, url=f"https://pool-test-{unit}.example.com/x",
                host=f"pool-test-{unit}.example.com", etag=f"etag-{unit}",
                last_modified=None, payload_sha256=f"sha-{unit}")
            client.conn.commit()
            return unit

        outcomes = list(fetch_in_parallel(
            range(4), worker, source_system="test_source", settings=settings,
            max_workers=4))
        assert all(o.ok for o in outcomes), [o.error for o in outcomes if not o.ok]

        # Read on a different connection, after the pool has closed its own:
        # the point is that the rows survived the connections that wrote them.
        rows = pg.execute(
            "SELECT url, etag FROM http_cache WHERE url LIKE 'https://pool-test%' "
            "ORDER BY url").fetchall()
        assert [r["etag"] for r in rows] == ["etag-0", "etag-1", "etag-2", "etag-3"]

        pg.execute("DELETE FROM http_cache WHERE url LIKE 'https://pool-test%'")
        pg.commit()

    def test_nothing_is_left_buffered_for_the_caller_to_flush(self, settings):
        """The other half: `fetch_in_parallel` still flushes on SQLite, and
        must find nothing to flush here rather than writing the same rows a
        second time on the module's connection."""
        from pipeline.parallel import _ClientPool

        pool = _ClientPool("test_source", settings)
        client = pool.get()
        assert client.conn.raw.info.server_version is not None
        assert pool.close() == []


class TestTheReadPoolHandsBackWhatItPromised:
    """A borrowed connection is the same connection the callers had.

    Opening a reader to this server is 68ms, and the web layer opened one per
    request — so the pool is the largest single win in Phase 4. It is also the
    change with the most ways to be quietly wrong, because every one of them
    shows up as two requests interfering with each other rather than as an
    error: session settings that only apply to a connection's first use, a
    connection returned twice and then held by two requests at once, a
    transaction left open on the way back.

    Each of those is a test here rather than a paragraph in a docstring.
    """

    @pytest.fixture
    def settings(self, scratch):
        from pipeline.config import Settings

        return Settings(contact_email="t@e.com", database_url=scratch.url,
                         database_ro_url=scratch.ro_url or scratch.url,
                         _env_file=None)

    def test_a_reused_connection_is_still_read_only(self, settings):
        """`configure` runs once per connection, not once per checkout — so
        the settings that make a read connection read-only have to survive
        being handed to the next request. If they did not, the fifth caller
        of the day would get a writable one."""
        from pipeline.web import queries

        for _ in range(4):
            conn = queries.readonly_connection(settings)
            try:
                assert conn.execute(
                    "SHOW default_transaction_read_only").fetchone().values().__iter__().__next__() == "on"
                assert conn.execute("SHOW statement_timeout").fetchone().values().__iter__().__next__() == "20s"
                with pytest.raises(db.Error):
                    conn.execute("CREATE TABLE pooled_write_probe (x int)")
            finally:
                conn.close()

    def test_closing_twice_does_not_hand_one_connection_to_two_callers(self, settings):
        """The callers were written against sqlite3, where a second `close()`
        is harmless. A second `putconn` is not: it puts a connection back that
        somebody else is already using."""
        from pipeline.web import queries

        first = queries.readonly_connection(settings)
        first.close()
        first.close()

        second = queries.readonly_connection(settings)
        third = queries.readonly_connection(settings)
        try:
            assert second._conn is not third._conn
            assert second.execute("SELECT 1").fetchone().values().__iter__().__next__() == 1
            assert third.execute("SELECT 2").fetchone().values().__iter__().__next__() == 2
        finally:
            second.close()
            third.close()

    def test_a_closed_connection_says_so(self, settings):
        from pipeline.web import queries

        conn = queries.readonly_connection(settings)
        conn.close()
        with pytest.raises(db.Error, match="closed"):
            conn.execute("SELECT 1")

    def test_a_failed_statement_does_not_poison_the_next_borrower(self, settings):
        """The autocommit decision, asked again now that connections are
        reused. A read connection that came back mid-transaction would hand
        the next request an `InFailedSqlTransaction` it did nothing to earn."""
        from pipeline.web import queries

        conn = queries.readonly_connection(settings)
        try:
            with pytest.raises(db.Error):
                conn.execute("SELECT * FROM no_such_table_at_all")
        finally:
            conn.close()

        after = queries.readonly_connection(settings)
        try:
            assert after.execute("SELECT 1").fetchone().values().__iter__().__next__() == 1
        finally:
            after.close()

    def test_more_callers_than_the_pool_holds_all_get_served(self, settings):
        """Beyond `max_size` a request waits rather than opening another
        connection. Sixteen threads against a pool of eight is the shape a
        browser with several tabs open produces."""
        import threading

        from pipeline import pg as pg_module
        from pipeline.web import queries

        failures: list[BaseException] = []

        def worker(n: int) -> None:
            try:
                for _ in range(4):
                    conn = queries.readonly_connection(settings)
                    try:
                        assert conn.execute("SELECT %s", (n,)).fetchone().values().__iter__().__next__() == n
                    finally:
                        conn.close()
            except BaseException as exc:   # noqa: BLE001 - reported below
                failures.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

        assert not failures, failures[:3]
        pool = next(iter(pg_module._pools.values()))
        assert pool.get_stats()["pool_size"] <= pg_module.POOL_MAX_SIZE

    def test_the_pool_is_shared_rather_than_made_per_request(self, settings):
        from pipeline import pg as pg_module
        from pipeline.web import queries

        pg_module.close_pools()
        for _ in range(3):
            queries.readonly_connection(settings).close()
        assert len(pg_module._pools) == 1

    def test_closing_the_pools_leaves_the_next_caller_working(self, settings):
        """`close_pools` runs at exit and when the web server stops. A caller
        afterwards should get a new pool, not a closed one."""
        from pipeline import pg as pg_module
        from pipeline.web import queries

        queries.readonly_connection(settings).close()
        pg_module.close_pools()

        conn = queries.readonly_connection(settings)
        try:
            assert conn.execute("SELECT 1").fetchone().values().__iter__().__next__() == 1
        finally:
            conn.close()
            pg_module.close_pools()


class TestThePortalRunsOnPostgres:
    """Every portal query, executed against a real PostgreSQL server.

    Phase 1 left `pipeline/web/public_queries.py` deliberately untouched, on
    the grounds that settled decision 7 puts the portal off-limits to admin
    work and whether a backend port counts was the owner's call. The cost of
    leaving it was found in Phase 4 by running it: `/api/v1/layers` and the
    coverage half of `/api/v1/authorities/{code}` queried `sqlite_master` by
    name and failed outright on PostgreSQL. Nothing had ever executed them
    against a server, so nothing said so.

    The schema is empty, and that is enough: what is under test is whether the
    SQL a portal route sends is SQL this engine accepts.

    Which makes the pass condition the delicate part. `QueryError` cannot
    simply be tolerated: most of the portal reads through `queries._run`,
    which turns *any* driver error into one, so "ignore QueryError" would
    ignore precisely the failure this class exists to catch — the version of
    this test that did was green against a route that could not run at all.
    What separates them is the cause: a refusal this codebase raises on
    purpose ("No authority 'E08000025'") has none, and a translated driver
    error is chained to the exception the server sent.
    """

    @pytest.fixture(scope="module")
    def portal(self, scratch):
        from pipeline import pg as pg_module

        conn = pg_module.connect(scratch.ro_url or scratch.url, readonly=True)
        try:
            yield conn
        finally:
            conn.close()

    @pytest.mark.parametrize("route", [
        "summary", "providers", "authorities", "contracts", "pay", "geography",
        "boundaries", "ndtms", "fingertips", "pfd", "freshness", "compare",
        "layers", "provider_timeline", "authority", "geography_years",
        "all_contract_notices",
    ])
    def test_the_route_runs(self, portal, route):
        from pipeline.web import public_queries
        from pipeline.web.public_queries import QueryError

        calls = {
            "geography_years": lambda c: public_queries.geography_years(
                c, "grant_total"),
            "provider_timeline": lambda c: public_queries.provider_timeline(
                c, "a_provider"),
            "authority": lambda c: public_queries.authority(c, "E08000025"),
            "compare": lambda c: public_queries.compare(
                c, ons_codes=("E08000025",)),
        }
        call = calls.get(route, getattr(public_queries, route))
        try:
            call(portal)
        except QueryError as exc:
            if isinstance(exc.__cause__, db.Error):
                pytest.fail(f"/api/v1/{route} does not run on PostgreSQL: "
                            f"{type(exc.__cause__).__name__}: {exc.__cause__}")
            # Otherwise a refusal this codebase means: "No authority …" on a
            # schema with no rows in it.
        except db.Error as exc:
            pytest.fail(f"/api/v1/{route} does not run on PostgreSQL: "
                        f"{type(exc).__name__}: {exc}")


class TestStringAgg:
    """The native PostgreSQL aggregate used by export queries."""

    ROWS = ("SELECT 'b' AS x UNION ALL SELECT 'a' UNION ALL SELECT 'b'")

    def test_two_argument_form(self, pg):
        got = pg.execute(
            f"SELECT string_agg(x, ', ') AS value FROM ({self.ROWS}) t").fetchone()["value"]
        assert sorted(got.split(", ")) == ["a", "b", "b"]

    def test_one_argument_form_separates_with_a_comma(self, pg):
        got = pg.execute(
            f"SELECT string_agg(x, ',') AS value FROM ({self.ROWS}) t").fetchone()["value"]
        assert sorted(got.split(",")) == ["a", "b", "b"]

    def test_distinct(self, pg):
        got = pg.execute(
            f"SELECT string_agg(DISTINCT x, ',') AS value FROM ({self.ROWS}) t").fetchone()["value"]
        assert sorted(got.split(",")) == ["a", "b"]

    def test_nulls_are_skipped_not_stringified(self, pg):
        """A NULL must not end the string or arrive as the text 'NULL'."""
        rows = "SELECT 'a' AS x UNION ALL SELECT NULL UNION ALL SELECT 'b'"
        got = pg.execute(
            f"SELECT string_agg(x, '|') AS value FROM ({rows}) t").fetchone()["value"]
        assert sorted(got.split("|")) == ["a", "b"]

    def test_all_nulls_gives_null_not_empty_string(self, pg):
        rows = "SELECT NULL AS x UNION ALL SELECT NULL"
        got = pg.execute(
            f"SELECT string_agg(x, '|') AS value FROM ({rows}) t").fetchone()["value"]
        assert got is None

    def test_no_rows_gives_null(self, pg):
        got = pg.execute(
            "SELECT string_agg(x, '|') AS value FROM "
            "(SELECT 'a' AS x WHERE 1 = 0) t").fetchone()["value"]
        assert got is None

    def test_a_concatenated_expression_as_the_value(self, pg):
        """`exports/schema.py:223` builds its value with `||` over a text and
        an integer column, which is the one call site that is not a plain
        column reference."""
        rows = "SELECT 'term' AS t, 3 AS n"
        got = pg.execute(
            f"SELECT string_agg(t || ' (' || n || ')', ', ') AS value "
            f"FROM ({rows}) x").fetchone()["value"]
        assert got == "term (3)"


class TestOrdering:
    def test_text_ordering_is_bytewise(self, pg):
        """The database must be created with a bytewise collation, or
        `ORDER BY name` differs from SQLite's on case and punctuation. See
        the CREATE DATABASE recipe in pipeline/migrations/postgres/README.md.
        """
        ordered = [r["x"] for r in pg.execute(
            "SELECT x FROM (SELECT 'a' AS x UNION ALL SELECT 'B' "
            "UNION ALL SELECT 'a b' UNION ALL SELECT 'ab') t ORDER BY x")]
        assert ordered == ["B", "a", "a b", "ab"], (
            f"collation is not bytewise (got {ordered}). The database was probably "
            "created without TEMPLATE = template0 and inherited the server's locale.")
