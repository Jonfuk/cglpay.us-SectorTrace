"""Navigable provider and authority workbenches (BETA-076).

A populated provider profile runs to hundreds of records across many evidence
types. This pins the shared navigation: a sticky section index with counts, a
scroll-spy, a back-to-top control, `?section=` deep links, and progressive
disclosure for a large collection. The runtime behaviour is a browser check;
this holds the wiring.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
PROVIDERS = PORTAL / "js" / "pages" / "providers.js"
AUTHORITY = PORTAL / "js" / "pages" / "authority.js"


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def test_the_shared_index_exports_exist(components: str) -> None:
    assert "export function workbenchNav(" in components
    assert "export function collapsibleSection(" in components


def test_the_index_has_scroll_spy_counts_and_back_to_top(components: str) -> None:
    body = components[components.index("export function workbenchNav("):]
    assert "IntersectionObserver" in body
    assert "workbench-index-count" in body
    assert "workbench-totop" in body
    # an empty section is greyed, not hidden
    assert "s.available === false" in body


def test_deep_links_are_a_section_query_key_not_a_re_render(components: str) -> None:
    body = components[components.index("export function workbenchNav("):]
    assert "q.set('section', id)" in body
    assert "history.replaceState(null, '', `#${routePath}?" in body
    assert "get('section')" in body


def test_progressive_disclosure_keeps_the_export_outside_the_collapse(components: str) -> None:
    body = components[components.index("export function collapsibleSection("):]
    assert "collapsedAbove" in body
    assert "details" in body and "Show all" in body
    # the `extra` slot (where a caller puts a Download button) is appended to
    # the section header, not inside the collapsible <details>
    assert "extra || null" in body


def test_both_workbenches_mount_the_index_and_clean_it_up() -> None:
    for path in (PROVIDERS, AUTHORITY):
        text = path.read_text(encoding="utf-8")
        assert "workbenchNav(page, sections" in text, f"{path.name} has no index"
        assert "wb.cleanup()" in text, f"{path.name} leaks the index listeners"
        assert "routePath:" in text


def test_the_provider_index_counts_come_from_the_payload() -> None:
    text = PROVIDERS.read_text(encoding="utf-8")
    block = text[text.index("const sections = ["):text.index("];", text.index("const sections = ["))]
    for field in ("data.events", "data.cqc_locations", "data.filings",
                  "data.tribunal_cases", "data.pfd_mentions"):
        assert field in block
