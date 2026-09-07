"""The in-process read cache and its wiring into the job registry.

Offline and deterministic: the LRU takes an injected clock (the same trick the
rate-limiter tests use), so TTL and eviction are exercised without a sleep, and
the registry tests run a trivial in-process job rather than the pipeline.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from pipeline.web.cache import InProcessCache, NullCache, get_cache
from pipeline.web.jobs import JobRegistry
from pipeline.web.server import _cache_ttl


def test_a_hit_returns_the_stored_value_without_recomputing():
    clock = [0.0]
    cache = InProcessCache(clock=lambda: clock[0])
    calls = []

    def compute():
        calls.append(1)
        return "v"

    assert cache.get_or_compute("k", 10, compute) == "v"   # miss -> computes
    assert cache.get_or_compute("k", 10, compute) == "v"   # hit  -> does not
    assert calls == [1]


def test_an_expired_entry_is_recomputed():
    clock = [0.0]
    cache = InProcessCache(clock=lambda: clock[0])
    calls = []

    def compute():
        calls.append(1)
        return "v"

    cache.get_or_compute("k", ttl=10, compute=compute)
    clock[0] = 10.001                                      # past the TTL
    cache.get_or_compute("k", ttl=10, compute=compute)
    assert calls == [1, 1]


def test_bumping_the_version_makes_every_entry_unreachable():
    cache = InProcessCache()
    calls = []

    def compute():
        calls.append(1)
        return "v"

    cache.get_or_compute("k", ttl=1000, compute=compute)   # cached, long TTL
    cache.bump_version()                                   # a run finished
    cache.get_or_compute("k", ttl=1000, compute=compute)   # must recompute
    assert calls == [1, 1]


def test_distinct_keys_do_not_collide():
    cache = InProcessCache()
    assert cache.get_or_compute("a", 10, lambda: "a") == "a"
    assert cache.get_or_compute("b", 10, lambda: "b") == "b"
    assert cache.get_or_compute("a", 10, lambda: "recomputed") == "a"


def test_the_lru_evicts_the_coldest_entry_past_the_cap():
    cache = InProcessCache(max_entries=2)
    cache.get_or_compute("a", 1000, lambda: "a")
    cache.get_or_compute("b", 1000, lambda: "b")
    cache.get_or_compute("c", 1000, lambda: "c")           # a is coldest -> evicted

    gone = []
    cache.get_or_compute("a", 1000, lambda: gone.append(1) or "a")
    assert gone == [1]                                     # a had been evicted


def test_using_an_entry_protects_it_from_eviction():
    cache = InProcessCache(max_entries=2)
    cache.get_or_compute("a", 1000, lambda: "a")
    cache.get_or_compute("b", 1000, lambda: "b")
    cache.get_or_compute("a", 1000, lambda: "a")           # hit: a now newest
    cache.get_or_compute("c", 1000, lambda: "c")           # evicts b, not a

    kept = []
    cache.get_or_compute("a", 1000, lambda: kept.append(1) or "a")
    assert kept == []                                      # a survived


def test_nullcache_always_computes_and_never_stores():
    cache = NullCache()
    calls = []
    for _ in range(3):
        cache.get_or_compute("k", 1000, lambda: calls.append(1) or "v")
    assert calls == [1, 1, 1]
    cache.bump_version()  # a no-op that must not raise


# --- get_or_compute_response: caching an already-encoded response ------------


def test_a_response_hit_reuses_the_encoded_bytes_without_reencoding():
    cache = InProcessCache()
    computes, encodes = [], []

    def compute():
        computes.append(1)
        return {"n": 1}

    def encode(payload):
        encodes.append(1)
        return (b"body", None)

    assert cache.get_or_compute_response("k", 10, compute, encode) == (b"body", None)
    assert cache.get_or_compute_response("k", 10, compute, encode) == (b"body", None)
    assert computes == [1]
    assert encodes == [1]  # not re-run on the hit


def test_response_cache_tracks_compute_and_serialize_time_separately():
    clock = [0.0]

    def tick(step: float):
        clock[0] += step
        return clock[0]

    cache = InProcessCache(clock=lambda: clock[0])

    def compute():
        tick(0.02)
        return "v"

    def encode(payload):
        tick(0.005)
        return (payload.encode(), None)

    cache.get_or_compute_response("k", 10, compute, encode)
    stats = cache.stats()
    assert stats["compute_seconds"] >= 0.02 - 1e-9
    assert stats["serialize_seconds"] >= 0.005 - 1e-9


def test_response_cache_hit_after_version_bump_recomputes_and_reencodes():
    cache = InProcessCache()
    calls = []

    def compute():
        calls.append("compute")
        return "v"

    def encode(payload):
        calls.append("encode")
        return (payload.encode(), None)

    cache.get_or_compute_response("k", 1000, compute, encode)
    cache.bump_version()
    cache.get_or_compute_response("k", 1000, compute, encode)
    assert calls == ["compute", "encode", "compute", "encode"]


def test_nullcache_get_or_compute_response_always_computes_and_encodes():
    cache = NullCache()
    calls = []
    for _ in range(2):
        cache.get_or_compute_response(
            "k", 1000,
            lambda: calls.append("compute") or "v",
            lambda payload: (calls.append("encode") or payload.encode(), None),
        )
    assert calls == ["compute", "encode", "compute", "encode"]


def test_stats_exposes_the_full_metric_set():
    cache = InProcessCache()
    cache.get_or_compute_response("k", 10, lambda: "v", lambda p: (p.encode(), None))
    stats = cache.stats()
    for key in ("hits", "misses", "waiters", "computes", "failures", "evictions",
                "queue_delay_seconds", "compute_seconds", "serialize_seconds"):
        assert key in stats

    assert NullCache().stats() == {"enabled": 0}


def test_get_cache_is_null_unless_enabled():
    off = SimpleNamespace(cache_enabled=False)
    assert isinstance(get_cache(off), NullCache)

    on = SimpleNamespace(cache_enabled=True, cache_max_entries=8)
    assert isinstance(get_cache(on), InProcessCache)


# --- per-route TTL ------------------------------------------------------------


def test_boundaries_gets_the_long_static_ttl():
    settings = SimpleNamespace(cache_ttl_seconds=300.0,
                                cache_static_ttl_seconds=86400.0)
    assert _cache_ttl("/api/v1/boundaries", settings) == 86400.0
    # A trailing slash names the same route.
    assert _cache_ttl("/api/v1/boundaries/", settings) == 86400.0


def test_other_routes_get_the_default_ttl():
    settings = SimpleNamespace(cache_ttl_seconds=300.0,
                                cache_static_ttl_seconds=86400.0)
    assert _cache_ttl("/api/v1/contracts", settings) == 300.0
    assert _cache_ttl("/api/v1/summary", settings) == 300.0


# --- the registry wiring ------------------------------------------------------


def _wait_until(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise AssertionError("condition not met within timeout")


def test_a_finished_run_invalidates_the_cache():
    calls = []
    registry = JobRegistry(invalidate=lambda: calls.append(1))
    job = registry.start("run", "trivial", {}, work=lambda: [], thread_names=set())
    _wait_until(lambda: job.state == "finished")
    assert calls == [1]


def test_a_failed_run_does_not_invalidate():
    """A run that changed nothing has nothing to invalidate for, and the cache
    stays warm rather than being dropped by a run that never committed."""
    # The failing job logs its traceback. Route logging to the tmp file the
    # autouse fixture points at, as the rest of the suite does, so the log does
    # not fall through to a raw console writer -- otherwise a Windows dev
    # console (cp1252) raises mid-emit on the rich traceback.
    from pipeline import logging_conf

    logging_conf.configure_logging()

    calls = []
    registry = JobRegistry(invalidate=lambda: calls.append(1))

    def boom():
        raise RuntimeError("collection failed")

    job = registry.start("run", "doomed", {}, work=boom, thread_names=set())
    _wait_until(lambda: job.finished_at is not None)
    assert job.state == "failed"
    assert calls == []


def test_a_registry_without_a_callback_still_runs():
    """The default construction -- no cache wired -- must be unaffected."""
    registry = JobRegistry()
    job = registry.start("run", "trivial", {}, work=lambda: [], thread_names=set())
    _wait_until(lambda: job.state == "finished")
    assert job.state == "finished"
