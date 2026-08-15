"""Snapshotting a real PostgreSQL warehouse, putting it back, and mirroring it
into SQLite.

Skipped unless `POSTGRES_TEST_URL` is set, read the same way the other live
suites read it. Everything here writes, so — as in `test_pg_migration_live.py`
— each test builds **schemas of its own** and drops them: a snapshot test that
restored into whatever `DATABASE_URL` happened to name would eventually empty
a working warehouse, and this one restores by design.

    uv run python -m pytest tests/test_pg_backup_live.py -q

What only a server can answer, and is therefore here rather than in
`tests/test_pgbackup.py`: that `COPY TO STDOUT` and `COPY FROM STDIN` are
inverse over this schema's real values, that a restore fires the five refusal
triggers in an order that satisfies them, that the identity sequences come out
of a restore pointing past the ids it wrote, and that a warehouse rebuilt in
SQLite from PostgreSQL passes the same row-by-row verification the Phase 2
migration was accepted on.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from conftest import scratch_schema

# The seeded warehouse from the loader's suite. One of each thing that can go
# wrong — a float that is not representable in decimal, text outside ASCII, a
# NULL beside a NOT NULL, an id with a gap in it, evidence that exists only
# because somebody promoted it — and a snapshot has to carry all of them
# unchanged, which is the same list.
from test_pg_migration_live import _seed
from test_postgres_live import (
    LIVE_POSTGRES,
    NO_LIVE_POSTGRES,
    POSTGRES_TEST_RO_URL,
    POSTGRES_TEST_URL,
)

from pipeline import backup, catalog, db, pgbackup, pgload, pgsync, pgverify

MIGRATIONS = Path(__file__).resolve().parent.parent / "pipeline" / "migrations"

pytestmark = pytest.mark.skipif(not LIVE_POSTGRES, reason=NO_LIVE_POSTGRES)


@pytest.fixture
def source_file(settings) -> sqlite3.Connection:
    """A seeded SQLite warehouse, read-only, as the loader takes it."""
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
def warehouse(source_file, settings):
    """A populated PostgreSQL warehouse of this test's own, and its settings.

    Loaded through `pgload` rather than by hand: what is being snapshotted has
    to be a warehouse this project would recognise, ids and promotions and
    all.
    """
    with scratch_schema(POSTGRES_TEST_URL, POSTGRES_TEST_RO_URL) as made:
        pg_settings = settings.model_copy(
            update={"database_url": made.url, "database_ro_url": made.ro_url})
        pgload.migrate(source_file, made.conn, settings=pg_settings)
        yield made.conn, pg_settings


@pytest.fixture
def empty(settings):
    """A second migrated warehouse, to restore into."""
    with scratch_schema(POSTGRES_TEST_URL, POSTGRES_TEST_RO_URL) as made:
        yield made.conn, settings.model_copy(
            update={"database_url": made.url, "database_ro_url": made.ro_url})


class TestASnapshotAndItsProof:
    def test_every_row_is_in_the_archive(self, warehouse):
        conn, pg_settings = warehouse

        manifest = backup.create(pg_settings)

        assert manifest["backend"] == "postgres"
        for table, count in manifest["warehouse"]["counts"].items():
            assert count == conn.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
        # The ledger is not copied — it records what was applied to *this*
        # database — but it is recorded, because a restore has to check it.
        assert "schema_migrations" not in manifest["warehouse"]["counts"]
        assert manifest["warehouse"]["migrations"]

    def test_the_archive_verifies_on_its_own(self, warehouse):
        """With the server unreachable and the warehouse gone, the file still
        has to be able to say whether it is intact."""
        _, pg_settings = warehouse
        manifest = backup.create(pg_settings)

        report = pgbackup.verify_archive(Path(manifest["warehouse"]["backup"]))

        assert report["rows"] == manifest["warehouse"]["rows"]
        assert report["counts"] == manifest["warehouse"]["counts"]

    def test_the_password_is_not_in_the_file(self, warehouse):
        """The URL carries a credential and this file is kept for weeks."""
        _, pg_settings = warehouse
        manifest = backup.create(pg_settings)

        header = pgbackup.read_header(Path(manifest["warehouse"]["backup"]))

        assert "***" in header["source"]
        assert pg_settings.database_url.split("@")[0].split(":")[-1] not in header["source"]

    def test_a_snapshot_is_a_readable_sql_script(self, warehouse):
        """Not a container format anybody needs this repository to open."""
        import gzip

        _, pg_settings = warehouse
        manifest = backup.create(pg_settings)

        with gzip.open(manifest["warehouse"]["backup"], "rb") as archive:
            text = archive.read().decode("utf-8")

        assert 'COPY "authorities"' in text
        assert "FROM stdin;" in text
        assert "\\.\n" in text


class TestPuttingItBack:
    def test_the_rows_come_back_as_themselves(self, warehouse, empty):
        conn, pg_settings = warehouse
        target, target_settings = empty
        manifest = backup.create(pg_settings)

        result = backup.restore(Path(manifest["warehouse"]["backup"]),
                                 target_settings)

        assert result["rows"] == manifest["warehouse"]["rows"]
        for table, count in manifest["warehouse"]["counts"].items():
            assert count == target.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0], table
        # A float that is not representable in decimal, and text outside
        # ASCII: the two values that a round-trip through a text format is
        # most likely to change.
        assert target.execute(
            "SELECT amount FROM public_health_grants "
            "WHERE financial_year = '2025-26'").fetchone()[0] == 0.1 + 0.2
        assert target.execute(
            "SELECT name FROM authorities WHERE ons_code = 'E06000002'"
        ).fetchone()[0] == "Kingston upon Hull — City of"

    def test_a_null_does_not_come_back_as_an_empty_string(self, warehouse, empty):
        _, pg_settings = warehouse
        target, target_settings = empty
        manifest = backup.create(pg_settings)

        backup.restore(Path(manifest["warehouse"]["backup"]), target_settings)

        assert target.execute(
            "SELECT region FROM authorities WHERE ons_code = 'E06000002'"
        ).fetchone()[0] is None

    def test_the_next_id_is_past_every_restored_one(self, warehouse, empty):
        """The failure this prevents arrives days later, as a duplicate key on
        somebody's review decision."""
        _, pg_settings = warehouse
        target, target_settings = empty
        manifest = backup.create(pg_settings)

        backup.restore(Path(manifest["warehouse"]["backup"]), target_settings)

        assert not pgverify.check_sequences(target)
        target.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            "created_at) VALUES ('m01', 'unmatched_buyer', 'after', 'pending', "
            "'2026-08-15T00:00:00+00:00')")
        target.commit()

    def test_the_refusal_triggers_were_armed_throughout(self, warehouse, empty):
        """Settled decision 4 is not suspended for a restore.

        The archive is written parents-first, including the edges the triggers
        impose and no foreign key expresses, so every promotion is in place
        before the evidence that depends on it arrives — and the trigger is
        still there afterwards to prove it was never disabled.
        """
        _, pg_settings = warehouse
        target, target_settings = empty
        manifest = backup.create(pg_settings)

        backup.restore(Path(manifest["warehouse"]["backup"]), target_settings)

        assert not pgverify.check_guarantees(target)
        with pytest.raises(db.IntegrityError):
            target.execute(
                "INSERT INTO cdp_documents (authority_ons_code, document_url, "
                "document_type, source_url, retrieved_at, http_status, "
                "source_system, payload_sha256) VALUES "
                "('E06000001', 'https://example.org/unpromoted.pdf', "
                "'cdp_strategy', 'https://example.org/s', "
                "'2026-08-15T00:00:00+00:00', 200, 'test', '0')")
        target.rollback()

    def test_a_warehouse_with_rows_is_not_replaced_by_accident(
            self, warehouse, empty):
        conn, pg_settings = warehouse
        _, target_settings = empty
        manifest = backup.create(pg_settings)

        with pytest.raises(backup.BackupError, match="already holds"):
            backup.restore(Path(manifest["warehouse"]["backup"]), pg_settings)

        assert conn.execute("SELECT COUNT(*) FROM authorities").fetchone()[0] == 2

    def test_forcing_it_snapshots_what_it_is_about_to_discard(self, warehouse):
        """`backup.restore` renames the SQLite file it replaces. There is
        nothing to rename here, so the equivalent is taken first."""
        conn, pg_settings = warehouse
        manifest = backup.create(pg_settings)
        conn.execute("DELETE FROM authorities WHERE ons_code = 'E06000002'")
        conn.commit()

        result = backup.restore(Path(manifest["warehouse"]["backup"]),
                                 pg_settings, force=True)

        assert result["superseded"], "the discarded state was not kept"
        kept = pgbackup.verify_archive(Path(result["superseded"]))
        assert kept["counts"]["authorities"] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM authorities").fetchone()[0] == 2

    def test_an_archive_from_a_later_schema_is_refused(self, warehouse, empty):
        """The schema comes from the migration tree, so an archive naming
        files this checkout does not have cannot be restored into it — and
        finding that out from a missing column at row 400,000 is worse than
        being told."""
        import gzip
        import json

        _, pg_settings = warehouse
        _, target_settings = empty
        manifest = backup.create(pg_settings)
        original = Path(manifest["warehouse"]["backup"])

        forged = original.with_name("warehouse-20990101T000000Z-forged.sql.gz")
        with gzip.open(original, "rb") as source, gzip.open(forged, "wb") as out:
            for line in source:
                text = line.decode("utf-8")
                if text.startswith("-- sectortrace-pgdump "):
                    header = json.loads(text[len("-- sectortrace-pgdump "):])
                    header["migrations"].append("9999_from_the_future.sql")
                    line = ("-- sectortrace-pgdump " + json.dumps(header)
                             + "\n").encode("utf-8")
                out.write(line)

        with pytest.raises(backup.BackupError, match="9999_from_the_future"):
            backup.restore(forged, target_settings)


class TestTheIntegrityCheck:
    """The Health tab's check, which Phase 1 refused to implement and left to
    this phase — "is this warehouse intact?" being the same question backup
    and restore are about.

    A check that can only pass is what was refused, so two of these three
    break something and require it to be found.
    """

    def test_it_says_what_it_looked_at(self, warehouse):
        from pipeline.web import health

        _, pg_settings = warehouse

        outcome = health.integrity_check(pg_settings)[0]

        assert outcome["ok"] and outcome["integrity"] == ["ok"]
        assert "foreign keys" in outcome["checked"]
        # The panel must not claim the page-level check that did not run.
        assert "pg_amcheck" in outcome["not_checked"]

    def test_an_orphan_is_found(self, warehouse):
        """Made by dropping the constraint, inserting, and putting it back
        `NOT VALID` — which is not a contrivance but the exact state this
        sweep exists to find: PostgreSQL accepts the constraint back without
        looking at a single existing row, and every query afterwards behaves
        as though it had.

        (Disabling the constraint's trigger instead would need superuser, and
        `sectortrace_app` deliberately is not one.)
        """
        from pipeline.web import health

        conn, pg_settings = warehouse
        constraint = conn.execute(
            "SELECT conname AS name, pg_get_constraintdef(oid) AS definition "
            "FROM pg_constraint "
            "WHERE conrelid = to_regclass('cdp_document_candidates') "
            "  AND contype = 'f'").fetchone()
        conn.execute("ALTER TABLE cdp_document_candidates DROP CONSTRAINT "
                      f'"{constraint["name"]}"')
        conn.execute(
            "INSERT INTO cdp_document_candidates (authority_ons_code, "
            "candidate_url, confidence, discovered_at, verified, rejected, "
            "source_url, retrieved_at, http_status, source_system, "
            "payload_sha256) VALUES ('E09999999', "
            "'https://example.org/orphan.pdf', 0.5, "
            "'2026-08-15T00:00:00+00:00', 0, 0, 'https://example.org/s', "
            "'2026-08-15T00:00:00+00:00', 200, 'test', '0')")
        conn.execute('ALTER TABLE cdp_document_candidates ADD CONSTRAINT '
                      f'"{constraint["name"]}" {constraint["definition"]} NOT VALID')
        conn.commit()

        outcome = health.integrity_check(pg_settings)[0]

        assert not outcome["ok"]
        orphans = [v for v in outcome["foreign_key_violations"]
                    if v["table"] == "cdp_document_candidates"]
        assert orphans and "1 orphaned row" in orphans[0]["rowid"]

    def test_a_constraint_that_was_never_checked_is_reported(self, warehouse):
        """`NOT VALID` is enforced for new rows and never checked against the
        old ones: a guarantee the schema claims and does not have. SQLite
        cannot express the state, so nothing in the SQLite path looks for it."""
        from pipeline.web import health

        conn, pg_settings = warehouse
        conn.execute("ALTER TABLE authorities ADD CONSTRAINT region_present "
                      "CHECK (region IS NOT NULL) NOT VALID")
        conn.commit()

        outcome = health.integrity_check(pg_settings)[0]

        assert not outcome["ok"]
        assert any("region_present" in line for line in outcome["integrity"])


class TestTheSqliteMirror:
    def test_a_rebuilt_warehouse_matches_value_for_value(self, warehouse,
                                                           tmp_path):
        """The same verification the Phase 2 migration was accepted on, run
        the other way round."""
        conn, pg_settings = warehouse
        destination = tmp_path / "mirror" / "warehouse.db"

        result = pgsync.refresh(pg_settings, destination=destination,
                                 verify=True, deep=True)

        assert result["verified"] and result["deep"]
        assert destination.is_file()
        with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as lite:
            lite.row_factory = sqlite3.Row
            report = pgverify.verify(lite, conn, deep=True)
        assert report["ok"], report["problems"]
        assert result["rows"] == report["rows"]

    def test_it_says_how_far_apart_they_are(self, warehouse, source_file):
        """`--check` is the question dual-maintenance needs answered on any
        given day, and neither file answers it by being looked at."""
        conn, pg_settings = warehouse
        conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, status, "
            "created_at) VALUES ('m01', 'unmatched_buyer', 'newer', 'pending', "
            "'2026-08-15T00:00:00+00:00')")
        conn.commit()

        report = pgsync.check(pg_settings)

        assert not report["in_step"]
        assert report["drifted"]["review_queue"] == {"sqlite": 3, "postgres": 4}
        assert any("review_queue" in problem for problem in report["problems"])

    def test_the_file_it_replaces_is_kept(self, warehouse, source_file):
        conn, pg_settings = warehouse
        target = pg_settings.database_path
        before = target.stat().st_size
        # Nothing may be holding the warehouse open: Windows refuses to rename
        # a file another process has a handle on, and this fixture is one —
        # which is the same reason the web server has to be stopped before a
        # refresh, and is why `_install` says so by name when it happens.
        source_file.close()

        result = pgsync.refresh(pg_settings, verify=True, deep=False)

        assert result["superseded"], "the warehouse it replaced was deleted"
        assert Path(result["superseded"]).stat().st_size == before
        assert not target.with_name(target.name + "-wal").exists(), (
            "a stale WAL beside a replaced database is how a good copy "
            "becomes a corrupt warehouse")

    def test_a_warehouse_something_else_has_open_is_not_replaced(
            self, warehouse, source_file):
        """The rebuild is finished and verified by then, so this has to name
        what is holding the file rather than fall back on copying over it."""
        _, pg_settings = warehouse

        with pytest.raises(pgsync.SyncError, match="could not be moved aside"):
            pgsync.refresh(pg_settings, verify=False)

        assert list(pg_settings.database_path.parent.glob("*.rebuilding-*")), (
            "the rebuilt warehouse was thrown away rather than kept for the "
            "retry the message asks for")

    def test_an_unverifiable_rebuild_is_not_installed(self, warehouse,
                                                       monkeypatch):
        """The build happens beside the target so that a file which fails
        verification never becomes the warehouse."""
        _, pg_settings = warehouse
        target = pg_settings.database_path
        before = target.read_bytes()

        monkeypatch.setattr(
            pgverify, "verify",
            lambda *a, **k: {"ok": False, "problems": ["invented"], "rows": 0})

        with pytest.raises(pgsync.SyncError, match="invented"):
            pgsync.refresh(pg_settings, verify=True, deep=False)

        assert target.read_bytes() == before
        assert not list(target.parent.glob("*.rebuilding-*")), (
            "the failed attempt was left on disk"
        )
