"""The portal's tables can be searched and paged, and say how much they hold.

Tabulator ships per-column search and paging; the portal configured neither,
so a reader looking for one buyer among 98,636 notices read rows until the
page ended. The contracts table asks for 1,000 of them and simply stopped,
which reads as "these are the notices" rather than as a page of them.

What is pinned here is the *configuration*, in the one function every table
goes through. The behaviour — a pager that appears past one page, a search box
that narrows the rows — is a browser check, not this file: asserting it here
would mean a JavaScript runtime in the test suite, which docs/upgrade-roadmap
§3J files as a trade to make deliberately rather than as a side effect of a
table fix. So these tests hold the shape and the browser pass holds the rest.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
PAGES = sorted((PORTAL / "js" / "pages").glob("*.js"))


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    return source[start:source.index("\n}\n", start)]


# --- the shared table ---------------------------------------------------------


def test_the_table_pages_rather_than_stopping(components):
    body = function_body(components, "export function table(")

    assert "pagination: true" in body, "the portal's tables do not page"
    assert "paginationSize" in body, "a pager with no page size shows every row"
    assert "paginationCounter" in body, (
        "the footer counter is where 'showing 1-25 of 98,636' comes from")


def test_every_column_gets_a_search_box_unless_it_refuses_one(components):
    """Default on, opt out per column. The other way round is how five future
    sections each end up without search."""
    body = function_body(components, "export function table(")

    assert "headerFilter === undefined" in body, (
        "columns should inherit a header filter, not have to ask for one")
    assert "headerFilter: 'input'" in body


def test_no_page_builds_its_own_table(components):
    """The reason this is one function: a page constructing a Tabulator
    directly would inherit none of the above."""
    for path in PAGES:
        source = path.read_text(encoding="utf-8")
        assert "new window.Tabulator" not in source, (
            f"{path.name} builds its own table; use table()/tableCard()")


# --- the count ----------------------------------------------------------------


def test_the_row_count_is_rendered_next_to_the_title(components):
    body = function_body(components, "export function tableCard(")

    assert "rowCount(rows.length, options.total)" in body
    assert "truncated" in body, (
        "a table showing part of a corpus should look different from one "
        "showing all of it")


def test_the_count_compares_what_is_shown_against_the_corpus(components):
    """`rowCount(shown, total)` is the whole of "1,000 of 98,636". The
    behaviour is three lines and is written to be readable rather than tested
    through a JS engine, so what is asserted is that both numbers reach it."""
    body = function_body(components, "export function rowCount(")

    assert "total <= shown" in body, (
        "a total no larger than what is shown is not a truncation and should "
        "read as a plain count")
    assert "of ${num(total)}" in body


def test_the_table_that_truncates_passes_its_corpus_total():
    """contracts.js is the call site the finding is about: it shows one page of
    ~98,636 notices and the payload's `total` is the only place the rest is
    counted. Without it the count says '100 rows' and is a lie by omission.

    Since BETA-040 the page pages the notices by offset, so the total is held
    in `session.total` — seeded from `data.total` and refreshed from each
    "show more" response — and that is what the table and the count line are
    given."""
    source = (PORTAL / "js" / "pages" / "contracts.js").read_text(encoding="utf-8")

    assert re.search(r"total:\s*Number\(data\.total\)", source), (
        "the notices session no longer seeds its total from the payload")
    assert re.search(r"total:\s*session\.total", source), (
        "the notices table does not pass the corpus total to its row count")
    assert "'Every notice'" not in source, (
        "the section was renamed: one page of ~98,636 notices is not every notice")
