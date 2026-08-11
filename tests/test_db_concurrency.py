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
