from __future__ import annotations

import pytest

from pipeline.modules import m07_ndtms as ndtms


# --- publication title parsing ------------------------------------------------

@pytest.mark.parametrize("title,expected", [
    ("Substance misuse treatment for adults: statistics 2024 to 2025", ("adults", "2024-25")),
    ("Substance misuse treatment for young people: statistics 2021 to 2022",
     ("young_people", "2021-22")),
])
def test_parse_publication_title(title, expected):
    assert ndtms.parse_publication_title(title) == expected


@pytest.mark.parametrize("title", [
    # a different population the brief does not ask for; must not be swept in
    "Substance misuse treatment in secure settings: 2023 to 2024",
    "Alcohol and drug misuse prevention, treatment and recovery guidance",
    "",
])
def test_parse_publication_title_rejects_other_publications(title):
    assert ndtms.parse_publication_title(title) is None


# --- area name normalisation ----------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("Barking and Dagenham", "barking and dagenham"),
    ("Bath and North East Somerset", "bath and north east somerset"),
    ("Bristol City Council", "bristol"),
    ("Kent County Council", "kent"),
])
def test_normalise_area_name(raw, expected):
    assert ndtms.normalise_area_name(raw) == expected


@pytest.mark.parametrize("published,ons_name", [
    ("Bedford Borough", "Bedford"),
    ("Cheshire East UA", "Cheshire East"),
    ("Cheshire West and Chester UA", "Cheshire West and Chester"),
])
def test_trailing_status_words_normalise_to_the_ons_name(published, ons_name):
    """NDTMS appends a status word ONS omits; stripping it is mechanical."""
    assert ndtms.normalise_area_name(published) == ndtms.normalise_area_name(ons_name)


def test_combined_areas_are_not_forced_onto_a_component():
    """"Cornwall & Isles of Scilly" is two ONS authorities reported together;
    it has no single code and must stay unmatched for review.
    """
    combined = ndtms.normalise_area_name("Cornwall & Isles of Scilly")
    assert combined != ndtms.normalise_area_name("Cornwall")
    assert combined != ndtms.normalise_area_name("Isles of Scilly")


def test_ons_style_inverted_names_round_trip():
    """ONS and NDTMS both write "Kingston upon Hull, City of", so the two
    sides normalise to the same string and match — the trailing "City of" is
    deliberately left alone rather than stripped as a council suffix.
    """
    assert (ndtms.normalise_area_name("Kingston upon Hull, City of")
            == ndtms.normalise_area_name("Kingston upon Hull, City of"))
    assert ndtms.normalise_area_name("Kingston upon Hull, City of") == "kingston upon hull city of"


def test_authority_lookup_matches_published_area_names(conn):
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E09000002', 'Barking and Dagenham', 'london_borough', '2020-01-01', 'x', 'x', "
        "'https://example.com', '2020-01-01T00:00:00Z', 200, 'test', 'abc')")
    lookup = ndtms.build_authority_lookup(conn)
    assert lookup[ndtms.normalise_area_name("Barking and Dagenham")] == "E09000002"


# --- LA sheet detection ------------------------------------------------------------

def test_find_header_row_detects_la_sheet():
    """Shape of the real Table 9.2 sheet: title rows, then the header."""
    rows = [
        ["Table 9.2: deaths in drug treatment, by local authority"],
        ["This worksheet contains one table."],
        ["Link back to the index"],
        ["Area name", "Age", "Time period", "Point estimate", "Observed"],
        ["Barnsley", "18+", "April 2022 to March 2025", "1.23", "61"],
    ]
    assert ndtms.find_header_row(rows) == 3


def test_find_header_row_returns_none_for_national_sheet():
    """Most sheets in this publication are national-only; that is not a
    failure and must not be reported as one.
    """
    rows = [
        ["Table 1.1: sex of all people in treatment"],
        ["Sex", "2023 to 2024", "2024 to 2025"],
        ["Male", "100", "110"],
    ]
    assert ndtms.find_header_row(rows) is None


def test_find_header_row_accepts_area_code_header():
    rows = [["x"], ["Area code", "Area name", "Value"], ["E09000002", "Barking", "5"]]
    assert ndtms.find_header_row(rows) == 1


# --- row extraction -------------------------------------------------------------------

def _real_shape_rows():
    return [
        ["Table 9.2: deaths in drug treatment, by local authority"],
        ["Area name", "Age", "Time period", "Point estimate", "Observed"],
        ["Barnsley", "18+", "April 2022 to March 2025", "1.237629579", "61"],
        ["Bedford", "18+", "April 2022 to March 2025", "0.685756696", "24"],
    ]


def test_extract_la_rows_produces_one_row_per_indicator():
    rows = ndtms.extract_la_rows(_real_shape_rows(), 1)
    assert len(rows) == 4  # 2 areas x 2 value columns
    barnsley = [r for r in rows if r["area_name_raw"] == "Barnsley"]
    indicators = {r["indicator"]: r["value"] for r in barnsley}
    assert indicators["Observed"] == 61
    assert indicators["Point estimate"] == pytest.approx(1.237629579)


def test_extract_la_rows_captures_dimensions():
    rows = ndtms.extract_la_rows(_real_shape_rows(), 1)
    assert all(r["age_group"] == "18+" for r in rows)
    assert all(r["time_period"] == "April 2022 to March 2025" for r in rows)


def test_extract_la_rows_keeps_verbatim_text_for_unparseable_values():
    """Statistical disclosure markers ('c', '*') must not silently become 0."""
    rows = [
        ["Area name", "Value"],
        ["Somewhere", "c"],
    ]
    extracted = ndtms.extract_la_rows(rows, 0)
    assert len(extracted) == 1
    assert extracted[0]["value"] is None
    assert extracted[0]["value_text"] == "c"


def test_extract_la_rows_skips_footnote_lines():
    rows = [
        ["Area name", "Value"],
        ["Barnsley", "61"],
        ["Source: NDTMS. Figures are rounded."],
        [""],
    ]
    extracted = ndtms.extract_la_rows(rows, 0)
    assert [r["area_name_raw"] for r in extracted] == ["Barnsley"]


def test_extract_la_rows_handles_percent_and_thousands():
    rows = [["Area name", "Rate"], ["Somewhere", "1,234"], ["Elsewhere", "45%"]]
    extracted = {r["area_name_raw"]: r["value"] for r in ndtms.extract_la_rows(rows, 0)}
    assert extracted["Somewhere"] == 1234
    assert extracted["Elsewhere"] == 45


# --- schema separation ---------------------------------------------------------------

def test_ndtms_tables_are_separate_from_workforce_tables(conn):
    """Service-demand data must not be merged into workforce tables; a
    caseload-per-worker style ratio would combine sources with different
    populations and methods.
    """
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "ndtms_la_statistics" in tables
    assert "workforce_census_metrics" in tables

    ndtms_cols = {r[1] for r in conn.execute("PRAGMA table_info(ndtms_la_statistics)")}
    census_cols = {r[1] for r in conn.execute("PRAGMA table_info(workforce_census_metrics)")}
    # no shared measure columns that would invite a silent join
    assert "wte" not in ndtms_cols
    assert not (ndtms_cols & census_cols) - {
        "source_url", "retrieved_at", "http_status", "source_system", "payload_sha256", "value"}


def test_sheet_inventory_records_national_sheets(conn):
    conn.execute(
        "INSERT INTO ndtms_sheet_inventory (publication_slug, table_ref, sheet_title, "
        "is_local_authority, row_count) VALUES ('/x', 'Table_1_1', 'Sex of all people', 0, 20)")
    row = conn.execute("SELECT * FROM ndtms_sheet_inventory").fetchone()
    assert row["is_local_authority"] == 0
