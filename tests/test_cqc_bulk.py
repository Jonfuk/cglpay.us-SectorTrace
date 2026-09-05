from __future__ import annotations

import csv
import io

from pipeline import cqc_bulk
from pipeline.http import PipelineHTTPClient

LANDING = cqc_bulk.LANDING_PAGE
CSV_URL = "https://www.cqc.org.uk/system/files/2026-08/19_August_2026_CQC_directory.csv"

LANDING_HTML = f'<html><body><a href="{CSV_URL}">CQC care directory - csv</a></body></html>'


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://www.cqc.org.uk/robots.txt", status_code=200, text="",
                             is_reusable=True)


def _client(settings, conn):
    return PipelineHTTPClient(cqc_bulk.SOURCE_SYSTEM, settings=settings, conn=conn)


def _csv_body(rows: list[list[str]]) -> bytes:
    header = ["Name", "Also known as", "Address", "Postcode", "Phone number",
              "Service's website (if available)", "Service types", "Date of latest check",
              "Specialisms/services", "Provider name", "Local authority", "Region",
              "Location URL", "CQC Location ID (for office use only)",
              "CQC Provider ID (for office use only)"]
    lines = [
        "CQC Locations data" + "," * 14,
        "," * 14,
        "This data was produced on 19 August 2026" + "," * 14,
        "," * 14,
        ",".join(header),
    ]
    for row in rows:
        lines.append(",".join(f'"{c}"' if "," in c else c for c in row))
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


# --- find_link ----------------------------------------------------------------

def test_find_link_matches():
    assert cqc_bulk.find_link(cqc_bulk.DIRECTORY_LINK_RE, LANDING_HTML) == CSV_URL


def test_find_link_returns_none_when_absent():
    assert cqc_bulk.find_link(cqc_bulk.DIRECTORY_LINK_RE, "<html>nothing here</html>") is None


# --- find_directory_url ---------------------------------------------------------

def test_find_directory_url_success(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=LANDING, text=LANDING_HTML)
    with _client(settings, conn) as client:
        assert cqc_bulk.find_directory_url(client, conn, "m05_cqc") == CSV_URL


def test_find_directory_url_records_review_item_on_fetch_failure(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=LANDING, status_code=404)
    with _client(settings, conn) as client:
        assert cqc_bulk.find_directory_url(client, conn, "m05_cqc") is None
    row = conn.execute(
        "SELECT * FROM review_queue WHERE module='m05_cqc' AND item_type='cqc_bulk_export_fetch_failed'"
    ).fetchone()
    assert row is not None
    assert row["raw_value"] == LANDING


def test_find_directory_url_records_review_item_when_link_missing(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=LANDING, text="<html>no csv link here</html>")
    with _client(settings, conn) as client:
        assert cqc_bulk.find_directory_url(client, conn, "m26_cqc_directory") is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE module='m26_cqc_directory' "
        "AND item_type='cqc_bulk_export_fetch_failed'"
    ).fetchone()["c"] == 1


# --- parse_directory_csv --------------------------------------------------------

def test_parse_directory_csv_returns_one_row_per_location(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([
        ["CHART Kirklees", "", "3 Wellington Street,Dewsbury", "WF13 1LY", "", "", "types",
         "14/Apr/2022 - 00:00", "", "Change, Grow, Live", "Kirklees", "Yorkshire & Humberside",
         "url", "1-10559211016", "1-125892604"],
    ]))
    with _client(settings, conn) as client:
        rows = cqc_bulk.parse_directory_csv(client, conn, "m05_cqc", CSV_URL)
    assert rows == [cqc_bulk.DirectoryRow(
        location_id="1-10559211016", location_name="CHART Kirklees",
        provider_id="1-125892604", provider_name="Change, Grow, Live")]


def test_parse_directory_csv_records_review_item_on_fetch_failure(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, status_code=404)
    with _client(settings, conn) as client:
        assert cqc_bulk.parse_directory_csv(client, conn, "m05_cqc", CSV_URL) is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='cqc_bulk_export_fetch_failed'"
    ).fetchone()["c"] == 1


def test_parse_directory_csv_records_review_item_when_header_missing(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, content=b"not,a,directory,file\r\n1,2,3,4\r\n")
    with _client(settings, conn) as client:
        assert cqc_bulk.parse_directory_csv(client, conn, "m05_cqc", CSV_URL) is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='cqc_bulk_export_unreadable'"
    ).fetchone()["c"] == 1


def _old_parse_directory_csv(body: bytes) -> list[cqc_bulk.DirectoryRow] | None:
    """The pre-refactor decode-then-StringIO-then-list approach, kept only as
    a reference implementation for test_parse_directory_csv_matches_old_full_decode_approach
    -- proof the streaming rewrite in pipeline.cqc_bulk did not change output,
    not something to keep in sync with the real function otherwise.
    """
    rows = list(csv.reader(io.StringIO(body.decode("utf-8", errors="replace"))))
    header = cqc_bulk._find_header(rows[:10], cqc_bulk.LOCATION_ID_COLUMN)
    if header is None:
        return None
    header_idx, col = header
    required = ("Name", "Provider name", cqc_bulk.LOCATION_ID_COLUMN, cqc_bulk.PROVIDER_ID_COLUMN)
    if not all(name in col for name in required):
        return None
    width = max(col[name] for name in required)

    out: list[cqc_bulk.DirectoryRow] = []
    for data_row in rows[header_idx + 1:]:
        if len(data_row) <= width:
            continue
        location_id = data_row[col[cqc_bulk.LOCATION_ID_COLUMN]]
        provider_id = data_row[col[cqc_bulk.PROVIDER_ID_COLUMN]]
        if not location_id or not provider_id:
            continue
        out.append(cqc_bulk.DirectoryRow(
            location_id=location_id,
            location_name=data_row[col["Name"]],
            provider_id=provider_id,
            provider_name=data_row[col["Provider name"]],
        ))
    return out


def test_parse_directory_csv_matches_old_full_decode_approach(httpx_mock, settings, conn):
    # _csv_body already puts the real header on row 4, after four preamble
    # rows -- exercising the same "peek past the preamble, then stream" split
    # the refactor introduces between the header search and the data pass.
    body = _csv_body([
        ["CHART Kirklees", "", "3 Wellington Street,Dewsbury", "WF13 1LY", "", "", "types",
         "14/Apr/2022 - 00:00", "", "Change, Grow, Live", "Kirklees", "Yorkshire & Humberside",
         "url", "1-10559211016", "1-125892604"],
        ["Some Service", "", "addr", "AB1 2CD", "", "", "types", "", "", "Some Provider",
         "Somewhere", "Region", "url", "", "1-88888"],  # no location id: skipped either way
        ["Other Service", "", "addr2", "CD3 4EF", "", "", "types", "", "", "Other Provider",
         "Elsewhere", "Region", "url2", "1-22222", "1-99999"],
    ])
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, content=body)
    with _client(settings, conn) as client:
        rows = cqc_bulk.parse_directory_csv(client, conn, "m05_cqc", CSV_URL)
    assert rows == _old_parse_directory_csv(body)
    assert len(rows) == 2  # sanity: the no-location-id row was actually skipped


def test_parse_directory_csv_skips_rows_with_no_location_or_provider_id(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([
        ["Some Service", "", "addr", "AB1 2CD", "", "", "types", "", "", "Some Provider",
         "Somewhere", "Region", "url", "", "1-88888"],  # no location id
    ]))
    with _client(settings, conn) as client:
        rows = cqc_bulk.parse_directory_csv(client, conn, "m05_cqc", CSV_URL)
    assert rows == []


# --- fetch_directory_rows (both steps together) ---------------------------------

def test_fetch_directory_rows_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=LANDING, text=LANDING_HTML)
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([
        ["CHART Kirklees", "", "addr", "WF13 1LY", "", "", "types", "", "",
         "Change, Grow, Live", "Kirklees", "Region", "url", "1-10559211016", "1-125892604"],
    ]))
    with _client(settings, conn) as client:
        rows = cqc_bulk.fetch_directory_rows(client, conn, "m05_cqc")
    assert len(rows) == 1
    assert rows[0].provider_id == "1-125892604"


def test_fetch_directory_rows_returns_none_when_the_link_cannot_be_found(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=LANDING, status_code=404)
    with _client(settings, conn) as client:
        assert cqc_bulk.fetch_directory_rows(client, conn, "m05_cqc") is None
