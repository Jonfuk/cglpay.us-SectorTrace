"""The PostgreSQL snapshot format, and what the backup tooling does with it.

No server here. What is being tested is the half of `pipeline/pgbackup.py`
that has to work when there is no server: reading an archive back, refusing a
damaged one, and the file-naming that decides which snapshots `prune` will
delete. The other half — taking the snapshot and putting it back — is in
`tests/test_pg_backup_live.py`, because a `COPY` round-trip cannot be
simulated into anything worth believing.

A backup nobody has restored is a hope, and a *verifier* nobody has lied to is
the same thing: most of this file builds archives that are wrong in one
specific way and checks that the wrongness is named.
"""
from __future__ import annotations

import gzip
import json

import pytest

from pipeline import backup, pgbackup
from pipeline.config import Settings

HEADER = {
    "format": 1,
    "created_at": "2026-08-15T00:00:00+00:00",
    "source": "postgresql://sectortrace_app:***@lan:5432/sectortrace",
    "server_version": "PostgreSQL 18.6",
    "migrations": ["0001_core.sql", "0002_geography.sql"],
    "tables": ["authorities", "module_cursors"],
}


def _archive(path, blocks, *, header=None, trailer="computed"):
    """An archive built by hand, so a test can break one thing in it.

    `blocks` is `{table: [row, ...]}` with rows as already-escaped COPY text.
    """
    counts, digests = {}, {}
    import hashlib

    with gzip.open(path, "wb") as out:
        out.write(b"-- SectorTrace PostgreSQL warehouse snapshot.\n")
        out.write(("-- sectortrace-pgdump "
                    + json.dumps(header if header is not None else HEADER)
                    + "\n").encode("utf-8"))
        for table, rows in blocks.items():
            out.write(b"\n")
            out.write(f'COPY "{table}" ("a", "b") FROM stdin;\n'.encode("utf-8"))
            digest = hashlib.sha256()
            for row in rows:
                line = (row + "\n").encode("utf-8")
                digest.update(line)
                out.write(line)
            out.write(b"\\.\n")
            counts[table] = len(rows)
            digests[table] = digest.hexdigest()
        if trailer == "computed":
            trailer = {"rows": sum(counts.values()), "counts": counts,
                        "sha256": digests, "finished_at": "2026-08-15T00:00:01+00:00"}
        if trailer is not None:
            out.write(("-- sectortrace-trailer " + json.dumps(trailer)
                        + "\n").encode("utf-8"))
    return path


class TestReadingAnArchiveBack:
    def test_it_counts_the_rows_it_holds(self, tmp_path):
        path = _archive(tmp_path / "w.sql.gz",
                         {"authorities": ["E06000001\tHartlepool",
                                           "E06000002\tMiddlesbrough"],
                          "module_cursors": ["m01\tDONE"]})

        report = pgbackup.verify_archive(path)

        assert report["rows"] == 3
        assert report["counts"] == {"authorities": 2, "module_cursors": 1}
        assert report["migrations"] == HEADER["migrations"]

    def test_an_empty_table_is_still_a_table(self, tmp_path):
        """A table with no rows has to appear, or a restore would leave
        whatever is in the target's copy of it."""
        path = _archive(tmp_path / "w.sql.gz",
                         {"authorities": [], "module_cursors": ["m01\tDONE"]})

        assert pgbackup.verify_archive(path)["counts"]["authorities"] == 0

    def test_a_row_that_looks_like_a_comment_is_data(self, tmp_path):
        """`--` at the start of a value is a value. Comments are only comments
        outside a COPY block, which is why the reader tracks where it is
        rather than matching on the line."""
        path = _archive(tmp_path / "w.sql.gz",
                         {"authorities": ["-- not a comment\tx"]})

        assert pgbackup.verify_archive(path)["counts"]["authorities"] == 1

    def test_the_header_can_be_read_without_the_data(self, tmp_path):
        path = _archive(tmp_path / "w.sql.gz", {"authorities": ["a\tb"]})

        assert pgbackup.read_header(path)["server_version"] == "PostgreSQL 18.6"


class TestWhatItRefuses:
    def test_a_file_with_no_trailer_did_not_finish(self, tmp_path):
        """The trailer is written last, so its absence is the signature of a
        dump that was interrupted — which is the failure this format is shaped
        to make visible."""
        path = _archive(tmp_path / "w.sql.gz", {"authorities": ["a\tb"]},
                         trailer=None)

        with pytest.raises(backup.BackupError, match="no trailer"):
            pgbackup.verify_archive(path)

    def test_a_count_that_disagrees_with_the_rows_is_named(self, tmp_path):
        path = _archive(tmp_path / "w.sql.gz", {"authorities": ["a\tb"]},
                         trailer={"rows": 9, "counts": {"authorities": 9},
                                   "sha256": {"authorities": "0" * 64}})

        with pytest.raises(backup.BackupError, match="authorities.*9 rows"):
            pgbackup.verify_archive(path)

    def test_changed_bytes_are_caught_by_the_hash(self, tmp_path):
        """The row count still agrees; only the content moved. Without the
        per-table digest this is the edit that would restore silently."""
        import hashlib

        rows = ["E06000001\t100"]
        path = _archive(tmp_path / "w.sql.gz", {"authorities": rows})
        honest = hashlib.sha256(b"E06000001\t100\n").hexdigest()

        tampered = tmp_path / "tampered.sql.gz"
        with gzip.open(path, "rb") as source, gzip.open(tampered, "wb") as out:
            out.write(source.read().replace(b"E06000001\t100",
                                             b"E06000001\t900"))

        assert pgbackup.verify_archive(path)["sha256"]["authorities"] == honest
        with pytest.raises(backup.BackupError, match="not the bytes"):
            pgbackup.verify_archive(tampered)

    def test_a_file_that_is_not_an_archive_says_so(self, tmp_path):
        path = tmp_path / "w.sql.gz"
        path.write_bytes(b"not gzip at all")

        with pytest.raises(backup.BackupError, match="gzip"):
            pgbackup.verify_archive(path)

    def test_a_gzip_file_that_is_not_ours_says_so(self, tmp_path):
        path = tmp_path / "w.sql.gz"
        with gzip.open(path, "wb") as out:
            out.write(b"SELECT 1;\n")

        with pytest.raises(backup.BackupError, match="no SectorTrace header"):
            pgbackup.verify_archive(path)

    def test_a_format_from_the_future_is_not_guessed_at(self, tmp_path):
        path = _archive(tmp_path / "w.sql.gz", {"authorities": ["a\tb"]},
                         header={**HEADER, "format": 99})

        with pytest.raises(backup.BackupError, match="format 99"):
            pgbackup.verify_archive(path)


class TestNamingAndRetention:
    """The rules `list-backups` and `prune` apply, with two suffixes in play.

    The hazard being pinned: `Path.stem` of `warehouse-….sql.gz` is
    `warehouse-….sql`, which matches no rule here. Every PostgreSQL snapshot
    would have been filed as labelled and kept for ever — a retention policy
    that silently retains everything, discovered when the disk fills.
    """

    def test_the_manifest_sits_beside_either_kind(self, tmp_path):
        assert backup.companion(tmp_path / "warehouse-X.db",
                                 ".manifest.json").name == "warehouse-X.manifest.json"
        assert backup.companion(tmp_path / "warehouse-X.sql.gz",
                                 ".manifest.json").name == "warehouse-X.manifest.json"

    def test_an_unlabelled_snapshot_is_prunable(self, tmp_path):
        settings = Settings(contact_email="t@example.com",
                             backup_dir=tmp_path / "backups", _env_file=None)
        settings.backup_dir.mkdir(parents=True)
        for name in ("warehouse-20260814T010101Z.sql.gz",
                      "warehouse-20260815T010101Z.sql.gz",
                      "warehouse-20260815T020202Z-before-cutover.sql.gz"):
            (settings.backup_dir / name).write_bytes(b"x")
        (settings.backup_dir / "warehouse-20260814T010101Z.manifest.json").write_text(
            "{}", encoding="utf-8")

        result = backup.prune(settings, keep=1)

        assert result["removed"] == ["warehouse-20260814T010101Z.sql.gz"]
        assert result["labelled_kept"] == 1
        assert not (settings.backup_dir
                     / "warehouse-20260814T010101Z.manifest.json").exists(), (
            "the manifest describes a file that is gone")

    def test_both_backends_appear_in_one_listing(self, tmp_path):
        settings = Settings(contact_email="t@example.com",
                             backup_dir=tmp_path / "backups", _env_file=None)
        settings.backup_dir.mkdir(parents=True)
        (settings.backup_dir / "warehouse-20260813T010101Z.db").write_bytes(b"x")
        (settings.backup_dir / "warehouse-20260815T010101Z.sql.gz").write_bytes(b"x")

        by_name = {e["name"]: e for e in backup.listing(settings)}

        assert by_name["warehouse-20260813T010101Z.db"]["backend"] == "sqlite"
        assert by_name["warehouse-20260815T010101Z.sql.gz"]["backend"] == "postgres"


class TestTheBackendDecidesNotTheFile:
    def test_a_sqlite_backup_is_not_restored_into_postgres(self, tmp_path):
        """Refused on the name, before anything is opened. The alternative is
        a parse error from inside a driver, which does not tell the operator
        that the thing to change is DATABASE_URL."""
        settings = Settings(contact_email="t@example.com",
                             database_url="postgresql://u:p@lan:5432/sectortrace",
                             _env_file=None)
        file = tmp_path / "warehouse-20260815T010101Z.db"
        file.write_bytes(b"SQLite format 3\x00")

        with pytest.raises(backup.BackupError, match="not a postgres backup"):
            backup.restore(file, settings)

    def test_a_postgres_snapshot_is_not_restored_into_sqlite(self, tmp_path):
        settings = Settings(contact_email="t@example.com",
                             database_path=tmp_path / "warehouse.db",
                             _env_file=None)
        file = tmp_path / "warehouse-20260815T010101Z.sql.gz"
        file.write_bytes(b"x")

        with pytest.raises(backup.BackupError, match="not a sqlite backup"):
            backup.restore(file, settings)

    def test_a_postgres_dump_needs_a_postgres_url(self, tmp_path):
        settings = Settings(contact_email="t@example.com",
                             database_path=tmp_path / "warehouse.db",
                             _env_file=None)

        with pytest.raises(backup.BackupError, match="DATABASE_URL is not set"):
            pgbackup.dump(settings)
