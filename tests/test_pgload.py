"""The Phase 2 loader, as far as it can be tested without a server.

Which is further than it looks. The load order, the preflight checks, the
value rules and the state file are all decided against the *source*, and the
source is SQLite — so everything here runs offline, on a real migrated
warehouse built from the real migration tree.

What genuinely needs PostgreSQL — `COPY`, the identity sequences, the triggers
firing during a load — is in `tests/test_pg_migration_live.py` behind
`POSTGRES_TEST_URL`.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from pipeline import catalog, pgload


@pytest.fixture
def source(conn, settings):
    """The migrated warehouse, reopened read-only, as the loader opens it."""
    conn.commit()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    reader = pgload.open_source(settings.database_path)
    yield reader
    reader.close()


class TestTheOrderTablesAreLoadedIn:
    def test_every_table_appears_once(self, source):
        order = pgload.load_order(source)
        assert len(order) == len(set(order))
        expected = {t for t in catalog.table_names(source)
                     if t not in pgload.SOURCE_ONLY_TABLES}
        assert set(order) == expected

    def test_the_migration_ledger_is_not_loaded(self, source):
        """The target records which files were applied *to it*.

        Copying the source's ledger across would leave a database claiming to
        have run migrations it had not — and the two are legitimately
        different, because the SQLite warehouse can be a file behind the tree
        while the PostgreSQL one is current.
        """
        assert "schema_migrations" not in pgload.load_order(source)

    def test_parents_come_before_children(self, source):
        order = pgload.load_order(source)
        position = {table: index for index, table in enumerate(order)}
        for child, parent in catalog.foreign_keys(source):
            if child in position and parent in position:
                assert position[parent] < position[child], (
                    f"{child} is loaded before {parent}, which it references")

    def test_the_decision_tables_come_before_what_they_authorise(self, source):
        """The trigger edges, which no foreign key expresses.

        `evidence_promotions` identifies its target by a `<authority>|<url>`
        string and a census verification matches on four columns of text, so
        neither dependency is a column reference — and both are enforced on
        every insert. Loading in the wrong order is refused by the database
        part-way through, which is the expensive way to find out.
        """
        position = {t: i for i, t in enumerate(pgload.load_order(source))}
        for child, parents in pgload.TRIGGER_EDGES.items():
            for parent in parents:
                assert position[parent] < position[child], (
                    f"{child} would be loaded before {parent}, and its "
                    "trigger would refuse every row")

    def test_the_order_is_stable(self, source):
        assert pgload.load_order(source) == pgload.load_order(source)

    def test_a_cycle_is_refused_rather_than_broken(self, monkeypatch, source):
        monkeypatch.setattr(pgload, "TRIGGER_EDGES",
                             {"authorities": ("contracts",),
                              "contracts": ("authorities",)})
        with pytest.raises(pgload.LoadError, match="cycle"):
            pgload.load_order(source)


class TestWhatMayCrossAndWhatMayNot:
    def test_text_goes_across_unchanged(self):
        assert pgload._coerce("a value", "text", "t.c") == "a value"

    def test_null_stays_null(self):
        assert pgload._coerce(None, "int8", "t.c") is None

    def test_an_integer_in_a_double_column_is_widened_exactly(self):
        assert pgload._coerce(3, "float8", "t.c") == 3.0
        assert isinstance(pgload._coerce(3, "float8", "t.c"), float)

    def test_an_integer_too_large_to_be_a_double_is_refused(self):
        """Widening it would round it, and a rounded figure that reads as
        exact is the failure this project is built against."""
        with pytest.raises(pgload.LoadError, match="exactly"):
            pgload._coerce(2 ** 53 + 1, "float8", "t.c")

    def test_text_in_an_integer_column_is_refused_not_cast(self):
        """SQLite's type affinity is a suggestion and PostgreSQL's is not.
        Nothing here casts: the source has to be corrected."""
        with pytest.raises(pgload.LoadError, match="Nothing here casts"):
            pgload._coerce("12", "int8", "t.c")

    def test_a_number_in_a_text_column_is_refused(self):
        with pytest.raises(pgload.LoadError, match="in a text column"):
            pgload._coerce(12, "text", "t.c")

    def test_a_nul_byte_in_text_is_refused_rather_than_stripped(self):
        """PostgreSQL cannot store one in any encoding. Much of this schema's
        text is extracted PDF prose, so stripping would edit the evidence."""
        with pytest.raises(pgload.LoadError, match="NUL byte"):
            pgload._coerce("a\x00b", "text", "restricted_pfd_report_text.body")

    def test_an_unknown_column_type_stops_the_migration(self):
        with pytest.raises(pgload.LoadError, match="no rule for loading"):
            pgload._coerce("2026-01-01", "timestamptz", "t.c")

    def test_the_message_names_the_column(self):
        with pytest.raises(pgload.LoadError, match=r"contracts\.value_core"):
            pgload._coerce("nope", "float8", "contracts.value_core")


class TestPreflight:
    def test_a_clean_warehouse_has_nothing_to_report(self, source):
        """Everything preflight checks about the source alone, on the schema
        the real migrations build."""
        assert pgload._storage_type_problems(source) == []
        assert pgload.null_key_problems(source) == []

    def test_a_value_stored_as_the_wrong_type_is_found(self, conn, settings):
        # `dry_run` is INTEGER, and SQLite's INTEGER affinity keeps a string
        # it cannot convert losslessly rather than refusing it. PostgreSQL
        # will not take the row at all.
        conn.execute(
            "INSERT INTO job_runs (id, kind, label, args_json, state, "
            "dry_run, started_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1, "run", "m01", "{}", "finished", "no", "2026-01-01"))
        conn.commit()
        reader = pgload.open_source(settings.database_path)
        try:
            problems = pgload._storage_type_problems(reader)
        finally:
            reader.close()
        assert any("job_runs.dry_run" in p for p in problems), problems

    def test_a_null_primary_key_is_found(self, conn, settings):
        """SQLite permits a NULL in a TEXT PRIMARY KEY; PostgreSQL cannot hold
        the row at all. `tests/test_postgres_live.py` argues this check has to
        exist — this is it, doing its job."""
        conn.execute(
            "INSERT INTO module_cursors (module, cursor_value, updated_at) "
            "VALUES (NULL, 'x', '2026-01-01')")
        conn.commit()
        reader = pgload.open_source(settings.database_path)
        try:
            problems = pgload.null_key_problems(reader)
        finally:
            reader.close()
        assert any("module_cursors" in p for p in problems), problems

    def test_a_target_that_is_not_postgresql_is_refused_immediately(
            self, source, conn):
        problems = pgload.preflight(source, conn)
        assert problems == ["the target is not a PostgreSQL connection."]

    def test_the_source_is_opened_read_only(self, source):
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            source.execute("DELETE FROM authorities")

    def test_a_missing_warehouse_is_named(self, tmp_path):
        with pytest.raises(pgload.LoadError, match="no SQLite warehouse"):
            pgload.open_source(tmp_path / "nothing.db")


class TestTheStateFile:
    def test_it_sits_beside_the_warehouse_it_reads(self, settings):
        """A state file next to one warehouse and describing another is how a
        resume loads half of the wrong database."""
        path = pgload.state_path_for(settings)
        assert path.parent == settings.database_path.parent

    def test_an_unreadable_state_file_is_a_refusal_not_a_fresh_start(
            self, tmp_path):
        path = tmp_path / "pg-migration-state.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(pgload.LoadError, match="not readable"):
            pgload._load_state(path)

    def test_a_written_state_reads_back(self, tmp_path):
        path = tmp_path / "state.json"
        pgload._write_state(path, {"version": 1, "tables": {"a": {"rows": 2}}})
        assert pgload._load_state(path)["tables"]["a"]["rows"] == 2
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == 1


class TestTheGuaranteesAreDescribedTheSameWayTwice:
    def test_every_trigger_edge_names_a_real_table(self, source):
        tables = set(catalog.table_names(source))
        for child, parents in pgload.TRIGGER_EDGES.items():
            assert child in tables, child
            for parent in parents:
                assert parent in tables, parent

    def test_the_trigger_edges_cover_every_trigger_in_the_schema(self, source):
        """A trigger added later without an edge here is a load that fails
        part-way through, so the two are pinned to each other.

        Read from the SQLite tree because that is the dialect this test can
        open; the PostgreSQL tree is diffed against it by
        `tests/test_migration_equivalence.py`.
        """
        guarded = {row[0] for row in source.execute(
            "SELECT DISTINCT tbl_name FROM sqlite_master WHERE type = 'trigger'")}
        assert guarded == set(pgload.TRIGGER_EDGES), (
            "a table is guarded by a trigger with no load-order edge: "
            f"{sorted(guarded - set(pgload.TRIGGER_EDGES))}")
