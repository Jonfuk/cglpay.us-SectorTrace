from __future__ import annotations

import json
import re
import time

import httpx
import pytest
from pytest_httpx import IteratorStream

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.modules import m04_companies as ch
from pipeline.registry import ModuleContext


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://api.company-information.service.gov.uk/robots.txt",
        status_code=200, text="", is_reusable=True)


def _allow_stream_robots(httpx_mock) -> None:
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/robots.txt", status_code=200, text="", is_reusable=True)


@pytest.fixture
def seed_companies():
    """The (provider_key, company_number) pairs m04.run() should walk.

    VERIFIED_IDENTIFIERS now seeds a company number for all nine tracked
    entities, and m04 fetches and fully walks every one. These tests each
    arrange a single company and mock only that one, so the default here
    is CGL alone; a test that is specifically about the name-search path
    clears it.
    """
    return [("change_grow_live", "03861209")]


@pytest.fixture(autouse=True)
def _only_walk_seed_companies(monkeypatch, seed_companies):
    monkeypatch.setattr(ch, "_seed_company_numbers", lambda conn: list(seed_companies))


# --- company number normalisation ---------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("3861209", "03861209"),      # Charity Commission publishes it unpadded
    (3861209, "03861209"),
    ("03861209", "03861209"),
    ("06228752", "06228752"),
    ("SC123456", "SC123456"),
    ("OC449691", "OC449691"),
    ("  3861209  ", "03861209"),
])
def test_normalise_company_number(raw, expected):
    assert ch.normalise_company_number(raw) == expected


def test_unpadded_number_would_not_match_padded_without_normalisation():
    """Regression guard: the register gives 7 digits, the API needs 8."""
    assert ch.normalise_company_number("3861209") != "3861209"


def test_identifiers_are_normalised_so_modules_do_not_create_duplicates(conn):
    """Module 3 reads the number off the charity register (unpadded) and
    Module 4 gets it from Companies House (padded). Without normalisation
    the same company would occupy two provider_identifiers rows and split
    its evidence in two.
    """
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "3861209", discovered_by="m03_charity_finance")
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="m04_companies")

    rows = conn.execute(
        "SELECT identifier FROM provider_identifiers "
        "WHERE provider_key='change_grow_live' AND scheme='company_number'").fetchall()
    assert [r["identifier"] for r in rows] == ["03861209"]


# --- name matching -------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("CHANGE, GROW, LIVE", "change_grow_live"),
    ("Change Grow Live Services Ltd", "change_grow_live"),
    ("CHANGE, GROW, LIVE SERVICES LIMITED", "change_grow_live"),
    ("Turning Point", "turning_point"),
])
def test_match_company_name_accepts_exact_variants(name, expected):
    assert ch.match_company_name(name) == expected


@pytest.mark.parametrize("name", [
    # every one of these is a real Companies House search hit for "Change Grow Live"
    "GROW CHANGE LTD",
    "GROWING CHANGE CIC",
    "DELIVER CHANGE GROW LTD",
    "CHANGE, GROW, THRIVE LLP",
    "GROWTH AND CHANGE LIMITED",
    "CHANGE LIVE GROW LTD",
])
def test_match_company_name_rejects_fuzzy_search_noise(name):
    assert ch.match_company_name(name) is None


def test_match_company_name_rejects_generic_acronyms():
    assert ch.match_company_name("CGL") is None
    assert ch.match_company_name("Via") is None
    assert ch.match_company_name(None) is None


# --- officer refs ---------------------------------------------------------------

def test_officer_ref_prefers_person_number():
    assert ch._officer_ref({"person_number": "12345", "name": "X"}) == "12345"


def test_officer_ref_is_stable_without_person_number():
    officer = {"name": "A Person", "officer_role": "director", "appointed_on": "2020-01-01"}
    assert ch._officer_ref(officer) == ch._officer_ref(dict(officer))
    other = dict(officer, appointed_on="2021-01-01")
    assert ch._officer_ref(officer) != ch._officer_ref(other)


def test_format_address_skips_missing_parts():
    assert ch._format_address({"address_line_1": "A", "postal_code": "B"}) == "A, B"
    assert ch._format_address(None) is None


# --- end-to-end -----------------------------------------------------------------

def _company_payload(number="03861209", name="CHANGE, GROW, LIVE"):
    return {
        "company_name": name, "company_number": number, "company_status": "active",
        "type": "private-limited-guarant-nsc-limited-exemption",
        "date_of_creation": "1999-10-19", "sic_codes": ["88990", "96090"],
        "jurisdiction": "england-wales",
        "registered_office_address": {"address_line_1": "North Suite", "locality": "Brighton",
                                       "postal_code": "BN1 1GE"},
        "previous_company_names": [
            {"name": "CRIME REDUCTION INITIATIVES", "effective_from": "1999-12-03",
             "ceased_on": "2016-04-01"},
        ],
    }


def _register_company_mocks(httpx_mock, number="03861209"):
    base = "https://api.company-information.service.gov.uk"
    httpx_mock.add_response(url=f"{base}/company/{number}", json=_company_payload(number))
    httpx_mock.add_response(
        url=re.compile(rf"{base}/company/{number}/officers.*"),
        json={"items": [
            {"person_number": "p1", "name": "A Person", "officer_role": "director",
             "appointed_on": "2020-01-01", "address": {"locality": "Brighton"}},
            {"person_number": "p2", "name": "B Person", "officer_role": "secretary",
             "appointed_on": "2018-01-01", "resigned_on": "2022-01-01", "address": {}},
        ]})
    httpx_mock.add_response(
        url=re.compile(rf"{base}/company/{number}/filing-history.*"),
        json={"total_count": 1, "items": [
            {"transaction_id": "t1", "date": "2025-06-01", "category": "accounts",
             "description": "accounts-with-accounts-type-group"},
        ]})
    # The disqualification sweep runs for every serving director, but only
    # from run()'s own end-of-sweep call -- a test that exercises
    # _refresh_company directly (JON-36's streaming consumers) never reaches
    # it, hence is_optional=True. An empty register answer is the normal case
    # and is what the run()-based tests want.
    httpx_mock.add_response(
        url=re.compile(rf"{base}/search/disqualified-officers.*"),
        json={"total_results": 0, "items": []}, is_reusable=True, is_optional=True)
    # The PSC pass (Phase 15 / G3) fetches the register for every company.
    # An empty register is the normal fixture state; the PSC-specific tests
    # register a richer payload BEFORE this helper so their rule wins the
    # first-call pick, which is why this one is optional.
    httpx_mock.add_response(
        url=re.compile(rf"{base}/company/{number}/persons-with-significant-control.*"),
        json={"register_view": "active", "items": [], "total_count": 0},
        is_reusable=True, is_optional=True)


def test_run_from_seed_identifier(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    # no search results, so only the seeded number is processed
    httpx_mock.add_response(
        url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    company = conn.execute("SELECT * FROM companies WHERE company_number='03861209'").fetchone()
    assert company["company_name"] == "CHANGE, GROW, LIVE"
    assert company["provider_key"] == "change_grow_live"
    assert company["match_basis"] == "seed"
    assert company["sic_codes"] == "88990,96090"


def test_previous_names_are_captured_as_authoritative_aliases(httpx_mock, settings, conn):
    """CGL was 'CRIME REDUCTION INITIATIVES' until 2016, so a pre-2016 record
    naming CRI is a CGL record. This comes from Companies House, not a guess.
    """
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    row = conn.execute("SELECT * FROM company_previous_names").fetchone()
    assert row["previous_name"] == "CRIME REDUCTION INITIATIVES"
    assert row["ceased_on"] == "2016-04-01"
    assert row["source_url"] is not None


def test_officers_go_only_to_the_restricted_table(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    officers = conn.execute("SELECT * FROM restricted_company_officers").fetchall()
    assert len(officers) == 2

    # the public companies row must not contain any officer name
    company_blob = " ".join(
        str(v) for v in conn.execute("SELECT * FROM companies").fetchone().values() if v is not None)
    assert "A Person" not in company_blob
    assert "B Person" not in company_blob


def test_officer_changes_view_is_name_free(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    row = conn.execute("SELECT * FROM v_company_officer_changes").fetchone()
    assert row["officers_total"] == 2
    assert row["officers_active"] == 1
    assert row["officers_resigned"] == 1
    columns = [d[0] for d in conn.execute("SELECT * FROM v_company_officer_changes").description]
    assert not any("name" in c for c in columns)


def test_fuzzy_search_hits_go_to_review_not_companies(httpx_mock, settings, conn, seed_companies):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    seed_companies.clear()  # this test is only about the search path
    httpx_mock.add_response(
        url=re.compile(r".*/search/companies.*"),
        json={"items": [
            {"company_number": "12345678", "title": "GROW CHANGE LTD"},
            {"company_number": "87654321", "title": "GROWING CHANGE CIC"},
        ]}, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM companies").fetchone()["c"] == 0
    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='possible_group_company'").fetchall()
    assert len(review) >= 1


def test_exact_name_hit_is_captured_but_not_linked(httpx_mock, settings, conn, seed_companies):
    """A shared name is not a shared identity. Live Companies House data has
    a dissolved "FORWARD TRUST LIMITED" (formerly Bradford & Bingley Personal
    Finance) and a 2025-incorporated "HUMANKIND LTD" — neither is the charity
    of that name. So a name-only hit records the company but leaves
    provider_key NULL until a human confirms it.
    """
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    seed_companies.clear()  # only the exact-name-hit path is under test
    httpx_mock.add_response(
        url=re.compile(r".*/search/companies.*"),
        json={"items": [{"company_number": "06228752",
                          "title": "CHANGE, GROW, LIVE SERVICES LIMITED"}]}, is_reusable=True)
    _register_company_mocks(httpx_mock, number="06228752")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    row = conn.execute("SELECT * FROM companies WHERE company_number='06228752'").fetchone()
    assert row is not None
    assert row["match_basis"] == "name_only_unconfirmed"
    assert row["provider_key"] is None

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='unconfirmed_name_match'"
    ).fetchone()["c"] == 1


def test_name_only_match_never_writes_a_provider_identifier(httpx_mock, settings, conn, seed_companies):
    """Otherwise an unrelated same-named company would silently become a
    permanent part of the provider's group.
    """
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    seed_companies.clear()  # only the name-only-hit path is under test
    httpx_mock.add_response(
        url=re.compile(r".*/search/companies.*"),
        json={"items": [{"company_number": "01865768", "title": "FORWARD TRUST LIMITED"}]},
        is_reusable=True)
    _register_company_mocks(httpx_mock, number="01865768")

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    linked = conn.execute(
        "SELECT COUNT(*) c FROM provider_identifiers "
        "WHERE scheme='company_number' AND identifier='01865768'").fetchone()["c"]
    assert linked == 0


def test_seeded_company_is_linked_to_its_provider(httpx_mock, settings, conn):
    """Contrast with the above: a number that arrived from an authoritative
    cross-reference (charity register / CQC) IS trusted to set provider_key.
    """
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="m03_charity_finance")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    row = conn.execute("SELECT * FROM companies WHERE company_number='03861209'").fetchone()
    assert row["match_basis"] == "seed"
    assert row["provider_key"] == "change_grow_live"

# --- People with Significant Control (Phase 15 / G3) ---------------------------

PSC_INDIVIDUAL = {
    "kind": "individual-person-with-significant-control",
    "name": "SOMEONE, Example",
    "date_of_birth": {"month": 6, "year": 1980},
    "nationality": "British",
    "country_of_residence": "United Kingdom",
    "natures_of_control": ["ownership-of-shares-more-than-25-percent",
                           "right-to-appoint-and-remove-directors"],
    "notifiable": True,
    "is_sanctioned": False,
    "links": {"self": "/company/03861209/persons-with-significant-control/individual/abc123"},
}
PSC_CORPORATE = {
    "kind": "corporate-entity-person-with-significant-control",
    "name": "CGL HOLDINGS LIMITED",
    "identification": {"company_number": "06228752", "legal_form": "Ltd",
                        "country_registered": "United Kingdom"},
    "natures_of_control": ["ownership-of-shares-more-than-25-percent"],
    "notifiable": True,
    "links": {"self": "/company/03861209/persons-with-significant-control/corporate-entity/def456"},
}


def _register_psc_mocks(httpx_mock, number="03861209", items=(PSC_INDIVIDUAL, PSC_CORPORATE),
                         register_view="active", statement=None):
    payload = {"register_view": register_view, "items": list(items),
               "total_count": len(items)}
    if statement is not None:
        payload["statement"] = statement
    httpx_mock.add_response(
        url=re.compile(rf"https://api\.company-information\.service\.gov\.uk/company/{number}/persons-with-significant-control.*"),
        json=payload, is_reusable=True)


def test_psc_edges_are_stored_with_names_only_in_the_restricted_table(
        httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    # PSC rules first: the first-call pick goes to the most specific rule
    _register_psc_mocks(httpx_mock)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    edges = conn.execute("SELECT * FROM company_psc ORDER BY psc_ref").fetchall()
    assert len(edges) == 2
    individual = [e for e in edges if e["kind"].startswith("individual")][0]
    assert individual["psc_ref"] == "abc123"
    assert individual["natures_of_control"] == "ownership-of-shares-more-than-25-percent," \
        "right-to-appoint-and-remove-directors"
    assert individual["notifiable"] == 1
    # the public row carries no name, no date of birth, no nationality
    public_blob = " ".join(str(v) for v in individual.values() if v is not None)
    assert "SOMEONE" not in public_blob and "1980" not in public_blob

    restricted = conn.execute(
        "SELECT * FROM restricted_company_psc WHERE psc_ref='abc123'").fetchone()
    assert restricted["name"] == "SOMEONE, Example"
    assert restricted["date_of_birth_month"] == 6
    assert restricted["date_of_birth_year"] == 1980
    assert restricted["nationality"] == "British"


def test_a_corporate_psc_carries_its_own_asserted_company_number(
        httpx_mock, settings, conn):
    """The register asserts the owning company's number; that identifier is
    authoritative and travels on the public edge for the entity graph. The
    corporate entity's name is not a person's name and is not restricted."""
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    _register_psc_mocks(httpx_mock)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    corporate = conn.execute(
        "SELECT * FROM company_psc WHERE psc_ref='def456'").fetchone()
    assert corporate["identification_company_number"] == "06228752"
    assert corporate["identification_legal_form"] == "Ltd"
    # corporate entities are not people: no restricted row for them
    assert conn.execute(
        "SELECT COUNT(*) c FROM restricted_company_psc WHERE psc_ref='def456'"
    ).fetchone()["c"] == 0


def test_a_redacted_register_is_a_review_item_not_an_absence(
        httpx_mock, settings, conn):
    """A company whose register is exempt or protected answers with a
    statement rather than a list. Recording nothing would make a redaction
    look like a finding."""
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    _register_psc_mocks(httpx_mock, items=[], register_view="exemptions",
                        statement={"text": "The register is exempt from " 
                                            "disclosure under regulation 15."})
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM company_psc").fetchone()["c"] == 0
    review = conn.execute("SELECT * FROM review_queue WHERE item_type='psc_register_statement'").fetchall()
    assert len(review) == 1
    assert review[0]["raw_value"] == "03861209"


def test_an_unavailable_psc_register_is_recorded(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r".*/persons-with-significant-control.*"), status_code=404)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    review = conn.execute("SELECT * FROM review_queue WHERE item_type='company_psc_unavailable'").fetchall()
    assert len(review) == 1
    assert conn.execute("SELECT COUNT(*) c FROM company_psc").fetchone()["c"] == 0


def test_psc_pagination_reads_the_whole_register(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    first = {"register_view": "active",
             "items": [dict(PSC_INDIVIDUAL, links={"self": "/company/03861209/persons-with-significant-control/individual/aaa"})],
             "total_count": 2}
    second = {"register_view": "active",
              "items": [dict(PSC_INDIVIDUAL, links={"self": "/company/03861209/persons-with-significant-control/individual/bbb"})],
              "total_count": 2}
    httpx_mock.add_response(
        url=re.compile(r".*persons-with-significant-control.*start_index=0"), json=first)
    httpx_mock.add_response(
        url=re.compile(r".*persons-with-significant-control.*start_index=1"), json=second)
    _register_company_mocks(httpx_mock)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM company_psc").fetchone()["c"] == 2


# --- charges (JON-36) -----------------------------------------------------------

def _seed_tracked_company(conn, company_number="03861209", provider_key="change_grow_live",
                           name="CHANGE, GROW, LIVE", match_basis="seed") -> None:
    """A company already in `companies`, as if a prior sweep had already run
    -- the state company_charges/company_insolvency_cases' foreign key
    requires, and every stream consumer test starts from."""
    providers.seed_providers(conn)
    db.upsert(conn, "companies", {
        "company_number": company_number,
        "provider_key": provider_key,
        "company_name": name,
        "company_status": "active",
        "company_type": None,
        "date_of_creation": None,
        "date_of_cessation": None,
        "sic_codes": None,
        "registered_address": None,
        "jurisdiction": None,
        "match_basis": match_basis,
        "source_url": "https://api.company-information.service.gov.uk/company/" + company_number,
        "retrieved_at": "2026-01-01T00:00:00+00:00",
        "http_status": 200,
        "source_system": ch.SOURCE_SYSTEM,
        "payload_sha256": "seed-fixture",
    }, natural_key=["company_number"])
    conn.commit()


def _charges_payload(number="03861209"):
    return {
        "total_count": 1,
        "items": [{
            "links": {"self": f"/company/{number}/charges/charge1"},
            "classification": {"type": "charge-description", "description": "A registered charge"},
            "status": "outstanding",
            "created_on": "2020-01-01",
            "delivered_on": "2020-01-05",
            "persons_entitled": [{"name": "Big Bank Plc"}],
        }],
    }


def test_fetch_charges_preserves_status_vocabulary_verbatim(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_tracked_company(conn)
    httpx_mock.add_response(
        url=re.compile(r".*/company/03861209/charges.*"), json=_charges_payload())

    client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    written = ch._fetch_charges(client, conn, "m04_companies", "03861209",
                                 profile={"links": {"charges": "/company/03861209/charges"}})
    client.close()

    assert written == 1
    row = conn.execute("SELECT * FROM company_charges").fetchone()
    # Never collapsed to a boolean "is_satisfied" -- Companies House's own word.
    assert row["status"] == "outstanding"
    assert row["persons_entitled"] == "Big Bank Plc"
    dates = {d["date_type"]: d["date_value"]
             for d in conn.execute("SELECT * FROM company_charge_dates").fetchall()}
    assert dates == {"created_on": "2020-01-01", "delivered_on": "2020-01-05"}


def test_fetch_charges_gated_on_profile_links_unless_forced(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_tracked_company(conn)
    client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)

    # No links.charges -> no request at all (nothing mocked, none consumed).
    written = ch._fetch_charges(client, conn, "m04_companies", "03861209", profile={})
    assert written == 0
    assert conn.execute("SELECT COUNT(*) c FROM company_charges").fetchone()["c"] == 0

    httpx_mock.add_response(
        url=re.compile(r".*/company/03861209/charges.*"), json=_charges_payload())
    written = ch._fetch_charges(client, conn, "m04_companies", "03861209", profile=None, force=True)
    client.close()
    assert written == 1


def test_fetch_insolvency_force_bypasses_the_profile_gate(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_tracked_company(conn)
    httpx_mock.add_response(
        url=re.compile(r".*/company/03861209/insolvency.*"),
        json={"cases": [{"number": "1", "type": "administration", "dates": [], "practitioners": []}]})

    client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    written = ch._fetch_insolvency(client, conn, "m04_companies", "03861209", profile=None, force=True)
    client.close()

    assert written == 1
    assert conn.execute("SELECT case_type FROM company_insolvency_cases").fetchone()["case_type"] == "administration"


# --- streaming discovery (JON-36) ------------------------------------------------

def test_company_stream_event_for_tracked_company_triggers_refresh(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _allow_stream_robots(httpx_mock)
    _seed_tracked_company(conn)

    event = {"resource_uri": "/company/03861209", "resource_kind": "company-profile",
              "event": {"type": "changed", "timepoint": 5}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/companies",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))
    _register_company_mocks(httpx_mock)  # the authoritative REST refresh this triggers

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_company_stream(
        rest_client, stream_client, conn, "m04_companies", {"03861209"}, settings)
    rest_client.close()
    stream_client.close()

    assert stats["matched"] == 1
    # The authoritative REST fetch actually ran -- the event's own payload
    # (which carried no company_name at all) was never trusted.
    row = conn.execute("SELECT * FROM companies WHERE company_number='03861209'").fetchone()
    assert row["company_name"] == "CHANGE, GROW, LIVE"
    stream_event = conn.execute("SELECT * FROM company_stream_events").fetchone()
    assert stream_event["stream"] == "companies"
    assert stream_event["timepoint"] == 5
    assert db.get_cursor(conn, "m04_companies:stream:companies") == "TIMEPOINT:5"


def test_company_stream_event_for_untracked_company_is_ignored_and_not_archived(
        httpx_mock, settings, conn):
    _allow_stream_robots(httpx_mock)
    event = {"resource_uri": "/company/99999999", "resource_kind": "company-profile",
              "event": {"type": "changed", "timepoint": 5}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/companies",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_company_stream(
        rest_client, stream_client, conn, "m04_companies", set(), settings)
    rest_client.close()
    stream_client.close()

    assert stats["scanned"] == 1
    assert stats["matched"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM company_stream_events").fetchone()["c"] == 0
    # The cursor still advances on an unmatched event -- consumption must not
    # replay the whole firehose every run just because nothing matched.
    assert db.get_cursor(conn, "m04_companies:stream:companies") == "TIMEPOINT:5"


def test_filing_stream_updates_company_filings_and_seeds_an_accounts_candidate_only(
        httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _allow_stream_robots(httpx_mock)
    _seed_tracked_company(conn)

    event = {"resource_uri": "/company/03861209/filing-history/t1",
              "resource_kind": "filing-history", "event": {"type": "changed", "timepoint": 7}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/filings",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))
    base = "https://api.company-information.service.gov.uk"
    httpx_mock.add_response(
        url=re.compile(rf"{base}/company/03861209/filing-history.*"),
        json={"total_count": 2, "items": [
            {"transaction_id": "t1", "date": "2025-06-01", "category": "accounts",
             "subcategory": "accounts-with-accounts-type-group", "description": "Accounts",
             "links": {"document_metadata":
                       "https://document-api.company-information.service.gov.uk/document/abc"}},
            {"transaction_id": "t2", "date": "2025-06-02", "category": "confirmation-statement",
             "description": "Confirmation statement",
             "links": {"document_metadata":
                       "https://document-api.company-information.service.gov.uk/document/def"}},
        ]})

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_filing_stream(
        rest_client, stream_client, conn, "m04_companies", {"03861209"}, settings)
    rest_client.close()
    stream_client.close()

    assert stats["matched"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM company_filings").fetchone()["c"] == 2

    candidates = conn.execute("SELECT * FROM companies_house_accounts_candidates").fetchall()
    assert len(candidates) == 1
    assert candidates[0]["accounts_type"] == "accounts-with-accounts-type-group"
    assert candidates[0]["candidate_url"] == \
        "https://document-api.company-information.service.gov.uk/document/abc"
    # A candidate is a pointer nobody has opened -- never evidence directly.
    assert conn.execute(
        "SELECT COUNT(*) c FROM companies_house_accounts_documents").fetchone()["c"] == 0


def test_filing_stream_reseeding_never_resets_a_human_decision(httpx_mock, settings, conn):
    """A filing re-seen on a later event must not silently reopen a
    candidate a person already promoted or rejected."""
    _allow_all_robots(httpx_mock)
    _allow_stream_robots(httpx_mock)
    _seed_tracked_company(conn)

    event = {"resource_uri": "/company/03861209/filing-history/t1",
              "resource_kind": "filing-history", "event": {"type": "changed", "timepoint": 9}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/filings",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))
    base = "https://api.company-information.service.gov.uk"
    httpx_mock.add_response(
        url=re.compile(rf"{base}/company/03861209/filing-history.*"),
        json={"total_count": 1, "items": [
            {"transaction_id": "t1", "date": "2025-06-01", "category": "accounts",
             "subcategory": "accounts-with-accounts-type-group", "description": "Accounts",
             "links": {"document_metadata":
                       "https://document-api.company-information.service.gov.uk/document/abc"}},
        ]})

    # As if an earlier run had already discovered and seeded this filing --
    # matching what the mocked REST re-fetch above will also produce, so the
    # stream-triggered reseed below hits the natural-key conflict rather than
    # inserting a fresh row.
    db.upsert(conn, "company_filings", {
        "company_number": "03861209", "transaction_id": "t1", "filing_date": "2025-06-01",
        "category": "accounts", "subcategory": "accounts-with-accounts-type-group",
        "description": "Accounts",
        "document_url": "https://document-api.company-information.service.gov.uk/document/abc",
        "source_url": "https://x", "retrieved_at": "2026-01-01T00:00:00+00:00",
        "http_status": 200, "source_system": ch.SOURCE_SYSTEM, "payload_sha256": "x",
    }, natural_key=["company_number", "transaction_id"])
    ch._seed_accounts_candidates(conn, "03861209")
    conn.execute(
        "UPDATE companies_house_accounts_candidates SET verified = 1, "
        "verified_at = '2026-01-01T00:00:00+00:00' WHERE company_number = '03861209'")
    conn.commit()

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    ch._consume_filing_stream(rest_client, stream_client, conn, "m04_companies", {"03861209"}, settings)
    rest_client.close()
    stream_client.close()

    row = conn.execute("SELECT * FROM companies_house_accounts_candidates").fetchone()
    assert row["verified"] == 1


def test_insolvency_stream_event_bypasses_the_rest_gate_via_force(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _allow_stream_robots(httpx_mock)
    _seed_tracked_company(conn)

    event = {"resource_uri": "/company/03861209/insolvency", "resource_kind": "insolvency",
              "event": {"type": "changed", "timepoint": 11}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/insolvency-cases",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))
    httpx_mock.add_response(
        url=re.compile(r".*/company/03861209/insolvency.*"),
        json={"cases": [{"number": "1", "type": "administration", "dates": [], "practitioners": []}]})

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_insolvency_stream(
        rest_client, stream_client, conn, "m04_companies", {"03861209"}, settings)
    rest_client.close()
    stream_client.close()

    assert stats["matched"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM company_insolvency_cases").fetchone()["c"] == 1


def test_charges_stream_event_bypasses_the_rest_gate_via_force(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _allow_stream_robots(httpx_mock)
    _seed_tracked_company(conn)

    event = {"resource_uri": "/company/03861209/charges", "resource_kind": "charges",
              "event": {"type": "changed", "timepoint": 13}}
    httpx_mock.add_response(
        url=f"{ch.STREAM_BASE}/charges",
        stream=IteratorStream([json.dumps(event).encode() + b"\n"]))
    httpx_mock.add_response(
        url=re.compile(r".*/company/03861209/charges.*"), json=_charges_payload())

    rest_client = PipelineHTTPClient(ch.SOURCE_SYSTEM, settings=settings, conn=conn)
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_charges_stream(
        rest_client, stream_client, conn, "m04_companies", {"03861209"}, settings)
    rest_client.close()
    stream_client.close()

    assert stats["matched"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM company_charges").fetchone()["c"] == 1


def test_stream_cursor_stale_resets_cursor_and_queues_a_review_item(httpx_mock, settings, conn):
    _allow_stream_robots(httpx_mock)
    # A regex, not a plain string: the checkpointed cursor below means the
    # actual request carries a ?timepoint=100 query string.
    httpx_mock.add_response(url=re.compile(rf"{re.escape(ch.STREAM_BASE)}/filings.*"), status_code=416)
    db.set_cursor(conn, "m04_companies:stream:filings", "TIMEPOINT:100")
    conn.commit()

    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    stats = ch._consume_stream(
        stream_client, conn, "m04_companies", "filings", set(), settings, lambda n, e: None)
    stream_client.close()

    assert stats["matched"] == 0
    assert db.get_cursor(conn, "m04_companies:stream:filings") == ""
    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='companies_house_stream_cursor_stale'").fetchall()
    assert len(review) == 1
    assert review[0]["raw_value"] == "filings"


def test_rate_limited_stream_returns_promptly_without_busy_waiting(httpx_mock, settings, conn):
    """Companies House documents a mandatory 60-second wait before
    reconnecting after a 429 -- this pipeline must not sit inside that wait
    on a foreground run."""
    _allow_stream_robots(httpx_mock)
    httpx_mock.add_response(url=f"{ch.STREAM_BASE}/filings", status_code=429,
                             headers={"Retry-After": "60"})

    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=settings, conn=conn)
    started = time.monotonic()
    stats = ch._consume_stream(
        stream_client, conn, "m04_companies", "filings", set(), settings, lambda n, e: None)
    elapsed = time.monotonic() - started
    stream_client.close()

    assert stats["matched"] == 0
    assert elapsed < 5  # nowhere near the documented 60-second wait
    assert db.get_cursor(conn, "m04_companies:stream:filings") is None


def test_transient_error_reconnects_up_to_the_configured_limit_then_gives_up(
        httpx_mock, settings, conn):
    _allow_stream_robots(httpx_mock)
    # Reusable rather than a fixed count: what this test verifies is that
    # _consume_stream gives up after exactly companies_house_stream_max_reconnects
    # attempts, not the precise number of underlying HTTP connect attempts
    # stream_events' own connect_retry_attempts happens to make along the way.
    httpx_mock.add_exception(
        httpx.ConnectError("boom"), url=f"{ch.STREAM_BASE}/filings", is_reusable=True)

    stream_settings = settings.model_copy(update={
        "companies_house_stream_connect_retry_attempts": 1,
        "companies_house_stream_connect_retry_wait_seconds": 0.01,
        "companies_house_stream_max_reconnects": 2,
    })
    stream_client = PipelineHTTPClient(ch.STREAM_SOURCE_SYSTEM, settings=stream_settings, conn=conn)
    stats = ch._consume_stream(
        stream_client, conn, "m04_companies", "filings", set(), stream_settings, lambda n, e: None)
    stream_client.close()

    assert stats["reconnects"] == 2


def test_streaming_disabled_by_default_and_run_is_unaffected(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "company_number", "03861209", discovered_by="test")
    httpx_mock.add_response(url=re.compile(r".*/search/companies.*"), json={"items": []}, is_reusable=True)
    _register_company_mocks(httpx_mock)

    assert settings.companies_house_streaming_enabled is False
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ch.run(ctx)  # would fail if it tried to reach STREAM_BASE -- nothing is mocked there

    assert conn.execute("SELECT COUNT(*) c FROM company_stream_events").fetchone()["c"] == 0


def test_stream_only_skips_the_rest_sweep_entirely(httpx_mock, settings, conn):
    stream_settings = settings.model_copy(update={
        "companies_house_streaming_enabled": True,
        "companies_house_streaming_api_key": "test-stream-key",
    })
    _allow_stream_robots(httpx_mock)
    for stream in ("companies", "filings", "insolvency-cases", "charges"):
        httpx_mock.add_response(url=f"{ch.STREAM_BASE}/{stream}", stream=IteratorStream([b""]))

    ctx = ModuleContext(conn=conn, settings=stream_settings, since=None, dry_run=False,
                         limit=None, source="stream")
    ch.run(ctx)

    # The REST sweep's own identity-discovery step would have hit the REST
    # host; --stream-only never runs it at all.
    rest_requests = [r for r in httpx_mock.get_requests() if str(r.url).startswith(ch.API_BASE)]
    assert rest_requests == []
