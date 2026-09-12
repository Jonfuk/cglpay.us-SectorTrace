"""Throughput, measured inside the pipeline rather than read from the OS.

A system-wide counter tells you what the machine is doing — during a
four-hour crawl that includes a browser and whatever else, so it moves for
reasons unrelated to the run. Measured here, every byte is attributable, and
the network total is a politeness figure as much as a performance one: it is
the answer to "how much traffic did you send us?" if a source ever asks.
"""
from __future__ import annotations

import threading
import time

import pytest

from pipeline.meters import DISK, NETWORK, Meter, compact_rate, human_bytes, reset_all

pytestmark = pytest.mark.serial


def test_a_meter_accumulates_a_total():
    meter = Meter()
    meter.add(100)
    meter.add(250)
    assert meter.total == 350


def test_zero_and_negative_counts_are_ignored():
    meter = Meter()
    meter.add(0)
    meter.add(-5)
    assert meter.total == 0
    assert meter.rate() == 0.0


def test_an_idle_meter_reports_no_rate():
    assert Meter().rate() == 0.0


def test_the_rate_uses_a_trailing_window_not_a_cumulative_average():
    """A run that fetched hard for a minute then sat rate-limited for an hour
    has a cumulative average decaying towards zero — it would read as
    "stalled", which is precisely the state it should distinguish.
    """
    meter = Meter(window_seconds=0.2)
    meter.add(10_000)
    assert meter.rate() > 0

    time.sleep(0.3)
    assert meter.rate() == 0.0, "old samples still counted towards the live rate"
    assert meter.total == 10_000, "the total must survive the window expiring"


def test_the_meter_is_thread_safe():
    """Modules, fetch pools and the archive writer all add concurrently."""
    meter = Meter()
    ready = threading.Barrier(8)

    def bump():
        ready.wait(timeout=10)
        for _ in range(100):
            meter.add(10)

    threads = [threading.Thread(target=bump) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert meter.total == 8_000


def test_reset_clears_both_meters():
    NETWORK.add(1)
    DISK.add(1)
    reset_all()
    assert NETWORK.total == 0 and DISK.total == 0


# --- formatting -----------------------------------------------------------------

def test_human_bytes_labels_binary_units():
    assert human_bytes(512) == "512 B"
    assert human_bytes(2048) == "2.0 KiB"
    assert human_bytes(5 * 1024 ** 2) == "5.0 MiB"


def test_compact_rate_fits_a_progress_line():
    """The full form, doubled for network and disk, wrapped the progress line
    into an unreadable mess at 80 columns.
    """
    for value in (0, 512, 204.4 * 1024, 3.2 * 1024 ** 2, 1.5 * 1024 ** 3):
        assert len(compact_rate(value)) <= 9, compact_rate(value)


def test_every_compact_rate_is_the_same_width():
    """Otherwise the column jitters as the rate crosses a unit boundary."""
    widths = {len(compact_rate(v))
              for v in (0, 512, 204.4 * 1024, 3.2 * 1024 ** 2, 1.5 * 1024 ** 3)}
    assert len(widths) == 1, f"inconsistent widths: {widths}"


def test_an_idle_rate_says_so_rather_than_showing_zero():
    """A rate-limited crawl is waiting, not broken, and the word carries that
    where "0.0K/s" reads as a fault.
    """
    assert "idle" in compact_rate(0)


def test_a_rate_is_labelled_as_a_rate():
    """The summary shows totals in the same units; without /s a live rate
    reads as one of them.
    """
    assert compact_rate(204.4 * 1024).endswith("/s")


class _Task:
    """Stands in for a rich Task. `run_level` marks the one bar that carries
    whole-run figures; every other bar renders them empty.
    """

    def __init__(self, run_level: bool = True):
        self.fields = {"run_level": run_level} if run_level else {}


def test_the_column_is_silent_before_anything_moves():
    from pipeline.console import ThroughputColumn

    reset_all()
    assert ThroughputColumn().render(_Task()).plain == ""
    NETWORK.add(1024)
    assert "net" in ThroughputColumn().render(_Task()).plain
    reset_all()


def test_whole_run_figures_appear_only_on_the_run_level_bar():
    """Repeating them per module said the same thing several times and pushed
    the line past the terminal width.
    """
    from pipeline.console import RequestCountColumn, ThroughputColumn

    reset_all()
    NETWORK.add(4096)
    from pipeline import http
    http.REQUESTS.record("h.example.com", not_modified=False)

    assert ThroughputColumn().render(_Task(run_level=False)).plain == ""
    assert RequestCountColumn().render(_Task(run_level=False)).plain == ""
    assert "net" in ThroughputColumn().render(_Task()).plain
    assert "req" in RequestCountColumn().render(_Task()).plain

    reset_all()
    http.REQUESTS.reset()


def test_cumulative_totals_show_when_the_terminal_has_room():
    from rich.console import Console

    from pipeline import console as ui
    from pipeline.console import ThroughputColumn

    reset_all()
    NETWORK.add(5 * 1024 * 1024)
    DISK.add(3 * 1024 * 1024)
    try:
        for width, expect_totals in ((130, True), (80, False)):
            ui.reset_console()
            ui._console = Console(theme=ui.THEME, width=width, force_terminal=True)
            rendered = ThroughputColumn().render(_Task()).plain
            assert ("5.0M" in rendered) is expect_totals, (width, rendered)
            assert "net" in rendered, "rates must show at every width"
    finally:
        ui.reset_console()
        reset_all()


def test_compact_total_is_fixed_width():
    from pipeline.meters import compact_total

    widths = {len(compact_total(v))
              for v in (0, 512, 204.4 * 1024, 3.2 * 1024 ** 2, 1.5 * 1024 ** 3)}
    assert len(widths) == 1, f"inconsistent widths: {widths}"
