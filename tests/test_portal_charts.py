"""A saved chart keeps the caveat that governs it.

ECharts owns a canvas and will hand back a PNG of it. That PNG is the wrong
artefact on its own: the caption above the chart and the pinned caveat beside
it are DOM siblings, and neither survives saving the canvas. A figure arriving
somewhere without the caveat that governs it is the failure the whole portal
is built against -- the same one the print stylesheet exists for.

So the text is composed into the image. What is pinned here is that the code
does the composing and reads the caveat from the page rather than from a
copy; whether the resulting PNG is legible is a browser check, and the one
that found the ARIA problem below.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
STYLES = PORTAL / "styles.css"
PAGES = sorted((PORTAL / "js" / "pages").glob("*.js"))


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    return source[start:source.index("\n}\n", start)]


def test_every_chart_offers_to_save_itself(components):
    body = function_body(components, "export function mountChart(")
    assert "chart-save" in body
    assert "saveChartImage(" in body


def test_the_saved_image_is_composed_rather_than_the_bare_canvas(components):
    """getDataURL alone would be the chart and nothing else."""
    body = function_body(components, "async function saveChartImage(")

    assert "getDataURL" in body
    assert "drawImage" in body, "the chart should be drawn into a larger canvas"
    assert "fillText" in body, "the caption and caveat have to be drawn, not attached"
    assert "noteLines" in body, "the caveat lines never reach the canvas"


def test_the_caveat_is_read_from_the_page_beside_the_chart(components):
    """Not passed in per call site. Whatever the reader can see next to the
    figure is what goes into the file, so the two cannot drift apart."""
    body = function_body(components, "function chartContext(")

    assert ".caveat-pinned" in body
    assert "closest('.panel')" in body and "closest('.section')" in body, (
        "nearest first: a caveat inside the chart's own panel is that chart's")


def test_the_saved_file_says_where_it_came_from(components):
    body = function_body(components, "async function saveChartImage(")
    assert "location.href" in body
    assert "SectorTrace" in body


def test_no_page_rasterises_a_chart_for_itself(components):
    for path in PAGES:
        source = path.read_text(encoding="utf-8")
        assert "getDataURL" not in source, (
            f"{path.name} saves its own chart; the shared path draws the caveat in")


def test_the_image_role_is_on_the_chart_and_not_around_the_button(components):
    """Found in the browser, not here: a button inside role="img" is a button
    no screen reader announces, because an img role's children are
    presentational. The role moved onto the chart element itself."""
    body = function_body(components, "export function mountChart(")
    holder = body[body.index("const holder"):body.index("const save")]
    wrap = body[body.index("const wrap"):body.index("replace(container, wrap)")]

    assert "role: 'img'" in holder
    assert "role" not in wrap


def test_the_save_button_does_not_print():
    """It is a control. `.btn` is already dropped by the print block, which is
    why the button carries that class rather than a bespoke one."""
    styles = STYLES.read_text(encoding="utf-8")
    printed = styles[styles.index("@media print"):]
    hidden = next(line for line in printed.splitlines()
                  if "display: none !important" in line and ".btn" in line)

    assert "class: 'btn tiny chart-save'" in COMPONENTS.read_text(encoding="utf-8"), (
        "the save button should carry .btn so the print rule already covers it")
    assert ".btn" in hidden
