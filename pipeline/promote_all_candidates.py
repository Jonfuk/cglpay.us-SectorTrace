"""One-shot: promote every undecided candidate, one real promote() at a time.

This is the "approve all" the operator UI deliberately does not offer, made
safe enough to exist at all. It is not a product change and it is not
pipeline/promote.py: that module documents why bulk promotion does not live
there, and this script does not add one. It calls the same promote() the UI
calls, once per candidate, so each promotion still has its own fetch, its own
archived payload and its own evidence_promotions row attributed to the person
who ran this.

Three rules, mirroring the ones the UI is built around:

  * Someone's name. `--by` is required and never defaulted; an audit row
    whose author is a guess is worse than no audit row.

  * A candidate that fails to promote stays undecided. promote() fetches the
    document before writing anything, so a dead link, robots refusal or
    blocked address leaves the candidate exactly where it was and is reported
    here, not papered over.

  * Nothing is confirmed by a guess. CDP candidates carry a
    `document_type_guess`; the evidence table says "confirmed, not guessed".
    If any CDP candidate is undecided you must say what they are with
    `--document-type`; the script refuses to promote a CDP candidate without
    it rather than copying the guess across.

It fetches real documents, so back up the PostgreSQL warehouse first. It writes
to the warehouse named by `DATABASE_URL`.

Whatever the target, the non-dry-run path confirms with you before writing
anything, and a shared PostgreSQL warehouse is the case that matters most:
it is the warehouse other sessions read.

    # the configured PostgreSQL warehouse
    uv run python -m pipeline.promote_all_candidates --by "Your Name"

`--dry-run` lists what would be promoted and writes nothing; `--yes` skips the
confirmation prompt.
"""
from __future__ import annotations

import argparse
import sqlite3

import structlog

from pipeline import db, promote
from pipeline.config import get_settings

log = structlog.get_logger()


def _undecided_urls(conn: sqlite3.Connection, spec: dict) -> list[str]:
    """Candidates nobody has decided on, in a stable order.

    Only `verified = 0 AND rejected = 0` are candidates at all. A promoted
    candidate whose flag was reset by a module re-run is not in here — that is
    `promotions_without_flag`'s job, and it is a repair, not a promotion.
    """
    return [row[spec["url_column"]] for row in conn.execute(
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
    stats = {"promoted": 0, "failed": 0, "skipped": 0, "needs_document_type": 0,
              "would_promote": 0}
    failures: list[tuple[str, str]] = []

    for name, url in todo:
        fields = {"document_type": document_type} if name == "cdp_document" else {}
        try:
            promote.promote(conn, name, url, promoted_by=by,
                            fields=fields, settings=settings)
        except promote.PromotionError as exc:
            stats["failed"] += 1
            failures.append((url, str(exc)))
            log.warning("promote_all.failed", kind=name, url=url,
                         error=str(exc))
        else:
            stats["promoted"] += 1
            log.info("promote_all.promoted", kind=name, url=url, by=by)

    stats["failures"] = failures
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--by", required=True,
                        help="who is promoting (goes on every evidence_promotions row)")
    parser.add_argument("--kind", choices=sorted(promote.KINDS),
                        help="restrict to one candidate kind")
    parser.add_argument("--document-type",
                        help="confirmed document type for every CDP candidate")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be promoted and write nothing")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt (non-dry-run)")
    args = parser.parse_args()

    settings = get_settings()
    conn = db.get_connection(settings)
    try:
        db.apply_migrations(conn)
        todo, needing_type = _plan(conn, args.kind, args.document_type)
        target = settings.redacted_database_url
        log.info("promote_all.start", by=args.by, kind=args.kind or "all",
                  warehouse=target, dry_run=args.dry_run,
                  candidates=len(todo), needing_document_type=needing_type)

        if not args.dry_run and not args.yes and todo:
            print(f"About to promote {len(todo)} candidate(s) into:\n"
                  f"  {target}\n"
                  "This fetches each document and records who promoted it.")
            answer = input("Type the number of candidates to continue, or "
                           "anything else to stop: ").strip()
            if answer != str(len(todo)):
                log.info("promote_all.aborted", warehouse=target)
                print("Nothing was written.")
                return

        if args.dry_run:
            for name, url in todo:
                log.info("promote_all.would_promote", kind=name, url=url, by=args.by)
            stats = {"promoted": 0, "failed": 0, "skipped": 0,
                      "needs_document_type": needing_type, "would_promote": len(todo),
                      "failures": []}
        else:
            stats = _run(conn, settings, args.by, todo, args.document_type)
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
