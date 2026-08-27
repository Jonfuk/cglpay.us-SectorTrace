from __future__ import annotations

import re

import pytest

from pipeline import providers
from pipeline.modules import m04_companies as ch
from pipeline.registry import ModuleContext


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(
        url="https://api.company-information.service.gov.uk/robots.txt",
        status_code=200, text="", is_reusable=True)


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
    # The disqualification sweep runs for every serving director. An empty
    # register answer is the normal case and is what these tests want.
    httpx_mock.add_response(
        url=re.compile(rf"{base}/search/disqualified-officers.*"),
        json={"total_results": 0, "items": []}, is_reusable=True)
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
        str(v) for v in tuple(conn.execute("SELECT * FROM companies").fetchone()) if v is not None)
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
    public_blob = " ".join(str(v) for v in tuple(individual) if v is not None)
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
