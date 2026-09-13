"""Module 42: Nomis labour-market context."""
from __future__ import annotations

import re

from pipeline.modules import m42_nomis_context as nomis
from pipeline.registry import ModuleContext


def _allow_robots(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://www\.nomisweb\.co\.uk/robots\.txt"),
        status_code=200, text="", is_reusable=True,
    )


def _csv(*rows: str) -> str:
    return (
        "GEOGRAPHY_CODE,GEOGRAPHY_NAME,SEX,SEX_NAME,ITEM,ITEM_NAME,PAY,PAY_NAME,"
        "TIME,OBS_VALUE,OBS_STATUS,OBS_CONF,RECORD_OFFSET,RECORD_COUNT\n"
        + "\n".join(rows)
        + "\n"
    )


def _run(conn, settings, httpx_mock, *, datasets=None):
    _allow_robots(httpx_mock)
    selected = nomis.DATASETS
    if datasets is not None:
        selected = datasets
    # This also keeps the fixture explicit if a future test adds a dataset.
    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(nomis, "DATASETS", selected)
    try:
        ctx = ModuleContext(conn=conn, settings=settings, since=None,
                            dry_run=False, limit=None)
        nomis.run(ctx)
    finally:
        monkeypatch.undo()


def test_parse_csv_is_column_order_independent_and_keeps_total():
    text = (
        "OBS_VALUE,TIME,GEOGRAPHY_NAME,GEOGRAPHY_CODE,RECORD_COUNT\n"
        "15.20,2024,Example, E06000001 ,2\n"
    )
    rows, total = nomis.parse_csv(text)
    assert total == 2
    assert rows[0]["GEOGRAPHY_CODE"] == "E06000001"
    assert nomis._value("15.20") == 15.2
    assert nomis._value("-") is None


def test_run_stores_resident_and_workplace_rows(conn, settings, httpx_mock):
    for dataset_id in ("ASHER", "ASHE"):
        httpx_mock.add_response(
            url=re.compile(
                rf"https://www\.nomisweb\.co\.uk/api/v01/dataset/{dataset_id}\.data\.csv.*"
            ),
            text=_csv(
                "E06000001,Example,7,Total,2,Median,6,Hourly pay - excluding overtime,"
                "2024,15.20,, ,0,2",
                "E06000001,Example,7,Total,2,Median,9,Hours worked - total,"
                "2024,32.50,, ,1,2",
            ),
            is_reusable=True,
        )
    _run(conn, settings, httpx_mock)
    rows = conn.execute(
        "SELECT dataset_id, analysis, geography_code, pay, value "
        "FROM nomis_labour_market_observations ORDER BY dataset_id, pay"
    ).fetchall()
    assert [(r["dataset_id"], r["analysis"], r["geography_code"], r["pay"], r["value"])
            for r in rows] == [
                ("ASHE", "workplace", "E06000001", "6", 15.2),
                ("ASHE", "workplace", "E06000001", "9", 32.5),
                ("ASHER", "resident", "E06000001", "6", 15.2),
                ("ASHER", "resident", "E06000001", "9", 32.5),
            ]


def test_non_numeric_value_is_quarantined_and_not_zero(conn, settings, httpx_mock):
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.nomisweb\.co\.uk/api/v01/dataset/ASHER\.data\.csv.*"),
        text=_csv(
            "E06000001,Example,7,Total,2,Median,6,Hourly pay - excluding overtime,"
            "2024,not-a-number,, ,0,1",
        ),
        is_reusable=True,
    )
    original = nomis.DATASETS
    try:
        import pytest
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(nomis, "DATASETS", (original[0],))
        ctx = ModuleContext(conn=conn, settings=settings, since=None,
                            dry_run=False, limit=None)
        nomis.run(ctx)
        monkeypatch.undo()
    except Exception:
        try:
            monkeypatch.undo()
        except Exception:
            pass
        raise
    value = conn.execute(
        "SELECT value, value_text FROM nomis_labour_market_observations"
    ).fetchone()
    assert value["value"] is None
    assert value["value_text"] == "not-a-number"
    failure = conn.execute(
        "SELECT COUNT(*) AS n FROM parse_failures WHERE module = %s",
        ("m42_nomis_context",),
    ).fetchone()
    assert failure["n"] == 1


def test_failed_source_is_reviewed_and_does_not_become_empty_evidence(
        conn, settings, httpx_mock):
    _allow_robots(httpx_mock)
    httpx_mock.add_response(
        url=re.compile(r"https://www\.nomisweb\.co\.uk/api/v01/dataset/ASHER\.data\.csv.*"),
        status_code=503, text="unavailable", is_reusable=True,
    )
    original = nomis.DATASETS
    import pytest
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(nomis, "DATASETS", (original[0],))
    try:
        ctx = ModuleContext(conn=conn, settings=settings, since=None,
                            dry_run=False, limit=None)
        nomis.run(ctx)
    finally:
        monkeypatch.undo()
    item = conn.execute(
        "SELECT item_type, raw_value FROM review_queue "
        "WHERE module = %s AND raw_value = %s",
        ("m42_nomis_context", "ASHER"),
    ).fetchone()
    assert item["item_type"] == "nomis_dataset_fetch_failed"
