"""What every response says about what the page it carries may do.

There is no authentication here by design, so these headers are not protecting
a session — there isn't one. They are protecting the operator's browser: the
one that can reach the queue, the SQL box and the `restricted_` tables, and
that is sitting on a LAN with whatever else is on it.

`frame-ancestors` is the one that matters most today. Without it any page on
that network can frame /admin and drive it with the operator's own browser,
and no amount of DOM discipline inside the page prevents that.
"""
from __future__ import annotations

import base64
import hashlib
import re
import threading

import httpx
import pytest

from pipeline.web import server as server_module
from pipeline.web.server import build_server

REQUIRED = ("Content-Security-Policy", "X-Frame-Options",
            "X-Content-Type-Options", "Referrer-Policy")


@pytest.fixture
def client(conn, settings):
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


def directives(response) -> dict[str, str]:
    out = {}
    for part in response.headers["Content-Security-Policy"].split(";"):
        name, _, value = part.strip().partition(" ")
        out[name] = value
    return out


@pytest.mark.parametrize("path", [
    "/",                      # portal document
    "/admin",                 # operator document
    "/app.js",                # portal asset
    "/admin/app.js",          # operator asset
    "/api/v1/summary",        # portal API
    "/api/overview",          # operator API
    "/api/schema",
])
def test_every_response_carries_them(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    for header in REQUIRED:
        assert header in response.headers, f"{path} is missing {header}"


def test_a_404_carries_them_too(client):
    """An error page renders in the same browser as a good one."""
    response = client.get("/api/v1/no-such-route")
    assert response.status_code == 404
    for header in REQUIRED:
        assert header in response.headers


def test_a_304_carries_them(client):
    first = client.get("/app.js")
    again = client.get("/app.js", headers={"If-None-Match": first.headers["ETag"]})

    assert again.status_code == 304
    for header in REQUIRED:
        assert header in again.headers, (
            "the cached copy renders under the policy sent with the 304")


def test_nothing_may_frame_this_server(client):
    for path in ("/", "/admin"):
        response = client.get(path)
        assert directives(response)["frame-ancestors"] == "'none'"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_the_portal_allows_no_inline_script_at_all(client):
    script = directives(client.get("/"))["script-src"]

    assert script == "'self'", (
        "the portal has no inline script, so its policy must not permit one")
    assert "unsafe-inline" not in script


def test_the_operator_page_allows_its_theme_guard_by_hash(client):
    """The one inline script on the page, allowed by what it actually is.

    Recomputed here from the file rather than pinned as a literal, so editing
    that script is not a way to silently break the page: if the two ever
    disagree this fails instead of the browser refusing to run it.
    """
    source = (server_module.STATIC_DIR / "index.html").read_bytes()
    inline = re.findall(rb"<script>(.*?)</script>", source, re.S)
    assert len(inline) == 1, "the page is expected to have exactly one inline script"
    expected = "'sha256-" + base64.b64encode(
        hashlib.sha256(inline[0]).digest()).decode() + "'"

    script = directives(client.get("/admin"))["script-src"]
    assert script == f"'self' {expected}"
    assert "unsafe-inline" not in script


def test_the_policy_is_not_shared_between_the_two_front_ends(client):
    """A hash for the operator page must not widen the portal's policy."""
    assert (directives(client.get("/admin"))["script-src"]
            != directives(client.get("/"))["script-src"])


def test_nothing_may_be_loaded_from_anywhere_else(client):
    found = directives(client.get("/"))

    assert found["default-src"] == "'self'"
    assert found["connect-src"] == "'self'"
    assert found["object-src"] == "'none'"
    assert found["base-uri"] == "'none'"
    assert found["form-action"] == "'none'"
    # The favicon is a data: URI in the page's own <head>.
    assert found["img-src"] == "'self' data:"


def test_the_referrer_stays_here(client):
    """URL hashes carry warehouse state -- #review?module=..., #database?table=...
    -- and a link out should not take the queue someone was clearing with it."""
    assert client.get("/admin").headers["Referrer-Policy"] == "same-origin"


def test_a_silent_client_does_not_hold_its_thread_forever():
    """ThreadingHTTPServer starts a thread per connection with no ceiling, and
    the base class leaves `timeout` as None, which blocks on read forever."""
    from pipeline.web.server import Handler

    assert isinstance(Handler.timeout, (int, float))
    assert 0 < Handler.timeout <= 120


def test_a_page_with_no_inline_script_gets_no_hashes(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<html><script src='/app.js'></script></html>", encoding="utf-8")

    assert server_module.inline_script_hashes(page) == ()


def test_a_missing_page_is_not_a_policy_error(tmp_path):
    assert server_module.inline_script_hashes(tmp_path / "gone.html") == ()
