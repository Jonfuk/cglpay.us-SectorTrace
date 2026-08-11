"""The per-host rate limit has to be a promise about the host.

It used to be a property of whichever PipelineHTTPClient happened to be
talking to it. Every module builds its own client, so two clients on one host
each independently believed they were within budget. Sequentially that was
invisible; the moment anything runs in parallel it is a doubled request rate
against a source this project has told, in writing, that it sends one request
every two seconds.

There was already a smaller version of the same leak: `run all` puts m02, m07,
m11 and m13 all on www.gov.uk, and each got a fresh limiter, so a module could
fire its first request immediately after the previous module's last one.
"""
from __future__ import annotations

import threading
import time

import pytest

from pipeline.config import Settings
from pipeline.http import HOST_CLOCK, _HostClock, _RateLimiter


@pytest.fixture
def clock():
    return _HostClock()


def _settings(**overrides) -> Settings:
    return Settings(contact_email="t@example.com", _env_file=None, **overrides)


# --- the fix -------------------------------------------------------------------

def test_two_clients_on_one_host_share_the_interval():
    """The regression. Two separate limiters, one host: the second must wait
    for the first, because the limit belongs to the host.
    """
    settings = _settings(default_rate_limit_seconds=0.2)
    first, second = _RateLimiter(settings), _RateLimiter(settings)

    start = time.perf_counter()
    first.wait("shared.example.com")
    second.wait("shared.example.com")
    elapsed = time.perf_counter() - start

    assert elapsed >= 0.2 - 0.02, "a second client ignored the first client's request"


def test_different_hosts_do_not_wait_for_each_other():
    """Politeness to one source must not slow collection from another."""
    settings = _settings(default_rate_limit_seconds=0.3)
    limiter = _RateLimiter(settings)

    start = time.perf_counter()
    limiter.wait("a.example.com")
    limiter.wait("b.example.com")
    limiter.wait("c.example.com")
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1


def test_per_host_overrides_still_apply():
    """Contracts Finder gets 5s because it blocks repeat offenders for
    minutes; the shared clock must not flatten that to the default.
    """
    settings = _settings(default_rate_limit_seconds=0.0,
                          rate_limit_overrides={"strict.example.com": 0.2})
    limiter = _RateLimiter(settings)

    start = time.perf_counter()
    limiter.wait("strict.example.com")
    limiter.wait("strict.example.com")
    strict_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    limiter.wait("relaxed.example.com")
    limiter.wait("relaxed.example.com")
    relaxed_elapsed = time.perf_counter() - start

    assert strict_elapsed >= 0.2 - 0.02
    assert relaxed_elapsed < 0.1


# --- slot reservation ----------------------------------------------------------

def test_the_first_call_to_a_host_does_not_wait(clock):
    assert clock.reserve("new.example.com", 5.0) == 0.0


def test_consecutive_calls_are_spaced_by_the_interval(clock):
    clock.reserve("h.example.com", 0.2)
    waited = clock.reserve("h.example.com", 0.2)
    assert waited == pytest.approx(0.2, abs=0.05)


def test_a_sequential_caller_waits_exactly_one_interval_each_time(clock):
    """A caller that sleeps out its wait before asking again is already at
    the next slot, so each call costs one interval — not a cumulative debt.
    (The consecutive-slot behaviour only shows with concurrent callers; that
    is test_concurrent_callers_never_share_a_slot.)
    """
    interval = 0.1
    clock.reserve("q.example.com", interval)

    waits = [clock.reserve("q.example.com", interval) for _ in range(3)]
    assert all(w == pytest.approx(interval, abs=0.05) for w in waits), waits


def test_waiting_on_a_slow_host_does_not_block_a_fast_one(clock):
    """The lock is held only for the reservation, so a thread sleeping out a
    long interval must not stall an unrelated host.
    """
    started = threading.Event()
    done = threading.Event()

    def slow():
        clock.reserve("slow.example.com", 0.6)
        started.set()
        clock.reserve("slow.example.com", 0.6)   # this one sleeps
        done.set()

    thread = threading.Thread(target=slow, daemon=True)
    thread.start()
    assert started.wait(timeout=2)

    start = time.perf_counter()
    clock.reserve("fast.example.com", 0.0)
    elapsed = time.perf_counter() - start

    assert elapsed < 0.1, "a slow host blocked a request to a different host"
    assert not done.is_set(), "the slow host's wait did not actually happen"
    thread.join(timeout=3)


# --- concurrency ----------------------------------------------------------------

def test_concurrent_callers_never_share_a_slot(clock):
    """The property that matters under a thread pool: N requests to one host
    must occupy N distinct slots, not collapse into a burst.
    """
    interval = 0.05
    workers = 8
    stamps: list[float] = []
    lock = threading.Lock()
    ready = threading.Barrier(workers)

    def worker():
        ready.wait()
        clock.reserve("burst.example.com", interval)
        with lock:
            stamps.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(stamps) == workers
    stamps.sort()
    gaps = [b - a for a, b in zip(stamps, stamps[1:])]
    assert all(gap >= interval - 0.02 for gap in gaps), \
        f"requests were closer together than the interval: {gaps}"


def test_concurrent_callers_on_different_hosts_run_at_once(clock):
    """The whole point of parallelising the council-walking modules: 300
    different councils are 300 different hosts and must not queue behind each
    other.
    """
    workers = 8
    ready = threading.Barrier(workers)
    waits: list[float] = []
    lock = threading.Lock()

    def worker(index: int):
        ready.wait()
        waited = clock.reserve(f"host{index}.example.com", 2.0)
        with lock:
            waits.append(waited)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(workers)]
    start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    elapsed = time.perf_counter() - start

    assert waits == [0.0] * workers
    assert elapsed < 1.0


# --- the shared instance ---------------------------------------------------------

def test_the_process_wide_clock_is_the_one_limiters_use():
    """An injected clock is one a caller can forget to share, which is the
    bug this replaces — so the module-level instance is the only one in play.
    """
    settings = _settings(default_rate_limit_seconds=0.0)
    _RateLimiter(settings).wait("registered.example.com")
    assert "registered.example.com" in HOST_CLOCK._next_free


def test_reset_clears_every_host(clock):
    clock.reserve("a.example.com", 1.0)
    clock.reserve("b.example.com", 1.0)
    clock.reset()
    assert clock.reserve("a.example.com", 1.0) == 0.0
    assert clock.reserve("b.example.com", 1.0) == 0.0
