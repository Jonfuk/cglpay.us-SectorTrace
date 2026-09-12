"""The one-shot that fills notice_web_url from the raw archive.

It reads bytes already on disk and never fetches, so these tests build a small
archive under tmp_path and point the settings at it. What matters is that it
fills only what a release actually published, that provenance is untouched,
and that running it twice is the same as running it once.
"""
from __future__ import annotations

import json

import pytest

from pipeline import backfill_notice_urls as backfill

FTS = "find_a_tender"
NOTICE = "https://www.find-tender.service.gov.uk/Notice/076079-2026"


def _page(*releases: dict) -> dict:
    return {"releases": list(releases)}


def _release(notice_id: str, *urls: str) -> dict:
    return {"id": notice_id,
             "contracts": [{"documents": [{"url": u} for u in urls]}]}


def _archive(settings, sha256: str, page: dict, source_system: str = FTS) -> None:
    directory = settings.raw_archive_dir / source_system
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{sha256}.json").write_text(json.dumps(page), encoding="utf-8")


def _contract(conn, notice_id: str, sha256: str, *, source_system: str = FTS,
               source_url: str = "https://api.example/page?cursor=abc") -> None:
    conn.execute(
        "INSERT INTO contracts (notice_id, supplier_id, ocid, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (%s, '', 'ocds-x', %s, '2026-01-01T00:00:00Z', 200, %s, %s)",
        (notice_id, source_url, source_system, sha256))
    conn.commit()


@pytest.fixture
def seeded(conn, settings):
    _archive(settings, "hash1", _page(_release("076079-2026", NOTICE)))
    _contract(conn, "076079-2026", "hash1")
    return conn


def test_a_published_notice_url_is_filled_in(seeded, settings):
    stats = backfill.backfill(seeded, settings)

    assert stats["rows_set"] == 1
    assert seeded.execute(
        "SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() == NOTICE


def test_the_provenance_column_is_not_touched(seeded, settings):
    """The whole reason there are two columns. source_url is the record of
    which bytes produced the row and this must not go near it."""
    before = seeded.execute("SELECT source_url, payload_sha256, retrieved_at, "
                             "http_status FROM contracts").fetchone()

    backfill.backfill(seeded, settings)

    after = seeded.execute("SELECT source_url, payload_sha256, retrieved_at, "
                            "http_status FROM contracts").fetchone()
    assert after == before


def test_a_release_that_published_no_notice_url_is_left_null(conn, settings):
    _archive(settings, "hash2",
              _page(_release("076079-2026", "https://in-tendhost.co.uk/mk")))
    _contract(conn, "076079-2026", "hash2")

    stats = backfill.backfill(conn, settings)

    assert stats["rows_set"] == 0
    assert stats["rows_without_a_published_url"] == 1
    assert conn.execute("SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() is None


def test_a_missing_archived_page_leaves_the_row_alone(conn, settings):
    """An archive that predates the row is not an error and not a licence to
    construct something."""
    _contract(conn, "076079-2026", "hash-not-on-disk")

    stats = backfill.backfill(conn, settings)

    assert stats["pages_missing"] == 1
    assert stats["rows_set"] == 0
    assert conn.execute("SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() is None


def test_an_unparseable_archived_page_leaves_the_row_alone(conn, settings):
    directory = settings.raw_archive_dir / FTS
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "hash3.json").write_text("{ this is not json", encoding="utf-8")
    _contract(conn, "076079-2026", "hash3")

    stats = backfill.backfill(conn, settings)

    assert stats["pages_missing"] == 1
    assert conn.execute("SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() is None


def test_running_it_twice_changes_nothing_the_second_time(seeded, settings):
    first = backfill.backfill(seeded, settings)
    second = backfill.backfill(seeded, settings)

    assert first["rows_set"] == 1
    assert second["rows_considered"] == 0, "a filled row is not reconsidered"
    assert seeded.execute(
        "SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() == NOTICE


def test_a_dry_run_writes_nothing(seeded, settings):
    stats = backfill.backfill(seeded, settings, dry_run=True)

    assert stats["rows_set"] == 1, "it still reports what it would set"
    assert seeded.execute(
        "SELECT notice_web_url FROM contracts").fetchone().values().__iter__().__next__() is None


def test_one_archived_page_serves_every_row_that_came_from_it(conn, settings):
    """A notice awarding to several suppliers is several contracts rows
    sharing one payload hash. The page is read once."""
    _archive(settings, "hash4", _page(_release("076079-2026", NOTICE)))
    for supplier in ("s1", "s2", "s3"):
        conn.execute(
            "INSERT INTO contracts (notice_id, supplier_id, ocid, source_url, "
            "retrieved_at, http_status, source_system, payload_sha256) VALUES "
            "('076079-2026', %s, 'ocds-x', 'https://api.example/p', "
            "'2026-01-01T00:00:00Z', 200, %s, 'hash4')", (supplier, FTS))
    conn.commit()

    stats = backfill.backfill(conn, settings)

    assert stats["pages_read"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE notice_web_url = %s",
        (NOTICE,)).fetchone().values().__iter__().__next__() == 3
