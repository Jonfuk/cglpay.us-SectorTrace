"""Module 21: ONS ASHE earnings via the developer API.

The module reads the version's own dimension options and queries the
intersection with its pinned codes, one (geography, code) pair per request —
the live API 400s a request naming several codes or geographies at once
(verified 2026-08-22). The tests pin the request shape, the observation
parsing (both documented response shapes), and the honest failure paths,
including a transport-level failure stopping the remaining combinations for
a dataset without discarding rows already collected.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import httpx

from pipeline.modules import m21_ons_ashe as ashe
from pipeline.registry import ModuleContext

API = "https://api.beta.ons.gov.uk/v1"
EDITION = "/editions/time-series"
OBS = (f"{API}/datasets/ashe-tables-3{EDITION}/versions/7/observations")


def _allow_robots(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://api\.beta\.ons\.gov\.uk/robots\.txt"),
        status_code=200, text="", is_reusable=True)


def _only_dataset(monkeypatch, dataset_id: str, *, codes: list[str] | None = None,
                  geographies: list[tuple[str, str]] | None = None) -> None:
    """Run the module against one dataset: the offline suite must mock every
    request the module makes, and the module makes requests for both.

    `codes`/`geographies` shrink the (geography, code) cross-product the
    module now issues one request per combination for — most tests only
    care about one or two combinations, not all sixteen.
    """
    dataset = dict(ashe.DATASETS[dataset_id])
    if codes is not None:
        dataset["codes"] = codes
    monkeypatch.setattr(ashe, "DATASETS", {dataset_id: dataset})
    if geographies is not None:
        monkeypatch.setattr(ashe, "GEOGRAPHIES", geographies)


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
    """One request per geography now (see the module docstring), so the two
    geographies' observations come back on separate, precisely-matched
    responses rather than one shared blob.
    """
    _only_dataset(monkeypatch, "ashe-tables-3", codes=["61"])
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(OBS)}\?.*geography=K02000001.*"),
        json={
            "observations": [
                _observation("61", "K02000001", "2023"),
                _observation("61", "K02000001", "2021", "x"),
            ],
            "total_observations": 2, "offset": 0, "limit": 10000,
            "unit_of_measure": "£"}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(OBS)}\?.*geography=E92000001.*"),
        json={
            "observations": [_observation("61", "E92000001", "2022", "16.01")],
            "total_observations": 1, "offset": 0, "limit": 10000,
            "unit_of_measure": "£"}, is_reusable=True)

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


def test_the_query_makes_one_single_valued_request_per_geography_and_code(
        conn, settings, httpx_mock, monkeypatch):
    """The live API 400s a request naming several codes or geographies at
    once (verified 2026-08-22) — every pinned code and both geographies
    still get queried, just one (geography, code) pair per request.
    """
    _only_dataset(monkeypatch, "ashe-tables-3")
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock, observations={
        "observations": [], "total_observations": 0, "offset": 0,
        "limit": 10000, "unit_of_measure": "£"})

    _run(conn, settings, httpx_mock)

    queries = [r for r in httpx_mock.get_requests() if "/observations" in str(r.url)]
    codes = ashe.DATASETS["ashe-tables-3"]["codes"]
    geographies = [code for code, _ in ashe.GEOGRAPHIES]
    assert len(queries) == len(codes) * len(geographies)

    seen: set[tuple[str, str]] = set()
    for request in queries:
        params = request.url.params
        assert params["time"] == "*"
        assert params["averagesandpercentiles"] == "median"
        assert params["hoursandearnings"] == "hourly-pay-excluding-overtime"
        assert params["sex"] == "all"
        assert params["workingpattern"] == "all"
        assert len(params.get_list("geography")) == 1
        assert len(params.get_list("standardoccupationalclassification")) == 1
        seen.add((params["geography"], params["standardoccupationalclassification"]))
    assert seen == {(geo, code) for geo in geographies for code in codes}


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
    writes nothing for that dataset — a plausible-looking zero series would
    be worse than an absent one. Every (geography, code) combination fails
    the same way here, but only one review item is written per dataset, not
    one per combination. A persistent 5xx or a transport-level failure is
    different — see test_a_transport_failure_stops_the_dataset_but_keeps_
    rows_already_collected — and stops the remaining combinations rather
    than retrying all of them the same losing way.
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
    _only_dataset(monkeypatch, "ashe-tables-3", codes=["61"],
                  geographies=[("K02000001", "United Kingdom")])
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
    """ashe-table-5's industry dimension has two names (verified
    2026-08-22): /dimensions/{name}/options answers under
    unofficialstandardindustrialclassification with real labels;
    /observations 400s on that name and wants
    standardindustrialclassification instead. The options request below
    stays on the "unofficial" name; the observations request and its
    response's embedded dimensions use the other one.
    """
    _only_dataset(monkeypatch, "ashe-table-5", codes=["88"],
                  geographies=[("E92000001", "England")])
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
                "standardindustrialclassification": {"option": {"id": "88"}},
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


# --- resilience against the endpoint that is currently broken ------------------

def test_a_run_keeps_rows_from_combinations_that_answered_ok(
        conn, settings, httpx_mock, monkeypatch):
    """One geography's request answers with real data, the other 404s.
    Failure on one (geography, code) combination is not a reason to discard
    the ones that worked: the good row is written, and the dataset still
    gets one review item noting the failure.
    """
    _only_dataset(monkeypatch, "ashe-tables-3", codes=["61"])
    _allow_robots(httpx_mock)
    _mock_dataset(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(OBS)}\?.*geography=K02000001.*"),
        json={"observations": [_observation("61", "K02000001", "2023")],
              "total_observations": 1, "offset": 0, "limit": 10000,
              "unit_of_measure": "£"}, is_reusable=True)
    httpx_mock.add_response(
        url=re.compile(rf"{re.escape(OBS)}\?.*geography=E92000001.*"),
        json={}, status_code=404, is_reusable=True)

    _run(conn, settings, httpx_mock)

    rows = conn.execute("SELECT * FROM ons_ashe_observations").fetchall()
    assert len(rows) == 1
    assert rows[0]["geography_code"] == "K02000001"

    item = conn.execute(
        "SELECT * FROM review_queue WHERE item_type = 'ons_ashe_observations_failed'"
    ).fetchone()
    assert item is not None
    assert '"rows_recovered": 1' in item["context_json"]


class _FakeResult:
    """A minimal stand-in for FetchResult — `_fetch_observations` only reads
    `.ok`, `.status_code`, `.body` and what `_provenance` reads off a
    successful one.
    """

    def __init__(self, *, ok: bool, body: bytes = b"{}"):
        self.ok = ok
        self.status_code = 200 if ok else 500
        self.body = body
        self.url = "https://api.beta.ons.gov.uk/v1/fake"
        self.retrieved_at = datetime.now(timezone.utc)
        self.payload_sha256 = "fake"


class _FakeClient:
    """Stands in for PipelineHTTPClient in a call to `_fetch_observations`
    directly, so this test can make a call raise without going through the
    real client's retry-with-real-sleep behaviour (six attempts with
    exponential backoff on anything retryable, including a timeout) — that
    behaviour is real and desired in production, just not something a unit
    test should sit through.
    """

    def __init__(self, responses: list):
        self._responses = list(responses)

    def get(self, url, *, params=None):
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_a_transport_failure_stops_the_dataset_but_keeps_rows_already_collected():
    """The first (geography, code) combination answers with real data; the
    second raises rather than answering (a timeout or a 5xx the shared
    client has already retried into exhaustion — verified 2026-08-22 against
    the live endpoint). The row already collected is kept, one error is
    recorded, and no further combinations are attempted for this dataset.
    """
    good = _FakeResult(ok=True, body=json.dumps({
        "observations": [_observation("61", "K02000001", "2023")],
        "total_observations": 1, "offset": 0, "unit_of_measure": "£",
    }).encode())
    client = _FakeClient([good, httpx.ReadTimeout("boom")])

    rows, errors = ashe._fetch_observations(
        client, dataset_id="ashe-tables-3", version="7",
        dimension_param="standardoccupationalclassification", codes=["61", "22"])

    assert len(rows) == 1
    assert rows[0]["dimensions"]["geography"] == "K02000001"
    assert len(errors) == 1
    assert "ReadTimeout" in errors[0]
