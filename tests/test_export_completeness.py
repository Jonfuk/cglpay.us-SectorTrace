"""An export is the whole dataset or it says what it is.

W-06: `/api/v1/contracts` answers a page, so it caps at 500 rows and the page
asks for 1,000 of 98,636. The Download CSV beneath that table passed no limit
at all, so it shipped the first 500 rows with nothing in the file admitting it
— a researcher's CSV that looks complete and is 0.5% of the corpus.

The fix has two halves and both are pinned here: the download reads its own
query rather than the page's slice, and the number of rows it holds is written
into the `#` header so the file can be checked against itself long after it has
been separated from the page it came from.

The corpus in these tests is 1,200 notices, which is deliberately larger than
both the 500-row default and the 1,000 the page asks for. A fixture of 400
would pass against the bug.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import threading

import httpx
import pytest

from pipeline.web import public_export, public_queries, queries
from pipeline.web.server import build_server

CORPUS = 1_200
# Deliberately larger than the 50-row `recent` window pfd() draws its table
# from, for the same reason CORPUS is larger than the contracts page's
# window -- a fixture of 40 would pass against the bug this file exists to
# catch.
CORPUS_PFD = 75


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """More notices than any window this portal offers, across two buyers and
    two years, so a filtered export has something to be complete about."""
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, active_from, "
        " first_seen_vintage, last_seen_vintage, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E08000025', 'Birmingham', 'MD', 'West Midlands', '2021-04-01', "
        " '2024', '2026', "
        " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'geo1')")
    conn.executemany(
        "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
        " supplier_name_raw, title, value_core, currency, date_published, "
        " procedure_type, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES (?, ?, ?, 'E08000025', 'A Supplier Ltd', "
        " 'Treatment services', 1000, 'GBP', ?, 'open', "
        " 'https://find.example/api?cursor=x', '2026-08-01T00:00:00Z', 200, "
        " 'find_a_tender', 'abc123')",
        [(f"n{i:05d}", f"ocds-{i}",
          "Birmingham City Council" if i % 2 else "Another Council",
          "2025-06-01" if i % 2 else "2026-06-01")
         for i in range(CORPUS)])
    conn.executemany(
        "INSERT INTO pfd_reports (report_ref, report_date, coroner_area, "
        " categories, report_url, matters_of_concern, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '2026-01-15', 'Birmingham and Solihull', 'Alcohol, drug "
        " and medication related deaths', ?, 'A concern.', "
        " 'https://judiciary.uk/reports', '2026-08-01T00:00:00Z', 200, "
        " 'judiciary_uk', 'pfd1')",
        [(f"2026-{i:04d}", f"https://judiciary.uk/reports/2026-{i:04d}/")
         for i in range(CORPUS_PFD)])
    conn.commit()
    return conn


@pytest.fixture
def ro(warehouse, settings):
    connection = queries.readonly_connection(settings)
    yield connection
    connection.close()


@pytest.fixture
def client(warehouse, settings):
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=30.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _parse(body: str) -> tuple[dict[str, str], list[dict]]:
    """The `#` header as key/value pairs, and the data rows."""
    lines = body.splitlines()
    header = {}
    for index, line in enumerate(lines):
        if not line.startswith("#"):
            break
        key, _, value = line[1:].strip().partition(": ")
        # `licence` repeats, one line per licence the rows can be under.
        header.setdefault(key, value)
    else:  # pragma: no cover - a header with no body is a bug in the fixture
        index = len(lines)
    return header, list(csv.DictReader(io.StringIO("\n".join(lines[index:]))))


# --- the complete download ------------------------------------------------------


def test_the_contracts_export_holds_every_row_and_names_the_count(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "contracts", "format": "csv"})
    assert response.status_code == 200

    header, rows = _parse(response.text)
    assert len(rows) == CORPUS
    assert header["rows"].startswith(f"{CORPUS:,}")
    # And the count in the file is the count the file holds. This is the whole
    # finding: a header saying 98,636 above 500 rows would be worse than the
    # bug it replaced.
    assert f"{len(rows):,}" == header["rows"].split(" ")[0]


def test_the_export_ignores_the_page_limit(client):
    """A `limit` in the query is the page's business. Honouring it on a
    download would put the truncation back one query parameter later."""
    response = client.get(
        "/api/v1/export",
        params={"endpoint": "contracts", "format": "csv", "limit": "10"})
    _, rows = _parse(response.text)
    assert len(rows) == CORPUS


def test_a_filtered_export_is_complete_for_its_filter(client):
    response = client.get(
        "/api/v1/export",
        params={"endpoint": "contracts", "format": "csv", "year_from": "2026"})
    header, rows = _parse(response.text)

    assert len(rows) == CORPUS // 2
    assert header["rows"].startswith(f"{CORPUS // 2:,}")
    assert header["filters_applied"] == "year_from=2026"
    assert {row["date_published"] for row in rows} == {"2026-06-01"}


def test_the_streamed_export_carries_the_same_provenance_as_any_other(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "contracts", "format": "csv"})
    header, _ = _parse(response.text)

    assert response.text.startswith("# SectorTrace export — /api/v1/contracts")
    assert "licence" in header
    assert "docs/CAVEATS.md" in header["note"]
    provenance = json.loads(response.headers["x-provenance"])
    assert provenance["row_count"] == CORPUS
    # Streamed, not built and measured. A Content-Length here would mean the
    # whole corpus was assembled in memory first, which is the thing this path
    # exists to avoid.
    assert response.headers.get("transfer-encoding") == "chunked"
    assert "content-length" not in response.headers


def test_the_export_columns_are_the_columns_the_page_shows(ro):
    """One SELECT feeds both, so a column added for the table reaches the
    download. They were two SELECTs for exactly one commit."""
    windowed = public_queries.contracts(ro, limit=5)["notices"]
    total, streamed = public_queries.all_contract_notices(ro)
    first = next(iter(streamed))

    assert total == CORPUS
    assert list(first) == list(windowed[0])


def test_the_json_export_is_complete_too(client):
    payload = client.get(
        "/api/v1/export",
        params={"endpoint": "contracts", "format": "json"}).json()
    assert len(payload["contracts"]) == CORPUS
    assert payload["_provenance"]["row_count"] == CORPUS


# --- the same fix, for PFD reports (BETA-019) -------------------------------------
#
# pfd()'s own `recent` key is LIMIT 50 for the same reason contracts() windows
# to 500: it is answering a page with other things to show beside the table.
# The download has to read the whole corpus instead, the same way
# all_contract_notices does -- see all_pfd_reports's own docstring.


def test_the_pfd_export_holds_every_row_and_names_the_count(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "pfd", "format": "csv"})
    assert response.status_code == 200

    header, rows = _parse(response.text)
    assert len(rows) == CORPUS_PFD
    assert header["rows"].startswith(f"{CORPUS_PFD:,}")


def test_the_pfd_export_carries_the_pfd_licence(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "pfd", "format": "csv"})
    header, _ = _parse(response.text)
    # OGL v3.0 (m08_pfd_reports) -- not "not recorded", which is what an
    # endpoint missing from licences.ENDPOINT_MODULES would produce.
    assert "Open Government Licence" in header.get("licence", "")


def test_the_pfd_export_columns_are_the_columns_the_page_shows(ro):
    """One SELECT feeds both `recent` and the complete export, the same
    discipline `all_contract_notices` follows and for the same reason: a
    column added for the table should reach the download without a second
    commit remembering to update it."""
    windowed = public_queries.pfd(ro)["recent"]
    total, streamed = public_queries.all_pfd_reports(ro)
    first = next(iter(streamed))

    assert total == CORPUS_PFD
    assert list(first) == list(windowed[0])


def test_the_pfd_json_export_is_complete_too(client):
    payload = client.get(
        "/api/v1/export",
        params={"endpoint": "pfd", "format": "json"}).json()
    assert len(payload["pfd"]) == CORPUS_PFD
    assert payload["_provenance"]["row_count"] == CORPUS_PFD


# --- and the easy path cannot reintroduce it -------------------------------------


def test_to_csv_refuses_a_windowed_endpoint():
    """The truncation came from a caller flattening a page payload. Making
    that raise is what stops the next one doing it again."""
    with pytest.raises(public_export.ExportError, match="windowed"):
        public_export.to_csv([{"notice_id": "n1"}],
                              public_export.provenance("contracts", {}))


def test_a_stream_that_disagrees_with_its_header_refuses_to_finish():
    """The header goes out before the rows are read. If the two disagree the
    file is wrong, and an unterminated response is better than a wrong one."""
    stream = public_export.stream_csv(
        iter([{"a": 1}]), public_export.provenance("contracts", {}), row_count=9)
    with pytest.raises(public_export.ExportError, match="claimed 9 rows"):
        list(stream)


def test_an_empty_export_says_so_rather_than_ending_after_the_header():
    chunks = b"".join(public_export.stream_csv(
        iter([]), public_export.provenance("contracts", {}), row_count=0))
    assert b"# rows: 0" in chunks
    assert b"# no rows matched" in chunks


def test_every_windowed_endpoint_has_a_complete_reader(client):
    """WINDOWED is a list of promises. An endpoint added to it without a
    reader behind it would 500 on download."""
    for endpoint in public_export.WINDOWED:
        response = client.get("/api/v1/export",
                               params={"endpoint": endpoint, "format": "csv"})
        assert response.status_code == 200, f"{endpoint} has no complete reader"
