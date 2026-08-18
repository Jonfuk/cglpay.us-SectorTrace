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
    "/health",                 # Railway process probe
])
def test_every_response_carries_them(client, path):
    response = client.get(path)
    assert response.status_code == 200, path
    for header in REQUIRED:
        assert header in response.headers, f"{path} is missing {header}"


def test_health_probe_has_no_database_payload(client):
    response = client.get("/health")
    assert response.text == "ok\n"
    assert response.headers["cache-control"] == "no-store"


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
    # Normalised to LF, which is what an HTML parser hands the script before
    # the browser hashes it. Hashing the file's raw bytes produces a policy
    # that blocks the very script it was computed from, on any checkout with
    # CRLF endings — which on Windows is most of them.
    normalised = inline[0].replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    expected = "'sha256-" + base64.b64encode(
        hashlib.sha256(normalised).digest()).decode() + "'"

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


def test_the_hash_survives_windows_line_endings(tmp_path):
    """The regression that left the operator page's theme guard blocked.

    A browser normalises CRLF to LF while parsing HTML, so the same page saved
    with either ending has to produce the same hash. A test that recomputes
    the hash the way the code does agrees with itself and proves nothing —
    this asserts the two files agree with *each other*, which is the property
    that was actually broken, and it was found by reading a browser console
    rather than by any test.
    """
    script = "<script>\n  var a = 1;\n</script>"
    unix = tmp_path / "unix.html"
    windows = tmp_path / "windows.html"
    unix.write_bytes(script.encode())
    windows.write_bytes(script.replace("\n", "\r\n").encode())

    assert server_module.inline_script_hashes(unix), "a hash was found at all"
    assert (server_module.inline_script_hashes(unix)
            == server_module.inline_script_hashes(windows))


class TestResponseSplitting:
    """A query parameter must not be able to add a header.

    This was live. `_export_name` interpolated `provider_key` and `metric`
    into `Content-Disposition`, and `BaseHTTPRequestHandler.send_header`
    formats `"%s: %s\r\n"` without validating anything, so

        /api/v1/export?endpoint=summary&format=csv&provider_key=x%0d%0aX-Injected:%20yes

    put `X-Injected` in the response. CodeQL had been reporting it as
    `py/http-response-splitting` since the scan was switched on, in the
    untriaged pile finding O-05 records; it took reading the alerts to find
    out that one of them was true.

    Over a raw socket rather than through httpx, deliberately. An HTTP client
    parses the response into a dict of headers, which is exactly the step that
    would make an injected header look like an ordinary one — the bytes on the
    wire are the evidence.
    """

    @pytest.fixture
    def port(self, conn, settings):
        conn.execute(
            "INSERT INTO providers (provider_key, canonical_name, is_target) "
            "VALUES ('cgl', 'Change Grow Live', 1)")
        conn.commit()
        server = build_server(settings, host="127.0.0.1", port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield server.server_address[1]
        server.shutdown()
        server.server_close()

    def _headers(self, port: int, path: str) -> bytes:
        import socket

        sock = socket.create_connection(("127.0.0.1", port), timeout=15)
        try:
            sock.sendall(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n"
                          "Connection: close\r\n\r\n".encode())
            received = b""
            while b"\r\n\r\n" not in received:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                received += chunk
        finally:
            sock.close()
        return received.split(b"\r\n\r\n", 1)[0]

    def _header_names(self, head: bytes) -> list[str]:
        """The name of every header line in the response.

        Asserting on names rather than on the absence of a substring, because
        once the fix is in the substring is present *legitimately*: the
        sanitised value is echoed inside the filename, and the raw value
        inside the JSON-escaped `X-Provenance`. Both sit on one header line
        each, which is the whole question. A test that searched the bytes for
        `X-Injected` would fail against a server behaving correctly — and the
        obvious way to make it pass would be to stop echoing the value rather
        than to stop splitting the response, which is fixing the test's
        opinion instead of the defect.
        """
        return [line.split(b":", 1)[0].decode("latin-1").strip().lower()
                 for line in head.split(b"\r\n")[1:] if b":" in line]

    def test_a_crlf_in_a_query_parameter_adds_no_header(self, port):
        head = self._headers(
            port, "/api/v1/export?endpoint=summary&format=csv"
                   "&provider_key=cgl%0d%0aX-Injected:%20yes")
        assert "x-injected" not in self._header_names(head), head

    def test_the_same_through_the_metric_parameter(self, port):
        """Two parameters reach the filename, and a fix that covered one of
        them would pass a test that only tried that one."""
        head = self._headers(
            port, "/api/v1/export?endpoint=geography&format=csv"
                   "&metric=grant_total%0d%0aX-Injected:%20yes")
        assert "x-injected" not in self._header_names(head), head

    def test_the_provenance_header_stays_one_line(self, port):
        """`X-Provenance` carries the filters back, hostile one included.

        `json.dumps` escapes the newline rather than emitting it, which is why
        that header was never the hole. Pinned so that a later change to
        hand-built JSON cannot quietly open one.
        """
        head = self._headers(
            port, "/api/v1/export?endpoint=summary&format=csv"
                   "&provider_key=cgl%0d%0aX-Injected:%20yes")
        provenance = [line for line in head.split(b"\r\n")
                       if line.lower().startswith(b"x-provenance")]
        # One line is the assertion. The text `X-Injected: yes` *is* in it —
        # the filters are echoed back, which is the header's job — but behind
        # a two-character `\r\n` escape rather than a real newline, so it is
        # data inside a value and not a header of its own.
        assert len(provenance) == 1, head
        assert rb"cgl\r\nX-Injected: yes" in provenance[0], provenance[0]

    def test_a_quote_does_not_end_the_filename(self, port):
        """No control character needed: a `"` closes the quoted filename and
        anything after it becomes another Content-Disposition parameter."""
        head = self._headers(
            port, '/api/v1/export?endpoint=summary&format=csv'
                   '&provider_key=x%22;%20filename%3D%22evil.exe')
        disposition = [line for line in head.split(b"\r\n")
                        if line.lower().startswith(b"content-disposition")]
        assert disposition, head
        assert disposition[0].count(b'filename=') == 1, disposition[0]

    def test_the_response_is_still_a_working_download(self, port):
        """The fix must not have broken the header it sanitises."""
        head = self._headers(
            port, "/api/v1/export?endpoint=summary&format=csv&provider_key=cgl")
        assert b"attachment; filename=" in head, head
        assert b"sectorTrace_summary_cgl_" in head, head


class TestHeaderSanitiser:
    def test_it_strips_both_carriage_return_and_newline(self):
        assert server_module._HEADER_BREAK.sub(" ", "a\r\nb") == "a  b"

    def test_a_filename_part_keeps_what_a_filename_may_hold(self):
        assert server_module._safe_name_part("change_grow_live") == "change_grow_live"
        assert server_module._safe_name_part("grant-total.2026") == "grant-total.2026"

    def test_a_filename_part_drops_everything_else(self):
        assert server_module._safe_name_part('x"; filename="evil.exe') == "x-filename-evil.exe"
        assert server_module._safe_name_part("a\r\nb") == "a-b"

    def test_a_filename_part_is_bounded(self):
        """A 4KB query parameter is not a filename, and some clients reject a
        header line long before that."""
        assert len(server_module._safe_name_part("a" * 5000)) == server_module._NAME_PART_MAX
