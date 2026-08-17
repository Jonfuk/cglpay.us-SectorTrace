"""One-shot: fill `contracts.notice_web_url` from bytes already on disk.

Migration 0032 added the column and m01 fills it going forward. This is for
the 98,636 rows collected before it existed.

It fetches nothing. Every contracts row carries the SHA-256 of the API page it
came from, and that page is in `data/raw/<source_system>/` under that hash --
which is the whole point of archiving raw bodies, and the reason the column
can be populated for history without asking two government services to serve
five years of pagination again. A row whose archived page is missing or no
longer parses is left NULL, because the alternative is constructing a URL and
storing it in a column that means "the source published this".

Idempotent, and safe to stop: it writes in batches and only ever sets rows
where the column is still NULL. Run a backup first -- it rewrites a column on
every matched row:

    ./start.sh backup
    uv run python -m pipeline.backfill_notice_urls

`--dry-run` reports what it would set and writes nothing.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path

import structlog

from pipeline import db
from pipeline.archive import get_archive
from pipeline.config import Settings, get_settings
from pipeline.notice_urls import published_notice_url

log = structlog.get_logger()

# Rows updated between commits. Small enough that stopping the run loses
# little, large enough not to commit per row across ~98k of them.
BATCH = 2_000


def _archived_page(raw_dir: Path, source_system: str, sha256: str) -> dict | None:
    """The archived OCDS page for one payload hash, or None.

    None covers three cases that are all the same decision -- leave the row
    alone: the archive predates this row, the file is not readable, or it is
    not the JSON it was when it was written.
    """
    if not sha256:
        return None
    directory = raw_dir / source_system
    if not directory.is_dir():
        return None
    for candidate in directory.glob(f"{sha256}.*"):
        if not candidate.is_file():
            continue
        try:
            return json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return None
    return None


def backfill(conn: sqlite3.Connection, settings: Settings | None = None,
              *, dry_run: bool = False) -> dict[str, int]:
    """Set notice_web_url wherever an archived release published one.

    Grouped by payload hash so each archived page is read and parsed once
    rather than once per row: a single API page carries up to 100 releases,
    and several contracts rows can share one release when a notice awards to
    several suppliers.
    """
    settings = settings or get_settings()
    archive = get_archive(settings)

    todo: dict[tuple[str, str], list[str]] = defaultdict(list)
    rows = conn.execute(
        "SELECT notice_id, source_system, payload_sha256 FROM contracts "
        "WHERE notice_web_url IS NULL AND payload_sha256 IS NOT NULL").fetchall()
    for row in rows:
        todo[(row["source_system"], row["payload_sha256"])].append(row["notice_id"])

    stats = {"rows_considered": len(rows), "pages_read": 0, "pages_missing": 0,
              "rows_set": 0, "rows_without_a_published_url": 0}
    pending: list[tuple[str, str]] = []

    for (source_system, sha256), notice_ids in todo.items():
        try:
            obj = archive.lookup(source_system, sha256)
            page = json.loads(obj.read_bytes()) if obj else None
        except (OSError, ValueError, UnicodeDecodeError):
            page = None
        if page is None:
            stats["pages_missing"] += 1
            stats["rows_without_a_published_url"] += len(notice_ids)
            continue
        stats["pages_read"] += 1

        wanted = set(notice_ids)
        found: dict[str, str] = {}
        for release in page.get("releases") or []:
            notice_id = release.get("id")
            if notice_id not in wanted:
                continue
            url = published_notice_url(release, source_system)
            if url:
                found[notice_id] = url

        for notice_id in notice_ids:
            url = found.get(notice_id)
            if url is None:
                stats["rows_without_a_published_url"] += 1
                continue
            pending.append((url, notice_id))

        if not dry_run and len(pending) >= BATCH:
            stats["rows_set"] += _write(conn, pending)
            pending.clear()

    if pending:
        if dry_run:
            stats["rows_set"] += len(pending)
        else:
            stats["rows_set"] += _write(conn, pending)

    return stats


def _write(conn: sqlite3.Connection, pending: list[tuple[str, str]]) -> int:
    """One batch. The NULL guard is repeated in the UPDATE so a second run --
    or a run racing m01 -- cannot overwrite a value already captured."""
    conn.executemany(
        "UPDATE contracts SET notice_web_url = ? "
        "WHERE notice_id = ? AND notice_web_url IS NULL", pending)
    conn.commit()
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                         help="report what would be set and write nothing")
    args = parser.parse_args()

    settings = get_settings()
    conn = db.get_connection(settings)
    try:
        stats = backfill(conn, settings, dry_run=args.dry_run)
    finally:
        conn.close()

    log.info("backfill.notice_urls", dry_run=args.dry_run, **stats)
    for key, value in stats.items():
        print(f"{key.replace('_', ' '):<34} {value:>9,}")


if __name__ == "__main__":
    main()
