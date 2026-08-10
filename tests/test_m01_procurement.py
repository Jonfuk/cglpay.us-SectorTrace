from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.modules import m01_procurement as proc
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str) -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="")


def _seed_authority(conn, ons_code: str, name: str) -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, last_seen_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'unitary', '2020-01-01', 'x', 'x', 'https://example.com', '2020-01-01T00:00:00Z', 200, 'test', 'abc')",
        (ons_code, name),
    )


# --- buyer name normalisation / matching ------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("West Northamptonshire Council", "west northamptonshire"),
    ("Birmingham City Council", "birmingham"),
    ("Kent County Council", "kent"),
    ("London Borough of Hackney", "hackney"),
    ("Royal Borough of Kensington and Chelsea", "kensington and chelsea"),
    ("Wigan Metropolitan Borough Council", "wigan"),
    ("City of London Corporation", "london corporation"),
])
def test_normalise_authority_name(raw, expected):
    assert proc._normalise_authority_name(raw) == expected


def test_match_buyer_exact_normalised_match(conn):
    _seed_authority(conn, "E06000061", "West Northamptonshire")
    lookup = proc._build_authority_lookup(conn)
    assert proc._match_buyer("West Northamptonshire Council", lookup) == "E06000061"


def test_match_buyer_falls_back_to_overrides(conn, monkeypatch):
    lookup = proc._build_authority_lookup(conn)
    monkeypatch.setitem(proc.BUYER_NAME_OVERRIDES, "Some Odd Council Name", "E06000099")
    assert proc._match_buyer("Some Odd Council Name", lookup) == "E06000099"


def test_match_buyer_returns_none_when_unmatched(conn):
    lookup = proc._build_authority_lookup(conn)
    assert proc._match_buyer("Totally Unknown Body Ltd", lookup) is None


def test_match_buyer_resolves_retired_authority(conn):
    # LGR: a notice referencing an abolished council must still join.
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, active_to, first_seen_vintage, last_seen_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000021', 'Northamptonshire', 'county', '2015-01-01', '2021-04-01', 'x', 'x', "
        "'https://example.com', '2020-01-01T00:00:00Z', 200, 'test', 'abc')"
    )
    lookup = proc._build_authority_lookup(conn)
    assert proc._match_buyer("Northamptonshire County Council", lookup) == "E10000021"


# --- CPV / keyword / supplier scope matching ---------------------------------

def test_extract_cpv_codes_from_tender_and_award_items():
    release = {
        "tender": {"items": [{"additionalClassifications": [{"scheme": "CPV", "id": "85000000"}]}]},
        "awards": [{"items": [{"additionalClassifications": [{"scheme": "CPV", "id": "85312000"}]}]}],
    }
    assert proc._extract_cpv_codes(release) == {"85000000", "85312000"}


def test_release_matches_scope_via_keyword():
    release = {"tender": {"title": "Substance misuse recovery service recommissioning", "description": ""}}
    assert proc._release_matches_scope(release)


def test_release_matches_scope_via_cpv_prefix():
    release = {"tender": {"title": "Unrelated title", "items": [
        {"additionalClassifications": [{"scheme": "CPV", "id": "85312300"}]}
    ]}}
    assert proc._release_matches_scope(release)


def test_release_matches_scope_via_supplier_name():
    release = {"tender": {"title": "Generic transport services"},
               "parties": [{"name": "Change, Grow, Live", "roles": ["supplier"]}]}
    assert proc._release_matches_scope(release)


def test_release_does_not_match_unrelated_release():
    release = {"tender": {"title": "Playground equipment supply", "items": [
        {"additionalClassifications": [{"scheme": "CPV", "id": "37535200"}]}
    ]}, "parties": [{"name": "Some Playground Co", "roles": ["supplier"]}]}
    assert not proc._release_matches_scope(release)


# --- PSR / direct award / procedure classification ---------------------------

def test_classify_procedure_detects_psr_by_legal_basis_id():
    tender = {"procurementMethod": "limited", "procurementMethodDetails": "Direct award",
              "legalBasis": {"id": "2023/1348", "scheme": "UKSI"}}
    procedure_type, psr = proc._classify_procedure(tender)
    assert psr is True
    assert procedure_type == "limited: Direct award"


def test_classify_procedure_not_psr_for_procurement_act():
    tender = {"procurementMethod": "open", "procurementMethodDetails": "Below threshold - open competition",
              "legalBasis": {"id": "2023/54", "scheme": "UKPGA"}}
    _, psr = proc._classify_procedure(tender)
    assert psr is False


@pytest.mark.parametrize("text,expected", [
    ("Awarded via Direct Award 2 under PSR", "DA2"),
    ("This uses DA3 of the Provider Selection Regime", "DA3"),
    ("No mention of any option here", None),
])
def test_extract_direct_award_option(text, expected):
    assert proc._extract_direct_award_option(text) == expected


# --- supplier/award fan-out ---------------------------------------------------

def test_iter_supplier_rows_no_award_yet():
    rows = proc._iter_supplier_rows({"tender": {"status": "planned"}})
    assert len(rows) == 1
    assert rows[0]["supplier_id"] == ""


def test_iter_supplier_rows_single_award_single_supplier():
    release = {
        "awards": [{"id": "1", "value": {"amount": 90000, "currency": "GBP"},
                    "suppliers": [{"id": "GB-FTS-1", "name": "H2S Cars Ltd"}]}],
        "contracts": [{"awardID": "1", "period": {"startDate": "2026-09-02", "endDate": "2028-07-23"}}],
    }
    rows = proc._iter_supplier_rows(release)
    assert len(rows) == 1
    assert rows[0]["supplier_id"] == "GB-FTS-1"
    assert rows[0]["value_core"] == 90000
    assert rows[0]["date_start"] == "2026-09-02"


def test_iter_supplier_rows_multi_lot_multi_supplier():
    release = {"awards": [
        {"id": "1", "value": {"amount": 1000}, "suppliers": [{"id": "S1", "name": "Supplier One"}]},
        {"id": "2", "value": {"amount": 2000}, "suppliers": [{"id": "S2", "name": "Supplier Two"}]},
    ]}
    rows = proc._iter_supplier_rows(release)
    assert {r["supplier_id"] for r in rows} == {"S1", "S2"}
    assert {r["value_core"] for r in rows} == {1000, 2000}


# --- end-to-end release processing against a real fixture --------------------

def test_process_release_against_real_fts_fixture(conn):
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    _seed_authority(conn, "E06000061", "West Northamptonshire")
    lookup = proc._build_authority_lookup(conn)

    class _FakeResult:
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?x=1"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    written = proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), lookup)
    assert written == 1

    row = conn.execute("SELECT * FROM contracts WHERE notice_id = ?", (release["id"],)).fetchone()
    assert row["buyer_ons_code"] == "E06000061"
    assert row["supplier_name_raw"] == "H2S Cars Ltd"
    assert row["value_core"] == 90000
    assert row["cpv_codes"] == "60000000"
    assert row["date_start"] == "2026-09-02T00:00:00Z"


def test_process_release_logs_review_item_for_unmatched_buyer(conn):
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    lookup = {}  # empty authorities table -> buyer can't match

    class _FakeResult:
        url = "https://example.com"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), lookup)
    rows = conn.execute("SELECT * FROM review_queue WHERE item_type = 'unmatched_buyer_name'").fetchall()
    assert len(rows) == 1
    assert rows[0]["raw_value"] == "West Northamptonshire Council"


# --- pagination / resumability -----------------------------------------------

def test_walk_and_process_follows_pagination_and_marks_done(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.find-tender.service.gov.uk")
    page1 = {"releases": [{"id": "1-2026", "ocid": "ocds-h6vhtk-000001",
                            "tender": {"title": "substance misuse service"}}],
             "links": {"next": "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?cursor=abc"}}
    page2 = {"releases": [{"id": "2-2026", "ocid": "ocds-h6vhtk-000002",
                            "tender": {"title": "irrelevant playground kit"}}]}
    httpx_mock.add_response(url=re.compile(r".*ocdsReleasePackages\?updatedFrom.*"), json=page1)
    httpx_mock.add_response(url="https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?cursor=abc", json=page2)

    with PipelineHTTPClient(proc.SOURCE_FTS, settings=settings, conn=conn) as client:
        matched = proc._walk_and_process(
            client, conn, "m01_procurement", proc.SOURCE_FTS, proc.FTS_URL,
            ("updatedFrom", "updatedTo"), None, date(2026, 1, 1), date(2026, 1, 2),
            "m01_procurement:fts", {}, None, False,
        )

    assert matched == 1  # only the substance-misuse-titled release matches scope
    cursor = db.get_cursor(conn, "m01_procurement:fts")
    assert cursor == "DONE:2026-01-02"


def test_walk_and_process_stops_at_limit_and_saves_resume_url(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.find-tender.service.gov.uk")
    page1 = {"releases": [{"id": "1-2026", "ocid": "ocds-h6vhtk-000001", "tender": {}},
                           {"id": "2-2026", "ocid": "ocds-h6vhtk-000002", "tender": {}}],
             "links": {"next": "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?cursor=abc"}}
    httpx_mock.add_response(url=re.compile(r".*ocdsReleasePackages\?updatedFrom.*"), json=page1)

    with PipelineHTTPClient(proc.SOURCE_FTS, settings=settings, conn=conn) as client:
        proc._walk_and_process(
            client, conn, "m01_procurement", proc.SOURCE_FTS, proc.FTS_URL,
            ("updatedFrom", "updatedTo"), None, date(2026, 1, 1), date(2026, 1, 2),
            "m01_procurement:fts", {}, 1, False,
        )

    cursor = db.get_cursor(conn, "m01_procurement:fts")
    assert cursor.startswith("URL:")


def test_resolve_start_resumes_from_saved_url(conn):
    db.set_cursor(conn, "m01_procurement:fts", "URL:https://example.com/next")
    resume_url, _ = proc._resolve_start(conn, "m01_procurement:fts", None, date(2020, 1, 1))
    assert resume_url == "https://example.com/next"


def test_resolve_start_uses_done_date_for_incremental_run(conn):
    db.set_cursor(conn, "m01_procurement:fts", "DONE:2026-06-01")
    resume_url, window_from = proc._resolve_start(conn, "m01_procurement:fts", None, date(2020, 1, 1))
    assert resume_url is None
    assert window_from == date(2026, 6, 1)


def test_resolve_start_explicit_since_overrides_cursor(conn):
    db.set_cursor(conn, "m01_procurement:fts", "DONE:2026-06-01")
    resume_url, window_from = proc._resolve_start(conn, "m01_procurement:fts", "2021-01-01", date(2020, 1, 1))
    assert resume_url is None
    assert window_from == date(2021, 1, 1)


# --- supplier alias seeding ---------------------------------------------------

def test_seed_supplier_aliases_populates_table(conn):
    proc._seed_supplier_aliases(conn)
    row = conn.execute("SELECT * FROM supplier_aliases WHERE alias_raw = 'CGL'").fetchone()
    assert row["supplier_key"] == "change_grow_live"


def test_match_supplier_key_exact_variant_only():
    assert proc._match_supplier_key("Change Grow Live") is not None
    assert proc._match_supplier_key("Change Grow Livee") is None  # no fuzzy matching
    assert proc._match_supplier_key(None) is None


# --- full run() integration ---------------------------------------------------

def test_run_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.find-tender.service.gov.uk")
    _allow_all_robots(httpx_mock, "https://www.contractsfinder.service.gov.uk")

    _seed_authority(conn, "E06000061", "West Northamptonshire")
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    # the real fixture is a passenger-transport award, genuinely out of
    # scope — retitle it in-place so this test exercises the full
    # match -> process -> persist path against a realistic release shape.
    release["tender"]["title"] = "Substance misuse treatment and recovery service recommissioning"

    fts_page = {"releases": [release]}
    cf_page = {"releases": []}
    httpx_mock.add_response(url=re.compile(r".*find-tender.*ocdsReleasePackages\?updatedFrom.*"), json=fts_page)
    httpx_mock.add_response(url=re.compile(r".*contractsfinder.*publishedFrom.*"), json=cf_page)

    ctx = ModuleContext(conn=conn, settings=settings, since="2026-08-01", dry_run=False, limit=None)
    proc.run(ctx)

    row = conn.execute("SELECT * FROM contracts WHERE notice_id = ?", (release["id"],)).fetchone()
    assert row is not None
    assert row["buyer_ons_code"] == "E06000061"
    assert db.get_cursor(conn, "m01_procurement:fts").startswith("DONE:")
    assert db.get_cursor(conn, "m01_procurement:cf").startswith("DONE:")
