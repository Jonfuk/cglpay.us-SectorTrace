"""Module 21: ONS ASHE earnings via the developer API.

The module reads the version's own dimension options and queries the
intersection with its pinned codes; the tests pin the request shape, the
observation parsing (both documented response shapes), and the honest
failure paths — including the 502 that the live endpoint was answering at
verification time.
"""
from __future__ import annotations

import re

from pipeline.modules import m21_ons_ashe as ashe
from pipeline.registry import ModuleContext

API = "https://api.beta.ons.gov.uk/v1"
EDITION = "/editions/time-series"
OBS = (f"{API}/datasets/ashe-tables-3{EDITION}/versions/7/observations")


def _allow_robots(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.beta\.ons\.gov\.uk/robots\.txt"),
        status_code=200, text="", is_reusable=True)


def _only_dataset(monkeypatch, dataset_id: str) -> None:
    """Run the module against one dataset: the offline suite must mock every
    request the module makes, and the module makes requests for both."""
    monkeypatch.setattr(ashe, "DATASETS", {dataset_id: ashe.DATASETS[dataset_id]})


def _mock_dataset(httpx_mock, *, dataset_id="ashe-tables-3", version="7",
                  options=None, observations=None, observations_status=200):
    if options is None:
        options = _options()  # the real option set for ashe-tables-3 v7
    httpx_mock.add_response(
        url=f"{API}/datasets/{dataset_id}",
        json={"title": "Earnings and hours worked, region by occupation by "
                        "two-digit SOC: ASHE Table 3", "id": dataset_id},
        is_reusable=True)
    httpx_mock.add_response(
        url=f"{API}/datasets/{dataset_id}{EDITION}",
        json={"links": {"latest_version": {"id": version,
                                            "href": f"{API}/datasets/{dataset_id}{EDITION}/versions/{version}"}}},
        is_reusable=True)
    dimension = ashe.DATASETS[dataset_id]["dimension_param"]
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/datasets/{dataset_id}{EDITION}/versions/{version}/dimensions/{dimension}/options.*"),
        json={"items": options}, is_reusable=True)
    if observations is not None:
        httpx_mock.add_response(
            url=re.compile(rf"{re.escape(API)}/datasets/{dataset_id}{EDITION}/versions/{version}/observations.*"),
            json=observations, status_code=observations_status, is_reusable=True)


def _options():
    """The real option set for ashe-tables-3 v7 (abridged), captured live."""
    return [
        {"option": "11", "label": "Corporate managers and directors",
         "dimension": "standardoccupationalclassification"},
        {"option": "22", "label": "Health professionals",
         "dimension": "standardoccupationalclassification"},
        {"option": "24", "label": "Business, media and public service professionals",
         "dimension": "standardoccupationalclassification"},
        {"option": "32", "label": "Health and social care associate professionals",
         "dimension": "standardoccupationalclassification"},
        {"option": "35", "label": "Business and public service associate professionals",
         "dimension": "standardoccupationalclassification"},
        {"option": "61", "label": "Caring personal service occupations",
         "dimension": "standardoccupationalclassification"},
        {"option": "62", "label": "Leisure, travel and related personal service occupations",
         "dimension": "standardoccupationalclassification"},
        {"option": "92", "label": "Elementary administration and service occupations",
         "dimension": "standardoccupationalclassification"},
    ]


def _observation(code, geography, time_value, value="15.42", **dims):
    observation = {
        "dimensions": {
            "standardoccupationalclassification": {"option": {"id": code}},
            "geography": {"option": {"id": geography}},
            "time": {"option": {"id": time_value}},
        },
        "observation": value,
    }
    for name, value in dims.items():
        observation["dimensions"][name] = {"option": {"id": value}}
    return observation


def _run(conn, settings, httpx_mock):
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    ashe.run(ctx)


# --- parsing -------------------------------------------------------------------

def test_option_labels_come_from_the_version_options():
    labels = ashe._option_labels({"items": _options()})
    assert labels["61"] == "Caring personal service occupations"
    assert labels["11"] == "Corporate managers and directors"


def test_an_observation_carries_its_own_dimensions_when_it_has_them():
    observation = {"dimensions": {
        "standardoccupationalclassification": {"option": {"id": "61"}},
        "geography": {"option": {"id": "K02000001"}},
        "time": {"option": {"id": "2023"}}}, "observation": "15.42"}
    dims = ashe._observation_dimensions(observation, {})
    assert dims == {"standardoccupationalclassification": "61",
                    "geography": "K02000001", "time": "2023"}


def test_a_single_value_query_falls_back_to_the_request_options():
    """The API documents per-observation dimensions for multi-option queries
    and top-level ones for a single value; the fallback keeps both shapes
    readable."""
    dims = ashe._observation_dimensions({"observation": "15.42"},
                                         {"standardoccupationalclassification": "61",
                                          "geography": "K02000001"})
    assert dims["standardoccupationalclassification"] == "61"


def test_an_observation_that_is_not_a_number_is_null_not_zero():
    assert ashe._as_number("15.42") == 15.42
    assert ashe._as_number("-3.1") == -3.1
    assert ashe._as_number("") is None
    assert ashe._as_number("-") is None
    assert ashe._as_number("N/A") is None


# --- a run ---------------------------------------------------------------------

def test_a_run_stores_the_observations_the_query_returns(
        conn, settings, httpx_mock, monkeypatch):
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock, observations={
        "observations": [
            _observation("61", "K02000001", "2023"),
            _observation("61", "K02000001", "2021", "x"),
            _observation("61", "E92000001", "2022", "16.01"),
        ],
        "total_observations": 3, "offset": 0, "limit": 10000,
        "unit_of_measure": "£"})

    _run(conn, settings, httpx_mock)

    rows = conn.execute("SELECT * FROM ons_ashe_observations ORDER BY time").fetchall()
    assert len(rows) == 3
    first = next(r for r in rows if r["time"] == "2022")
    assert first["dataset_id"] == "ashe-tables-3"
    assert first["version"] == "7"
    assert first["dimension_kind"] == "occupation"
    assert first["dimension_code"] == "61"
    assert first["dimension_label"] == "Caring personal service occupations"
    assert first["geography_code"] == "E92000001"
    assert first["geography_label"] == "England"
    assert first["time"] == "2022"
    assert first["value"] == 16.01
    assert first["value_text"] == "16.01"
    assert first["unit_of_measure"] == "£"
    assert first["hoursandearnings"] == "hourly-pay-excluding-overtime"
    assert first["source_system"] == "ons_ashe"

    unparsed = next(r for r in rows if r["value_text"] == "x")
    assert unparsed["value"] is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM parse_failures WHERE module = 'm21_ons_ashe'"
    ).fetchone()["c"] == 1


def test_the_query_names_every_pinned_code_and_both_geographies(
        conn, settings, httpx_mock, monkeypatch):
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock, observations={
        "observations": [], "total_observations": 0, "offset": 0,
        "limit": 10000, "unit_of_measure": "£"})

    _run(conn, settings, httpx_mock)

    queries = [r for r in httpx_mock.get_requests() if "/observations" in str(r.url)]
    assert len(queries) == 1
    params = queries[0].url.params
    assert params["time"] == "*"
    assert params["averagesandpercentiles"] == "median"
    assert params["hoursandearnings"] == "hourly-pay-excluding-overtime"
    assert params["sex"] == "all"
    assert params["workingpattern"] == "all"
    assert params.get_list("geography") == ["K02000001", "E92000001"]
    assert params.get_list("standardoccupationalclassification") == \
        ashe.DATASETS["ashe-tables-3"]["codes"]


def test_a_pinned_code_the_version_no_longer_serves_raises_a_review_item(
        conn, settings, httpx_mock, monkeypatch):
    """The version's own options are the source of truth: a pinned code that
    is not among them is flagged, and the rest are still queried."""
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    options = [o for o in _options() if o["option"] != "92"]
    _mock_dataset(httpx_mock, options=options, observations={
        "observations": [], "total_observations": 0, "offset": 0,
        "limit": 10000, "unit_of_measure": "£"})

    _run(conn, settings, httpx_mock)

    item = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'ons_ashe_pinned_code_missing'"
    ).fetchone()
    assert item is not None
    assert "92" in item["raw_value"]


def test_a_4xx_from_observations_is_recorded_not_guessed(
        conn, settings, httpx_mock, monkeypatch):
    """A 4xx returns as a result, and the module records the failure and
    writes nothing — a plausible-looking zero series would be worse than an
    absent one. A persistent 5xx is different and deliberately NOT handled
    here: the shared client retries it and raises, so a broken endpoint
    fails the run loudly (the rule m16's suite pins). The live endpoint was
    answering 502 at verification, which is why this module currently fails
    against it rather than collecting nothing quietly.
    """
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock, observations={}, observations_status=404)

    _run(conn, settings, httpx_mock)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'ons_ashe_observations_failed'").fetchone()["c"] == 1
    assert conn.execute("SELECT COUNT(*) c FROM ons_ashe_observations").fetchone()["c"] == 0


def test_an_edition_with_no_version_is_recorded(conn, settings, httpx_mock, monkeypatch):
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url=f"{API}/datasets/ashe-tables-3",
        json={"title": "x", "id": "ashe-tables-3"}, is_reusable=True)
    httpx_mock.add_response(
        url=f"{API}/datasets/ashe-tables-3{EDITION}",
        json={"links": {}}, is_reusable=True)

    _run(conn, settings, httpx_mock)

    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'ons_ashe_edition_unavailable'").fetchone()["c"] == 1


def test_a_paged_response_is_read_to_the_total(conn, settings, httpx_mock, monkeypatch):
    """The response pages by offset to its own total_observations; a short
    first page must not be read as the whole series."""
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    page_one = {
        "observations": [_observation("61", "K02000001", "2023")],
        "total_observations": 2, "offset": 0, "limit": 10000,
        "unit_of_measure": "£"}
    page_two = {
        "observations": [_observation("61", "K02000001", "2022")],
        "total_observations": 2, "offset": 1, "limit": 10000,
        "unit_of_measure": "£"}
    # Registered before the generic page: httpx-mock answers with the first
    # matching response, and the offset=1 request matches both.
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/datasets/ashe-tables-3{EDITION}/versions/7/observations\?.*offset=1.*"),
        json=page_two, is_reusable=True)
    _mock_dataset(httpx_mock, observations=None)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/datasets/ashe-tables-3{EDITION}/versions/7/observations.*"),
        json=page_one, is_reusable=True)

    _run(conn, settings, httpx_mock)

    assert conn.execute("SELECT COUNT(*) c FROM ons_ashe_observations").fetchone()["c"] == 2


def test_the_industry_dataset_uses_its_own_dimension(conn, settings, httpx_mock, monkeypatch):
    _only_dataset(monkeypatch, "ashe-table-5")
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url=f"{API}/datasets/ashe-table-5",
        json={"title": "Earnings and Hours Worked, UK Region by Industry by "
                        "Two-Digit SIC: ASHE Table 5", "id": "ashe-table-5"},
        is_reusable=True)
    httpx_mock.add_response(
        url=f"{API}/datasets/ashe-table-5{EDITION}",
        json={"links": {"latest_version": {"id": "7",
                                            "href": f"{API}/datasets/ashe-table-5{EDITION}/versions/7"}}},
        is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/datasets/ashe-table-5{EDITION}/versions/7/dimensions/unofficialstandardindustrialclassification/options.*"),
        json={"items": [
            {"option": "84", "label": "Public Administration and Defence; Compulsory Social Security"},
            {"option": "86", "label": "Human Health Activities"},
            {"option": "87", "label": "Residential Care Activities"},
            {"option": "88", "label": "Social Work Activities Without Accommodation"},
        ]}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(API)}/datasets/ashe-table-5{EDITION}/versions/7/observations.*"),
        json={"observations": [{
            "dimensions": {
                "unofficialstandardindustrialclassification": {"option": {"id": "88"}},
                "geography": {"option": {"id": "E92000001"}},
                "time": {"option": {"id": "2023"}}},
            "observation": "12.50"}],
            "total_observations": 1, "offset": 0, "limit": 10000,
            "unit_of_measure": "£"}, is_reusable=True)

    _run(conn, settings, httpx_mock)

    row = conn.execute("SELECT * FROM ons_ashe_observations").fetchone()
    assert row is not None
    assert row["dataset_id"] == "ashe-table-5"
    assert row["dimension_kind"] == "industry"
    assert row["dimension_code"] == "88"
    assert row["dimension_label"] == "Social Work Activities Without Accommodation"
