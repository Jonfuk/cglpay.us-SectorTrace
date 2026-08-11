"""The fetch pool: faster, without giving up the things that make the output
defensible.

Four properties matter more than the speed, and each has a test that fails if
it is lost:

  * results come back in submission order, so two runs are diffable;
  * one broken council costs one council, not the crawl;
  * no SQLite connection crosses a thread boundary;
  * the per-host rate limit still holds, including when two workers collide
    on one host.
"""
from __future__ import annotations

import threading
import time

import pytest

from pipeline import parallel
from pipeline.config import Settings
from pipeline.http import HOST_CLOCK
from pipeline.parallel import Outcome, fetch_in_parallel, worker_count


def _settings(tmp_path, **overrides) -> Settings:
    base = dict(
        contact_email="t@example.com",
        database_path=tmp_path / "w.db",
        raw_archive_dir=tmp_path / "raw",
        logs_dir=tmp_path / "logs",
        default_rate_limit_seconds=0.0,
        _env_file=None,
    )
    base.update(overrides)
    return Settings(**base)


def _run(units, worker, settings, **kwargs):
    return list(fetch_in_parallel(units, worker,
                                   source_system="test_source", settings=settings, **kwargs))


# --- determinism ------------------------------------------------------------------

def test_results_come_back_in_submission_order(tmp_path):
    """Completion order depends on which council answered first. A run whose
    log order changes run to run cannot be diffed against yesterday's, which
    is the same reason resolve_run_order breaks ties alphabetically.
    """
    settings = _settings(tmp_path)

    def worker(unit, _client):
        # Deliberately finish in reverse order.
        time.sleep((10 - unit) * 0.01)
        return unit * 2

    outcomes = _run(range(10), worker, settings, max_workers=10)
    assert [o.unit for o in outcomes] == list(range(10))
    assert [o.value for o in outcomes] == [n * 2 for n in range(10)]


def test_every_unit_is_visited_exactly_once(tmp_path):
    settings = _settings(tmp_path)
    seen: list[int] = []
    lock = threading.Lock()

    def worker(unit, _client):
        with lock:
            seen.append(unit)
        return unit

    outcomes = _run(range(50), worker, settings, max_workers=8)
    assert sorted(seen) == list(range(50))
    assert len(outcomes) == 50


def test_an_empty_unit_list_does_no_work(tmp_path):
    settings = _settings(tmp_path)

    def worker(unit, _client):   # pragma: no cover - must never run
        raise AssertionError("worker ran with no units")

    assert _run([], worker, settings) == []


# --- failure isolation --------------------------------------------------------------

def test_one_failing_unit_does_not_stop_the_others(tmp_path):
    """One council with a broken TLS chain should cost one council. Before
    the pool, an unexpected exception aborted the whole module.
    """
    settings = _settings(tmp_path)

    def worker(unit, _client):
        if unit == 3:
            raise RuntimeError("that council is down")
        return unit

    outcomes = _run(range(6), worker, settings, max_workers=4)
    assert [o.ok for o in outcomes] == [True, True, True, False, True, True]
    assert [o.value for o in outcomes if o.ok] == [0, 1, 2, 4, 5]


def test_a_failure_carries_the_exception_for_the_caller_to_record(tmp_path):
    """Swallowed silently, a failed council is indistinguishable from a
    council with nothing to find.
    """
    settings = _settings(tmp_path)

    def worker(unit, _client):
        raise ValueError(f"boom {unit}")

    outcome = _run([7], worker, settings)[0]
    assert outcome.ok is False
    assert isinstance(outcome.error, ValueError)
    assert "boom 7" in str(outcome.error)
    assert outcome.value is None


def test_outcome_ok_reflects_the_error(tmp_path):
    assert Outcome(unit=1, value="x").ok is True
    assert Outcome(unit=1, error=RuntimeError()).ok is False


# --- thread safety ------------------------------------------------------------------

def test_each_thread_gets_its_own_client_and_connection(tmp_path):
    """No SQLite object may cross a thread boundary. Each client is built in
    the thread that uses it, which is why check_same_thread can stay on.
    """
    settings = _settings(tmp_path)
    clients: dict[int, int] = {}
    lock = threading.Lock()
    ready = threading.Barrier(4)

    def worker(unit, client):
        ready.wait(timeout=10)     # force all four threads to be live at once
        with lock:
            clients[threading.get_ident()] = id(client)
        return id(client)

    outcomes = _run(range(4), worker, settings, max_workers=4)
    assert len(clients) == 4, "threads shared a client"
    assert len({o.value for o in outcomes}) == 4


def test_a_workers_connection_is_usable_from_its_own_thread(tmp_path):
    """The conditional-request cache is the one bit of database work a worker
    unavoidably does; it must not raise the cross-thread ProgrammingError.
    """
    settings = _settings(tmp_path)

    def worker(unit, client):
        return client.conn.execute("SELECT 1").fetchone()[0]

    outcomes = _run(range(4), worker, settings, max_workers=4)
    assert all(o.ok for o in outcomes), [o.error for o in outcomes if not o.ok]
    assert [o.value for o in outcomes] == [1, 1, 1, 1]


def test_clients_are_closed_even_when_a_worker_raises(tmp_path):
    settings = _settings(tmp_path)
    captured: list = []

    def worker(unit, client):
        captured.append(client)
        raise RuntimeError("no")

    _run(range(3), worker, settings, max_workers=2)
    assert captured
    for client in captured:
        with pytest.raises(Exception):
            client.conn.execute("SELECT 1")


# --- the conditional-request cache ---------------------------------------------------

def test_worker_clients_defer_their_cache_writes(tmp_path):
    """The bug this exists to prevent: a worker writing the HTTP cache takes
    SQLite's single writer slot, which the main thread is holding while it
    commits an authority's evidence — so the worker blocks for the whole
    busy_timeout, over and over. Observed as a hung test suite.
    """
    settings = _settings(tmp_path)

    def worker(unit, client):
        assert client.defer_cache_writes is True
        client.pending_cache_writes.append(
            dict(url=f"https://h{unit}.example.com/x", host=f"h{unit}.example.com",
                 etag=f"etag-{unit}", last_modified=None, payload_sha256=f"sha-{unit}"))
        return unit

    assert all(o.ok for o in _run(range(4), worker, settings, max_workers=4))


def test_deferred_cache_entries_are_flushed_by_the_caller(tmp_path, settings, conn):
    """Deferring must not mean discarding: conditional requests are how
    re-runs avoid re-downloading documents that have not changed.
    """
    def worker(unit, client):
        client.pending_cache_writes.append(
            dict(url=f"https://h{unit}.example.com/x", host=f"h{unit}.example.com",
                 etag=f"etag-{unit}", last_modified=None, payload_sha256=f"sha-{unit}"))
        return unit

    list(fetch_in_parallel(range(3), worker, source_system="test_source",
                           settings=settings, max_workers=3, cache_conn=conn))

    rows = conn.execute("SELECT url, etag FROM http_cache ORDER BY url").fetchall()
    assert [r["etag"] for r in rows] == ["etag-0", "etag-1", "etag-2"]


def test_without_a_cache_connection_nothing_is_written(tmp_path, settings, conn):
    """A caller that does not pass one is opting out, not silently losing
    writes to a connection it never named.
    """
    def worker(unit, client):
        client.pending_cache_writes.append(
            dict(url="https://x.example.com/y", host="x.example.com",
                 etag="e", last_modified=None, payload_sha256="s"))
        return unit

    list(fetch_in_parallel(range(2), worker, source_system="test_source",
                           settings=settings, max_workers=2))
    assert conn.execute("SELECT COUNT(*) c FROM http_cache").fetchone()["c"] == 0


def test_a_serial_client_still_writes_its_cache_immediately(conn, settings):
    """Deferral is opt-in for the pool. Every other module writes as it goes."""
    from pipeline.http import PipelineHTTPClient

    client = PipelineHTTPClient("test_source", settings=settings, conn=conn)
    try:
        assert client.defer_cache_writes is False
    finally:
        client.close()


# --- politeness ---------------------------------------------------------------------

def test_workers_on_the_same_host_still_queue(tmp_path):
    """The property the whole design rests on. Parallelism must buy speed
    across *different* hosts only — two workers landing on one host must not
    double its request rate.
    """
    HOST_CLOCK.reset()
    settings = _settings(tmp_path, default_rate_limit_seconds=0.15)
    stamps: list[float] = []
    lock = threading.Lock()

    def worker(unit, client):
        client._rate_limiter.wait("shared.example.com")
        with lock:
            stamps.append(time.monotonic())
        return unit

    _run(range(4), worker, settings, max_workers=4)

    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(gap >= 0.15 - 0.02 for gap in gaps), \
        f"parallel workers exceeded the per-host rate: {gaps}"


def test_different_hosts_are_fetched_concurrently(tmp_path):
    """Otherwise none of this was worth doing."""
    HOST_CLOCK.reset()
    settings = _settings(tmp_path, default_rate_limit_seconds=0.3)

    def worker(unit, client):
        client._rate_limiter.wait(f"host{unit}.example.com")
        return unit

    start = time.perf_counter()
    outcomes = _run(range(8), worker, settings, max_workers=8)
    elapsed = time.perf_counter() - start

    assert all(o.ok for o in outcomes)
    assert elapsed < 0.5, "eight different hosts were fetched serially"


# --- worker count ---------------------------------------------------------------------

def test_worker_count_comes_from_settings(tmp_path):
    assert worker_count(_settings(tmp_path, max_fetch_workers=4)) == 4


def test_a_small_limit_does_not_open_a_full_pool(tmp_path):
    """`--limit 5` should not open eight connections to fetch five things."""
    assert worker_count(_settings(tmp_path, max_fetch_workers=8), limit=3) == 3
    assert worker_count(_settings(tmp_path, max_fetch_workers=8), limit=50) == 8


def test_one_worker_restores_serial_collection(tmp_path):
    assert worker_count(_settings(tmp_path, max_fetch_workers=1)) == 1

    settings = _settings(tmp_path, max_fetch_workers=1)
    live: list[int] = []
    peak = 0
    lock = threading.Lock()

    def worker(unit, _client):
        nonlocal peak
        with lock:
            live.append(unit)
            peak = max(peak, len(live))
        time.sleep(0.01)
        with lock:
            live.remove(unit)
        return unit

    _run(range(6), worker, settings, max_workers=worker_count(settings))
    assert peak == 1


def test_pool_size_never_exceeds_the_unit_count(tmp_path):
    settings = _settings(tmp_path)
    outcomes = _run([1], lambda u, c: u, settings, max_workers=16)
    assert len(outcomes) == 1


def test_the_default_is_documented_as_a_constant():
    assert parallel.DEFAULT_MAX_WORKERS >= 2
