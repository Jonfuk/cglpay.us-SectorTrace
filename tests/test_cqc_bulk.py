from __future__ import annotations

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
