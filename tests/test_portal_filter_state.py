"""Consistent filters and URL-restored query state (BETA-072).

One typed serializer (`js/filterstate.js`) owns the shared filter keys; the
summary shows resolved-name chips, a result count and validation errors;
"Clear all" wipes the whole hash query; a hash change re-syncs state so
history and shared links restore the exact query. Behaviour is a browser
check; this holds the wiring in place.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
FILTERSTATE = PORTAL / "js" / "filterstate.js"
APP = PORTAL / "app.js"
SERVER = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "server.py"


@pytest.fixture(scope="module")
def filterstate() -> str:
    return FILTERSTATE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js() -> str:
    return APP.read_text(encoding="utf-8")


def test_the_serializer_module_exists_and_is_served(filterstate: str) -> None:
    for name in ("FILTER_SCHEMA", "parseFilters", "serializeFilters",
                 "validateFilters", "chipLabels"):
        assert f"export function {name}" in filterstate or f"export const {name}" in filterstate
    served = SERVER.read_text(encoding="utf-8")
    assert '"filterstate"' in served, "the module is not in the static whitelist"


def test_the_schema_covers_the_shared_keys(filterstate: str) -> None:
    for key in ("provider", "yearFrom", "yearTo"):
        assert f"{key}:" in filterstate


def test_page_owned_query_keys_survive_serialisation(filterstate: str) -> None:
    # serializeFilters must carry through keys it does not own (compare's
    # ons_code, contracts' q, pay's source) so one URL restores both.
    body = filterstate[filterstate.index("export function serializeFilters"):]
    assert "SHARED_PARAMS.has(key)" in body and "existing.getAll(key)" in body


def test_year_validation_bounds_and_order(filterstate: str) -> None:
    body = filterstate[filterstate.index("export function validateFilters"):]
    assert "YEAR_MIN" in body
    assert "yearFrom" in body and "yearTo" in body
    assert "after the" in body  # from > to message


def test_app_reads_state_back_on_history_navigation(app_js: str) -> None:
    # A hashchange (back/forward, edited address bar) must re-sync the shared
    # filter state, not only re-render the route.
    assert "hashchange" in app_js
    assert "readStateFromUrl(); render();" in app_js


def test_clear_all_wipes_the_whole_query_not_just_shared_keys(app_js: str) -> None:
    body = app_js[app_js.index("function clearFilters("):]
    assert "location.hash.slice(1)" in body and "`#${path}`" in body


def test_pages_report_their_result_count(app_js: str) -> None:
    assert "export function setFilterResultCount" in app_js
    for page in ("contracts.js", "providers.js", "treatment.js"):
        text = (PORTAL / "js" / "pages" / page).read_text(encoding="utf-8")
        assert "setFilterResultCount(" in text, f"{page} does not report a count"


def test_the_chip_resolves_the_provider_key_to_a_name(app_js: str) -> None:
    assert "providerNames" in app_js
    assert "providerName: providerNames.get(" in app_js
