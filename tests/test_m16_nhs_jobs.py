"""Module 16, and the one thing this source will do to you if you let it.

Searching NHS Jobs by employer does not filter by employer. Search a name that
does not exist and it returns "659 jobs found" of unrelated adverts; search
"Turning Point" and West Point Medical Centre comes back alongside it; search
"Richmond Fellowship" and all eighteen hits belong to Kingston and Richmond
NHS Foundation Trust. A parser that trusts the result set publishes another
employer's salary under a provider's name, and nothing about the response says
it has happened.

It does also have a genuine empty answer, on its own separate page, and that
distinction is pinned here too: "found nothing" and "could not read the page"
must not be the same event.

So the assertions here are mostly about what does NOT get stored, and they are
made against pages captured live on 2026-08-11 rather than hand-written HTML.
Each fixture is two verbatim slices of a real response — the results heading
and the results list with its pagination — joined by a comment marking the
page furniture that was dropped. The only edit inside a slice is the
per-session _csrf token, replaced with REDACTED.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.modules import m16_nhs_jobs as nj
from pipeline.registry import ModuleContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CGL = (FIXTURES / "nhs_jobs_search_cgl.html").read_text(encoding="utf-8")
TURNING_POINT = (FIXTURES / "nhs_jobs_search_turning_point.html").read_text(encoding="utf-8")
UNMATCHED = (FIXTURES / "nhs_jobs_search_unmatched_employer.html").read_text(encoding="utf-8")
NO_RESULTS = (FIXTURES / "nhs_jobs_search_no_results.html").read_text(encoding="utf-8")

CGL_URL = "https://www.jobs.nhs.uk/candidate/search/results?employer=Change%20Grow%20Live&page=1"
TP_URL = "https://www.jobs.nhs.uk/candidate/search/results?employer=Turning%20Point&page=1"


def _rows(html: str, url: str = CGL_URL) -> list[dict]:
    return nj.parse_search_results(html, url)


def _by_reference(html: str, reference: str, url: str = CGL_URL) -> dict:
    return next(r for r in _rows(html, url) if r["job_reference"] == reference)


# --- reading a results page ---------------------------------------------------

def test_reads_every_advert_on_the_page():
    assert len(_rows(CGL)) == 10
    assert len(_rows(TURNING_POINT, TP_URL)) == 5


def test_every_advert_carries_its_fields_and_not_just_a_title():
    """Regression. Each advert nests two more <ul>/<li> lists for the salary
    and contract fields, so the obvious `<li ...>(.*?)</li>` pattern ends the
    advert at the first nested </li>. That version returned ten adverts with a
    title, a reference and every other column NULL — which downstream is
    indistinguishable from ten employers who published no pay.
    """
    for row in _rows(CGL):
        assert row["employer_name_raw"], row["job_reference"]
        assert row["salary_raw"], row["job_reference"]
        assert row["contract_type"], row["job_reference"]
        assert row["working_pattern"], row["job_reference"]
        assert row["posted_date"], row["job_reference"]
        assert row["locations"], row["job_reference"]


def test_the_job_reference_comes_from_the_advert_path():
    row = _by_reference(CGL, "U0080-26-20864")
    assert row["job_title"] == "Substance Misuse Nurse"
    assert row["advert_url"] == "https://www.jobs.nhs.uk/candidate/jobadvert/U0080-26-20864"


def test_the_advert_url_does_not_carry_the_search_that_found_it():
    """The same advert reached by two provider searches is one advert at one
    address. Keeping "?employer=…&page=1" would make its URL depend on how it
    happened to be found.
    """
    for row in _rows(CGL):
        assert "?" not in row["advert_url"]
        assert "employer=" not in row["advert_url"]


def test_no_duplicate_references_within_a_page():
    references = [r["job_reference"] for r in _rows(CGL)]
    assert len(references) == len(set(references))


def test_an_empty_page_yields_no_rows_rather_than_raising():
    assert nj.parse_search_results("", CGL_URL) == []
    assert nj.parse_search_results("<html><body><p>Something else</p></body></html>",
                                    CGL_URL) == []


def test_unbalanced_markup_yields_nothing_rather_than_the_rest_of_the_document():
    """A truncated response must not read as a page of adverts assembled from
    whatever followed the results list.
    """
    truncated = CGL[:CGL.index('data-test="search-result"') + 200]
    assert nj.parse_search_results(truncated, CGL_URL) == []


# --- pay, which is the whole point of this module -----------------------------

def test_reads_an_advertised_range():
    row = _by_reference(CGL, "U0080-26-20864")
    assert row["salary_raw"] == "£38,114.53 to £44,469.24 a year"
    assert row["salary_min"] == 38114.53
    assert row["salary_max"] == 44469.24
    assert row["salary_period"] == "year"
    assert row["salary_basis"] == "range"


def test_a_single_figure_is_stored_as_both_ends_of_the_range():
    """Otherwise every range query over this table silently drops the adverts
    that quote one number.
    """
    parsed = nj.parse_salary("£27,580 a year")
    assert parsed["salary_min"] == parsed["salary_max"] == 27580.0
    assert parsed["salary_basis"] == "single"


def test_an_employer_who_published_no_figure_is_not_recorded_as_zero():
    """"Depends on experience" is what the employer chose to publish. It is an
    absence, not a parse failure and certainly not a salary of nothing.
    """
    row = _by_reference(TURNING_POINT, "B0471-26-0037", TP_URL)
    assert row["salary_raw"] == "Depends on experience"
    assert row["salary_min"] is None
    assert row["salary_max"] is None
    assert row["salary_basis"] == "not_stated"


def test_a_figure_that_cannot_be_read_is_distinguished_from_one_that_is_absent():
    assert nj.parse_salary("£TBC on appointment")["salary_basis"] == "unparsed"
    assert nj.parse_salary("Negotiable")["salary_basis"] == "not_stated"


@pytest.mark.parametrize("raw,period", [
    ("£23.83 an hour", "hour"),
    ("£1,850 a session", "session"),
    ("£100,870 to £111,441 a year", "year"),
    ("£3,000 a month", "month"),
])
def test_the_period_the_employer_published_is_kept_as_published(raw, period):
    assert nj.parse_salary(raw)["salary_period"] == period


def test_an_hourly_rate_is_never_annualised():
    """The conversion depends on contracted hours this pipeline does not know,
    and would put a figure in the warehouse that no source ever stated.
    """
    parsed = nj.parse_salary("£23.83 an hour")
    assert parsed["salary_min"] == parsed["salary_max"] == 23.83
    assert parsed["salary_period"] == "hour"
    assert parsed["salary_min"] < 100    # not multiplied up by anything


def test_the_raw_salary_line_is_always_kept():
    for raw in ("£23.83 an hour", "Depends on experience", "£TBC"):
        assert nj.parse_salary(raw)["salary_raw"] == raw


def test_an_out_of_order_range_is_stored_as_published():
    """Silently swapping them would hide a genuine oddity in the source."""
    parsed = nj.parse_salary("£44,469 to £38,114 a year")
    assert parsed["salary_min"] == 44469.0
    assert parsed["salary_max"] == 38114.0


# --- locations ----------------------------------------------------------------

def test_an_advert_can_name_several_sites():
    row = _by_reference(CGL, "U0080-20402")
    assert row["locations"] == ["Chichester PO19 1XP", "CRAWLEY RH10 8GN",
                                 "Worthing BN11 1UG"]


def test_a_location_containing_a_comma_is_one_place_not_two():
    """Regression. The service separates sites with a comma AND a line break,
    and splitting on the comma turns "Liverpool, Merseyside L11 4SJ" into a
    place called Liverpool and a place called Merseyside.
    """
    assert _by_reference(CGL, "U0080-2026-20859")["locations"] == \
        ["Liverpool, Merseyside L11 4SJ"]


# --- dates --------------------------------------------------------------------

def test_dates_are_reformatted_not_inferred():
    assert nj.parse_uk_date("11 August 2026") == "2026-08-11"
    assert nj.parse_uk_date("4 September 2026") == "2026-09-04"


@pytest.mark.parametrize("raw", ["", None, "soon", "31 February 2026", "2026-08-11x",
                                  "11 Augvst 2026"])
def test_a_date_that_does_not_parse_is_none_rather_than_a_guess(raw):
    assert nj.parse_uk_date(raw) is None


def test_the_advert_dates_are_read_from_the_page():
    row = _by_reference(CGL, "U0080-26-20864")
    assert row["posted_date"] == "2026-08-11"
    assert row["closing_date"] == "2026-09-04"


# --- attribution: the discipline this module exists to keep ---------------------

def test_an_exact_employer_name_matches_its_provider():
    assert nj.match_employer("Change Grow Live") == ("change_grow_live", "exact")
    assert nj.match_employer("Turning Point") == ("turning_point", "exact")


def test_a_longer_employer_name_containing_a_known_variant_matches_as_a_component():
    assert nj.match_employer("Change Grow Live North West") == \
        ("change_grow_live", "component")
    assert nj.match_employer("Humankind Charity") == ("humankind", "component")


def test_a_registered_suffix_still_counts_as_the_same_name():
    """"Change Grow Live Services Ltd" is a configured variant and "Limited" is
    stripped before matching, so this is the same name, not a longer one.
    """
    assert nj.match_employer("Change Grow Live Services Limited") == \
        ("change_grow_live", "exact")


def test_west_point_medical_centre_is_not_turning_point():
    """The headline regression, and it is in the live fixture: searching
    "Turning Point" returns five adverts, one of which belongs to West Point
    Medical Centre. Attributing that advert's pay to Turning Point is exactly
    the failure this module is built to avoid.
    """
    assert nj.match_employer("West Point Medical Centre") == (None, None)

    employers = {r["employer_name_raw"] for r in _rows(TURNING_POINT, TP_URL)}
    assert "West Point Medical Centre" in employers, "fixture no longer covers this"
    matched = {e for e in employers if nj.match_employer(e)[0] is not None}
    assert matched == {"Turning Point"}


@pytest.mark.parametrize("employer", [
    "Viaduct Care", "Inclusion Housing", "CGL Recruitment Partners",
])
def test_short_or_ordinary_variants_do_not_match_inside_a_longer_name(employer):
    """"Via" and "Inclusion" are English words and "CGL" is three letters. As a
    whole employer name each is fine; hunted for inside one they attribute
    other people's adverts to a provider.
    """
    assert nj.match_employer(employer) == (None, None)


def test_an_unknown_employer_matches_nothing():
    for employer in ("NHS Employers", "Nimbuscare Ltd", "Employ-Ability", "", None):
        assert nj.match_employer(employer) == (None, None)


def test_the_searched_variants_exclude_the_ones_that_cannot_be_attributed():
    variants = [variant for _key, variant in nj.search_variants()]
    assert "Change Grow Live" in variants
    assert "Turning Point" in variants
    for unsafe in ("CGL", "Via", "Inclusion"):
        assert unsafe not in variants, (
            f"{unsafe!r} is searched but can never be attributed, so its results "
            "would all be discarded — requests to a public service for nothing")


def test_comparators_are_searched_and_not_only_the_target():
    """One provider's advertised bands say nothing on their own about whether
    they are low.
    """
    keys = {key for key, _variant in nj.search_variants()}
    assert "change_grow_live" in keys
    assert len(keys) > 1


def test_the_search_order_is_stable():
    assert nj.search_variants() == nj.search_variants()
    assert [k for k, _ in nj.search_variants()] == sorted(k for k, _ in nj.search_variants())


# --- a full result set is not evidence about the employer searched for ----------

def test_a_nonsense_employer_still_returns_a_full_page_of_adverts():
    """Pinned from a live response. This is the reason attribution is on the
    advert's own employer field and never on the search that found it: a
    non-empty result set says nothing at all about who was searched for.
    """
    rows = _rows(UNMATCHED)
    assert len(rows) == 10
    assert nj.reported_total(UNMATCHED) == 659
    assert all(nj.match_employer(r["employer_name_raw"]) == (None, None) for r in rows)


def test_the_reported_total_is_read_but_it_is_the_size_of_the_result_set():
    assert nj.reported_total(CGL) == 20
    assert nj.reported_total(TURNING_POINT) == 5
    assert nj.reported_total("<h1>no count here</h1>") is None


# --- and an empty one is a real answer, stated by the service --------------------

def test_the_service_says_when_it_found_nothing():
    """Captured from `employer=Addaction`: a different heading, no results list
    and its own "No result found" panel.
    """
    assert nj.has_no_results(NO_RESULTS) is True
    assert nj.parse_search_results(NO_RESULTS, CGL_URL) == []
    assert nj.reported_total(NO_RESULTS) is None


def test_a_page_with_adverts_is_not_a_no_results_page():
    for page in (CGL, TURNING_POINT, UNMATCHED):
        assert nj.has_no_results(page) is False


def test_an_advert_titled_no_result_found_cannot_empty_a_run():
    """The marker is anchored on the search heading element, not matched
    anywhere on the page, so advert text cannot trigger it.
    """
    assert nj.has_no_results(
        CGL.replace("Substance Misuse Nurse", "No result found Nurse")) is False


# --- pagination ----------------------------------------------------------------

def test_the_next_page_is_followed_from_the_pages_own_link():
    following = nj.next_result_page_url(CGL, CGL_URL)
    assert following is not None
    assert "page=2" in following
    assert following.startswith("https://www.jobs.nhs.uk/candidate/search/results")


def test_there_is_no_next_page_on_the_last_page():
    assert nj.next_result_page_url(TURNING_POINT, TP_URL) is None


def test_result_pages_per_variant_are_capped():
    """The only thing standing between a name the search does not recognise and
    paging through the whole service.
    """
    assert 1 <= nj.MAX_RESULT_PAGES <= 5


# --- robots -----------------------------------------------------------------------

def test_an_html_robots_response_yields_no_rules():
    """www.jobs.nhs.uk answers /robots.txt with an HTML page, not a rules file.
    The claim in the module docstring is that this leaves nothing to honour;
    this is that claim tested rather than assumed.
    """
    from pipeline.http import RobotsRules

    shell = ("<!DOCTYPE html><html><head><title>Service Domain Information</title>"
              "</head><body><p>Nothing here is a directive.</p></body></html>")
    rules = RobotsRules(shell, "cglpay-evidence-pipeline/0.1")
    assert rules.can_fetch("https://www.jobs.nhs.uk/candidate/search/results?employer=x")


# --- a run against mocked responses -------------------------------------------------

def _mock_search(httpx_mock, body: str, status_code: int = 200):
    httpx_mock.add_response(url="https://www.jobs.nhs.uk/robots.txt",
                             status_code=200, text="<html><body>Service</body></html>",
                             is_reusable=True)
    httpx_mock.add_response(url=re.compile(r"https://www\.jobs\.nhs\.uk/candidate/search/.*"),
                             status_code=status_code, text=body, is_reusable=True)


def _one_variant(monkeypatch, provider_key="change_grow_live", variant="Change Grow Live"):
    monkeypatch.setattr(nj, "search_variants", lambda: [(provider_key, variant)])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 1)
    # The role-keyword pass runs after the employer pass; these tests are
    # about the employer pass, so the keyword pass is silenced rather than
    # left to re-fetch the same fixture.
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", [])


def _run(conn, settings, since=None, limit=None):
    nj.run(ModuleContext(conn=conn, settings=settings, since=since,
                          dry_run=False, limit=limit))


def _search_requests(httpx_mock):
    return [r for r in httpx_mock.get_requests()
             if "/candidate/search/results" in str(r.url)]


def test_a_run_writes_the_adverts_it_could_attribute(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    rows = conn.execute("SELECT * FROM nhs_job_adverts").fetchall()
    assert len(rows) == 10
    assert {r["provider_key"] for r in rows} == {"change_grow_live"}
    assert {r["provider_match_basis"] for r in rows} == {"exact"}
    assert all(r["searched_variant"] == "Change Grow Live" for r in rows)


def test_written_rows_carry_provenance(conn, settings, httpx_mock, monkeypatch):
    from pipeline import db

    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    assert db.rows_missing_provenance(conn, "nhs_job_adverts") == []
    row = conn.execute("SELECT * FROM nhs_job_adverts LIMIT 1").fetchone()
    assert row["source_system"] == "nhs_jobs"
    assert row["payload_sha256"]
    assert row["http_status"] == 200


def test_the_pay_reaches_the_table_not_just_the_row(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    row = conn.execute(
        "SELECT * FROM nhs_job_adverts WHERE job_reference = 'U0080-26-20864'").fetchone()
    assert row["job_title"] == "Substance Misuse Nurse"
    assert row["salary_min"] == 38114.53
    assert row["salary_max"] == 44469.24
    assert row["salary_period"] == "year"
    assert row["posted_date"] == "2026-08-11"
    assert row["contract_type"] == "Permanent"


def test_locations_are_written_as_rows(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    sites = [r["location_raw"] for r in conn.execute(
        "SELECT location_raw FROM nhs_job_advert_locations "
        "WHERE job_reference = 'U0080-20402' ORDER BY location_raw")]
    assert sites == ["CRAWLEY RH10 8GN", "Chichester PO19 1XP", "Worthing BN11 1UG"]


def test_another_employers_advert_is_never_stored_under_the_searched_name(
        conn, settings, httpx_mock, monkeypatch):
    """The search returned it for "Turning Point". Its employer is West Point
    Medical Centre. It does not become a Turning Point pay figure.
    """
    _one_variant(monkeypatch, "turning_point", "Turning Point")
    _mock_search(httpx_mock, TURNING_POINT)

    _run(conn, settings)

    employers = {r["employer_name_raw"] for r in conn.execute(
        "SELECT employer_name_raw FROM nhs_job_adverts")}
    assert employers == {"Turning Point"}
    assert conn.execute(
        "SELECT COUNT(*) c FROM nhs_job_adverts WHERE employer_name_raw LIKE '%West Point%'"
    ).fetchone()["c"] == 0


def test_a_discarded_employer_is_recorded_rather_than_dropped_silently(
        conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch, "turning_point", "Turning Point")
    _mock_search(httpx_mock, TURNING_POINT)

    _run(conn, settings)

    discarded = conn.execute(
        "SELECT raw_value FROM review_queue WHERE item_type = 'unmatched_nhs_jobs_employer'"
    ).fetchall()
    assert [r["raw_value"] for r in discarded] == ["West Point Medical Centre"]


def test_a_search_that_matched_nothing_is_recorded_as_such(
        conn, settings, httpx_mock, monkeypatch):
    """Every advert belonged to someone else. That is a real answer — the
    provider may simply not advertise here — but it must not look like a
    productive crawl.
    """
    _one_variant(monkeypatch, "phoenix_futures", "Phoenix Futures")
    _mock_search(httpx_mock, UNMATCHED)

    _run(conn, settings)

    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_search_matched_nothing'").fetchone()["c"] == 1


def test_a_genuinely_empty_search_is_recorded_as_the_service_stated_it(
        conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch, "addaction", "Addaction")
    _mock_search(httpx_mock, NO_RESULTS)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_search_no_matches'").fetchone()["c"] == 1
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_results_unrecognised'").fetchone()["c"] == 0


def test_an_unrecognised_page_is_not_read_as_an_employer_with_no_vacancies(
        conn, settings, httpx_mock, monkeypatch):
    """A 200 that is neither a results page nor the service's own "no result
    found" page means the markup moved. Recording it as "no vacancies" would
    be a silent, and very plausible, lie.
    """
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, "<html><body><p>Something else entirely</p></body></html>")

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_results_unrecognised'").fetchone()["c"] == 1
    for absent in ("nhs_jobs_search_no_matches", "nhs_jobs_search_matched_nothing"):
        assert conn.execute(
            "SELECT COUNT(*) c FROM review_queue WHERE item_type = ?",
            (absent,)).fetchone()["c"] == 0


def test_a_blocked_search_is_recorded_and_does_not_empty_the_table(
        conn, settings, httpx_mock, monkeypatch):
    """A 4xx comes back as a result rather than an exception, so the module
    records the gap and carries on to the next provider. This is the case that
    matters: a variant whose adverts are simply absent from the run has to be
    visible, or the next run's totals move for no stated reason.

    A persistent 5xx is different and is deliberately NOT handled here — the
    shared client retries it six times and then raises, and the run reports a
    failed module. Swallowing that would make a broken source look like a
    provider that stopped advertising.
    """
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, "", status_code=403)

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_search_unavailable'").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 0


def test_since_filters_on_the_advert_date(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings, since="2026-08-01")

    posted = [r["posted_date"] for r in conn.execute(
        "SELECT posted_date FROM nhs_job_adverts")]
    assert posted, "the fixture has adverts on or after this date"
    assert all(value >= "2026-08-01" for value in posted)
    assert len(posted) < 10, "the fixture also has older adverts, which should be filtered"


def test_a_rerun_updates_rather_than_duplicates(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)
    _run(conn, settings)

    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 10
    assert conn.execute(
        "SELECT COUNT(*) c FROM nhs_job_advert_locations").fetchone()["c"] == 12


def test_limit_caps_what_is_written(conn, settings, httpx_mock, monkeypatch):
    _one_variant(monkeypatch)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings, limit=3)

    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 3


def test_paging_stops_at_the_cap(conn, settings, httpx_mock, monkeypatch):
    """Every page serves the same body, so its next-page link never runs out
    and every page attributes adverts. Only MAX_RESULT_PAGES ends the loop.
    """
    monkeypatch.setattr(nj, "search_variants", lambda: [("change_grow_live", "Change Grow Live")])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 2)
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", [])
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    assert len(_search_requests(httpx_mock)) == 2


def test_paging_stops_as_soon_as_a_page_attributes_nothing(
        conn, settings, httpx_mock, monkeypatch):
    """Results are relevance-ranked, so a page with none of the employer's own
    adverts means the search has run past them into the fallback. Four more
    pages of it would be requests to a public service for rows this module
    discards.
    """
    monkeypatch.setattr(nj, "search_variants", lambda: [("phoenix_futures", "Phoenix Futures")])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 5)
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", [])
    _mock_search(httpx_mock, UNMATCHED)   # 10 adverts, none attributable, next page offered

    _run(conn, settings)

    assert len(_search_requests(httpx_mock)) == 1, (
        "the first page attributed nothing, so there was no reason to ask for a second")


def test_a_search_that_only_re_finds_known_adverts_is_not_reported_as_matching_nothing(
        conn, settings, httpx_mock, monkeypatch):
    """Regression. `matched_here` was counted after de-duplication, so the
    second name variant for a provider — whose adverts the first variant had
    already collected — logged "every advert belonged to a different
    employer". It had in fact found all of the target's.
    """
    monkeypatch.setattr(nj, "search_variants", lambda: [
        ("change_grow_live", "Change Grow Live"),
        ("change_grow_live", "Change Grow Live Services Ltd"),
    ])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 1)
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 10
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_search_matched_nothing'").fetchone()["c"] == 0


def test_variants_differing_only_in_punctuation_are_searched_once():
    """"Change, Grow, Live" and "Change Grow Live" return the same twenty
    adverts and the same reported total, checked against the live service. One
    search, not two.
    """
    variants = [variant for _key, variant in nj.search_variants()]
    assert "Change Grow Live" in variants
    assert "Change, Grow, Live" not in variants


# --- the sustained crawl: the role-keyword pass ---------------------------------

def _keyword_only(monkeypatch, *terms):
    monkeypatch.setattr(nj, "search_variants", lambda: [])
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", list(terms))
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 1)


def test_a_role_search_surfaces_and_attributes_adverts(
        conn, settings, httpx_mock, monkeypatch):
    _keyword_only(monkeypatch, "recovery worker")
    _mock_search(httpx_mock, CGL)

    _run(conn, settings)

    rows = conn.execute("SELECT * FROM nhs_job_adverts").fetchall()
    assert len(rows) == 10
    assert {r["provider_key"] for r in rows} == {"change_grow_live"}
    assert all(r["surfaced_by"] == "role_search" for r in rows)
    assert all(r["searched_variant"] == "keyword:recovery worker" for r in rows)


def test_the_keyword_never_decides_whose_advert_it_is(
        conn, settings, httpx_mock, monkeypatch):
    """The keyword pass must hold the same rule as the employer pass: the
    advert's own employer field attributes it, never the term that found it.
    The Turning Point fixture contains West Point Medical Centre, and it must
    not become a Turning Point pay figure just because the search did.
    """
    _keyword_only(monkeypatch, "recovery worker")
    _mock_search(httpx_mock, TURNING_POINT)

    _run(conn, settings)

    employers = {r["employer_name_raw"] for r in conn.execute(
        "SELECT employer_name_raw FROM nhs_job_adverts")}
    assert employers == {"Turning Point"}


def test_a_role_search_that_finds_nothing_is_not_a_finding_about_a_provider(
        conn, settings, httpx_mock, monkeypatch):
    """A keyword with no results is a normal outcome, not a question about a
    provider — the `nhs_jobs_search_no_matches` item exists for employer
    searches, and a role search must not flood the queue with it.
    """
    _keyword_only(monkeypatch, "recovery worker")
    _mock_search(httpx_mock, NO_RESULTS)

    _run(conn, settings)

    assert conn.execute("SELECT COUNT(*) c FROM nhs_job_adverts").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type IN ('nhs_jobs_search_no_matches', "
        "'nhs_jobs_search_matched_nothing', "
        "'unmatched_nhs_jobs_employer')").fetchone()["c"] == 0


def test_a_role_search_markup_change_is_still_recorded(
        conn, settings, httpx_mock, monkeypatch):
    """The keyword pass is silent about empty searches and unmatched adverts,
    but not about a page that is neither results nor "no result found" — a
    markup change is a markup change whichever pass tripped over it.
    """
    _keyword_only(monkeypatch, "recovery worker")
    _mock_search(httpx_mock, "<html><body><p>Something else entirely</p></body></html>")

    _run(conn, settings)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'nhs_jobs_results_unrecognised'").fetchone()["c"] == 1


def test_surfaced_by_records_the_first_discovery_and_stays_stable(
        conn, settings, httpx_mock, monkeypatch):
    """An advert found by both passes keeps the record of which one found it
    first. The employer pass runs first: its rows say employer_search, and a
    later role search that re-finds them must not overwrite that.
    """
    _one_variant(monkeypatch)   # employer pass only, keyword pass silenced
    _mock_search(httpx_mock, CGL)
    _run(conn, settings)

    monkeypatch.setattr(nj, "search_variants", lambda: [])
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", ["recovery worker"])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 1)
    _run(conn, settings)

    row = conn.execute("SELECT * FROM nhs_job_adverts LIMIT 1").fetchone()
    assert row["surfaced_by"] == "employer_search"
    assert row["searched_variant"] == "Change Grow Live"


def test_a_role_search_first_discovery_survives_a_later_employer_search(
        conn, settings, httpx_mock, monkeypatch):
    """The reverse order: the keyword pass finds the adverts first, and a
    later employer search that re-finds them does not rewrite the discovery
    record — searched_variant and surfaced_by both describe how the advert
    first entered the corpus, and that is the keyword search.
    """
    _keyword_only(monkeypatch, "recovery worker")
    _mock_search(httpx_mock, CGL)
    _run(conn, settings)

    monkeypatch.setattr(nj, "search_variants", lambda: [("change_grow_live", "Change Grow Live")])
    monkeypatch.setattr(nj, "ROLE_KEYWORDS", [])
    monkeypatch.setattr(nj, "MAX_RESULT_PAGES", 1)
    _run(conn, settings)

    row = conn.execute("SELECT * FROM nhs_job_adverts LIMIT 1").fetchone()
    assert row["surfaced_by"] == "role_search"
    assert row["searched_variant"] == "keyword:recovery worker"


# --- the repeat-advertisement view --------------------------------------------------

def _insert_advert(conn, reference, title, posted, salary_min=30000.0, salary_max=35000.0,
                    period="year", employer="Change Grow Live"):
    conn.execute(
        "INSERT INTO nhs_job_adverts (job_reference, provider_key, provider_match_basis, "
        "employer_name_raw, job_title, advert_url, salary_raw, salary_min, salary_max, "
        "salary_period, salary_basis, posted_date, searched_variant, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "(?, 'change_grow_live', 'exact', ?, ?, 'https://x', 'raw', ?, ?, ?, 'range', ?, "
        "'Change Grow Live', 'https://u', '2026-08-11T00:00:00Z', 200, 'nhs_jobs', 'h')",
        (reference, employer, title, salary_min, salary_max, period, posted))


def test_a_role_advertised_twice_is_surfaced_as_a_candidate(conn):
    from pipeline import providers

    providers.seed_providers(conn)
    _insert_advert(conn, "REF-1", "Recovery Worker", "2026-01-10")
    _insert_advert(conn, "REF-2", "recovery worker", "2026-06-02")
    _insert_advert(conn, "REF-3", "Senior Recovery Worker", "2026-03-01")

    rows = conn.execute("SELECT * FROM v_nhs_repeat_advertised_roles").fetchall()
    assert len(rows) == 1
    assert rows[0]["job_title_normalised"] == "recovery worker"
    assert rows[0]["advert_count"] == 2
    assert rows[0]["first_posted_date"] == "2026-01-10"
    assert rows[0]["last_posted_date"] == "2026-06-02"


def test_a_seniority_prefix_is_a_different_job_not_a_repeat(conn):
    from pipeline import providers

    providers.seed_providers(conn)
    _insert_advert(conn, "REF-1", "Recovery Worker", "2026-01-10")
    _insert_advert(conn, "REF-2", "Senior Recovery Worker", "2026-06-02")

    assert conn.execute(
        "SELECT COUNT(*) c FROM v_nhs_repeat_advertised_roles").fetchone()["c"] == 0


def test_mixed_pay_periods_in_a_group_are_flagged_rather_than_averaged(conn):
    from pipeline import providers

    providers.seed_providers(conn)
    _insert_advert(conn, "REF-1", "Nurse", "2026-01-10", 30000.0, 35000.0, "year")
    _insert_advert(conn, "REF-2", "Nurse", "2026-06-02", 22.0, 26.0, "hour")

    row = conn.execute("SELECT * FROM v_nhs_repeat_advertised_roles").fetchone()
    assert row["distinct_salary_periods"] == 2, (
        "an hourly and an annual figure in one group are not comparable and the "
        "view has to say so")
