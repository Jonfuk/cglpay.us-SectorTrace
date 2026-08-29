"""The per-authority page (Phase 11: W-13, W-12, W-27, W-17, W-14).

One page per authority is the campaign's own question answered — "what does
my authority get?" — and the phase's pins are that the page must not invent
anything:

  * its figures are the same figures the existing endpoints return (W-13);
  * its coverage ticks agree with the admin health matrix row for row (W-12);
  * its budget drill-down computes no ratio and keeps grant and budget as
    separate payloads (W-27);
  * every authority name resolves through the find-council control (W-17);
  * the map click carries the ONS code (W-14, pinned statically — the suite
    has no JavaScript runtime, and the browser check is a deliberate human
    step, see tests/test_portal_tables.py for the same decision).
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.web import health, public_queries, queries
from pipeline.web.server import build_server

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"

BIRMINGHAM = "E08000025"


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """An authority with evidence of every kind the page renders, plus one
    authority that has none of it."""
    for ons_code, name, kind, region in [
        (BIRMINGHAM, "Birmingham", "metropolitan_district", "West Midlands"),
        ("E10000028", "Staffordshire", "county", "West Midlands"),
        # No public health role, and none of the evidence either.
        ("E07000192", "Cannock Chase", "non_metropolitan_district", "West Midlands"),
    ]:
        conn.execute(
            "INSERT INTO authorities (ons_code, name, type, region, active_from, "
            " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (?, ?, ?, ?, '2021-04-01', '2024', '2026', "
            " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
            (ons_code, name, kind, region))

    for year, status, amount in [("2024-25", "confirmed", 8_000_000),
                                  ("2025-26", "indicative", 8_200_000)]:
        conn.execute(
            "INSERT INTO public_health_grants (ons_code, financial_year, grant_type, "
            " allocation_status, unit, amount, source_column_header, source_document, "
            " source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (?, ?, 'allocation', ?, 'gbp', ?, '2025-26 allocation', 'alloc.xlsx', "
            " 'https://gov.example/g', '2026-08-01T00:00:00Z', 200, 'dhsc', 'y')",
            (BIRMINGHAM, year, status, amount))
        conn.execute(
            "INSERT INTO public_health_grants (ons_code, financial_year, grant_type, "
            " allocation_status, unit, amount, source_column_header, source_document, "
            " source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (?, ?, 'of_which_is_drug_&_alcohol_ring-fenced_funding_total', "
            " 'confirmed', 'gbp', ?, 'ring-fence', 'alloc.xlsx', "
            " 'https://gov.example/g', '2026-08-01T00:00:00Z', 200, 'dhsc', 'y')",
            (BIRMINGHAM, year, 500_000))
    conn.execute(
        "INSERT INTO public_health_grants (ons_code, financial_year, grant_type, "
        " allocation_status, unit, amount, source_column_header, source_document, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('E10000028', '2025-26', 'allocation', 'confirmed', 'gbp', 4000000, "
        " '2025-26 allocation', 'alloc.xlsx', 'https://gov.example/g', "
        " '2026-08-01T00:00:00Z', 200, 'dhsc', 'y')")

    for year, amount in [("2024-25", 9_000_000), ("2025-26", 9_400_000)]:
        conn.execute(
            "INSERT INTO la_revenue_budgets (ons_code, financial_year, line_code, "
            " section, line_number, column_label, amounts_multiplier, amount, "
            " value_text, source_document, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, 'transpblopr', 'Public Health', '271', "
            " 'Public health (operational)', 1000, ?, '9000', 'b.xlsx', "
            " 'https://gov.example/b', '2026-08-01T00:00:00Z', 200, 'mhclg', 'z')",
            (BIRMINGHAM, year, amount))
    conn.execute(
        "INSERT INTO la_revenue_budgets (ons_code, financial_year, line_code, "
        " section, line_number, column_label, amounts_multiplier, amount, "
        " value_text, source_document, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (?, '2025-26', 'eduerl', 'Education Services', '110', "
        " 'Education and early years', 1000, 120000000, '120000', 'b.xlsx', "
        " 'https://gov.example/b', '2026-08-01T00:00:00Z', 200, 'mhclg', 'z')",
        (BIRMINGHAM,))
    # The unparseable-denomination row: amount NULL, verbatim cell kept.
    conn.execute(
        "INSERT INTO la_revenue_budgets (ons_code, financial_year, line_code, "
        " section, line_number, column_label, amounts_multiplier, amount, "
        " value_text, source_document, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (?, '2025-26', 'badline', 'Public Health', '999', "
        " 'Unreadable line', NULL, NULL, 'n/a', 'b.xlsx', "
        " 'https://gov.example/b', '2026-08-01T00:00:00Z', 200, 'mhclg', 'z')",
        (BIRMINGHAM,))

    conn.execute(
        "INSERT INTO fingertips_indicators (indicator_id, indicator_name, topic, "
        " unit, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) "
        "VALUES (92454, 'Numbers in treatment', 'numbers_in_treatment', 'count', "
        " 'https://fingertips.example/i', '2026-08-01T00:00:00Z', 200, 'ohid', 'f')")
    for period, value, lower, upper in [("2023-24", 1200, 1150, 1250),
                                         ("2024-25", 1180, 1130, 1230)]:
        conn.execute(
            "INSERT INTO fingertips_la_values (indicator_id, area_code, area_type_id, "
            " time_period, area_name, ons_code, area_level, value, lower_ci_95, "
            " upper_ci_95, time_period_sortable, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (92454, ?, 102, ?, 'Birmingham', ?, 'local_authority', "
            " ?, ?, ?, ?, 'https://fingertips.example/v', '2026-08-01T00:00:00Z', "
            " 200, 'ohid', 'f')",
            (BIRMINGHAM, period, BIRMINGHAM, value, lower, upper, period))
    conn.execute(
        "INSERT INTO fingertips_la_values (indicator_id, area_code, area_type_id, "
        " time_period, area_name, area_level, value, time_period_sortable, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (92454, 'E92000001', 102, '2024-25', 'England', 'england', 60000, "
        " '2024-25', 'https://fingertips.example/v', '2026-08-01T00:00:00Z', "
        " 200, 'ohid', 'f')")

    conn.execute(
        "INSERT INTO ndtms_publications (publication_slug, cohort, financial_year, "
        " title, sheets_total, sheets_local_authority, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES ('adult_2024-25', 'adults', '2024-25', 'Adult substance misuse', "
        " 44, 1, 'https://ndtms.example/p', '2026-08-01T00:00:00Z', 200, 'ohid', 'n')")
    for indicator, value, value_text in [
        ("Point estimate", 1.36, "1.36"),
        ("Lower bound to confidence interval (CI)", 0.98, "0.98"),
        ("Upper bound to confidence interval (CI)", 1.86, "1.86"),
    ]:
        conn.execute(
            "INSERT INTO ndtms_la_statistics (publication_slug, table_ref, "
            " area_name_raw, ons_code, age_group, time_period, indicator, value, "
            " value_text, cohort, financial_year, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES ('adult_2024-25', 'Table_9_2', 'Birmingham', ?, '18+', "
            " 'April 2022 to March 2025', ?, ?, ?, 'adults', '2024-25', "
            " 'https://ndtms.example/v', '2026-08-01T00:00:00Z', 200, 'ohid', 'n')",
            (BIRMINGHAM, indicator, value, value_text))

    for notice_id, value in [("n1", 4_200_000), ("n2", None)]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, 'Birmingham City Council', ?, 'Supplier Ltd', "
            " 'Treatment services', ?, 'GBP', '2026-03-01', 'open', 'psr', "
            " 'https://find.example/n', '2026-08-01T00:00:00Z', 200, "
            " 'find_a_tender', 'abc123')",
            (notice_id, f"ocds-{notice_id}", BIRMINGHAM, value))

    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_name, registration_status, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('prov1', 'A Provider', 'Registered', 'https://cqc.example/p', "
        " '2026-08-01T00:00:00Z', 200, 'cqc', 'c')")
    conn.execute(
        "INSERT INTO cqc_locations (location_id, provider_id, location_name, "
        " local_authority_raw, local_authority_ons_code, registration_status, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('loc1', 'prov1', 'A regulated service', 'Birmingham', ?, "
        " 'Registered', 'https://cqc.example/l', '2026-08-01T00:00:00Z', "
        " 200, 'cqc', 'c')",
        (BIRMINGHAM,))
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
        " title, confidence, discovered_at, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (?, 'https://birmingham.example/cdp.pdf', 'CDP strategy', 0.8, "
        " '2026-08-01', 'https://birmingham.example/', '2026-08-01T00:00:00Z', "
        " 200, 'm09', 'd')",
        (BIRMINGHAM,))
    conn.execute(
        "INSERT INTO committee_paper_candidates (authority_ons_code, document_url, "
        " report_title, committee_system, discovered_at, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, 'https://birmingham.example/paper.pdf', 'A committee paper', "
        " 'moderngov', '2026-08-01', 'https://birmingham.example/', "
        " '2026-08-01T00:00:00Z', 200, 'm10', 'e')",
        (BIRMINGHAM,))
    conn.execute(
        "INSERT INTO foi_request_candidates (ons_code, candidate_url, title, "
        " discovered_at, discovery_source, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (?, 'https://birmingham.example/foi.pdf', 'An FOI response', "
        " '2026-08-01', 'disclosure_log', 'https://birmingham.example/', "
        " '2026-08-01T00:00:00Z', 200, 'm15', 'q')",
        (BIRMINGHAM,))

    conn.execute(
        "INSERT INTO rough_sleeping_snapshot (ons_code, snapshot_year, count, "
        " count_text, rate_per_100k, rate_text, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) "
        "VALUES (?, 2025, 12, '12', 1.4, '1.4', 'https://gov.example/rs', "
        " '2026-08-01T00:00:00Z', 200, 'mhclg_rough_sleeping', 'r')",
        (BIRMINGHAM,))
    conn.execute(
        "INSERT INTO statutory_homelessness_snapshot (ons_code, quarter_start, "
        " quarter_label, total_initial_assessments, "
        " total_initial_assessments_text, total_owed_duty, total_owed_duty_text, "
        " prevention_duty_owed, prevention_duty_owed_text, relief_duty_owed, "
        " relief_duty_owed_text, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (?, '2026-01-01', 'January to March 2026', 300, '300', 260, "
        " '260', 120, '120', 140, '140', 'https://gov.example/hclic', "
        " '2026-08-01T00:00:00Z', 200, 'mhclg_statutory_homelessness', 's')",
        (BIRMINGHAM,))
    conn.execute(
        "INSERT INTO temporary_accommodation_snapshot (ons_code, quarter_start, "
        " quarter_label, total_households_ta, total_households_ta_text, "
        " households_ta_with_children, children_in_ta, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (?, '2026-01-01', 'January to March 2026', 180, '180', 90, "
        " 160, 'https://gov.example/hclic-ta', '2026-08-01T00:00:00Z', 200, "
        " 'mhclg_temporary_accommodation', 't')",
        (BIRMINGHAM,))
    for measure, value in (("bb_households", "40"),
                            ("bb_households_with_children", "[c]")):
        conn.execute(
            "INSERT INTO temporary_accommodation_breakdowns (ons_code, "
            " quarter_start, quarter_label, measure, unit, households, "
            " households_text, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, '2026-01-01', 'January to March 2026', ?, 'households', "
            " ?, ?, 'https://gov.example/hclic-ta', '2026-08-01T00:00:00Z', "
            " 200, 'mhclg_temporary_accommodation', 't')",
            (BIRMINGHAM, measure,
             int(value) if value.isdigit() else None, value))

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
                           timeout=15.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# --- W-13: the page shows the same figures the existing endpoints return ----


def test_authority_payload_agrees_with_the_existing_endpoints(ro):
    payload = public_queries.authority(ro, BIRMINGHAM)

    # Grant: the allocation figures are the geography endpoint's figures.
    for row in payload["grant"]["rows"]:
        if row["grant_type"] != "allocation":
            continue
        geo = public_queries.geography(ro, metric="grant_total",
                                        year=row["financial_year"])
        value = next(f["value"] for f in geo["features"]
                     if f["ons_code"] == BIRMINGHAM)
        assert row["amount"] == value

    # Budget: the geography budget metric's sums, per year.
    for row in payload["budget"]["rows"]:
        geo = public_queries.geography(ro, metric="budget_public_health",
                                        year=row["financial_year"])
        value = next(f["value"] for f in geo["features"]
                     if f["ons_code"] == BIRMINGHAM)
        assert row["amount"] == value

    # Treatment: the payloads are the endpoints' payloads, re-used rather
    # than re-written. If someone replaces the reuse with a hand-written
    # query, this fails where the two disagree.
    assert payload["treatment"]["fingertips"] == public_queries.fingertips(
        ro, topic="numbers_in_treatment", ons_code=BIRMINGHAM)
    assert payload["treatment"]["ndtms"]["estimates"] == public_queries.ndtms(
        ro, ons_code=BIRMINGHAM)["estimates"]

    # Contracts: the count is the contracts endpoint's count.
    assert payload["contracts"]["total"] == public_queries.contracts(
        ro, buyer_ons_code=BIRMINGHAM)["total"]


# --- comparators (Modules 29-31) ---------------------------------------------

def test_comparators_are_present_and_carry_their_own_caveats(ro):
    payload = public_queries.authority(ro, BIRMINGHAM)
    comparators = payload["comparators"]

    rough_sleeping = comparators["rough_sleeping"]
    assert rough_sleeping["rows"][0]["snapshot_year"] == 2025
    assert rough_sleeping["rows"][0]["count_text"] == "12"
    assert "comparator" in rough_sleeping["caveat"].lower()

    homelessness = comparators["statutory_homelessness"]
    assert homelessness["rows"][0]["quarter_label"] == "January to March 2026"
    assert homelessness["rows"][0]["total_owed_duty"] == 260
    assert "comparator" in homelessness["caveat"].lower()

    ta = comparators["temporary_accommodation"]
    assert ta["rows"][0]["total_households_ta_text"] == "180"
    assert ta["rows"][0]["children_in_ta"] == 160
    assert "comparator" in ta["caveat"].lower()

    # BETA-064: the bed-and-breakfast breakdown, verbatim — a [c] placeholder
    # stays [c] with a NULL number, never 0.
    breakdown = {row["measure"]: row for row in ta["breakdown"]}
    assert breakdown["bb_households"]["households"] == 40
    assert breakdown["bb_households_with_children"]["households"] is None
    assert breakdown["bb_households_with_children"]["households_text"] == "[c]"
    assert breakdown["bb_households"]["unit"] == "households"
    assert "not" in ta["breakdown_caveat"].lower()


def test_comparators_never_combined_or_scored_against_other_evidence():
    """The three comparator caveats must say, in words, that these figures
    are not combined with the authority's own evidence — the entire reason
    Modules 29-31 exist as separate tables rather than joined columns."""
    for key in ("rough_sleeping_comparator", "statutory_homelessness_comparator",
                "temporary_accommodation_comparator"):
        text = public_queries.CAVEATS[key].lower()
        assert "never" in text or "not" in text


def test_an_authority_with_no_comparator_data_gets_empty_rows_not_an_error(ro):
    """Staffordshire has no rough sleeping/homelessness rows in the fixture
    — absence must read as an empty list, not a missing key or an error."""
    payload = public_queries.authority(ro, "E10000028")
    comparators = payload["comparators"]
    assert comparators["rough_sleeping"]["rows"] == []
    assert comparators["statutory_homelessness"]["rows"] == []
    assert comparators["temporary_accommodation"]["rows"] == []
    assert comparators["temporary_accommodation"]["breakdown"] == []


def test_an_authority_with_nothing_returns_the_same_empty_shapes(ro):
    payload = public_queries.authority(ro, "E07000192")

    assert payload["authority"]["name"] == "Cannock Chase"
    assert payload["grant"]["rows"] == []
    assert payload["budget"]["rows"] == []
    assert payload["budget_detail"]["rows"] == []
    assert payload["contracts"]["total"] == 0
    assert all(count == 0 for count in payload["coverage"]["cells"].values())


def test_an_unknown_authority_is_refused(ro):
    with pytest.raises(queries.QueryError, match="No authority"):
        public_queries.authority(ro, "E99999999")


def test_the_route_answers_over_http(client):
    response = client.get(f"/api/v1/authorities/{BIRMINGHAM}")
    assert response.status_code == 200
    assert response.json()["authority"]["name"] == "Birmingham"
    assert "max-age" in response.headers["Cache-Control"]

    # The pattern is pinned: a code that is not a letter plus eight digits
    # is a different route, and routes that do not exist are 404s.
    assert client.get("/api/v1/authorities/nonsense").status_code == 404
    assert client.get(f"/api/v1/authorities/{BIRMINGHAM}0").status_code == 404


# --- W-12: coverage ticks agree with the admin matrix ------------------------


def test_public_coverage_agrees_with_the_admin_matrix_row_for_row(ro):
    admin = health.coverage(ro, tier="upper")
    admin_row = next(a for a in admin["authorities"]
                     if a["ons_code"] == BIRMINGHAM)

    public = public_queries.authority(ro, BIRMINGHAM)["coverage"]["cells"]
    labels = [c["label"] for c in admin["columns"]]

    assert list(public) == labels, "the tick labels are the matrix's labels"
    for label in labels:
        assert public[label] == admin_row["cells"].get(label, 0), (
            f"{label}: the public tick and the admin matrix disagree")


def test_the_coverage_ticks_carry_the_absence_caveat(ro):
    payload = public_queries.authority(ro, BIRMINGHAM)
    assert payload["coverage"]["caveat"]
    assert "absence" in payload["coverage"]["caveat"].lower()


# --- W-27: the drill-down computes no ratio ----------------------------------


def test_budget_drill_down_computes_no_ratio(ro):
    payload = public_queries.authority(ro, BIRMINGHAM)

    # The drill-down rows are exactly the published columns. A derived
    # number — per-capita, deflated, a share of the grant — would appear
    # here as a new key, and there is no key a derived number could hide in.
    expected_columns = {"financial_year", "section", "line_code", "line_number",
                         "column_label", "amounts_multiplier", "amount",
                         "value_text"}
    for row in payload["budget_detail"]["rows"]:
        assert set(row) == expected_columns

    # Grant and budget are separate payload keys, never a combined figure.
    assert set(payload["grant"]) == {"rows", "unit"}
    assert set(payload["budget"]) == {"rows", "unit"}
    assert all("ratio" not in key for key in payload["caveats"])


def test_the_drill_down_keeps_an_unreadable_amount_null(ro):
    rows = public_queries.authority(ro, BIRMINGHAM)["budget_detail"]["rows"]
    unreadable = next(r for r in rows if r["line_code"] == "badline")

    assert unreadable["amount"] is None
    assert unreadable["amounts_multiplier"] is None
    assert unreadable["value_text"] == "n/a"


# --- W-17 and W-14: the entry points -----------------------------------------


def test_every_authority_the_control_navigates_with_has_a_name_and_code(ro):
    """The find-council control navigates with `name` and `ons_code` from
    /api/v1/authorities; an authority the payload cannot name or key cannot
    be reached through it."""
    authorities = public_queries.authorities(ro)
    assert len(authorities) >= 3
    for authority in authorities:
        assert authority["name"]
        assert re.fullmatch(r"[A-Z][0-9]{8}", authority["ons_code"])


def test_the_find_council_control_builds_the_authority_hash(appjs):
    """Static pin of the browser half: the control navigates to
    `#/authorities/{ons_code}` and searches Fuse keys `name` and `ons_code`.
    The behavioural half is a browser check by decision — see the module
    docstring."""
    assert "find-council" in appjs
    assert "keys: ['name', 'ons_code']" in appjs
    assert re.search(r"location\.hash = `#/authorities/\$\{code\}`", appjs)


def test_the_map_click_carries_the_ons_code(geographyjs):
    """W-14: the click target is the authority page, keyed by the boundary's
    own property — so the code the map drew is the code that opens.

    The map click no longer navigates directly; it selects the boundary and
    shows a preview with an "Open authority" link, so this pins the two
    halves of that chain instead — the click handing off the clicked
    boundary's own `ons_code` property, and the resulting link keyed by the
    same code the click passed in."""
    assert "map.on('click', 'authority-fill', (event) => select(event.features?.[0]?.properties?.ons_code))" in geographyjs
    assert "href: `#/authorities/${code}`" in geographyjs


@pytest.fixture(scope="module")
def appjs() -> str:
    return (PORTAL / "app.js").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def geographyjs() -> str:
    return (PORTAL / "js" / "pages" / "geography.js").read_text(encoding="utf-8")
