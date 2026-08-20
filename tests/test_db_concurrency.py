"""The warehouse has to survive two writers.

Under the default rollback journal a writer takes an exclusive lock on the
whole file, and `busy_timeout` was 5 seconds. A single m13 commit writes tens
of thousands of budget rows; anything queued behind it raised "database is
locked" part-way through a crawl that had already made every request. The
requests are the expensive, impolite-to-repeat part, so failing after making
them is the worst available outcome.
"""
from __future__ import annotations

import gc
import sqlite3
import threading
import time

import pytest

from pipeline import db


def test_the_warehouse_is_in_wal_mode(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_wal_survives_reconnection(settings):
    """WAL is a property of the file, not the connection. A second connection
    must not find itself back on a rollback journal.
    """
    first = db.get_connection(settings)
    first.close()
    second = db.get_connection(settings)
    try:
        assert second.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    finally:
        second.close()


def test_busy_timeout_is_long_enough_for_a_large_commit(conn):
    """5 seconds was not. m13 writes 237,831 rows in one transaction."""
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout >= 60_000, "a queued writer will give up mid-crawl"


def test_foreign_keys_are_still_enforced(conn):
    """The pragmas are set in one place; adding two must not drop the third."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_a_reader_is_not_blocked_by_an_open_write_transaction(settings):
    """The property WAL buys: a long commit no longer stops everything else.
    Under the old rollback journal this read raised "database is locked".
    """
    writer = db.get_connection(settings)
    db.apply_migrations(writer, settings.migrations_dir)
    writer.commit()

    reader = db.get_connection(settings)
    try:
        writer.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('m00','x','y','2026-01-01')")
        # Deliberately not committed: the writer holds an open transaction.
        rows = reader.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"]
        assert rows == 0, "the reader saw uncommitted data"
        writer.commit()
        assert reader.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 1
    finally:
        reader.close()
        writer.close()


def test_a_writer_is_not_starved_by_writers_that_arrive_after_it(settings):
    """The failure that took m13 out of wave 2.

    No single holder is slow here: each busy writer holds the slot for about a
    fiftieth of a second. SQLite's busy handler is a backoff rather than a
    queue, so before the write slot was serialised in-process a latecomer
    could lose every race and fail with "database is locked" having written
    nothing — which is exactly what m13 did while m05, m07, m12 and m15 wrote
    around it.

    Measured before the fix: starved after 5.53s against a 5s timeout.
    """
    starter = db.get_connection(settings)
    db.apply_migrations(starter, settings.migrations_dir)
    starter.commit()
    starter.close()

    stop = threading.Event()
    errors: list[Exception] = []

    def busy(index: int) -> None:
        conn = db.get_connection(settings)
        conn.write_label = f"busy{index}"
        try:
            counter = 0
            while not stop.is_set():
                conn.execute(
                    "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                    "VALUES (?, 'x', ?, '2026-01-01')",
                    (f"busy{index}", f"{index}-{counter}"))
                time.sleep(0.05)      # as a module does between rows
                conn.commit()
                counter += 1
        except Exception as exc:       # pragma: no cover - the regression
            errors.append(exc)
        finally:
            conn.close()

    threads = [threading.Thread(target=busy, args=(n,), daemon=True) for n in range(4)]
    for thread in threads:
        thread.start()
    time.sleep(0.5)                    # let them get into their stride

    latecomer = db.get_connection(settings)
    latecomer.write_label = "latecomer"
    started = time.monotonic()
    try:
        latecomer.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('late', 'x', 'y', '2026-01-01')")
        latecomer.commit()
        waited = time.monotonic() - started
    finally:
        latecomer.close()
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    assert not errors, f"a busy writer failed: {errors[0]}"
    # Four writers ahead of it, each holding ~50ms: one pass through the queue.
    assert waited < 2.0, (
        f"the latecomer waited {waited:.2f}s behind four writers holding 50ms "
        "each — it is being passed over rather than queued")


def test_the_write_slot_is_released_when_a_connection_is_closed_mid_transaction(settings):
    """A module that dies holding the slot must not take the run with it."""
    first = db.get_connection(settings)
    db.apply_migrations(first, settings.migrations_dir)
    first.commit()

    first.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                   "VALUES ('m01', 'held', 'v', '2026-01-01')")
    assert db.WRITE_SLOT.holder is not None
    first.close()                       # no commit, no rollback
    assert db.WRITE_SLOT.holder is None

    second = db.get_connection(settings)
    try:
        second.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                        "VALUES ('m02', 'after', 'v', '2026-01-01')")
        second.commit()
    finally:
        second.close()


def test_the_write_slot_is_released_when_a_connection_is_only_dropped(settings):
    """Nobody closed it and nobody can: the slot still has to come back.

    `close()` is a Python-level override, and sqlite3.Connection's
    deallocation does not call it. Before `__del__` existed, a connection
    abandoned inside a write transaction held the slot for the life of the
    process — measured, with a full `gc.collect()` in between — and the next
    writer in that thread was told the *same thread* already held it on
    another connection. True, and useless: the connection it named no longer
    existed, and the error landed on the innocent writer. One such leak in
    this suite turned a single broken INSERT into 261 failures and 365
    errors, none of them near the bug.

    The second writer here is the other half of it. Every sqlite3.Connection
    is in a reference cycle with its own statement cache, so an abandoned one
    is freed by the cycle collector with its statements still unfinalized,
    and sqlite3_close_v2 defers the close — leaving the write lock on the
    file. Giving back the slot alone got this test past the queue and into
    "database is locked" for the full 120s busy timeout, which is why __del__
    closes rather than merely releasing.
    """
    def abandon():
        conn = db.get_connection(settings)
        db.apply_migrations(conn, settings.migrations_dir)
        conn.commit()
        conn.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                      "VALUES ('m01', 'abandoned', 'v', '2026-01-01')")
        assert db.WRITE_SLOT.held()
        # Returns without closing — the shape a module or a test takes when a
        # statement raises before whatever would have closed it.

    abandon()
    gc.collect()
    assert not db.WRITE_SLOT.held()

    after = db.get_connection(settings)
    try:
        after.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                       "VALUES ('m02', 'after', 'v', '2026-01-01')")
        after.commit()
        # The abandoned transaction was rolled back on the way out, so the
        # only row here is the one the surviving writer committed.
        assert [r[0] for r in after.execute("SELECT module FROM review_queue")] == ["m02"]
    finally:
        after.close()


def test_the_context_manager_releases_the_write_slot(settings):
    """`with conn:` must release, not just commit.

    sqlite3.Connection.__exit__ is written in C and commits the transaction
    without calling the Python-level commit(), so overriding commit() alone
    leaves the slot held for the life of the connection. apply_migrations uses
    a `with conn:` per migration file and every review decision uses one, so
    the first thing the CLI does on every run would have held the write slot
    for the whole run.
    """
    conn = db.get_connection(settings)
    db.apply_migrations(conn, settings.migrations_dir)
    conn.commit()
    try:
        with conn:
            conn.execute(
                "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                "VALUES ('m01', 'ctx', 'v', '2026-01-01')")
            assert db.WRITE_SLOT.holder is not None
        assert db.WRITE_SLOT.holder is None, "`with conn:` committed but kept the slot"

        # And on the failure path.
        try:
            with conn:
                conn.execute(
                    "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                    "VALUES ('m01', 'ctx', 'v2', '2026-01-01')")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert db.WRITE_SLOT.holder is None, "`with conn:` rolled back but kept the slot"
    finally:
        conn.close()


def test_migrations_do_not_leave_the_write_slot_held(settings):
    """The exact sequence the CLI runs: migrate, then let a module write."""
    first = db.get_connection(settings)
    db.apply_migrations(first, settings.migrations_dir)
    assert db.WRITE_SLOT.holder is None, "applying migrations kept the write slot"

    # A module's own connection, in the same thread, as `run` does serially.
    second = db.get_connection(settings)
    try:
        second.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('m01', 'after-migrate', 'v', '2026-01-01')")
        second.commit()
    finally:
        second.close()
        first.close()


def test_two_write_connections_in_one_thread_fail_loudly(settings):
    """A thread cannot queue behind itself.

    One connection per module is the rule; a second one writing in the same
    thread would wait for a slot only the first can release. That has to be an
    error naming the thread, not a run that stops producing output and never
    ends.
    """
    first = db.get_connection(settings)
    db.apply_migrations(first, settings.migrations_dir)
    first.commit()
    second = db.get_connection(settings)
    try:
        first.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                       "VALUES ('m01', 'a', 'v', '2026-01-01')")
        with pytest.raises(sqlite3.OperationalError, match="already holds it on another"):
            second.execute(
                "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                "VALUES ('m02', 'b', 'v', '2026-01-01')")
    finally:
        second.close()
        first.rollback()
        first.close()


def test_reads_do_not_take_the_write_slot(settings):
    """WAL's whole point is that readers do not queue. Serialising them behind
    the write slot would undo it."""
    writer = db.get_connection(settings)
    db.apply_migrations(writer, settings.migrations_dir)
    writer.commit()

    writer.execute("INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                    "VALUES ('m01', 'held', 'v', '2026-01-01')")
    assert db.WRITE_SLOT.holder is not None       # a write transaction is open

    reader = db.get_connection(settings)
    try:
        # Would block forever if a SELECT queued for the write slot.
        reader.execute("SELECT COUNT(*) FROM review_queue").fetchone()
    finally:
        reader.close()
        writer.rollback()
        writer.close()


@pytest.mark.parametrize("sql, expected", [
    ("SELECT 1", False),
    ("  select * from authorities", False),
    ("PRAGMA journal_mode", False),
    ("EXPLAIN QUERY PLAN SELECT 1", False),
    ("WITH x AS (SELECT 1) SELECT * FROM x", False),
    ("INSERT INTO t VALUES (1)", True),
    ("update t set a = 1", True),
    ("DELETE FROM t", True),
    ("CREATE TABLE t (a)", True),
    ("WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", True),
    ("-- a comment first\nSELECT 1", True),     # unrecognised: treated as a write
])
def test_statement_classification(sql, expected):
    """Anything unrecognised must be treated as a write. Over-acquiring costs
    concurrency; under-acquiring costs the guarantee."""
    assert db._is_write(sql) is expected


def test_a_second_writer_waits_rather_than_failing(settings):
    """Two writers must serialise, not error. The one that has already spent
    two seconds per request getting its data must not lose it to a lock.
    """
    holder = db.get_connection(settings)
    db.apply_migrations(holder, settings.migrations_dir)
    holder.commit()

    outcome: dict[str, object] = {}
    attempted = threading.Event()

    def queued_writer():
        # Created inside this thread: the point under test is two independent
        # writers, not one connection used from two places.
        second = db.get_connection(settings)
        try:
            attempted.set()
            second.execute(
                "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
                "VALUES ('m02','queued','v','2026-01-01')")
            second.commit()
            outcome["ok"] = True
        except sqlite3.OperationalError as exc:   # pragma: no cover - the regression
            outcome["error"] = exc
        finally:
            second.close()

    try:
        # Open a write transaction and leave it open, so the second writer
        # arrives to a locked database.
        holder.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES ('m01','held','v','2026-01-01')")

        thread = threading.Thread(target=queued_writer)
        thread.start()
        assert attempted.wait(timeout=5)
        time.sleep(0.3)     # long enough for it to be blocked on the lock
        assert "ok" not in outcome, "the second writer was never actually blocked"

        holder.commit()     # release
        thread.join(timeout=30)

        assert "error" not in outcome, \
            f"second writer failed instead of waiting: {outcome.get('error')}"
        assert outcome.get("ok") is True
        assert holder.execute(
            "SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 2
    finally:
        holder.close()


def test_many_connections_can_open_a_fresh_warehouse_at_once(settings):
    """The fetch pool opens one connection per worker thread.

    Changing journal_mode takes an exclusive lock and returns SQLITE_BUSY
    *without consulting the busy handler*, so issuing the WAL pragma
    unconditionally made eight threads race and two lose. Reading the mode
    first is lock-free, and the write only ever happens once in the file's
    life.
    """
    # The real sequence: the CLI opens the module's connection first, so the
    # file is already WAL by the time any worker starts. SQLite cannot flip an
    # already-open database to WAL, so this ordering is not incidental.
    module_conn = db.get_connection(settings)
    assert module_conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    errors: list[Exception] = []
    modes: list[str] = []
    lock = threading.Lock()
    ready = threading.Barrier(8)

    def open_one():
        try:
            ready.wait(timeout=10)
            conn = db.get_connection(settings, check_same_thread=False)
            with lock:
                modes.append(conn.execute("PRAGMA journal_mode").fetchone()[0].lower())
            conn.close()
        except Exception as exc:      # pragma: no cover - the regression
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=open_one) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    module_conn.close()

    assert not errors, f"opening connections concurrently failed: {errors}"
    assert modes == ["wal"] * 8


def test_concurrent_opens_of_a_brand_new_file_never_raise(settings):
    """Belt and braces for the case the pool should never hit — no connection
    open yet, eight arriving together. SQLite may refuse to flip the mode
    while others hold the file open, and that is its right; what it must not
    do is fail the open. The mode is reported, not asserted.
    """
    errors: list[Exception] = []
    lock = threading.Lock()
    ready = threading.Barrier(8)

    def open_one():
        try:
            ready.wait(timeout=10)
            db.get_connection(settings, check_same_thread=False).close()
        except Exception as exc:      # pragma: no cover - the regression
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=open_one) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert not errors, f"opening connections concurrently failed: {errors}"


# --- a whole wave of writers, which is what `run all --jobs N` actually is -------
#
# Everything above tests TWO writers, and two writers were always fine. The
# failure was thirteen. A `run all --jobs 4` reported
# "OperationalError: database is locked" against twelve of seventeen modules,
# each after almost exactly BUSY_TIMEOUT_MS, having made no requests at all.
#
# The cause was not the timeout being short. Every module opened a write
# transaction in its first milliseconds — providers.seed_providers writes
# reference rows — and Python's sqlite3 holds that transaction until commit.
# One module won the single write slot and kept it across all of its HTTP
# work; the rest sat on the busy handler until it expired. SQLite's busy
# handler is a backoff, not a fair queue, so the losers do not take turns.

def _module_shaped_writer(settings, name: str, hold_seconds: float, seed_commits: bool):
    """One module: seed the provider tables, do some 'fetching', then write."""
    from pipeline import providers

    conn = db.get_connection(settings)
    try:
        providers.seed_providers(conn, commit=seed_commits)
        time.sleep(hold_seconds)          # stands in for rate-limited HTTP
        conn.execute(
            "INSERT INTO review_queue (module, item_type, raw_value, created_at) "
            "VALUES (?,?,?,?) ON CONFLICT DO NOTHING",
            (name, "x", name, "2026-01-01"))
        conn.commit()
        return None
    except sqlite3.OperationalError as exc:
        return exc
    finally:
        conn.close()


def _run_a_wave(settings, seed_commits: bool, width: int = 12):
    from concurrent.futures import ThreadPoolExecutor

    setup = db.get_connection(settings)
    db.apply_migrations(setup, settings.migrations_dir)
    setup.commit()
    setup.close()

    # One module whose own first commit is far away — m11 and m13 are shaped
    # like this — and eleven ordinary ones starting at the same moment.
    plan = [("slow", 2.5)] + [(f"m{i:02d}", 0.2) for i in range(width - 1)]
    with ThreadPoolExecutor(max_workers=width) as pool:
        futures = [pool.submit(_module_shaped_writer, settings, name, hold, seed_commits)
                    for name, hold in plan]
        return [f.result() for f in futures]


def test_seeding_providers_does_not_hold_the_write_slot(settings):
    """The regression, at the size it actually happened.

    Twelve modules starting together must all get their work written. Before
    the fix, whichever one won the write slot kept it across its fetches and
    the other eleven failed.
    """
    errors = [e for e in _run_a_wave(settings, seed_commits=True) if e is not None]
    assert errors == [], (
        f"{len(errors)} of 12 concurrent modules could not write: {errors[:2]}")


def test_the_regression_reproduces_when_the_write_slot_is_not_serialised(settings, monkeypatch):
    """A guard on the guard. If this stops failing, the test above has stopped
    proving anything and something else is protecting the run.

    This used to reproduce the starvation by leaving the provider seed
    uncommitted, and asserted that doing so still starved a wave. It no longer
    does, and that is the improvement rather than the test rotting: the write
    slot is now handed out in arrival order by a process-wide lock, so a
    module holding a transaction open makes the others *wait* instead of
    failing. Committing the seed promptly still matters — it decides how long
    they wait — but it is no longer the only thing standing between a wave and
    twelve "database is locked" errors.

    So the control now removes the protection rather than the good practice:
    with the in-process serialisation disabled, the wave falls back to
    SQLite's busy handler, and the starvation comes straight back.

    Deliberately given a busy timeout of a few seconds rather than the real
    two minutes — the point is that writers are starved, not how long they are
    willing to wait for it.
    """
    monkeypatch.setattr(
        db.WriteSerialisedConnection, "_acquire_for",
        lambda self, sql, assume_write=False: None)

    original = db.BUSY_TIMEOUT_MS
    db.BUSY_TIMEOUT_MS = 3_000
    try:
        errors = [e for e in _run_a_wave(settings, seed_commits=False) if e is not None]
    finally:
        db.BUSY_TIMEOUT_MS = original

    assert errors, (
        "a wave no longer starves anyone even with the write slot unserialised "
        "— if that is a real improvement, delete this test and say why")
    assert all("locked" in str(e) for e in errors)


def test_the_wave_survives_a_module_that_holds_its_transaction_open(settings):
    """What the serialisation buys, stated as the outcome rather than the
    mechanism: a module that writes and then goes off to fetch — m00's shape,
    and m11's before it — costs the others time and not their work.
    """
    errors = [e for e in _run_a_wave(settings, seed_commits=False) if e is not None]
    assert errors == [], (
        f"{len(errors)} of 12 modules lost their work to a wave-mate holding a "
        f"transaction open: {errors[:2]}")


def test_every_module_commits_its_provider_seed(settings):
    """The fix has to be in every module, not most of them. A module that
    seeds without committing reintroduces the stampede on its own.
    """
    import inspect
    import re as _re

    from pipeline.registry import MODULE_REGISTRY, discover_modules

    discover_modules()
    offenders = []
    for name, fn in MODULE_REGISTRY.items():
        if not _re.match(r"^m\d{2}_[a-z_]+$", name):
            continue
        source = inspect.getsource(fn)
        if "seed_providers(" not in source:
            continue
        if "commit=" not in source:
            offenders.append(name)
    assert offenders == [], (
        f"these modules seed the provider tables without committing: {offenders}")


def test_cross_thread_access_is_opt_in(settings):
    """The fetch pools need it; nothing else should get it by accident,
    because SQLite being thread-safe does not make Python's transaction state
    thread-safe.
    """
    guarded = db.get_connection(settings)
    try:
        errors: list[Exception] = []

        def touch():
            try:
                guarded.execute("SELECT 1")
            except sqlite3.ProgrammingError as exc:
                errors.append(exc)

        thread = threading.Thread(target=touch)
        thread.start()
        thread.join(timeout=5)
        assert errors, "the default connection allowed cross-thread use"
    finally:
        guarded.close()

    shared = db.get_connection(settings, check_same_thread=False)
    try:
        ok: list[int] = []

        def touch_shared():
            ok.append(shared.execute("SELECT 1").fetchone()[0])

        thread = threading.Thread(target=touch_shared)
        thread.start()
        thread.join(timeout=5)
        assert ok == [1]
    finally:
        shared.close()
