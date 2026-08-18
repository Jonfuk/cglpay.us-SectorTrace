"""Read-only inventory of undecided promotion candidates.

Autonomous bulk promotion is disabled. A successful fetch proves that a URL
answers; it does not prove that the document is what its listing claims, and
attributing a loop to a person's name does not prove that person opened every
document. Use the Candidates tab or `pipeline.promote.promote()` one reviewed
candidate at a time.

Only `--dry-run` is accepted; it lists candidates and writes nothing.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import structlog

from pipeline import db, promote
from pipeline.config import get_settings

log = structlog.get_logger()


class BulkPromotionDisabled(RuntimeError):
    """An attempted autonomous bulk promotion."""


def _undecided_urls(conn: sqlite3.Connection, spec: dict) -> list[str]:
    """Candidates nobody has decided on, in a stable order.

    Only `verified = 0 AND rejected = 0` are candidates at all. A promoted
    candidate whose flag was reset by a module re-run is not in here — that is
    `promotions_without_flag`'s job, and it is a repair, not a promotion.
    """
    return [row[0] for row in conn.execute(
        f"SELECT {spec['candidate_url_column']} FROM {spec['candidate_table']} "
        "WHERE verified = 0 AND rejected = 0 ORDER BY 1")]


def _plan(conn: sqlite3.Connection, kind: str | None,
           document_type: str | None) -> tuple[list[tuple[str, str]], int]:
    """The candidates that would be promoted, and how many are blocked on a
    missing `--document-type`.

    Built up front rather than during the loop so the confirmation prompt can
    name a real count of real documents before anything is fetched.
    """
    todo: list[tuple[str, str]] = []
    needing_type = 0
    for name, spec in promote.KINDS.items():
        if kind and name != kind:
            continue
        already = promote.promoted_urls(conn, name)
        for url in _undecided_urls(conn, spec):
            if url in already:
                continue
            if name == "cdp_document" and not document_type:
                needing_type += 1
                continue
            todo.append((name, url))
    return todo, needing_type


def _run(conn: sqlite3.Connection, settings, by: str, todo: list[tuple[str, str]],
         document_type: str | None) -> dict:
    raise BulkPromotionDisabled(
        "autonomous bulk promotion is disabled; review and promote each "
        "candidate individually")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--by", required=True,
                        help="who requested this read-only inventory")
    parser.add_argument("--kind", choices=sorted(promote.KINDS),
                        help="restrict to one candidate kind")
    parser.add_argument("--document-type",
                        help="confirmed document type for every CDP candidate")
    parser.add_argument("--db", type=Path,
                        help="force the SQLite warehouse at this path")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be promoted and write nothing")
    args = parser.parse_args()

    if not args.dry_run:
        parser.error(
            "autonomous bulk promotion is disabled; use --dry-run to inventory "
            "candidates, then review them individually")

    settings = get_settings()
    if args.db:
        # A --db names a file, so it is a SQLite target and must be one even
        # when .env names a PostgreSQL warehouse: silently ignoring it would
        # mean the run went to whatever .env said while the operator believes
        # it is writing to the file they typed. The config treats an unset
        # DATABASE_URL as SQLite for exactly this reason.
        settings.database_path = args.db
        settings.database_url = None

    conn = db.get_connection(settings)
    try:
        db.apply_migrations(conn)
        todo, needing_type = _plan(conn, args.kind, args.document_type)
        target = settings.redacted_database_url or str(settings.database_path)
        log.info("promote_all.start", by=args.by, kind=args.kind or "all",
                  warehouse=target, dry_run=args.dry_run,
                  candidates=len(todo), needing_document_type=needing_type)

        for name, url in todo:
            log.info("promote_all.would_promote", kind=name, url=url, by=args.by)
        stats = {"promoted": 0, "failed": 0, "skipped": 0,
                  "needs_document_type": needing_type, "would_promote": len(todo),
                  "failures": []}
    finally:
        conn.close()

    failures = stats.pop("failures")
    log.info("promote_all.done", **stats)
    for key, value in stats.items():
        print(f"{key.replace('_', ' '):<22} {value:>9,}")
    if failures:
        print("\ncandidates left undecided (fetch or confirmation refused):")
        for url, reason in failures:
            print(f"  {url}\n    {reason}")


if __name__ == "__main__":
    main()
