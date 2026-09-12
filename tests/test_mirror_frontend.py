"""Mirror cutover preflight over disposable assets, with no container or DB."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "deploy/ansible-mirror/check_frontend.py"
SPEC = importlib.util.spec_from_file_location("mirror_frontend_check", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


def _assets(tmp_path):
    for app, prefix in (("public", ""), ("admin", "/admin")):
        base = tmp_path / app
        (base / "_nuxt").mkdir(parents=True)
        html = (f'<script type="module" src="{prefix}/_nuxt/entry.js"></script>'
                f'<link rel="stylesheet" href="{prefix}/_nuxt/entry.css">')
        for name in ("index.html", "200.html", "404.html"):
            (base / name).write_text(html, encoding="utf-8")
        (base / "_nuxt/entry.js").write_text("export {}", encoding="utf-8")
        (base / "_nuxt/entry.css").write_text("body {}", encoding="utf-8")
    return tmp_path


def test_both_entry_points_and_their_assets_are_required(tmp_path):
    dist = _assets(tmp_path)
    CHECK.verify_assets(dist)
    (dist / "admin/_nuxt/entry.js").unlink()
    with pytest.raises(RuntimeError, match="Missing generated admin entry asset"):
        CHECK.verify_assets(dist)


def test_missing_fallback_is_not_mistaken_for_a_ready_build(tmp_path):
    dist = _assets(tmp_path)
    (dist / "public/200.html").unlink()
    with pytest.raises(RuntimeError, match="Missing generated public/200.html"):
        CHECK.verify_assets(dist)


@pytest.mark.parametrize("src", ["https://example.invalid/entry.js", "/extensionless", "/admin/_nuxt/entry.js"])
def test_external_fallback_and_cross_app_references_fail(tmp_path, src):
    dist = _assets(tmp_path)
    (dist / "public/index.html").write_text(f'<script src="{src}"></script>', encoding="utf-8")
    with pytest.raises(RuntimeError):
        CHECK.verify_assets(dist)


def test_an_environment_override_cannot_silently_keep_the_legacy_frontend(monkeypatch):
    from pipeline import config

    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(serve_nuxt=False, nuxt_dist_dir=None))
    monkeypatch.setattr(CHECK.sys, "argv", [str(SCRIPT), "true", "nuxt"])
    with pytest.raises(RuntimeError, match="Effective SERVE_NUXT disagrees"):
        CHECK.main()


def test_explicit_rollback_does_not_require_generated_assets(monkeypatch):
    from pipeline import config

    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(serve_nuxt=False, admin_ui_variant="legacy", nuxt_dist_dir=None))
    monkeypatch.setattr(CHECK.sys, "argv", [str(SCRIPT), "false", "legacy"])
    CHECK.main()


def test_public_rollback_still_checks_independently_enabled_admin(tmp_path, monkeypatch):
    from pipeline import config

    dist = _assets(tmp_path)
    (dist / "public/index.html").unlink()
    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(serve_nuxt=False, admin_ui_variant="nuxt", nuxt_dist_dir=dist))
    monkeypatch.setattr(CHECK.sys, "argv", [str(SCRIPT), "false", "nuxt"])
    CHECK.main()
    (dist / "admin/_nuxt/entry.js").unlink()
    with pytest.raises(RuntimeError, match="Missing generated admin entry asset"):
        CHECK.main()


def test_admin_override_cannot_silently_serve_another_variant(monkeypatch):
    from pipeline import config

    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(serve_nuxt=True, admin_ui_variant="legacy", nuxt_dist_dir=None))
    monkeypatch.setattr(CHECK.sys, "argv", [str(SCRIPT), "true", "nuxt"])
    with pytest.raises(RuntimeError, match="Effective ADMIN_UI_VARIANT disagrees"):
        CHECK.main()


def test_public_selection_does_not_require_an_explicitly_legacy_admin_build(tmp_path, monkeypatch):
    from pipeline import config

    dist = _assets(tmp_path)
    (dist / "admin/index.html").unlink()
    monkeypatch.setattr(config, "Settings", lambda: SimpleNamespace(serve_nuxt=True, admin_ui_variant="legacy", nuxt_dist_dir=dist))
    monkeypatch.setattr(CHECK.sys, "argv", [str(SCRIPT), "true", "legacy"])
    CHECK.main()
