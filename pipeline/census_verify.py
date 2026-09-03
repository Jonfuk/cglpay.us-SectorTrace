"""Checking a workforce census figure against the page it was read from.

The census half of what `pipeline/promote.py` does for candidates, and
deliberately not the same code. Migration `0033` argues the schema side of
that; the argument the code adds is about what the *act* is.

Promoting a candidate is a statement about the world — this URL is a Combating
Drugs Partnership strategy for this authority — and it is made by fetching the
document, which is why `promote()` reaches the open web. Verifying a census
metric is a statement about a parse: *this number is the number that appears on
page 21 of a PDF this pipeline already holds*. Nothing needs retrieving to
settle it, so nothing is retrieved, and this module never touches the network.

What that leaves it recording is who checked, when, against which archived
bytes, and on what note. There is no payload hash of its own because there was
no payload; `checked_against_sha256` is m06's hash of the report, copied so
that a reissued PDF makes the verification visibly stale rather than quietly
wrong. `stale()` is that query.

Two rules hold, and the database enforces both rather than trusting this file:

  * **`verified = 1` is refused without a decision row** (migration 0033), on
    UPDATE and on INSERT. The bulk `UPDATE ... WHERE census_year = ?` the old
    generated worklist printed now aborts, which is the point: it set twenty
    flags on one statement, attributed to nobody, with no record that a page
    had been read.

  * **Verified is not comparable.** Provider participation varies between
    census rounds and the reports say so themselves, so a checked figure is
    still not differenceable against the year before
    (`docs/CAVEATS.md`). Verification raises the confidence that the number was
    transcribed correctly and changes nothing else. Nothing here computes
    across years, and nothing downstream may either.

Rejection is bulk and verification is not, the same asymmetry `promote.py` has
and for the same reason: rejecting says a parse is wrong, which a person can
see from the line in front of them, and the cost of being wrong is a figure
that stays unverified. Verifying says a figure is right, one figure at a time.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone

import structlog

log = structlog.get_logger()

METRICS = "workforce_census_metrics"

# The four columns that identify a metric, in the order the primary key
# declares them.
KEY_COLUMNS = ("census_year", "metric", "workforce_segment", "raw_text")

# How long a metric key is, in hex characters. The key is a digest of the four
# key columns rather than a rowid, for the reason 0030 gives: rowids are not
# stable across a rebuild, and the identity of a census metric has to survive
# one. 16 hex characters is 64 bits over a table currently holding 68 rows;
# `resolve` still checks for a collision instead of assuming, because a silent
# collision here would attach a person's judgement to the wrong figure.
KEY_LENGTH = 16


class VerificationError(RuntimeError):
    """A census metric that cannot be decided, and why."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def metric_key(row: dict | sqlite3.Row) -> str:
    """A stable handle for one metric, for a UI and a request body to name it.

    Built from the natural key with a unit separator between parts, so that two
    different metrics cannot produce the same input by having their fields run
    together. `raw_text` is a whole line of PDF prose, which is why the handle
    exists at all: passing the key itself through a URL would work and would be
    unreadable in a log.
    """
    parts = "\x1f".join(str(row[column]) for column in KEY_COLUMNS)
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:KEY_LENGTH]


def _keyed(conn: sqlite3.Connection) -> dict[str, dict]:
    """Every metric by its key, with collisions raised rather than resolved.

    A full scan. The table holds 68 rows and gains a few dozen per census
    round, so an index on a stored digest would be a second source of truth
    bought for nothing.
    """
    out: dict[str, dict] = {}
    for row in conn.execute(f"SELECT * FROM {METRICS}"):
        record = dict(row)
        key = metric_key(record)
        if key in out:
            raise VerificationError(
                f"two census metrics share the key {key}. Widen KEY_LENGTH in "
                "pipeline/census_verify.py; do not decide either until it is "
                "widened, because a judgement would attach to whichever row "
                "was read second.")
        out[key] = record
    return out


def resolve(conn: sqlite3.Connection, key: str) -> dict:
    """The metric a key names, or a refusal."""
    found = _keyed(conn).get((key or "").strip())
    if found is None:
        raise VerificationError(
            f"no census metric with key {key!r}. Reload the worklist — a "
            "re-parse can change the line a figure was read from, which "
            "changes its key.")
    return found


def _decision_params(row: dict, decision: str, who: str,
                      note: str | None) -> tuple:
    return (row["census_year"], row["metric"], row["workforce_segment"],
             row["raw_text"], decision, who, _now(), note,
             row.get("value"), row.get("unit"), row.get("source_page"),
             row.get("source_url"), row.get("payload_sha256"))


_INSERT_DECISION = (
    "INSERT INTO census_verifications "
    "(census_year, metric, workforce_segment, raw_text, decision, "
    " decided_by, decided_at, note, checked_value, checked_unit, checked_page, "
    " checked_against_url, checked_against_sha256) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")

_WHERE_KEY = (f"WHERE {' AND '.join(f'{c} = %s' for c in KEY_COLUMNS)}")


def _key_values(row: dict) -> tuple:
    return tuple(row[column] for column in KEY_COLUMNS)


def verify(conn: sqlite3.Connection, key: str, verified_by: str,
            note: str | None = None) -> dict:
    """Record that one census figure was checked, and raise its flag.

    The decision row is written first, because the trigger on the flag looks
    for it. That ordering is the same one `promote()` uses and for the same
    reason: the audit trail is not something the caller is trusted to remember
    afterwards.
    """
    if not (verified_by or "").strip():
        raise VerificationError(
            "verifications are attributed. Say who checked this figure.")

    row = resolve(conn, key)
    if row.get("verified"):
        raise VerificationError(
            "that figure is already verified. Reset it if the check needs "
            "redoing.")
    if row.get("rejected"):
        raise VerificationError(
            "that figure was rejected as a bad parse. Reset it before "
            "verifying it.")

    who = verified_by.strip()
    decided_at = _now()
    try:
        conn.execute(_INSERT_DECISION,
                      _decision_params(row, "verified", who, note))
        conn.execute(
            f"UPDATE {METRICS} SET verified = 1, rejected = 0, verified_at = %s "
            f"{_WHERE_KEY}", (decided_at, *_key_values(row)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("census.verified", key=key, year=row["census_year"],
              metric=row["metric"], segment=row["workforce_segment"], by=who)
    return {"key": key, "decision": "verified", "decided_by": who,
             "decided_at": decided_at, "census_year": row["census_year"],
             "metric": row["metric"],
             "workforce_segment": row["workforce_segment"]}


def reject(conn: sqlite3.Connection, keys: list[str], rejected_by: str,
            note: str | None = None) -> int:
    """Record that these figures were checked and the parse is wrong.

    Bulk, unlike `verify`. A wrong parse is visible from the line beside the
    number — a percentage read off a sentence that was talking about a
    different year, say — and the cost of being wrong is a figure that stays
    unverified. Rejecting also files a `parse_failures` row, because a bad
    parse is a fact about the parser and that is where m06's other ones are:
    a rejection nobody can find from the parser's side gets rediscovered by
    the next person to read the same page.
    """
    if not (rejected_by or "").strip():
        raise VerificationError("rejections are attributed. Say who is rejecting.")
    if not keys:
        return 0

    who = rejected_by.strip()
    rows = [resolve(conn, key) for key in keys]
    decided_at = _now()
    try:
        for row in rows:
            conn.execute(_INSERT_DECISION,
                          _decision_params(row, "rejected", who, note))
            conn.execute(
                f"UPDATE {METRICS} SET rejected = 1, verified = 0, "
                f"verified_at = %s {_WHERE_KEY}",
                (decided_at, *_key_values(row)))
            _record_bad_parse(conn, row, who, note)
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    log.info("census.rejected", count=len(rows), by=who, note=note)
    return len(rows)


def _record_bad_parse(conn: sqlite3.Connection, row: dict, who: str,
                       note: str | None) -> None:
    from pipeline import db

    read_as = " ".join(str(part) for part in (row.get("value"), row.get("unit"))
                        if part not in (None, ""))
    reason = (f"rejected by {who} as a bad parse of "
               f"{row['metric']}/{row['workforce_segment']} (read as {read_as})")
    if note:
        reason = f"{reason}: {note}"
    db.record_parse_failure(
        conn, "m06_workforce_census", row["metric"], row["raw_text"], reason,
        source_url=row.get("source_url"))


def reset(conn: sqlite3.Connection, key: str) -> dict:
    """Back to unchecked. The decision rows stay.

    The same rule `promote.reset` follows: a judgement that was taken was still
    taken, and deleting the record of it to tidy the flag is how "who said
    this?" stops having an answer.

    So the surviving decision row would satisfy the trigger on its own if the
    flag were raised again by hand — which is the same property 0030 leaves for
    a reset promotion, and it is the floor rather than the record. `verify()`
    writes a fresh decision row regardless, because raising the flag a second
    time is a second judgement and the audit trail is what says who took it.
    """
    row = resolve(conn, key)
    conn.execute(
        f"UPDATE {METRICS} SET verified = 0, rejected = 0, verified_at = NULL "
        f"{_WHERE_KEY}", _key_values(row))
    conn.commit()
    log.info("census.reset", key=key, year=row["census_year"],
              metric=row["metric"])
    return {"key": key, "decision": None}


def stale(conn: sqlite3.Connection) -> list[dict]:
    """Verified figures whose source no longer reads the way it was checked.

    Two ways that happens, and neither is hypothetical:

      * **The parser changed.** `raw_text` is part of the metric's key, so a
        differently-extracted line arrives as a new unverified row — but the
        same line re-read as a different *number* updates the old row in place,
        under a verification that vouched for the old number.

      * **The publisher reissued the PDF** at the same URL. m06 rewrites the
        provenance on every row it re-reads, so the metric's `payload_sha256`
        moves and the bytes somebody checked are no longer the bytes the row
        claims to come from.

    A query, not a repair, for the reason `promotions_without_flag` is one:
    which way to settle it is a person's call. The honest answer is usually to
    reset the figure and check it again, which is what the UI offers.
    """
    rows = conn.execute(f"""
        SELECT m.census_year, m.metric, m.workforce_segment, m.raw_text,
               m.value AS value, m.unit AS unit, m.payload_sha256 AS sha256,
               v.decided_by, v.decided_at, v.checked_value, v.checked_unit,
               v.checked_against_sha256
        FROM {METRICS} m
        JOIN census_verifications v
          ON v.census_year = m.census_year
         AND v.metric = m.metric
         AND v.workforce_segment = m.workforce_segment
         AND v.raw_text = m.raw_text
         AND v.decision = 'verified'
        WHERE m.verified = 1
          AND v.id = (SELECT MAX(id) FROM census_verifications w
                       WHERE w.census_year = m.census_year
                         AND w.metric = m.metric
                         AND w.workforce_segment = m.workforce_segment
                         AND w.raw_text = m.raw_text
                         AND w.decision = 'verified')
        ORDER BY m.census_year, m.metric, m.workforce_segment""")

    out = []
    for row in rows:
        record = dict(row)
        why = []
        if record["checked_value"] is not None and record["value"] != record["checked_value"]:
            why.append(f"value now {record['value']}, checked as "
                        f"{record['checked_value']}")
        if record["checked_unit"] and record["unit"] != record["checked_unit"]:
            why.append(f"unit now {record['unit']}, checked as "
                        f"{record['checked_unit']}")
        if (record["checked_against_sha256"]
                and record["sha256"] != record["checked_against_sha256"]):
            why.append("the report has been reissued since it was checked")
        if why:
            out.append({**record, "key": metric_key(record), "why": why})
    return out


def history(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT id, census_year, metric, workforce_segment, decision, "
        "       decided_by, decided_at, note, checked_value, checked_unit, "
        "       checked_page, checked_against_sha256 "
        "FROM census_verifications ORDER BY id DESC LIMIT %s", (limit,))]
