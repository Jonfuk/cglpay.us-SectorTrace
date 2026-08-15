"""The verification suite, run SQLite against SQLite.

`pgverify` asks its questions through `pipeline/catalog.py`, which answers them
the same way on either backend — so pointing it at two SQLite warehouses
exercises every comparison it makes, offline, with no server. That is not a
compromise: what is being tested here is whether the checks *notice*, and a
difference between two files is as invisible to them as a difference between a
file and a server.

The two checks that are genuinely PostgreSQL-only — the trigger guarantees and
the identity sequences — are skipped by `verify` when the target is not
PostgreSQL, and are exercised in `tests/test_pg_migration_live.py`.
"""
from __future__ import annotations

import shutil
import sqlite3

import pytest

from pipeline import pgverify

AUTHORITY = (
    "ons_code, name, type, active_from, first_seen_vintage, last_seen_vintage, "
    "source_url, retrieved_at, http_status, source_system, payload_sha256")
PLACEHOLDERS = ", ".join("?" * len(AUTHORITY.split(",")))


def _authority(code: str, name: str = "Hartlepool") -> tuple:
    return (code, name, "unitary", "2020-01-01", "2020", "2026",
            "https://example.org/authorities", "2026-08-15T00:00:00+00:00",
            200, "ons", "0" * 64)


def _insert(conn, *rows) -> None:
    for row in rows:
        conn.execute(
            f"INSERT INTO authorities ({AUTHORITY}) VALUES ({PLACEHOLDERS})", row)
    conn.commit()


@pytest.fixture
def target(tmp_path, _schema_template) -> sqlite3.Connection:
    """A second migrated warehouse, standing in for the PostgreSQL one."""
    path = tmp_path / "target.db"
    shutil.copy(_schema_template, path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


class TestTwoWarehousesThatAgree:
    def test_an_identical_copy_verifies(self, conn, target):
        _insert(conn, _authority("E06000001"), _authority("E06000002", "Redcar"))
        _insert(target, _authority("E06000001"), _authority("E06000002", "Redcar"))
        report = pgverify.verify(conn, target)
        assert report["ok"], report["problems"]
        assert report["rows"] == 2

    def test_two_empty_warehouses_verify(self, conn, target):
        report = pgverify.verify(conn, target)
        assert report["ok"], report["problems"]
        assert report["rows"] == 0

    def test_the_migration_ledger_is_not_compared(self, conn, target):
        """The two databases legitimately record different applied files —
        one applied the SQLite tree, the other the PostgreSQL one — so a
        check that compared them would fail on every correct migration."""
        target.execute("DELETE FROM schema_migrations")
        target.commit()
        assert pgverify.verify(conn, target)["ok"]


class TestWhatItNotices:
    def test_a_missing_row(self, conn, target):
        _insert(conn, _authority("E06000001"), _authority("E06000002", "Redcar"))
        _insert(target, _authority("E06000001"))
        report = pgverify.verify(conn, target)
        assert not report["ok"]
        assert any("authorities: 2 rows in SQLite, 1 in PostgreSQL"
                    in p for p in report["problems"]), report["problems"]

    def test_a_changed_value_names_the_row_and_the_column(self, conn, target):
        _insert(conn, _authority("E06000001"))
        _insert(target, _authority("E06000001", "Hartelpool"))
        report = pgverify.verify(conn, target)
        assert not report["ok"]
        assert any("ons_code='E06000001'" in p and "name" in p
                    for p in report["problems"]), report["problems"]

    def test_a_value_that_became_null(self, conn, target):
        _insert(conn, _authority("E06000001"))
        _insert(target, _authority("E06000001"))
        target.execute("UPDATE authorities SET region = NULL")
        conn.execute("UPDATE authorities SET region = 'North East'")
        conn.commit()
        target.commit()
        report = pgverify.verify(conn, target)
        assert any("region" in p and "nulls differ" in p
                    for p in report["problems"]), report["problems"]

    def test_a_number_that_changed_without_changing_the_row_count(
            self, conn, target):
        """The check the whole exercise is for: same rows, same shape, one
        figure different."""
        _insert(conn, _authority("E06000001"))
        _insert(target, _authority("E06000001"))
        target.execute("UPDATE authorities SET http_status = 404")
        target.commit()
        report = pgverify.verify(conn, target)
        assert any("http_status: 200 vs 404" in p
                    for p in report["problems"]), report["problems"]

    def test_a_missing_table_is_reported_rather_than_crashed_on(
            self, conn, target):
        target.execute("DROP TABLE authorities")
        target.commit()
        report = pgverify.verify(conn, target)
        assert any("no table authorities" in p for p in report["problems"])

    def test_it_reports_everything_wrong_rather_than_the_first_thing(
            self, conn, target):
        """A verification that stopped at the first fault would have to be run
        once per fault, and each run reads the whole warehouse."""
        _insert(conn, _authority("E06000001"), _authority("E06000002", "Redcar"))
        _insert(target, _authority("E06000001", "Wrong"),
                 _authority("E06000002", "Also wrong"))
        report = pgverify.verify(conn, target)
        assert len(report["problems"]) >= 2

    def test_it_stops_listing_differences_after_a_handful(self, conn, target):
        for index in range(pgverify.MAX_REPORTED_DIFFERENCES + 4):
            _insert(conn, _authority(f"E060000{index:02d}", "Right"))
            _insert(target, _authority(f"E060000{index:02d}", "Wrong"))
        report = pgverify.verify(conn, target)
        listed = [p for p in report["problems"] if "authorities[" in p]
        assert len(listed) == pgverify.MAX_REPORTED_DIFFERENCES


class TestTheCheapPass:
    def test_quick_verification_skips_the_row_comparison(self, conn, target):
        """Same rows, same aggregates, one value swapped between two rows —
        invisible to counts and to MIN/MAX, and the reason the deep pass
        exists."""
        _insert(conn, _authority("E06000001", "Hartlepool"),
                 _authority("E06000002", "Redcar"))
        _insert(target, _authority("E06000001", "Redcar"),
                 _authority("E06000002", "Hartlepool"))
        assert pgverify.verify(conn, target, deep=False)["ok"]
        assert not pgverify.verify(conn, target, deep=True)["ok"]

    def test_quick_verification_still_catches_a_lost_row(self, conn, target):
        _insert(conn, _authority("E06000001"))
        report = pgverify.verify(conn, target, deep=False)
        assert not report["ok"]

    def test_the_report_says_which_pass_it_ran(self, conn, target):
        assert pgverify.verify(conn, target, deep=False)["checks"]["rows"] is False
        assert pgverify.verify(conn, target, deep=True)["checks"]["rows"] is True


class TestScopeAndSameness:
    def test_a_named_subset_is_all_it_reads(self, conn, target):
        _insert(conn, _authority("E06000001"))
        report = pgverify.verify(conn, target, tables=["contracts"])
        assert report["ok"], report["problems"]
        assert report["tables"] == 1

    def test_nan_is_equal_to_itself_here(self):
        """A NaN that arrived as a NaN did arrive; `float('nan') != float('nan')`
        would otherwise report the same column as different for ever."""
        assert pgverify._same(float("nan"), float("nan"))

    def test_an_integer_is_not_a_float(self):
        assert not pgverify._same(1, 1.0)

    def test_the_postgresql_only_checks_are_skipped_on_sqlite(self, conn, target):
        report = pgverify.verify(conn, target)
        assert "guarantees" not in report["checks"]
        assert "sequences" not in report["checks"]
