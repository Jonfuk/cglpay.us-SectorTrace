"""`/api/openapi.json` — an OpenAPI 3.1 description of the public API (BETA-048).

The value of this document is that it is a *checked* inventory: the route
table in `pipeline/web/openapi.py` is bound here, in both directions, to the
frozen public surface in `tests/test_portal_isolation.py`. A new `/api/v1/`
route that nobody described fails; a described route the server does not serve
fails.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import openapi
from pipeline.web.server import build_server
from tests.test_portal_isolation import (
    PUBLIC_API_EXTRA,
    PUBLIC_API_PATTERNS,
    PUBLIC_API_ROUTES,
)

FROZEN = PUBLIC_API_ROUTES | PUBLIC_API_PATTERNS | PUBLIC_API_EXTRA


def test_the_route_table_matches_the_frozen_public_surface_exactly():
    described = {spec["surface"] for spec in openapi.ROUTES.values()}
    assert described == FROZEN, (
        "openapi.ROUTES and the frozen public surface disagree. "
        f"described only: {sorted(described - FROZEN)}; "
        f"surface only: {sorted(FROZEN - described)}")


def test_every_path_template_lines_up_with_its_surface():
    """A `{param}` path must correspond to a PUBLIC_API_PATTERNS regex; a plain
    path to a PUBLIC_API_ROUTES / EXTRA name."""
    for path, spec in openapi.ROUTES.items():
        surface = spec["surface"]
        templated = "{" in path
        if templated:
            assert surface in PUBLIC_API_PATTERNS, f"{path} is templated but {surface!r} is not a pattern"
        else:
            tail = path[len("/api/v1/"):] if path.startswith("/api/v1/") else path.split("/api/")[1]
            assert surface in (PUBLIC_API_ROUTES | PUBLIC_API_EXTRA)
            # `export` and `feed` are EXTRA surfaces whose path tail is not a
            # bare name (`export` takes an `endpoint` param; `feed` is
            # `feed/changes.atom`).
            if surface not in ("export", "feed"):
                assert tail == surface, f"{path} tail {tail!r} != surface {surface!r}"


def test_the_document_is_valid_openapi_3_1_shaped():
    doc = openapi.document()
    assert doc["openapi"] == "3.1.0"
    assert doc["info"]["title"] and doc["info"]["version"]
    assert doc["servers"] and "url" in doc["servers"][0]
    assert doc["components"]["schemas"]["Error"]["required"] == ["error"]

    for path, item in doc["paths"].items():
        assert set(item) == {"get"}, f"{path} documents a non-GET method"
        get = item["get"]
        assert get["summary"]
        assert "200" in get["responses"] and "400" in get["responses"]
        for param in get["parameters"]:
            assert param["in"] in ("query", "path")
            assert "schema" in param and "description" in param
            if param["in"] == "path":
                assert param["required"] is True
                assert "{" + param["name"] + "}" in path


def test_path_parameters_are_all_declared():
    import re
    for path, item in openapi.document()["paths"].items():
        in_path = set(re.findall(r"\{([^}]+)\}", path))
        declared = {p["name"] for p in item["get"]["parameters"] if p["in"] == "path"}
        assert in_path == declared, f"{path}: path vars {in_path} != declared {declared}"


@pytest.fixture
def client(settings: Settings, conn: sqlite3.Connection):
    conn.close()
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


def test_it_is_served_at_the_sibling_of_the_api_page(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/json")
    body = response.json()
    assert body["openapi"] == "3.1.0"
    assert "/api/v1/summary" in body["paths"]
    # HEAD works (the read-only smoke gate shape), mutating verbs do not.
    assert client.head("/api/openapi.json").status_code == 200
    assert client.post("/api/openapi.json").status_code == 404
    # And it is not itself a /api/v1/ route.
    assert client.get("/api/v1/openapi.json").status_code == 404


def test_the_served_document_equals_the_module_output(client):
    served = client.get("/api/openapi.json").json()
    assert served == openapi.document()
