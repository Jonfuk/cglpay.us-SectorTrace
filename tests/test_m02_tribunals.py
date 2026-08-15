from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pipeline import providers
from pipeline.modules import m02_tribunals as trib
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str = "https://www.gov.uk") -> None:
    # reusable: each module run builds a fresh client, which re-fetches robots.txt
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="", is_reusable=True)


def _no_eat_results(httpx_mock) -> None:
    """The appeal pass runs in every end-to-end test. Keyed on its format
    filter in the query string so it can never intercept the first-instance
    search, which shares the URL; the register's own answer for most names
    is an empty result set.
    """
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_appeal_tribunal_decision.*"),
        json={"total": 0, "results": []}, is_reusable=True)


# --- case number parsing ------------------------------------------------------

def test_parse_case_number_from_title():
    parsed = trib.parse_case_number("Ms X Roe v Change, Grow, Live: 1308908/2022", "")
    assert parsed == ("1308908/2022", "13", "2022")


def test_parse_case_number_falls_back_to_slug():
    parsed = trib.parse_case_number(
        "Title without a case number",
        "/employment-tribunal-decisions/ms-s-thompson-v-change-grow-live-2409308-slash-2022",
    )
    assert parsed == ("2409308/2022", "24", "2022")


def test_parse_case_number_returns_none_when_absent():
    assert trib.parse_case_number("No case number here", "/some/other/path") is None


@pytest.mark.parametrize("title,expected", [
    # Each of these reproduces the *shape* of a real GOV.UK decision title
    # that the original end-anchored, slash-only pattern silently dropped.
    # Claimant names are synthetic — only the case-number formatting matters.
    ("Ms A Roe v Change, Grow, Live and others: 2303382/2024 and others",
     ("2303382/2024", "23", "2024")),        # trailing text after the number
    ("Miss B Roe v Change, Grow, Live: 3205625/2022 and Others",
     ("3205625/2022", "32", "2022")),        # trailing text, different casing
    ("Mr C Roe v Change Grow Live: 2201707 2018",
     ("2201707/2018", "22", "2018")),        # space instead of a slash
])
def test_parse_case_number_handles_real_title_variants(title, expected):
    assert trib.parse_case_number(title, "") == expected


def test_parse_case_number_ignores_implausible_year():
    # a stray number must not be misread as a case number
    assert trib.parse_case_number("Some Body v Another: 1234567 1899", "") is None


# --- name extraction / pseudonymisation ---------------------------------------

def test_extract_claimant_and_respondent():
    title = "Ms X Roe v Change, Grow, Live: 1308908/2022"
    assert trib.extract_claimant_name(title) == "Ms X Roe"
    assert trib.extract_respondent_name(title) == "Change, Grow, Live"


def test_claim_ref_is_deterministic_and_name_free():
    ref_a = trib.claim_ref_for("1308908/2022")
    ref_b = trib.claim_ref_for("1308908/2022")
    assert ref_a == ref_b
    assert ref_a.startswith("ET-")
    assert "Roe" not in ref_a
    assert trib.claim_ref_for("2409308/2022") != ref_a


# --- respondent -> provider matching -------------------------------------------

@pytest.mark.parametrize("respondent", [
    "Change, Grow, Live",
    "Change Grow Live",
    "Change Grow Live Services Ltd",
])
def test_match_provider_key_handles_real_name_variants(respondent):
    assert trib.match_provider_key(respondent) == "change_grow_live"


def test_match_provider_key_returns_none_for_unrelated_respondent():
    assert trib.match_provider_key("Some Unrelated Employer Ltd") is None
    assert trib.match_provider_key(None) is None


def test_exact_match_reports_exact_basis():
    assert trib.match_respondent("Change Grow Live") == ("change_grow_live", "exact")


@pytest.mark.parametrize("respondent", [
    # all of these are real respondent strings observed in live GOV.UK data
    "Change Grow Live and A Person",
    "Lifeline Project (in administration) and Change Grow Live",
    "Change Grow Live and others",
    "Change Grow Live and Crime Reduction Unit",
])
def test_component_match_catches_real_multi_respondent_cases(respondent):
    provider_key, basis = trib.match_respondent(respondent)
    assert provider_key == "change_grow_live"
    assert basis == "component"


@pytest.mark.parametrize("respondent", [
    # real false positives that the ambiguous "CGL" acronym search surfaced
    "L'Oreal UK",
    "Durham County Council",
    "London North Eastern Railway and Ms B Person",
    "Midlands Pallets",
    "Tower Transit Operations",
])
def test_unrelated_employers_never_match(respondent):
    assert trib.match_respondent(respondent) == (None, None)


def test_component_match_respects_token_boundaries():
    # "Via" is a real provider name but also an ordinary word — it must not
    # match inside a longer unrelated word or an unrelated company name.
    assert trib.match_respondent("Viaduct Engineering Ltd") == (None, None)
    assert trib.match_respondent("Inclusion Housing Association") == (None, None)


# --- body text extraction ------------------------------------------------------

def test_extract_hearing_venue_strips_trailing_date():
    body = "Claimant: Ms X\r\nHeard at: Birmingham by telephone On: 15 June 2023\r\nBefore: EJ Y"
    assert trib.extract_hearing_venue(body) == "Birmingham by telephone"


def test_extract_hearing_venue_returns_none_when_absent():
    assert trib.extract_hearing_venue("no venue line here") is None
    assert trib.extract_hearing_venue(None) is None


@pytest.mark.parametrize("body,expected", [
    ("The claim for unfair dismissal is struck out and dismissed", "struck_out"),
    ("The claim is dismissed upon withdrawal", "dismissed"),
    ("The complaint is well-founded", "upheld"),
    ("Some text with no recognisable outcome phrasing at all", None),
])
def test_extract_outcome(body, expected):
    assert trib.extract_outcome(body) == expected


def test_extract_outcome_none_for_empty_body():
    assert trib.extract_outcome(None) is None


def test_document_type_classification():
    assert trib._document_type("X v Y: 1/2022 - Judgment with Reasons") == "judgment_with_reasons"
    assert trib._document_type("X v Y: 1/2022 - Judgment") == "judgment"
    assert trib._document_type("X v Y - Reconsideration") == "reconsideration"
    # no explicit type stated -> NULL rather than an assumed default
    assert trib._document_type("X v Y: 1/2022") is None
    assert trib._document_type(None) is None


# --- provider seeding ----------------------------------------------------------

def test_seed_providers_is_idempotent(conn):
    providers.seed_providers(conn)
    providers.seed_providers(conn)
    count = conn.execute("SELECT COUNT(*) c FROM providers").fetchone()["c"]
    assert count > 0
    cgl = conn.execute("SELECT * FROM providers WHERE provider_key = 'change_grow_live'").fetchone()
    assert cgl["is_target"] == 1


def test_seeded_charity_number_is_verified(conn):
    providers.seed_providers(conn)
    row = conn.execute(
        "SELECT * FROM provider_identifiers WHERE provider_key='change_grow_live' AND scheme='charity_number'"
    ).fetchone()
    assert row["identifier"] == "1079327"
    assert row["status"] == "verified"


def test_discovered_identifier_never_overwrites_verified(conn):
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "change_grow_live", "charity_number", "1079327", discovered_by="m03_charity_finance"
    )
    row = conn.execute(
        "SELECT * FROM provider_identifiers WHERE provider_key='change_grow_live' AND scheme='charity_number'"
    ).fetchone()
    assert row["status"] == "verified"
    assert row["discovered_by"] is None


def test_discovered_identifier_recorded_as_unverified(conn):
    providers.seed_providers(conn)
    providers.record_discovered_identifier(
        conn, "turning_point", "company_number", "00000001", discovered_by="m04_companies"
    )
    row = conn.execute(
        "SELECT * FROM provider_identifiers WHERE provider_key='turning_point' AND scheme='company_number'"
    ).fetchone()
    assert row["status"] == "unverified"
    assert row["discovered_by"] == "m04_companies"


# --- end-to-end ----------------------------------------------------------------

def test_run_end_to_end_against_real_fixtures(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    # single variant keeps the mock accounting simple; multi-variant dedup
    # is covered separately below
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change, Grow, Live"])

    search_fixture = json.loads((FIXTURES / "govuk_search_tribunals.json").read_text())
    one_result = {"total": 1, "results": search_fixture["results"][:1]}
    content_fixture = json.loads((FIXTURES / "govuk_content_tribunal_decision.json").read_text())

    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=one_result)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=content_fixture)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM tribunal_cases").fetchone()
    assert case["case_number"] == "1308908/2022"
    assert case["provider_key"] == "change_grow_live"
    assert case["decision_date"] == "2025-02-18"
    assert case["jurisdiction_codes"] == "race-discrimination,unfair-dismissal"
    assert case["document_count"] == 3  # multi-document case modelled correctly
    assert case["office_prefix"] == "13"
    # no verified prefix mapping exists, so region must stay NULL not guessed
    assert case["region"] is None
    assert case["hearing_venue_raw"] == "Birmingham by telephone"
    # outcome is body-derived only, so it can never be flagged high confidence
    assert case["outcome_confidence"] in (None, "low")

    docs = conn.execute("SELECT * FROM tribunal_documents ORDER BY document_url").fetchall()
    assert len(docs) == 3

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='unmapped_tribunal_office_prefix'"
    ).fetchall()
    assert [r["raw_value"] for r in review] == ["13"]


def test_run_puts_claimant_name_only_in_restricted_table(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change, Grow, Live"])

    search_fixture = json.loads((FIXTURES / "govuk_search_tribunals.json").read_text())
    one_result = {"total": 1, "results": search_fixture["results"][:1]}
    content_fixture = json.loads((FIXTURES / "govuk_content_tribunal_decision.json").read_text())
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=one_result)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=content_fixture)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    restricted = conn.execute("SELECT * FROM restricted_tribunal_parties").fetchone()
    assert restricted["claimant_name_raw"] == "Ms X Roe"

    # The public row must not carry the claimant's name in ANY column.
    public = conn.execute("SELECT * FROM tribunal_cases").fetchone()
    public_blob = " ".join(str(v) for v in tuple(public) if v is not None)
    assert "Roe" not in public_blob
    assert "X Roe" not in public_blob


def test_run_dedupes_case_found_under_multiple_name_variants(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live",
                         ["Change, Grow, Live", "Change Grow Live"])

    search_fixture = json.loads((FIXTURES / "govuk_search_tribunals.json").read_text())
    one_result = {"total": 1, "results": search_fixture["results"][:1]}
    content_fixture = json.loads((FIXTURES / "govuk_content_tribunal_decision.json").read_text())

    # both variants return the same case
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
                             json=one_result, is_reusable=True)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             json=content_fixture, is_reusable=True)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM tribunal_cases").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM tribunal_documents").fetchone()["c"] == 3


def test_run_skips_unmatched_respondent_and_logs_it(httpx_mock, settings, conn, monkeypatch):
    """A search on an ambiguous acronym returns unrelated employers; those
    must never land in tribunal_cases, or COUNT(*) becomes indefensible.
    """
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["CGL"])

    unrelated = {"total": 1, "results": [{
        "title": "Mr A Smith v L'Oreal UK: 2301827/2023",
        "link": "/employment-tribunal-decisions/mr-a-smith-v-loreal-uk-2301827-slash-2023",
        "tribunal_decision_categories": ["unfair-dismissal"],
        "tribunal_decision_decision_date": "2023-06-01",
        "tribunal_decision_country": "england-and-wales",
    }]}
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=unrelated)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM tribunal_cases").fetchone()["c"] == 0
    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='unmatched_tribunal_respondent'"
    ).fetchall()
    assert len(review) == 1
    assert "Oreal" in review[0]["raw_value"]


def test_run_flags_component_match_for_review(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change Grow Live"])

    multi = {"total": 1, "results": [{
        "title": "Ms X v Change Grow Live and A Person: 2401267/2021",
        "link": "/employment-tribunal-decisions/ms-x-v-cgl-and-k-morris-2401267-slash-2021",
        "tribunal_decision_categories": ["unfair-dismissal"],
        "tribunal_decision_decision_date": "2022-01-01",
        "tribunal_decision_country": "england-and-wales",
    }]}
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=multi)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             json={"details": {"attachments": [], "metadata": {}}})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM tribunal_cases").fetchone()
    assert case["provider_key"] == "change_grow_live"
    assert case["provider_match_basis"] == "component"
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='multi_respondent_tribunal_case'"
    ).fetchone()["c"] == 1


def test_documents_survive_a_304_on_rerun(httpx_mock, settings, conn, monkeypatch):
    """Regression: on a second run the decision page returns 304, and the
    module previously treated that as a failure and recorded zero documents —
    silently wiping every attachment on every re-run.
    """
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change, Grow, Live"])

    search_fixture = json.loads((FIXTURES / "govuk_search_tribunals.json").read_text())
    one_result = {"total": 1, "results": search_fixture["results"][:1]}
    content_fixture = json.loads((FIXTURES / "govuk_content_tribunal_decision.json").read_text())
    content_bytes = json.dumps(content_fixture).encode()

    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"),
                             json=one_result, is_reusable=True)
    # first run: real body, with an ETag so the next run is conditional
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             content=content_bytes,
                             headers={"content-type": "application/json", "etag": 'W/"abc123"'})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)
    assert conn.execute("SELECT COUNT(*) c FROM tribunal_documents").fetchone()["c"] == 3

    # second run: server says unchanged
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"), status_code=304)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM tribunal_cases").fetchone()
    assert case["document_count"] == 3, "304 on re-run must not zero out document_count"
    assert conn.execute("SELECT COUNT(*) c FROM tribunal_documents").fetchone()["c"] == 3


def test_region_populated_when_prefix_mapping_verified(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    _no_eat_results(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change, Grow, Live"])
    conn.execute(
        "INSERT INTO tribunal_office_regions (office_prefix, region, office_name, verified_source) "
        "VALUES ('13', 'West Midlands', 'Birmingham', 'https://example.com/citation')"
    )

    search_fixture = json.loads((FIXTURES / "govuk_search_tribunals.json").read_text())
    one_result = {"total": 1, "results": search_fixture["results"][:1]}
    content_fixture = json.loads((FIXTURES / "govuk_content_tribunal_decision.json").read_text())
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"), json=one_result)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=content_fixture)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM tribunal_cases").fetchone()
    assert case["region"] == "West Midlands"
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='unmapped_tribunal_office_prefix'"
    ).fetchone()["c"] == 0

# --- Employment Appeal Tribunal (Phase 15 / G4) --------------------------------

EAT_TITLE = "Change Grow Live v Ms A Person: [2024] EAT 12"
EAT_BODY = (
    "The Employment Appeal Tribunal received submissions from both parties.\r\n"
    "The appeal is dismissed.\r\n"
    "The judgment below was on a claim between Ms A Person and Change Grow "
    "Live (Case No.: 2303961/2024). A further case (Case No. 1308908/2022) "
    "was referred to.\r\n"
)


def test_extract_eat_citation_from_title():
    assert trib.extract_eat_citation(EAT_TITLE) == "[2024] EAT 12"
    assert trib.extract_eat_citation("No citation here") is None
    assert trib.extract_eat_citation(None) is None


def test_split_eat_parties():
    assert trib.split_eat_parties(EAT_TITLE) == ("Change Grow Live", "Ms A Person")
    assert trib.split_eat_parties("Single Name [2024] EAT 1") == (None, None)
    assert trib.split_eat_parties(None) == (None, None)


def test_extract_eat_outcome_phrases():
    assert trib.extract_eat_outcome("The appeal is dismissed.") == "dismissed"
    assert trib.extract_eat_outcome("We allow the appeal.") == "allowed"
    assert trib.extract_eat_outcome("The appeal is allowed in part.") == "allowed_in_part"
    assert trib.extract_eat_outcome("The appeal is remitted to the tribunal.") == "remitted"
    assert trib.extract_eat_outcome("The appeal is withdrawn.") == "withdrawn"
    assert trib.extract_eat_outcome("The tribunal made findings of fact.") is None
    assert trib.extract_eat_outcome(None) is None


def test_extract_underlying_et_cases_handles_real_punctuation():
    body = ("Case No.: 2303961/2024 and Case No. : 3305345/2022 and "
            "Case No. 2202400/2022 and Case No.: 2303961/2024 again")
    assert trib.extract_underlying_et_cases(body) == "2303961/2024,3305345/2022,2202400/2022"
    assert trib.extract_underlying_et_cases("no cases cited") is None
    assert trib.extract_underlying_et_cases(None) is None


def test_eat_pass_stores_an_appeal_with_both_parties_matched(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change Grow Live"])

    search = {"total": 1, "results": [{
        "title": EAT_TITLE,
        "link": "/employment-appeal-tribunal-decisions/change-grow-live-v-ms-a-person-2024-eat-12",
        "tribunal_decision_categories": ["unfair-dismissal"],
        "tribunal_decision_decision_date": "2024-06-01",
    }]}
    content = {"details": {
        "metadata": {"hidden_indexable_content": EAT_BODY,
                      "tribunal_decision_landmark": "not-landmark"},
        "attachments": [{"url": "https://www.gov.uk/example.pdf", "title": "Judgment PDF",
                          "content_type": "application/pdf"}],
    }}
    # the first-instance pass must find nothing; the appeal pass gets its own
    # response, keyed on the format filter in the query string so the two can
    # never cross
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_tribunal_decision.*"),
        json={"total": 0, "results": []}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_appeal_tribunal_decision.*"),
        json=search)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"), json=content)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM eat_cases").fetchone()
    assert case["neutral_citation"] == "[2024] EAT 12"
    assert case["provider_key"] == "change_grow_live"
    assert case["provider_side"] == "appellant"
    assert case["provider_match_basis"] == "exact"
    assert case["decision_date"] == "2024-06-01"
    assert case["outcome"] == "dismissed"
    assert case["outcome_confidence"] == "low"
    assert case["underlying_et_cases"] == "2303961/2024,1308908/2022"
    assert case["document_count"] == 1
    # the public row must not carry either party's name
    public_blob = " ".join(str(v) for v in tuple(case) if v is not None)
    assert "Person" not in public_blob and "Change Grow Live" not in public_blob

    restricted = conn.execute("SELECT * FROM restricted_eat_parties").fetchone()
    assert restricted["appellant_name_raw"] == "Change Grow Live"
    assert restricted["respondent_name_raw"] == "Ms A Person"

    doc = conn.execute("SELECT * FROM eat_documents").fetchone()
    assert doc["document_url"] == "https://www.gov.uk/example.pdf"


def test_eat_pass_matches_respondent_side_too(httpx_mock, settings, conn, monkeypatch):
    _allow_all_robots(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change Grow Live"])

    search = {"total": 1, "results": [{
        "title": "Ms A Person v Change Grow Live: [2025] EAT 3",
        "link": "/employment-appeal-tribunal-decisions/ms-a-person-v-change-grow-live-2025-eat-3",
        "tribunal_decision_decision_date": "2025-01-10",
    }]}
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_tribunal_decision.*"),
        json={"total": 0, "results": []}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_appeal_tribunal_decision.*"),
        json=search)
    httpx_mock.add_response(url=re.compile(r"https://www\.gov\.uk/api/content/.*"),
                             json={"details": {"metadata": {}, "attachments": []}})

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    case = conn.execute("SELECT * FROM eat_cases").fetchone()
    assert case["provider_key"] == "change_grow_live"
    assert case["provider_side"] == "respondent"


def test_eat_body_only_mention_is_queued_not_attributed(httpx_mock, settings, conn, monkeypatch):
    """The GOV.UK search indexes judgment bodies, so a hit can mention a
    provider without either party being one (the Attorney General's
    restriction-order judgments list the target's litigation history,
    provider cases included, in the body). That is a review item, never an
    eat_cases row -- attribution rests on the title alone, and the module
    does not fetch the decision page for a title it will not attribute.
    """
    _allow_all_robots(httpx_mock)
    monkeypatch.setitem(trib.SUPPLIER_NAME_VARIANTS, "change_grow_live", ["Change Grow Live"])

    search = {"total": 1, "results": [{
        "title": "The Attorney General v Ms S Person: [2026] EAT 34",
        "link": "/employment-appeal-tribunal-decisions/the-attorney-general-v-ms-s-person-2026-eat-34",
        "tribunal_decision_decision_date": "2026-03-03",
    }]}
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_tribunal_decision.*"),
        json={"total": 0, "results": []}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.gov\.uk/api/search\.json.*"
                       r"filter_format=employment_appeal_tribunal_decision.*"),
        json=search)

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    trib.run(ctx)

    assert conn.execute("SELECT COUNT(*) c FROM eat_cases").fetchone()["c"] == 0
    review = conn.execute("SELECT * FROM review_queue WHERE item_type='eat_body_mention_only'").fetchall()
    assert len(review) == 1
    assert "[2026] EAT 34" in review[0]["raw_value"]
    assert conn.execute("SELECT COUNT(*) c FROM restricted_eat_parties").fetchone()["c"] == 0
    # the decision page was never fetched: nothing would be attributed to it
    assert [r for r in httpx_mock.get_requests()
             if "/api/content/" in str(r.url)] == []
