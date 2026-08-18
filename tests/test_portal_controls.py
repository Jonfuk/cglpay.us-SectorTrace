"""Every filter control the portal renders reaches an endpoint.

The portal's honesty rules are all about figures: no number without the caveat
that governs it. A dead control is the one failure those rules do not cover. It
produces no wrong number and no missing caveat -- the reader picks a value,
sees exactly the same figures, and has no way to tell the control was ignored.

That was live for months. `#f-region` rendered in the global filter bar, its
change handler wrote `state.region`, `filterParams()` forwarded
`provider_key`, `year_from` and `year_to`, and no page read the region at all.

So the chain is pinned here, control by control:

    a control in the filter bar
      -> the state key it declares in `data-filter`
        -> a key `filterParams()` forwards, or a page reads through getState()

Break any link and this fails. The attribute is not decoration for the test's
benefit either: `Reset` clears the controls by walking it, so a wrong key stops
reset working in the browser as well as failing here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
INDEX = PORTAL / "index.html"
APP = PORTAL / "app.js"
PAGES = sorted((PORTAL / "js" / "pages").glob("*.js"))
COMPONENTS = PORTAL / "js" / "components.js"

# A control the reader can set a value in. `<button>` is excluded: Reset is a
# control that operates on the others rather than carrying a filter of its own.
VALUE_CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*)>", re.IGNORECASE)
ATTRIBUTE = re.compile(r'\b([a-z-]+)="([^"]*)"', re.IGNORECASE)


@pytest.fixture(scope="module")
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app() -> str:
    return APP.read_text(encoding="utf-8")


def filter_bar(index: str) -> str:
    """The filter bar element, found by balancing its own divs.

    Taken from the document rather than assumed, because the point of the file
    is to check what the portal actually renders.
    """
    marker = re.search(r'<div\s+class="[^"]*\bfilterbar\b[^"]*"', index)
    assert marker, "the filter bar element is not present"
    start = marker.start()
    depth, cursor = 0, start
    for match in re.finditer(r"<div\b|</div>", index[start:]):
        depth += 1 if match.group(0) == "<div" else -1
        cursor = start + match.end()
        if depth == 0:
            return index[start:cursor]
    raise AssertionError("the filter bar element is not closed")


def controls(index: str) -> list[dict[str, str]]:
    return [dict(ATTRIBUTE.findall(attrs))
            for _tag, attrs in VALUE_CONTROL.findall(filter_bar(index))]


def state_keys(app: str) -> set[str]:
    body = re.search(r"^const state = \{(.*?)\};", app, re.M | re.S)
    assert body, "app.js no longer declares a global filter state"
    return set(re.findall(r"(\w+):", body.group(1)))


def filter_params_body(app: str) -> str:
    start = app.index("export function filterParams(")
    return app[start:app.index("\n}", start)]


# --- the chain ----------------------------------------------------------------


def test_every_control_declares_the_state_key_it_writes(index):
    """A control with no `data-filter` writes nothing, or writes something this
    file cannot follow. Either way it is the shape `#f-region` had."""
    for control in controls(index):
        assert control.get("data-filter"), (
            f"{control.get('id', control)} sets no filter. If it is meant to, "
            "give it data-filter=\"<state key>\"; if it is not, it does not "
            "belong in the filter bar.")


def test_every_control_writes_a_key_the_state_actually_holds(index, app):
    keys = state_keys(app)
    for control in controls(index):
        declared = control["data-filter"]
        assert declared in keys, (
            f"{control['id']} declares data-filter=\"{declared}\", which is not "
            f"a key of app.js's filter state ({', '.join(sorted(keys))})")


def test_every_state_key_is_read_by_something(app):
    """The assertion `#f-region` failed. `state.region` was written on every
    change and read by nothing between here and the warehouse."""
    forwarded = filter_params_body(app)
    pages = {path: path.read_text(encoding="utf-8") for path in PAGES}

    for key in state_keys(app):
        if f"s.{key}" in forwarded:
            continue
        # A page counts as a reader only if it goes through getState(). Looking
        # for `.region` anywhere in the page files instead would have passed on
        # the very control this file exists for: geography.js carries an
        # authority's `region` in a map tooltip, which has nothing to do with
        # the filter and would have been read as a consumer of it.
        readers = [path.name for path, source in pages.items()
                   if "getState(" in source and re.search(rf"\.{key}\b", source)]
        assert readers, (
            f"state.{key} is written by a control and read by nothing. Either "
            f"forward it in filterParams() or take the control out.")


def test_every_state_key_has_a_control_that_sets_it(index, app):
    """The mirror image: a filter nobody can set from the page. Harmless in
    itself and a sign the two halves have drifted."""
    declared = {control["data-filter"] for control in controls(index)}
    assert state_keys(app) == declared


# --- and no handler is left behind --------------------------------------------


def test_app_js_wires_up_only_controls_that_exist(index, app):
    """The rot deleting a control leaves: a listener bound to `null`, which
    throws during boot and takes the whole filter bar with it."""
    ids = set(re.findall(r'id="([^"]+)"', index))
    for selector in set(re.findall(r"\$\('#([\w-]+)'\)", app)):
        assert selector in ids, (
            f"app.js reaches for #{selector}, which the portal does not render")


def test_the_region_control_is_gone(index, app):
    """Named rather than left to the general rules, because it is the one this
    file was written for and re-adding it would need a consumer, not a select."""
    assert "f-region" not in index
    assert "region" not in state_keys(app)


def test_campaign_lens_menu_keeps_the_five_public_perspectives(index):
    assert 'class="lens-menu"' in index
    menu = index[index.index('class="lens-menu"'):]
    menu = menu[:menu.index('</details>')]
    for label in ("Workforce", "Public money", "Service access",
                  "Safety &amp; legal", "Accountability"):
        assert label in menu
    assert 'aria-label="Explore by campaign lens"' in menu


def test_evidence_components_keep_explicit_timing_and_briefing_contract():
    source = COMPONENTS.read_text(encoding="utf-8")
    for export in ("CAMPAIGN_LENSES", "timingBadge", "findingBlock",
                   "copyBriefingButton", "thinEvidenceControl", "evidenceMeta"):
        assert f"export {'const' if export == 'CAMPAIGN_LENSES' else 'function'} {export}" in source
    for label in ("Current extract", "Dated snapshot", "Historical", "Live"):
        assert label in source
    assert "Copy briefing bundle" in source
    assert "URL: ${url}" in source


def test_public_campaign_assets_are_self_hosted():
    css = (PORTAL / "styles.css").read_text(encoding="utf-8")
    for filename in ("archivo-narrow-500.woff2", "archivo-narrow-700.woff2"):
        assert f"/fonts/{filename}" in css
        assert (PORTAL / "fonts" / filename).exists()


def test_workbench_selection_state_has_shareable_url_contracts():
    geography = (PORTAL / "js" / "pages" / "geography.js").read_text(encoding="utf-8")
    compare = (PORTAL / "js" / "pages" / "compare.js").read_text(encoding="utf-8")
    providers = (PORTAL / "js" / "pages" / "providers.js").read_text(encoding="utf-8")
    for key in ("metric", "year", "layers", "selected"):
        assert f"params.get('{key}')" in geography
        assert f"params.set('{key}'" in geography
    assert "params.getAll('ons_code')" in compare
    assert "params.getAll('provider_key')" in compare
    assert "#/providers/${encodeURIComponent(provider.provider_key)}" in providers
