"""Providers link to the registers they are on.

The cheapest verification a reader can do is open the register and look, and
the portal made them search for it: `company_number` and `charity_number` were
rendered as plain text on a page whose whole purpose is to be checkable.

What is pinned here is the URL *shapes*, because they are the part that can be
wrong in a way nothing else notices -- a link that 404s still looks like a
link. Both were checked against the live registers on 2026-08-14 using real
identifiers out of this warehouse, and the checks are named in the test that
holds each one so a future change has something to re-run rather than a
constant to trust.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
COMPONENTS = PORTAL / "js" / "components.js"
PROVIDERS_PAGE = PORTAL / "js" / "pages" / "providers.js"


@pytest.fixture(scope="module")
def components() -> str:
    return COMPONENTS.read_text(encoding="utf-8")


def register_block(components: str) -> str:
    start = components.index("const REGISTERS = {")
    return components[start:components.index("\n};", start)]


def test_companies_house_links_to_the_company_profile(components):
    """Verified 2026-08-14: /company/03861209 is the Companies House profile
    for CHANGE, GROW, LIVE, which is company_number 03861209 in this
    warehouse. The same shape is recorded in docs/review-queue-improvements.md
    from an earlier check."""
    block = register_block(components)
    assert "find-and-update.company-information.service.gov.uk/company/" in block


def test_the_charity_link_searches_the_register_by_number(components):
    """Verified 2026-08-14: this search returns exactly one match for 1079327
    (CHANGE, GROW, LIVE) and for 234887 (TURNING POINT).

    Not the charity-details page, which is keyed by an internal organisation
    number this pipeline does not store. Building a details URL out of the
    registered charity number would produce a link that looks right and is
    not."""
    block = register_block(components)
    assert "register-of-charities.charitycommission.gov.uk/en/" in block
    assert "charity-search/-/results/page/1/delta/20/keywords/" in block


def test_no_link_is_built_for_a_register_whose_shape_was_not_verified(components):
    """CQC is the one this applies to. Its public API publishes no profile URL
    and the site refuses automated clients, so the shape is unverified -- and
    an unverified link is exactly the kind of plausible-looking wrongness this
    project spends its design budget avoiding."""
    block = register_block(components)
    assert "cqc.org.uk" not in block


def test_identifiers_are_escaped_into_the_url(components):
    """A warehouse value reaching an href unescaped is the one place this
    portal's DOM discipline does not protect by itself."""
    block = register_block(components)
    assert block.count("encodeURIComponent(id)") == len(
        re.findall(r"url: \(id\) =>", block))


def test_a_link_is_offered_rather_than_asserted(components):
    """The wording is the finding: "verify at source" says the register has
    not been consulted, which is true and is the point of offering it."""
    assert "Verify at source" in components
    body = components[components.index("export function registerLinks("):]
    assert "Verify at source: " in body[:body.index("\n}\n")]


def test_an_unknown_scheme_or_a_missing_number_produces_nothing(components):
    body = components[components.index("export function registerLink("):]
    body = body[:body.index("\n}\n")]
    assert "if (!register || !identifier) return null" in body


# --- and they reach the page --------------------------------------------------


def test_the_providers_payload_carries_both_identifiers():
    """Rendered as a link needs them returned in the first place; the list
    page had neither."""
    import inspect

    from pipeline.web import public_queries

    source = inspect.getsource(public_queries.providers)
    assert "AS company_number" in source
    assert "AS charity_number" in source


def test_the_deep_dive_builds_them_from_the_entity_edges():
    """No second query: an `identified_by` edge is a scheme and an identifier,
    which is what a register lookup takes."""
    page = PROVIDERS_PAGE.read_text(encoding="utf-8")
    assert "registerLinks(" in page
    assert "e.target_type" in page and "e.target_id" in page


def test_the_list_page_renders_them_as_dom_nodes_not_html():
    """Tabulator formatters may return an element, so a link in a cell does not
    need an HTML string built from a warehouse value."""
    page = PROVIDERS_PAGE.read_text(encoding="utf-8")
    for field in ("company_number", "charity_number"):
        assert f"registerLink('{field}', c.getValue())" in page
