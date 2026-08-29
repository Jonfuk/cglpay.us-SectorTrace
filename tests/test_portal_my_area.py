"""My area context (BETA-073).

A reader keeps one council as a local starting point with no account: only the
ONS code goes to localStorage, and every figure on the card comes from the
existing `/api/v1/authorities/:code` payload, linked back to its section.
"""
from __future__ import annotations

from pathlib import Path

import pytest

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"
MYAREA = PORTAL / "js" / "myarea.js"
SERVER = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "server.py"


@pytest.fixture(scope="module")
def myarea() -> str:
    return MYAREA.read_text(encoding="utf-8")


def test_module_is_served(myarea: str) -> None:
    assert '"myarea"' in SERVER.read_text(encoding="utf-8")
    for name in ("getMyArea", "setMyArea", "clearMyArea", "myAreaToggle",
                 "renderMyAreaCard"):
        assert f"export function {name}" in myarea or f"export async function {name}" in myarea


def test_local_storage_holds_only_a_validated_ons_code(myarea: str) -> None:
    assert "sectortrace.my_area" in myarea
    # a strict ONS-code shape gates the write, so nothing else can be stored
    assert "ONS = /^[A-Z][0-9]{8}$/" in myarea
    assert "if (!ONS.test(code || '')) return;" in myarea
    # the only setItem writes the validated `code`, nothing composed
    assert "localStorage.setItem(KEY, code)" in myarea
    assert myarea.count("localStorage.setItem(") == 1


def test_localstorage_access_is_guarded(myarea: str) -> None:
    # private mode must degrade to "no feature", never throw
    assert myarea.count("catch (e)") >= 3
    assert "try {" in myarea


def test_the_card_only_reads_the_existing_authority_route(myarea: str) -> None:
    assert "fetchJSON(`authorities/${encodeURIComponent(code)}`)" in myarea
    # no new endpoint invented
    assert "my-area" not in myarea or "/api/" not in myarea.split("fetchJSON")[0]


def test_every_stat_links_into_the_authority_workbench(myarea: str) -> None:
    body = myarea[myarea.index("const stat ="):]
    assert "`#/authorities/${code}${anchor}`" in body
    for anchor in ("#grant-budget", "#treatment", "#contracts", "#comparators"):
        assert anchor in myarea


def test_the_overview_and_authority_pages_wire_it_in() -> None:
    overview = (PORTAL / "js" / "pages" / "overview.js").read_text(encoding="utf-8")
    authority = (PORTAL / "js" / "pages" / "authority.js").read_text(encoding="utf-8")
    assert "renderMyAreaCard" in overview and "id: 'my-area'" in overview
    assert "myAreaToggle(" in authority
    # the overview listener is removed on dispose
    assert "removeEventListener('myareachange'" in overview
