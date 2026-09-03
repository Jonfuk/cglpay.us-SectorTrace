"""Module 20: gender pay gap reports.

The two disciplines this module exists to keep: a filing is attributed by
company number where one exists and by exact name otherwise (never by
near-miss), and a provider absent from the file is a review item — possibly
out of scope, possibly a missed filing — never a stored zero.
"""
from __future__ import annotations

import re

from pipeline import providers
from pipeline.modules import m20_gender_pay_gap as gpg
from pipeline.registry import ModuleContext

SERVICE = "https://gender-pay-gap.service.gov.uk"
DOWNLOAD = f"{SERVICE}/viewing/download"

HEADER = ("EmployerName,EmployerId,Address,PostCode,CompanyNumber,SicCodes,"
          "DiffMeanHourlyPercent,DiffMedianHourlyPercent,DiffMeanBonusPercent,"
          "DiffMedianBonusPercent,MaleBonusPercent,FemaleBonusPercent,"
          "MaleLowerQuartile,FemaleLowerQuartile,MaleLowerMiddleQuartile,"
          "FemaleLowerMiddleQuartile,MaleUpperMiddleQuartile,"
          "FemaleUpperMiddleQuartile,MaleTopQuartile,FemaleTopQuartile,"
          "CompanyLinkToGPGInfo,ResponsiblePerson,EmployerSize,CurrentName,"
          "SubmittedAfterTheDeadline,DueDate,DateSubmitted")


def _page(*years: int) -> str:
    links = "".join(
        f'<li><a href="/viewing/download-data/{year}" class="govuk-link">'
        f'<span class="govuk-visually-hidden">Download gender pay gap data for'
        f"</span>Reporting year\n{year} to {year + 1}\n({len(str(year))}KB CSV"
        f" file)</a></li>"
        for year in years)
    return f"<html><body><ul>{links}</ul></body></html>"


def _csv(rows: list[str], header: str = HEADER) -> str:
    # No BOM here — the real file ships one, and parse_csv_rows's
    # utf-8-sig decode expects it, so the encode happens at the call site.
    return "\n".join([header, *rows])


def _row(name: str, employer_id: str, company_number: str, mean_hourly: str,
         median_hourly: str, *, current_name: str | None = None,
         size: str = "1000 to 4999", link: str = "") -> str:
    """One filing row, in the file's column order. Blank bonus cells on
    purpose unless the caller cares about them — a blank is not a zero and
    the parser must keep it that way."""
    current = current_name or name
    return (f'"{name}","{employer_id}","1 Some Street","POST CD","{company_number}",'
            f'"86900","{mean_hourly}","{median_hourly}","","","","",'
            f'"20.00","80.00","30.00","70.00","40.00","60.00","50.00","50.00",'
            f'"{link}","Jane Doe","{size}","{current}","False",'
            f'"2018/04/05 00:00:00","2018/03/27 11:42:49"')


def _allow_robots(httpx_mock):
    httpx_mock.add_response(
        url=re.compile(r"https://gender-pay-gap\.service\.gov\.uk/robots\.txt"),
        status_code=200, text="", is_reusable=True)


def _run(conn, settings, httpx_mock):
    ctx = ModuleContext(conn=conn, settings=settings, since=None, dry_run=False, limit=None)
    gpg.run(ctx)


def _add_company_number(conn, provider_key: str, number: str) -> None:
    providers.seed_providers(conn)  # the identifier row references providers
    # CGL's 03861209 (and the other comparators' company numbers) are now
    # seeded verified by seed_providers; a conflict-free insert keeps that row
    # and still inserts the numbers a test invents.
    conn.execute(
        "INSERT INTO provider_identifiers (provider_key, scheme, identifier, "
        "status, role, discovered_by) VALUES (?, 'company_number', ?, "
        "'unverified', 'test', 'm04') ON CONFLICT DO NOTHING",
        (provider_key, providers.normalise_identifier("company_number", number)))


# --- the scope rule and the year list ------------------------------------------

def test_a_year_is_complete_only_once_its_deadline_has_passed():
    from datetime import date

    assert gpg.completed_years([2025, 2024, 2023, 2017], date(2026, 8, 15)) == \
        [2025, 2024, 2023, 2017]
    assert gpg.completed_years([2025, 2026], date(2026, 4, 4)) == []
    assert gpg.completed_years([2025, 2026], date(2026, 4, 5)) == [2025]
    assert gpg.completed_years([2025, 2026], date(2026, 8, 15)) == [2025]


def test_year_labels_are_read_from_the_page_verbatim():
    rows = gpg._year_rows(_page(2017, 2025))
    assert rows == [(2017, "2017 to 2018"), (2025, "2025 to 2026")]


# --- the CSV -------------------------------------------------------------------

def test_parse_csv_rows_handles_quoted_commas_and_embedded_newlines():
    body = _csv([
        '"BRYANSTON SCHOOL","676","Blandford, Dorset","DT11 0PX","00226143",'
        '"85310,\n70229","18.00","28.20","","","0.00","0.00","24.40","75.60",'
        '"50.80","49.20","49.20","50.80","51.50","48.50","https://example.com",'
        '"Nick McRobb (Bursar)","500 to 999","BRYANSTON SCHOOL",'
        '"False","2018/04/05 00:00:00","2018/03/27 11:42:49"',
    ])
    rows = gpg.parse_csv_rows(body.encode("utf-8-sig"))
    assert len(rows) == 1
    assert rows[0]["EmployerName"] == "BRYANSTON SCHOOL"
    assert rows[0]["SicCodes"] == "85310,\n70229"  # the physical line break stays inside the cell
    assert rows[0]["DiffMeanHourlyPercent"] == "18.00"
    assert rows[0]["DiffMedianBonusPercent"] == ""  # blank cells survive as blank
    assert rows[0]["ResponsiblePerson"] == "Nick McRobb (Bursar)"


def test_a_blank_cell_is_null_not_zero():
    assert gpg._number("") is None
    assert gpg._number(" ") is None
    assert gpg._number("2.30") == 2.3
    assert gpg._number("-2.70") == -2.7
    assert gpg._number("0.00") == 0.0
    assert gpg._number("n/a") is None


# --- matching ------------------------------------------------------------------

def test_company_number_matches_are_normalised_on_both_sides(conn, settings, httpx_mock):
    """m04 stores padded numbers; the CSV ships them unpadded. Both go through
    the same normalisation or one company's filing splits in two.
    """
    _allow_robots(httpx_mock)
    _add_company_number(conn, "change_grow_live", "03861209")
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017), is_reusable=True)
    httpx_mock.add_response(
        url=f"{SERVICE}/viewing/download-data/2017",
        text=_csv([_row("Change Grow Live", "100", "3861209", "16.00", "18.00",
                        link="https://cgl.example")]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    row = conn.execute("SELECT * FROM gender_pay_gap_reports").fetchone()
    assert row is not None
    assert row["provider_key"] == "change_grow_live"
    assert row["match_basis"] == "company_number"
    assert row["diff_mean_hourly_percent"] == 16.0
    assert row["diff_median_hourly_percent"] == 18.0
    assert row["diff_mean_bonus_percent"] is None
    assert row["reporting_year_label"] == "2017 to 2018"
    assert row["employer_name"] == "Change Grow Live"
    assert row["employer_size"] == "1000 to 4999"
    assert row["submitted_after_deadline"] == 0
    assert row["current_name"] == "Change Grow Live"


def test_a_name_exact_match_is_the_fallback(conn, settings, httpx_mock):
    """Charities file without a company number; their row matches on the
    reporting name, exact-normalised only."""
    _allow_robots(httpx_mock)
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017), is_reusable=True)
    httpx_mock.add_response(
        url=f"{SERVICE}/viewing/download-data/2017",
        text=_csv([_row("With You", "101", "", "10.00", "12.00")]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    row = conn.execute("SELECT * FROM gender_pay_gap_reports").fetchone()
    assert row["provider_key"] == "with_you"
    assert row["match_basis"] == "name_exact"


def test_a_near_miss_name_is_not_a_filing(conn, settings, httpx_mock):
    """"Viaduct Care" is not Via — the normaliser strips registered suffixes,
    not arbitrary words, and there is no component matching here: a shared
    word is not a shared identity. Nothing means the absence item, not a row.
    """
    _allow_robots(httpx_mock)
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017), is_reusable=True)
    httpx_mock.add_response(
        url=f"{SERVICE}/viewing/download-data/2017",
        text=_csv([_row("Viaduct Care", "102", "", "10.00", "12.00",
                        size="250 to 499")]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    assert conn.execute("SELECT COUNT(*) c FROM gender_pay_gap_reports").fetchone()["c"] == 0
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue WHERE item_type = 'gender_pay_gap_absence'"
    ).fetchone()["c"] == len(providers.SUPPLIER_NAME_VARIANTS)


def test_the_person_who_confirmed_the_figures_is_not_collected(conn, settings, httpx_mock):
    """ResponsiblePerson is personal data and has no column in the table — the
    schema itself is the assertion, so a future editor cannot slip it in
    without noticing."""
    from pipeline import catalog

    columns = {c["name"] for c in catalog.columns_of(conn, "gender_pay_gap_reports")}
    assert "responsible_person" not in columns


def test_absence_is_a_review_item_that_names_the_decision(
        conn, settings, httpx_mock):
    """A provider not in the file may be out of scope (fewer than 250 staff)
    or may not have filed. The item says both are possible and never stores a
    zero gap."""
    _allow_robots(httpx_mock)
    _add_company_number(conn, "change_grow_live", "03861209")
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017), is_reusable=True)
    httpx_mock.add_response(
        url=f"{SERVICE}/viewing/download-data/2017",
        text=_csv([_row("Some Other Employer", "103", "99999999", "1.00", "2.00",
                        size="250 to 499")]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    item = conn.execute(
        "SELECT * FROM review_queue "
        "WHERE item_type = 'gender_pay_gap_absence' AND raw_value = 'change_grow_live 2017'"
    ).fetchone()
    assert item is not None
    assert "out of scope" in item["context_json"]
    assert "03861209" in item["context_json"]  # what was searched is recorded


def test_absent_providers_are_not_named_as_filed_even_when_their_entity_filed(
        conn, settings, httpx_mock):
    """The same provider can have several legal entities in the file. Each
    matched filing is its own row (the employer_id is part of the key), and
    the provider is not reported absent."""
    _allow_robots(httpx_mock)
    _add_company_number(conn, "change_grow_live", "03861209")
    _add_company_number(conn, "change_grow_live", "08123456")
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017), is_reusable=True)
    httpx_mock.add_response(
        url=f"{SERVICE}/viewing/download-data/2017",
        text=_csv([_row("Change Grow Live", "100", "3861209", "16.00", "18.00"),
                   _row("Change Grow Live Services Ltd", "104", "8123456",
                        "1.00", "2.00", size="250 to 499")]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    rows = conn.execute(
        "SELECT employer_id FROM gender_pay_gap_reports "
        "WHERE provider_key = 'change_grow_live' ORDER BY employer_id").fetchall()
    assert [r["employer_id"] for r in rows] == ["100", "104"]
    assert conn.execute(
        "SELECT COUNT(*) c FROM review_queue "
        "WHERE item_type = 'gender_pay_gap_absence' AND raw_value LIKE 'change_grow_live%'"
    ).fetchone()["c"] == 0


def test_the_newest_completed_years_are_fetched(conn, settings, httpx_mock):
    _allow_robots(httpx_mock)
    httpx_mock.add_response(url=DOWNLOAD, text=_page(2017, 2018, 2019), is_reusable=True)
    for year in (2017, 2018, 2019):
        httpx_mock.add_response(
            url=f"{SERVICE}/viewing/download-data/{year}",
            text=_csv([
                '"Nothing Here Ltd","999","1 Street","77777777","86900",'
                '"1.00","2.00","","","0.00","0.00","20.00","80.00","30.00",'
                '"70.00","40.00","60.00","50.00","50.00","","",'
                '"250 to 499","Nothing Here Ltd","False",'
                '"2018/04/05 00:00:00","2018/03/27 11:42:49"',
            ]), is_reusable=True)

    _run(conn, settings, httpx_mock)

    fetched = {str(r.url).split("/")[-1] for r in httpx_mock.get_requests()
               if "/viewing/download-data/" in str(r.url)}
    assert fetched == {"2019", "2018", "2017"}
