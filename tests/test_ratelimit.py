"""The token bucket in isolation, with a fake clock so nothing here sleeps."""
from __future__ import annotations

import pytest

from pipeline.web.ratelimit import TokenBucketLimiter


class FakeClock:
    """A controllable clock: `tick(n)` advances it, `__call__` reads it."""

    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def tick(self, seconds: float) -> None:
        self._now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def test_allows_up_to_capacity_with_no_time_passing(clock):
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=1.0, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") is None


def test_the_next_one_is_throttled(clock):
    limiter = TokenBucketLimiter(capacity=3, refill_per_second=1.0, clock=clock)
    for _ in range(3):
        limiter.check("a")
    retry_after = limiter.check("a")
    assert retry_after is not None
    assert retry_after == pytest.approx(1.0, abs=1e-6)


def test_refills_over_time_and_then_allows_again(clock):
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1.0, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is not None  # bucket empty

    clock.tick(1.0)  # exactly one token's worth
    assert limiter.check("a") is None


def test_refill_never_exceeds_capacity(clock):
    limiter = TokenBucketLimiter(capacity=2, refill_per_second=1.0, clock=clock)
    limiter.check("a")  # 1 token left
    clock.tick(1000.0)  # would refill far past capacity if unbounded
    # Capacity is 2: two checks succeed, a third does not.
    assert limiter.check("a") is None
    assert limiter.check("a") is None
    assert limiter.check("a") is not None


def test_keys_are_independent(clock):
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1.0, clock=clock)
    assert limiter.check("a") is None
    assert limiter.check("a") is not None
    # A different key has never been touched — its bucket is still full.
    assert limiter.check("b") is None


def test_retry_after_reflects_the_actual_deficit(clock):
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=0.5, clock=clock)
    limiter.check("a")  # empties the bucket
    retry_after = limiter.check("a")
    # Needs a full token back at 0.5/s: 2 seconds.
    assert retry_after == pytest.approx(2.0, abs=1e-6)


def test_full_buckets_are_evicted_once_the_tracked_count_grows(clock):
    limiter = TokenBucketLimiter(capacity=1, refill_per_second=1.0, clock=clock,
                                 max_tracked_keys=5)
    for i in range(10):
        limiter.check(f"key-{i}")  # each leaves its bucket at capacity - 1, not full
    # Every key was touched once and is one token short of full, so nothing
    # is evicted yet — the sweep only drops keys sitting at a *full* bucket.
    assert len(limiter._buckets) == 10

    # Bring every existing key back to full, then push past the threshold
    # with one more distinct key to trigger the sweep.
    clock.tick(10.0)
    limiter.check("trigger")
    # "trigger" itself is not full (just consumed a token) and survives;
    # every key that had refilled to capacity is gone.
    assert len(limiter._buckets) == 1
    assert "trigger" in limiter._buckets


def test_rejects_non_positive_configuration():
    with pytest.raises(ValueError):
        TokenBucketLimiter(capacity=0, refill_per_second=1.0)
    with pytest.raises(ValueError):
        TokenBucketLimiter(capacity=1, refill_per_second=0.0)
