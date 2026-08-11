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
from pipeline.web import queries, review

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Served by exact name. A dict rather than a directory walk: this is a fixed
# three-file front end, and matching names against a whitelist means path
# traversal is not a thing that has to be got right.
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}

MAX_BODY_BYTES = 256 * 1024

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

    # Reset per request in _dispatch. Declared here so the error path is safe
    # even for a request that never reaches it.
    _body_read = False
    _responded = False

    def __init__(self, *args, settings: Settings, **kwargs):
        self.settings = settings
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

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self._responded = True
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if self.close_connection:
            self.send_header("Connection", "close")
        # Nothing here is cacheable: the whole point is the current state of
        # the queue, and a stale page would show decisions that are not there.
        self.send_header("Cache-Control", "no-store")
        # The API is same-origin only. No CORS headers are ever sent, so a
        # cross-origin page cannot read a reply even if it manages to send a
        # request.
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

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
        except queries.QueryError as exc:
            self._fail(400, str(exc))
        except review.DecisionError as exc:
            self._fail(400, str(exc))
        except (BrokenPipeError, ConnectionResetError):
            # The browser navigated away mid-response. Nothing to report and
            # nowhere to report it to.
            log.debug("web.client_disconnected", path=path)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("web.unhandled", path=path)
            self._fail(500, f"{type(exc).__name__}: {exc}")

    def _fail(self, status: int, message: str) -> None:
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
            self._send_json({"error": message}, status=status)
        else:
            self._send(status, message.encode("utf-8"), "text/plain; charset=utf-8")

    def _serve_static(self, path: str) -> None:
        filename, content_type = STATIC_FILES[path]
        file_path = STATIC_DIR / filename
        if not file_path.is_file():
            raise ApiError(f"Missing UI asset {filename}", status=500)
        self._send(200, file_path.read_bytes(), content_type)

    def _serve_api(self, path: str, params: dict[str, list[str]]) -> None:
        if self.command == "POST":
            handler = self._post_routes().get(path)
            if handler is None:
                raise ApiError(f"No route for POST {path}", status=404)
            return self._send_json(handler(self._read_json()))

        if self.command not in ("GET", "HEAD"):
            raise ApiError(f"{self.command} is not supported here.", status=405)

        conn = queries.readonly_connection(self.settings)
        try:
            self._send_json(self._get(path, params, conn))
        finally:
            conn.close()

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
            return queries.review_facets(conn)

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

        raise ApiError(f"No route for GET {path}", status=404)

    # --- write routes ---------------------------------------------------------

    def _post_routes(self) -> dict[str, Callable[[dict], Any]]:
        return {
            "/api/review/decide": self._decide,
            "/api/review/decide-matching": self._decide_matching,
            "/api/query": self._query,
        }

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
    server = ThreadingHTTPServer((host, port), partial(Handler, settings=settings))
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
