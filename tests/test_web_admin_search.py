"""The admin semantic-search workbench (BETA-046).

The retrieval backend (`/api/admin/search`, keyword / semantic / hybrid) and
its isolation are already pinned in `tests/test_nlp_search_eval.py` and
`tests/test_portal_isolation.py`. This file pins the workbench UI that sits
on top: it exists, it is wired into the operator shell, and it surfaces the
things a reviewer needs to judge a result — score components, model identity
and fallback state — without presenting relevance as evidence confidence.

Source pins, like the rest of the front-end suite: the tests run offline with
no browser.
"""
from __future__ import annotations

from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP = (STATIC / "app.js").read_text(encoding="utf-8")
SHELL = (STATIC / "js" / "shell.js").read_text(encoding="utf-8")
SEARCH = (STATIC / "js" / "search.js").read_text(encoding="utf-8")


def test_the_operator_page_declares_the_search_tab_and_panel():
    assert '<button class="tab" data-tab="search"' in INDEX
    assert 'id="tab-search"' in INDEX
    # The controls the workbench needs: a mode switch across all three modes,
    # source and date filters, and a result limit.
    for control in ('id="search-q"', 'id="search-mode"', 'id="search-source"',
                    'id="search-from"', 'id="search-to"', 'id="search-limit"'):
        assert control in INDEX, f"{control} missing from the search panel"
    for mode in ('value="hybrid"', 'value="keyword"', 'value="semantic"'):
        assert mode in INDEX, f"mode option {mode} missing"


def test_the_search_tab_is_registered_in_the_router():
    assert "'search'" in APP
    tabs = APP[APP.index("const TABS ="):APP.index("const TABS =") + 200]
    assert "'search'" in tabs, "search is not in the TABS list app.js iterates"


def test_the_shell_boots_the_search_module():
    assert "import { initSearch } from './search.js';" in SHELL
    assert "initSearch();" in SHELL


def test_the_workbench_surfaces_score_components_model_and_fallback():
    # Score components — the ordering must be inspectable, not magic.
    for key in ("keyword_rank", "semantic_rank", "cosine", "rrf"):
        assert key in SEARCH, f"score component {key!r} not labelled in the workbench"
    # Model identity and the fallback notes are shown, not buried.
    assert "model_key" in SEARCH
    assert "data.notes" in SEARCH or ".notes" in SEARCH
    # And the caveat that relevance is retrieval behaviour, not evidence.
    assert "caveat" in SEARCH
    assert "not" in INDEX[INDEX.index('id="tab-search"'):].split("</section>")[0].lower()


def test_the_workbench_builds_the_dom_without_raw_html():
    """Search results are scraped PDF text; settled decision 9 applies here
    like every other surface."""
    assert "innerHTML" not in SEARCH
    assert "import { el } from './dom.js';" in SEARCH


def test_the_workbench_calls_only_the_admin_route():
    assert "/api/admin/search" in SEARCH
    assert "/api/v1/" not in SEARCH
