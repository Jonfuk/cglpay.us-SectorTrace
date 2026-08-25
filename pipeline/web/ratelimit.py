"""A per-key token bucket, for throttling the public API by client IP.

The public API (`/api/v1/*`) has no authentication (settled decision 8) and,
since production is a publicly reachable host (Railway), is reachable by
anyone who finds the URL. This answers sustained abuse from one address with
`429` and `Retry-After` rather than either silence or the thing this project
has never wanted: authenticating readers to make the problem go away.

Deliberately not a dependency: `token-bucket`/`limits`/`slowapi` all exist,
but the algorithm is a dozen lines and this project's whole dependency
philosophy (`CLAUDE.md` settled decision 6) is that each entry earns its
place.
"""
from __future__ import annotations

import time
from threading import Lock


class TokenBucketLimiter:
    """Thread-safe: `ThreadingHTTPServer` runs one thread per connection, and
    every one of them shares this instance (see `server.build_server`).

    Deliberately in-memory and per-process, not shared across workers or
    persisted. A restart resets everyone's bucket to full, which is the
    right failure mode for a limiter whose job is deterring sustained abuse,
    not enforcing a precise quota.
    """

    def __init__(self, capacity: float, refill_per_second: float,
                 *, max_tracked_keys: int = 5000,
                 clock: "callable[[], float]" = time.monotonic) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self._capacity = capacity
        self._refill = refill_per_second
        self._max_tracked_keys = max_tracked_keys
        self._clock = clock
        self._lock = Lock()
        # key -> (tokens remaining, last time this key was checked)
        self._buckets: dict[str, tuple[float, float]] = {}

    def check(self, key: str) -> float | None:
        """Consume one token for `key`. Returns `None` if that is allowed, or
        the number of seconds the caller should wait before trying again.

        A key with a full bucket costs nothing to remember, so growth is
        bounded by evicting exactly those entries when the tracked count
        passes `max_tracked_keys` — the sweep only ever runs when there is
        something worth doing, and it never drops a key mid-penalty.
        """
        now = self._clock()
        with self._lock:
            if len(self._buckets) > self._max_tracked_keys:
                self._evict_full_locked(now)

            tokens, last = self._buckets.get(key, (self._capacity, now))
            tokens = min(self._capacity, tokens + (now - last) * self._refill)

            if tokens < 1.0:
                self._buckets[key] = (tokens, now)
                return (1.0 - tokens) / self._refill

            self._buckets[key] = (tokens - 1.0, now)
            return None

    def _evict_full_locked(self, now: float) -> None:
        """Drop every key that would be at a full bucket *as of `now`*.
        Caller holds `_lock`.

        Recomputes the refill for each entry rather than reading its stored
        token count, which is (almost) never exactly full — `check()`
        always writes back one token short of whatever it found, on both
        the allow and the deny path. Reading the stored value directly would
        make this a near-total no-op. A key that *would* be full by now
        carries no information a missing one would not also give —
        `check()` treats a missing key exactly like a full bucket — so
        forgetting it costs nothing and is what keeps a long-running process
        from growing one dict entry per distinct address forever.
        """
        for key in [k for k, (tokens, last) in self._buckets.items()
                    if min(self._capacity, tokens + (now - last) * self._refill)
                    >= self._capacity]:
            del self._buckets[key]
