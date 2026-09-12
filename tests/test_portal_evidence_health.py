"""Page-level evidence health strip (BETA-084).

One strip at the top of every public evidence page, in the same place and the
same shape: scope, latest retrieval, verification state, coverage
completeness, licence and the known limitation — each an explicit state, a
missing value shown as "unknown" / "not stated", never a blank, with links to
the dataset catalogue and the coverage records.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
PAGES = PORTAL / "js" / "pages"
STYLES = PORTAL / "styles.css"


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def test_the_strip_is_one_shared_component(components: str) -> None:
    assert "export function evidenceHealthStrip(" in components
    body = components[components.index("export function evidenceHealthStrip("):]
    for label in ("Scope", "Latest retrieval", "Verification", "Coverage", "Licence"):
        assert f"'{label}'" in body


def test_missing_values_render_an_explicit_state_not_a_blank(components: str) -> None:
    body = components[components.index("export function evidenceHealthStrip("):]
    assert "ehs-unknown" in body
    assert "'unknown'" in body and "'not stated'" in body
    # verification / coverage map an absent value to a word, never ''
    assert "|| 'unknown'" in body


def test_the_strip_links_to_the_catalogue_and_the_coverage_page(components: str) -> None:
    body = components[components.index("export function evidenceHealthStrip("):]
    assert "`#/catalogue/${catalogueSlug}`" in body
    assert "'#/catalogue'" in body
    assert "'#/coverage'" in body


def test_at_least_three_pages_adopt_it() -> None:
    adopters = [p.name for p in PAGES.glob("*.js")
                if "evidenceHealthStrip(" in p.read_text(encoding="utf-8")]
    assert set(adopters) >= {"pay.js", "contracts.js", "treatment.js"}, adopters


def test_the_strip_has_its_own_styles(components: str) -> None:
    css = STYLES.read_text(encoding="utf-8")
    assert ".evidence-health" in css and ".ehs-grid" in css
    assert ".ehs-unknown" in css
