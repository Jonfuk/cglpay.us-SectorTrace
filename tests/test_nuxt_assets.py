"""The Phase 6 Nuxt cutover seam: path resolution, cache policy, and CSP.

These are DB-free unit tests over `pipeline/web/nuxt_assets` and the two Nuxt
CSP helpers in `pipeline/web/server`. They build a tiny fake `generate` output
in `tmp_path` so they never depend on a real build, and they assert the
properties that keep the seam safe:

  * `/api` and `/api/**` are never claimed by the seam;
  * path traversal cannot escape an app directory;
  * a missing asset (a path with an extension) is a 404, not the SPA shell;
  * an extensionless route falls back to the app's `200.html`;
  * content-hashed `_nuxt/` assets are immutable, HTML entries are not;
  * the CSP hashes the page's executable inline scripts and skips data islands.
"""
from __future__ import annotations

import base64
import hashlib

import pytest

from pipeline.web import nuxt_assets
from pipeline.web.server import (
    Handler,
    nuxt_content_security_policy,
    nuxt_inline_script_hashes,
)


def _build(tmp_path):
    """A minimal two-app dist: public/ and admin/, each with an index/200 and a
    hashed asset."""
    for app in ("public", "admin"):
        base = tmp_path / app
        (base / "_nuxt").mkdir(parents=True)
        (base / "index.html").write_text(f"<html><body>{app}</body></html>")
        (base / "200.html").write_text(f"<html><body>{app} spa</body></html>")
        (base / "_nuxt" / "abc123.js").write_text("console.log(1)")
    return nuxt_assets.NuxtAssets(tmp_path)


def test_available_requires_the_public_build(tmp_path):
    assert nuxt_assets.NuxtAssets(tmp_path).available() is False
    _build(tmp_path)
    assert nuxt_assets.NuxtAssets(tmp_path).available() is True


def test_api_paths_are_never_claimed(tmp_path):
    assets = _build(tmp_path)
    for path in ("/api", "/api/v1/meta", "/api/admin/health"):
        assert assets.resolve(path) is None


def test_routes_fall_back_to_the_spa_shell(tmp_path):
    assets = _build(tmp_path)
    for path in ("/", "/pay", "/providers/abc", "/admin", "/admin/candidates"):
        served = assets.resolve(path)
        assert served is not None
        assert served.path.name == "200.html"
        assert served.immutable is False
        assert served.max_age == 0


def test_hashed_assets_are_immutable(tmp_path):
    assets = _build(tmp_path)
    served = assets.resolve("/_nuxt/abc123.js")
    assert served is not None
    assert served.immutable is True
    assert served.max_age == 31_536_000
    # Admin assets resolve under the admin subtree.
    admin = assets.resolve("/admin/_nuxt/abc123.js")
    assert admin is not None and admin.immutable is True


def test_content_addressed_pmtiles_are_immutable(tmp_path):
    assets = _build(tmp_path)
    archive_dir = tmp_path / "public" / "map"
    archive_dir.mkdir()
    archive = archive_dir / ("boundaries-" + "a" * 64 + ".pmtiles")
    archive.write_bytes(b"PMTiles\x03")

    served = assets.resolve("/map/" + archive.name)
    assert served is not None
    assert served.content_type == "application/octet-stream"
    assert served.immutable is True
    assert served.max_age == 31_536_000


def test_missing_asset_is_a_404_not_the_shell(tmp_path):
    assets = _build(tmp_path)
    # A path with an extension that does not exist must NOT return index.html.
    assert assets.resolve("/_nuxt/nope.js") is None
    assert assets.resolve("/admin/_nuxt/nope.css") is None


def test_path_traversal_cannot_escape(tmp_path):
    assets = _build(tmp_path)
    secret = tmp_path / "secret.txt"
    secret.write_text("no")
    for path in ("/../secret.txt", "/admin/../../secret.txt",
                 "/%2e%2e/secret.txt", "/_nuxt/../../secret.txt"):
        assert assets.resolve(path) is None


def test_for_settings_is_inert_without_the_flag(tmp_path):
    _build(tmp_path)
    nuxt_assets._CACHE.clear()

    class S:
        serve_nuxt = False
        nuxt_dist_dir = tmp_path

    assert nuxt_assets.for_settings(S()) is None


def test_for_settings_returns_resolver_when_enabled(tmp_path):
    _build(tmp_path)
    nuxt_assets._CACHE.clear()

    class S:
        serve_nuxt = True
        nuxt_dist_dir = tmp_path

    resolver = nuxt_assets.for_settings(S())
    assert resolver is not None
    assert resolver.resolve("/").path.name == "200.html"


def _sha256(body: bytes) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode() + "'"


def test_csp_hashes_executable_inline_scripts_only():
    boot = b"window.__x=1"
    imap = b'{"imports":{}}'
    html = (
        b"<html><head>"
        b'<script type="importmap">' + imap + b"</script>"
        b'<script type="module" src="/_nuxt/entry.js" crossorigin></script>'
        b"<script>" + boot + b"</script>"
        b'<script type="application/json" id="__NUXT_DATA__">[1,2,3]</script>'
        b"</head></html>"
    )
    hashes = nuxt_inline_script_hashes(html)
    # importmap + bootstrap are hashed; the external module and the JSON data
    # island are not.
    assert _sha256(imap) in hashes
    assert _sha256(boot) in hashes
    assert len(hashes) == 2

    csp = nuxt_content_security_policy(html)
    assert "script-src 'self'" in csp
    assert _sha256(boot) in csp
    # No 'unsafe-inline' for scripts — the seam keeps the strict policy.
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1]


def test_csp_normalises_crlf_like_the_browser():
    # The browser hashes the newline-normalised body; a CRLF in the file must
    # not produce a policy that blocks its own script.
    html = b"<html><script>a=1\r\nb=2</script></html>"
    expected = _sha256(b"a=1\nb=2")
    assert expected in nuxt_inline_script_hashes(html)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-99", (0, 99)),
        ("bytes=100-", (100, 999)),
        ("bytes=-50", (950, 999)),
        ("bytes=0-9999", (0, 999)),
    ],
)
def test_pmtiles_range_parser_supports_single_bounded_ranges(header, expected):
    assert Handler._parse_byte_range(header, 1000) == expected


@pytest.mark.parametrize("header", ["bytes=1000-", "bytes=50-10", "bytes=0-1,2-3", "wat=0-1"])
def test_pmtiles_range_parser_rejects_invalid_or_multi_ranges(header):
    assert Handler._parse_byte_range(header, 1000) is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
