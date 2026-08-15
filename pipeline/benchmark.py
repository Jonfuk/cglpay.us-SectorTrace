"""Phase 3: what the two backends actually cost, measured before anything is
changed to make them cheaper.

The point of this file is to make Phase 4 arguable. Every optimisation in the
plan — keyset pagination, `percentile_cont`, index work, a connection pool, a
COPY staging table for m13 — is gated on evidence, and evidence means a number
recorded before the change and the same number recorded after. Without that,
"this is faster" is a memory of how the page felt.

So: no changes here, only measurements, and they are written to
`docs/benchmarks/` as JSON so a later run can be diffed against this one
rather than against a recollection.

**Both backends are asked the same questions of the same data.** That is the
whole basis of the comparison and it is only true because Phase 2 proved it:
the two warehouses hold the same 655,344 rows, verified value by value. This
module re-checks the row counts of the tables it measures before reporting,
because a benchmark comparing a full warehouse with a half-loaded one produces
numbers that look like findings.

**Percentiles, not means.** The plan asks for p50/p95/p99 and it is right to:
the interesting behaviour of a deep `OFFSET` or a full-table scan lives in the
tail, and a mean over ten runs hides exactly the case that makes an operator
reload the page. The first run of each measurement is discarded — it pays for
the page cache on one side and the plan cache on the other, and neither is
what a warm portal does.

**What is deliberately not measured here.** Ingestion wall-clock and jobs
scaling. A full collection is bounded by one request per two seconds per host,
by design and by settled decision 5, so the honest measurement needs live
sources and takes hours; and an offline version would be measuring a mocked
transport, which is measuring the mock. What *can* be measured offline is the
part PostgreSQL actually changes — how long a writer spends waiting for
another writer — and that is `write_contention` below.
"""
from __future__ import annotations

import json
import platform
import sqlite3
import statistics
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import structlog

from pipeline import catalog, db
from pipeline.config import Settings, get_settings

log = structlog.get_logger()

# Measurements per case, after the discarded warm-up. Ten is enough for a p50
# that does not move between runs and a p95 that means something; it is not
# enough for a p99 to be more than "the worst of ten", and the report says so
# rather than implying a precision it does not have.
REPETITIONS = 10

# Cases whose absolute cost is high enough that ten runs is minutes rather
# than seconds. Measured fewer times, and the count is recorded per case so a
# later comparison knows what it is comparing.
SLOW_REPETITIONS = 3


def _percentiles(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "n": len(ordered),
        "min_ms": round(ordered[0] * 1000, 2),
        "p50_ms": round(statistics.median(ordered) * 1000, 2),
        "p95_ms": round(ordered[min(int(len(ordered) * 0.95), len(ordered) - 1)] * 1000, 2),
        "p99_ms": round(ordered[min(int(len(ordered) * 0.99), len(ordered) - 1)] * 1000, 2),
        "max_ms": round(ordered[-1] * 1000, 2),
    }


def _time(call, repetitions: int) -> dict:
    """Run `call` once to warm, then `repetitions` times, timed.

    The result of the call is discarded except for its length where it has
    one, which is recorded so that a case returning nothing is visible as such
    rather than being reported as very fast.
    """
    outcome = call()
    samples = []
    for _ in range(repetitions):
        started = time.perf_counter()
        outcome = call()
        samples.append(time.perf_counter() - started)

    measured = _percentiles(samples)
    try:
        measured["rows"] = len(outcome)
    except TypeError:
        measured["rows"] = None
    return measured


# The read paths, named and called as the application calls them.
#
# Written as callables over a connection rather than as SQL strings on
# purpose: what Phase 4 will change is these functions, and a benchmark of
# hand-copied SQL would keep reporting on code that no longer runs. Each entry
# says why it is here — a case with no argument for its presence is a case
# nobody will know whether to keep.
def _read_cases() -> list[dict]:
    from pipeline.web import health, public_queries, queries

    return [
        {
            "name": "portal.summary",
            "why": "The portal's front page. Aggregates over contracts, which "
                    "is 98,636 rows and the largest table anyone reaches "
                    "through a browser.",
            "call": lambda conn: public_queries.summary(conn),
        },
        {
            "name": "portal.contracts.first_page",
            "why": "The contracts list as it first loads, ordered by "
                    "date_published — which no index covers today, and is "
                    "candidate one for Phase 4 index work.",
            "call": lambda conn: public_queries.contracts(conn, limit=50),
        },
        {
            "name": "portal.contracts.full_page",
            "why": "The same list at its cap. The plan expected the portal to "
                    "paginate with OFFSET and it does not — `contracts()` takes "
                    "a limit and no offset, and the cap is what protects it — "
                    "so the deep-OFFSET cost the keyset-pagination proposal is "
                    "aimed at lives on the admin side only, below. This is what "
                    "the portal's worst case actually is.",
            "call": lambda conn: public_queries.contracts(conn, limit=1000),
        },
        {
            "name": "portal.geography",
            "why": "The map's payload: grant totals per authority, joined "
                    "across the authority spine.",
            "call": lambda conn: public_queries.geography(conn),
        },
        {
            "name": "portal.boundaries",
            "why": "347 generalised boundary polygons. Dominated by moving "
                    "text rather than by the query, which is worth knowing "
                    "before anyone optimises the query.",
            "call": lambda conn: public_queries.boundaries(conn),
        },
        {
            "name": "portal.providers",
            "why": "Goes through v_provider_viability, the view whose bare "
                    "GROUP BY had to be restructured for PostgreSQL. If the "
                    "rewrite cost anything, it shows up here.",
            "call": lambda conn: public_queries.providers(conn),
        },
        {
            "name": "portal.pay",
            "why": "Includes _median_value, which loads every priced notice "
                    "into Python and sorts it there. percentile_cont is the "
                    "Phase 4 replacement, and this is what it has to beat.",
            "call": lambda conn: public_queries.pay(conn),
        },
        {
            "name": "portal.fingertips",
            "why": "22,667 rows behind a view, filtered per indicator.",
            "call": lambda conn: public_queries.fingertips(conn),
        },
        {
            "name": "portal.authorities",
            "why": "ORDER BY name over the authority spine — the query whose "
                    "answer changes if the collation is wrong.",
            "call": lambda conn: public_queries.authorities(conn),
        },
        {
            "name": "admin.read_table.contracts",
            "why": "The table browser on the biggest table, in primary-key "
                    "order — what replaced ORDER BY rowid.",
            "call": lambda conn: queries.read_table(conn, "contracts", limit=50),
        },
        {
            "name": "admin.read_table.budgets_deep",
            "why": "477,199 rows, paged near the end. The worst OFFSET in the "
                    "application.",
            "call": lambda conn: queries.read_table(conn, "la_revenue_budgets",
                                                     limit=50, offset=400_000),
            "slow": True,
        },
        {
            "name": "admin.read_table.search",
            "why": "LIKE with an escaped term over every column cast to text. "
                    "Case sensitivity differs between the engines and the cost "
                    "does too.",
            "call": lambda conn: queries.read_table(conn, "contracts",
                                                     search="council", limit=50),
            "slow": True,
        },
        {
            "name": "admin.review_items",
            "why": "The operator's worklist, ordered by created_at and id — "
                    "already the sort keyset pagination would use.",
            "call": lambda conn: queries.review_items(conn, limit=50),
        },
        {
            "name": "admin.review_items.deep_offset",
            "why": "The same worklist near the end of 4,822 items. This and "
                    "the budgets page below are the two numbers that decide "
                    "whether Phase 4's keyset pagination is worth building.",
            "call": lambda conn: queries.review_items(conn, status=None,
                                                       limit=50, offset=4_000),
        },
        {
            "name": "admin.list_objects",
            "why": "Sidebar. One COUNT(*) per table, 68 of them, on every "
                    "page load of the operator UI.",
            "call": lambda conn: queries.list_objects(conn),
            "slow": True,
        },
        {
            "name": "admin.health.freshness",
            "why": "Deliberately unindexed full scans of every table carrying "
                    "retrieved_at. Documented as expensive on purpose; the "
                    "question is how expensive, on each engine.",
            "call": lambda conn: health.freshness(conn),
            "slow": True,
        },
        {
            "name": "admin.overview",
            "why": "The admin landing page.",
            "call": lambda conn: queries.overview(conn),
        },
    ]


def read_latency(conn, cases=None) -> list[dict]:
    """Every read case against one connection. Failures are recorded, not
    raised: a case that cannot run on one backend is a finding, and losing the
    other fifteen measurements to it is not.
    """
    results = []
    for case in cases or _read_cases():
        repetitions = SLOW_REPETITIONS if case.get("slow") else REPETITIONS
        try:
            measured = _time(lambda: case["call"](conn), repetitions)
        except Exception as exc:                      # noqa: BLE001 - recorded
            results.append({"name": case["name"], "why": case["why"],
                             "error": f"{type(exc).__name__}: {exc}"})
            log.warning("benchmark.case_failed", case=case["name"], error=str(exc))
            continue
        results.append({"name": case["name"], "why": case["why"], **measured})
        log.info("benchmark.case", case=case["name"], p50_ms=measured["p50_ms"])
    return results


def write_throughput(conn, rows: int = 2_000) -> dict:
    """Upserts per second, and what a commit costs.

    Deliberately through `db.upsert` and committing per unit, because that is
    the discipline every module follows — a benchmark of one big transaction
    would measure something this pipeline never does.

    Writes into `parse_failures`, which is the one table with a natural key
    made entirely of strings this can generate, and cleans up after itself.
    The caller is responsible for pointing this at a warehouse it is allowed
    to write to; `benchmark()` below never points it at a real one.
    """
    module = "__benchmark__"
    started = time.perf_counter()
    commit_samples = []
    for index in range(rows):
        db.record_parse_failure(conn, module, "field", f"fragment {index}",
                                 "benchmark", f"https://example.invalid/{index}")
        commit_started = time.perf_counter()
        conn.commit()
        commit_samples.append(time.perf_counter() - commit_started)
    elapsed = time.perf_counter() - started

    conn.execute("DELETE FROM parse_failures WHERE module = ?", (module,))
    conn.commit()

    return {"rows": rows, "seconds": round(elapsed, 3),
             "rows_per_second": round(rows / elapsed, 1),
             "commit": _percentiles(commit_samples)}


def _concurrent_writers(settings: Settings, writers: int, rows_each: int) -> dict:
    """`writers` threads each committing `rows_each` rows, started together."""
    import threading

    barrier = threading.Barrier(writers)
    errors: list[str] = []
    lock = threading.Lock()

    def writer(index: int) -> None:
        conn = db.get_connection(settings, check_same_thread=False)
        try:
            barrier.wait()
            for row in range(rows_each):
                db.record_parse_failure(
                    conn, f"__contention_{index}__", "field", f"fragment {row}",
                    "benchmark", f"https://example.invalid/{index}/{row}")
                conn.commit()
        except Exception as exc:                      # noqa: BLE001 - recorded
            with lock:
                errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(writers)]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started

    cleanup = db.get_connection(settings)
    try:
        for index in range(writers):
            cleanup.execute("DELETE FROM parse_failures WHERE module = ?",
                             (f"__contention_{index}__",))
        cleanup.commit()
    finally:
        cleanup.close()

    total = writers * rows_each
    return {"writers": writers, "rows": total, "wall_seconds": round(wall, 3),
             "rows_per_second": round(total / wall, 1) if wall else None,
             "errors": errors}


def write_contention(settings: Settings, counts=(1, 2, 4, 8),
                      rows_each: int = 100) -> dict:
    """Write throughput as the number of concurrent writers rises.

    This is the measurement PostgreSQL exists to change. Under SQLite one
    writer holds the warehouse at a time and `db.WRITE_SLOT` hands the slot out
    in arrival order; under PostgreSQL there is no slot and MVCC lets writers
    interleave.

    **Scaling against one writer, not a ratio of thread lifetimes.** The first
    version of this measured `sum(per-writer elapsed) / wall clock` and read
    3.8 on both backends, which looked like a result and was an artefact: when
    writers are serialised they are still all *alive* for the whole run, each
    one waiting its turn, so that ratio approaches the writer count whether
    anything overlapped or not. It could not tell the two backends apart,
    which is the one thing it was for. Throughput at N writers over throughput
    at one cannot be fooled that way: if the slot serialises, adding writers
    buys nothing and the number stays near 1.

    The plan is explicit that none of this makes a collection faster — a
    collection waits on one request per two seconds per host. What is being
    recorded is the shape of the constraint that goes away.

    Threads, not processes, because that is what a run is: module waves are a
    ThreadPoolExecutor in one process.
    """
    measured = [_concurrent_writers(settings, count, rows_each)
                 for count in counts]
    baseline = next((m["rows_per_second"] for m in measured
                      if m["writers"] == 1), None)
    for entry in measured:
        entry["scaling_vs_one_writer"] = (
            round(entry["rows_per_second"] / baseline, 2)
            if baseline and entry["rows_per_second"] else None)
    return {"rows_each": rows_each, "by_writers": measured,
             "errors": [e for m in measured for e in m["errors"]]}


def _environment(conn, settings: Settings) -> dict:
    backend = db.backend_of(conn)
    info = {
        "backend": backend,
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "commit": _git_commit(),
    }
    # These files are committed, and this repository is public. The database
    # name and the server version are what a later comparison needs; the host
    # and the absolute path are not, and `redacted_database_url` redacts the
    # password only. A benchmark is not a reason to publish where the server
    # lives or whose home directory the warehouse is in.
    if backend == "postgres":
        info["server"] = conn.execute("SHOW server_version").fetchone()[0]
        info["target"] = conn.execute("SELECT current_database()").fetchone()[0]
    else:
        info["server"] = f"sqlite {sqlite3.sqlite_version}"
        info["target"] = settings.database_path.name
        if settings.database_path.is_file():
            info["bytes"] = settings.database_path.stat().st_size
    return info


def _git_commit() -> str | None:
    """The commit the measurement was taken at, so a benchmark file can be
    placed in the history rather than only in time."""
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 capture_output=True, text=True, timeout=5,
                                 cwd=Path(__file__).resolve().parent.parent)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def table_sizes(conn) -> dict[str, int]:
    """Row counts for the tables the read cases touch.

    Recorded with every benchmark, and the reason is that a comparison between
    two backends is only a comparison if they hold the same rows. Phase 2
    proved they do; this makes each measurement carry its own proof rather
    than inheriting the claim.
    """
    wanted = ["contracts", "la_revenue_budgets", "fingertips_la_values",
               "ndtms_la_statistics", "public_health_grants", "authorities",
               "review_queue", "providers"]
    sizes = {}
    present = set(catalog.table_names(conn))
    for table in wanted:
        if table in present:
            sizes[table] = conn.execute(
                f"SELECT COUNT(*) FROM {catalog.quote(table)}").fetchone()[0]
    return sizes


def benchmark(settings: Settings | None = None, *, reads: bool = True,
               writes: bool = True, output_dir: Path | None = None) -> dict:
    """Measure the configured backend and write the result to JSON.

    Reads run against the working warehouse, because the point is the real
    data. Writes do not: they go to a scratch database — a temporary file on
    SQLite, a temporary schema on PostgreSQL — because a benchmark that
    inserted two thousand rows into the warehouse would leave it no longer
    equal to the other one, which is the property everything here rests on.
    """
    settings = settings or get_settings()
    report: dict = {}

    conn = db.get_connection(settings)
    try:
        report["environment"] = _environment(conn, settings)
        report["tables"] = table_sizes(conn)
        if reads:
            report["reads"] = read_latency(conn)
    finally:
        conn.close()

    if writes:
        with scratch_warehouse(settings) as scratch:
            report["write_throughput"] = write_throughput(scratch.conn)
            report["write_contention"] = write_contention(scratch.settings)

    if output_dir:
        path = _write_report(report, output_dir)
        report["written_to"] = str(path)
    return report


@dataclass
class Scratch:
    """A migrated, empty warehouse the benchmark may write to."""

    settings: Settings
    conn: object


@contextmanager
def scratch_warehouse(settings: Settings):
    """One of those, on the configured backend, thrown away afterwards.

    A temporary file on SQLite; a temporary schema on PostgreSQL, because that
    server holds one database and `sectortrace_app` cannot create another. The
    settings come back with it so that `write_contention` — which opens its
    own connections, one per writer thread — reaches the same scratch
    warehouse rather than the real one.
    """
    if settings.database_backend != "postgres":
        import shutil
        import tempfile

        base = Path(tempfile.mkdtemp(prefix="sectortrace-bench-"))
        scoped = settings.model_copy(update={"database_path": base / "warehouse.db"})
        conn = db.get_connection(scoped)
        try:
            db.apply_migrations(conn, db.migrations_dir_for(scoped))
            conn.commit()
            yield Scratch(settings=scoped, conn=conn)
        finally:
            conn.close()
            shutil.rmtree(base, ignore_errors=True)
        return

    from uuid import uuid4

    from pipeline import pg

    name = f"bench_{uuid4().hex[:12]}"
    admin = pg.connect(settings.database_url,
                        application_name="sectortrace-benchmark")
    try:
        admin.execute(f"CREATE SCHEMA {catalog.quote(name)}")
        admin.commit()
        scoped = settings.model_copy(update={
            "database_url": pg.with_schema(settings.database_url, name),
            "database_ro_url": None})
        conn = db.get_connection(scoped)
        try:
            db.apply_migrations(conn, db.migrations_dir_for(scoped))
            conn.commit()
            yield Scratch(settings=scoped, conn=conn)
        finally:
            conn.close()
    finally:
        admin.execute(f"DROP SCHEMA {catalog.quote(name)} CASCADE")
        admin.commit()
        admin.close()


def _write_report(report: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = report["environment"]["backend"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{stamp}-{backend}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def compare(left: dict, right: dict) -> list[dict]:
    """Two reports, case by case.

    Ratios rather than differences, and both p50 and p95, because the two
    frequently disagree — a case can have a faster median and a worse tail,
    and only one of those is what an operator waiting for a page notices.
    """
    right_cases = {case["name"]: case for case in right.get("reads", [])}
    rows = []
    for case in left.get("reads", []):
        other = right_cases.get(case["name"])
        if not other or "p50_ms" not in case or "p50_ms" not in other:
            rows.append({"name": case["name"],
                          "left_ms": case.get("p50_ms"),
                          "right_ms": other.get("p50_ms") if other else None,
                          "note": case.get("error") or (other or {}).get("error")
                                   or "not measured on both"})
            continue
        rows.append({
            "name": case["name"],
            "left_p50_ms": case["p50_ms"], "right_p50_ms": other["p50_ms"],
            "p50_ratio": round(other["p50_ms"] / case["p50_ms"], 2) if case["p50_ms"] else None,
            "left_p95_ms": case["p95_ms"], "right_p95_ms": other["p95_ms"],
            "p95_ratio": round(other["p95_ms"] / case["p95_ms"], 2) if case["p95_ms"] else None,
            "rows": case.get("rows"),
        })
    return rows
