from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import pytest

from pipeline.http import PipelineHTTPClient
from pipeline.modules import m00_geography as geo

FIXTURES = Path(__file__).parent / "fixtures"


def _allow_all_robots(httpx_mock, origin: str = "https://www.arcgis.com") -> None:
    httpx_mock.add_response(url=f"{origin}/robots.txt", status_code=200, text="")


def test_discover_boundary_series_parses_real_search_response(httpx_mock, settings):
    """Regression fixture: a real ArcGIS Online search response for the
    Counties and Unitary Authorities BGC series, including the
    "inc Metropolitan Counties" decoy title that must NOT be picked up.
    """
    _allow_all_robots(httpx_mock)
    fixture = json.loads((FIXTURES / "arcgis_search_ctyua_bgc.json").read_text())
    httpx_mock.add_response(url=re.compile(r"https://www\.arcgis\.com/sharing/rest/search.*"), json=fixture)

    with PipelineHTTPClient("test", settings=settings) as client:
        series = geo._discover_boundary_series(client, "Counties and Unitary Authorities", "BGC")

    labels = [v.vintage_label for v in series]
    assert labels == sorted(labels, key=lambda l: series[labels.index(l)].vintage_date)
    assert "DEC_2025" in labels
    # the decoy "inc Metropolitan Counties" title must be excluded
    assert not any("inc Metropolitan Counties" in v.title for v in series)
    # series must be chronologically ascending
    dates = [v.vintage_date for v in series]
    assert dates == sorted(dates)
    assert series[-1].vintage_label == "DEC_2025"
    assert series[-1].vintage_date == date(2025, 12, 1)


def test_discover_boundary_series_deduplicates_v2_corrections(httpx_mock, settings):
    results = [
        {"id": "orig", "title": "Local Authority Districts (May 2025) Boundaries UK BGC",
         "type": "Feature Service", "created": 1000, "owner": "ONSGeography_data"},
        {"id": "v2", "title": "Local Authority Districts (May 2025) Boundaries UK BGC (V2)",
         "type": "Feature Service", "created": 2000, "owner": "ONSGeography_data"},
    ]
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=re.compile(r"https://www\.arcgis\.com/sharing/rest/search.*"),
                             json={"results": results})

    with PipelineHTTPClient("test", settings=settings) as client:
        series = geo._discover_boundary_series(client, "Local Authority Districts", "BGC")

    assert len(series) == 1
    assert series[0].item_id == "v2"


def test_find_field_requires_exactly_one_match():
    assert geo._find_field(["CTYUA25CD", "CTYUA25NM"], "ctyua_code") == "CTYUA25CD"
    with pytest.raises(geo.DiscoveryError):
        geo._find_field(["CTYUA25NM"], "ctyua_code")
    with pytest.raises(geo.DiscoveryError):
        geo._find_field(["CTYUA25CD", "CTYUA26CD"], "ctyua_code")


@pytest.mark.parametrize("code,expected", [
    ("E10000003", "county"),
    ("E06000001", "unitary"),
    ("E08000001", "metropolitan_district"),
    ("E09000001", "london_borough"),
    ("E07000008", "non_metropolitan_district"),
    ("W06000001", None),
])
def test_authority_type_from_prefix(code, expected):
    assert geo._authority_type(code) == expected


def _square(x0, y0, x1, y1) -> dict:
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def test_overlap_fraction_full_containment():
    predecessor = _square(0, 0, 2, 2)
    successor = _square(-1, -1, 3, 3)  # fully contains predecessor
    assert geo._overlap_fraction(predecessor, successor) == pytest.approx(1.0)


def test_overlap_fraction_half_overlap():
    predecessor = _square(0, 0, 2, 2)  # area 4
    successor = _square(1, 0, 3, 2)  # overlaps x in [1,2] -> area 2, half of predecessor
    assert geo._overlap_fraction(predecessor, successor) == pytest.approx(0.5)


def test_overlap_fraction_no_overlap():
    predecessor = _square(0, 0, 1, 1)
    successor = _square(5, 5, 6, 6)
    assert geo._overlap_fraction(predecessor, successor) == pytest.approx(0.0)


def test_resolve_successors_logs_review_item_when_no_candidates(conn, settings):
    module_name = "m00_geography"
    v = geo.Vintage(item_id="x", title="t", vintage_label="DEC_2024", vintage_date=date(2024, 12, 1), service_url="https://example.com/svc")

    with PipelineHTTPClient("test", settings=settings, conn=conn) as client:
        geo._resolve_successors(conn, client, module_name, {"E10000099": (v, "ctyua_code")}, {}, {}, "DEC_2024", "DEC_2025")

    rows = conn.execute("SELECT * FROM review_queue WHERE item_type = 'unresolved_successor'").fetchall()
    assert len(rows) == 1
    assert rows[0]["raw_value"] == "E10000099"
