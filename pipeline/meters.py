"""Bytes in and bytes out, measured from inside the pipeline.

Deliberately not psutil or a system-wide counter. Two reasons, and the second
is the important one:

  * A system-wide reading tells you what the *machine* is doing. During a
    four-hour crawl that includes a browser, a backup, whatever else — so the
    number moves for reasons that have nothing to do with this run, which is
    the opposite of a status indicator.

  * Measured here, every byte is attributable. `network` is exactly what this
    pipeline pulled from public sources, which is a politeness number as much
    as a performance one: it is the answer to "how much traffic did you send
    us?" if a source ever asks. `disk` is exactly what it wrote to the raw
    archive and the page-text cache.

Rates are computed over a short trailing window rather than as a cumulative
average. A cumulative average of a run that fetched hard for a minute and then
sat rate-limited for an hour decays towards zero and reads as "stalled" —
which is precisely the state it would be failing to distinguish.
"""
from __future__ import annotations

import threading
import time
from collections import deque


class Meter:
    """A thread-safe byte counter with a windowed rate."""

    def __init__(self, window_seconds: float = 5.0) -> None:
        self._lock = threading.Lock()
        self._window = window_seconds
        self.total = 0
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, count: int) -> None:
        if count <= 0:
            return
        now = time.monotonic()
        with self._lock:
            self.total += count
            self._samples.append((now, count))
            self._trim(now)

    def _trim(self, now: float) -> None:
        cutoff = now - self._window
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def rate(self) -> float:
        """Bytes per second over the trailing window, or 0.0 when idle."""
        now = time.monotonic()
        with self._lock:
            self._trim(now)
            if not self._samples:
                return 0.0
            moved = sum(count for _, count in self._samples)
            oldest = self._samples[0][0]
        elapsed = max(now - oldest, 1e-3)
        return moved / elapsed

    def reset(self) -> None:
        with self._lock:
            self.total = 0
            self._samples.clear()


NETWORK = Meter()
DISK = Meter()


def human_bytes(count: float) -> str:
    """Sizes a person reads at a glance. Binary units, labelled as such."""
    value = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"   # pragma: no cover - unreachable, kept explicit


def human_rate(bytes_per_second: float) -> str:
    if bytes_per_second <= 0:
        return "idle"
    return f"{human_bytes(bytes_per_second)}/s"


def compact_rate(bytes_per_second: float) -> str:
    """A rate that fits on a progress line beside everything else.

    The full form ("151.4 KiB/s") is 11 characters and, doubled for network
    and disk, pushed the progress line past 80 columns and wrapped it into an
    unreadable mess. Precision is not the point here — nobody tunes anything
    off the third significant figure of a live rate — legibility at a glance
    is. The exact totals are in the end-of-run summary.
    """
    if bytes_per_second <= 0:
        return "    idle"  # padded to the width of a rate, so the column does not jitter
    for unit, size in (("G", 1024 ** 3), ("M", 1024 ** 2), ("K", 1024)):
        if bytes_per_second >= size:
            return f"{bytes_per_second / size:5.1f}{unit}/s"
    return f"{int(bytes_per_second):5d}B/s"


def compact_total(count: float) -> str:
    """A cumulative total sized to sit next to a rate on the progress line.

    Same fixed width as compact_rate for the same reason: a column that
    changes width as the number crosses a unit boundary makes the whole line
    jitter, which is worse than the information is useful.
    """
    value = float(count)
    for unit, size in (("G", 1024 ** 3), ("M", 1024 ** 2), ("K", 1024)):
        if value >= size:
            return f"{value / size:5.1f}{unit}"
    return f"{int(value):5d}B"


def reset_all() -> None:
    NETWORK.reset()
    DISK.reset()
