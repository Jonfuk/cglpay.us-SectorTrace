"""Accessibility and performance guardrails for the BETA-038–049 round (BETA-049).

Search, comparison and review features are not complete if they regress the
things a caveat rule does not cover: a status change nothing announces, a
route that streams an unbounded result set, a script that reaches off-origin,
a value concatenated into markup. Each of those was checked by hand as the
round shipped; this file makes the checks repeatable, offline, and part of
the suite.

The round's new surfaces:
  * public pages:  js/pages/catalogue.js  (+ the provider layers added to
    js/pages/compare.js)
  * admin tabs:    js/search.js, js/claimreview.js
  * public routes: /api/v1/catalogue, /catalogue/{id}, /provider_compare,
    /relationships/{id}, /api/openapi.json
  * admin routes:  /api/admin/claim-candidates(+detail/decide),
    /claim-gate, /claim-ontology
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import openapi, public_queries
from pipeline.web.server import PUBLIC_MAX_AGE, build_server

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "pipeline" / "web" / "static" / "public"
ADMIN = ROOT / "pipeline" / "web" / "static"

NEW_PUBLIC_JS = [PUBLIC / "js" / "pages" / "catalogue.js"]
NEW_ADMIN_JS = [ADMIN / "js" / "search.js", ADMIN / "js" / "claimreview.js"]
NEW_JS = NEW_PUBLIC_JS + NEW_ADMIN_JS

INDEX_PUBLIC = (PUBLIC / "index.html").read_text(encoding="utf-8")
INDEX_ADMIN = (ADMIN / "index.html").read_text(encoding="utf-8")


# --- accessibility: nothing changes silently ------------------------------


@pytest.mark.parametrize("region_id", [
    "search-status",        # BETA-046
    "claimreview-status",   # BETA-047
])
def test_the_new_status_regions_are_live(region_id):
    """A search or a decision changes a count on the page; a screen reader has
    to be told. Each new async surface owns an aria-live status region."""
    pattern = rf'id="{region_id}"[^>]*aria-live="(polite|assertive)"'
    assert re.search(pattern, INDEX_ADMIN), (
        f"#{region_id} is not an aria-live region")


def test_the_new_public_page_reaches_the_dom_as_text_nodes():
    for path in NEW_JS:
        source = path.read_text(encoding="utf-8")
        assert "innerHTML" not in source, f"{path.name} uses innerHTML"
        assert "outerHTML" not in source, f"{path.name} uses outerHTML"


def test_the_new_admin_forms_label_every_control():
    """A control with neither a <label> nor an aria-label is unusable with a
    screen reader. The round's new admin forms carry a label on each."""
    for section_id in ("tab-search", "tab-claimreview"):
        start = INDEX_ADMIN.index(f'id="{section_id}"')
        end = INDEX_ADMIN.index("</section>", start)
        block = INDEX_ADMIN[start:end]
        for control in re.finditer(r"<(input|select)\b([^>]*)>", block):
            attrs = control.group(2)
            has_aria = 'aria-label="' in attrs
            has_id = re.search(r'\bid="([^"]+)"', attrs)
            wrapped = has_id and f'for="{has_id.group(1)}"' in block
            # a control wrapped in <label>…</label> is also fine
            labelled = has_aria or wrapped or "<label" in block[:control.start()][-120:]
            assert labelled, f"unlabelled control in #{section_id}: <{control.group(0)}>"


# --- local assets: no new off-origin reference ---------------------------


_OFFSITE = re.compile(r"""(?:src|href)\s*=\s*["']https?://|import\s+[^;]*["']https?://"""
                      r"""|\bfetch\(\s*["']https?://""", re.IGNORECASE)


def test_the_new_scripts_make_no_off_origin_request():
    for path in NEW_JS:
        source = path.read_text(encoding="utf-8")
        assert not _OFFSITE.search(source), f"{path.name} references an external URL"
        # No hard-coded scheme at all in the new files — every outbound link is
        # built from a source_url the API returned, never a literal.
        assert "http://" not in source and "https://" not in source, (
            f"{path.name} contains a literal URL")


def test_the_frozen_public_static_surface_gained_no_remote_url():
    from tests.test_portal_isolation import PUBLIC_STATIC_PATHS
    assert all(p.startswith("/") for p in PUBLIC_STATIC_PATHS), (
        "a public static path is an absolute URL, not a local asset")


# --- performance: every new route bounds its output ---------------------


@pytest.fixture
def client(settings: Settings, conn: sqlite3.Connection):
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=15.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_provider_compare_is_bounded_to_four_providers(client):
    keys = [("provider_key", f"p{i}") for i in range(5)]
    assert client.get("/api/v1/provider_compare", params=keys).status_code == 400


def test_the_relationship_timeline_is_capped():
    """The drawer shows one relationship's history, not a stream. The query
    carries a LIMIT and the payload a `truncated` flag."""
    source = __import__("inspect").getsource(public_queries.relationship_detail)
    assert "LIMIT :cap" in source
    assert '"truncated": truncated' in source


def test_the_catalogue_is_a_fixed_small_list(client):
    body = client.get("/api/v1/catalogue").json()
    # One row per collecting module — a bounded set, not a user-growable list.
    assert body["count"] == len(body["datasets"]) <= 60


def test_the_public_read_routes_carry_a_cache_header(client):
    for path in ("/api/v1/catalogue", "/api/openapi.json"):
        response = client.get(path)
        assert response.status_code == 200
        cache_control = response.headers.get("Cache-Control", "")
        assert f"max-age={PUBLIC_MAX_AGE}" in cache_control, (
            f"{path} does not advertise the public max-age")


def test_openapi_documents_a_limit_on_the_paged_routes():
    """The contract itself must show the bounds: a client reading the spec
    should see that document_search and contracts page."""
    doc = openapi.document()
    for path in ("/api/v1/document_search", "/api/v1/contracts"):
        names = {p["name"] for p in doc["paths"][path]["get"]["parameters"]}
        assert {"limit", "offset"} <= names, f"{path} spec omits limit/offset"
