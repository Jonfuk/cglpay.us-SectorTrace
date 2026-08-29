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
import secrets
import socket
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

import structlog

from pipeline import census_verify, db, promote
from pipeline import claims as claims_core
from pipeline.claims import ClaimError
from pipeline.config import Settings, get_settings
from pipeline.web import (
    admin,
    artefacts,
    candidates,
    census,
    claim_review,
    claims,
    degrade,
    health,
    name_matches,
    openapi,
    public_export,
    public_queries,
    queries,
    resolve,
    review,
    semantic,
)
from pipeline.web.cache import Cache, NullCache, get_cache
from pipeline.web.jobs import JobError, JobRegistry, JobStore
from pipeline.web.ratelimit import TokenBucketLimiter

STATIC_DIR = Path(__file__).resolve().parent / "static"
PUBLIC_DIR = STATIC_DIR / "public"

HTML = "text/html; charset=utf-8"
JS = "text/javascript; charset=utf-8"
CSS = "text/css; charset=utf-8"
FONT = "font/woff2"

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

    # The API documentation. `/api` is the address a reader would guess, and it
    # reaches this page rather than the API dispatcher because _dispatch checks
    # this map before it checks the /api/ prefix — deliberately, and pinned by
    # a test, because the alternative is documenting the API at an address
    # nobody would try.
    "/api": ("api.html", HTML, PUBLIC_DIR),
    "/api.html": ("api.html", HTML, PUBLIC_DIR),

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
for _module in ("shell", "dom", "context", "theme", "palette", "pipeline",
                 "health", "exports", "candidates", "census", "claims", "search",
                 "claimreview"):
    STATIC_FILES[f"/admin/js/{_module}.js"] = (f"js/{_module}.js", JS, STATIC_DIR)

# Portal ES modules, listed rather than globbed for the same reason as above.
for _module in ("theme", "components", "palette", "filterstate", "myarea",
                 "recent", "notebook", "savedsearch", "journey"):
    STATIC_FILES[f"/js/{_module}.js"] = (f"js/{_module}.js", JS, PUBLIC_DIR)
for _page in ("overview", "pay", "contracts", "geography", "treatment", "providers",
              "pfd", "authority", "compare", "claims", "coverage", "relationships",
              "documents", "catalogue", "cqc", "changes", "calendar",
              "revisions", "pathfinder", "timeline",
              "cooccurrence", "discrepancies", "diary", "links",
              "doctables"):
    STATIC_FILES[f"/js/pages/{_page}.js"] = (f"js/pages/{_page}.js", JS, PUBLIC_DIR)

# Third-party builds, committed under static/public/vendor. See its README for
# versions and provenance.
for _lib, _type in (
    ("echarts.min.js", JS),
    ("d3.min.js", JS),
    ("tabulator.min.js", JS),
    ("tabulator_midnight.min.css", CSS),
    ("maplibre-gl.js", JS),
    ("maplibre-gl.css", CSS),
    ("fuse.min.js", JS),
    ("bootstrap.min.css", CSS),
    ("bootstrap.bundle.min.js", JS),
):
    STATIC_FILES[f"/vendor/{_lib}"] = (f"vendor/{_lib}", _type, PUBLIC_DIR)

for _font in ("manrope-400.woff2", "manrope-600.woff2", "manrope-700.woff2",
              "space-grotesk-500.woff2", "space-grotesk-700.woff2",
              "archivo-narrow-500.woff2", "archivo-narrow-700.woff2"):
    STATIC_FILES[f"/fonts/{_font}"] = (f"fonts/{_font}", FONT, PUBLIC_DIR)

# Build-time-generated presentational assets — not evidence, not queried, and
# regenerated by hand only when their source changes (see each generator's
# own docstring). The overview hero's England silhouette is a simplified
# dissolve of the authority boundaries /api/v1/boundaries already serves in
# full; see scripts/generate_region_outline.py for why it is a separate,
# much smaller file rather than that same 14MB payload.
for _asset, _type in (
    ("england-regions.json", "application/json; charset=utf-8"),
):
    STATIC_FILES[f"/assets/{_asset}"] = (f"assets/{_asset}", _type, PUBLIC_DIR)

# Assets that are large and change only when a source publisher releases new
# ones. These get a cache lifetime; everything else stays no-store.
CACHEABLE_PREFIXES = ("/vendor/", "/fonts/", "/assets/")
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
    "img-src 'self' data: https://*.basemaps.cartocdn.com https://tiles.basemaps.cartocdn.com",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' https://basemaps.cartocdn.com https://*.basemaps.cartocdn.com https://tiles.basemaps.cartocdn.com",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
)

_INLINE_SCRIPT_RE = re.compile(rb"<script>(.*?)</script>", re.S)


def inline_script_hashes(page: Path) -> tuple[str, ...]:
    """CSP hashes for every inline <script> in a page we serve.

    Read as bytes, then normalised to LF before hashing, because that is what
    the browser hashes. An HTML parser converts CRLF and lone CR to LF while
    tokenising, so the script text a page executes never contains a CR
    whatever the file on disk holds -- and on Windows the file frequently
    does. Hashing the raw bytes produces a policy that blocks the very script
    it was computed from.

    This is not theoretical and a unit test will not catch it: a test that
    recomputes the hash the same way agrees with itself no matter which of the
    two is right. It was found by loading the page and reading the console.
    """
    import base64
    import hashlib

    try:
        source = page.read_bytes()
    except OSError:  # pragma: no cover - a missing page is a 404, not a policy
        return ()
    return tuple(
        "'sha256-" + base64.b64encode(
            hashlib.sha256(body.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
            .digest()).decode() + "'"
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


# CR and LF, the two characters that end an HTTP header line. See
# `Handler.send_header`.
_HEADER_BREAK = re.compile(r"[\r\n]")

# What a generated filename may contain. Everything else becomes a hyphen:
# these values reach a quoted `filename="…"` in a Content-Disposition header,
# where a quote or a semicolon changes what the header means.
_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")

# Long enough for a provider key or a metric name, short enough that a
# filename stays a filename.
_NAME_PART_MAX = 64


def _safe_name_part(value: str) -> str:
    return _NAME_UNSAFE.sub("-", value).strip("-")[:_NAME_PART_MAX]


def _str(params: dict[str, list[str]], name: str, default: str = "") -> str:
    return (params.get(name, [default])[0] or "").strip()


# Public routes whose payload changes only on a rare collection run, not on the
# minute-to-minute cadence the default TTL is sized for. They still invalidate
# on a completed run like everything else; the long TTL is only their backstop.
# A set so a second near-static route (authorities is the obvious next one)
# joins by name rather than by another branch.
_NEAR_STATIC_ROUTES = frozenset({"boundaries"})


def _cache_ttl(path: str, settings: Settings) -> float:
    """How long a public payload may be served before it is recomputed.

    Most /api/v1/* answers move when a module runs, and the completed run drops
    them the instant they do (bump_version), so the TTL is only a backstop for
    a write that never went through a job. A near-static route can carry a much
    longer one: boundaries is authority geometry, parsed out of the warehouse
    into a large GeoJSON on every miss and changed only by an m00 run, so a day
    means it is built once daily instead of every few minutes -- without ever
    outliving a real change, which the version bump still clears at once.
    """
    route = path[len("/api/v1/"):].rstrip("/")
    if route in _NEAR_STATIC_ROUTES:
        return settings.cache_static_ttl_seconds
    return settings.cache_ttl_seconds


def _cache_key(path: str, params: dict[str, list[str]]) -> str:
    """A stable cache key for a public read: the route and its query.

    Query-parameter *order* never changes an answer, so the keys are sorted and
    two requests that differ only in key order share an entry. Repeated-value
    order is *not* sorted, because it can matter -- /api/v1/compare?ons_code=A&
    ons_code=B draws its series in that order -- so [A,B] and [B,A] are kept as
    distinct keys rather than risk one request being served the other's
    payload. Caching both costs an entry; conflating them would be a wrong
    answer, which this project never trades for a smaller cache.
    """
    items = sorted((name, list(values)) for name, values in params.items())
    return path + "?" + json.dumps(items, separators=(",", ":"))


def _claim_id(body: dict) -> int:
    """The claim id a write route was sent, as an int, or a refusal.

    In a helper rather than inline in five handlers because the refusals must
    agree: a claim id that is not a whole number is a request error, not a
    ClaimError about the claim.
    """
    try:
        return int(body.get("claim_id") or 0)
    except (TypeError, ValueError):
        raise ApiError("claim_id must be a whole number.") from None


def _contract_query(params: dict[str, list[str]]) -> dict:
    """The contract filters a request carries, as query keyword arguments.

    Here rather than inline in the route because two callers need exactly the
    same set: the page's windowed read and the export's complete one. A filter
    understood by one and not the other would produce a download that does not
    match the table it was offered beneath.
    """
    return {
        "provider_key": _str(params, "provider_key") or None,
        "buyer_ons_code": _str(params, "buyer_ons_code") or None,
        "year_from": _str(params, "year_from") or None,
        "year_to": _str(params, "year_to") or None,
        "psr_only": _flag(params, "psr_only"),
        # BETA-040. Both callers get these so the download matches the table:
        # a case-insensitive buyer/supplier name search and a retrieved-since
        # bound. `limit`/`offset` are the page's alone — the export is always
        # the complete matching set.
        "q": _str(params, "q") or None,
        "since_retrieved_at": _str(params, "since_retrieved_at") or None,
    }


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

    def __init__(self, *args, settings: Settings, jobs: JobRegistry,
                 rate_limiter: TokenBucketLimiter | None = None,
                 cache: Cache | None = None, **kwargs):
        self.settings = settings
        # Shared across every request: the whole point of the registry is that
        # a run started by one request is visible to the next.
        self.jobs = jobs
        # Shared across every request too, and for the same reason a token
        # bucket exists at all: a per-connection one would reset every time a
        # client opened a new connection, which is exactly what a scraper
        # working around it would do.
        self.rate_limiter = rate_limiter
        # Shared for the same reason again: an in-process cache is only worth
        # having if the entry one request populates is there for the next.
        # NullCache when unset, so a Handler built without one behaves exactly
        # as it did before the cache existed.
        self.cache = cache if cache is not None else NullCache()
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

    def send_header(self, keyword: str, value: Any) -> None:
        """Every header this server sends, with CR and LF taken out of it.

        `BaseHTTPRequestHandler.send_header` formats `"%s: %s\\r\\n"` and
        validates nothing, so a value carrying its own CRLF ends the header and
        starts another one. That is HTTP response splitting, and it was live
        here: `_export_name` interpolated the `provider_key` and `metric` query
        parameters straight into `Content-Disposition`, so

            /api/v1/export?endpoint=summary&format=csv&provider_key=x%0d%0aX-Injected:%20yes

        put `X-Injected` in the response. Confirmed over a raw socket before
        this was written, and pinned by
        `tests/test_web_security_headers.py`. CodeQL had been reporting it as
        `py/http-response-splitting` since the scan was first switched on; it
        sat in the untriaged pile that finding O-05 records.

        The names are fixed by this file, so only the values are a real risk —
        but both are checked, because the cost is a regex and the argument for
        checking one and not the other is the kind that stops being true later.

        Stripping rather than refusing, which is the opposite of what this
        project usually does. A refusal here would raise part-way through
        writing a response whose status line has already gone out, turning a
        blocked attack into a broken connection and a stack trace. So the value
        is made safe and the attempt is logged loudly — the log line is what
        makes it visible, and the strip is what makes it harmless.

        This is the backstop. `_export_name` sanitises at the source as well,
        because a filename containing a quote or a semicolon still produces a
        `Content-Disposition` that parses wrongly without ever touching a
        newline.
        """
        text = str(value)
        if _HEADER_BREAK.search(text) or _HEADER_BREAK.search(str(keyword)):
            log.warning("web.header_break_stripped", header=str(keyword),
                         client=self.address_string())
            keyword = _HEADER_BREAK.sub(" ", str(keyword))
            text = _HEADER_BREAK.sub(" ", text)
        super().send_header(keyword, text)

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
               max_age: int | None = None, etag: str | None = None,
               extra_headers: dict[str, str] | None = None) -> None:
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
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        # The API is same-origin only. No CORS headers are ever sent, so a
        # cross-origin page cannot read a reply even if it manages to send a
        # request.
        self._send_security_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200,
                    max_age: int | None = None,
                    extra_headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8",
                   max_age=max_age, extra_headers=extra_headers)

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

    def _client_ip(self) -> str:
        """The address rate limiting keys on.

        `X-Forwarded-For`'s first hop, when present, else the direct TCP
        peer. Every real deployment puts a reverse proxy in front and the
        app is not otherwise reachable — the Docker builds publish the app's
        own port on loopback only, and Caddy is the sole way in; Railway's
        edge is the equivalent there. A spoofed header sent straight to an
        unproxied `./start.sh web` only ever lets someone evade their own
        local rate limit, which is not worth defending against.
        """
        forwarded = self.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

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
            if not self.settings.admin_ui_enabled and (
                path == "/admin" or path.startswith("/admin/")
                or path == "/api/admin" or path.startswith("/api/admin/")
            ):
                raise ApiError(f"No route for {path}", status=404)
            if path == "/health" and self.command in ("GET", "HEAD"):
                # Process-level readiness probe. Schema migration runs before
                # the server starts; keeping this endpoint dependency-free
                # means Railway can distinguish a live HTTP process from a
                # database query failure reported by the application APIs.
                return self._send(200, b"ok\n", "text/plain; charset=utf-8",
                                  max_age=0)
            if path in STATIC_FILES and self.command in ("GET", "HEAD"):
                return self._serve_static(path)
            # /api/v1/* only: the public, unauthenticated API a scraper can
            # reach. /api/admin/* is the operator's own tooling, gated on
            # trust in the network it is bound to rather than on request
            # rate — see the settled decisions in CLAUDE.md.
            if (path.startswith("/api/v1/") and self.rate_limiter is not None
                    and self.settings.api_rate_limit_enabled):
                retry_after = self.rate_limiter.check(self._client_ip())
                if retry_after is not None:
                    return self._send_json(
                        {"error": "Too many requests. Slow down and try again shortly."},
                        status=429,
                        extra_headers={"Retry-After": str(max(1, int(retry_after) + 1))},
                    )
            if path.startswith("/api/"):
                return self._serve_api(path, params)
            raise ApiError(f"No route for {path}", status=404)
        except degrade.FeatureUnavailable as exc:
            # A capability that cannot be served on this build (BETA-068):
            # a missing migration, an absent extension, a section timeout.
            # The reader gets a bounded unavailable state naming the feature,
            # never the underlying SQL.
            self._fail(exc.status, exc.message,
                        detail=self._feature_detail(exc))
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
        except ClaimError as exc:
            self._fail(400, str(exc))
        except public_export.ExportError as exc:
            self._fail(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away mid-response. Nothing to report and
            # nowhere to report it to.
            log.debug("web.client_disconnected", path=path)
        except Exception as exc:  # pragma: no cover - defensive
            # Before the generic 500: a raw database error that is really
            # schema drift (a table or column this build has not migrated in,
            # a cancelled slow query) becomes a bounded feature-unavailable
            # state rather than a traceback in the page (BETA-068).
            drift = degrade.classify_db_error(exc)
            if drift is not None:
                log.warning("web.feature_unavailable", path=path,
                            feature=drift.feature, code=drift.code,
                            cause=f"{type(exc).__name__}: {exc}")
                return self._fail(drift.status, drift.message,
                                   detail=self._feature_detail(drift))
            log.exception("web.unhandled", path=path)
            self._fail(500, f"{type(exc).__name__}: {exc}")

    def _feature_detail(self, exc: degrade.FeatureUnavailable) -> dict:
        """The additive `error_detail` object for a feature-unavailable reply.

        `error` stays the human string the portal and the existing tests
        read; this rides alongside it with the machine-actionable fields:
        a stable code, whether a retry is worth offering, the feature name,
        this build's identity, and a short `ref` also written to the log so
        an operator can find the cause without the reader ever seeing it.
        """
        ref = secrets.token_hex(4)
        build = {
            "revision": self.settings.git_revision or None,
            "build_time": self.settings.build_time or None,
            "environment": self.settings.environment,
        }
        schema: dict[str, Any] = {"available": False}
        try:
            conn = queries.readonly_connection(self.settings)
            try:
                applied = db.applied_migrations(conn)
                schema = {
                    "available": True,
                    "latest_migration": degrade.max_applied_migration(applied),
                    "applied_count": len(applied),
                }
            finally:
                conn.close()
        except Exception:  # pragma: no cover - the DB itself may be the fault
            pass
        log.info("web.feature_unavailable.ref", ref=ref, feature=exc.feature,
                  code=exc.code)
        return {
            "code": exc.code,
            "message": exc.message,
            "retryable": bool(exc.retryable),
            "feature": exc.feature,
            "build": build,
            "schema": schema,
            "ref": ref,
        }

    def _fail(self, status: int, message: str, extra: dict | None = None,
               detail: dict | None = None) -> None:
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
            body: dict[str, Any] = {"error": message, **(extra or {})}
            if detail is not None:
                body["error_detail"] = detail
            self._send_json(body, status=status)
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

        # The OpenAPI 3.1 description of the public API (BETA-048). A static
        # document — no warehouse read — and a sibling of `/api` (the HTML
        # page), not a `/api/v1/*` route. `tests/test_web_openapi.py` binds
        # its paths to the frozen public surface.
        if path == "/api/openapi.json":
            return self._send_json(openapi.document(), max_age=PUBLIC_MAX_AGE)

        conn = queries.readonly_connection(self.settings)
        try:
            if path == "/api/v1/export":
                return self._export(params, conn)
            if path == "/api/v1/feed/changes.atom":
                # BETA-089: the "what changed?" stream as a stable Atom feed,
                # same kind/source/since filter as /api/v1/changes. A raw XML
                # body, so it goes out here rather than through _send_json.
                return self._feed_changes(params, conn)
            # Portal answers change only when a module runs, so a short cache
            # keeps chart interactions from re-querying the warehouse for the
            # same numbers. Operator answers stay no-store: the review queue
            # changes as you work on it.
            max_age = PUBLIC_MAX_AGE if path.startswith("/api/v1/") else None
            if path.startswith("/api/v1/"):
                # The server-side twin of that max-age header: an in-process
                # cache over the same derived payloads, so a warehouse hot with
                # a page's worth of chart requests answers most of them without
                # touching the aggregates again. Only /api/v1/* (public,
                # read-only, guard_columns-checked, invalidated by a completed
                # run); operator routes fall through and are recomputed every
                # time, because the queue changes as you work on it. NullCache
                # unless CACHE_ENABLED, so this is a no-op by default. The
                # connection is still opened above -- the cache saves the query,
                # not the connect, and moving the check earlier would tangle
                # with the export and admin branches for a microsecond.
                payload = self.cache.get_or_compute(
                    _cache_key(path, params),
                    _cache_ttl(path, self.settings),
                    lambda: self._get(path, params, conn))
            else:
                payload = self._get(path, params, conn)
            self._send_json(payload, max_age=max_age)
        finally:
            conn.close()

    def _export(self, params: dict[str, list[str]], conn) -> None:
        """A section's data as CSV or JSON, with its provenance attached.

        The provenance travels in the file, not beside it. An exported CSV
        gets separated from any accompanying note within about a day of
        leaving here, so the filters that produced it, the corpus it came from
        and how many rows it holds are written into the download itself.

        Two paths, and which one an endpoint takes is a property of the
        endpoint rather than of the request. Everything whose `/api/v1` payload
        *is* the dataset is built in memory and sent with a Content-Length.
        Everything whose payload is a window onto something larger — see
        `public_export.WINDOWED` — is read again, in full, by its own query and
        streamed. A download must never be the page's slice: that was W-06,
        where the contracts CSV shipped 500 rows of 98,636 and said nothing.
        """
        endpoint = _str(params, "endpoint") or "summary"
        fmt = (_str(params, "format") or "csv").lower()
        if fmt not in ("csv", "json"):
            raise ApiError(f"format must be csv or json, got {fmt!r}.")

        # `limit`/`offset` page the on-screen table (BETA-040); an export is
        # always the complete matching set, so they are not filters and must
        # not be written into the file's `filters_applied` line as if they
        # were.
        filters = {k: v[0] for k, v in params.items()
                    if k not in ("endpoint", "format", "limit", "offset")}

        if endpoint in public_export.WINDOWED:
            return self._export_complete(endpoint, fmt, filters, params, conn)

        payload = self._public_api(f"/api/v1/{endpoint}", params, conn)
        rows, label = public_export.rows_for(endpoint, payload)
        provenance = public_export.provenance(endpoint, filters, row_count=len(rows))

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
        self.send_header("Content-Disposition",
                          f'attachment; filename="{self._export_name(label, params)}.{fmt}"')
        self.send_header("X-Provenance", json.dumps(provenance, default=str))
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _feed_changes(self, params: dict[str, list[str]], conn) -> None:
        """The change feed as Atom 1.0. Raw XML, cached like the rest of
        /api/v1/*, with host-independent entry ids so a subscription survives
        a move between hosts."""
        from urllib.parse import urlencode

        from pipeline.web import feeds

        proto = (self.headers.get("X-Forwarded-Proto") or "http").split(",")[0].strip()
        host = self.headers.get("Host") or "localhost"
        query = {k: v[0] for k, v in params.items() if k in ("kind", "source", "since")}
        self_url = (f"{proto}://{host}/api/v1/feed/changes.atom"
                    + (f"?{urlencode(query)}" if query else ""))
        body = feeds.changes_atom(
            conn,
            kind=_str(params, "kind") or None,
            source=_str(params, "source") or None,
            since=_str(params, "since") or None,
            self_url=self_url).encode("utf-8")

        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", "application/atom+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", f"public, max-age={PUBLIC_MAX_AGE}")
        self._send_security_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _export_complete(self, endpoint: str, fmt: str, filters: dict,
                          params: dict[str, list[str]], conn) -> None:
        """Every row of a windowed endpoint, streamed.

        The count is taken first, because it goes in the header line above rows
        that have not been read yet, and it is what makes this file honest: a
        reader can see that 98,636 is the number of notices matching these
        filters and that 98,636 is what they were sent.
        """
        if endpoint == "contracts":
            total, rows = public_queries.all_contract_notices(
                conn, **_contract_query(params))
            _, label = public_export.rows_for(endpoint, {"notices": []})
        elif endpoint == "pfd":
            total, rows = public_queries.all_pfd_reports(conn)
            _, label = public_export.rows_for(endpoint, {"recent": []})
        else:  # pragma: no cover - every WINDOWED member is handled above
            raise ApiError(f"No complete reader for {endpoint!r}.", status=500)

        provenance = public_export.provenance(endpoint, filters, row_count=total)
        name = f"{self._export_name(label, params)}.{fmt}"

        if fmt == "json":
            # JSON is one document, so it is built rather than streamed. The
            # audience for a 40 MB JSON array is a program, and a program that
            # cannot hold it cannot parse it either.
            body = json.dumps({"_provenance": provenance, label: list(rows)},
                               indent=2, default=str).encode("utf-8")
            self._responded = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
            self.send_header("X-Provenance", json.dumps(provenance, default=str))
            self.send_header("Cache-Control", "no-store")
            self._send_security_headers()
            if self.close_connection:
                self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            return

        self._send_chunked(
            public_export.stream_csv(rows, provenance, total),
            "text/csv; charset=utf-8", name, provenance)

    def _export_name(self, label: str, params: dict[str, list[str]]) -> str:
        """The download's filename, built from what was asked for.

        `provider_key` and `metric` come from the query string and land in a
        `Content-Disposition` header, so they are reduced to the characters a
        filename may contain rather than interpolated. Two separate problems
        are being avoided and only one of them involves a newline: a value
        carrying `"` or `;` ends the quoted filename and adds a parameter to
        the header, which needs no control character at all.

        `send_header` strips CR and LF as a backstop — see its docstring, and
        the response-splitting hole this pair of fixes closed.
        """
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        parts = [_safe_name_part(p) for p
                  in (_str(params, "provider_key"), _str(params, "metric"))]
        return "_".join(["sectorTrace", label, *[p for p in parts if p], stamp])

    def _send_chunked(self, chunks, content_type: str, filename: str,
                       provenance: dict) -> None:
        """A response whose length is not known when the headers go out.

        Chunked transfer encoding rather than `Connection: close`, because this
        is an HTTP/1.1 server and a keep-alive connection that ends by hanging
        up is indistinguishable from a truncated one at the far end.

        Which is also the reason the terminating chunk is only written after
        the producer finishes: if the export raises part-way — and
        `stream_csv` deliberately raises when the rows it wrote disagree with
        the count in the header it already sent — the response ends without its
        terminator, and every HTTP client treats that as a failed download.
        A broken download is recoverable. A complete-looking file with the
        wrong rows in it is not.
        """
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("X-Provenance", json.dumps(provenance, default=str))
        self.send_header("Cache-Control", "no-store")
        self._send_security_headers()
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

        if self.command == "HEAD":
            return

        for chunk in chunks:
            if not chunk:
                continue
            self.wfile.write(f"{len(chunk):x}\r\n".encode("ascii"))
            self.wfile.write(chunk)
            self.wfile.write(b"\r\n")
        self.wfile.write(b"0\r\n\r\n")

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

        if path == "/api/admin/schema-graph":
            # BETA-083: a read-only schema graph — tables, columns, FK edges
            # and short descriptions — from the existing catalogue helpers.
            return queries.schema_graph(conn)

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

        if path == "/api/review/clusters":
            # Pending items grouped by (module, item_type, org token) —
            # display only (BETA-053). Bulk actions still recount.
            return queries.review_clusters(
                conn, status=_str(params, "status", "pending") or "pending")

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

        if path == "/api/admin/storage":
            # And this one because it is seconds of stat calls over the raw
            # archive -- 8,502 files and 4.5 GB on the warehouse it was
            # measured against.
            return {"storage": health.storage(self.settings)}

        if path == "/api/admin/coverage":
            return health.coverage(conn, tier=_str(params, "tier") or "upper")

        if path == "/api/admin/pg-capabilities":
            # BETA-063: extension + extension-backed-index readiness and the
            # list of query paths currently on their fallback. Read-only.
            from pipeline import pg_capabilities

            return pg_capabilities.report(conn)

        if path == "/api/admin/failures":
            return health.failures(
                conn,
                module=_str(params, "module") or None,
                search=_str(params, "q") or None,
                limit=_int(params, "limit", 100),
                offset=_int(params, "offset", 0))

        # Semantic-analysis retrieval (BETA-034A). A finding aid over parsed
        # committee papers / CDP documents: keyword, semantic or hybrid search
        # of `document_chunks`, each result carrying its source URL and page.
        # Admin-only by the same rule as everything else here -- it reads the
        # archive, not `restricted_` data, but it is the operator's tool.
        if path == "/api/admin/search":
            return semantic.search(
                conn,
                query=_str(params, "q") or "",
                mode=_str(params, "mode") or "hybrid",
                limit=_int(params, "limit", 20),
                source_system=_str(params, "source_system") or None,
                date_from=_str(params, "date_from") or None,
                date_to=_str(params, "date_to") or None)

        # The semantic claim-candidate review workbench (BETA-047). List and
        # detail read `document_claim_candidates`; the gate report is
        # `pipeline/nlp/gate.check` verbatim. Deciding is a POST, one at a time.
        if path == "/api/admin/claim-candidates":
            return claim_review.listing(
                conn,
                status=_str(params, "status") or None,
                predicate=_str(params, "predicate") or None,
                source_system=_str(params, "source_system") or None,
                q=_str(params, "q") or None,
                offset=_int(params, "offset", 0),
                limit=_int(params, "limit", claim_review.PAGE))

        match = re.fullmatch(r"/api/admin/claim-candidates/([A-Za-z0-9_:-]{1,120})", path)
        if match:
            return claim_review.detail(conn, match.group(1))

        if path == "/api/admin/claim-gate":
            return claim_review.gate(conn)

        if path == "/api/admin/claim-ontology":
            return claim_review.ontology_options(conn)

        if path == "/api/admin/candidates":
            kind = _str(params, "kind") or "cdp_document"
            try:
                return candidates.listing(
                    conn, kind,
                    status=_str(params, "status") or "undecided",
                    authority=_str(params, "authority") or None,
                    search=_str(params, "q") or None,
                    offset=_int(params, "offset", 0),
                    limit=_int(params, "limit", candidates.PAGE))
            except promote.PromotionError as exc:
                raise ApiError(str(exc), status=400) from None

        if path == "/api/admin/candidates/counts":
            return {"kinds": candidates.counts(conn),
                     "promotions": promote.history(conn, limit=20)}

        if path == "/api/admin/candidates/authorities":
            try:
                return {"authorities": candidates.authorities_with_candidates(
                    conn, _str(params, "kind") or "cdp_document")}
            except promote.PromotionError as exc:
                raise ApiError(str(exc), status=400) from None

        if path == "/api/admin/candidates/detail":
            try:
                found = candidates.detail(conn, _str(params, "kind") or "",
                                           _str(params, "url") or "")
            except promote.PromotionError as exc:
                raise ApiError(str(exc), status=400) from None
            if found is None:
                raise ApiError("No such candidate.", status=404)
            return found

        # The census worklist. Separate from /api/admin/candidates because the
        # act is different -- nothing is fetched and nothing crosses into
        # another table; a figure already in the warehouse is checked against a
        # page already archived. See pipeline/census_verify.py.
        if path == "/api/admin/census":
            try:
                return census.listing(
                    conn,
                    year=_int(params, "year", 0) or None,
                    status=_str(params, "status") or "unchecked",
                    offset=_int(params, "offset", 0),
                    limit=_int(params, "limit", census.PAGE))
            except census_verify.VerificationError as exc:
                raise ApiError(str(exc), status=400) from None

        if path == "/api/admin/census/counts":
            return {**census.counts(conn),
                     "stale": census_verify.stale(conn),
                     "decisions": census_verify.history(conn, limit=20)}

        # The archived page text a figure is checked against. The whole reason
        # this screen can replace the markdown worklist rather than duplicate
        # it: the line is what was parsed, the page is what it meant.
        if path == "/api/admin/census/page":
            try:
                return census.page_text(conn, _int(params, "year", 0),
                                         _int(params, "page", -1))
            except census_verify.VerificationError as exc:
                raise ApiError(str(exc), status=404) from None

        # The claim worklist. Separate from /api/admin/candidates and
        # /api/admin/census because the act is different yet again: nothing is
        # fetched and nothing crosses into another table; a claim is a
        # statement, written by a person and linked to evidence rows the
        # person picked, and deciding it is the same named-person act the
        # other two record. See pipeline/claims.py.
        if path == "/api/admin/claims":
            return claims.listing(
                conn,
                status=_str(params, "status") or "all",
                offset=_int(params, "offset", 0),
                limit=_int(params, "limit", claims.PAGE))

        if path == "/api/admin/claims/counts":
            return claims.counts(conn)

        # The evidence-row picker behind the Citations box: rows of a citable
        # table that match a search term, as {key, label, url} candidates.
        # Called with no table it returns the citable list instead, so the
        # picker can build its select without a second route.
        if path == "/api/admin/claims/evidence":
            try:
                table = _str(params, "table")
                if not table:
                    return {"tables": claims_core.citable_tables(), "rows": []}
                return {"rows": claims.evidence_search(
                    conn,
                    table=table,
                    q=_str(params, "q") or "",
                    limit=_int(params, "limit", 20))}
            except ClaimError as exc:
                raise ApiError(str(exc), status=400) from None

        if path == "/api/admin/exports":
            listed = artefacts.listing(self.settings)
            return {**listed,
                     "staleness": artefacts.staleness(
                         self.settings, conn, listed["files"])}

        if path == "/api/admin/url-overlaps":
            # Candidate URL overlap signals (BETA-057): one canonical URL
            # appearing in more than one source table. A lead, not proof.
            from pipeline.web import url_overlaps
            return url_overlaps.overlaps(conn, limit=_int(params, "limit", 200))

        if path == "/api/admin/aliases":
            # Human alias-resolution workflow (BETA-056): unmatched names for
            # one scheme with their append-only decision history.
            from pipeline.web import alias_resolution
            return alias_resolution.unresolved(
                conn, scheme=_str(params, "scheme", "buyer") or "buyer",
                limit=_int(params, "limit", 100))

        if path == "/api/admin/aliases/verified":
            from pipeline.web import alias_resolution
            return alias_resolution.verified(conn)

        if path == "/api/admin/archive-audits":
            # The append-only archive audit history (BETA-060). Read-only —
            # recording a new one is the `pipeline archive-audit` CLI.
            from pipeline import archive_audit
            return {"audits": archive_audit.history(
                conn, _int(params, "limit", 30))}

        if path == "/api/admin/completeness":
            # The coverage completion action board (BETA-059): one reason
            # code + one non-destructive next step per catalogued dataset.
            from pipeline.web import completeness_board
            return completeness_board.board(conn)

        if path == "/api/admin/cockpit":
            # BETA-086: the operator action cockpit — prioritised cards over
            # operational state, each with a deterministic reason and a link
            # to a pre-filtered workflow. Read-only.
            from pipeline.web import cockpit
            return cockpit.overview(conn, self.settings)

        if path == "/api/admin/run-ledger":
            # The durable run ledger (BETA-058) — every module-run, whatever
            # entry point started it, not only the browser-started jobs.
            # Preflighted (BETA-068): a checkout without migration 0073 gets a
            # named unavailable state, not a `no such table: run_ledger`.
            degrade.preflight(conn, "run_ledger")
            from pipeline import run_ledger
            return {"runs": run_ledger.recent(conn, _int(params, "limit", 20))}

        if path == "/api/admin/mission-control":
            # BETA-082: one read model over the module registry, the active
            # job and the run ledger. Read-only; the run route is untouched.
            degrade.preflight(conn, "run_ledger")
            from pipeline.web import mission_control
            return mission_control.overview(conn, self.settings, self.jobs)

        if path == "/api/admin/validation-rules":
            # BETA-104: a read-only catalogue of the warehouse's validation
            # rules — promotion/decision triggers, CHECK and provenance
            # constraints, and the observed parse_failures / review_queue
            # gates — each with a purpose and recent counts. Failure examples
            # are reduced to their shape; the raw fragment never leaves here.
            from pipeline.web import validation
            return validation.rules(conn, today=_str(params, "today") or None)

        if path == "/api/admin/lineage":
            # BETA-102: one typed graph over the module registry, the dataset
            # catalogue, the live foreign keys and the export tab registry —
            # source -> module -> table -> table -> export. Every edge is
            # derived; none is hand-maintained. Read-only.
            from pipeline.web import lineage
            return lineage.graph(conn, self.settings)

        if path == "/api/admin/run-comparison":
            # BETA-101: a per-module diff between two runs — status, rows,
            # review items, failures, duration and freshness effect — derived
            # from the immutable ledger. Writes nothing, duplicates no
            # payloads. No ids -> the two most recent runs.
            degrade.preflight(conn, "run_ledger")
            from pipeline import run_ledger
            try:
                return run_ledger.compare(
                    conn, _str(params, "a") or None, _str(params, "b") or None)
            except ValueError as exc:
                raise ApiError(str(exc), status=404) from exc

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

        match = re.fullmatch(r"/api/admin/review/(\d+)/name-matches", path)
        if match:
            # Operator aid: candidate targets for an unmatched name, ranked by
            # trigram similarity (pg_trgm) or difflib. Ranks, does not resolve.
            try:
                return name_matches.suggestions(conn, int(match.group(1)))
            except name_matches.NameMatchError as exc:
                raise ApiError(str(exc), status=404) from None

        match = re.fullmatch(r"/api/review/(\d+)/sidecar", path)
        if match:
            # Decision support (BETA-054): the item's own source excerpt plus
            # the ranked candidates, relabelled as similarity and never
            # preselected.
            from pipeline.web import sidecar as sidecar_mod
            return sidecar_mod.sidecar(conn, int(match.group(1)))

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
        if route == "meta":
            # Release identity for the beta — build, schema, capabilities.
            # `/health` stays the plain `ok` liveness probe; this is the
            # auditable identity beside it. Needs settings, unlike the rest.
            return public_queries.meta(conn, self.settings)
        if route == "providers":
            return {"providers": public_queries.providers(conn)}
        if route == "authorities":
            return {"authorities": public_queries.authorities(conn)}
        if route == "contracts":
            return public_queries.contracts(
                conn, **_contract_query(params),
                limit=_int(params, "limit", 500),
                offset=_int(params, "offset", 0))
        if route == "pay":
            return public_queries.pay(
                conn,
                provider_key=_str(params, "provider_key") or None,
                year_from=_str(params, "year_from") or None,
                year_to=_str(params, "year_to") or None,
                # BETA-070 workforce pay explorer: additive, backward-compatible
                # narrowing. Omitted => the full multi-source payload as before.
                role=_str(params, "role") or None,
                source=_str(params, "source") or None,
                pay_unit=_str(params, "pay_unit") or None)
        if route == "council_spend":
            return public_queries.council_spend(
                conn,
                authority_ons_code=_str(params, "authority_ons_code") or None,
                provider_key=_str(params, "provider_key") or None,
                limit=_int(params, "limit", 500))
        if route == "geography":
            metric = _str(params, "metric") or "grant_total"
            return {**public_queries.geography(
                        conn, metric=metric, year=_str(params, "year") or None),
                     "available_years": public_queries.geography_years(conn, metric)}
        if route == "boundaries":
            return public_queries.boundaries(conn)
        if route == "ndtms":
            return public_queries.ndtms(
                conn,
                ons_code=_str(params, "ons_code") or None,
                table_ref=_str(params, "table_ref") or None)
        if route == "fingertips":
            return public_queries.fingertips(
                conn,
                indicator_id=_str(params, "indicator_id") or None,
                topic=_str(params, "topic") or None,
                ons_code=_str(params, "ons_code") or None,
                substance=_str(params, "substance") or None)
        if route == "treatment_metrics":
            # The metric catalogue shown before a chart (BETA-075): definition,
            # unit, CI availability, exact periods, coverage and provenance.
            return public_queries.treatment_metrics(conn)
        if route == "pfd":
            return public_queries.pfd(conn)
        if route == "safety":
            # HSE enforcement notices attributed to a tracked provider by
            # exact name match (BETA-051). Individuals excluded at collection.
            return public_queries.safety(conn)
        if route == "safety_legal":
            # One filterable chronology over PFD, SAR, HSE, tribunal and CQC
            # evidence, each event carrying exactly one relationship label
            # (BETA-079). Counts by source and by relationship, never summed.
            return public_queries.safety_legal(
                conn,
                source=_str(params, "source") or None,
                relationship=_str(params, "relationship") or None,
                provider_key=_str(params, "provider_key") or None,
                year_from=_str(params, "year_from") or None,
                year_to=_str(params, "year_to") or None)
        if route == "cqc_locations":
            # BETA-065: tracked providers' CQC-registered locations, filtered
            # and paginated. Not a service map; a location count is not
            # coverage. No personal data (registered managers are restricted_).
            return public_queries.cqc_locations(
                conn,
                provider_key=_str(params, "provider_key") or None,
                authority_ons_code=_str(params, "authority_ons_code") or None,
                registration_status=_str(params, "registration_status") or None,
                regulated_activity=_str(params, "regulated_activity") or None,
                service_type=_str(params, "service_type") or None,
                rating=_str(params, "rating") or None,
                limit=_int(params, "limit", 100),
                offset=_int(params, "offset", 0))
        if route == "claims":
            return public_queries.claims(conn)
        if route == "freshness":
            # Its own route rather than a key of `summary` for the same
            # reason the admin one is: seconds of full table scans, and the
            # landing page loads it lazily after first paint.
            return public_queries.freshness(conn)
        if route == "compare":
            return public_queries.compare(
                conn,
                ons_codes=params.get("ons_code", []),
                provider_keys=params.get("provider_key", []))
        if route == "layers":
            return public_queries.layers(conn)
        if route == "atlas_layers":
            # The closed atlas layer registry (BETA-078): one layer at a time,
            # no overlay, no composite score. A static manifest.
            return public_queries.atlas_layers()
        if route == "relationships":
            return public_queries.relationships(
                conn,
                ons_code=_str(params, "ons_code") or None,
                provider_key=_str(params, "provider_key") or None)
        if route == "document_tables":
            # BETA-099: tables detected in a parsed document -- the grid the
            # parser wrote to document_tables, its page context and
            # extraction status. No cell is re-detected. `table_id` -> one
            # table with its full grid and context.
            from pipeline.web import doc_tables
            tid = _str(params, "table_id")
            if tid:
                return doc_tables.table_detail(conn, tid)
            return doc_tables.tables(conn, _str(params, "document_id"))

        if route == "source_link":
            # BETA-100: whether a source URL was live / redirected / gone at
            # the last fetch, and whether a checksum-verified archive copy is
            # held. Derived from collection-time metadata only -- no live
            # request. No `url` -> the warehouse-wide state breakdown.
            from pipeline.web import link_check
            target = _str(params, "url")
            if target:
                return link_check.check(conn, self.settings, target)
            return link_check.overview(conn)

        if route == "contract_diary":
            # BETA-098: procurement lifecycle records as dated events --
            # published, award, contract period start/end. Every date is
            # transcribed from the notice; no renewal or completion is
            # predicted.
            from pipeline.web import contract_diary
            return contract_diary.diary(
                conn,
                provider_key=_str(params, "provider_key") or None,
                buyer_ons_code=_str(params, "buyer_ons_code") or None,
                year=_str(params, "year") or None,
                ocid=_str(params, "ocid") or None)

        if route == "discrepancies":
            # BETA-096: fields two or more public sources report differently
            # for one verified entity. Both values shown, neither resolved or
            # called an error. A closed registry of comparable field pairs.
            from pipeline.web import discrepancy
            return discrepancy.check(
                conn,
                provider_key=_str(params, "provider_key") or None,
                ons_code=_str(params, "ons_code") or None)

        if route == "cooccurrence":
            # BETA-095: documents and records naming two or more selected
            # tracked entities together, with the exact passage or field.
            # Verified aliases + same-record only; co-occurrence is location,
            # never an asserted relationship.
            from pipeline.web import cooccurrence
            return cooccurrence.find(conn, params.get("key", []))

        if route == "coverage_timeline":
            # BETA-097: which periods each source holds for one provider or
            # authority. Never gap-filled — an absent period stays "not
            # collected / not published", not a zero.
            from pipeline.web import coverage_timeline
            return coverage_timeline.timeline(
                conn,
                provider_key=_str(params, "provider_key") or None,
                ons_code=_str(params, "ons_code") or None)

        if route == "relationship_path":
            # BETA-093: the shortest *verified* path between two entities
            # through v_entity_edges. Unconfirmed name-match edges are
            # excluded; the traversal is deterministic and hop-bounded.
            from pipeline.web import pathfinder
            return pathfinder.find_path(
                conn,
                from_type=_str(params, "from_type") or "provider",
                from_id=_str(params, "from_id"),
                to_type=_str(params, "to_type") or "authority",
                to_id=_str(params, "to_id"),
                max_hops=_int(params, "max_hops", 6))
        if route == "document_search":
            # Preflighted (BETA-068): schema drift on this surface was the
            # original bug — a `UndefinedTable` where results should be.
            degrade.preflight(conn, "document_search")
            return public_queries.document_search(
                conn, query=_str(params, "q") or "",
                source_system=_str(params, "source_system") or None,
                document_type=_str(params, "document_type") or None,
                year_from=_str(params, "year_from") or None,
                year_to=_str(params, "year_to") or None,
                since_retrieved_at=_str(params, "since_retrieved_at") or None,
                limit=_int(params, "limit", 25), offset=_int(params, "offset", 0))

        if route == "catalogue":
            # The public dataset catalogue (BETA-043): static registry in
            # pipeline/web/datasets.py, live counts/freshness measured here.
            return public_queries.catalogue(conn)

        match = re.fullmatch(r"catalogue/([a-z0-9-]{1,64})", route)
        if match:
            return public_queries.catalogue_detail(conn, match.group(1))

        if route == "publication_calendar":
            # BETA-091: each source's stated vs observed release cadence, last
            # retrieval held here, next-expected date and overdue/unknown
            # status. Derived on the request; the stated cadence is the only
            # asserted figure and never merged with the observed estimate.
            return public_queries.publication_calendar(
                conn, today=_str(params, "today") or None)

        if route == "record_diff":
            # BETA-092: field-aware diff of two procurement notices sharing an
            # OCID, or text-aware diff of two parsed versions of one document.
            # Labels a publisher amendment ('source' field) apart from a
            # normalisation this pipeline recomputed ('derived' field / parser
            # change). Read-only; documents gated by DOCUMENT_SEARCH_SOURCES.
            from pipeline.web import record_diff as _record_diff
            return _record_diff.record_diff(
                conn,
                kind=_str(params, "kind") or "ocds",
                a=_str(params, "a") or None,
                b=_str(params, "b") or None,
                ocid=_str(params, "ocid") or None,
                document_id=_str(params, "document_id") or None)

        if route == "changes":
            # BETA-090: a derived, filterable chronology of what the warehouse
            # recorded changing — added/refreshed, reparsed, superseded,
            # verified. Read-only; adds no collection-time write path.
            return public_queries.change_feed(
                conn,
                kind=_str(params, "kind") or None,
                source=_str(params, "source") or None,
                evidence_type=_str(params, "evidence_type") or None,
                since=_str(params, "since") or None,
                limit=_int(params, "limit", 200))

        # The notices that share one OCID, grouped into published OCDS
        # lifecycle stages (BETA-050). No inferred stage, no computed
        # completion/performance.
        match = re.fullmatch(r"contracts/process/([A-Za-z0-9_-]{1,100})", route)
        if match:
            return public_queries.contract_process(conn, match.group(1))

        # One AWARDED_TO edge and the dated contract notices behind every edge
        # between the same authority and provider (BETA-044).
        match = re.fullmatch(r"relationships/(relationship:[0-9a-f]{64})", route)
        if match:
            return public_queries.relationship_detail(conn, match.group(1))

        if route == "provider_compare":
            # 2-4 providers across four separate pay-evidence layers (BETA-045).
            # A flat name like `document_search` / `council_spend`, not
            # `providers/compare`: it keeps this out of the `providers/...`
            # pattern space and inside the frozen-surface machinery unchanged.
            return public_queries.providers_compare(
                conn, params.get("provider_key", []))

        match = re.fullmatch(r"providers/([a-z0-9_]+)/timeline", route)
        if match:
            return public_queries.provider_timeline(conn, match.group(1))

        # BETA-066: the verified administrative lineage of a provider entity —
        # renamed / merged / dissolved edges from the lifecycle config, both
        # directions, plus the forward chain to the surviving entity. Not a
        # statement about continuity of service or workforce.
        match = re.fullmatch(r"providers/([a-z0-9_]+)/lineage", route)
        if match:
            return public_queries.provider_lineage(conn, match.group(1))

        # A document id is `document-<uuid5>` (pipeline/documents/repository.py).
        # The bounded window around one matched element (BETA-042); the source
        # allowlist and active-version rules are enforced in the query.
        match = re.fullmatch(r"documents/([A-Za-z0-9_-]{1,80})", route)
        if match:
            return public_queries.document_context(
                conn, match.group(1),
                element_id=_str(params, "element_id") or None,
                context=_int(params, "context", 3))

        # ONS codes are a letter followed by eight digits (E08000025). The
        # pattern is intentionally tighter than "anything": an authority page
        # is keyed by a code the /api/v1/authorities list actually returns.
        match = re.fullmatch(r"authorities/([A-Z][0-9]{8})", route)
        if match:
            return public_queries.authority(conn, match.group(1))

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
            "/api/admin/candidates/promote": self._promote,
            "/api/admin/candidates/reject": self._reject_candidates,
            "/api/admin/candidates/reset": self._reset_candidate,
            "/api/admin/census/verify": self._verify_census,
            "/api/admin/census/reject": self._reject_census,
            "/api/admin/census/reset": self._reset_census,
            "/api/admin/claims/create": self._create_claim,
            "/api/admin/claims/update": self._update_claim,
            "/api/admin/claims/cite": self._cite_claim,
            "/api/admin/claims/uncite": self._uncite_claim,
            "/api/admin/claims/decide": self._decide_claim,
            "/api/admin/claims/reset": self._reset_claim,
            "/api/admin/claim-candidates/decide": self._decide_claim_candidate,
            "/api/admin/aliases/decide": self._decide_alias,
        }

    def _decide_alias(self, body: dict) -> Any:
        """Record one human alias-resolution decision (BETA-056).

        One name per request; a named reviewer is required, and an `accepted`
        decision needs a `canonical_id` that exists. No fuzzy match is ever
        applied automatically — this is the only path that resolves a name.
        """
        conn = db.get_connection(self.settings)
        try:
            from pipeline.web import alias_resolution
            result = alias_resolution.decide(
                conn,
                unmatched_name=str(body.get("unmatched_name", "")),
                target_scheme=str(body.get("target_scheme", "")),
                status=str(body.get("status", "")),
                decided_by=str(body.get("decided_by", "")),
                canonical_id=body.get("canonical_id") or None,
                reason=body.get("reason") or None,
                review_item_id=body.get("review_item_id"),
                supersedes_id=body.get("supersedes_id") or None)
        except queries.QueryError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.alias_decided", decision_id=result["decision_id"],
                  status=result["status"])
        return result

    def _decide_claim_candidate(self, body: dict) -> Any:
        """Record one reviewer's judgement on one semantic claim candidate.

        One candidate per request, the same rule `_verify_census` and
        `_decide_claim` follow: the act being recorded is that a person read a
        sentence and judged a machine-extracted triple. `corrected` needs (and
        the nlp layer validates) at least one ontology-valid `corrected_*`
        field. Nothing here writes `graph_claims` or trains anything.
        """
        conn = db.get_connection(self.settings)
        try:
            result = claim_review.decide(
                conn,
                claim_candidate_id=str(body.get("claim_candidate_id", "")),
                decision=str(body.get("decision", "")),
                decided_by=str(body.get("decided_by", "")),
                reason_code=body.get("reason_code") or None,
                corrected_predicate=body.get("corrected_predicate") or None,
                corrected_object_concept_id=body.get("corrected_object_concept_id") or None,
                corrected_object_literal=body.get("corrected_object_literal") or None,
                corrected_subject_mention_id=body.get("corrected_subject_mention_id") or None,
                review_queue_id=body.get("review_queue_id"),
                note=body.get("note") or None)
        except queries.QueryError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_candidate_decided",
                  claim_candidate_id=result["claim_candidate_id"],
                  decision=result["decision"])
        return result

    def _verify_census(self, body: dict) -> Any:
        """Record that one census figure was checked against its page.

        One, never a list, the same rule `_promote` follows -- and for a reason
        that is not the fetch, because there is no fetch here. What is being
        recorded is that a person read a page and agreed with a number, and a
        route taking an array would be a route that made claiming that cheap.
        Bulk rejection has its own endpoint: see census_verify.reject.
        """
        conn = db.get_connection(self.settings)
        try:
            result = census_verify.verify(
                conn,
                key=str(body.get("key", "")),
                verified_by=str(body.get("verified_by", "")),
                note=body.get("note"))
        except census_verify.VerificationError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()

        log.info("web.census_verified", key=result["key"],
                  year=result["census_year"], metric=result["metric"],
                  by=result["decided_by"])
        return result

    def _reject_census(self, body: dict) -> Any:
        keys = body.get("keys")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ApiError("keys must be a list of strings.", status=400)
        conn = db.get_connection(self.settings)
        try:
            count = census_verify.reject(
                conn, keys=keys,
                rejected_by=str(body.get("rejected_by", "")),
                note=body.get("note"))
        except census_verify.VerificationError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.census_rejected", count=count)
        return {"rejected": count}

    def _reset_census(self, body: dict) -> Any:
        conn = db.get_connection(self.settings)
        try:
            return census_verify.reset(conn, key=str(body.get("key", "")))
        except census_verify.VerificationError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()

    def _create_claim(self, body: dict) -> Any:
        """Write a draft claim. One, never a list, the same rule `_promote`
        follows: the act being recorded is that somebody wrote the statement,
        and a route taking an array would be a route that made claiming cheap.
        """
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.create(
                conn,
                claim_text=str(body.get("claim_text", "")),
                created_by=str(body.get("created_by", "")),
                caveats=str(body.get("caveats", "")),
                note=body.get("note"),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_created", claim_id=result["id"],
                  by=result["created_by"])
        return result

    def _update_claim(self, body: dict) -> Any:
        """Edit a draft claim's text, caveats and note."""
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.update_text(
                conn,
                claim_id=_claim_id(body),
                claim_text=str(body.get("claim_text", "")),
                caveats=str(body.get("caveats", "")),
                note=body.get("note"),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_updated", claim_id=result["id"])
        return result

    def _cite_claim(self, body: dict) -> Any:
        """Link one evidence row to a draft claim."""
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.cite(
                conn,
                claim_id=_claim_id(body),
                evidence_table=str(body.get("evidence_table", "")),
                evidence_key=str(body.get("evidence_key", "")),
                cited_by=str(body.get("cited_by", "")),
                note=body.get("note"),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_cited", claim_id=result["id"])
        return result

    def _uncite_claim(self, body: dict) -> Any:
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.uncite(
                conn,
                claim_id=_claim_id(body),
                evidence_table=str(body.get("evidence_table", "")),
                evidence_key=str(body.get("evidence_key", "")),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_uncited", claim_id=result["id"])
        return result

    def _decide_claim(self, body: dict) -> Any:
        """Move a claim to a decided status, recording who decided it.

        One claim per request, the same rule `_verify_census` follows: the
        act being recorded is that a person reviewed this statement.
        """
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.decide(
                conn,
                claim_id=_claim_id(body),
                decision=str(body.get("decision", "")),
                decided_by=str(body.get("decided_by", "")),
                note=body.get("note"),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_decided", claim_id=result["id"],
                  decision=result["status"])
        return result

    def _reset_claim(self, body: dict) -> Any:
        conn = db.get_connection(self.settings)
        try:
            result = claims_core.reset(
                conn,
                claim_id=_claim_id(body),
            )
        except ClaimError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.claim_reset", claim_id=result["id"])
        return result

    def _promote(self, body: dict) -> Any:
        """Promote one candidate into the evidence base.

        One, never a list. The act being recorded is that somebody opened the
        document, and a route that took an array would be a route that made
        pretending cheap. Bulk rejection has its own endpoint below.

        The operator UI does now offer a batch promote, and this route is
        still the only way through it: the page sends one request per
        candidate, in turn, for candidates it saw the operator open. That
        leaves the guarantee here exactly where it was -- one fetch, one
        archived payload and one evidence_promotions row per document -- and
        keeps the batching where it belongs, which is in the clicking.

        This fetches the document, so it reaches the open web with the same
        standing as a module run: robots, the shared rate limit, and the bytes
        archived under data/raw/.
        """
        conn = db.get_connection(self.settings)
        try:
            result = promote.promote(
                conn,
                kind=str(body.get("kind", "")),
                url=str(body.get("url", "")),
                promoted_by=str(body.get("promoted_by", "")),
                fields=body.get("fields") or {},
                note=body.get("note"),
                settings=self.settings,
            )
        except promote.PromotionError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()

        log.info("web.candidate_promoted", kind=result["kind"], url=result["url"],
                  by=result["promoted_by"], target=result["target_table"])
        return result

    def _reject_candidates(self, body: dict) -> Any:
        urls = body.get("urls")
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise ApiError("urls must be a list of strings.", status=400)
        conn = db.get_connection(self.settings)
        try:
            count = promote.reject(conn, kind=str(body.get("kind", "")), urls=urls,
                                    rejected_by=str(body.get("rejected_by", "")),
                                    note=body.get("note"))
        except promote.PromotionError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        log.info("web.candidates_rejected", kind=body.get("kind"), count=count)
        return {"rejected": count}

    def _reset_candidate(self, body: dict) -> Any:
        conn = db.get_connection(self.settings)
        try:
            promote.reset(conn, kind=str(body.get("kind", "")),
                           url=str(body.get("url", "")))
        except promote.PromotionError as exc:
            raise ApiError(str(exc), status=400) from None
        finally:
            conn.close()
        return {"reset": body.get("url")}

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
    # One bucket per client address, shared across every request thread —
    # see Handler.__init__'s comment on why it has to be shared rather than
    # per-connection. capacity/burst covers a page load that fires several
    # endpoint calls at once; per-minute is the sustained rate a scraper
    # would be held to.
    rate_limiter = (
        TokenBucketLimiter(
            capacity=settings.api_rate_limit_burst,
            refill_per_second=settings.api_rate_limit_per_minute / 60.0,
        )
        if settings.api_rate_limit_enabled else None
    )
    # NullCache unless CACHE_ENABLED; shared across every request thread. Its
    # bump_version is handed to the registry so a completed run drops the
    # public read cache -- the one event that changes what /api/v1/* returns.
    # When the cache is off this is a no-op, so the wiring is unconditional.
    cache = get_cache(settings)
    # The registry is given a store, so the job list opens showing what this
    # warehouse has been asked to do rather than only what has happened since
    # the last restart. A run killed by a crash reappears as interrupted.
    server = ThreadingHTTPServer(
        (host, port),
        partial(Handler, settings=settings,
                 jobs=JobRegistry(store=JobStore(settings),
                                   invalidate=cache.bump_version),
                 rate_limiter=rate_limiter,
                 cache=cache))
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
        close_read_pools()


def close_read_pools() -> None:
    """Give back the PostgreSQL read pool when the server stops.

    `atexit` would do it too. This is here so that a caller which builds a
    server, serves, and carries on — the tests do exactly that — does not
    leave a pool holding connections to a warehouse nobody is reading any
    more. A no-op on SQLite, and on a checkout without psycopg installed.
    """
    try:
        from pipeline import pg
    except ImportError:  # pragma: no cover - no postgres extra installed
        return
    pg.close_pools()
