"""The Phase 2 loader against a real PostgreSQL server.

Skipped unless `POSTGRES_TEST_URL` is set, and reading it from the same place
`tests/test_postgres_live.py` does — environment first, then `.env` — because
these are the same two credentials and having them read two different ways is
how one of them ends up silently ignored.

**Everything here truncates the target's tables.** Point `POSTGRES_TEST_URL`
at a database kept for the tests, never at a warehouse holding anything. The
source is a small SQLite warehouse built fresh in `tmp_path` from the real
migration tree, so nothing touches `data/warehouse.db` either.

    uv run python -m pytest tests/test_pg_migration_live.py -q

What is here that the offline suites cannot reach: `COPY` itself, the identity
sequences, and — the reason the load order exists — the five triggers firing
during a load of the tables they guard.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

# The same two variables, read the same way. `tests/` is on `sys.path` under
# pytest's default import mode, so this is the sibling module.
from test_postgres_live import POSTGRES_TEST_URL, _configured_url

from pipeline import catalog, db, pgload, pgverify
from pipeline.config import Settings

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_URL,
    reason="POSTGRES_TEST_URL is not set; the offline suite does not need a server")

PROVENANCE = ("https://example.org/source", "2026-08-15T00:00:00+00:00", 200,
               "test", "0" * 64)


def _seed(conn: sqlite3.Connection) -> None:
    """A small warehouse with one of each thing that can go wrong.

    Deliberately not a subset of the real one: what is wanted is a row that
    exercises each hazard — a float that is not representable in decimal, text
    outside ASCII, a NULL beside a NOT NULL, an id that a sequence has to be
    moved past, and evidence that only exists because a person promoted it.
    """
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("E06000001", "Hartlepool", "unitary", "North East", "2020-01-01",
         "2020", "2026", *PROVENANCE))
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        # NULL region, and a name that is not ASCII — the two things a
        # round-trip through a different encoding or a different NULL
        # convention would change.
        ("E06000002", "Kingston upon Hull — City of", "unitary", None,
         "2020-01-01", "2020", "2026", *PROVENANCE))

    for year, amount in (("2025-26", 0.1 + 0.2), ("2026-27", 1e308)):
        conn.execute(
            "INSERT INTO public_health_grants (ons_code, financial_year, "
            "grant_type, allocation_status, unit, amount, "
            "source_column_header, source_document, source_url, retrieved_at, "
            "http_status, source_system, payload_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("E06000001", year, "total", "confirmed", "gbp", amount,
             "Total", "https://example.org/grants.ods", *PROVENANCE))

    # Evidence, and the promotion without which no trigger will accept it.
    conn.execute(
        "INSERT INTO evidence_promotions (id, candidate_table, candidate_url, "
        "target_table, target_key, promoted_by, promoted_at, "
        "candidate_context_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (7, "cdp_document_candidates", "https://example.org/cdp.pdf",
         "cdp_documents", "E06000001|https://example.org/cdp.pdf",
         "a person", "2026-08-15T00:00:00+00:00", "{}"))
    conn.execute(
        "INSERT INTO cdp_documents (authority_ons_code, document_url, "
        "document_type, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("E06000001", "https://example.org/cdp.pdf", "cdp_strategy",
         *PROVENANCE))

    # A verified census figure, and the decision behind it.
    conn.execute(
        "INSERT INTO census_verifications (id, census_year, metric, "
        "workforce_segment, raw_text, decision, decided_by, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (3, 2024, "wte_total", "delivery", "Total WTE: 1,234",
         "verified", "a person", "2026-08-15T00:00:00+00:00"))
    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, "
        "workforce_segment, value, unit, raw_text, verified, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (2024, "wte_total", "delivery", 1234.0, "wte", "Total WTE: 1,234", 1,
         *PROVENANCE))

    # An identity column with a gap in it, so a sequence left behind would
    # collide rather than merely look wrong.
    for identifier in (1, 2, 41):
        conn.execute(
            "INSERT INTO review_queue (id, module, item_type, raw_value, "
            "status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (identifier, "m01", "unmatched_buyer", f"Buyer {identifier}",
             "2026-08-15T00:00:00+00:00"))
    conn.commit()


@pytest.fixture
def source(settings) -> sqlite3.Connection:
    """A seeded SQLite warehouse, then reopened read-only as the loader does."""
    path = settings.database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = sqlite3.connect(path)
    writer.row_factory = sqlite3.Row
    try:
        db.apply_migrations(writer, MIGRATIONS)
        writer.commit()
        _seed(writer)
        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        writer.close()

    reader = pgload.open_source(path)
    yield reader
    reader.close()


@pytest.fixture
def target():
    """The PostgreSQL warehouse, migrated and emptied, and emptied again after.

    Emptied at both ends deliberately: at the start because a previous run
    that failed part-way leaves rows, and at the end because the next suite to
    run against this database should find it as it found it.
    """
    from pipeline import pg as pg_module

    conn = pg_module.connect(POSTGRES_TEST_URL,
                              application_name="sectortrace-migration-tests")
    try:
        db.apply_migrations(conn, MIGRATIONS / "postgres")
        conn.commit()
        tables = pgload.load_order(conn)
        pgload.truncate_all(conn, tables)
        yield conn
        pgload.truncate_all(conn, tables)
    finally:
        conn.close()


@pytest.fixture
def pg_settings(settings) -> Settings:
    """The suite's settings with the test server's URL added.

    Derived from the shared fixture rather than built fresh, so every writable
    path still points into `tmp_path`. A `Settings()` constructed here would
    take the repository's defaults for `backup_dir`, `logs_dir` and the rest,
    and this suite has deposited its output next to the operator's twice
    already — see `tests/conftest.py`.
    """
    return settings.model_copy(update={"database_url": POSTGRES_TEST_URL})


class TestALoadAndItsProof:
    def test_the_whole_warehouse_crosses_and_verifies(self, source, target,
                                                        pg_settings):
        summary = pgload.migrate(source, target, settings=pg_settings)
        assert summary["rows"] == sum(
            source.execute(f"SELECT COUNT(*) FROM {catalog.quote(t)}").fetchone()[0]
            for t in pgload.load_order(target))

        report = pgverify.verify(source, target)
        assert report["ok"], report["problems"]
        assert report["checks"]["guarantees"] is True
        assert report["checks"]["sequences"] is True

    def test_text_outside_ascii_survives(self, source, target, pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        name = target.execute(
            "SELECT name FROM authorities WHERE ons_code = ?",
            ("E06000002",)).fetchone()[0]
        assert name == "Kingston upon Hull — City of"

    def test_a_float_arrives_bit_for_bit(self, source, target, pg_settings):
        """`0.1 + 0.2` is the value that is not the value it prints as. It
        crosses as a double or the figure has changed."""
        pgload.migrate(source, target, settings=pg_settings)
        rows = {r["financial_year"]: r["amount"] for r in target.execute(
            "SELECT financial_year, amount FROM public_health_grants")}
        assert rows["2025-26"] == 0.1 + 0.2
        assert rows["2025-26"].hex() == (0.1 + 0.2).hex()
        assert rows["2026-27"] == 1e308

    def test_a_null_stays_a_null_and_does_not_become_an_empty_string(
            self, source, target, pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        assert target.execute(
            "SELECT region FROM authorities WHERE ons_code = ?",
            ("E06000002",)).fetchone()[0] is None

    def test_the_migration_ledger_is_the_targets_own(self, source, target,
                                                      pg_settings):
        """The source is at the SQLite tree's files, the target at the
        PostgreSQL tree's. Copying one over the other would leave a database
        claiming it had run migrations it had not."""
        pgload.migrate(source, target, settings=pg_settings)
        applied = db.applied_migrations(target)
        assert "0034_group_concat_compat.sql" in applied
        assert target.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == len(
                sorted((MIGRATIONS / "postgres").glob("*.sql")))


class TestTheGuaranteesSurviveTheLoad:
    def test_evidence_arrives_because_its_promotion_arrived_first(
            self, source, target, pg_settings):
        """No trigger was disabled to load this row.

        `COPY` fires `BEFORE INSERT` triggers exactly as `INSERT` does, so
        the row is in the target only because `evidence_promotions` was loaded
        before `cdp_documents` and the trigger's own question answered yes.
        """
        pgload.migrate(source, target, settings=pg_settings)
        assert target.execute(
            "SELECT COUNT(*) FROM cdp_documents").fetchone()[0] == 1
        assert pgverify.check_guarantees(target) == []

    def test_the_trigger_is_still_armed_afterwards(self, source, target,
                                                    pg_settings):
        """The load must not leave the guarantee switched off — which is what
        the `DISABLE TRIGGER` approach risks if it fails between the two."""
        pgload.migrate(source, target, settings=pg_settings)
        with pytest.raises(db.IntegrityError, match="nothing is promoted"):
            target.execute(
                "INSERT INTO cdp_documents (authority_ons_code, document_url, "
                "document_type, source_url, retrieved_at, http_status, "
                "source_system, payload_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("E06000001", "https://example.org/unpromoted.pdf",
                 "cdp_strategy", *PROVENANCE))
        target.rollback()

    def test_a_verified_census_figure_keeps_its_decision(self, source, target,
                                                          pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        assert target.execute(
            "SELECT verified FROM workforce_census_metrics").fetchone()[0] == 1


class TestIdentitySequences:
    def test_the_next_id_is_past_every_loaded_one(self, source, target,
                                                   pg_settings):
        """Ids are copied verbatim so foreign keys still point where they did.
        A sequence left at 1 fails on the first review item somebody adds —
        days later, with nothing connecting it to the migration."""
        pgload.migrate(source, target, settings=pg_settings)
        assert pgverify.check_sequences(target) == []

        target.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            "created_at) VALUES (?, ?, ?, 'pending', ?)",
            ("m01", "unmatched_buyer", "a new one", "2026-08-15T00:00:00+00:00"))
        target.commit()
        assert target.execute(
            "SELECT MAX(id) FROM review_queue").fetchone()[0] == 42

    def test_an_empty_table_leaves_its_sequence_usable(self, source, target,
                                                        pg_settings):
        """`setval(seq, 0)` is below the minimum value and raises, which is
        why the loader adds one and says the value is not yet used."""
        pgload.migrate(source, target, settings=pg_settings)
        target.execute(
            "INSERT INTO parse_failures (module, field_name, raw_fragment, "
            "reason, created_at) VALUES (?, ?, ?, ?, ?)",
            ("m01", "f", "frag", "why", "2026-08-15T00:00:00+00:00"))
        target.commit()
        assert target.execute(
            "SELECT id FROM parse_failures").fetchone()[0] == 1


class TestRefusalsAndRecovery:
    def test_a_target_holding_rows_is_refused(self, source, target, pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        pgload.state_path_for(pg_settings).unlink()
        with pytest.raises(pgload.LoadError, match="already holds rows"):
            pgload.migrate(source, target, settings=pg_settings)

    def test_truncate_says_so_explicitly(self, source, target, pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        pgload.state_path_for(pg_settings).unlink()
        summary = pgload.migrate(source, target, settings=pg_settings,
                                  truncate=True)
        assert pgverify.verify(source, target)["ok"]
        assert summary["rows"] > 0

    def test_an_interrupted_load_resumes_where_it_stopped(self, source, target,
                                                           pg_settings):
        """One table at a time, one line in the state file each, so what an
        interruption leaves is whole tables and never a partial one."""
        first = pgload.load_order(target)[0]
        pgload.migrate(source, target, settings=pg_settings, only=[first])

        summary = pgload.migrate(source, target, settings=pg_settings, resume=True)
        assert first in summary["counts"]
        assert pgverify.verify(source, target)["ok"]

    def test_a_second_run_without_resume_says_what_to_do(self, source, target,
                                                          pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        with pytest.raises(pgload.LoadError, match="Delete it"):
            pgload.migrate(source, target, settings=pg_settings)

    def test_a_resume_against_a_changed_target_is_refused(
            self, source, target, pg_settings):
        first = pgload.load_order(target)[0]
        pgload.migrate(source, target, settings=pg_settings, only=[first])
        target.execute(f"DELETE FROM {catalog.quote(first)}")
        target.commit()
        with pytest.raises(pgload.LoadError, match="written to this database"):
            pgload.migrate(source, target, settings=pg_settings, resume=True)

    def test_the_source_is_never_written_to(self, source, target, pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            source.execute("DELETE FROM authorities")


class TestVerificationNoticesWhatWentWrong:
    def test_a_row_deleted_from_the_target_is_reported(self, source, target,
                                                        pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        target.execute("DELETE FROM authorities WHERE ons_code = ?",
                        ("E06000002",))
        target.commit()
        report = pgverify.verify(source, target)
        assert not report["ok"]
        assert any("authorities" in p for p in report["problems"])

    def test_a_changed_value_is_reported_with_its_key(self, source, target,
                                                       pg_settings):
        pgload.migrate(source, target, settings=pg_settings)
        target.execute("UPDATE authorities SET name = ? WHERE ons_code = ?",
                        ("Something else", "E06000001"))
        target.commit()
        report = pgverify.verify(source, target)
        assert any("ons_code='E06000001'" in p for p in report["problems"]), (
            report["problems"])

    def test_a_reader_role_can_run_the_verification(self, source, target,
                                                     pg_settings):
        """The check that says the two agree should not need write access to
        either of them."""
        ro_url = _configured_url("POSTGRES_TEST_RO_URL")
        if not ro_url:
            pytest.skip("POSTGRES_TEST_RO_URL is not set; no reader role to test")
        from pipeline import pg as pg_module

        pgload.migrate(source, target, settings=pg_settings)
        reader = pg_module.connect(ro_url, readonly=True)
        try:
            # Deep, so it exercises the streaming cursor on an autocommit
            # connection — the one place the read path and the verification
            # meet, and the one that would fail with "cursor does not exist".
            report = pgverify.verify(source, reader, deep=True)
        finally:
            reader.close()
        assert report["ok"], report["problems"]
        # Except the one it cannot: the sequences live outside what the reader
        # role holds SELECT on, and the report says so rather than reporting a
        # check it did not run as passed.
        assert report["checks"]["sequences"] is False
        assert report["checks"]["guarantees"] is True
