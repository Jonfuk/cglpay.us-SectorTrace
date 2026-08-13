"""Listing and downloading the files an export produced.

This is the only route in the web layer that hands back a file off disk, so
the tests that matter are the ones about which files it will not hand back.
The implementation does not sanitise a requested path -- it matches it against
a listing computed on the spot -- and these pin that: traversal, absolute
paths, and a symlink planted inside the export tree all fail for the same
reason, which is that they are not in the listing.
"""
from __future__ import annotations

import json
import threading

import httpx
import pytest

from pipeline.exports import run as export_run
from pipeline.web import artefacts
from pipeline.web.server import build_server


@pytest.fixture
def exports(settings, tmp_path):
    """A populated exports/output next to the warehouse."""
    root = artefacts.export_root(settings)
    (root / "sheets").mkdir(parents=True, exist_ok=True)
    (root / "geojson").mkdir(parents=True, exist_ok=True)

    # newline="" so the bytes on disk are the bytes asserted on: Windows would
    # otherwise translate these to CRLF and the download, which is byte-exact,
    # would look wrong when it was right.
    (root / "sheets" / "01_Authorities.csv").write_text(
        "ons_code,name\nE08000025,Birmingham\n", encoding="utf-8", newline="")
    (root / "sheets" / "01_Authorities.csv.provenance.json").write_text(
        json.dumps({"tables": ["authorities"]}), encoding="utf-8")
    (root / "geojson" / "contracts.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
    return root


@pytest.fixture
def client(conn, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=30.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- listing --------------------------------------------------------------------


def test_the_listing_is_empty_but_honest_before_anything_is_exported(client, settings):
    payload = client.get("/api/admin/exports").json()
    assert payload["exists"] is False
    assert payload["files"] == []
    assert payload["root"].endswith("output")


def test_the_listing_reports_every_export_with_its_size(client, exports):
    payload = client.get("/api/admin/exports").json()
    by_path = {entry["path"]: entry for entry in payload["files"]}

    assert set(by_path) == {"sheets/01_Authorities.csv", "geojson/contracts.geojson"}
    assert by_path["sheets/01_Authorities.csv"]["bytes"] > 0
    assert by_path["sheets/01_Authorities.csv"]["group"] == "sheets"
    assert payload["bytes"] == sum(e["bytes"] for e in payload["files"])


def test_a_provenance_file_travels_with_the_file_it_describes(client, exports):
    """One artefact, two files. Listing them side by side doubles the length
    of the list and halves its use."""
    files = client.get("/api/admin/exports").json()["files"]
    csv = next(f for f in files if f["path"] == "sheets/01_Authorities.csv")

    assert csv["provenance"] == "sheets/01_Authorities.csv.provenance.json"
    assert not any(f["path"].endswith(".provenance.json") for f in files), \
        "the companion should not also be listed in its own right"


def test_an_orphaned_provenance_file_is_still_listed(client, exports):
    """Hiding it would misreport what is on disk."""
    (exports / "sheets" / "01_Authorities.csv").unlink()
    files = client.get("/api/admin/exports").json()["files"]
    assert any(f["path"] == "sheets/01_Authorities.csv.provenance.json" for f in files)


# --- downloading ------------------------------------------------------------------


def test_an_export_can_be_downloaded(client, exports):
    response = client.get("/api/admin/exports/file?path=sheets/01_Authorities.csv")

    assert response.status_code == 200
    assert response.text == "ons_code,name\nE08000025,Birmingham\n"
    assert response.headers["Content-Type"] == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "01_Authorities.csv" in response.headers["Content-Disposition"]


def test_a_geojson_export_is_labelled_as_one(client, exports):
    response = client.get("/api/admin/exports/file?path=geojson/contracts.geojson")
    assert response.headers["Content-Type"] == "application/geo+json"


def test_a_large_export_survives_being_streamed(client, exports):
    """Downloads are chunked rather than read whole: treatment_numbers.geojson
    is 23 MB in the real tree."""
    big = "x" * (artefacts.CHUNK_BYTES * 3 + 17)
    (exports / "geojson" / "big.geojson").write_text(big, encoding="utf-8")

    response = client.get("/api/admin/exports/file?path=geojson/big.geojson")
    assert response.status_code == 200
    assert len(response.text) == len(big)
    assert response.text == big


# --- what it refuses ----------------------------------------------------------------


@pytest.mark.parametrize("attempt", [
    "../../../data/warehouse.db",
    "..%2F..%2Fdata%2Fwarehouse.db",
    "sheets/../../../data/warehouse.db",
    "/etc/passwd",
    "C:/Windows/win.ini",
    "sheets/./../../pipeline/config.py",
    "....//....//data/warehouse.db",
    "",
])
def test_nothing_outside_the_export_tree_can_be_reached(client, exports, attempt):
    """Not sanitised -- unrepresentable. Every one of these fails for the same
    reason: it is not a path this server enumerated."""
    response = client.get("/api/admin/exports/file", params={"path": attempt})
    assert response.status_code == 404


def test_the_warehouse_itself_cannot_be_downloaded(client, exports, settings):
    """The single most valuable file on the machine, and it holds restricted_
    tables of personal data."""
    response = client.get("/api/admin/exports/file",
                           params={"path": str(settings.database_path)})
    assert response.status_code == 404


def test_a_symlink_out_of_the_export_tree_is_not_an_export(client, exports, settings):
    """A link planted inside exports/output resolves to somewhere it does not
    belong, so it is dropped from the listing -- and therefore undownloadable."""
    link = exports / "sheets" / "escape.db"
    try:
        link.symlink_to(settings.database_path)
    except (OSError, NotImplementedError):
        pytest.skip("this platform/user cannot create symlinks")

    listed = {entry["path"] for entry in client.get("/api/admin/exports").json()["files"]}
    assert "sheets/escape.db" not in listed
    assert client.get("/api/admin/exports/file?path=sheets/escape.db").status_code == 404


def test_a_file_that_has_gone_since_the_listing_is_a_404(client, exports):
    assert client.get(
        "/api/admin/exports/file?path=sheets/removed.csv").status_code == 404


def test_resolve_for_download_agrees_with_the_listing(settings, exports):
    """The property the route depends on, stated directly."""
    listed = [entry["path"] for entry in artefacts.listing(settings)["files"]]
    for path in listed:
        assert artefacts.resolve_for_download(settings, path) is not None
    assert artefacts.resolve_for_download(settings, "nope.csv") is None


# --- running an export ---------------------------------------------------------------


def wait_for(client, job_id, timeout=60.0):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/admin/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("the export never finished")


def test_an_export_runs_as_a_job_and_writes_files(client, conn, settings):
    started = client.post("/api/admin/export", json={"target": "echarts"})
    assert started.status_code == 200

    job = wait_for(client, started.json()["id"])
    assert job["state"] == "finished", job.get("error")
    assert job["summary"][0]["target"] == "echarts"

    listed = client.get("/api/admin/exports").json()["files"]
    assert listed, "the export produced nothing"
    assert all(entry["path"].startswith("echarts/") for entry in listed)


def test_an_unknown_export_target_is_a_404(client):
    response = client.post("/api/admin/export", json={"target": "powerpoint"})
    assert response.status_code == 404
    assert "powerpoint" in response.json()["error"]


def test_an_export_needs_a_target(client):
    assert client.post("/api/admin/export", json={}).status_code == 400


def test_starting_an_export_needs_a_json_content_type(client):
    response = client.post("/api/admin/export", content='{"target": "echarts"}',
                            headers={"Content-Type": "text/plain"})
    assert response.status_code == 415


def test_an_export_takes_the_same_slot_as_a_run(client, monkeypatch):
    """An export reads the whole warehouse; running one while a module rewrites
    the tables underneath produces an artefact matching no moment in time."""
    from pipeline.registry import MODULE_REGISTRY

    release = threading.Event()
    monkeypatch.setitem(MODULE_REGISTRY, "a_slow", lambda ctx: release.wait(timeout=10))

    client.post("/api/admin/run", json={"module": "a_slow"})
    try:
        assert client.post("/api/admin/export",
                            json={"target": "echarts"}).status_code == 409
    finally:
        release.set()


def test_the_web_never_pushes_to_google_sheets(client):
    """Pushing writes to a shared document other people are reading. It needs
    credentials and someone watching, so it stays a CLI flag."""
    import inspect

    from pipeline.web import admin

    source = inspect.getsource(admin.start_export)
    assert "push=False" in source
    assert "body.get(\"push\")" not in source


# --- the CLI and the browser write the same exports -----------------------------------


def test_both_callers_go_through_the_same_export_runner():
    import inspect

    from pipeline import cli
    from pipeline.web import admin

    assert "export_run.run_targets" in inspect.getsource(cli.export)
    assert "export_run.run_targets" in inspect.getsource(admin.start_export)


def test_resolve_targets_expands_all_and_refuses_anything_else():
    assert export_run.resolve_targets("all") == list(export_run.TARGETS)
    assert export_run.resolve_targets("docs") == ["docs"]
    with pytest.raises(export_run.ExportError):
        export_run.resolve_targets("everything")
