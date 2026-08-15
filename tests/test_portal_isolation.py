"""The boundary between the public portal and the operator UI.

Two front ends share one process, one static-file map and one request handler,
and only one of them is meant to be handed to people outside the team. That
arrangement is fine while the boundary holds and quietly wrong the moment it
does not: an operator page that pulls in a portal asset, an admin endpoint
answering under /api/v1/, a portal route that starts serving something new.

None of those failures is visible from the admin side. The portal keeps
working, so nobody notices until the wrong thing has been published.

So the boundary is written down here as literal lists rather than derived from
the code under test. A test that recomputes the answer from the same source
agrees with any change, including the change nobody meant to make. These lists
have to be edited by hand, and editing them is the point: it is the moment
someone decides that the public surface really should be different.
"""
from __future__ import annotations

import inspect
import re
import threading

import httpx
import pytest

from pipeline.web import server as server_module
from pipeline.web.server import PUBLIC_DIR, STATIC_DIR, STATIC_FILES, build_server

# --- the frozen public surface ------------------------------------------------

# Everything the portal serves, by request path. Adding an entry here is a
# decision to publish something new.
PUBLIC_STATIC_PATHS = {
    "/",
    "/index.html",
    "/app.js",
    "/styles.css",
    "/api",
    "/api.html",
    "/js/theme.js",
    "/js/components.js",
    "/js/pages/overview.js",
    "/js/pages/pay.js",
    "/js/pages/contracts.js",
    "/js/pages/geography.js",
    "/js/pages/treatment.js",
    "/js/pages/providers.js",
    "/js/pages/pfd.js",
    "/js/pages/authority.js",
    "/vendor/echarts.min.js",
    "/vendor/d3.min.js",
    "/vendor/tabulator.min.js",
    "/vendor/tabulator_midnight.min.css",
    "/vendor/fuse.min.js",
    "/vendor/date-fns.cdn.min.js",
}

# The portal's read-only API, as route names under /api/v1/.
PUBLIC_API_ROUTES = {
    "summary",
    "providers",
    "authorities",
    "contracts",
    "pay",
    "geography",
    "boundaries",
    "fingertips",
    "ndtms",
    "pfd",
    "freshness",
}

# Route patterns under /api/v1/ that take a parameter.
PUBLIC_API_PATTERNS = {
    r"providers/([a-z0-9_]+)/timeline",
    r"authorities/([A-Z][0-9]{8})",
}

# Published under /api/v1/ and dispatched before the table above, so it is not
# a `route ==` literal in `_public_api` and would otherwise be absent from
# every list here. It is part of the same public surface and the documentation
# must cover it.
PUBLIC_API_EXTRA = {"export"}

# Files the portal is made of. Admin work does not edit these, and no admin
# module may import from them -- see test_the_admin_ui_does_not_import_portal_code.
PORTAL_MODULES = {"pipeline.web.public_queries", "pipeline.web.public_export"}


def _admin(path: str) -> bool:
    return path == "/admin" or path.startswith("/admin/")


# Assets a page pulls in, as opposed to places it links to. The portal carries
# an "Admin ->" link, which is a door between the two front ends and fine; a
# stylesheet or script crossing the same way is the bug this file exists for.
ASSET_REFERENCE = re.compile(
    r'<(?:link|script|img)\b[^>]*?\b(?:href|src)="(/[^"]*)"', re.IGNORECASE)
ANCHOR_REFERENCE = re.compile(r'<a\b[^>]*?\bhref="(/[^"]*)"', re.IGNORECASE)


# --- static files -------------------------------------------------------------


def test_every_non_admin_static_path_is_served_from_the_portal_directory():
    """The directory is the guarantee. A path outside /admin that resolves
    into the operator directory is an operator file published at a public URL,
    whatever it happens to be called."""
    for path, (filename, _type, directory) in STATIC_FILES.items():
        if _admin(path):
            continue
        assert directory == PUBLIC_DIR, (
            f"{path} serves {filename} from {directory}, not the portal directory")


def test_every_admin_static_path_is_served_from_the_operator_directory():
    for path, (filename, _type, directory) in STATIC_FILES.items():
        if not _admin(path):
            continue
        assert directory == STATIC_DIR, (
            f"{path} serves {filename} from {directory}, not the operator directory")


def test_the_set_of_public_static_paths_has_not_changed():
    served = {path for path in STATIC_FILES if not _admin(path)}
    assert served == PUBLIC_STATIC_PATHS, (
        "The portal's static surface changed. If that was deliberate, update "
        "PUBLIC_STATIC_PATHS in this test; if it was a side effect of admin "
        "work, the new asset belongs under /admin/.")


def test_every_mapped_file_exists_on_disk():
    """A missing asset is a 500 at request time. Cheaper to find here."""
    for path, (filename, _type, directory) in STATIC_FILES.items():
        assert (directory / filename).is_file(), f"{path} maps to a missing file"


# --- the public API -----------------------------------------------------------


def test_the_public_api_routes_have_not_changed():
    """Read the route literals out of the dispatcher rather than probing it,
    so a route that exists but is unreachable for want of data still counts."""
    source = inspect.getsource(server_module.Handler._public_api)
    equality = set(re.findall(r'route == "([^"]+)"', source))
    patterns = set(re.findall(r'fullmatch\(r"([^"]+)", route\)', source))

    assert equality == PUBLIC_API_ROUTES, (
        "The portal's API surface changed. Admin endpoints belong under "
        "/api/admin/, not /api/v1/.")
    assert patterns == PUBLIC_API_PATTERNS


# --- and what the portal says the API is --------------------------------------
#
# Two places publish a list of endpoints: the /api documentation page and the
# <noscript> block, which is the only description a reader with JavaScript off
# ever sees. Both are pinned against the frozen list above, because a published
# endpoint list that is out of date is worse than none — it sends someone to
# build against a route that does not exist, and makes the ones that do exist
# look unreliable. This is not hypothetical: the <noscript> block did not gain
# /api/v1/ndtms when that endpoint shipped, and nothing noticed for a day.


def _documented_routes(html: str) -> set[str]:
    return set(re.findall(r'data-route="([^"]+)"', html))


def _mentioned_routes(text: str) -> set[str]:
    return {match for match in re.findall(r"/api/v1/([a-z_]+)", text)}


def test_the_api_page_documents_every_public_route_and_no_other():
    html = (PUBLIC_DIR / "api.html").read_text(encoding="utf-8")
    documented = _documented_routes(html)
    patterns = set(re.findall(r'data-route-pattern="([^"]+)"', html))

    parameterised = {route for route in documented if "{" in route}
    assert documented - parameterised == PUBLIC_API_ROUTES | PUBLIC_API_EXTRA, (
        "The API documentation and the portal's routes disagree. Whichever "
        "changed, the other has to: a published endpoint list that is wrong is "
        "worse than no list at all.")
    assert patterns == PUBLIC_API_PATTERNS, (
        "A parameterised route is documented with a shape the server does not "
        "match, or one it does match is undocumented.")


def test_the_noscript_block_names_every_public_route():
    """The only description of the API a reader with JavaScript off sees."""
    html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
    block = html[html.index("<noscript>"):html.index("</noscript>")]

    assert _mentioned_routes(block) == PUBLIC_API_ROUTES | PUBLIC_API_EXTRA


def test_the_api_page_needs_no_javascript():
    """It documents the API for the case where the portal is not what the
    reader wants, which includes the case where the portal does not run."""
    html = (PUBLIC_DIR / "api.html").read_text(encoding="utf-8")
    assert "<script" not in html.lower()


def test_public_api_dispatch_is_reachable_only_through_the_v1_prefix():
    """`_get` hands off to the portal API on one prefix and one only, so an
    operator route cannot fall through into it."""
    source = inspect.getsource(server_module.Handler._get)
    handoffs = re.findall(r'path\.startswith\("([^"]+)"\)', source)
    assert handoffs == ["/api/v1/"]


# --- the two front ends do not share code -------------------------------------


def test_the_admin_page_loads_only_its_own_assets():
    """The failure this catches happened: the operator UI moved from / to
    /admin and its asset references did not move with it, so it loaded the
    portal's stylesheet and script."""
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assets = ASSET_REFERENCE.findall(html)

    assert assets, "expected the operator page to reference some assets"
    for reference in assets:
        assert _admin(reference), (
            f"{reference} is a portal path. The operator page must reference "
            "/admin/... assets.")
        assert reference in STATIC_FILES, f"{reference} is not a served path"


def test_the_portal_page_loads_only_its_own_assets():
    html = (PUBLIC_DIR / "index.html").read_text(encoding="utf-8")
    assets = ASSET_REFERENCE.findall(html)

    assert assets
    for reference in assets:
        assert not _admin(reference), f"the portal loads {reference} as an asset"
        assert reference in STATIC_FILES, f"{reference} is not a served path"

    # Links may cross the boundary; they still have to go somewhere real.
    for reference in ANCHOR_REFERENCE.findall(html):
        assert reference in STATIC_FILES, f"the portal links to {reference}, which is not served"


def test_the_admin_modules_import_only_from_each_other():
    """The operator UI's ES modules sit next to the portal's, one directory
    apart, and `../` would reach them. Relative imports that leave /admin/js
    are the shape that failure takes."""
    for path in sorted((STATIC_DIR / "js").glob("*.js")):
        source = path.read_text(encoding="utf-8")
        for target in re.findall(r"""^\s*import\s[^'"]*['"]([^'"]+)['"]""",
                                  source, re.MULTILINE):
            assert target.startswith("./"), (
                f"{path.name} imports {target}; admin modules import siblings only")
            assert (path.parent / target).is_file(), f"{path.name} imports missing {target}"


def test_the_admin_ui_does_not_import_portal_code():
    """Shared helpers are the usual way a boundary rots: a change made for the
    admin side lands in a function the portal calls. The operator modules
    duplicate what they need instead."""
    for name in ("queries", "review", "resolve"):
        module = __import__(f"pipeline.web.{name}", fromlist=["_"])
        source = inspect.getsource(module)
        for portal in ("public_queries", "public_export"):
            assert f"import {portal}" not in source and f"from pipeline.web.{portal}" not in source, (
                f"pipeline.web.{name} imports {portal}")


# --- and it holds over HTTP ---------------------------------------------------


@pytest.fixture
def client(conn, settings):
    """`conn` for its side effect: a migrated warehouse on disk. Without one
    every read is a 400 about a missing database, and a test that asserts a
    404 passes for the wrong reason."""
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_the_two_index_pages_are_different_documents(client):
    """The symptom of the boundary breaking, checked end to end."""
    admin = client.get("/admin")
    portal = client.get("/")

    assert admin.status_code == 200
    assert portal.status_code == 200
    assert admin.text != portal.text
    assert "Evidence pipeline" in admin.text
    assert "SectorTrace" in portal.text


def test_the_admin_assets_served_are_the_operator_files(client):
    """/admin/app.js and /app.js are different scripts. This is the assertion
    that would have failed while the operator page was loading the portal's."""
    admin_js = client.get("/admin/app.js").text
    portal_js = client.get("/app.js").text

    assert admin_js != portal_js
    assert "no raw HTML" in admin_js
    assert client.get("/admin/styles.css").text != client.get("/styles.css").text


def test_the_admin_modules_are_served(client):
    """A module that 404s takes the whole import graph with it, and the page
    keeps working well enough that nobody notices the palette is gone."""
    for name in ("shell", "dom", "theme", "palette", "pipeline", "health", "exports"):
        response = client.get(f"/admin/js/{name}.js")
        assert response.status_code == 200, f"/admin/js/{name}.js is not served"
        assert response.headers["Content-Type"].startswith("text/javascript")


def test_the_api_documentation_answers_at_the_address_a_reader_would_guess(client):
    """`/api` is a static page and `/api/v1/...` is the API. The dispatcher
    checks the static map first, which is what makes that possible; a change
    to that order would document the API at an address nobody would try."""
    page = client.get("/api")
    assert page.status_code == 200
    assert page.headers["Content-Type"].startswith("text/html")
    assert "/api/v1/summary" in page.text
    assert client.get("/api.html").text == page.text

    # And the prefix underneath it is untouched.
    assert client.get("/api/v1/summary").status_code == 200
    assert client.get("/api/v1/nonesuch").status_code == 404


def test_the_operator_api_is_not_reachable_under_the_public_prefix(client):
    """An operator route answering under /api/v1/ would be published."""
    for route in ("overview", "schema", "review", "review/facets", "overrides"):
        assert client.get(f"/api/v1/{route}").status_code == 404


def test_public_responses_are_cacheable_and_operator_responses_are_not(client):
    """Different audiences, different staleness rules: the portal's numbers
    change when a module runs, the review queue changes as you work on it."""
    assert "max-age" in client.get("/api/v1/summary").headers["Cache-Control"]
    assert client.get("/api/overview").headers["Cache-Control"] == "no-store"
