"""Module 4's viability extension: insolvency, and the disqualified register.

Two questions answered from the key and client m04 already has.

The insolvency fixture is a **live** response, captured 2026-08-11, from
LIFELINE PROJECT (01842240) — a substance misuse provider large enough to
appear as a co-respondent alongside CGL in employment tribunal judgments. It
went into administration on 2017-06-02, was wound up on 2018-06-07 and
dissolved on 2024-01-25. Testing against it rather than against a payload
someone imagined matters here for the usual reason and one more: the case list
holds two cases with different date vocabularies, which is exactly the shape a
hand-written fixture would have flattened away.

The disqualification fixtures are the only synthetic ones in the suite. The
real response identifies a person by full name, date of birth and home
address, and there is no reason to put that in this repository's git history
to test a parser that does not care what the name is. Every key and value
format in them was verified against the live API on the same date; see the
`_fixture_note` in each.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import providers
from pipeline.modules import m04_companies as ch
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LIFELINE = json.loads((FIXTURES / "ch_insolvency_lifeline_project.json").read_text(encoding="utf-8"))
DISQ_SEARCH = json.loads((FIXTURES / "ch_disqualified_search.json").read_text(encoding="utf-8"))
DISQ_DETAIL = json.loads(
    (FIXTURES / "ch_disqualified_officer_natural.json").read_text(encoding="utf-8"))

BASE = "https://api.company-information.service.gov.uk"


# --- reading a real insolvency history ------------------------------------------

def test_the_lifeline_fixture_is_the_event_this_is_built_for():
    """A guard on the fixture, not on the code. If this ever stops holding,
    the tests below are asserting against something else.
    """
    types = [case["type"] for case in LIFELINE["cases"]]
    assert types == ["in-administration", "creditors-voluntary-liquidation"]


def _run(conn, settings, limit=None):
    ch.run(ModuleContext(conn=conn, settings=settings, since=None,
                          dry_run=False, limit=limit))


_SEEDED_FOR_TEST: list[tuple[str, str]] = []


@pytest.fixture(autouse=True)
def _walk_only_test_seeded_companies(monkeypatch):
    """VERIFIED_IDENTIFIERS now seeds a company number for every tracked
    provider, and m04 fetches and fully walks every one. Each test here
    arranges a single company through `_seed(...)`; restrict the walk to
    the numbers `_seed` recorded so the run does not reach for the other
    eight. `_seed` often re-asserts CGL's own 03861209, which is already
    a config-seeded verified row, so filtering the table by status or
    discovered_by would miss it — track the intent explicitly instead.
    """
    _SEEDED_FOR_TEST.clear()
    monkeypatch.setattr(ch, "_seed_company_numbers",
                         lambda conn: list(_SEEDED_FOR_TEST))


def _allow_all_robots(httpx_mock):
    httpx_mock.add_response(url=f"{BASE}/robots.txt", status_code=200, text="",
                            is_reusable=True)


def _profile(number, *, insolvency=False, status="active", name="LIFELINE PROJECT"):
    links = {"self": f"/company/{number}"}
    if insolvency:
        links["insolvency"] = f"/company/{number}/insolvency"
    return {
        "company_name": name, "company_number": number, "company_status": status,
        "type": "private-limited-guarant-nsc", "date_of_creation": "1984-08-20",
        "date_of_cessation": "2024-01-25" if status == "dissolved" else None,
        "jurisdiction": "england-wales",
        "has_insolvency_history": insolvency,
        "links": links,
    }


def _mock_company(httpx_mock, number, *, insolvency=False, status="active",
                   officers=None, insolvency_body=None):
    httpx_mock.add_response(url=f"{BASE}/company/{number}",
                             json=_profile(number, insolvency=insolvency, status=status))
    httpx_mock.add_response(
        url=re.compile(rf"{BASE}/company/{number}/officers.*"),
        json={"items": officers if officers is not None else []})
    httpx_mock.add_response(
        url=re.compile(rf"{BASE}/company/{number}/filing-history.*"),
        json={"total_count": 0, "items": []})
    httpx_mock.add_response(url=re.compile(rf".*{BASE}/search/companies.*"),
                             json={"items": []}, is_reusable=True)
    # The PSC pass (Phase 15 / G3) fetches the register for every company; an
    # empty register is the normal fixture state here.
    httpx_mock.add_response(
        url=re.compile(rf"{BASE}/company/{number}/persons-with-significant-control.*"),
        json={"register_view": "active", "items": [], "total_count": 0}, is_reusable=True)
    if insolvency_body is not None:
        httpx_mock.add_response(url=f"{BASE}/company/{number}/insolvency",
                                 json=insolvency_body)


def _seed(conn, number="01842240", provider_key="change_grow_live"):
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, provider_key, "company_number", number, discovered_by="test")
    _SEEDED_FOR_TEST.append(
        (provider_key, providers.normalise_identifier("company_number", number)))


def test_an_insolvency_history_is_recorded_case_by_case(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)

    _run(conn, settings)

    cases = conn.execute(
        "SELECT * FROM company_insolvency_cases ORDER BY case_number").fetchall()
    assert [c["case_type"] for c in cases] == \
        ["in-administration", "creditors-voluntary-liquidation"]
    assert all(c["company_number"] == "01842240" for c in cases)


def test_the_sources_own_date_vocabulary_is_kept(httpx_mock, settings, conn):
    """An administration ending and a company being wound up are different
    facts. Flattening both into a "date_ended" column would assert they are
    the same one.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)

    _run(conn, settings)

    dates = {(r["case_number"], r["date_type"]): r["date_value"] for r in conn.execute(
        "SELECT * FROM company_insolvency_case_dates")}
    assert dates[("1", "administration-started-on")] == "2017-06-02"
    assert dates[("1", "administration-ended-on")] == "2018-06-07"
    assert dates[("2", "wound-up-on")] == "2018-06-07"
    assert dates[("2", "dissolved-on")] == "2024-01-25"


def test_practitioners_go_only_to_the_restricted_table(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)

    _run(conn, settings)

    names = [r["practitioner_name"] for r in conn.execute(
        "SELECT practitioner_name FROM restricted_company_insolvency_practitioners")]
    assert names, "the fixture names practitioners on both cases"

    columns = {r["name"] for r in conn.execute("PRAGMA table_info(company_insolvency_cases)")}
    assert not {"practitioner_name", "practitioners"} & columns


def test_a_practitioners_firm_address_is_not_stored_at_all(httpx_mock, settings, conn):
    """It answers nothing this pipeline asks, so it is personal data with no
    argument behind keeping it.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)

    _run(conn, settings)

    columns = {r["name"] for r in conn.execute(
        "PRAGMA table_info(restricted_company_insolvency_practitioners)")}
    assert not any("address" in column for column in columns)


def test_no_insolvency_request_is_made_when_the_profile_says_there_is_none(
        httpx_mock, settings, conn):
    """The register says where to look. Asking every company a question most
    of them answer 404 to is a request budget spent on nothing.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", insolvency=False)

    _run(conn, settings)

    assert not [r for r in httpx_mock.get_requests() if "/insolvency" in str(r.url)]
    assert conn.execute(
        "SELECT COUNT(*) c FROM company_insolvency_cases").fetchone()["c"] == 0


def test_a_profile_promising_insolvency_that_does_not_answer_is_recorded(
        httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved")
    httpx_mock.add_response(url=f"{BASE}/company/01842240/insolvency", status_code=404,
                             json={"errors": [{"error": "company-insolvency-information-not-found"}]})

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'company_insolvency_unavailable'").fetchone()["c"] == 1


def test_a_rerun_does_not_duplicate_cases(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)
    httpx_mock.add_response(url=f"{BASE}/company/01842240",
                             json=_profile("01842240", insolvency=True, status="dissolved"),
                             is_reusable=True)
    httpx_mock.add_response(url=f"{BASE}/company/01842240/insolvency", json=LIFELINE,
                             is_reusable=True)
    httpx_mock.add_response(url=re.compile(rf"{BASE}/company/01842240/officers.*"),
                             json={"items": []}, is_reusable=True)
    httpx_mock.add_response(url=re.compile(rf"{BASE}/company/01842240/filing-history.*"),
                             json={"total_count": 0, "items": []}, is_reusable=True)

    _run(conn, settings)
    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM company_insolvency_cases").fetchone()["c"] == 2
    assert conn.execute(
        "SELECT COUNT(*) c FROM company_insolvency_case_dates").fetchone()["c"] == 4


# --- dissolved is not insolvent ---------------------------------------------------

def test_a_dissolved_company_without_a_case_is_not_flagged_as_a_failure(
        httpx_mock, settings, conn):
    """Both dissolved companies this pipeline holds have no insolvency case:
    a company can be struck off having paid everyone. Reading "dissolved" as
    "failed" would turn an ordinary wind-down into evidence of collapse.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "01865768")
    _mock_company(httpx_mock, "01865768", insolvency=False, status="dissolved")

    _run(conn, settings)

    row = conn.execute("SELECT * FROM v_provider_viability").fetchone()
    assert row["company_status"] == "dissolved"
    assert row["insolvency_cases"] == 0
    assert row["viability_flag"] == "dissolved_no_insolvency_case"


def test_the_viability_view_reports_a_recorded_case(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn)
    _mock_company(httpx_mock, "01842240", insolvency=True, status="dissolved",
                   insolvency_body=LIFELINE)

    _run(conn, settings)

    row = conn.execute("SELECT * FROM v_provider_viability").fetchone()
    assert row["viability_flag"] == "insolvency_case_recorded"
    assert row["insolvency_cases"] == 2
    assert "in-administration" in row["insolvency_case_types"]
    assert row["first_insolvency_date"] == "2017-06-02"
    assert row["last_insolvency_date"] == "2024-01-25"


def test_the_viability_view_names_nobody(conn):
    """It joins tables that hold practitioners and officers. It must not carry
    either into something exportable.
    """
    columns = [r[1] for r in conn.execute("PRAGMA table_info(v_provider_viability)")]
    for column in columns:
        assert "name" not in column or column in ("company_name",), column


# --- splitting an officer's name --------------------------------------------------

@pytest.mark.parametrize("name,surname,forenames", [
    ("DENHOLM, Craig Nicholas", "denholm", ["craig", "nicholas"]),
    ("SMITH, Jane", "smith", ["jane"]),
    ("Jane Smith", "smith", ["jane"]),
    ("O'BRIEN, Mary Anne", "o'brien", ["mary", "anne"]),
])
def test_officer_names_split_into_surname_and_forenames(name, surname, forenames):
    assert ch.split_officer_name(name) == (surname, forenames)


@pytest.mark.parametrize("name", ["", None, "Cher", "   "])
def test_a_name_that_cannot_be_split_yields_nothing(name):
    assert ch.split_officer_name(name) == ("", [])
    assert ch.disqualification_search_term(name) is None


def test_the_search_term_is_the_name_as_a_person_would_write_it():
    assert ch.disqualification_search_term("DENHOLM, Craig Nicholas") == "craig denholm"


# --- who gets checked -------------------------------------------------------------

@pytest.mark.parametrize("officer,expected", [
    ({"officer_role": "director"}, True),
    ({"officer_role": "corporate-director"}, True),
    ({"officer_role": "director", "resigned_on": "2020-01-01"}, False),
    ({"officer_role": "secretary"}, False),
    ({"officer_role": "llp-member"}, False),
    ({}, False),
])
def test_only_serving_directors_are_checked(officer, expected):
    """Disqualification bars a person from acting as a director, so a serving
    director is the only officer the question is about. Sweeping resigned
    officers and secretaries too would multiply the number of people searched
    against a disqualification register to answer nothing.
    """
    assert ch.is_serving_director(officer) is expected


# --- deciding what is worth opening, from the search response alone ------------------

def test_the_two_sides_write_names_in_opposite_orders():
    """Companies House gives an officer as "SMITH, Aaron Donald"; the register
    gives a search hit as "Aaron Donald SMITH". They are the same person.
    """
    assert ch.names_agree("SMITH, Aaron Donald", "Aaron Donald SMITH") is True
    assert ch.names_agree("EXAMPLE, Alexander Peter", "Alexander Peter EXAMPLE") is True


@pytest.mark.parametrize("officer_name,hit_title", [
    ("SMITH, Aaron", "Aaron JONES"),          # different surname
    ("SMITH, Aaron", "Brian SMITH"),          # different forename
    ("SMITH, Aaron", "EXAMPLE HOLDINGS LLC"), # a company, not a person
    ("SMITH, Aaron", None),
    (None, "Aaron SMITH"),
])
def test_names_that_do_not_agree(officer_name, hit_title):
    assert ch.names_agree(officer_name, hit_title) is False


def test_dates_of_birth_agree_on_month_and_year():
    officer = {"date_of_birth": {"month": 3, "year": 1974}}
    assert ch.dates_of_birth_agree(officer, "1974-03-09T00:00:00") is True
    assert ch.dates_of_birth_agree(officer, "1974-03-09") is True
    assert ch.dates_of_birth_agree(officer, "1974-04-09") is False
    assert ch.dates_of_birth_agree(officer, "1975-03-09") is False


@pytest.mark.parametrize("officer,published", [
    ({}, "1974-03-09"),
    ({"date_of_birth": {"month": 3, "year": 1974}}, None),
    ({"date_of_birth": {"month": 3, "year": 1974}}, "1974"),
    ({"date_of_birth": {"month": 3, "year": 1974}}, "not a date at all"),
    ({"date_of_birth": {}}, "1974-03-09"),
])
def test_a_missing_or_unreadable_date_is_never_agreement(officer, published):
    """No corroboration is possible, so there is nothing to corroborate with.
    Treating absence as agreement would reduce this to a name match.
    """
    assert ch.dates_of_birth_agree(officer, published) is False


def test_a_hit_is_only_opened_when_the_name_and_the_date_both_agree():
    officer = {"name": "EXAMPLE, Alexander Peter",
                "date_of_birth": {"month": 3, "year": 1974}}
    hit = DISQ_SEARCH["items"][0]
    assert ch.search_hit_is_worth_opening(officer, hit) == (True, True)

    namesake = {"name": "EXAMPLE, Alexander Peter",
                 "date_of_birth": {"month": 11, "year": 1990}}
    assert ch.search_hit_is_worth_opening(namesake, hit) == (True, False)

    stranger = {"name": "UNRELATED, Bernard",
                 "date_of_birth": {"month": 3, "year": 1974}}
    assert ch.search_hit_is_worth_opening(stranger, hit) == (False, False)


# --- what counts as a match -------------------------------------------------------

def _officer(name="EXAMPLE, Alexander Peter", month=3, year=1974, person_number="p1"):
    return {"name": name, "person_number": person_number,
            "date_of_birth": {"month": month, "year": year}}


def test_a_matching_person_number_is_an_identifier_match():
    officer = _officer(person_number="999000010001")
    assert ch.disqualification_match_basis(officer, DISQ_DETAIL) == "person_number"


def test_name_and_month_and_year_of_birth_together_are_enough():
    assert ch.disqualification_match_basis(_officer(), DISQ_DETAIL) == "name_and_date_of_birth"


def test_a_name_on_its_own_is_never_enough():
    """The whole discipline of this module in one assertion. A shared name is
    not a shared identity — and here, being wrong means recording that a named
    person was banned from directing companies.
    """
    assert ch.disqualification_match_basis(
        {"name": "EXAMPLE, Alexander Peter", "person_number": "p1"}, DISQ_DETAIL) is None
    assert ch.disqualification_match_basis(
        _officer(month=None, year=None), DISQ_DETAIL) is None


@pytest.mark.parametrize("kwargs", [
    {"month": 4},                               # different birth month
    {"year": 1975},                             # different birth year
    {"name": "EXAMPLE, Andrew Peter"},          # different forename
    {"name": "EXAMPLED, Alexander Peter"},      # different surname
])
def test_any_disagreement_defeats_the_match(kwargs):
    assert ch.disqualification_match_basis(_officer(**kwargs), DISQ_DETAIL) is None


def test_a_malformed_date_of_birth_is_not_treated_as_agreement():
    assert ch.disqualification_match_basis(
        _officer(), {**DISQ_DETAIL, "date_of_birth": "not a date"}) is None
    assert ch.disqualification_match_basis(
        _officer(), {**DISQ_DETAIL, "date_of_birth": None}) is None


# --- the sweep, end to end ---------------------------------------------------------

DIRECTOR = {"person_number": "999000010001", "name": "EXAMPLE, Alexander Peter",
            "officer_role": "director", "appointed_on": "2020-01-01",
            "date_of_birth": {"month": 3, "year": 1974}, "address": {"locality": "Exampleton"}}
NAMESAKE = {"person_number": "p-other", "name": "EXAMPLE, Alexander Peter",
            "officer_role": "director", "appointed_on": "2020-01-01",
            "date_of_birth": {"month": 11, "year": 1990}, "address": {}}


def _mock_disqualification(httpx_mock, search=None, detail=None, with_detail=True):
    httpx_mock.add_response(url=re.compile(rf"{BASE}/search/disqualified-officers.*"),
                             json=search if search is not None else DISQ_SEARCH,
                             is_reusable=True)
    if with_detail:
        httpx_mock.add_response(
            url=re.compile(rf"{BASE}/disqualified-officers/natural/.*"),
            json=detail if detail is not None else DISQ_DETAIL, is_reusable=True)


def test_a_corroborated_disqualification_is_recorded(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[DIRECTOR])
    _mock_disqualification(httpx_mock)

    _run(conn, settings)

    row = conn.execute("SELECT * FROM restricted_officer_disqualifications").fetchone()
    assert row is not None
    assert row["case_identifier"] == "INV0000001"
    assert row["match_basis"] == "person_number"
    assert row["disqualification_type"] == "undertaking"
    assert row["disqualified_until"] == "2031-04-30"
    assert row["disqualified_company_names"] == "EXAMPLE TRADING LIMITED"


def test_a_namesake_is_queued_for_review_and_never_stored(httpx_mock, settings, conn):
    """Same name, different person. This is the row that must not be written.

    No detail mock is registered: a namesake is rejected from the search
    response alone, so opening their record would be an unregistered request
    and this test would fail.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[NAMESAKE])
    _mock_disqualification(httpx_mock, with_detail=False)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM restricted_officer_disqualifications").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'unconfirmed_disqualification_name_match'").fetchone()["c"] == 1
    assert [r for r in httpx_mock.get_requests()
             if "/disqualified-officers/natural/" in str(r.url)] == []


def test_an_unrelated_search_hit_costs_no_request_and_no_review_row(
        httpx_mock, settings, conn):
    """The register's search is fuzzy — a search for one director returns
    every approximate match it holds. Opening each hit to find that out would
    be one request per stranger at one every two seconds, per director, and
    queueing each for review would bury the real namesakes.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[
        {"person_number": "d9", "name": "UNRELATED, Bernard", "officer_role": "director",
         "appointed_on": "2020-01-01", "date_of_birth": {"month": 3, "year": 1974},
         "address": {}},
    ])
    _mock_disqualification(httpx_mock, with_detail=False)

    _run(conn, settings)

    assert [r for r in httpx_mock.get_requests()
             if "/disqualified-officers/natural/" in str(r.url)] == []
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'unconfirmed_disqualification_name_match'").fetchone()["c"] == 0


def test_the_review_item_does_not_repeat_the_registers_identifying_detail(
        httpx_mock, settings, conn):
    """The point of the row is that this is NOT known to be the same person.
    Copying the register record's name and date of birth into it would attach
    a disqualified person's details to a director who is not them.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[NAMESAKE])
    _mock_disqualification(httpx_mock, with_detail=False)

    _run(conn, settings)

    item = conn.execute(
        "SELECT raw_value, context_json FROM review_queue "
        "WHERE item_type = 'unconfirmed_disqualification_name_match'").fetchone()
    blob = f"{item['raw_value']} {item['context_json']}"
    assert "1974-03-09" not in blob
    assert "INV0000001" not in blob
    assert "EXAMPLE TRADING" not in blob


def test_a_corporate_disqualification_is_skipped(httpx_mock, settings, conn):
    """Sanctioned corporate entities appear in the same search results. A
    company is not a serving director of a provider.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[DIRECTOR])
    _mock_disqualification(httpx_mock)

    _run(conn, settings)

    corporate = [r for r in httpx_mock.get_requests()
                  if "/disqualified-officers/corporate/" in str(r.url)]
    assert corporate == []


def test_an_empty_register_answer_writes_nothing(httpx_mock, settings, conn):
    """The expected outcome, every run. An empty table is a checkable
    negative, not a skipped check.
    """
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[DIRECTOR])
    _mock_disqualification(httpx_mock, search={"total_results": 0, "items": []},
                            with_detail=False)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM restricted_officer_disqualifications").fetchone()["c"] == 0
    assert [r for r in httpx_mock.get_requests()
             if "/search/disqualified-officers" in str(r.url)], "the check did run"


def test_secretaries_and_resigned_officers_are_not_searched(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[
        {"person_number": "s1", "name": "SECRETARY, Sam", "officer_role": "secretary",
         "address": {}},
        {"person_number": "r1", "name": "RESIGNED, Rita", "officer_role": "director",
         "resigned_on": "2021-01-01", "address": {}},
    ])
    # Deliberately no disqualification mock: if the sweep searched anyway,
    # there would be no response registered and the run would fail here.

    _run(conn, settings)

    assert [r for r in httpx_mock.get_requests()
             if "/search/disqualified-officers" in str(r.url)] == []


def test_a_failed_register_search_is_recorded(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed(conn, "03861209")
    _mock_company(httpx_mock, "03861209", officers=[DIRECTOR])
    httpx_mock.add_response(url=re.compile(rf"{BASE}/search/disqualified-officers.*"),
                             status_code=404, json={}, is_reusable=True)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'disqualification_search_failed'").fetchone()["c"] == 1


def test_disqualifications_are_restricted(conn):
    from pipeline import db

    assert "restricted_officer_disqualifications" in db.restricted_tables(conn)
    assert "restricted_company_insolvency_practitioners" in db.restricted_tables(conn)
