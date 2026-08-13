"""`run all` must order modules by what they read, not alphabetically.

Alphabetical order silently produced a worse run in two specific ways, both
observed live:

  * m04_companies ran before m05_cqc, so it never saw the company numbers CQC
    publishes and left every name match unconfirmed.
  * m09/m10 ran before m15_foi, so they saw one authority website instead of
    the 315 mySociety publish.

Neither failed. Both just quietly produced less.
"""
from __future__ import annotations

import re

import pytest

from pipeline.registry import (
    MODULE_REGISTRY,
    DependencyCycleError,
    ModuleMeta,
    discover_modules,
    missing_dependencies,
    module_meta,
    resolve_run_order,
)

# Real pipeline modules follow the mNN_name convention; test-only modules
# registered by other test files do not and must not affect these assertions.
_REAL_MODULE_RE = re.compile(r"^m\d{2}_[a-z_]+$")


@pytest.fixture(scope="module", autouse=True)
def _discovered():
    discover_modules()


def _position(order: list[str], name: str) -> int:
    return order.index(name)


# --- the orderings that motivated this ------------------------------------------

def test_geography_runs_before_every_other_pipeline_module():
    """Everything joins to the authorities table.

    Asserted as "before all others" rather than "position 0", because
    test_cli.py registers fake modules to exercise the CLI's commit path and
    those sort ahead of m00 alphabetically. Only real mNN_ modules matter here.
    """
    order = [n for n in resolve_run_order() if _REAL_MODULE_RE.match(n)]
    assert order[0] == "m00_geography"


def test_companies_runs_after_the_modules_that_publish_company_numbers():
    order = resolve_run_order()
    assert _position(order, "m04_companies") > _position(order, "m03_charity_finance")
    assert _position(order, "m04_companies") > _position(order, "m05_cqc")


def test_discovery_modules_run_after_the_website_register():
    order = resolve_run_order()
    for module in ("m09_cdp_documents", "m10_committee_papers"):
        assert _position(order, module) > _position(order, "m15_foi")


def test_annual_reports_run_after_the_module_that_archives_the_pdfs():
    order = resolve_run_order()
    assert _position(order, "m14_annual_reports") > _position(order, "m03_charity_finance")


def test_alphabetical_order_would_break_these():
    """Documents why the sort exists: plain alphabetical violates both."""
    alphabetical = sorted(MODULE_REGISTRY)
    assert alphabetical.index("m04_companies") < alphabetical.index("m05_cqc")
    assert alphabetical.index("m09_cdp_documents") < alphabetical.index("m15_foi")


# --- ordering properties ------------------------------------------------------------

def test_every_module_appears_exactly_once():
    order = resolve_run_order()
    assert len(order) == len(MODULE_REGISTRY)
    assert len(set(order)) == len(order)


def test_every_dependency_precedes_its_dependent():
    order = resolve_run_order()
    for name in order:
        for dependency in module_meta(name).depends_on:
            if dependency in order:
                assert _position(order, dependency) < _position(order, name), \
                    f"{name} runs before its dependency {dependency}"


def test_order_is_deterministic():
    """Two runs of the same checkout must do the same work in the same
    sequence, or comparing two logs means nothing.
    """
    assert resolve_run_order() == resolve_run_order()


def test_subset_runs_only_what_was_asked_for():
    """Asking for a subset must not silently pull in dependencies."""
    order = resolve_run_order(["m04_companies", "m00_geography"])
    assert set(order) == {"m04_companies", "m00_geography"}
    assert order[0] == "m00_geography"


def test_subset_still_orders_the_members_it_does_contain():
    order = resolve_run_order(["m09_cdp_documents", "m15_foi"])
    assert order == ["m15_foi", "m09_cdp_documents"]


# --- cycles and reporting ------------------------------------------------------------

def test_a_dependency_cycle_raises_rather_than_picking_an_order(monkeypatch):
    from pipeline import registry

    monkeypatch.setitem(registry.MODULE_META, "a", ModuleMeta(name="a", depends_on=("b",)))
    monkeypatch.setitem(registry.MODULE_META, "b", ModuleMeta(name="b", depends_on=("a",)))
    with pytest.raises(DependencyCycleError):
        resolve_run_order(["a", "b"])


def test_missing_dependencies_are_reportable():
    """A single-module run should be able to say what it is working without."""
    absent = missing_dependencies(["m04_companies"])
    assert absent["m04_companies"] == ["m03_charity_finance", "m05_cqc"]


def test_missing_dependencies_empty_for_a_complete_selection():
    assert missing_dependencies(resolve_run_order()) == {}


def test_every_declared_dependency_is_a_real_module():
    for name in MODULE_REGISTRY:
        for dependency in module_meta(name).depends_on:
            assert dependency in MODULE_REGISTRY, \
                f"{name} depends on {dependency}, which is not registered"


def test_modules_with_dependencies_explain_them():
    """A bare ordering constraint is not much use to whoever reads the run."""
    for name in MODULE_REGISTRY:
        meta = module_meta(name)
        if meta.depends_on:
            assert meta.depends_note.strip(), f"{name} declares dependencies with no explanation"
