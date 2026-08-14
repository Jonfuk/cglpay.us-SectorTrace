"""The PostgreSQL backend, against a real server.

Skipped unless `POSTGRES_TEST_URL` is set. Deliberately **not** `DATABASE_URL`:
that one names a working warehouse, and a test suite that wrote to whatever a
developer happened to have configured would eventually write to a real one.
Two different variables means pointing the tests at a database is a separate,
deliberate act. Everything here writes, and cleans up after itself.

Either as environment variables or as lines in `.env` — both are read, so
the credentials can live in the same file as everything else rather than
having to be re-exported into each shell:

    POSTGRES_TEST_URL=postgresql://sectortrace_app:pw@host:5432/sectortrace
    POSTGRES_TEST_RO_URL=postgresql://sectortrace_reader:pw@host:5432/sectortrace

    uv run python -m pytest -m postgres -q

What this covers that `test_migration_equivalence.py` cannot: that one diffs
the two trees as *text*, offline, which catches a file added to one tree and
not the other. This one applies both and compares what the two servers
actually built — the difference between a migration that parses and a
migration that produces the schema it was supposed to.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

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

# Two gates, and they answer different questions. The marker keeps these out
# of `uv run python -m pytest`, which is documented as offline: a developer who
# has configured a server should not have the default suite quietly start
# depending on it being up. The skipif is for when the marker has been asked
# for and there is still no URL to use.
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not POSTGRES_TEST_URL,
        reason="POSTGRES_TEST_URL is not set; set it in .env or the environment"),
]


@pytest.fixture(scope="module")
def pg():
    """A migrated PostgreSQL warehouse. Applying is idempotent, so this is
    safe to run against a database that already has the schema."""
    from pipeline import pg as pg_module

    conn = pg_module.connect(POSTGRES_TEST_URL, application_name="sectortrace-tests")
    try:
        db.apply_migrations(conn, MIGRATIONS / "postgres")
        conn.commit()
        yield conn
    finally:
        conn.close()


@pytest.fixture(scope="module")
def lite(tmp_path_factory):
    """The same schema on SQLite, built fresh, for comparison."""
    path = tmp_path_factory.mktemp("sqlite") / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        db.apply_migrations(conn, MIGRATIONS)
        conn.commit()
        yield conn
    finally:
        conn.close()


class TestTheSchemaTheyActuallyBuilt:
    def test_the_same_tables_exist(self, pg, lite):
        pg_tables = {o["name"] for o in catalog.list_objects(pg) if o["type"] == "table"}
        lite_tables = {o["name"] for o in catalog.list_objects(lite) if o["type"] == "table"}
        # SQLite records applied migrations in a table it also creates.
        assert pg_tables == lite_tables, (
            f"only PostgreSQL: {sorted(pg_tables - lite_tables)}; "
            f"only SQLite: {sorted(lite_tables - pg_tables)}")

    def test_the_same_views_exist(self, pg, lite):
        pg_views = {o["name"] for o in catalog.list_objects(pg) if o["type"] == "view"}
        lite_views = {o["name"] for o in catalog.list_objects(lite) if o["type"] == "view"}
        assert pg_views == lite_views

    def test_the_same_columns_in_the_same_order(self, pg, lite):
        differences = {}
        for name in sorted({o["name"] for o in catalog.list_objects(lite)}):
            pg_columns = [c["name"] for c in catalog.columns_of(pg, name)]
            lite_columns = [c["name"] for c in catalog.columns_of(lite, name)]
            if pg_columns != lite_columns:
                differences[name] = (lite_columns, pg_columns)
        assert not differences, f"column mismatch: {differences}"

    def test_nullability_agrees_away_from_primary_keys(self, pg, lite):
        """A column NOT NULL on one side and nullable on the other is a
        constraint that exists on one backend only.

        Primary key columns are excluded and checked separately below,
        because there the two engines disagree by design — see
        `test_postgres_makes_primary_keys_not_null`.
        """
        differences = {}
        for name in sorted({o["name"] for o in catalog.list_objects(lite)
                             if o["type"] == "table"}):
            key = set(catalog.primary_key(lite, name)) | set(catalog.primary_key(pg, name))
            pg_nn = {c["name"] for c in catalog.columns_of(pg, name)
                      if c["notnull"]} - key
            lite_nn = {c["name"] for c in catalog.columns_of(lite, name)
                        if c["notnull"]} - key
            if pg_nn != lite_nn:
                differences[name] = sorted(lite_nn ^ pg_nn)
        assert not differences, f"nullability differs: {differences}"

    def test_postgres_makes_primary_keys_not_null(self, pg, lite):
        """The one nullability difference, asserted rather than tolerated.

        SQLite does not enforce NOT NULL on a PRIMARY KEY column unless it is
        declared so — a documented legacy quirk kept for backwards
        compatibility, and it is not cosmetic: SQLite will accept an actual
        NULL into a TEXT PRIMARY KEY. Only `INTEGER PRIMARY KEY`, the rowid
        alias, is exempt. PostgreSQL makes every key column NOT NULL.

        PostgreSQL is stricter, so nothing legal there is illegal here. It
        runs the other way that matters: a row already in the SQLite
        warehouse with a NULL in its key cannot be loaded into PostgreSQL at
        all. Measured on the live warehouse the day this was written, no such
        row exists — but that is a property of the data, not of the schema,
        so the Phase 2 loader has to check rather than assume. This test
        pins the reason that check needs to exist.
        """
        checked = 0
        for name in sorted({o["name"] for o in catalog.list_objects(lite)
                             if o["type"] == "table"}):
            key = catalog.primary_key(pg, name)
            if not key:
                continue
            nullable = {c["name"] for c in catalog.columns_of(pg, name)
                         if not c["notnull"]}
            assert not (set(key) & nullable), (
                f"{name}: PostgreSQL left a key column nullable: "
                f"{sorted(set(key) & nullable)}")
            checked += 1
        assert checked > 50, "the primary key inventory looks wrong"

    def test_no_row_in_the_source_warehouse_has_a_null_key(self, lite):
        """The Phase 2 pre-flight the test above argues for.

        Runs against the freshly built empty schema here, so it passes
        trivially; it exists so the loader has a written contract to
        implement against the real warehouse.
        """
        for name in sorted({o["name"] for o in catalog.list_objects(lite)
                             if o["type"] == "table"}):
            key = catalog.primary_key(lite, name)
            if not key:
                continue
            predicate = " OR ".join(f'"{column}" IS NULL' for column in key)
            from pipeline.web import queries
            count = lite.execute(
                f'SELECT COUNT(*) FROM {queries._quote(name)} WHERE {predicate}'
            ).fetchone()[0]
            assert count == 0, f"{name}: {count} rows have a NULL in {key}"

    def test_primary_keys_agree(self, pg, lite):
        differences = {}
        for name in sorted({o["name"] for o in catalog.list_objects(lite)
                             if o["type"] == "table"}):
            if catalog.primary_key(pg, name) != catalog.primary_key(lite, name):
                differences[name] = (catalog.primary_key(lite, name),
                                      catalog.primary_key(pg, name))
        assert not differences, f"primary keys differ: {differences}"

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
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("E06000001", "https://example.org/never", "https://example.org",
                 "2026-08-14T00:00:00+00:00", 200, "test", "0" * 64))
        pg.rollback()
        assert "nothing is promoted without a human" in str(caught.value)

    def test_the_message_names_where_to_go(self, pg):
        with pytest.raises(db.IntegrityError) as caught:
            pg.execute(
                "INSERT INTO foi_requests (ons_code, request_url, "
                "source_url, retrieved_at, http_status, source_system, payload_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
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
                "SELECT COUNT(*) FROM parse_failures WHERE module = ?",
                ("test_module",)).fetchone()[0]
            assert count == 1
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = ?", ("test_module",))
            pg.commit()

    def test_it_folds_null_and_empty_the_same_way(self, pg):
        """The COALESCE in the index expression is what makes a NULL
        source_url and an absent one one row rather than two."""
        try:
            db.record_parse_failure(pg, "test_module", "f", "frag", "why", None)
            db.record_parse_failure(pg, "test_module", "f", "frag", "why again", None)
            pg.commit()
            rows = pg.execute(
                "SELECT reason FROM parse_failures WHERE module = ?",
                ("test_module",)).fetchall()
            assert len(rows) == 1
            assert rows[0]["reason"] == "why again"
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = ?", ("test_module",))
            pg.commit()

    def test_record_review_item_leaves_a_decided_row_alone(self, pg):
        try:
            db.record_review_item(pg, "test_module", "a_type", "a value", '{"n": 1}')
            pg.execute("UPDATE review_queue SET status = 'approved' WHERE module = ?",
                        ("test_module",))
            pg.commit()
            db.record_review_item(pg, "test_module", "a_type", "a value", '{"n": 2}')
            pg.commit()
            row = pg.execute(
                "SELECT status, context_json FROM review_queue WHERE module = ?",
                ("test_module",)).fetchone()
            assert row["status"] == "approved"
            assert row["context_json"] == '{"n": 1}', "a decided row was overwritten"
        finally:
            pg.execute("DELETE FROM review_queue WHERE module = ?", ("test_module",))
            pg.commit()


class TestRowsAndCountersBehave:
    def test_rows_answer_to_name_and_position(self, pg):
        row = pg.execute("SELECT 1 AS a, 'x' AS b, NULL AS c").fetchone()
        assert row["a"] == 1 and row[0] == 1
        assert row["b"] == "x" and row[1] == "x"
        assert row["c"] is None
        assert dict(row) == {"a": 1, "b": "x", "c": None}
        assert tuple(row) == (1, "x", None)

    def test_total_changes_counts_writes_and_not_reads(self, pg):
        before = pg.total_changes
        pg.execute("SELECT COUNT(*) FROM parse_failures").fetchone()
        assert pg.total_changes == before, "a SELECT was counted as a write"
        try:
            db.record_parse_failure(pg, "test_counter", "f", "frag", "why", None)
            pg.commit()
            assert pg.total_changes == before + 1
        finally:
            pg.execute("DELETE FROM parse_failures WHERE module = ?", ("test_counter",))
            pg.commit()

    def test_a_literal_percent_survives_a_parameterised_query(self, pg):
        """The scanner's `%%` rule, against the server rather than a string
        comparison."""
        row = pg.execute(
            "SELECT COUNT(*) AS n FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name NOT LIKE 'sqlite_%' "
            "AND table_type = ?", ("BASE TABLE",)).fetchone()
        assert row["n"] > 50


class TestTheReadPath:
    """`pipeline/web/queries.py` against a real server.

    Set `POSTGRES_TEST_RO_URL` as well to exercise the `sectortrace_reader`
    role — the tests that need it skip individually rather than the whole
    class, because everything else here works through the ordinary URL.
    """

    @pytest.fixture
    def readonly(self):
        from pipeline.config import Settings
        from pipeline.web import queries

        settings = Settings(contact_email="t@e.com", database_url=POSTGRES_TEST_URL,
                             database_ro_url=POSTGRES_TEST_RO_URL)
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

    def test_columns_come_back_in_declaration_order(self, readonly, lite):
        from pipeline.web import queries

        assert ([c["name"] for c in queries.columns_of(readonly, "contracts")]
                == [c["name"] for c in queries.columns_of(lite, "contracts")])

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

    def test_a_write_is_refused_by_the_server_not_by_the_code(self):
        """With a reader role configured, the refusal survives a bug here.

        `run_select` guards by statement inspection and the connection carries
        `default_transaction_read_only`; both are things this application asks
        for. This goes underneath both and writes directly, which is what a bug
        in either would amount to.
        """
        ro_url = POSTGRES_TEST_RO_URL
        if not ro_url:
            pytest.skip("POSTGRES_TEST_RO_URL is not set; no reader role to test")
        from pipeline import pg as pg_module

        conn = pg_module.connect(ro_url, readonly=True)
        try:
            with pytest.raises(db.Error):
                conn.execute("CREATE TABLE should_not_exist (x int)")
            conn.rollback()
        finally:
            conn.close()

    def test_the_reader_can_still_read_everything_it_needs(self):
        ro_url = POSTGRES_TEST_RO_URL
        if not ro_url:
            pytest.skip("POSTGRES_TEST_RO_URL is not set; no reader role to test")
        from pipeline import pg as pg_module

        conn = pg_module.connect(ro_url, readonly=True)
        try:
            assert conn.execute("SELECT COUNT(*) FROM authorities").fetchone()[0] >= 0
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


class TestGroupConcatMatchesSqlite:
    """The compatibility aggregate from 0034.

    Nine export queries call `GROUP_CONCAT` from application SQL and stay one
    query each because PostgreSQL is taught the name. Every assertion here
    runs against both engines, so SQLite is the specification rather than my
    recollection of it.
    """

    ROWS = ("SELECT 'b' AS x UNION ALL SELECT 'a' UNION ALL SELECT 'b'")

    def test_two_argument_form(self, pg, lite):
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(x, ', ') FROM ({self.ROWS}) t").fetchone()[0]
            assert sorted(got.split(", ")) == ["a", "b", "b"], db.backend_of(conn)

    def test_one_argument_form_separates_with_a_comma(self, pg, lite):
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(x) FROM ({self.ROWS}) t").fetchone()[0]
            assert sorted(got.split(",")) == ["a", "b", "b"], db.backend_of(conn)

    def test_distinct(self, pg, lite):
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(DISTINCT x) FROM ({self.ROWS}) t").fetchone()[0]
            assert sorted(got.split(",")) == ["a", "b"], db.backend_of(conn)

    def test_nulls_are_skipped_not_stringified(self, pg, lite):
        """A NULL must not end the string or arrive as the text 'NULL'."""
        rows = "SELECT 'a' AS x UNION ALL SELECT NULL UNION ALL SELECT 'b'"
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(x, '|') FROM ({rows}) t").fetchone()[0]
            assert sorted(got.split("|")) == ["a", "b"], db.backend_of(conn)

    def test_all_nulls_gives_null_not_empty_string(self, pg, lite):
        rows = "SELECT NULL AS x UNION ALL SELECT NULL"
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(x, '|') FROM ({rows}) t").fetchone()[0]
            assert got is None, f"{db.backend_of(conn)}: {got!r}"

    def test_no_rows_gives_null(self, pg, lite):
        for conn in (pg, lite):
            got = conn.execute(
                "SELECT GROUP_CONCAT(x, '|') FROM "
                "(SELECT 'a' AS x WHERE 1 = 0) t").fetchone()[0]
            assert got is None, f"{db.backend_of(conn)}: {got!r}"

    def test_a_concatenated_expression_as_the_value(self, pg, lite):
        """`exports/schema.py:223` builds its value with `||` over a text and
        an integer column, which is the one call site that is not a plain
        column reference."""
        rows = "SELECT 'term' AS t, 3 AS n"
        for conn in (pg, lite):
            got = conn.execute(
                f"SELECT GROUP_CONCAT(t || ' (' || n || ')', ', ') "
                f"FROM ({rows}) x").fetchone()[0]
            assert got == "term (3)", db.backend_of(conn)


class TestOrderingMatchesSqlite:
    def test_nulls_sort_to_the_same_end(self, pg, lite):
        """SQLite puts NULLs first ascending, PostgreSQL last. The export
        queries now say which they want; this proves the clause does what the
        comment claims on both engines."""
        for conn in (pg, lite):
            ascending = [r[0] for r in conn.execute(
                "SELECT x FROM (SELECT 'b' AS x UNION ALL SELECT NULL "
                "UNION ALL SELECT 'a') t ORDER BY x NULLS FIRST")]
            assert ascending == [None, "a", "b"], f"{db.backend_of(conn)}: {ascending}"

            descending = [r[0] for r in conn.execute(
                "SELECT x FROM (SELECT 'b' AS x UNION ALL SELECT NULL "
                "UNION ALL SELECT 'a') t ORDER BY x DESC NULLS LAST")]
            assert descending == ["b", "a", None], f"{db.backend_of(conn)}: {descending}"

    def test_text_ordering_is_bytewise(self, pg):
        """The database must be created with a bytewise collation, or
        `ORDER BY name` differs from SQLite's on case and punctuation. See
        the CREATE DATABASE recipe in pipeline/migrations/postgres/README.md.
        """
        ordered = [r[0] for r in pg.execute(
            "SELECT x FROM (SELECT 'a' AS x UNION ALL SELECT 'B' "
            "UNION ALL SELECT 'a b' UNION ALL SELECT 'ab') t ORDER BY x")]
        assert ordered == ["B", "a", "a b", "ab"], (
            f"collation is not bytewise (got {ordered}). The database was probably "
            "created without TEMPLATE = template0 and inherited the server's locale.")
