"""Copying the warehouse, and putting it back.

The thing worth testing here is not that a file appears. It is that the file
holds what the original held, that a damaged one is refused rather than
restored, and that restoring never destroys what it replaces. A backup nobody
has restored is a hope; these tests restore.

The warehouse this protects took hours of deliberately slow crawling to build
and can only be rebuilt by doing that again.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from pipeline import backup, db


@pytest.fixture
def warehouse(conn, settings):
    """A warehouse with rows in it, and an archive beside it."""
    conn.execute(
        "INSERT INTO module_cursors (module, cursor_value, updated_at) "
        "VALUES ('m01_procurement', 'DONE:2026-01-01', '2026-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO review_queue (module, item_type, raw_value, context_json, "
        "status, created_at) VALUES ('m10_committee_papers', "
        "'committee_url_unknown', 'Kent', '{}', 'pending', '2026-01-01T00:00:00Z')")
    conn.commit()

    archive = settings.raw_archive_dir / "find_a_tender"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / ("a" * 64 + ".json")).write_bytes(b'{"notice": 1}')
    (archive / ("b" * 64 + ".json")).write_bytes(b'{"notice": 2}')
    (settings.raw_archive_dir / "cqc").mkdir(parents=True, exist_ok=True)
    (settings.raw_archive_dir / "cqc" / ("c" * 64 + ".json")).write_bytes(b"{}")
    return conn


def test_a_backup_holds_what_the_warehouse_held(warehouse, settings):
    manifest = backup.create(settings)

    copy = settings.backup_dir / manifest["warehouse"]["backup"].rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    assert copy.is_file()

    with sqlite3.connect(f"file:{copy}?mode=ro", uri=True) as restored:
        assert restored.execute(
            "SELECT cursor_value FROM module_cursors").fetchone()[0] == "DONE:2026-01-01"
        assert restored.execute(
            "SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1
    assert manifest["warehouse"]["integrity"] == "ok"


def test_the_copy_is_verified_table_by_table(warehouse, settings):
    manifest = backup.create(settings)
    counts = manifest["warehouse"]["counts"]

    assert counts["module_cursors"] == 1
    assert counts["review_queue"] == 1
    # Every table in the source, not just the ones with rows.
    assert "schema_migrations" in counts
    assert manifest["warehouse"]["drifted_while_copying"] == {}


def test_the_migrations_travel_with_it(warehouse, settings):
    """A backup restored against a checkout expecting a later schema should be
    diagnosable without opening it."""
    manifest = backup.create(settings)

    assert manifest["warehouse"]["migrations"], "the copy records its own schema"
    assert any(name.startswith("0001") for name in manifest["warehouse"]["migrations"])


def test_the_archive_is_inventoried_not_copied(warehouse, settings):
    manifest = backup.create(settings)
    archive = manifest["raw_archive"]

    assert archive["files"] == 3
    assert archive["sources"]["find_a_tender"]["files"] == 2
    assert archive["sources"]["cqc"]["files"] == 1
    assert archive["bytes"] > 0
    # Nothing was duplicated into the backup directory.
    assert not (settings.backup_dir / "find_a_tender").exists()


def test_the_listing_names_every_archived_file(warehouse, settings):
    backup.create(settings)
    listing = next(settings.backup_dir.glob("*.archive.txt"))

    names = listing.read_text(encoding="utf-8").split()
    assert len(names) == 3
    assert any(name.startswith("find_a_tender/") for name in names)


def test_a_manifest_says_what_went_missing(warehouse, settings):
    """The question the inventory exists to answer."""
    backup.create(settings)
    manifest_path = next(settings.backup_dir.glob("*.manifest.json"))

    assert backup.missing_from_archive(manifest_path) == []

    (settings.raw_archive_dir / "cqc" / ("c" * 64 + ".json")).unlink()
    missing = backup.missing_from_archive(manifest_path)

    assert missing == [f"cqc/{'c' * 64}.json"]


def test_it_will_not_overwrite_an_existing_backup(warehouse, settings, tmp_path):
    target = tmp_path / "taken.db"
    target.write_bytes(b"not a database")

    with pytest.raises(backup.BackupError, match="already exists"):
        backup.create(settings, destination=target)

    assert target.read_bytes() == b"not a database"


def test_backing_up_nothing_is_an_error_not_an_empty_file(settings, tmp_path):
    settings.database_path = tmp_path / "never-created.db"

    with pytest.raises(backup.BackupError, match="no warehouse"):
        backup.create(settings)


# --- restore -------------------------------------------------------------------


def test_a_restore_brings_the_rows_back(warehouse, settings):
    manifest = backup.create(settings)
    source = manifest["warehouse"]["backup"]

    # Lose the warehouse the way it actually gets lost: something rewrites it.
    warehouse.execute("DELETE FROM review_queue")
    warehouse.commit()
    warehouse.close()

    from pathlib import Path

    result = backup.restore(Path(source), settings, force=True)

    conn = db.get_connection(settings)
    try:
        assert conn.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1
    finally:
        conn.close()
    assert result["rows"] > 0


def test_a_restore_keeps_what_it_replaces(warehouse, settings):
    manifest = backup.create(settings)
    warehouse.close()

    from pathlib import Path

    result = backup.restore(Path(manifest["warehouse"]["backup"]), settings, force=True)

    superseded = Path(result["superseded"])
    assert superseded.is_file(), "the replaced warehouse is renamed, never deleted"
    with sqlite3.connect(f"file:{superseded}?mode=ro", uri=True) as old:
        assert old.execute("SELECT COUNT(*) FROM review_queue").fetchone()[0] == 1


def test_a_restore_over_a_live_warehouse_needs_force(warehouse, settings):
    manifest = backup.create(settings)
    from pathlib import Path

    with pytest.raises(backup.BackupError, match="already exists"):
        backup.restore(Path(manifest["warehouse"]["backup"]), settings)

    assert settings.database_path.is_file()


def test_a_corrupt_backup_is_refused(warehouse, settings, tmp_path):
    """A restore is the one moment the warehouse is at its most replaceable."""
    manifest = backup.create(settings)
    from pathlib import Path

    damaged = Path(manifest["warehouse"]["backup"])
    content = bytearray(damaged.read_bytes())
    # Past the header, into the first page's contents.
    for i in range(2048, 6000):
        content[i] = 0
    damaged.write_bytes(bytes(content))

    with pytest.raises(backup.BackupError):
        backup.restore(damaged, settings, force=True)


def test_restoring_a_file_that_is_not_there(settings, tmp_path):

    with pytest.raises(backup.BackupError, match="no backup file"):
        backup.restore(tmp_path / "nope.db", settings)


def test_stale_wal_sidecars_do_not_survive_a_restore(warehouse, settings):
    """A WAL belonging to the replaced database, left beside a restored file,
    is how a good backup becomes a corrupt warehouse."""
    manifest = backup.create(settings)
    warehouse.close()

    wal = settings.database_path.with_name(settings.database_path.name + "-wal")
    wal.write_bytes(b"stale wal from the database being replaced")

    from pathlib import Path

    backup.restore(Path(manifest["warehouse"]["backup"]), settings, force=True)

    assert not wal.exists()


# --- listing -------------------------------------------------------------------


def test_backups_are_listed_newest_first(warehouse, settings):
    backup.create(settings, label="first")
    backup.create(settings, label="second")

    names = [entry["name"] for entry in backup.listing(settings)]

    assert len(names) == 2
    assert "second" in names[0]
    assert "first" in names[1]
    assert all(entry["rows"] for entry in backup.listing(settings))


def test_listing_nothing_is_not_an_error(settings):
    assert backup.listing(settings) == []


def test_a_label_lands_in_the_filename(warehouse, settings):
    manifest = backup.create(settings, label="before-m04-rerun")

    assert "before-m04-rerun" in manifest["warehouse"]["backup"]


def test_the_manifest_is_readable_json(warehouse, settings):
    backup.create(settings)
    path = next(settings.backup_dir.glob("*.manifest.json"))

    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed["warehouse"]["integrity"] == "ok"
    assert parsed["sqlite_version"]


def test_two_backups_in_one_second_do_not_collide(warehouse, settings):
    """Second-resolution names, and a script that takes one either side of a
    short module run. The caller did not choose the name, so a collision in it
    is not their mistake to be told about."""
    first = backup.create(settings)
    second = backup.create(settings)

    assert first["warehouse"]["backup"] != second["warehouse"]["backup"]
    assert len(backup.listing(settings)) == 2


def test_an_explicit_destination_is_never_overwritten(warehouse, settings, tmp_path):
    """The opposite rule, and deliberately so: a path someone typed."""
    chosen = tmp_path / "chosen.db"
    backup.create(settings, destination=chosen)
    before = chosen.stat().st_size

    with pytest.raises(backup.BackupError, match="already exists"):
        backup.create(settings, destination=chosen)

    assert chosen.stat().st_size == before
