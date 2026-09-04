from __future__ import annotations

import pytest

from pipeline.exports import PERSONAL_DATA_COLUMNS, guard_columns
from pipeline.modules import m08_pfd_reports as pfd

# Shape of a real judiciary.uk PFD report body, with names replaced.
REAL_SHAPE = """
Date of report : 27/04/2026  Ref : 2026-0285  Deceased name : Alex Roe
Coroner name : Sam Casey  Coroner area : East Riding of Yorkshire and City of Kingston Upon Hull.
This report is being sent to Yorkshire Ambulance Service NHS Trust and NHS Pathways
REGULATION 28 REPORT TO PREVENT FUTURE DEATHS
1. THIS REPORT IS BEING SENT TO:
1. Yorkshire Ambulance Service NHS Trust
2. Change Grow Live
I am also sending this to the family of Alex Roe and Some Care Home.
2. CORONER I am Sam Casey, Assistant Coroner, for the coroner area of East Riding.
5. CORONERS MATTERS OF CONCERN are as follows. (1) Staffing levels on the ward were
insufficient and vacancy rates had been high for some months. (2) Caseload pressures
meant reviews were delayed.
6. ACTION SHOULD BE TAKEN
"""


# --- header parsing -----------------------------------------------------------

def test_parse_header_fields():
    f = pfd.parse_header_fields(REAL_SHAPE)
    assert f["report_ref"] == "2026-0285"
    assert f["deceased_name"] == "Alex Roe"
    assert f["coroner_name"] == "Sam Casey"
    assert f["coroner_area"].startswith("East Riding of Yorkshire")
    assert f["report_date"] == "27/04/2026"


NEWER_SHAPE = """
Date of report: 01/08/2025
 Ref: 2025-0399
 Deceased name: Alex Roe
 Coroners name: Sam Casey
 Coroners Area: Milton Keynes
 Category: Alcohol, drug and medication related deaths | Police related deaths
 This report is being sent to: Central North NHS Trust
"""


def test_parse_header_fields_newer_coroners_spelling():
    """Newer reports write "Coroners name:" / "Coroners Area:" rather than
    "Coroner name :". Matching only the older form left the coroner
    unrecorded on about half of a live 200-report sample.
    """
    f = pfd.parse_header_fields(NEWER_SHAPE)
    assert f["coroner_name"] == "Sam Casey"
    assert f["coroner_area"] == "Milton Keynes"
    assert f["deceased_name"] == "Alex Roe"
    assert f["report_ref"] == "2025-0399"


def test_coroner_area_stops_before_category_field():
    f = pfd.parse_header_fields(NEWER_SHAPE)
    assert "Category" not in (f["coroner_area"] or "")


# --- redaction ------------------------------------------------------------------

def test_redact_name_removes_full_name_and_surname():
    text = "Alex Roe was not reviewed. Roe had been waiting six weeks."
    out = pfd.redact_name(text, "Alex Roe")
    assert "Alex Roe" not in out
    assert "Roe" not in out
    assert "waiting six weeks" in out


def test_redact_name_is_case_insensitive():
    assert "ALEX ROE" not in pfd.redact_name("ALEX ROE died", "Alex Roe")


def test_redact_name_removes_the_forename_used_alone():
    """From the first real PDF this module read: "As a result Kay was not
    referred to a senior medical practitioner". Surname-only redaction
    published the forename, and coroner prose uses it constantly — 1,056 of
    the 1,059 affected reports have one."""
    out = pfd.redact_name(
        "Kay Simmonds was admitted. As a result Kay was not referred.",
        "Kay Simmonds")
    assert "Kay" not in out
    assert "Simmonds" not in out
    assert "was not referred" in out


def test_redact_name_over_redacts_a_forename_that_is_also_a_word():
    """The accepted cost. Eighteen of the affected deceased are called Mark,
    Rose, May, June or Joy, and a sentence about a date loses a word. That is
    the right way round to fail in a corpus of reports into deaths."""
    out = pfd.redact_name("June Smith died in June 2022.", "June Smith")
    assert "June" not in out
    assert out.count("[name redacted]") >= 2


def test_redact_name_leaves_initials_alone():
    """A one or two character part matches far too much to be safe."""
    out = pfd.redact_name("A B Roe was seen. A nurse recorded it.", "A B Roe")
    assert "A nurse recorded it" in out
    assert "Roe" not in out


@pytest.mark.parametrize("placeholder", ["REDACTED", "Redacted", "Unknown", "Withheld"])
def test_redact_name_ignores_placeholders(placeholder):
    """judiciary.uk sometimes withholds the name itself, putting a placeholder
    in the field. Treating that as a name rewrote unrelated text.
    """
    text = "The REDACTED family raised concerns about waiting times."
    assert pfd.redact_name(text, placeholder) == text


@pytest.mark.parametrize("heading", [
    "MATTERS OF CONCERN", "MATTER OF CONCERN", "CONCERNS",
])
def test_matters_heading_variants_are_all_recognised(heading):
    text = f"5. {heading} are as follows. Staffing was inadequate. ACTION SHOULD BE TAKEN"
    matters = pfd.extract_matters_of_concern(text)
    assert matters is not None
    assert "Staffing was inadequate" in matters


def test_redact_name_passthrough_when_nothing_to_redact():
    assert pfd.redact_name("no names here", "Alex Roe") == "no names here"
    assert pfd.redact_name("text", None) == "text"
    assert pfd.redact_name(None, "Alex Roe") is None


def test_parse_header_fields_missing_values_are_none():
    f = pfd.parse_header_fields("nothing structured here")
    assert f["report_ref"] is None
    assert f["coroner_name"] is None


def test_strip_html_unescapes_and_flattens():
    text = pfd.strip_html("<p>Ref&nbsp;: 2026-1<br>Coroner name : A&#8217;B</p>")
    assert "2026-1" in text
    assert "A'B" in text
    assert "<" not in text


# --- recipients ------------------------------------------------------------------

def test_extract_recipients_reads_the_numbered_list():
    recipients = pfd.extract_recipients(REAL_SHAPE)
    assert "Yorkshire Ambulance Service NHS Trust" in recipients
    assert "Change Grow Live" in recipients


def test_extract_recipients_excludes_the_also_sending_aside():
    """"I am also sending this to the family of X and Some Care Home" names
    people and bodies that are not recipients of the report.
    """
    recipients = pfd.extract_recipients(REAL_SHAPE)
    assert not any("family" in r.lower() for r in recipients)
    assert not any("Some Care Home" in r for r in recipients)


def test_extract_recipients_empty_when_section_absent():
    assert pfd.extract_recipients("no such section") == []


# --- matters of concern -------------------------------------------------------------

def test_extract_matters_of_concern_is_verbatim():
    matters = pfd.extract_matters_of_concern(REAL_SHAPE)
    assert "Staffing levels on the ward were" in matters
    assert "Caseload pressures" in matters
    # must stop before the next numbered section
    assert "ACTION SHOULD BE TAKEN" not in matters


def test_extract_matters_of_concern_none_when_absent():
    assert pfd.extract_matters_of_concern("no concerns section") is None


def test_index_concern_terms_counts_watched_words():
    matters = pfd.extract_matters_of_concern(REAL_SHAPE)
    counts = pfd.index_concern_terms(matters)
    assert counts.get("staffing") == 1
    assert counts.get("vacancy") == 1
    assert counts.get("caseload") == 1
    assert "waiting" not in counts


def test_index_concern_terms_empty_for_no_text():
    assert pfd.index_concern_terms("") == {}
    assert pfd.index_concern_terms(None) == {}


# --- provider matching ----------------------------------------------------------------

def test_find_provider_mentions_matches_whole_tokens():
    found = dict(pfd.find_provider_mentions("sent to Change Grow Live and others"))
    assert found.get("change_grow_live") == "Change Grow Live"


@pytest.mark.parametrize("text", [
    "Viaduct Engineering Limited",       # must not match provider "Via"
    "an inclusive approach was taken",    # must not match provider "Inclusion"
    "the CGL app was unavailable",        # bare acronym is excluded entirely
    "",
])
def test_find_provider_mentions_avoids_false_positives(text):
    assert pfd.find_provider_mentions(text) == []


def test_short_acronyms_are_excluded_from_matching():
    """A false positive here would attribute a coroner's report to an
    organisation that had nothing to do with the death.
    """
    assert "cgl" in pfd._UNSAFE_VARIANTS
    assert "via" in pfd._UNSAFE_VARIANTS


# --- personal data boundary --------------------------------------------------------------

def test_public_report_table_has_no_deceased_name_column(conn):
    columns = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'pfd_reports'")}
    assert "deceased_name" not in columns
    assert "page_title_raw" not in columns
    # the coroner is a public official and IS captured
    assert "coroner_name" in columns


def test_full_report_text_is_not_in_the_public_table(conn):
    """Regression: body_text was originally on pfd_reports, and a live sample
    showed the deceased named in the body of every single report — so any
    export touching that column would have leaked a name.
    """
    public_columns = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'pfd_reports'")}
    assert "body_text" not in public_columns

    restricted_columns = {r["column_name"] for r in conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'restricted_pfd_report_text'")}
    assert "body_text" in restricted_columns


def test_no_public_pfd_column_carries_the_deceased_name(conn):
    """End-to-end guard over the real schema: write a report whose body and
    concerns both name the deceased, then assert nothing public contains it.
    """
    name = "Alex Roe"
    matters = pfd.redact_name(f"{name} waited six weeks. Roe was not reviewed.", name)
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, coroner_name, matters_of_concern, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('R9', 'u', 'Sam Casey', %s, 'u', 't', 200, 's', 'h')", (matters,))
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) VALUES ('R9', %s)",
                  (name,))
    conn.execute("INSERT INTO restricted_pfd_report_text (report_ref, body_text) "
                  "VALUES ('R9', %s)", (f"{name} died on a ward.",))

    row = conn.execute("SELECT * FROM pfd_reports WHERE report_ref='R9'").fetchone()
    blob = " ".join(str(v) for v in row.values() if v is not None)
    assert "Alex Roe" not in blob
    assert "Roe" not in blob
    # the restricted copies still hold it, which is the point
    assert conn.execute(
        "SELECT deceased_name FROM restricted_pfd_persons WHERE report_ref='R9'"
    ).fetchone()["deceased_name"] == name


def test_deceased_name_column_is_blocked_from_exports():
    with pytest.raises(ValueError, match="personal data"):
        guard_columns("some_table", ["report_ref", "deceased_name"])


def test_coroner_name_is_exportable():
    """Blocking it would make the field pointless; a coroner is named on the
    face of a published report in a professional capacity.
    """
    assert "coroner_name" not in PERSONAL_DATA_COLUMNS
    guard_columns("pfd_reports", ["report_ref", "coroner_name", "coroner_area"])


def test_cross_report_redaction_removes_third_party_names(conn):
    """A coroner's concerns can name someone who is a *different* report's
    deceased. Per-report redaction cannot see that, and a live run left six
    such names in a public column.
    """
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, matters_of_concern, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('A', 'u', 'The earlier death of Kristopher Tilbury was not reviewed.', "
        "'u','t',200,'s','h')")
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) "
                  "VALUES ('A', 'Someone Else')")
    # Kristopher Tilbury is the deceased of a different report
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, source_url, retrieved_at, "
        "http_status, source_system, payload_sha256) VALUES ('B','u','u','t',200,'s','h')")
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) "
                  "VALUES ('B', 'Kristopher Tilbury')")

    changed = pfd.redact_known_names_across_reports(conn)
    assert changed == 1
    row = conn.execute("SELECT matters_of_concern FROM pfd_reports WHERE report_ref='A'").fetchone()
    assert "Kristopher Tilbury" not in row["matters_of_concern"]
    assert "[name redacted]" in row["matters_of_concern"]


def test_cross_report_redaction_leaves_coroner_names_alone(conn):
    """A coroner may share a name with someone's deceased. Coroners are
    public officials and must not be redacted.
    """
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, coroner_name, matters_of_concern, "
        "source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('A','u','Michael Spencer','Nothing sensitive here.','u','t',200,'s','h')")
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) "
                  "VALUES ('A', 'Michael Spencer')")

    pfd.redact_known_names_across_reports(conn)
    row = conn.execute("SELECT coroner_name FROM pfd_reports WHERE report_ref='A'").fetchone()
    assert row["coroner_name"] == "Michael Spencer"


def test_cross_report_redaction_ignores_placeholders(conn):
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, matters_of_concern, source_url, "
        "retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('A','u','The [REDACTED] family raised concerns.','u','t',200,'s','h')")
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) "
                  "VALUES ('A', '[REDACTED]')")
    assert pfd.redact_known_names_across_reports(conn) == 0


def test_restricted_table_is_discoverable_as_restricted(conn):
    from pipeline import db
    assert "restricted_pfd_persons" in db.restricted_tables(conn)


# --- mention type separation ---------------------------------------------------------------

def test_recipient_and_body_mentions_are_distinct_rows(conn):
    """Being sent a report by a coroner and being named in one are different
    facts; the schema must keep them apart.
    """
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_url, source_url, retrieved_at, http_status, "
        "source_system, payload_sha256) VALUES ('R1', 'u', 'u', 't', 200, 's', 'h')")
    for mention_type in ("recipient", "body_text"):
        conn.execute(
            "INSERT INTO pfd_provider_mentions (report_ref, provider_key, mention_type, matched_name) "
            "VALUES ('R1', 'change_grow_live', %s, 'Change Grow Live')", (mention_type,))
    rows = conn.execute("SELECT mention_type FROM pfd_provider_mentions ORDER BY mention_type").fetchall()
    assert [r["mention_type"] for r in rows] == ["body_text", "recipient"]
