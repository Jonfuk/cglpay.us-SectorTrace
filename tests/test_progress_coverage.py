"""Every module must report progress.

The original failure was not that the display was broken — it worked
perfectly for the three modules that used it. It was that nobody noticed the
other thirteen reported nothing, so `run all` showed a blank screen for its
entire first wave. Nothing in the test suite could have caught that, because
every test used the instrumented modules or stubs.

This is that missing check: a new module that never calls ctx.track() fails
here, offline, rather than on someone's four-hour run.
"""
from __future__ import annotations

import inspect
import re

import pytest

from pipeline.registry import MODULE_REGISTRY, discover_modules

_REAL_MODULE_RE = re.compile(r"^m\d{2}_[a-z_]+$")


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    discover_modules()


def _real_modules() -> list[str]:
    return sorted(n for n in MODULE_REGISTRY if _REAL_MODULE_RE.match(n))


def test_every_module_reports_progress():
    silent = [name for name in _real_modules()
              if "ctx.track(" not in inspect.getsource(MODULE_REGISTRY[name])]
    assert silent == [], (
        f"these modules report no progress and will show only a pulsing bar: {silent}")


def test_all_twenty_modules_are_covered():
    """A sanity check on the check: if discovery broke, the assertion above
    would pass vacuously over an empty list.
    """
    assert len(_real_modules()) == 23


@pytest.mark.parametrize("name", [
    "m00_geography", "m01_procurement", "m02_tribunals", "m03_charity_finance",
    "m04_companies", "m05_cqc", "m06_workforce_census", "m07_ndtms",
    "m08_pfd_reports", "m09_cdp_documents", "m10_committee_papers",
    "m11_public_health_grant", "m12_fingertips", "m13_la_budgets",
    "m14_annual_reports", "m15_foi", "m16_nhs_jobs",
    "m17_statutory_pay_rates", "m18_living_wage", "m19_data_gov_uk", "m20_gender_pay_gap", "m21_ons_ashe", "m22_provider_pay_pages",
])
def test_the_tracked_loop_carries_a_label(name):
    """A bar labelled with the module name twice tells a reader nothing about
    what is being counted.
    """
    source = inspect.getsource(MODULE_REGISTRY[name])
    labels = re.findall(r"ctx\.track\([^,]+,\s*\"([^\"]+)\"", source)
    assert labels, f"{name} calls ctx.track without a label"
    for label in labels:
        assert label.strip(), f"{name} has an empty progress label"
        assert label.lower() != name, f"{name} labels its bar with its own name"


def test_progress_never_changes_what_a_module_collects():
    """ctx.track is a pass-through. If it ever filtered, sliced or reordered,
    a display setting would change the evidence — which is the one thing this
    layer must never do.
    """
    from pipeline.console import NULL_REPORTER, ProgressReporter, progress

    items = [{"a": 1}, {"a": 2}, {"a": 3}]
    assert list(NULL_REPORTER.track(items, "x")) == items

    with progress() as bar:
        assert list(ProgressReporter(bar).track(items, "x")) == items


# --- the decorator is on the right function -------------------------------------------

@pytest.mark.parametrize("name", [
    "m00_geography", "m01_procurement", "m02_tribunals", "m03_charity_finance",
    "m04_companies", "m05_cqc", "m06_workforce_census", "m07_ndtms",
    "m08_pfd_reports", "m09_cdp_documents", "m10_committee_papers",
    "m11_public_health_grant", "m12_fingertips", "m13_la_budgets",
    "m14_annual_reports", "m15_foi", "m16_nhs_jobs",
    "m17_statutory_pay_rates", "m18_living_wage", "m19_data_gov_uk", "m20_gender_pay_gap", "m21_ons_ashe", "m22_provider_pay_pages",
])
def test_each_module_registers_its_run_function(name):
    """m15_foi was registered to crawl_disclosure_log(profile, client).

    A helper had been inserted between @register_module and `run`, so the
    decorator landed on the helper. `run m15_foi` would have called it with a
    ModuleContext and died on the missing second argument — a module broken in
    production that every existing test missed, because they all call
    foi.run(...) directly rather than through the registry.
    """
    assert MODULE_REGISTRY[name].__name__ == "run", (
        f"{name} is registered to {MODULE_REGISTRY[name].__name__!r}, not run() — "
        "check whether a helper was inserted between the decorator and run")


@pytest.mark.parametrize("name", [
    "m00_geography", "m01_procurement", "m02_tribunals", "m03_charity_finance",
    "m04_companies", "m05_cqc", "m06_workforce_census", "m07_ndtms",
    "m08_pfd_reports", "m09_cdp_documents", "m10_committee_papers",
    "m11_public_health_grant", "m12_fingertips", "m13_la_budgets",
    "m14_annual_reports", "m15_foi", "m16_nhs_jobs",
    "m17_statutory_pay_rates", "m18_living_wage", "m19_data_gov_uk", "m20_gender_pay_gap", "m21_ons_ashe", "m22_provider_pay_pages",
])
def test_each_module_takes_exactly_a_context(name):
    """The signature the CLI calls with. Catches the same class of mistake
    even if a helper is renamed to `run`.
    """
    parameters = list(inspect.signature(MODULE_REGISTRY[name]).parameters)
    assert parameters == ["ctx"], f"{name} takes {parameters}, not (ctx)"


# --- saying what is happening before the counted loop starts ---------------------------

def test_phase_is_write_only_and_safe_without_a_display():
    """Like track(): a module must behave identically whether or not anything
    is watching.
    """
    from pipeline.registry import ModuleContext

    ctx = ModuleContext(conn=None, settings=None, since=None, dry_run=False, limit=None)
    ctx.phase("doing something")   # must not raise


def test_phase_relabels_the_modules_own_bar():
    from pipeline.console import ProgressReporter, progress

    with progress() as bar:
        task = bar.add_task("m05_cqc", total=None)
        ProgressReporter(bar, parent_description="m05_cqc", task_id=task).phase(
            "paging the provider index")
        labels = [t.description for t in bar.tasks]
        # ASCII separator: the console is reconfigured to UTF-8, but a middle
        # dot is not worth depending on that holding.
        assert "m05_cqc - paging the provider index" in labels


def test_the_slowest_modules_say_what_they_are_doing():
    """A module whose counted loop starts a minute in showed a bare "0/?"
    until then — the same "working or stuck?" question the display exists to
    answer. These are the ones with the longest silent stretches.
    """
    import inspect

    for name in ("m00_geography", "m02_tribunals", "m03_charity_finance",
                 "m05_cqc", "m06_workforce_census", "m08_pfd_reports"):
        source = inspect.getsource(MODULE_REGISTRY[name])
        assert "ctx.phase(" in source, f"{name} is silent before its counted loop"
