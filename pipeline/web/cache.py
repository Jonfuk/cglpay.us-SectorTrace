"""An in-process read cache for the public API's derived responses.

Optional and in-process by deliberate choice (CLAUDE.md settled decision 6):
no external store, nothing to run, nothing to unplug. It is a pure accelerator
-- every entry is recomputable from the warehouse, so a cold cache, a warm
cache and a disabled cache all return identical bytes. `NullCache` is that last
case made explicit, and is the default: turning the cache on is opt-in
(`CACHE_ENABLED`), for the same reason the rate limiter is (settled decision 8)
-- a mechanism that changes what the server returns should be a reviewable
setting, not an accident of what happened to be installed.

Invalidation is by data version, not by key. The warehouse only changes when a
pipeline run commits -- rare and coarse. Rather than track which query each
write touches, every cached response is stamped with a global version token,
and a completed run bumps it (`bump_version`, wired from the job registry).
Every prior key becomes unreachable in one integer increment and ages out of
the LRU on its own. The per-entry TTL is only a backstop for anything that
mutates the warehouse without going through that path.

Only the public read path (`/api/v1/*`) is cached, and only responses that
have already been through `guard_columns()` in `public_queries` -- nothing
keyed off a `restricted_` table ever reaches here (settled decision 3).

This is the same design the optional Valkey backend would take: the protocol
below, `get_or_compute` and a version token, with the state in a network store
instead of a local dict. A `ValkeyCache` implementing `Cache` would swap in
without a caller learning which it got.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable, Protocol, TypeVar

import structlog

log = structlog.get_logger()

T = TypeVar("T")


class Cache(Protocol):
    """The seam. Everything talks to this, so an in-process LRU today and a
    shared store later swap without a call site changing."""

    def get_or_compute(self, key: str, ttl: float, compute: Callable[[], T]) -> T:
        ...

    def bump_version(self) -> None:
        ...


class NullCache:
    """The disabled case, made explicit. Every call recomputes -- which is what
    guarantees the cache can only ever change the time to an answer, never the
    answer. This is the default, and what the offline suite runs against unless
    a test asks for the real one."""

    def get_or_compute(self, key: str, ttl: float, compute: Callable[[], T]) -> T:
        return compute()

    def bump_version(self) -> None:
        pass


class InProcessCache:
    """A bounded, thread-safe, TTL'd LRU shared by every request thread.

    `ThreadingHTTPServer` runs one thread per connection and they all share one
    instance (see `server.build_server`), exactly as the rate limiter does, so
    every path here holds `_lock`. Kept small and synchronous on purpose: the
    win is skipping a multi-table aggregate over ~100k rows, which dwarfs any
    contention on an OrderedDict.
    """

    def __init__(self, *, max_entries: int = 512,
                 clock: Callable[[], float] = time.monotonic) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max = max_entries
        self._clock = clock
        self._lock = threading.Lock()
        self._version = 0
        # versioned key -> (value, expiry). OrderedDict gives the LRU ordering:
        # move_to_end on use, popitem(last=False) drops the coldest.
        self._store: "OrderedDict[str, tuple[object, float]]" = OrderedDict()

    def get_or_compute(self, key: str, ttl: float, compute: Callable[[], T]) -> T:
        now = self._clock()
        with self._lock:
            version = self._version
            vkey = f"{version}:{key}"
            hit = self._store.get(vkey)
            if hit is not None and hit[1] > now:
                self._store.move_to_end(vkey)
                return hit[0]  # type: ignore[return-value]
            # Present-but-expired is dropped here and rewritten below.
            self._store.pop(vkey, None)

        # Compute OUTSIDE the lock: the query can take hundreds of milliseconds
        # and must not block every other request thread while it runs. The cost
        # is that two threads missing the same key at once both compute it -- a
        # rare, bounded waste this version accepts rather than adding per-key
        # locking. Both write the same value, so the result stays correct.
        value = compute()

        with self._lock:
            # Only store if the version has not moved under us. If a run
            # finished during the compute, this response is already stale and
            # belongs to no reader -- dropping it is cheaper than serving it,
            # and keeps a slow compute from resurrecting a version everyone
            # else has moved past.
            if version == self._version:
                self._store[vkey] = (value, self._clock() + ttl)
                self._store.move_to_end(vkey)
                while len(self._store) > self._max:
                    self._store.popitem(last=False)
        return value

    def bump_version(self) -> None:
        """A pipeline write happened: make every cached response unreachable.

        Incrementing the version rather than clearing the dict means an
        in-flight `get_or_compute` on the old version cannot write into the new
        one (see the guard above), and the orphaned entries evict themselves as
        the LRU fills. One integer under the lock.
        """
        with self._lock:
            self._version += 1
        log.info("web.cache_invalidated")


def get_cache(settings) -> Cache:
    """The configured cache, or the null one.

    Byte-identical to the pre-cache server unless `CACHE_ENABLED` is set, so a
    checkout, the offline suite and a LAN-only run behave exactly as they did
    before this module existed. `getattr` with defaults so a Settings object
    predating these fields (or a test double) still works.
    """
    if getattr(settings, "cache_enabled", False):
        log.info("web.cache_enabled", backend="in_process")
        return InProcessCache(max_entries=getattr(settings, "cache_max_entries", 512))
    return NullCache()
