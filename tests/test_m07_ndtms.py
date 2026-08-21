from __future__ import annotations

import pytest

from pipeline.modules import m07_ndtms as ndtms
from pipeline.modules.m07_ndtms import build_authority_lookup, build_transition_lookup

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


def _add_authority(conn, ons_code: str, name: str, kind: str = "unitary") -> None:
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, active_from, first_seen_vintage, "
        "last_seen_vintage, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, '2020-01-01', 'x', 'x', 'https://example.com', "
        "'2020-01-01T00:00:00Z', 200, 'test', 'abc')", (ons_code, name, kind))


@pytest.fixture
def lookup_conn(conn):
    """The authorities the NDTMS naming problem actually turns on."""
    for code, name in [
        ("E06000023", "Bristol, City of"),
        ("E06000019", "Herefordshire, County of"),
        ("E06000010", "Kingston upon Hull, City of"),
        ("E09000001", "City of London"),
        ("E06000047", "County Durham"),
        ("E06000004", "Stockton-on-Tees"),
        ("E06000033", "Southend-on-Sea"),
        ("E06000052", "Cornwall"),
        ("E06000053", "Isles of Scilly"),
        ("E06000058", "Bournemouth, Christchurch and Poole"),
    ]:
        _add_authority(conn, code, name)
    return conn


@pytest.mark.parametrize("published,expected", [
    ("Bristol", "E06000023"),
    ("Herefordshire", "E06000019"),
    ("Kingston Upon Hull", "E06000010"),
    # The full ONS spelling still resolves — the short form is an additional
    # key, not a replacement. NDTMS publishes both across its sheets.
    ("Kingston upon Hull, City of", "E06000010"),
])
def test_ons_trailing_qualifier_is_an_additional_lookup_key(lookup_conn, published, expected):
    lookup = ndtms.build_authority_lookup(lookup_conn)
    assert lookup.get(ndtms.normalise_area_name(published)) == expected


def test_city_of_london_is_not_reduced_to_london(lookup_conn):
    """The qualifier strip is anchored to the trailing comma form on purpose.
    A leading "City of" is part of the name: reducing E09000001 to "london"
    would file a London borough's figures under the London region, and it
    would do it silently.
    """
    lookup = ndtms.build_authority_lookup(lookup_conn)
    assert lookup[ndtms.normalise_area_name("City of London")] == "E09000001"
    assert "london" not in lookup


@pytest.mark.parametrize("published,expected", [
    ("Durham", "E06000047"),
    ("Stockton", "E06000004"),
    ("Southend", "E06000033"),
])
def test_written_out_aliases_resolve(lookup_conn, published, expected):
    """Three areas where NDTMS's name and the ONS name simply differ. Each is
    written out with its code rather than derived by a rule.
    """
    lookup = ndtms.build_authority_lookup(lookup_conn)
    assert lookup.get(ndtms.normalise_area_name(published)) == expected


@pytest.mark.parametrize("published", [
    "ENGLAND", "England", "National", "North East", "Yorkshire and the Humber",
    # Two authorities reported as one: forcing it onto either component
    # invents a figure for the other.
    "Cornwall and Isles of Scilly", "Cornwall & Isles of Scilly",
    # Abolished in 2019. Resolving these to Bournemouth, Christchurch and
    # Poole would date a figure to a council that did not yet exist.
    "Poole", "Bournemouth",
])
def test_aggregates_and_abolished_areas_stay_unmatched(lookup_conn, published):
    """These are the names the alias map must never grow to cover. NULL plus
    a review item is the correct answer for all of them, not a gap to close.
    """
    lookup = ndtms.build_authority_lookup(lookup_conn)
    assert ndtms.normalise_area_name(published) not in lookup


def test_a_real_name_is_never_shadowed_by_another_authoritys_abbreviation(conn):
    """Every authority's own name is claimed before any shortened form, so an
    authority actually called "Bristol" wins the key over another's
    abbreviation of "Bristol, City of" — whichever order the rows arrive in.
    """
    _add_authority(conn, "E06000023", "Bristol, City of")
    _add_authority(conn, "E99999999", "Bristol")
    lookup = ndtms.build_authority_lookup(conn)
    assert lookup["bristol"] == "E99999999"


# --- lifecycle-suffixed area names ---------------------------------------------------

def _add_successor(conn, predecessor: str, successor: str, overlap: float) -> None:
    conn.execute(
        "INSERT INTO authority_successors (predecessor_code, successor_code, "
        "overlap_fraction, method, transition_from_vintage, transition_to_vintage, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, ?, ?, 'geometry_overlap', 'A', 'B', 'https://example.com', "
        "'2020-01-01T00:00:00Z', 200, 'test', 'abc')", (predecessor, successor, overlap))


@pytest.fixture
def renumbered_conn(conn):
    """Barnsley as the spine actually holds it: two codes for one borough,
    linked by a near-total geometry overlap at the April 2026 renumbering.
    """
    _add_authority(conn, "E08000016", "Barnsley", "metropolitan_district")
    _add_authority(conn, "E08000038", "Barnsley", "metropolitan_district")
    _add_successor(conn, "E08000016", "E08000038", 0.9997)
    return conn


def test_transition_lookup_pairs_the_two_codes(renumbered_conn):
    transitions = build_transition_lookup(renumbered_conn)
    assert transitions["barnsley"] == ("E08000016", "E08000038")


@pytest.mark.parametrize("published,expected", [
    ("Barnsley (discontinued)", "E08000016"),
    ("Barnsley (pre April 2026)", "E08000016"),
    ("Barnsley (from April 2026)", "E08000038"),
])
def test_lifecycle_markers_resolve_through_the_successor_edge(
        renumbered_conn, published, expected):
    """The date in the suffix is not parsed. Which side of the change a name
    is on comes from the marker word; which code that side is comes from
    `authority_successors`.
    """
    lookup = build_authority_lookup(renumbered_conn)
    transitions = build_transition_lookup(renumbered_conn)
    assert ndtms.match_area_name(published, lookup, transitions) == expected


def test_a_plain_name_still_wins_over_lifecycle_handling(renumbered_conn):
    """The ordinary lookup is tried first, so adding this cannot change what
    an unsuffixed name already resolved to.
    """
    lookup = build_authority_lookup(renumbered_conn)
    transitions = build_transition_lookup(renumbered_conn)
    assert ndtms.match_area_name("Barnsley", lookup, transitions) == lookup["barnsley"]


def test_an_unrecognised_marker_is_not_guessed(renumbered_conn):
    """A marker nobody has seen before is a question for a person. Falling
    back to the base name would answer it with whichever code sorted first.
    """
    lookup = build_authority_lookup(renumbered_conn)
    transitions = build_transition_lookup(renumbered_conn)
    assert ndtms.match_area_name("Barnsley (provisional)", lookup, transitions) is None


def test_a_boundary_change_that_moved_land_is_not_treated_as_a_renumbering(conn):
    """Northamptonshire split into two unitaries at 0.45/0.55 overlap. A pair
    like that is a reorganisation, not the same place renumbered, and a figure
    carried across it would be a figure for somewhere else.
    """
    _add_authority(conn, "E10000021", "Northamptonshire")
    _add_authority(conn, "E06000061", "Northamptonshire")
    _add_successor(conn, "E10000021", "E06000061", 0.4179)
    transitions = build_transition_lookup(conn)
    assert "northamptonshire" not in transitions
    lookup = build_authority_lookup(conn)
    assert ndtms.match_area_name(
        "Northamptonshire (discontinued)", lookup, transitions) is None


def test_an_ambiguous_pairing_is_dropped_rather_than_resolved(conn):
    """Three codes under one name with two qualifying edges has no single
    answer, and one invented here would be invisible downstream.
    """
    for code in ("E00000001", "E00000002", "E00000003"):
        _add_authority(conn, code, "Ambiguous")
    _add_successor(conn, "E00000001", "E00000002", 0.999)
    _add_successor(conn, "E00000002", "E00000003", 0.999)
    assert "ambiguous" not in build_transition_lookup(conn)


def test_transition_lookup_ignores_names_holding_a_single_code(lookup_conn):
    """Every authority in this fixture has exactly one code, so there is
    nothing to pair and nothing should be invented.
    """
    assert build_transition_lookup(lookup_conn) == {}


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


# --- two-row / colspan-compressed headers -----------------------------------------

def _two_row_header_shape():
    """The real shape of 2_1_Drug_prevalence in the 2018-19 and 2019-20 adult
    publications: a colspan-compressed group-label row (6 cells; the
    'Number of users' and 'Rate...' cells each cover a further 6-9 real
    columns that do not appear as separate cells here) followed by a row of
    per-column sub-labels, then real data with the full column count.
    """
    return [
        ["Table 2.1: National and local prevalence estimates..."],
        ["Link back to the index"],
        ["https://www.gov.uk/government/publications/opiate-and-crack-cocaine-use-prevalence-estimates-for-local-populations"],
        ["Region", "Local authority", "15-64 population", "Number of users",
         "Rate of use per thousand of the population", ""],
        ["OCU", "Lower bound 95% CI", "Upper bound 95% CI", "Opiates",
         "Lower bound 95% CI", "Upper bound 95% CI", "Crack cocaine",
         "Lower bound 95% CI", "Upper bound 95% CI", "OCU", "Lower bound 95% CI",
         "Upper bound 95% CI", "Opiates", "Lower bound 95% CI", "Upper bound 95% CI",
         "Crack cocaine", "Lower bound 95% CI", "Upper bound 95% CI", ""],
        [""],
        ["East Midlands", "Derby", "164,510", "2,162", "1,672", "2,647", "1,826",
         "1,533", "2,103", "979", "696", "1,281", "13.14", "10.16", "16.09", "11.10",
         "9.32", "12.78", "5.95", "4.23", "7.79", ""],
    ]


def test_find_header_row_still_locates_the_compressed_group_row():
    """The group-label row is still recognisable as *a* header by its area
    column; whether it can be trusted positionally is a separate question.
    """
    assert ndtms.find_header_row(_two_row_header_shape()) == 3


def test_has_reliable_header_false_for_two_row_shape():
    rows = _two_row_header_shape()
    assert ndtms.has_reliable_header(rows, 3) is False


def test_has_reliable_header_true_for_ordinary_single_row_header():
    rows = [
        ["Area name", "Age", "Time period", "Point estimate", "Observed"],
        ["Barnsley", "18+", "April 2022 to March 2025", "1.23", "61"],
    ]
    assert ndtms.has_reliable_header(rows, 0) is True


def test_extract_la_rows_leaves_two_row_header_sheet_unextracted():
    """Regression: the sub-label row was previously read as a data row
    (producing area_name_raw == 'Lower bound 95% CI'), and worse, the real
    area rows below it were silently mis-paired by position -- Derby's
    'Rate of use per thousand of the population' resolved to 1,672, which is
    actually the opiate lower-bound *count* from an unrelated measure group.
    Neither the phantom row nor the mis-paired real rows should be written.
    """
    rows = _two_row_header_shape()
    header_index = ndtms.find_header_row(rows)
    extracted = ndtms.extract_la_rows(rows, header_index)
    assert extracted == []


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
