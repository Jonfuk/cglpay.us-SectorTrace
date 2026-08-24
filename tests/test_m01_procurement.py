from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

import pytest

from pipeline import db, notice_urls
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


def test_extract_cpv_codes_from_item_primary_classification():
    """Regression: the pre-2020 Contracts Finder OCDS export (what the CSV
    archive channel reconstructs) puts an item's CPV code under
    `classification`, not `additionalClassifications` -- a real 2015 notice
    ("Derbyshire Educational Psychology Service") was invisible to scope
    matching until this was checked too, confirmed against the archived
    bytes 2026-08-23.
    """
    release = {
        "tender": {"items": [{"classification": {"scheme": "CPV", "id": "85000000"}}]},
        "awards": [{"items": [{"classification": {"scheme": "CPV", "id": "85312000"}}]}],
    }
    assert proc._extract_cpv_codes(release) == {"85000000", "85312000"}


def test_extract_cpv_codes_from_both_item_classification_fields_at_once():
    release = {"tender": {"items": [{
        "classification": {"scheme": "CPV", "id": "85000000"},
        "additionalClassifications": [{"scheme": "CPV", "id": "85312000"}],
    }]}}
    assert proc._extract_cpv_codes(release) == {"85000000", "85312000"}


def test_release_matches_scope_via_item_primary_classification():
    release = {"tender": {"title": "Derbyshire Educational Psychology Service", "items": [
        {"classification": {"scheme": "CPV", "id": "85000000"}}
    ]}}
    assert proc._release_matches_scope(release)


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
    # The notice's own page, published by the release. The API cursor stays in
    # source_url, where the provenance belongs.
    assert row["notice_web_url"] == "https://www.find-tender.service.gov.uk/Notice/072960-2026"
    assert row["source_url"] == _FakeResult.url


# --- the notice's address, as distinct from the fetch's ----------------------
#
# All of these are about one thing: a link a reader follows must reach the
# notice this row is about. The documents array in a release is not a list of
# notice pages -- it carries attachments, bidding packs on third-party
# portals, and sometimes a link to a different notice entirely.


@pytest.mark.parametrize("notice_id, expected", [
    # Find a Tender: the release id is the notice.
    ("076079-2026", "076079-2026"),
    # Contracts Finder: notice GUID, then the release sequence.
    ("5f01b648-fca2-4a25-abed-09d788ae4cc2-910254",
      "5f01b648-fca2-4a25-abed-09d788ae4cc2"),
    ("", None),
])
def test_notice_slug(notice_id, expected):
    assert notice_urls.notice_slug(notice_id) == expected


def _release(notice_id: str, *urls: str) -> dict:
    return {"id": notice_id,
             "contracts": [{"documents": [{"url": u} for u in urls]}]}


def test_notice_url_is_taken_only_when_the_release_publishes_it():
    release = _release("076079-2026",
                        "https://www.find-tender.service.gov.uk/Notice/076079-2026")
    assert notice_urls.published_notice_url(release, proc.SOURCE_FTS) == (
        "https://www.find-tender.service.gov.uk/Notice/076079-2026")


def test_a_release_with_no_notice_link_gets_null_not_a_guess():
    """NULL is the normal case here, not a failure. The portal constructs a
    labelled link at read time; nothing is invented into the table."""
    release = _release("076079-2026",
                        "https://in-tendhost.co.uk/milton-keynes")
    assert notice_urls.published_notice_url(release, proc.SOURCE_FTS) is None


@pytest.mark.parametrize("url", [
    # Both share the /Notice/ prefix and neither is a notice. Every one of the
    # 18,048 archived URLs that failed the id rule was one of these.
    "https://www.find-tender.service.gov.uk/Notice/Attachment/A-13118",
    "https://www.contractsfinder.service.gov.uk/Notice/SupplierAttachment/"
    "c12c7b6f-4626-4877-8926-828643887b97",
    # A release citing a different notice. Following it would show a reader a
    # document about something else.
    "https://www.find-tender.service.gov.uk/Notice/000822-2022",
])
def test_an_attachment_or_another_notice_is_not_this_notice(url):
    assert notice_urls.published_notice_url(_release("033897-2022", url), proc.SOURCE_FTS) is None


def test_a_notice_url_on_another_host_is_refused():
    """The host is half the check: only the publishing service serves the
    notice, whatever a document on somebody else's portal is called."""
    release = _release("076079-2026",
                        "https://example.org/Notice/076079-2026")
    assert notice_urls.published_notice_url(release, proc.SOURCE_FTS) is None


def test_the_contracts_finder_notice_is_found_from_an_award_document():
    release = {
        "id": "ae57c38a-0427-41e1-9c23-25b094277d3d-906531",
        "awards": [{"documents": [
            {"documentType": "awardNotice",
              "url": "https://www.contractsfinder.service.gov.uk/Notice/"
                     "ae57c38a-0427-41e1-9c23-25b094277d3d"}]}],
    }
    assert notice_urls.published_notice_url(release, proc.SOURCE_CF) == (
        "https://www.contractsfinder.service.gov.uk/Notice/"
        "ae57c38a-0427-41e1-9c23-25b094277d3d")


def test_an_unknown_source_system_has_no_notice_host():
    release = _release("076079-2026",
                        "https://www.find-tender.service.gov.uk/Notice/076079-2026")
    assert notice_urls.published_notice_url(release, "some_other_feed") is None


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
    _allow_all_robots(httpx_mock, "https://ckan.publishing.service.gov.uk")

    _seed_authority(conn, "E06000061", "West Northamptonshire")
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    # the real fixture is a passenger-transport award, genuinely out of
    # scope — retitle it in-place so this test exercises the full
    # match -> process -> persist path against a realistic release shape.
    release["tender"]["title"] = "Substance misuse treatment and recovery service recommissioning"

    fts_page = {"releases": [release]}
    cf_page = {"releases": []}
    ckan_page = {"success": True, "result": {"count": 0, "results": []}}
    httpx_mock.add_response(url=re.compile(r".*find-tender.*ocdsReleasePackages\?updatedFrom.*"), json=fts_page)
    httpx_mock.add_response(url=re.compile(r".*contractsfinder.*publishedFrom.*"), json=cf_page)
    httpx_mock.add_response(url=re.compile(r".*ckan\.publishing\.service\.gov\.uk.*package_search.*"), json=ckan_page)

    ctx = ModuleContext(conn=conn, settings=settings, since="2026-08-01", dry_run=False, limit=None)
    proc.run(ctx)

    row = conn.execute("SELECT * FROM contracts WHERE notice_id = ?", (release["id"],)).fetchone()
    assert row is not None
    assert row["buyer_ons_code"] == "E06000061"
    assert db.get_cursor(conn, "m01_procurement:fts").startswith("DONE:")
    assert db.get_cursor(conn, "m01_procurement:cf").startswith("DONE:")


# --- Contracts Finder CSV archive ---------------------------------------------

def test_unflatten_release_row_reconstructs_nested_shape():
    row = {
        "uri": "https://www.contractsfinder.service.gov.uk/Published/Notice/releases/x.json",
        "publishedDate": "2019-06-30T17:31:14+01:00",
        "releases/0/ocid": "ocds-b5fd17-abc",
        "releases/0/id": "4e24328a-95cd-43b6-97f4-4c6cb25649ab-298466",
        "releases/0/tag/0": "award",
        "releases/0/tender/title": "Recovery service",
        "releases/0/tender/classification/scheme": "CPV",
        "releases/0/tender/classification/id": "85312000",
        "releases/0/tender/value/amount": "90000",
        "releases/0/tender/value/currency": "GBP",
        "releases/0/buyer/name": "West Northamptonshire Council",
        "releases/0/parties/0/name": "West Northamptonshire Council",
        "releases/0/parties/0/roles/0": "buyer",
        "releases/0/parties/1/name": "Change, Grow, Live",
        "releases/0/parties/1/roles/0": "supplier",
        "releases/0/awards/0/id": "1",
        "releases/0/awards/0/value/amount": "90000",
        "releases/0/awards/0/suppliers/0/id": "S1",
        "releases/0/awards/0/suppliers/0/name": "Change, Grow, Live",
        # blank cells -- the CSV form of "absent" -- must not appear as ""
        "releases/0/tender/description": "",
    }
    release = proc._unflatten_release_row(row)

    assert release["ocid"] == "ocds-b5fd17-abc"
    assert release["id"] == "4e24328a-95cd-43b6-97f4-4c6cb25649ab-298466"
    assert release["tag"] == ["award"]
    assert release["tender"]["classification"] == {"scheme": "CPV", "id": "85312000"}
    assert "description" not in release["tender"]
    assert release["buyer"] == {"name": "West Northamptonshire Council"}
    assert release["parties"][0] == {"name": "West Northamptonshire Council", "roles": ["buyer"]}
    assert release["parties"][1] == {"name": "Change, Grow, Live", "roles": ["supplier"]}
    assert release["awards"][0]["suppliers"][0] == {"id": "S1", "name": "Change, Grow, Live"}
    # OCDS Amount fields are numeric regardless of nesting depth or path.
    assert release["tender"]["value"]["amount"] == 90000.0
    assert isinstance(release["tender"]["value"]["amount"], float)
    assert release["awards"][0]["value"]["amount"] == 90000.0


def test_unflatten_release_row_ignores_package_level_columns():
    row = {"uri": "https://example.com/x.json", "publisher/name": "Cabinet Office",
           "releases/0/id": "abc-1"}
    release = proc._unflatten_release_row(row)
    assert release == {"id": "abc-1"}


def test_unflatten_release_row_drops_padded_none_list_gaps():
    """Real-world crash fixture: a CSV file's column set is shared across
    every release in it, and a release whose first populated value at some
    array path is index 2 (nothing this release had at 0 or 1 fell inside
    this file's columns) makes `_assign_flattened_path` pad indices 0 and 1
    with `None` to reach index 2. Left in, that `None` reaches
    `_process_release`'s `p.get("roles")` over `parties` as something with
    no `.get()` -- an AttributeError seen against a real archive month.
    """
    row = {
        "releases/0/id": "abc-1",
        "releases/0/parties/2/name": "Change, Grow, Live",
        "releases/0/parties/2/roles/0": "supplier",
    }
    release = proc._unflatten_release_row(row)

    assert release["parties"] == [{"name": "Change, Grow, Live", "roles": ["supplier"]}]


def test_process_csv_release_row_matches_and_persists(conn):
    _seed_authority(conn, "E06000061", "West Northamptonshire")
    row = {
        "releases/0/ocid": "ocds-b5fd17-hist1",
        "releases/0/id": "4e24328a-95cd-43b6-97f4-4c6cb25649ab-298466",
        "releases/0/tender/title": "Substance misuse recovery service",
        "releases/0/buyer/name": "West Northamptonshire Council",
    }

    class _FakeResult:
        url = "https://cdp-sirsi-production-cfs.s3.eu-west-2.amazonaws.com/Harvester-new/2016-06/x.csv"
        retrieved_at = __import__("datetime").datetime(2026, 8, 22, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    written = proc._process_csv_release_row(
        conn, "m01_procurement", proc.SOURCE_CF_CSV, row, _FakeResult(), proc._build_authority_lookup(conn))
    assert written == 1

    stored = conn.execute("SELECT * FROM contracts WHERE notice_id = ?",
                           (row["releases/0/id"],)).fetchone()
    assert stored["buyer_ons_code"] == "E06000061"
    assert stored["source_system"] == proc.SOURCE_CF_CSV
    # Same host as the live channel -- the notice lives on Contracts Finder
    # regardless of which channel fetched the bytes.
    assert stored["notice_web_url"] is None or "contractsfinder.service.gov.uk" in stored["notice_web_url"]


def test_process_csv_release_row_out_of_scope_writes_nothing(conn):
    row = {"releases/0/id": "abc-1", "releases/0/tender/title": "Playground equipment"}
    written = proc._process_csv_release_row(conn, "m01_procurement", proc.SOURCE_CF_CSV,
                                             row, object(), {})
    assert written == 0
    assert conn.execute("SELECT * FROM contracts").fetchone() is None


def _ckan_package(title: str, name: str, csv_count: int, modified: str) -> dict:
    resources = [{"format": "CSV", "url": f"https://s3.example/{name}-{i}.csv"} for i in range(csv_count)]
    resources.append({"format": "HTML", "url": "https://standard.open-contracting.org/"})
    return {"title": title, "name": name, "metadata_modified": modified, "resources": resources}


def test_select_best_cf_csv_packages_prefers_more_csv_resources():
    packages = [
        _ckan_package("Contracts Finder Notices 09 2021", "contracts-finder-notices-09-20214", 0, "2018-01-10"),
        _ckan_package("Contracts Finder Notices 09 2021", "contracts-finder-notices-09-20215", 30, "2026-08-20"),
    ]
    best = proc._select_best_cf_csv_packages(packages)
    assert best[(2021, 9)]["name"] == "contracts-finder-notices-09-20215"


def test_select_best_cf_csv_packages_ties_break_on_recency():
    packages = [
        _ckan_package("Contracts Finder Notices 06 2016", "contracts-finder-notices-06-2016", 30, "2018-01-10"),
        _ckan_package("Contracts Finder Notices 06 2016", "contracts-finder-notices-06-20162", 30, "2026-08-20"),
    ]
    best = proc._select_best_cf_csv_packages(packages)
    assert best[(2016, 6)]["name"] == "contracts-finder-notices-06-20162"


def test_select_best_cf_csv_packages_ignores_unrelated_titles():
    packages = [{"title": "Something else entirely", "name": "x", "resources": []}]
    assert proc._select_best_cf_csv_packages(packages) == {}


def test_discover_cf_csv_months_paginates_and_filters_to_window(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://ckan.publishing.service.gov.uk")
    page1 = {"success": True, "result": {"count": 2, "results": [
        _ckan_package("Contracts Finder Notices 12 2014", "contracts-finder-notices-12-2014", 4, "2018-01-10"),
    ]}}
    page2 = {"success": True, "result": {"count": 2, "results": [
        # This month is on/after WINDOW_START (2020-08-06) and must be excluded --
        # the live API channel already covers it.
        _ckan_package("Contracts Finder Notices 09 2020", "contracts-finder-notices-09-2020", 30, "2026-08-20"),
    ]}}
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*start=0.*"), json=page1)
    httpx_mock.add_response(
        url=re.compile(r".*package_search.*start=1.*"), json=page2)

    with PipelineHTTPClient(proc.SOURCE_CF_CSV, settings=settings, conn=conn) as client:
        months = proc._discover_cf_csv_months(client, conn, "m01_procurement", proc.WINDOW_START)

    assert [m[0] for m in months] == [date(2014, 12, 1)]


def test_walk_and_process_csv_archive_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://ckan.publishing.service.gov.uk")
    _allow_all_robots(httpx_mock, "https://cdp-sirsi-production-cfs.s3.eu-west-2.amazonaws.com")
    _seed_authority(conn, "E06000061", "West Northamptonshire")

    package = _ckan_package("Contracts Finder Notices 06 2016", "contracts-finder-notices-06-2016", 0, "2018-01-10")
    package["resources"] = [{
        "format": "CSV",
        "url": "https://cdp-sirsi-production-cfs.s3.eu-west-2.amazonaws.com/Harvester-new/2016-06/day1.csv",
    }]
    ckan_response = {"success": True, "result": {"count": 1, "results": [package]}}
    httpx_mock.add_response(url=re.compile(r".*package_search.*"), json=ckan_response)

    csv_body = (
        "releases/0/ocid,releases/0/id,releases/0/tender/title,releases/0/buyer/name\r\n"
        "ocds-b5fd17-hist1,4e24328a-95cd-43b6-97f4-4c6cb25649ab-298466,"
        "Substance misuse recovery service,West Northamptonshire Council\r\n"
    )
    httpx_mock.add_response(url=package["resources"][0]["url"], text=csv_body)

    with PipelineHTTPClient(proc.SOURCE_CF_CSV, settings=settings, conn=conn) as client:
        matched = proc._walk_and_process_csv_archive(
            client, conn, "m01_procurement", proc.SOURCE_CF_CSV,
            "m01_procurement:cf_csv", proc.WINDOW_START,
            proc._build_authority_lookup(conn), None, False,
        )

    assert matched == 1
    row = conn.execute(
        "SELECT * FROM contracts WHERE notice_id = ?",
        ("4e24328a-95cd-43b6-97f4-4c6cb25649ab-298466",)).fetchone()
    assert row["buyer_ons_code"] == "E06000061"
    assert row["source_system"] == proc.SOURCE_CF_CSV
    assert db.get_cursor(conn, "m01_procurement:cf_csv") == "DONE:2016-06-01"


def test_walk_and_process_csv_archive_skips_robots_disallowed_file(httpx_mock, settings, conn):
    """A resource host with no configured robots_exceptions entry must not
    take the whole month down if its robots.txt blocks a file -- the
    disallowed file is recorded to review_queue and its siblings still
    process, exactly like every other module that walks many individual
    files (m09/m10/m15/m22/m24/m28). www.dropbox.com is the real host this
    was found against (a handful of the earliest, Dec-2014 archive files),
    but that host now has its own robots_exceptions entry and would no
    longer reach this code path -- so this uses an unrelated host that
    carries no exception, to keep exercising the fallback itself.
    """
    _allow_all_robots(httpx_mock, "https://ckan.publishing.service.gov.uk")
    _allow_all_robots(httpx_mock, "https://cdp-sirsi-production-cfs.s3.eu-west-2.amazonaws.com")
    httpx_mock.add_response(
        url="https://blocked-mirror.test/robots.txt", status_code=200,
        text="User-agent: *\nDisallow: /\n")
    _seed_authority(conn, "E06000061", "West Northamptonshire")

    package = _ckan_package("Contracts Finder Notices 12 2014", "contracts-finder-notices-12-2014", 0, "2018-01-10")
    package["resources"] = [
        {"format": "CSV", "url": "https://blocked-mirror.test/day0.csv"},
        {"format": "CSV", "url": "https://cdp-sirsi-production-cfs.s3.eu-west-2.amazonaws.com/Harvester-new/2014-12/day1.csv"},
    ]
    ckan_response = {"success": True, "result": {"count": 1, "results": [package]}}
    httpx_mock.add_response(url=re.compile(r".*package_search.*"), json=ckan_response)

    csv_body = (
        "releases/0/ocid,releases/0/id,releases/0/tender/title,releases/0/buyer/name\r\n"
        "ocds-b5fd17-hist2,4e24328a-95cd-43b6-97f4-4c6cb25649ab-298467,"
        "Substance misuse recovery service,West Northamptonshire Council\r\n"
    )
    httpx_mock.add_response(url=package["resources"][1]["url"], text=csv_body)

    with PipelineHTTPClient(proc.SOURCE_CF_CSV, settings=settings, conn=conn) as client:
        matched = proc._walk_and_process_csv_archive(
            client, conn, "m01_procurement", proc.SOURCE_CF_CSV,
            "m01_procurement:cf_csv", proc.WINDOW_START,
            proc._build_authority_lookup(conn), None, False,
        )

    assert matched == 1
    row = conn.execute(
        "SELECT * FROM contracts WHERE notice_id = ?",
        ("4e24328a-95cd-43b6-97f4-4c6cb25649ab-298467",)).fetchone()
    assert row is not None
    review_row = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'cf_csv_file_robots_disallowed'").fetchone()
    assert review_row["raw_value"] == "https://blocked-mirror.test/day0.csv"
    # The month still completes -- one disallowed file does not stall the cursor.
    assert db.get_cursor(conn, "m01_procurement:cf_csv") == "DONE:2014-12-01"


def test_process_release_records_a_channel_sighting(conn):
    """Every channel that writes `contracts` also leaves a notice-level
    summary in procurement_channel_sightings -- not just --kag -- so the
    three supply routes can be compared against each other directly.
    """
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    _seed_authority(conn, "E06000061", "West Northamptonshire")
    lookup = proc._build_authority_lookup(conn)

    class _FakeResult:
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?x=1"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), lookup)

    row = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE notice_id = ? AND source_system = ?",
        (release["id"], proc.SOURCE_FTS)).fetchone()
    assert row is not None
    assert row["buyer_name"] == "West Northamptonshire Council"
    assert row["total_award_value_amount"] == 90000
    assert row["supplier_names"] == "H2S Cars Ltd"


# --- Kaggle cross-check archive ------------------------------------------------

def _kaggle_result(url: str = "https://www.kaggle.com/api/v1/datasets/download/x") -> object:
    class _FakeResult:
        pass

    result = _FakeResult()
    result.url = url
    result.retrieved_at = __import__("datetime").datetime(2026, 8, 23, tzinfo=__import__("datetime").timezone.utc)
    result.status_code = 200
    result.payload_sha256 = "kaggledeadbeef"
    return result


def test_kaggle_field_matches_across_naming_variants():
    """The real file's column names were not independently verified against
    a fetched copy until after this channel first ran -- the lookup has to
    survive both the uploader's own extraction-script names and the file's
    actual, simpler names for the same logical fields (confirmed live
    2026-08-23: e.g. `buyer` and `tender_value`, not `buyer_name`/
    `value_amount`).
    """
    index_a = proc._kaggle_column_index(["ocid", "tender_title", "tender_end_date"])
    index_b = proc._kaggle_column_index(["OCID", "Tender_Title", "tender_endDate"])

    row_a = {"ocid": "ocds-abc", "tender_title": "Recovery service", "tender_end_date": "2026-01-01"}
    row_b = {"OCID": "ocds-abc", "Tender_Title": "Recovery service", "tender_endDate": "2026-01-01"}

    for row, index in ((row_a, index_a), (row_b, index_b)):
        assert proc._kaggle_field(row, index, "ocid") == "ocds-abc"
        assert proc._kaggle_field(row, index, "tender_title", "release_title", "title") == "Recovery service"


def test_kaggle_field_returns_none_for_blank_or_missing():
    index = proc._kaggle_column_index(["buyer"])
    assert proc._kaggle_field({"buyer": ""}, index, "buyer") is None
    assert proc._kaggle_field({"buyer": "X"}, index, "cpv_main") is None


def test_map_kaggle_row_to_release_builds_ocds_shape():
    """Field names match the live file's real header (confirmed 2026-08-23),
    not the uploader's own extraction-script names -- see the module
    docstring on why the two differ and why lookup is defensive regardless.
    """
    row = {
        "ocid": "ocds-b5fd17-abc",
        "tender_title": "Substance misuse recovery service",
        "buyer": "West Northamptonshire Council",
        "CPV_main": "85312000",
        "tender_value": "90000",
        "award_value": "90000",
        "supplier": "Change, Grow, Live",
    }
    index = proc._kaggle_column_index(list(row.keys()))
    release = proc._map_kaggle_row_to_release(row, index)

    # No separate release id in this file -- ocid stands in for it (see the mapper's docstring).
    assert release["id"] == "ocds-b5fd17-abc"
    assert release["ocid"] == "ocds-b5fd17-abc"
    assert release["tender"]["value"] == {"amount": 90000.0, "currency": None}
    assert release["tender"]["classification"] == {"scheme": "CPV", "id": "85312000"}
    assert release["buyer"] == {"name": "West Northamptonshire Council"}
    assert release["awards"][0]["suppliers"] == [{"id": "", "name": "Change, Grow, Live"}]


def test_map_kaggle_row_to_release_none_without_an_ocid():
    assert proc._map_kaggle_row_to_release({"buyer": "X"}, {"buyer": "buyer"}) is None


def test_process_kaggle_release_row_out_of_scope_writes_nothing(conn):
    row = {"ocid": "ocds-1", "tender_title": "Playground equipment"}
    index = proc._kaggle_column_index(list(row.keys()))
    written = proc._process_kaggle_release_row(conn, "m01_procurement", row, index, _kaggle_result())
    assert written == 0
    assert conn.execute("SELECT * FROM procurement_channel_sightings").fetchone() is None


def test_process_kaggle_release_row_matched_writes_sighting_and_coverage_gap(conn):
    row = {
        "ocid": "ocds-2", "tender_title": "Substance misuse recovery service",
        "buyer": "West Northamptonshire Council", "tender_value": "50000",
    }
    index = proc._kaggle_column_index(list(row.keys()))
    written = proc._process_kaggle_release_row(conn, "m01_procurement", row, index, _kaggle_result())
    assert written == 1

    sighting = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE notice_id = 'ocds-2'").fetchone()
    assert sighting["source_system"] == proc.SOURCE_CF_KAGGLE
    assert sighting["tender_value_amount"] == 50000

    # No other channel has a sighting sharing this ocid -- a coverage gap, not a mismatch.
    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'kaggle_coverage_gap'").fetchone()
    assert review["raw_value"] == "ocds-2"
    assert conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'kaggle_cross_channel_mismatch'").fetchone() is None


def test_check_kaggle_against_other_channels_matches_by_ocid_not_notice_id(conn):
    """The regression this exists to catch: a live channel's notice_id is a
    real release id (e.g. an FTS notice number), never equal to the Kaggle
    row's ocid -- so the comparison has to join on the `ocid` column, or
    every single in-scope Kaggle row would misreport as a coverage gap even
    when the other channels have the exact same contracting process.
    """
    _record = proc._record_channel_sighting
    fts_result = _kaggle_result("https://www.find-tender.service.gov.uk/x")
    kag_result = _kaggle_result()

    _record(conn, "076079-2026", proc.SOURCE_FTS, {
        "ocid": "ocds-shared-3", "buyer_name": "West Northamptonshire Council", "title": "Recovery service",
        "cpv_codes": None, "tender_value_amount": 90000, "tender_value_currency": "GBP",
        "total_award_value_amount": None, "supplier_names": None, "date_published": None,
    }, fts_result)
    _record(conn, "ocds-shared-3", proc.SOURCE_CF_KAGGLE, {
        "ocid": "ocds-shared-3", "buyer_name": "West Northamptonshire Council", "title": "Recovery service",
        "cpv_codes": None, "tender_value_amount": 12345, "tender_value_currency": None,
        "total_award_value_amount": None, "supplier_names": None, "date_published": None,
    }, kag_result)

    proc._check_kaggle_against_other_channels(conn, "m01_procurement", "ocds-shared-3")

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'kaggle_cross_channel_mismatch'").fetchone()
    assert review is not None
    context = json.loads(review["context_json"])
    assert context["fields"]["tender_value_amount"] == {"kaggle": 12345, proc.SOURCE_FTS: 90000}
    # ocid-matched, despite the two channels' notice_id values being completely different.
    assert conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'kaggle_coverage_gap'").fetchone() is None


def test_check_kaggle_against_other_channels_agrees_raises_nothing(conn):
    _record = proc._record_channel_sighting
    shared_fields = {
        "ocid": "ocds-shared-4", "buyer_name": "West Northamptonshire Council", "title": "Recovery service",
        "cpv_codes": None, "tender_value_amount": 90000, "tender_value_currency": "GBP",
        "total_award_value_amount": None, "supplier_names": None, "date_published": None,
    }
    _record(conn, "some-other-notice-id", proc.SOURCE_CF, dict(shared_fields), _kaggle_result("https://cf.example"))
    _record(conn, "ocds-shared-4", proc.SOURCE_CF_KAGGLE, dict(shared_fields), _kaggle_result())

    proc._check_kaggle_against_other_channels(conn, "m01_procurement", "ocds-shared-4")

    assert conn.execute("SELECT * FROM review_queue").fetchone() is None


def test_check_kaggle_against_other_channels_ignores_case_and_whitespace_only_differences(conn):
    """Regression for the 2026-08-23 production sample: ~20% of raised
    mismatches were purely "DERBYSHIRE COUNTY COUNCIL" vs "Derbyshire County
    Council" -- formatting, not a finding, and comparing case/whitespace
    means one production entity is not flagged as disagreeing with itself.
    """
    _record = proc._record_channel_sighting
    _record(conn, "some-other-notice-id", proc.SOURCE_CF, {
        "ocid": "ocds-shared-5", "buyer_name": "  Derbyshire   County Council", "title": "Recovery Service",
        "cpv_codes": None, "tender_value_amount": 90000, "tender_value_currency": "GBP",
        "total_award_value_amount": None, "supplier_names": None, "date_published": None,
    }, _kaggle_result("https://cf.example"))
    _record(conn, "ocds-shared-5", proc.SOURCE_CF_KAGGLE, {
        "ocid": "ocds-shared-5", "buyer_name": "DERBYSHIRE COUNTY COUNCIL", "title": "RECOVERY SERVICE",
        "cpv_codes": None, "tender_value_amount": 90000, "tender_value_currency": "GBP",
        "total_award_value_amount": None, "supplier_names": None, "date_published": None,
    }, _kaggle_result())

    proc._check_kaggle_against_other_channels(conn, "m01_procurement", "ocds-shared-5")

    assert conn.execute("SELECT * FROM review_queue").fetchone() is None


def test_kaggle_csv_text_reads_plain_csv(conn):
    text = proc._kaggle_csv_text(b"a,b\r\n1,2\r\n", "m01_procurement", conn, "https://example.com")
    assert text == "a,b\r\n1,2\r\n"


def test_kaggle_csv_text_unzips_a_zip_response(conn):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("contracts_finder_2014-2025.csv", "a,b\r\n1,2\r\n")
    text = proc._kaggle_csv_text(buf.getvalue(), "m01_procurement", conn, "https://example.com")
    assert text == "a,b\r\n1,2\r\n"


def test_kaggle_csv_text_records_parse_failure_for_zip_with_no_csv(conn):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("readme.txt", "not a csv")
    text = proc._kaggle_csv_text(buf.getvalue(), "m01_procurement", conn, "https://example.com")
    assert text is None
    assert conn.execute("SELECT * FROM parse_failures WHERE field_name = 'kaggle_zip'").fetchone() is not None


def test_walk_and_process_kaggle_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.kaggle.com")
    _seed_authority(conn, "E06000061", "West Northamptonshire")
    csv_body = (
        "ocid,tender_title,buyer,tender_value\r\n"
        "ocds-5,Substance misuse recovery service,West Northamptonshire Council,90000\r\n"
        "ocds-6,Playground equipment,Some Council,1000\r\n"
    )
    httpx_mock.add_response(url=proc.KAGGLE_DOWNLOAD_URL, text=csv_body)

    with PipelineHTTPClient(proc.SOURCE_CF_KAGGLE, settings=settings, conn=conn) as client:
        client.set_basic_auth("user", "key")
        matched = proc._walk_and_process_kaggle(
            client, conn, "m01_procurement", "m01_procurement:kaggle", None, False)

    assert matched == 1  # only the in-scope row
    assert db.get_cursor(conn, "m01_procurement:kaggle") == "DONE"
    row = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE notice_id = 'ocds-5'").fetchone()
    assert row["source_system"] == proc.SOURCE_CF_KAGGLE


def test_walk_and_process_kaggle_skips_when_already_done(httpx_mock, settings, conn):
    db.set_cursor(conn, "m01_procurement:kaggle", "DONE")
    # No response registered: if this re-fetched, the missing mock would fail the test.
    with PipelineHTTPClient(proc.SOURCE_CF_KAGGLE, settings=settings, conn=conn) as client:
        matched = proc._walk_and_process_kaggle(
            client, conn, "m01_procurement", "m01_procurement:kaggle", None, False)
    assert matched == 0


def test_walk_and_process_kaggle_stops_at_limit_and_saves_row_offset(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://www.kaggle.com")
    csv_body = (
        "ocid,tender_title\r\n"
        "ocds-7,Substance misuse recovery service\r\n"
        "ocds-8,Substance misuse treatment service\r\n"
    )
    httpx_mock.add_response(url=proc.KAGGLE_DOWNLOAD_URL, text=csv_body)

    with PipelineHTTPClient(proc.SOURCE_CF_KAGGLE, settings=settings, conn=conn) as client:
        client.set_basic_auth("user", "key")
        matched = proc._walk_and_process_kaggle(
            client, conn, "m01_procurement", "m01_procurement:kaggle", 1, False)

    assert matched == 1
    assert db.get_cursor(conn, "m01_procurement:kaggle") == "ROW:1"


def test_require_kaggle_credentials_raises_when_unset(settings):
    settings.kaggle_username = None
    settings.kaggle_key = None
    with pytest.raises(RuntimeError, match="KAGGLE_USERNAME"):
        settings.require_kaggle_credentials()


def test_backfill_channel_sightings_derives_rows_from_existing_contracts(conn):
    """The 2026-08-23 incident this exists to fix: a notice --api/--csv
    already fetched, with no sighting row because it predates migration
    0058, must stop reading as a --kag coverage gap once backfilled.
    """
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())
    lookup = {}  # buyer matching irrelevant here

    class _FakeResult:
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?x=1"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    # Simulate the pre-existing state: a contracts row with no sighting row,
    # as if it had been written before procurement_channel_sightings existed.
    proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), lookup)
    conn.execute("DELETE FROM procurement_channel_sightings WHERE notice_id = ?", (release["id"],))
    assert conn.execute("SELECT * FROM procurement_channel_sightings").fetchone() is None

    inserted = proc.backfill_channel_sightings(conn)
    assert inserted == 1

    row = conn.execute(
        "SELECT * FROM procurement_channel_sightings WHERE notice_id = ? AND source_system = ?",
        (release["id"], proc.SOURCE_FTS)).fetchone()
    assert row is not None
    assert row["ocid"] == release["ocid"]
    assert row["buyer_name"] == "West Northamptonshire Council"
    # Deliberately not reconstructed -- see the function's docstring.
    assert row["tender_value_amount"] is None


def test_backfill_channel_sightings_is_idempotent(conn):
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())

    class _FakeResult:
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?x=1"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), {})
    conn.execute("DELETE FROM procurement_channel_sightings WHERE notice_id = ?", (release["id"],))

    first = proc.backfill_channel_sightings(conn)
    second = proc.backfill_channel_sightings(conn)
    assert first == 1
    assert second == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM procurement_channel_sightings").fetchone()["n"] == 1


def test_backfill_then_kaggle_check_reports_no_coverage_gap(conn):
    """End-to-end proof of the fix: a notice fetched before migration 0058,
    then backfilled, is no longer flagged when --kag sees the same ocid.
    """
    release = json.loads((FIXTURES / "fts_release_award_sample.json").read_text())

    class _FakeResult:
        url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?x=1"
        retrieved_at = __import__("datetime").datetime(2026, 8, 10, tzinfo=__import__("datetime").timezone.utc)
        status_code = 200
        payload_sha256 = "deadbeef"

    # The fixture is a genuinely out-of-scope passenger-transport award --
    # retitled in-place, the same as test_run_end_to_end, purely so the
    # scope filter passes and this test actually reaches the check it means
    # to exercise.
    release["tender"]["title"] = "Substance misuse treatment and recovery service recommissioning"
    proc._process_release(conn, "m01_procurement", proc.SOURCE_FTS, release, _FakeResult(), {})
    conn.execute("DELETE FROM procurement_channel_sightings WHERE notice_id = ?", (release["id"],))
    proc.backfill_channel_sightings(conn)

    row = {"ocid": release["ocid"], "tender_title": release["tender"]["title"], "buyer": "West Northamptonshire Council"}
    index = proc._kaggle_column_index(list(row.keys()))
    proc._process_kaggle_release_row(conn, "m01_procurement", row, index, _kaggle_result())

    assert conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'kaggle_coverage_gap'").fetchone() is None


def test_walk_and_process_csv_archive_skips_months_already_done(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock, "https://ckan.publishing.service.gov.uk")
    db.set_cursor(conn, "m01_procurement:cf_csv", "DONE:2016-06-01")

    package = _ckan_package("Contracts Finder Notices 06 2016", "contracts-finder-notices-06-2016", 1, "2018-01-10")
    ckan_response = {"success": True, "result": {"count": 1, "results": [package]}}
    httpx_mock.add_response(url=re.compile(r".*package_search.*"), json=ckan_response)
    # No CSV-file response registered: if the month were reprocessed, the
    # missing mock would fail the test with an unmatched request.

    with PipelineHTTPClient(proc.SOURCE_CF_CSV, settings=settings, conn=conn) as client:
        matched = proc._walk_and_process_csv_archive(
            client, conn, "m01_procurement", proc.SOURCE_CF_CSV,
            "m01_procurement:cf_csv", proc.WINDOW_START, {}, None, False,
        )

    assert matched == 0
