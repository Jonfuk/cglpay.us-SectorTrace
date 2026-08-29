"""The public dataset catalogue (BETA-043).

A reader should be able to find out what the portal holds — its source,
licence, cadence and the one limitation that matters most — without reading
module code. Two things keep the catalogue honest and are pinned here:

  * **Every collecting module has exactly one entry.** A new `mNN_` module
    without a row in `pipeline/web/datasets.py` fails, the same way
    `tests/test_licences.py` fails for a module with no licence.
  * **The counts are measured, not declared.** The registry carries no
    numbers; `catalogue()` reads them from the warehouse, so a dataset can
    never advertise rows it does not have.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline import licences
from pipeline.config import Settings
from pipeline.exports import guard_not_restricted
from pipeline.web import datasets
from pipeline.web.datasets import DATASETS, EVIDENCE_LAYERS
from pipeline.web.server import build_server

ROOT = Path(__file__).resolve().parent.parent
COLLECTING_MODULES = {p.stem for p in (ROOT / "pipeline" / "modules").glob("m*.py")}


# --- the registry -----------------------------------------------------------


def test_every_collecting_module_has_exactly_one_catalogue_entry():
    assert COLLECTING_MODULES, "no modules found; the glob is wrong"
    registered = [d.module for d in DATASETS]
    missing = sorted(COLLECTING_MODULES - set(registered))
    extra = sorted(set(registered) - COLLECTING_MODULES)
    assert not missing, f"no catalogue entry for {missing}"
    assert not extra, f"catalogue entry for a module that does not exist: {extra}"
    assert len(registered) == len(set(registered)), "a module is catalogued twice"


def test_dataset_ids_are_unique_kebab_case_slugs():
    ids = [d.dataset_id for d in DATASETS]
    assert len(ids) == len(set(ids)), "duplicate dataset_id"
    for dataset_id in ids:
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", dataset_id), dataset_id
        # The route pattern only accepts up to 64 chars.
        assert len(dataset_id) <= 64


def test_every_entry_names_a_known_evidence_layer():
    for d in DATASETS:
        assert d.evidence_layer in EVIDENCE_LAYERS, (
            f"{d.dataset_id} is in unknown layer {d.evidence_layer!r}")


def test_every_public_table_is_portal_safe():
    """A restricted_ table or personal-data column named here would put its
    rows into the catalogue's counts. The same guard the export layer uses."""
    for d in DATASETS:
        assert d.public_tables, f"{d.dataset_id} lists no tables"
        for table in d.public_tables:
            guard_not_restricted(table)


def test_every_entry_has_a_licence_and_a_real_source_url():
    for d in DATASETS:
        assert licences.for_module(d.module), f"{d.module} has no licence"
        assert d.official_url.startswith("https://"), d.dataset_id
        assert d.publisher and d.caveat and d.geography and d.cadence, d.dataset_id


# --- the served catalogue -------------------------------------------------


@pytest.fixture
def client(settings: Settings, conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES ('E08000025', 'Birmingham', 'MD', 'West Midlands', '2021-04-01', "
        " '2024', '2026', 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, "
        " 'ons', 'geo1')")
    conn.executemany(
        "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
        " supplier_name_raw, title, value_core, currency, date_published, "
        " procedure_type, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES (?, ?, 'Birmingham City Council', 'E08000025', "
        " 'A Supplier Ltd', 'Treatment services', 1000, 'GBP', '2025-06-01', "
        " 'open', 'https://find.example/api', '2026-08-02T00:00:00Z', 200, "
        " 'find_a_tender', 'abc123')",
        [(f"n{i}", f"ocds-{i}") for i in range(3)])
    conn.commit()
    conn.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{server.server_address[1]}", timeout=15.0
        ) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_catalogue_lists_every_dataset_with_measured_counts(client):
    body = client.get("/api/v1/catalogue").json()
    assert body["count"] == len(DATASETS)
    assert body["evidence_layers"] == EVIDENCE_LAYERS
    assert "caveat" in body
    by_id = {d["dataset_id"]: d for d in body["datasets"]}
    assert set(by_id) == {d.dataset_id for d in DATASETS}

    geography = by_id["geography"]
    assert geography["row_count"] == 1
    assert geography["last_retrieved_at"] == "2026-08-01T00:00:00Z"
    assert geography["licence"]["id"] == "ogl_v3_os"

    procurement = by_id["procurement-notices"]
    assert procurement["row_count"] == 3
    assert procurement["last_retrieved_at"] == "2026-08-02T00:00:00Z"
    assert procurement["evidence_layer_label"] == EVIDENCE_LAYERS["procurement"]

    # A dataset that has not been collected in this warehouse reads zero, not
    # absent — that is the honest signal, not a bug.
    assert by_id["rough-sleeping"]["row_count"] == 0


def test_catalogue_detail_adds_the_full_licence_statement(client):
    entry = client.get("/api/v1/catalogue/workforce-census").json()
    assert entry["dataset_id"] == "workforce-census"
    assert entry["licence"]["id"] == "nhs_benchmarking"
    assert "Not open-licensed" in entry["licence_caution"]
    assert entry["licence_statement"]
    assert [t["name"] for t in entry["tables"]] == list(
        datasets.BY_ID["workforce-census"].public_tables)


def test_catalogue_detail_rejects_an_unknown_dataset(client):
    response = client.get("/api/v1/catalogue/not-a-dataset")
    assert response.status_code == 400
    assert "not-a-dataset" in response.json()["error"]
