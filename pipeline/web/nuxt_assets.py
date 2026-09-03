"""Serving the built Nuxt frontends — the Phase 6 cutover seam.

This module owns exactly one thing: given a request path, decide whether the
built Nuxt static output should answer it and, if so, which file with which
cache policy. It never touches the API, the database, or evidence. It is inert
unless ``SERVE_NUXT`` is set and the built output is actually present, so the
default deployment behaves byte-identically to before this module existed.

Two applications are served from one directory:

    <dist>/public/   -> the public evidence atlas, served at ``/``
    <dist>/admin/    -> the operator control room, served at ``/admin``

Each subdirectory is a ``nuxt generate`` output: an ``index.html`` (plus
``200.html``/``404.html`` SPA fallbacks) and content-hashed assets under
``_nuxt/``. The build runs in a separate Docker stage; Node never runs in the
serving process.

Serving rules (Phase 6 delivery contract):

  * Content-hashed assets under ``_nuxt/`` are immutable — one year, immutable.
  * HTML entry points are ``no-cache`` so a redeploy is picked up immediately.
  * A path with a file extension that does not resolve to a real file returns
    ``None`` (a real 404 for a missing asset), never the SPA shell — returning
    HTML for a missing ``.js`` masks build breakage.
  * A path with no extension (an application route, e.g. ``/pay`` or a deep
    link) falls back to the app's ``index.html`` so client-side routing and
    bookmarks resolve. This is the ``200.html`` behaviour.
  * ``/api`` and ``/api/**`` are never handled here — the API is always the
    Python server's, regardless of this flag.

Path traversal cannot escape the app directory: the resolved candidate must sit
inside it, checked with ``Path.resolve`` and ``is_relative_to`` rather than by
string juggling.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Default location the Docker build stage copies the two generated outputs to.
# Kept beside the legacy static tree but distinct from it, so both can coexist
# in the image during the migration.
DEFAULT_DIST_DIR = Path(__file__).resolve().parent / "static_nuxt"

_HTML = "text/html; charset=utf-8"
_IMMUTABLE_MAX_AGE = 31_536_000  # one year

# Minimal, explicit content-type map. The Nuxt output is JS/CSS/HTML plus a few
# font/image/map types; anything unlisted is served as octet-stream rather than
# guessed, so a surprising file type is never mislabelled as executable text.
_CONTENT_TYPES = {
    ".html": _HTML,
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}


@dataclass(frozen=True)
class Served:
    """One resolved file to send: its path, content type, and max-age (seconds).

    ``max_age`` is ``0`` for HTML entry points (``no-cache`` semantics at the
    server layer) and one year for immutable hashed assets.
    """

    path: Path
    content_type: str
    max_age: int
    immutable: bool


def _content_type(path: Path) -> str:
    return _CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class NuxtAssets:
    """Resolver over the two built application directories."""

    def __init__(self, dist_dir: Path) -> None:
        self.root = dist_dir.resolve()
        self.public = (self.root / "public").resolve()
        self.admin = (self.root / "admin").resolve()

    def available(self) -> bool:
        """True only if the public build is actually present. The seam stays
        inert (the caller treats it as absent) until a build has been copied in,
        so enabling the flag without the assets present cannot 404 the site."""
        return (self.public / "index.html").is_file()

    def resolve(self, path: str) -> Served | None:
        """Resolve a request path to a file to serve, or ``None`` to let the
        legacy dispatch (or a 404) handle it. Never handles ``/api``."""
        if path == "/api" or path.startswith("/api/"):
            return None

        if path == "/admin" or path.startswith("/admin/"):
            base = self.admin
            rel = path[len("/admin"):]
        else:
            base = self.public
            rel = path
        rel = rel.lstrip("/")

        if not base.is_dir():
            return None

        # A concrete file request (has a real relative path).
        if rel:
            candidate = (base / rel).resolve()
            # Traversal guard: the resolved path must stay inside the app dir.
            if not _within(candidate, base):
                return None
            if candidate.is_file():
                immutable = _is_hashed_asset(rel)
                return Served(
                    path=candidate,
                    content_type=_content_type(candidate),
                    max_age=_IMMUTABLE_MAX_AGE if immutable else 0,
                    immutable=immutable,
                )
            # A missing file WITH an extension is a genuine 404, not the shell.
            if _has_extension(rel):
                return None

        # A route (root, or an extensionless deep link): the SPA shell.
        return self._spa_shell(base)

    @staticmethod
    def _spa_shell(base: Path) -> Served | None:
        # Prefer the explicit 200.html fallback; fall back to index.html.
        for name in ("200.html", "index.html"):
            candidate = base / name
            if candidate.is_file():
                return Served(path=candidate, content_type=_HTML, max_age=0, immutable=False)
        return None


def _within(candidate: Path, base: Path) -> bool:
    try:
        return candidate == base or candidate.is_relative_to(base)
    except ValueError:  # pragma: no cover - different drives on Windows
        return False


def _is_hashed_asset(rel: str) -> bool:
    # Nuxt emits content-hashed assets under `_nuxt/`. Those, and only those,
    # are safe to mark immutable — their name changes when their bytes do.
    return rel.startswith("_nuxt/") or "/_nuxt/" in rel


def _has_extension(rel: str) -> bool:
    return "." in rel.rsplit("/", 1)[-1]


# Module-level cache so the directory is stat-checked once per process, not per
# request. Keyed on the resolved directory so a test can point it elsewhere.
_CACHE: dict[Path, NuxtAssets | None] = {}


def for_settings(settings) -> NuxtAssets | None:
    """Return a ready ``NuxtAssets`` when the cutover seam is active and the
    build is present, else ``None``. Cheap to call per request."""
    if not getattr(settings, "serve_nuxt", False):
        return None
    dist = settings.nuxt_dist_dir or DEFAULT_DIST_DIR
    dist = Path(dist).resolve()
    if dist not in _CACHE:
        assets = NuxtAssets(dist)
        _CACHE[dist] = assets if assets.available() else None
    return _CACHE[dist]
