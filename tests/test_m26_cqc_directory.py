from __future__ import annotations

import io
import zipfile

from pipeline.modules import m26_cqc_directory as directory
from pipeline.registry import ModuleContext

LANDING = "https://www.cqc.org.uk/about-us/transparency/using-cqc-data"
CSV_URL = "https://www.cqc.org.uk/system/files/2026-08/19_August_2026_CQC_directory.csv"
ODS_URL = "https://www.cqc.org.uk/system/files/2026-08/04_August_2026_Latest_ratings.ods"

LANDING_HTML = f"""
<html><body>
<a href="{CSV_URL}">CQC care directory - csv</a>
<a href="{ODS_URL}">Care directory with ratings</a>
</body></html>
"""


def _allow_all_robots(httpx_mock) -> None:
    httpx_mock.add_response(url="https://www.cqc.org.uk/robots.txt", status_code=200, text="",
                             is_reusable=True)


def _seed_provider(conn, provider_id: str = "1-125892604", provider_key: str = "change_grow_live") -> None:
    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_key, provider_name, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, 'Change, Grow, Live', 'https://example.com', "
        "'2026-01-01T00:00:00Z', 200, 'test', 'abc') ON CONFLICT DO NOTHING",
        (provider_id, provider_key))


def _seed_location(conn, location_id: str, provider_id: str = "1-125892604",
                    provider_key: str = "change_grow_live", overall_rating: str | None = "Good",
                    overall_rating_date: str | None = "2019-01-21") -> None:
    _seed_provider(conn, provider_id, provider_key)
    conn.execute(
        "INSERT INTO cqc_locations (location_id, provider_id, provider_key, location_name, "
        "overall_rating, overall_rating_date, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES (?, ?, ?, 'CHART Kirklees', ?, ?, "
        "'https://example.com', '2026-01-01T00:00:00Z', 200, 'test', 'abc')",
        (location_id, provider_id, provider_key, overall_rating, overall_rating_date))


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


def _build_ods(sheets: dict[str, list[list[str]]]) -> bytes:
    """A minimal but structurally real ODS: proper table/table-row/table-cell
    namespaces, a genuinely blank middle cell (repeat=1, no text), and a huge
    trailing padding cell (repeat=200) -- the two shapes _expand_row has to
    tell apart.
    """
    def cell_xml(value: str | None, repeat: int = 1) -> str:
        attr = f' table:number-columns-repeated="{repeat}"' if repeat != 1 else ""
        if value is None or value == "":
            return f'<table:table-cell{attr}/>'
        return f'<table:table-cell{attr}><text:p>{value}</text:p></table:table-cell>'

    def row_xml(cells: list[str]) -> str:
        parts = [cell_xml(c) for c in cells]
        parts.append(cell_xml(None, repeat=200))  # trailing sheet-width padding
        return "<table:table-row>" + "".join(parts) + "</table:table-row>"

    tables = []
    for name, rows in sheets.items():
        rows_xml = "".join(row_xml(r) for r in rows)
        tables.append(f'<table:table table:name="{name}">{rows_xml}</table:table>')

    content = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        '<office:body><office:spreadsheet>' + "".join(tables) + '</office:spreadsheet></office:body>'
        '</office:document-content>'
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.spreadsheet")
        z.writestr("content.xml", content)
    return buf.getvalue()


RATINGS_HEADER = ["Location ID", "Location Name", "Provider Name",
                   "Service / Population Group", "Domain", "Latest Rating", "Publication Date"]


# --- _expand_row: the exact bug caught while building this module ----------

def test_expand_row_holds_the_position_of_a_blank_middle_cell():
    """A blank cell that is NOT the row's trailing padding must still occupy
    its own slot -- collapsing it (an earlier draft of this parser did)
    shifts every later column left by one and silently corrupts every field
    read from it.
    """
    body = _build_ods({"S": [["a", "", "c"]]})
    rows = list(directory.iter_ods_rows(body, "S"))
    assert rows[0][:3] == ["a", "", "c"]


def test_iter_ods_rows_reads_only_the_named_sheet():
    body = _build_ods({
        "README": [["ignore this sheet"]],
        "Locations": [["Location ID", "Location Name"], ["1-1", "Test Location"]],
    })
    rows = list(directory.iter_ods_rows(body, "Locations"))
    assert rows[0][:2] == ["Location ID", "Location Name"]
    assert rows[1][:2] == ["1-1", "Test Location"]


# --- landing-page link discovery --------------------------------------------

def test_finds_the_dated_directory_and_ratings_links():
    assert directory.find_link(directory.DIRECTORY_LINK_RE, LANDING_HTML) == CSV_URL
    assert directory.find_link(directory.RATINGS_LINK_RE, LANDING_HTML) == ODS_URL


def test_no_link_found_returns_none():
    assert directory.find_link(directory.DIRECTORY_LINK_RE, "<html>nothing here</html>") is None


# --- report scraping: a location's own CQC page ------------------------------

def _location_page_html(report_href: str | None = "/location/1-10559211016/reports/LAP-1/overall",
                         published: str | None = "3 June 2026") -> str:
    """Matches the real markup (both confirmed live): href before class,
    the link text nested in its own <span>, and the publish date in a
    separate sibling <p> with whitespace and a newline around the date."""
    link_block = ""
    if report_href is not None:
        link_block = (
            f'<a data-test="LAP-1-planId-overall" href="{report_href}" '
            f'class="download-report__link"><span class="download-report__text">'
            f'Read the latest assessment report - HTML</span></a>')
    date_block = ""
    if published is not None:
        date_block = (
            f'<p class="download-report__publish-info-date">\n    Published\n'
            f'        {published}\n    </p>')
    return (
        '<div class="overview-download-report"><footer class="download-report">'
        f'<div class="download-report__publish-info"><p class="download-report__publish-info-title">'
        f'{link_block}</p>{date_block}</div></footer></div>')


def test_extract_report_info_parses_a_relative_new_style_link():
    """Confirmed live for a location the API has stopped serving reports
    for (Aspire Havering): CQC's newer path, relative to the site root."""
    uri, date = directory._extract_report_info(_location_page_html())
    assert uri == "https://www.cqc.org.uk/location/1-10559211016/reports/LAP-1/overall"
    assert date == "2026-06-03"


def test_extract_report_info_parses_an_absolute_old_style_link():
    """Confirmed live for a location the API still serves reports for
    (CHART Kirklees): the older api.cqc.org.uk-hosted path, already
    absolute."""
    html = _location_page_html(
        report_href="https://api.cqc.org.uk/public/v1/reports/106534dd-abcd?20220414070037",
        published="14 April 2022")
    uri, date = directory._extract_report_info(html)
    assert uri == "https://api.cqc.org.uk/public/v1/reports/106534dd-abcd?20220414070037"
    assert date == "2022-04-14"


def test_extract_report_info_returns_none_when_nothing_published():
    uri, date = directory._extract_report_info(
        _location_page_html(report_href=None, published=None))
    assert (uri, date) == (None, None)


# --- directory completeness check -------------------------------------------

def test_directory_flags_a_location_missing_from_cqc_locations(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    csv_url = CSV_URL
    httpx_mock.add_response(url=csv_url, content=_csv_body([[
        "CHART Kirklees", "", "3 Wellington Street,Dewsbury", "WF13 1LY", "1924438383", "",
        "Community services - Substance abuse", "14/Apr/2022 - 00:00", "Substance misuse problems",
        "Change, Grow, Live", "Kirklees", "Yorkshire & Humberside",
        "https://www.cqc.org.uk/location/1-10559211016", "1-10559211016", "1-125892604",
    ]]))

    missing = directory._check_directory_completeness(
        _client(settings, conn), conn, "m26_cqc_directory", csv_url, _ctx(settings, conn))

    assert missing == 1
    row = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='cqc_directory_location_missing'").fetchone()
    assert row["raw_value"] == "1-10559211016"
    assert "change_grow_live" in row["context_json"]


def test_directory_does_not_flag_a_location_already_present(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016")
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([[
        "CHART Kirklees", "", "addr", "WF13 1LY", "", "", "types", "14/Apr/2022 - 00:00", "",
        "Change, Grow, Live", "Kirklees", "Yorkshire & Humberside", "url",
        "1-10559211016", "1-125892604",
    ]]))

    missing = directory._check_directory_completeness(
        _client(settings, conn), conn, "m26_cqc_directory", CSV_URL, _ctx(settings, conn))

    assert missing == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='cqc_directory_location_missing'"
    ).fetchone()["c"] == 0


def test_directory_ignores_substring_only_provider_matches(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([[
        "Some Service", "", "addr", "AB1 2CD", "", "", "types", "", "",
        "At Home With You Limited", "Somewhere", "Region", "url", "1-99999", "1-88888",
    ]]))

    missing = directory._check_directory_completeness(
        _client(settings, conn), conn, "m26_cqc_directory", CSV_URL, _ctx(settings, conn))

    assert missing == 0
    assert conn.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 0


# --- ratings currency check --------------------------------------------------

def test_ratings_flags_a_newer_publication_date(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating="Requires improvement",
                    overall_rating_date="2019-01-21")
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "14/04/2022"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    stale = directory._check_ratings_currency(
        _client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    assert stale == 1
    row = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='cqc_directory_rating_stale'").fetchone()
    assert row["raw_value"] == "1-10559211016"
    assert '"directory_rating": "Good"' in row["context_json"]
    assert '"api_overall_rating": "Requires improvement"' in row["context_json"]


LOCATION_URL = "https://www.cqc.org.uk/location/1-10559211016"


def test_ratings_backfills_when_the_api_returned_no_rating_at_all(httpx_mock, settings, conn):
    """Confirmed for real against location 1-12790083928 ('Aspire Havering'):
    a same-day fetch of GET /locations/{id} can return currentRatings.overall
    as null while the bulk export has a real published rating. Re-running
    m05_cqc does not fix that, so this is the one case where the module
    writes to cqc_locations -- into separate bulk_* columns, never into
    overall_rating/overall_rating_date themselves -- and, since the API's
    silence extends to reports too, the one case it also writes a report row.
    """
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating=None, overall_rating_date=None)
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "03/06/2026"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    httpx_mock.add_response(url=LOCATION_URL, text=_location_page_html())
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    stale = directory._check_ratings_currency(
        _client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    assert stale == 0  # backfilled, not flagged as merely stale
    row = conn.execute("SELECT * FROM cqc_locations WHERE location_id='1-10559211016'").fetchone()
    assert row["overall_rating"] is None  # the API's own answer is untouched
    assert row["overall_rating_date"] is None
    assert row["bulk_overall_rating"] == "Good"
    assert row["bulk_overall_rating_date"] == "2026-06-03"
    assert row["bulk_rating_source_url"] == ODS_URL

    review = conn.execute(
        "SELECT * FROM review_queue WHERE item_type='cqc_directory_rating_backfilled'").fetchone()
    assert review["raw_value"] == "1-10559211016"

    report = conn.execute(
        "SELECT * FROM cqc_location_reports WHERE location_id='1-10559211016'").fetchone()
    assert report["report_link_id"] == "bulk_export"
    assert report["report_uri"] == "https://www.cqc.org.uk/location/1-10559211016/reports/LAP-1/overall"
    assert report["report_date"] == "2026-06-03"
    assert report["source_system"] == "cqc_location_page"


def test_ratings_backfill_falls_back_to_the_ods_date_when_the_page_has_none(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating=None, overall_rating_date=None)
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "03/06/2026"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    # A report link with no parseable publish-date block alongside it.
    httpx_mock.add_response(url=LOCATION_URL, text=_location_page_html(published=None))
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    directory._check_ratings_currency(_client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    report = conn.execute(
        "SELECT * FROM cqc_location_reports WHERE location_id='1-10559211016'").fetchone()
    assert report["report_date"] == "2026-06-03"  # the ODS's own publication date


def test_ratings_backfill_still_sets_the_rating_when_the_location_page_fetch_fails(
        httpx_mock, settings, conn):
    """A rating backfill this module is confident about must not be undone
    by an unrelated failure to also fetch the location's own page."""
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating=None, overall_rating_date=None)
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "03/06/2026"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    httpx_mock.add_response(url=LOCATION_URL, status_code=404)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    directory._check_ratings_currency(_client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    row = conn.execute("SELECT * FROM cqc_locations WHERE location_id='1-10559211016'").fetchone()
    assert row["bulk_overall_rating"] == "Good"
    assert conn.execute(
        "SELECT COUNT(*) c FROM cqc_location_reports WHERE location_id='1-10559211016'"
    ).fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type='cqc_location_page_unavailable'"
    ).fetchone()["c"] == 1


def test_ratings_does_not_backfill_when_the_bulk_export_also_has_nothing(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating=None, overall_rating_date=None)
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "", "03/06/2026"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    directory._check_ratings_currency(_client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    row = conn.execute("SELECT * FROM cqc_locations WHERE location_id='1-10559211016'").fetchone()
    assert row["bulk_overall_rating"] is None


def test_ratings_clears_a_backfill_once_the_api_supplies_its_own_rating(httpx_mock, settings, conn):
    """A fallback value left over from when the API was silent must not sit
    beside a real API value forever with nothing marking it stale -- and
    neither must a report row this module scraped in its absence."""
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating="Good", overall_rating_date="2026-07-01")
    conn.execute(
        "UPDATE cqc_locations SET bulk_overall_rating='Good', bulk_overall_rating_date='2026-06-03', "
        "bulk_rating_source_url=?, bulk_rating_retrieved_at='2026-08-20T00:00:00Z' "
        "WHERE location_id='1-10559211016'", (ODS_URL,))
    conn.execute(
        "INSERT INTO cqc_location_reports (location_id, report_link_id, report_date, "
        "first_visit_date, report_uri, source_url, retrieved_at, http_status, source_system, "
        "payload_sha256) VALUES ('1-10559211016', 'bulk_export', '2026-06-03', NULL, ?, ?, "
        "'2026-08-20T00:00:00Z', 200, 'cqc_location_page', 'page123')",
        (LOCATION_URL, LOCATION_URL))
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "03/06/2026"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    directory._check_ratings_currency(_client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    row = conn.execute("SELECT * FROM cqc_locations WHERE location_id='1-10559211016'").fetchone()
    assert row["overall_rating"] == "Good"  # the API's own value, untouched
    assert row["bulk_overall_rating"] is None
    assert row["bulk_overall_rating_date"] is None
    assert row["bulk_rating_source_url"] is None
    assert conn.execute(
        "SELECT COUNT(*) c FROM cqc_location_reports WHERE location_id='1-10559211016' "
        "AND report_link_id='bulk_export'"
    ).fetchone()["c"] == 0


def test_ratings_ignores_non_overall_rows(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating="Good", overall_rating_date="2019-01-21")
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        # A per-service, per-domain breakdown row -- not the location's own rating.
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live",
         "Substance misuse services", "Safe", "Outstanding", "14/04/2022"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    stale = directory._check_ratings_currency(
        _client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    assert stale == 0


def test_ratings_skips_a_location_not_in_cqc_locations_at_all(httpx_mock, settings, conn):
    """Already caught by the completeness check -- flagging it again here
    would just be the same gap reported twice under a different item_type.
    """
    _allow_all_robots(httpx_mock)
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "14/04/2022"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    stale = directory._check_ratings_currency(
        _client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    assert stale == 0
    assert conn.execute("SELECT COUNT(*) c FROM review_queue").fetchone()["c"] == 0


def test_ratings_does_not_flag_an_older_or_equal_publication_date(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating="Good", overall_rating_date="2022-04-14")
    ods = _build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "14/04/2022"],
    ]})
    httpx_mock.add_response(url=ODS_URL, content=ods)
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)

    stale = directory._check_ratings_currency(
        _client(settings, conn), conn, "m26_cqc_directory", ODS_URL, ctx)

    assert stale == 0


# --- end-to-end ---------------------------------------------------------------

def test_run_end_to_end(httpx_mock, settings, conn):
    _allow_all_robots(httpx_mock)
    _seed_location(conn, "1-10559211016", overall_rating="Requires improvement",
                    overall_rating_date="2019-01-21")
    httpx_mock.add_response(url=LANDING, text=LANDING_HTML)
    httpx_mock.add_response(url=CSV_URL, content=_csv_body([
        [  # already in cqc_locations -- ratings-stale, not missing
            "CHART Kirklees", "", "addr", "WF13 1LY", "", "", "types", "14/Apr/2022 - 00:00", "",
            "Change, Grow, Live", "Kirklees", "Yorkshire & Humberside", "url",
            "1-10559211016", "1-125892604",
        ],
        [  # not in cqc_locations -- missing
            "New CGL Service", "", "addr2", "AB1 2CD", "", "", "types", "", "",
            "Change, Grow, Live", "Somewhere", "Region", "url", "1-99999999999", "1-125892604",
        ],
    ]))
    httpx_mock.add_response(url=ODS_URL, content=_build_ods({"Locations": [
        RATINGS_HEADER,
        ["1-10559211016", "CHART Kirklees", "Change, Grow, Live", "Overall", "Overall",
         "Good", "14/04/2022"],
    ]}))

    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    directory.run(ctx)

    missing = conn.execute(
        "SELECT raw_value FROM review_queue WHERE item_type='cqc_directory_location_missing'"
    ).fetchall()
    assert {r["raw_value"] for r in missing} == {"1-99999999999"}

    stale = conn.execute(
        "SELECT raw_value FROM review_queue WHERE item_type='cqc_directory_rating_stale'"
    ).fetchall()
    assert {r["raw_value"] for r in stale} == {"1-10559211016"}


def _client(settings, conn):
    from pipeline.http import PipelineHTTPClient
    return PipelineHTTPClient(directory.SOURCE_SYSTEM, settings=settings, conn=conn)


def _ctx(settings, conn):
    return ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
