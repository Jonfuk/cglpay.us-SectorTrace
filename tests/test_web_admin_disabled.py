"""The hosted deployment can remove the unauthenticated operator surface."""

from __future__ import annotations

import threading

import httpx

from pipeline.web.server import build_server


def test_admin_ui_can_be_disabled_without_disabling_the_public_portal(
    warehouse, settings
):
    settings.admin_ui_enabled = False
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}",
            timeout=15.0,
        ) as client:
            for path in (
                "/admin",
                "/admin/",
                "/admin/app.js",
                "/api/admin/health",
                "/api/admin/run",
            ):
                assert client.get(path).status_code == 404

            assert client.get("/").status_code == 200
            assert client.get("/api").status_code == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
