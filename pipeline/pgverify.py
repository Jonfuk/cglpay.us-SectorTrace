"""Proving the PostgreSQL warehouse holds what the SQLite one does.

`pipeline/backup.py` set the rule this follows: a backup is verified before it
is called one. A migration is a copy with more ways to go wrong than
`VACUUM INTO` has — two engines, two type systems, two collations and a
network in between — so it gets checked harder, and by something that is not
the thing that wrote it.

Three levels, and the reason there are three:

**Counts** answer "did every row arrive". They cost one query per table and
they are the check that catches a load that stopped early.

**Aggregates** — per-column NULL counts, and MIN/MAX per column — answer "did
every row arrive *as itself*", cheaply, in a way that is independent of row
order. There is deliberately no SUM here: floating-point addition is not
associative, so two engines summing 477,199 doubles in different physical
orders can legitimately disagree in the last bits, and a check that needs a
tolerance to pass is a check that will one day pass something it should not.
MIN and MAX need no tolerance, and the row-by-row pass below covers what SUM
was reaching for.

**Every value** answers the same question with nothing left to infer. Both
sides are streamed in primary-key order and compared in Python, so no hashing
convention has to agree between the engines and no float is ever rendered to
text. It reads 655,000 rows twice and takes minutes; it is the check that
makes the word "equivalent" mean something, and this is a project that would
rather spend the minutes.

Then two things counts and values cannot see:

  * **The guarantees.** The triggers behind settled decision 4 ran during the
    load, and this asks their questions again as queries. A trigger that was
    somehow not firing would have let the rows in silently, and "the load
    succeeded" is precisely what that failure looks like.
  * **The sequences.** Ids are copied verbatim, so every identity sequence has
    to be pointed past them. Left at 1, the next review decision anybody makes
    fails on a duplicate key — days later, with nothing connecting it to the
    migration.
"""
from __future__ import annotations

import math
from contextlib import contextmanager, nullcontext

import structlog

from pipeline import catalog, db
from pipeline.pgload import SOURCE_ONLY_TABLES, null_key_problems

log = structlog.get_logger()

# How many differing rows to report per table before moving on. Enough to see
# whether the fault is one row or the whole table, which is the only thing the
# list is being read for; the fix is never "read all 400,000 of them".
MAX_REPORTED_DIFFERENCES = 5

# The seven refusals from migrations 0030, 0033 and 0048, re-asked as queries.
#
# Each is the trigger's own condition with `NEW.` removed. They are written
# out rather than derived from the trigger definitions on purpose: a check
# generated from the thing it is checking agrees with it by construction, and
# would have agreed just as readily with a trigger that had been dropped.
GUARANTEES: tuple[tuple[str, str], ...] = (
    ("cdp_documents",
     "SELECT COUNT(*) FROM cdp_documents d WHERE NOT EXISTS ("
     "  SELECT 1 FROM evidence_promotions p "
     "  WHERE p.target_table = 'cdp_documents' "
     "    AND p.target_key = d.authority_ons_code || '|' || d.document_url)"),
    ("committee_papers",
     "SELECT COUNT(*) FROM committee_papers c WHERE NOT EXISTS ("
     "  SELECT 1 FROM evidence_promotions p "
     "  WHERE p.target_table = 'committee_papers' "
     "    AND p.target_key = c.authority_ons_code || '|' || c.document_url)"),
    ("foi_requests",
     "SELECT COUNT(*) FROM foi_requests f WHERE NOT EXISTS ("
     "  SELECT 1 FROM evidence_promotions p "
     "  WHERE p.target_table = 'foi_requests' "
     "    AND p.target_key = f.ons_code || '|' || f.request_url)"),
    ("workforce_census_metrics",
     "SELECT COUNT(*) FROM workforce_census_metrics m "
     "WHERE m.verified = 1 AND NOT EXISTS ("
     "  SELECT 1 FROM census_verifications v "
     "  WHERE v.census_year = m.census_year AND v.metric = m.metric "
     "    AND v.workforce_segment = m.workforce_segment "
     "    AND v.raw_text = m.raw_text AND v.decision = 'verified')"),
    # Migration 0048: no decided claim without the verification that decided
    # it. The claim trigger's own condition with `NEW.` removed, like the
    # rest of this tuple.
    ("claims",
     "SELECT COUNT(*) FROM claims c WHERE c.status <> 'draft' AND NOT EXISTS ("
     "  SELECT 1 FROM claim_verifications v "
     "  WHERE v.claim_id = c.id AND v.decision = c.status)"),
)


@contextmanager
def _streamed(conn, sql: str):
    """Rows from `sql`, without materialising the result set.

    psycopg's ordinary cursor downloads every row before the first one is
    handed over, which for `la_revenue_budgets` is 477,199 rows of Python
    objects held while the same number are read off SQLite beside it. A
    server-side cursor streams instead. It needs a transaction, and the read
    connections in this codebase run in autocommit — see `pipeline/pg.py` for
    why — so one is opened explicitly when there is not one already.

    SQLite needs none of this and gets the plain path, which is also what
    makes this comparable source-to-source in the offline tests.
    """
    if db.backend_of(conn) != "postgres":
        yield conn.execute(sql)
        return

    raw = conn.raw
    with (raw.transaction() if raw.autocommit else nullcontext()):
        with raw.cursor(name="pgverify") as cursor:
            cursor.itersize = 10_000
            cursor.execute(sql)
            yield cursor


def _same(left, right) -> bool:
    """Whether two values crossed the migration unchanged.

    Exact equality, with one exception: NaN is not equal to itself, so a
    column holding one would be reported as different on every run for ever.
    A NaN that arrived as a NaN did arrive.
    """
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
    return left == right and type(left) is type(right)


def compare_counts(source, target, tables: list[str]) -> list[str]:
    problems = []
    for table in tables:
        quoted = catalog.quote(table)
        here = source.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        there = target.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
        if here != there:
            problems.append(
                f"{table}: {here:,} rows in SQLite, {there:,} in PostgreSQL "
                f"({there - here:+,})")
    return problems


def compare_aggregates(source, target, table: str) -> list[str]:
    """NULL count, minimum and maximum, per column, on both sides.

    Order-independent by construction, so it says nothing about which row went
    where and everything about whether the column as a whole survived. A
    difference in MIN or MAX on a text column is also the cheapest alarm there
    is for the collation being wrong, which is a fault that otherwise shows up
    as a portal page listing authorities in a slightly different order.
    """
    problems = []
    columns = [c["name"] for c in catalog.columns_of(source, table)]
    if not columns:
        return problems

    selects = []
    for column in columns:
        quoted = catalog.quote(column)
        selects += [f"SUM(CASE WHEN {quoted} IS NULL THEN 1 ELSE 0 END)",
                     f"MIN({quoted})", f"MAX({quoted})"]
    sql = f"SELECT {', '.join(selects)} FROM {catalog.quote(table)}"
    here = tuple(source.execute(sql).fetchone())
    there = tuple(target.execute(sql).fetchone())

    for index, column in enumerate(columns):
        # SUM over no rows is NULL on both engines; over rows it is an integer
        # here and, on PostgreSQL, a numeric that psycopg hands back as
        # Decimal. Compared as integers so the two spellings of "none of them"
        # agree — this one is about arithmetic, not about the stored type.
        nulls_here = int(here[index * 3] or 0)
        nulls_there = int(there[index * 3] or 0)
        if nulls_here != nulls_there:
            problems.append(f"{table}.{column}: nulls differ — "
                             f"SQLite {nulls_here:,}, PostgreSQL {nulls_there:,}")
        for offset, what in ((1, "minimum"), (2, "maximum")):
            a, b = here[index * 3 + offset], there[index * 3 + offset]
            if not _same(a, b):
                problems.append(f"{table}.{column}: {what} differs — "
                                 f"SQLite {a!r}, PostgreSQL {b!r}")
    return problems


def compare_rows(source, target, table: str) -> list[str]:
    """Every value of every row, in primary-key order, on both sides.

    Primary-key order is what makes the two streams comparable, and it is
    available because every table in this warehouse has one — checked, not
    assumed, below. The two engines agree on that ordering because the
    PostgreSQL database is created with a bytewise collation; if it were not,
    this is the check that would say so, in the form of two rows that are each
    present and in the wrong places.
    """
    key = catalog.primary_key(source, table)
    if not key:
        return [f"{table}: no primary key, so its rows cannot be compared in "
                 "a defined order. Compare it by hand or give it a key."]

    columns = [c["name"] for c in catalog.columns_of(source, table)]
    column_list = ", ".join(catalog.quote(c) for c in columns)
    order = ", ".join(catalog.quote(c) for c in key)
    sql = f"SELECT {column_list} FROM {catalog.quote(table)} ORDER BY {order}"
    key_positions = [columns.index(c) for c in key]

    problems: list[str] = []
    compared = 0
    with _streamed(source, sql) as here, _streamed(target, sql) as there:
        source_iter, target_iter = iter(here), iter(there)
        while True:
            a = next(source_iter, None)
            b = next(target_iter, None)
            if a is None and b is None:
                break
            if a is None or b is None:
                # Counts are compared first, so reaching here means the two
                # sides hold the same number of rows and not the same rows.
                problems.append(
                    f"{table}: the two sides run out at different points "
                    f"after {compared:,} rows")
                break
            compared += 1
            left, right = tuple(a), tuple(b)
            if left == right:
                # A C-level tuple compare, run 655,000 times, so it is the
                # fast path on purpose. It is looser than `_same` in one way —
                # `1 == 1.0` — and that gap is covered by the MIN/MAX check
                # above, which compares types as well and would report a
                # column that changed type wholesale.
                continue
            differing = [columns[i] for i in range(len(columns))
                          if not _same(left[i], right[i])]
            if not differing:
                # `==` on the tuples disagreed with `_same` column by column,
                # which is the NaN case and not a difference.
                continue
            identity = ", ".join(f"{columns[p]}={left[p]!r}"
                                  for p in key_positions)
            detail = "; ".join(
                f"{c}: {left[columns.index(c)]!r} vs {right[columns.index(c)]!r}"
                for c in differing[:3])
            problems.append(f"{table}[{identity}] differs — {detail}")
            if len(problems) >= MAX_REPORTED_DIFFERENCES:
                problems.append(
                    f"{table}: stopped after {MAX_REPORTED_DIFFERENCES} "
                    "differing rows")
                break
    return problems


def check_guarantees(target) -> list[str]:
    problems = []
    for table, sql in GUARANTEES:
        count = target.execute(sql).fetchone()[0]
        if count:
            problems.append(
                f"{table}: {count:,} row(s) exist with no decision row behind "
                "them. Settled decision 4 says nothing is promoted without a "
                "person, and these are.")
    return problems


def check_sequences(target) -> list[str]:
    """Every identity sequence points past the ids that were loaded."""
    problems = []
    rows = target.execute(
        "SELECT table_name AS tbl, column_name AS col "
        "FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND is_identity = 'YES' "
        "ORDER BY table_name, column_name").fetchall()
    for row in rows:
        table, column = row["tbl"], row["col"]
        sequence = target.execute(
            "SELECT pg_get_serial_sequence(?, ?) AS s",
            (table, column)).fetchone()["s"]
        if not sequence:
            problems.append(f"{table}.{column} is an identity column with no "
                             "sequence, which should not be possible.")
            continue
        state = target.execute(
            f"SELECT last_value, is_called FROM {sequence}").fetchone()
        next_value = state["last_value"] + (1 if state["is_called"] else 0)
        highest = target.execute(
            f"SELECT COALESCE(MAX({catalog.quote(column)}), 0) "
            f"FROM {catalog.quote(table)}").fetchone()[0]
        if next_value <= highest:
            problems.append(
                f"{table}.{column}: the sequence would next hand out "
                f"{next_value}, and {highest} is already in use. The next "
                "insert into this table fails.")
    return problems


def verify(source, target, *, deep: bool = True, tables: list[str] | None = None,
            on_table=None) -> dict:
    """Check the target against the source. Returns a report.

    Nothing raises: every check that can run does, and the report carries the
    complete list of problems. A verification that stopped at the first fault
    would need running as many times as there are faults, and each run reads
    the whole warehouse.
    """
    excluded = SOURCE_ONLY_TABLES | catalog.fts5_tables(source)
    checked = tables or sorted(
        t for t in catalog.table_names(source) if t not in excluded)

    report: dict = {"tables": len(checked), "deep": deep, "problems": [],
                     "rows": 0, "checks": {}}
    problems: list[str] = report["problems"]

    in_target = set(catalog.table_names(target))
    absent = [t for t in checked if t not in in_target]
    if absent:
        problems.append(f"the target has no table {', '.join(sorted(absent))}")
        checked = [t for t in checked if t in in_target]

    problems.extend(null_key_problems(source))
    problems.extend(compare_counts(source, target, checked))
    report["checks"]["counts"] = True

    for table in checked:
        rows = source.execute(
            f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
        report["rows"] += rows
        if on_table:
            on_table(table, rows)
        problems.extend(compare_aggregates(source, target, table))
        if deep:
            problems.extend(compare_rows(source, target, table))
    report["checks"]["aggregates"] = True
    report["checks"]["rows"] = deep

    if db.backend_of(target) == "postgres":
        problems.extend(check_guarantees(target))
        report["checks"]["guarantees"] = True
        # Sequences are read from the sequence relations themselves, and the
        # `sectortrace_reader` role holds SELECT on tables and views — not on
        # those. Rather than widen the role for a check, or turn a permission
        # error into a reported fault, a read-only connection says it did not
        # run this one: it is a question about the next write, asked from a
        # connection that cannot make one.
        if getattr(target, "readonly", False):
            report["checks"]["sequences"] = False
        else:
            problems.extend(check_sequences(target))
            report["checks"]["sequences"] = True

    report["ok"] = not problems
    log.info("pgverify.complete", ok=report["ok"], tables=report["tables"],
              rows=report["rows"], problems=len(problems), deep=deep)
    return report
