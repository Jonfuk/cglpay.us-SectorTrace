"""Fail a mirror deploy before restart if its frontend selection cannot work."""
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


class EntryAssets(HTMLParser):
    """Collect executable and stylesheet references without executing HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        if tag == "script" and fields.get("src"):
            self.references.append(fields["src"] or "")
        if tag == "link" and fields.get("rel") in {"stylesheet", "modulepreload"}:
            self.references.append(fields.get("href") or "")


def verify_assets(dist: Path, apps: tuple[str, ...] = ("public", "admin")) -> None:
    # Import only when called. The helper can be tested with disposable static
    # fixtures and does not open a warehouse connection or contact a source.
    from pipeline.web.nuxt_assets import NuxtAssets

    assets = NuxtAssets(dist)
    for app, prefix in (("public", "/"), ("admin", "/admin/")):
        if app not in apps:
            continue
        for filename in ("index.html", "200.html", "404.html"):
            entry = dist / app / filename
            if not entry.is_file():
                raise RuntimeError(f"Missing generated {app}/{filename}")
        parser = EntryAssets()
        parser.feed((dist / app / "index.html").read_text(encoding="utf-8"))
        if not parser.references:
            raise RuntimeError(f"No generated entry assets found for {app}")
        for reference in parser.references:
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                raise RuntimeError(f"External entry asset in generated {app} frontend")
            path = url.path if url.path.startswith("/") else prefix + url.path
            served = assets.resolve(path)
            if (served is None or not served.path.is_file()
                    or not served.path.is_relative_to((dist / app).resolve())
                    or served.path.suffix not in {".js", ".mjs", ".css"}):
                raise RuntimeError(f"Missing generated {app} entry asset: {path}")


def main() -> None:
    # A script path makes Python start its imports in this directory. The image
    # root contains pipeline and is determined from this file, never the caller.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.config import Settings
    from pipeline.web.nuxt_assets import DEFAULT_DIST_DIR

    if (len(sys.argv) != 3 or sys.argv[1] not in {"true", "false"}
            or sys.argv[2] not in {"nuxt", "legacy"}):
        raise RuntimeError("Expected public true/false and admin nuxt/legacy choices")
    expected = sys.argv[1] == "true"
    expected_admin = sys.argv[2] == "nuxt"
    settings = Settings()
    if settings.serve_nuxt != expected:
        raise RuntimeError("Effective SERVE_NUXT disagrees with the deployment choice. Check .env.merge overrides.")
    admin_variant = settings.admin_ui_variant
    actual_admin = admin_variant == "nuxt" if admin_variant is not None else settings.serve_nuxt
    if actual_admin != expected_admin:
        raise RuntimeError("Effective ADMIN_UI_VARIANT disagrees with the deployment choice. Check .env.merge overrides.")
    apps = tuple(app for app, enabled in (("public", expected), ("admin", expected_admin)) if enabled)
    if apps:
        verify_assets(Path(settings.nuxt_dist_dir or DEFAULT_DIST_DIR), apps)


if __name__ == "__main__":
    main()
