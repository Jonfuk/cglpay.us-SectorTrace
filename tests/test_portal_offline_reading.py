"""The portal read without JavaScript, and read on paper.

Both are ways this evidence actually gets consumed and neither was served.
Without JavaScript the page rendered its header and nothing else, on a site
whose whole purpose is to be citable. Printed, a caveat left collapsed on
screen simply did not appear — which is the exact failure the portal is built
against: a figure arriving somewhere without the caveat that governs it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from test_portal_isolation import PUBLIC_API_ROUTES

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
INDEX = PORTAL / "index.html"
STYLES = PORTAL / "styles.css"


@pytest.fixture(scope="module")
def index() -> str:
    return INDEX.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def styles() -> str:
    return STYLES.read_text(encoding="utf-8")


def test_there_is_a_noscript_block(index):
    assert "<noscript>" in index


def test_every_route_it_names_actually_exists(index):
    """A list of endpoints is a promise, and a wrong one is worse than none.

    The first draft of this block advertised /api/v1/overview and
    /api/v1/treatment, neither of which has ever existed. Checked against the
    same frozen list the isolation test pins the public surface to, so a route
    that gets renamed takes this with it.
    """
    noscript = re.search(r"<noscript>(.*?)</noscript>", index, re.S)
    assert noscript, "no <noscript> block to check"

    named = set(re.findall(r"/api/v1/([a-z0-9_]+)", noscript.group(1)))
    assert named, "the block should tell a reader where the evidence is"

    # `export` is a real route and is not in the frozen data-route list.
    unknown = named - PUBLIC_API_ROUTES - {"export"}
    assert not unknown, f"advertised routes that do not exist: {sorted(unknown)}"


def test_it_sends_the_reader_to_the_caveats(index):
    noscript = re.search(r"<noscript>(.*?)</noscript>", index, re.S).group(1)

    assert "caveat" in noscript.lower(), (
        "pointing at raw API data without pointing at the caveats is the one "
        "thing this project does not do")


def test_there_is_a_print_stylesheet(styles):
    assert "@media print" in styles


def test_a_collapsed_caveat_still_prints(styles):
    """The whole reason the print block exists.

    `.caveat-body[hidden]` is how a caveat sits closed on screen. On paper
    there is nothing to click, so hidden has to mean shown.
    """
    printed = styles[styles.index("@media print"):]

    assert ".caveat-body[hidden]" in printed
    assert "display: block !important" in printed


def test_controls_do_not_print(styles):
    printed = styles[styles.index("@media print"):]

    for control in (".topbar", ".filterbar", ".busybar"):
        assert control in printed, f"{control} is a control, not content"


def test_link_targets_are_written_out_on_paper(styles):
    """A citation whose URL only existed as an href is not a citation in print."""
    printed = styles[styles.index("@media print"):]

    assert 'content: " (" attr(href) ")"' in printed


def test_the_portal_still_makes_no_external_requests(index):
    """Unchanged by any of the above, and the reason the CSP can be strict."""
    assert "http://" not in index.replace("http://www.w3.org", "")
    assert "https://" not in index
