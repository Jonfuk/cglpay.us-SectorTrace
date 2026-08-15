"""Module 19: the data.gov.uk CKAN catalogue.

Discovery metadata, and the two honest limits that keep it citable: the
query cap is said out loud, and the organisation pass links only exact
normalised name matches — a differently-spelled organisation is the universe
work's problem, not a guess here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pipeline.modules import m19_data_gov_uk as ckan
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str = "https://www.data.gov.uk") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="", is_reusable=True)


def _dataset(**overrides) -> dict:
    dataset = {
        "id": "b0f1b81a-8c69-4ae0-87ec-788c64656d7d",
        "name": "camden-substance-misuse-needs-assessment",
        "title": "Camden Substance Misuse Needs Assessment",
        "notes": "Profile of alcohol and substance misuse in Camden.",
        "url": "https://opendata.camden.gov.uk/d/wc9b-i8n2",
        "license_id": "uk-ogl",
        "license_title": "UK Open Government Licence (OGL)",
        "state": "active",
        "organization": {"id": "679a9f85", "name": "london-borough-of-camden",
                          "title": "London Borough of Camden"},
        "resources": [
            {"id": "db4e67a5", "name": "Download", "format": "PDF",
             "url": "https://opendata.camden.gov.uk/download/wc9b-i8n2/application/pdf",
             "description": None, "position": 0},
        ],
    }
    dataset.update(overrides)
    return dataset


def _search_response(*datasets) -> dict:
    return {"success": True, "result": {"count": len(datasets),
                                         "results": list(datasets)}}


def _add_authority(conn, ons_code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, "
        "first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'utla', '2023-01-01', '2023', '2026', "
        "'https://example.com/spine', '2026-01-01T00:00:00+00:00', 200, "
        "'test', 'abc')",
        (ons_code, name))


# --- merging ------------------------------------------------------------------

def test_terms_accumulate_across_passes():
    row = ckan._merge_row(
        {"matched_terms": "drug,alcohol", "matched_ons_code": None,
         "matched_provider_key": None},
        {"matched_terms": "alcohol,harm reduction", "matched_ons_code": None,
         "matched_provider_key": None})
    assert row["matched_terms"] == "drug,alcohol,harm reduction"


def test_organisation_link_merges_with_keyword_terms():
    row = ckan._merge_row(
        {"matched_terms": "drug", "matched_ons_code": None, "matched_provider_key": None},
        {"matched_terms": "", "matched_ons_code": "E09000007", "matched_provider_key": None})
    assert row["matched_terms"] == "drug"
    assert row["matched_ons_code"] == "E09000007"


def test_normalise_org_name_drops_suffix_words():
    # both sides of a match go through the same normalisation, so the words
    # dropped are the words that never distinguish a council's name
    assert ckan._normalise_org_name("London Borough of Camden") == "london of camden"
    assert ckan._normalise_org_name("Camden Council") == "camden"
    assert ckan._normalise_org_name("Wigan Council") == "wigan"
    assert ckan._normalise_org_name("Wigan") == "wigan"


# --- end to end ---------------------------------------------------------------

def test_run_keyword_pass_stores_datasets_and_resources(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    response = _search_response(_dataset(), _dataset(id="2560359f", title="Substance misuse",
                                                      resources=[]))
    httpx_mock.add_response(
        url=re.compile(r"https://www\.data\.gov\.uk/api/3/action/package_search.*"),
        json=response, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.data\.gov\.uk/api/3/action/organization_list.*"),
        json={"success": True, "result": []})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ckan.run(ctx)

    datasets = conn.execute(
        "SELECT * FROM data_gov_uk_datasets ORDER BY dataset_id").fetchall()
    assert len(datasets) == 2
    camden = {d["dataset_id"]: d for d in datasets}["b0f1b81a-8c69-4ae0-87ec-788c64656d7d"]
    assert camden["title"] == "Camden Substance Misuse Needs Assessment"
    assert camden["organisation_name"] == "London Borough of Camden"
    assert camden["license_id"] == "uk-ogl"
    assert "drug" in camden["matched_terms"]  # found under the keyword pass
    assert camden["source_url"].startswith("https://www.data.gov.uk/api/3/action")

    resources = conn.execute("SELECT * FROM data_gov_uk_resources").fetchall()
    assert len(resources) == 1
    assert resources[0]["resource_format"] == "PDF"
    assert resources[0]["resource_url"].startswith("https://opendata.camden.gov.uk")


def test_run_organisation_pass_links_exact_matches(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    # keyword pass finds nothing (0 results); the org pass finds Camden's
    # dataset because "London Borough of Camden" normalise-matches.
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*[?&]q=[^&]"),
        json={"success": True, "result": {"count": 0, "results": []}},
        is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*organization_list.*"),
        json=json.loads((FIXTURES / "ckan_organization_list.json").read_text()))
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*fq=organization"),
        json=_search_response(_dataset()), is_reusable=True)

    _add_authority(conn, "E09000007", "London Borough of Camden")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ckan.run(ctx)

    row = conn.execute("SELECT * FROM data_gov_uk_datasets").fetchone()
    assert row is not None
    assert row["matched_ons_code"] == "E09000007"
    assert row["matched_terms"] is None  # found only by the organisation pass


def test_run_does_not_link_a_near_miss_organisation(httpx_mock, settings, conn):
    """An authority whose catalogue sits under a differently-spelled
    organisation is not linked: no match, no review item, no guess."""
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*[?&]q=[^&]"),
        json={"success": True, "result": {"count": 0, "results": []}},
        is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*organization_list.*"),
        json={"success": True, "result": [
            {"name": "wigan-council", "title": "Wigan Council"}]})

    # "Salford City Council" normalises to "salford", which is not "wigan":
    # a genuinely different authority, not a spelling variant.
    _add_authority(conn, "E08000006", "Salford City Council")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ckan.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM data_gov_uk_datasets").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 0


def test_run_raises_a_review_item_when_a_query_is_capped(httpx_mock, settings, conn, monkeypatch):
    """The catalogue says 400 results; the module reads 300 and says so."""
    _allow_all_robots(httpx_mock)
    page = {"success": True, "result": {"count": 400, "results": [
        _dataset(id=f"id-{i}") for i in range(ckan.PAGE_SIZE)]}}
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*"), json=page, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*organization_list.*"), json={"success": True, "result": []})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ckan.run(ctx)

    review = conn.execute("SELECT * FROM review_queue WHERE item_type='data_gov_uk_query_capped'").fetchall()
    assert review, "the cap must be said out loud, never silent"
    assert conn.execute("SELECT COUNT(*) c FROM data_gov_uk_datasets").fetchone()["c"] == 100
