"""The HTTP layer: a JSON API over `queries` and `review`, plus three static files.

On the standard library rather than a framework. This pipeline's dependency
list is short and every entry earns its place; a local, single-user, six-route
admin page is not the thing to add a web stack and an ASGI server for, and
`ThreadingHTTPServer` handles a browser talking to localhost perfectly well.

Three properties are worth stating rather than leaving to be inferred:

  * **Loopback by default.** The warehouse contains `restricted_` tables of
    personal data. `--host` can widen that, and says so loudly, but nothing
    here authenticates anyone: a wider bind is a decision to trust the network
    it is bound to.

  * **Writes require a JSON content type and a same-origin `Origin`.** A page
    on another site can make your browser POST to 127.0.0.1 — it cannot read
    the reply, but a write would still land. Requiring `application/json`
    forces a CORS preflight the browser will not send for a cross-origin
    request without permission, and the `Origin` check refuses one that
    arrives anyway.

  * **`restricted_` rows need an explicit ask.** Browsing to a personal-data
    table returns a refusal with a flag to repeat the request. It is a guard
    against opening one by accident, not a permission boundary — the SQL box
    reads the same rows, and so does `sqlite3` — but "I clicked the wrong
    table" should not be how someone ends up looking at 1,539 named
    individuals from PFD reports.
"""
from __future__ import annotations

import json
import re
import socket
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import structlog

from pipeline import db
from pipeline.config import Settings, get_settings
from pipeline.web import (
    admin,
    artefacts,
    health,
    public_export,
    public_queries,
    queries,
    resolve,
    review,
)
from pipeline.web.jobs import JobError, JobRegistry, JobStore

STATIC_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_DIR = STATIC_DIR / "public"

HTML = "text/html; charset=utf-8"
JS = "text/javascript; charset=utf-8"
CSS = "text/css; charset=utf-8"

# Two front ends on one server, each served by exact name from a whitelist.
#
# A dict rather than a directory walk, still: matching a request path against
# known names means path traversal is not a thing that has to be got right,
# and that property is worth more now that one of the two interfaces is meant
# to be handed to people outside the team.
#
# The operator UI moved from / to /admin when the portal took the root. Its
# files did not move on disk, so the mapping carries the directory as well as
# the filename.
STATIC_FILES: dict[str, tuple[str, str, Path]] = {
    # Public evidence portal.
    "/": ("index.html", HTML, PUBLIC_DIR),
    "/index.html": ("index.html", HTML, PUBLIC_DIR),
    "/app.js": ("app.js", JS, PUBLIC_DIR),
    "/styles.css": ("styles.css", CSS, PUBLIC_DIR),

    # Operator UI: the review queue and the raw warehouse browser. Unchanged
    # in every respect except the prefix it answers on.
    "/admin": ("index.html", HTML, STATIC_DIR),
    "/admin/": ("index.html", HTML, STATIC_DIR),
    "/admin/index.html": ("index.html", HTML, STATIC_DIR),
    "/admin/app.js": ("app.js", JS, STATIC_DIR),
    "/admin/styles.css": ("styles.css", CSS, STATIC_DIR),
}

# The operator UI's ES modules. app.js stays a classic script -- it works, and
# reloading working review tooling differently buys nothing -- so everything
# added to that page since is a module loaded alongside it. Listed by name for
# the same reason the rest of this map is: no directory walk, no traversal.
for _module in ("shell", "dom", "theme", "palette", "pipeline", "health", "exports"):
    STATIC_FILES[f"/admin/js/{_module}.js"] = (f"js/{_module}.js", JS, STATIC_DIR)

# Portal ES modules, listed rather than globbed for the same reason as above.
for _module in ("theme", "components"):
    STATIC_FILES[f"/js/{_module}.js"] = (f"js/{_module}.js", JS, PUBLIC_DIR)
for _page in ("overview", "pay", "contracts", "geography", "treatment", "providers"):
    STATIC_FILES[f"/js/pages/{_page}.js"] = (f"js/pages/{_page}.js", JS, PUBLIC_DIR)

# Third-party builds, committed under static/public/vendor. See its README for
# versions and provenance.
for _lib, _type in (
    ("echarts.min.js", JS),
    ("d3.min.js", JS),
    ("tabulator.min.js", JS),
    ("tabulator_midnight.min.css", CSS),
    ("fuse.min.js", JS),
    ("date-fns.cdn.min.js", JS),
):
    STATIC_FILES[f"/vendor/{_lib}"] = (f"vendor/{_lib}", _type, PUBLIC_DIR)

# Assets that are large and change only when a source publisher releases new
# ones. These get a cache lifetime; everything else stays no-store.
CACHEABLE_PREFIXES = ("/vendor/",)
ASSET_MAX_AGE = 86_400

# Portal answers change only when a module runs, which is hours apart at best.
# Five minutes keeps chart interaction from re-querying the warehouse for
# numbers it already has, without anyone waiting long to see a fresh run.
PUBLIC_MAX_AGE = 300

MAX_BODY_BYTES = 256 * 1024

# --- Content Security Policy ---------------------------------------------------
#
# Not the primary defence and not a substitute for one. Warehouse values reach
# both pages as text nodes, never as concatenated HTML, and static/app.js
# throws on an `html:` prop to keep it that way. This is the layer underneath
# that: if a value ever does reach the parser, the policy decides whether it
# can then load anything, phone anywhere, or frame this page inside another.
#
# `frame-ancestors 'none'` is the part that earns its place today. This server
# has no authentication by design, so any page on the LAN could otherwise
# frame /admin and drive it with the operator's own browser.
#
# Scripts differ between the two surfaces, which is why the policy is computed
# per path rather than being one constant:
#
#   * The portal has no inline script at all, so it gets `script-src 'self'`
#     with nothing added.
#   * The operator UI has exactly one -- the three lines in <head> that apply a
#     saved theme before the stylesheet paints, which cannot move to a file
#     without reintroducing the flash it exists to prevent. It is allowed by
#     hash, read from the file being served, so editing that script without
#     updating anything here cannot silently leave the page broken: the hash
#     follows the file, and a test asserts the two agree.
#
# `style-src` keeps 'unsafe-inline' on both. The operator UI has five style
# attributes, and the vendored table and chart libraries set styles at
# runtime; hashing attribute styles needs 'unsafe-hashes' and buys little.
# Styles are a defacement vector, not an exfiltration one.
_CSP_COMMON = (
    "default-src 'self'",
    "img-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
)

_INLINE_SCRIPT_RE = re.compile(rb"<script>(.*?)</script>", re.S)


def inline_script_hashes(page: Path) -> tuple[str, ...]:
    """CSP hashes for every inline <script> in a page we serve.

    Read as bytes and hashed as bytes: the browser hashes exactly what is
    between the tags, and reading in text mode would translate CRLF into LF on
    Windows and produce a hash that matches nothing.
    """
    import base64
    import hashlib

    try:
        source = page.read_bytes()
    except OSError:  # pragma: no cover - a missing page is a 404, not a policy
        return ()
    return tuple(
        "'sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode() + "'"
        for body in _INLINE_SCRIPT_RE.findall(source))


def content_security_policy(path: str) -> str:
    """The policy for one response, by which front end it belongs to."""
    script = ["script-src 'self'"]
    if path.startswith("/admin"):
        script.extend(inline_script_hashes(STATIC_DIR / "index.html"))
    return "; ".join((*_CSP_COMMON, " ".join(script)))

# Below this a response is not worth compressing: the CPU and the round trip
# through zlib cost more than the bytes saved, and most replies here are a few
# hundred bytes of JSON.
GZIP_MIN_BYTES = 4 * 1024

# Only text. Compressing an already-compressed payload makes it bigger, and
# nothing here serves images.
GZIP_TYPES = {
    "application/json", "application/geo+json", "text/html", "text/css",
    "text/javascript", "text/csv", "text/plain", "text/markdown",
}

log = structlog.get_logger()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status
        self.message = message


def _flag(params: dict[str, list[str]], name: str, default: bool = False) -> bool:
    value = params.get(name, [None])[0]
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


def _int(params: dict[str, list[str]], name: str, default: int) -> int:
    value = params.get(name, [None])[0]
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        raise ApiError(f"{name} must be a whole number, got {value!r}.") from None


def _str(params: dict[str, list[str]], name: str, default: str = "") -> str:
    return (params.get(name, [default])[0] or "").strip()


class Handler(BaseHTTPRequestHandler):
    """One request. Threaded, so every handler opens and closes its own
    connections rather than sharing one across threads — sqlite3 objects are
    not safe to pass between them, and a connection per request against a
    local file costs microseconds.
    """

    server_version = "cglpay-review-ui"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # A client that opens a connection and then says nothing holds the thread
    # that accepted it, and ThreadingHTTPServer starts one per connection with
    # no ceiling. Without this the class attribute is None and the read blocks
    # forever. Long enough that a phone on a slow LAN finishes its request,
    # short enough that a stalled one is not permanent. Note this bounds the
    # *request*: a long-running job is watched by polling, so no response this
    # server sends is held open for minutes.
    timeout = 30

    # Reset per request in _dispatch. Declared here so the error path is safe
    # even for a request that never reaches it.
    _body_read = False
    _responded = False

    def __init__(self, *args, settings: Settings, jobs: JobRegistry, **kwargs):
        self.settings = settings
        # Shared across every request: the whole point of the registry is that
        # a run started by one request is visible to the next.
        self.jobs = jobs
        super().__init__(*args, **kwargs)

    # --- plumbing -------------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:
        """Requests go to the structured log, not to stderr.

        BaseHTTPRequestHandler writes a line per request to stderr, which in
        this project would interleave with Rich's output and land in whatever
        a run was being teed to. The pipeline already has one place where "what
        happened" is recorded, and it is structlog.
        """
        log.debug("web.request", client=self.address_string(), message=format % args)

    def _accepts_gzip(self) -> bool:
        return "gzip" in (self.headers.get("Accept-Encoding") or "").lower()

    def _send_security_headers(self) -> None:
        """The same four on every response this server sends.

        On every response rather than only on HTML, because a policy that
        depends on remembering to add it to the next route added is a policy
        that will be missing from the next route added. `Referrer-Policy`
        matters here specifically: warehouse state travels in the URL hash --
        `#review?module=m10_committee_papers`, `#database?table=...` -- and a
        link out of the operator UI should not carry the queue someone was
        clearing into a third party's logs.
        """
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                          content_security_policy(urlparse(self.path).path))
        # Redundant beside frame-ancestors for any browser from the last few
        # years, and free for anything older.
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")

    def _send(self, status: int, body: bytes, content_type: str,
               max_age: int | None = None, etag: str | None = None) -> None:
        self._responded = True

        # Compressed above a threshold, and only for things that compress. The
        # payloads that matter are the coverage matrix, a page of a wide table
        # and app.js -- all text, all several times smaller gzipped. Below the
        # threshold the round trip through zlib costs more than the bytes it
        # saves, and on loopback none of this matters at all: it is for the
        # phone on the other side of the LAN, which is a supported way to reach
        # this server.
        encoding = None
        if (len(body) >= GZIP_MIN_BYTES and self._accepts_gzip()
                and content_type.split(";")[0].strip() in GZIP_TYPES):
            import gzip

            compressed = gzip.compress(body, compresslevel=6)
            # Only if it actually helped. Some payloads are already entropy.
            if len(compressed) < len(body):
                body = compressed
                encoding = "gzip"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if encoding:
            self.send_header("Content-Encoding", encoding)
        # Whether or not this particular response was compressed: a cache that
        # keeps one must not serve it to a client that cannot read it.
        self.send_header("Vary", "Accept-Encoding")
        if etag:
            self.send_header("ETag", etag)
        if self.close_connection:
            self.send_header("Connection", "close")
        # Warehouse data is not cacheable: the point of the operator UI is the
        # current state of the queue, and a stale page would show decisions
        # that are not there. Vendored libraries and boundary geometry are the
        # exception — they change when someone replaces a file, not when a
        # module runs — and they are the only things large enough to be worth
        # a round trip. `private` because this server has no authentication
        # and nothing it serves should be held by a shared proxy.
        if max_age:
            self.send_header("Cache-Control", f"max-age={max_age}, private")
        else:
            self.send_header("Cache-Control", "no-store")
        # The API is same-origin only. No CORS headers are ever sent, so a
        # cross-origin page cannot read a reply even if it manages to send a
        # request.
        self._send_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200,
                    max_age: int | None = None) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", max_age=max_age)

    def _discard_body(self) -> None:
        """Read and throw away a request body that was refused unread.

        Rejecting a POST before reading its body leaves those bytes in the
        socket, and keep-alive means the *next* request on that connection
        starts parsing them as a request line. The symptom is a UI that hangs
        or errors several actions after the one that was refused, which is a
        miserable thing to debug. So a refusal reads the body it is refusing —
        or, when the body is too large to be worth reading, hangs up instead.
        """
        if self._body_read:
            return
        self._body_read = True
        try:
            remaining = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            remaining = -1
        if remaining < 0 or remaining > MAX_BODY_BYTES:
            self.close_connection = True
            return
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 64 * 1024))
            if not chunk:
                break
            remaining -= len(chunk)

    def _read_json(self) -> dict:
        # Content-Type is the CSRF guard: a cross-origin POST that a browser
        # will send without asking permission first cannot carry this one.
        content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type != "application/json":
            raise ApiError("Request must be sent as application/json.", status=415)

        origin = self.headers.get("Origin")
        if origin and not self._same_origin(origin):
            raise ApiError(
                f"Refusing a write from another origin ({origin}).", status=403)

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ApiError("Bad Content-Length.") from None
        if length <= 0:
            raise ApiError("Empty request body.")
        if length > MAX_BODY_BYTES:
            raise ApiError("Request body is too large.", status=413)

        self._body_read = True
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(f"Body is not valid JSON: {exc}") from None

    def _same_origin(self, origin: str) -> bool:
        host_header = self.headers.get("Host") or ""
        return urlparse(origin).netloc.lower() == host_header.lower()

    # --- routing --------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - name fixed by BaseHTTPRequestHandler
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def _dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)
        # Per request, not per connection: one handler instance serves every
        # request on a keep-alive connection.
        self._body_read = False
        self._responded = False

        try:
            if path in STATIC_FILES and self.command in ("GET", "HEAD"):
                return self._serve_static(path)
            if path.startswith("/api/"):
                return self._serve_api(path, params)
            raise ApiError(f"No route for {path}", status=404)
        except ApiError as exc:
            self._fail(exc.status, exc.message)
        except JobError as exc:
            # The refusal carries the running job's id, so the page can offer
            # to show it rather than just saying no.
            self._fail(exc.status, exc.message,
                        extra={"job_id": exc.job_id} if exc.job_id else None)
        except queries.QueryError as exc:
            self._fail(400, str(exc))
        except review.DecisionError as exc:
            self._fail(400, str(exc))
        except resolve.ResolveError as exc:
            self._fail(400, str(exc))
        except public_export.ExportError as exc:
            self._fail(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away mid-response. Nothing to report and
            # nowhere to report it to.
            log.debug("web.client_disconnected", path=path)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("web.unhandled", path=path)
            self._fail(500, f"{type(exc).__name__}: {exc}")

    def _fail(self, status: int, message: str, extra: dict | None = None) -> None:
        if self._responded:
            # Something went wrong after the reply was already on the wire —
            # a serialisation error part-way through, or the client going
            # away. A second response would be read as the answer to the
            # *next* request on this connection, so hang up instead.
            self.close_connection = True
            return
        if self.command == "POST":
            self._discard_body()
        if self.path.startswith("/api/"):
            self._send_json({"error": message, **(extra or {})}, status=status)
        else:
            self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        filename, content_type, directory = STATIC_FILES[path]
        file_path = directory / filename
        if not file_path.is_file():
            raise ApiError(f"Missing UI asset {filename}", status=500)

        # Size and modification time, which change together whenever a file is
        # edited. Not a hash of the content: these are read on every request,
        # and hashing 23 MB of vendored ECharts to save sending it is the wrong
        # trade. Weak ("W/") because the byte-for-byte guarantee a strong tag
        # implies is not one an mtime can make.
        stat = file_path.stat()
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        cache = ASSET_MAX_AGE if path.startswith(CACHEABLE_PREFIXES) else None

        if self._matches_etag(etag):
            # 304 carries no body, and must repeat the headers a cache needs to
            # keep using what it already has.
            self._responded = True
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control",
                              f"max-age={cache}, private" if cache else "no-store")
            self.send_header("Vary", "Accept-Encoding")
            # A 304 tells the browser to reuse what it has, and the policy the
            # reused copy renders under is the one sent with *this* response.
            self._send_security_headers()
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            return

        self._send(200, file_path.read_bytes(), content_type, max_age=cache, etag=etag)

    def _matches_etag(self, etag: str) -> bool:
        """Whether the client already holds this version.

        `If-None-Match` may carry several tags, and a weak tag compares by its
        opaque part -- the W/ prefix is about what the tag promises, not about
        which resource it names.
        """
        header = self.headers.get("If-None-Match")
        if not header:
            return False
        mine = etag[2:] if etag.startswith("W/") else etag
        for candidate in header.split(","):
            candidate = candidate.strip()
            if candidate == "*":
                return True
            if candidate.startswith("W/"):
                candidate = candidate[2:]
            if candidate == mine:
                return True
        return False

    def _serve_api(self, path: str, params: dict[str, list[str]]) -> None:
        if self.command == "POST":
            handler = self._post_routes().get(path)
            if handler is None:
                raise ApiError(f"No route for POST {path}", status=404)
            return self._send_json(handler(self._read_json()))

        if self.command not in ("GET", "HEAD"):
            raise ApiError(f"{self.command} is not supported here.", status=405)

        # Before the warehouse is opened: this one serves a file off disk and
        # has no use for a connection.
        if path == "/api/admin/exports/file":
            return self._download_export(params)

        conn = queries.readonly_connection(self.settings)
        try:
            if path == "/api/v1/export":
                return self._export(params, conn)
            # Portal answers change only when a module runs, so a short cache
            # keeps chart interactions from re-querying the warehouse for the
            # same numbers. Operator answers stay no-store: the review queue
            # changes as you work on it.
            max_age = PUBLIC_MAX_AGE if path.startswith("/api/v1/") else None
            self._send_json(self._get(path, params, conn), max_age=max_age)
        finally:
            conn.close()

    def _export(self, params: dict[str, list[str]], conn) -> None:
        """A section's data as CSV or JSON, with its provenance attached.

        The provenance travels in the file, not beside it. An exported CSV
        gets separated from any accompanying note within about a day of
        leaving here, so the filters that produced it and the corpus it came
        from are written into the download itself.
        """
        endpoint = _str(params, "endpoint") or "summary"
        fmt = (_str(params, "format") or "csv").lower()
        if fmt not in ("csv", "json"):
            raise ApiError(f"format must be csv or json, got {fmt!r}.")

        payload = self._public_api(f"/api/v1/{endpoint}", params, conn)
        rows, label = public_export.rows_for(endpoint, payload)
        provenance = public_export.provenance(
            endpoint, {k: v[0] for k, v in params.items()
                        if k not in ("endpoint", "format")})

        stamp = provenance["exported_at"][:10].replace("-", "")
        parts = [p for p in (_str(params, "provider_key"), _str(params, "metric")) if p]
        name = "_".join(["sectorTrace", label, *parts, stamp])

        if fmt == "json":
            body = json.dumps({"_provenance": provenance, label: rows},
                               indent=2, default=str).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            body = public_export.to_csv(rows, provenance).encode("utf-8")
            content_type = "text/csv; charset=utf-8"

        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{name}.{fmt}"')
        self.send_header("X-Provenance", json.dumps(provenance, default=str))
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _download_export(self, params: dict[str, list[str]]) -> None:
        """Hand back one export file, streamed.

        The path is not sanitised, it is matched: `artefacts.resolve_for_download`
        compares it against a listing computed on the spot, so anything that is
        not a file this server just enumerated is simply not found. See that
        module for why it is done that way round.
        """
        wanted = _str(params, "path")
        target = artefacts.resolve_for_download(self.settings, wanted)
        if target is None:
            raise ApiError(f"No export file {wanted!r}.", status=404)

        size = target.stat().st_size
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", artefacts.content_type(target))
        self.send_header("Content-Length", str(size))
        # An attachment always. Some of these are 23 MB of GeoJSON, and none of
        # them is improved by a browser trying to render it in a tab.
        self.send_header("Content-Disposition",
                          f'attachment; filename="{target.name}"')
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

        if self.command == "HEAD":
            return
        with target.open("rb") as handle:
            while True:
                chunk = handle.read(artefacts.CHUNK_BYTES)
                if not chunk:
                    break
                self.wfile.write(chunk)

    # --- read routes ----------------------------------------------------------

    def _get(self, path: str, params: dict[str, list[str]], conn) -> Any:
        if path == "/api/overview":
            return queries.overview(conn, self.settings)

        if path == "/api/schema":
            return {"objects": queries.list_objects(conn)}

        if path == "/api/review":
            return queries.review_items(
                conn,
                status=_str(params, "status", "pending") or "pending",
                module=_str(params, "module") or None,
                item_type=_str(params, "item_type") or None,
                search=_str(params, "q") or None,
                limit=_int(params, "limit", queries.DEFAULT_PAGE_SIZE),
                offset=_int(params, "offset", 0),
                oldest_first=not _flag(params, "newest_first"),
            )

        if path == "/api/review/facets":
            return {**queries.review_facets(conn),
                     "resolvable": resolve.resolvable_types()}

        if path == "/api/overrides":
            return {"overrides": resolve.overrides(conn)}

        # --- admin: the pipeline itself, not the warehouse --------------------

        if path == "/api/admin/modules":
            return admin.modules(conn)

        if path == "/api/admin/health":
            return health.health(conn, self.settings)

        if path == "/api/admin/freshness":
            # Its own route because it is seconds of table scans; see
            # health.freshness for why that is not fixed with an index.
            return {"freshness": health.freshness(conn)}

        if path == "/api/admin/coverage":
            return health.coverage(conn, tier=_str(params, "tier") or "upper")

        if path == "/api/admin/failures":
            return health.failures(
                conn,
                module=_str(params, "module") or None,
                search=_str(params, "q") or None,
                limit=_int(params, "limit", 100),
                offset=_int(params, "offset", 0))

        if path == "/api/admin/exports":
            return artefacts.listing(self.settings)

        if path == "/api/admin/jobs":
            running = self.jobs.running()
            return {"jobs": [job.head() for job in self.jobs.all()],
                     "running": running.id if running else None}

        match = re.fullmatch(r"/api/admin/jobs/(\d+)", path)
        if match:
            job = self.jobs.get(int(match.group(1)))
            if job is None:
                raise ApiError(f"No job {match.group(1)}.", status=404)
            # `after` is a line index, not an offset: the buffer drops its
            # oldest lines on a long run, and an index survives that where a
            # count would silently skip whatever was trimmed.
            lines, next_index = job.since(_int(params, "after", -1))
            return {**job.head(), "log": lines, "next": next_index}

        match = re.fullmatch(r"/api/review/(\d+)", path)
        if match:
            item = queries.review_item(conn, int(match.group(1)))
            if item is None:
                raise ApiError(f"No review item {match.group(1)}.", status=404)
            return item

        match = re.fullmatch(r"/api/table/(.+)", path)
        if match:
            from urllib.parse import unquote

            name = unquote(match.group(1))
            if queries.is_restricted(name) and not _flag(params, "reveal"):
                raise ApiError(
                    f"{name} holds personal data and is excluded from every export "
                    "(constraint 3). Confirm to read it here.",
                    status=403,
                )
            return queries.read_table(
                conn,
                name,
                limit=_int(params, "limit", queries.DEFAULT_PAGE_SIZE),
                offset=_int(params, "offset", 0),
                order_by=_str(params, "order_by") or None,
                descending=_str(params, "dir").lower() == "desc",
                search=_str(params, "q") or None,
            )

        if path.startswith("/api/v1/"):
            return self._public_api(path, params, conn)

        raise ApiError(f"No route for GET {path}", status=404)

    # --- public portal API ----------------------------------------------------

    def _public_api(self, path: str, params: dict[str, list[str]], conn) -> Any:
        """Read-only, no personal data, everything caveated.

        Separate from the operator routes above because the audience is
        different: these answers are meant to be published, and every function
        behind them declares the tables it reads so the no-restricted_
        guarantee is enforced rather than asserted.
        """
        route = path[len("/api/v1/"):].rstrip("/")

        if route == "summary":
            return public_queries.summary(conn)
        if route == "providers":
            return {"providers": public_queries.providers(conn)}
        if route == "authorities":
            return {"authorities": public_queries.authorities(conn)}
        if route == "contracts":
            return public_queries.contracts(
                conn,
                provider_key=_str(params, "provider_key") or None,
                buyer_ons_code=_str(params, "buyer_ons_code") or None,
                year_from=_str(params, "year_from") or None,
                year_to=_str(params, "year_to") or None,
                psr_only=_flag(params, "psr_only"),
                limit=_int(params, "limit", 500))
        if route == "pay":
            return public_queries.pay(
                conn,
                provider_key=_str(params, "provider_key") or None,
                year_from=_str(params, "year_from") or None,
                year_to=_str(params, "year_to") or None)
        if route == "geography":
            metric = _str(params, "metric") or "grant_total"
            return {**public_queries.geography(
                        conn, metric=metric, year=_str(params, "year") or None),
                     "available_years": public_queries.geography_years(conn, metric)}
        if route == "boundaries":
            return public_queries.boundaries(conn)
        if route == "fingertips":
            return public_queries.fingertips(
                conn,
                indicator_id=_str(params, "indicator_id") or None,
                topic=_str(params, "topic") or None,
                ons_code=_str(params, "ons_code") or None,
                substance=_str(params, "substance") or None)

        match = re.fullmatch(r"providers/([a-z0-9_]+)/timeline", route)
        if match:
            return public_queries.provider_timeline(conn, match.group(1))

        raise ApiError(f"No route for GET {path}", status=404)

    # --- write routes ---------------------------------------------------------

    def _post_routes(self) -> dict[str, Callable[[dict], Any]]:
        return {
            "/api/review/decide": self._decide,
            "/api/review/decide-matching": self._decide_matching,
            "/api/review/resolve": self._resolve,
            "/api/check-url": self._check_url,
            "/api/query": self._query,
            "/api/admin/run": self._run,
            "/api/admin/check": self._check,
            "/api/admin/export": self._export_job,
        }

    def _export_job(self, body: dict) -> Any:
        job = admin.start_export(self.jobs, self.settings, body)
        return {**job.head(), "log": job.since(-1)[0], "next": job.since(-1)[1]}

    def _check(self, body: dict) -> Any:
        """Integrity-check the warehouse, as a job.

        A job rather than an inline reply because it reads every page of the
        file. It takes the same single slot a module run takes, which is right:
        both want the whole warehouse, and checking one that is being written
        would report on a moving target.
        """
        settings = self.settings
        job = self.jobs.start(
            kind="check", label="integrity check", args={},
            work=lambda: health.integrity_check(settings),
            thread_names=set())
        return {**job.head(), "log": job.since(-1)[0], "next": job.since(-1)[1]}

    def _run(self, body: dict) -> Any:
        """Start a module run. The only route here that reaches the open web.

        Nothing authenticates this, and the server binds every interface by
        default, so anyone who can reach the UI can start a crawl against real
        public sources under this project's contact email and rate limits.
        That is a known, recorded decision -- see docs/admin-ui-plan.md -- and
        `--host 127.0.0.1` is the lever that closes it.
        """
        job = admin.start_run(self.jobs, self.settings, body)
        return {**job.head(), "log": job.since(-1)[0], "next": job.since(-1)[1]}

    def _check_url(self, body: dict) -> Any:
        """Fetch a candidate URL so the reviewer can see what is there before
        committing to it. Same client, robots and rate limit as a module."""
        conn = db.get_connection(self.settings)
        try:
            return resolve.check_url(str(body.get("url", "")), self.settings, conn)
        finally:
            conn.commit()  # the fetch writes the conditional-request cache
            conn.close()

    def _resolve(self, body: dict) -> Any:
        conn = db.get_connection(self.settings)
        try:
            result = resolve.resolve_authority_url(
                conn,
                item_id=int(body.get("id") or 0),
                url=str(body.get("url", "")),
                resolved_by=str(body.get("resolved_by", "")),
                note=body.get("note"),
                settings=self.settings,
            )
        finally:
            conn.close()

        log.info("web.review_resolved", ons_code=result["ons_code"],
                  field=result["field"], url=result["url"],
                  system=result["system"], resolved_by=result["resolved_by"])
        return result

    def _decide(self, body: dict) -> Any:
        ids = body.get("ids")
        if ids is None and body.get("id") is not None:
            ids = [body["id"]]
        if not isinstance(ids, list):
            raise ApiError("`ids` must be a list of review item ids.")

        conn = db.get_connection(self.settings)
        try:
            result = review.decide(
                conn,
                ids,
                decision=str(body.get("decision", "")),
                decided_by=str(body.get("decided_by", "")),
                note=body.get("note"),
            )
        finally:
            conn.close()

        log.info(
            "web.review_decision",
            decision=result["decision"], decided_by=result["decided_by"],
            updated=len(result["updated"]), unchanged=len(result["unchanged"]),
            missing=len(result["missing"]),
        )
        return result

    def _decide_matching(self, body: dict) -> Any:
        """Decide a whole filtered set. The count the page was showing is sent
        with it and checked against the database inside the transaction."""
        conn = db.get_connection(self.settings)
        try:
            result = review.decide_matching(
                conn,
                decision=str(body.get("decision", "")),
                decided_by=str(body.get("decided_by", "")),
                confirm_count=body.get("confirm_count"),
                note=body.get("note"),
                status=(body.get("status") or "pending"),
                module=(body.get("module") or None),
                item_type=(body.get("item_type") or None),
                search=(body.get("search") or None),
            )
        finally:
            conn.close()

        log.info(
            "web.review_decision_bulk",
            decision=result["decision"], decided_by=result["decided_by"],
            matched=result["matched"], updated=len(result["updated"]),
            module=body.get("module"), item_type=body.get("item_type"),
        )
        return result

    def _query(self, body: dict) -> Any:
        """The SQL box. POSTed rather than GET because a query is a body, not
        a URL, and read-only because the connection it runs on is."""
        sql = str(body.get("sql", ""))
        conn = queries.readonly_connection(self.settings)
        try:
            return queries.run_select(conn, sql, limit=int(body.get("limit") or queries.MAX_PAGE_SIZE))
        finally:
            conn.close()


def local_addresses() -> list[str]:
    """This machine's own IPv4 addresses, best-effort, for printing URLs that
    another device on the network can actually type.

    Link-local (169.254.x) addresses are dropped: Windows keeps one on every
    idle adapter — Bluetooth, unused Ethernet ports, the VPN's spare
    interfaces — and none of them is reachable from anything. What is left can
    still include a VPN address alongside the real LAN one, so these are
    offered as a list rather than guessed between.
    """
    candidates: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if address.startswith(("127.", "169.254.")):
                continue
            if address not in candidates:
                candidates.append(address)
    except OSError:
        # No DNS for the local hostname. Not worth failing a server start over.
        pass
    return candidates


def reachable_urls(host: str, port: int) -> list[str]:
    """The URLs this server can be reached on, most useful first.

    A wildcard bind is the case worth handling: "listening on 0.0.0.0" tells
    nobody what to type into a phone.
    """
    if host in ("0.0.0.0", "::", ""):
        return [f"http://127.0.0.1:{port}"] + [
            f"http://{address}:{port}" for address in local_addresses()]
    return [f"http://{host}:{port}"]


def build_server(settings: Settings | None = None, host: str = "127.0.0.1",
                  port: int = 1801) -> ThreadingHTTPServer:
    """A configured, unstarted server.

    Unstarted so that tests can bind an ephemeral port and drive it directly,
    and so the CLI can report the real port before anything blocks.
    """
    settings = settings or get_settings()
    # The registry is given a store, so the job list opens showing what this
    # warehouse has been asked to do rather than only what has happened since
    # the last restart. A run killed by a crash reappears as interrupted.
    server = ThreadingHTTPServer(
        (host, port),
        partial(Handler, settings=settings,
                 jobs=JobRegistry(store=JobStore(settings))))
    # Sockets held by request threads must not keep the process alive after
    # Ctrl-C; a review UI that needs killing twice is a review UI people leave
    # running by accident.
    server.daemon_threads = True
    return server


def serve(settings: Settings | None = None, host: str = "127.0.0.1",
           port: int = 1801) -> None:
    server = build_server(settings, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
