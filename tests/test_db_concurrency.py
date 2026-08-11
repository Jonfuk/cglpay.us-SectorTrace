"""The warehouse has to survive two writers.

Under the default rollback journal a writer takes an exclusive lock on the
whole file, and `busy_timeout` was 5 seconds. A single m13 commit writes tens
of thousands of budget rows; anything queued behind it raised "database is
locked" part-way through a crawl that had already made every request. The
requests are the expensive, impolite-to-repeat part, so failing after making
them is the worst available outcome.
"""
from __future__ import annotations

import sqlite3
import threading
import time

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


def test_the_regression_reproduces_when_the_seed_is_left_uncommitted(settings):
    """A guard on the guard. If this stops failing, the test above has stopped
    proving anything and something else is protecting the run.

    Deliberately given a busy timeout of a few seconds rather than the real
    two minutes — the point is that writers are starved, not how long they are
    willing to wait for it.
    """
    original = db.BUSY_TIMEOUT_MS
    db.BUSY_TIMEOUT_MS = 3_000
    try:
        errors = [e for e in _run_a_wave(settings, seed_commits=False) if e is not None]
    finally:
        db.BUSY_TIMEOUT_MS = original

    assert errors, (
        "holding the provider seed open across a wave no longer starves anyone — "
        "if that is a real improvement, delete this test and say why")
    assert all("locked" in str(e) for e in errors)


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
