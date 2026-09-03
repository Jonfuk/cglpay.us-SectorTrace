"""Phase 12 — show what is already collected (W-23, W-26, W-25, W-24).

Four findings, one shape each, and the tests that pin the plan's "verified
by" clauses:

  * W-23 — the value bands are fixed rather than data-derived, and the
    corpus payload carries the three shape charts.
  * W-26 — the funnel counts match the candidate tables and a zero is a
    zero, not an absent key; freshness lists every source table.
  * W-25 — the portal cannot reach either restricted PFD table, and sent
    and named are separate series in the payload.
  * W-24 — the disclosure matrix keeps "not matched" apart from "not
    searched", and the charity share is computed within a single row.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import public_queries


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """A small warehouse exercising every new payload shape."""
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
                  "VALUES ('change_grow_live', 'Change Grow Live', 1, 'Campaign subject.')")
    conn.execute(
        "INSERT INTO authorities (ons_code, name, type, region, geometry_geojson, "
        " active_from, first_seen_vintage, last_seen_vintage, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "('E08000025', 'Birmingham', 'MD', 'West Midlands', "
        " '{\"type\":\"Polygon\",\"coordinates\":[[[0,0],[1,0],[1,1],[0,0]]]}', "
        " '2021-04-01', '2024', '2026', "
        " 'https://ons.example/boundaries', '2026-08-01T00:00:00Z', 200, "
        " 'ons_open_geography_portal', 'geo123')")
    conn.execute("INSERT INTO supplier_aliases (alias_raw, supplier_key, canonical_name) "
                  "VALUES ('Change Grow Live', 'change_grow_live', 'Change Grow Live')")
    conn.execute(
        "INSERT INTO provider_identifiers (provider_key, scheme, identifier, status) "
        "VALUES ('change_grow_live', 'charity_number', '1079327', 'verified'), "
        "       ('change_grow_live', 'company_number', '03861209', 'verified')")

    # --- W-23: a corpus with quarters, bands and an ending notice -----------
    for notice_id, supplier, value, published, date_end in [
        ("n1", "Change Grow Live", 4_200_000, "2026-01-15", "2027-03-31"),
        ("n2", "Someone Else Ltd", 15_000_000, "2026-03-10", "2026-09-30"),
        ("n3", "Big Framework Ltd", 120_000_000_000, "2025-11-02", "2031-01-01"),
        ("n4", "Change Grow Live", 50_000, "2026-06-20", None),
        ("n5", "No Value Yet Ltd", None, "2026-04-05", "2026-12-01"),
    ]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
                " date_end, procedure_type, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (%s, %s, 'Birmingham City Council', 'E08000025', %s, "
                " 'Treatment services', %s, 'GBP', %s, %s, 'open', "
            " 'https://find.example/n', '2026-08-01T00:00:00Z', 200, "
            " 'find_a_tender', 'abc123')",
            (notice_id, f"ocds-{notice_id}", supplier, value, published, date_end))

    # --- W-26: a funnel with one of everything ------------------------------
    conn.execute(
        "INSERT INTO cdp_document_candidates (authority_ons_code, candidate_url, "
        " title, document_type_guess, confidence, discovered_at, discovery_method, "
        " verified, rejected, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES "
        "('E08000025', 'https://birmingham.gov.uk/cdp.pdf', 'CDP strategy', "
        " 'strategy', 0.9, '2026-08-01T00:00:00Z', 'link', 0, 0, "
        " 'https://birmingham.gov.uk/list', '2026-08-01T00:00:00Z', 200, 'm09', 'h1'),"
        "('E08000025', 'https://birmingham.gov.uk/needs.pdf', 'Needs assessment', "
        " 'needs_assessment', 0.8, '2026-08-01T00:00:00Z', 'link', 1, 0, "
        " 'https://birmingham.gov.uk/list', '2026-08-01T00:00:00Z', 200, 'm09', 'h2'),"
        "('E08000025', 'https://birmingham.gov.uk/old.pdf', 'Old document', "
        " NULL, 0.4, '2026-08-01T00:00:00Z', 'link', 0, 1, "
        " 'https://birmingham.gov.uk/list', '2026-08-01T00:00:00Z', 200, 'm09', 'h3')")
    conn.execute(
        "INSERT INTO evidence_promotions (candidate_table, candidate_url, "
        " target_table, target_key, promoted_by, promoted_at, "
        " candidate_context_json) VALUES "
        "('cdp_document_candidates', 'https://birmingham.gov.uk/needs.pdf', "
        " 'cdp_documents', 'E08000025|https://birmingham.gov.uk/needs.pdf', "
        " 'Jon', '2026-08-02T00:00:00Z', '{}')")
    conn.execute(
        "INSERT INTO cdp_documents (authority_ons_code, document_url, "
        " document_type, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES ('E08000025', "
        " 'https://birmingham.gov.uk/needs.pdf', 'needs_assessment', "
        " 'https://birmingham.gov.uk/needs.pdf', '2026-08-02T00:00:00Z', 200, "
        " 'manual', 'h4')")

    # --- W-25: PFD reports, one with concerns and one a stub ----------------
    conn.execute(
        "INSERT INTO pfd_reports (report_ref, report_date, coroner_area, "
        " categories, report_url, matters_of_concern, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "('2026-0001', '10/04/2026', 'Inner North London', 'Hospital', "
        " 'https://judiciary.example/2026-0001', 'The coroner wrote concerns.', "
        " 'https://judiciary.example/list', '2026-08-01T00:00:00Z', 200, "
        " 'judiciary_uk', 'p1'),"
        "('2025-0002', '12 March 2025', 'Shropshire, Telford and Wrekin', "
        " 'Care home', 'https://judiciary.example/2025-0002', NULL, "
        " 'https://judiciary.example/list', '2026-08-01T00:00:00Z', 200, "
        " 'judiciary_uk', 'p2'),"
        "('2024-0003', 'March 2024', NULL, NULL, 'https://judiciary.example/2024-0003', "
        " 'More concerns.', 'https://judiciary.example/list', "
        " '2026-08-01T00:00:00Z', 200, 'judiciary_uk', 'p3')")
    conn.execute(
        "INSERT INTO pfd_concern_terms (report_ref, term, occurrences) VALUES "
        "('2026-0001', 'waiting', 3), ('2024-0003', 'waiting', 2), "
        "('2024-0003', 'staffing', 1)")
    conn.execute(
        "INSERT INTO pfd_provider_mentions (report_ref, provider_key, "
        " mention_type, matched_name) VALUES "
        "('2026-0001', 'change_grow_live', 'recipient', 'Change Grow Live'), "
        "('2025-0002', 'change_grow_live', 'body_text', 'Change Grow Live')")
    conn.execute(
        "INSERT INTO pfd_recipients (report_ref, organisation_name) VALUES "
        "('2026-0001', 'Change Grow Live'), "
        "('2026-0001', 'Birmingham City Council')")
    conn.execute("INSERT INTO restricted_pfd_persons (report_ref, deceased_name) "
                  "VALUES ('2026-0001', 'A Named Person')")
    conn.execute("INSERT INTO restricted_pfd_report_text (report_ref, body_text) "
                  "VALUES ('2026-0001', 'Full text naming the deceased throughout.')")

    # --- Safeguarding Adult Reviews: one board-named PDF, one unread scan ---
    conn.execute(
        "INSERT INTO sar_documents (document_url, document_ext, library_year, "
        " sab_name, has_body_text, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) VALUES "
        "('https://nationalnetwork.example/2026/edward.pdf', '.pdf', 2026, "
        " 'Hertfordshire Safeguarding Adults Board', 1, "
        " 'https://nationalnetwork.example/2026/edward.pdf', "
        " '2026-08-01T00:00:00Z', 200, 'national_sar_library', 's1'),"
        "('https://nationalnetwork.example/2025/hannah.pdf', '.pdf', 2025, "
        " NULL, 0, 'https://nationalnetwork.example/2025/hannah.pdf', "
        " '2026-08-01T00:00:00Z', 200, 'national_sar_library', 's2')")
    conn.execute(
        "INSERT INTO sar_concern_terms (document_url, term, occurrences) VALUES "
        "('https://nationalnetwork.example/2026/edward.pdf', 'staffing', 2)")
    conn.execute(
        "INSERT INTO sar_provider_mentions (document_url, provider_key, matched_name) "
        "VALUES ('https://nationalnetwork.example/2026/edward.pdf', "
        " 'change_grow_live', 'Change Grow Live')")
    conn.execute("INSERT INTO restricted_sar_persons (document_url, title_raw) "
                  "VALUES ('https://nationalnetwork.example/2026/edward.pdf', "
                  " 'HSAB SAR Edward report.pdf')")
    conn.execute("INSERT INTO restricted_sar_report_text (document_url, body_text) "
                  "VALUES ('https://nationalnetwork.example/2026/edward.pdf', "
                  " 'Full text naming the subject throughout.')")

    # --- W-24: cqc inspections, charity finance, disclosure, filings --------
    conn.execute(
        "INSERT INTO cqc_providers (provider_id, provider_key, provider_name, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES ('prov1', 'change_grow_live', 'Change Grow Live', "
        " 'https://cqc.example/prov1', '2026-08-01T00:00:00Z', 200, 'cqc', 'c0')")
    conn.execute(
        "INSERT INTO cqc_locations (location_id, provider_id, provider_key, "
        " location_name, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES "
        "('loc1', 'prov1', 'change_grow_live', 'CGL Birmingham', "
        " 'https://cqc.example/loc1', '2026-08-01T00:00:00Z', 200, 'cqc', 'c1')")
    conn.execute(
        "INSERT INTO cqc_location_reports (location_id, report_link_id, "
        " report_date, first_visit_date, report_uri, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "('loc1', 'r1', '2023-09-12', '2023-08-01', '/reports/guid?stamp', "
        " 'https://cqc.example/reports', '2026-08-01T00:00:00Z', 200, 'cqc', 'c2')")
    conn.execute(
        "INSERT INTO charity_financials (charity_number, financial_year_end, "
        " total_income, total_expenditure, income_from_govt_contracts, "
        " income_from_govt_grants, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) VALUES "
        "('1079327', '2025-03-31', 100000000, 90000000, 70000000, 5000000, "
        " 'https://api.charitycommission.example', '2026-08-01T00:00:00Z', 200, "
        " 'charity_commission', 'f1')")
    conn.execute(
        "INSERT INTO provider_annual_reports (provider_key, financial_year_end, "
        " document_url, source_url, retrieved_at, http_status, source_system, "
        " payload_sha256) VALUES "
        "('change_grow_live', '2024-03-31', 'https://cc.example/2024', "
        " 'https://cc.example', '2026-08-01T00:00:00Z', 200, 'm14', 'a1'), "
        "('change_grow_live', '2025-03-31', 'https://cc.example/2025', "
        " 'https://cc.example', '2026-08-01T00:00:00Z', 200, 'm14', 'a2')")
    conn.execute(
        "INSERT INTO provider_report_disclosure (provider_key, financial_year_end, "
        " topic, matched, pages_matched, search_terms, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "('change_grow_live', '2024-03-31', 'recruitment', 0, 0, "
        " 'recruitment of staff', 'https://cc.example', '2026-08-01T00:00:00Z', "
        " 200, 'm14', 'a3'), "
        "('change_grow_live', '2024-03-31', 'retention', 1, 2, "
        " 'staff retention', 'https://cc.example', '2026-08-01T00:00:00Z', "
        " 200, 'm14', 'a4')")
    conn.execute(
        "INSERT INTO company_filings (company_number, transaction_id, "
        " filing_date, category, description, document_url, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        "('03861209', 't1', '2026-01-19', 'officers', 'appoint-person-director', "
        " 'https://document-api.example/one', 'https://api.company.example', "
        " '2026-08-01T00:00:00Z', 200, 'companies_house', 'ch1')")

    conn.commit()
    return conn


# --- W-23: the contracts corpus gets a shape ---------------------------------


def test_the_value_bands_are_fixed_not_data_derived(warehouse):
    """The bands are a pinned module constant, and the same notice stays in
    the same band whatever filters are applied — a histogram whose buckets
    moved with the filters could not be compared with itself."""
    labels = [label for _lower, _upper, label in public_queries.CONTRACT_VALUE_BANDS]
    assert labels == ["under £10k", "£10k–£100k", "£100k–£1m", "£1m–£10m",
                      "£10m–£100m", "£100m–£1bn", "£1bn and above"]

    full = public_queries.contracts(warehouse)["value_bands"]
    filtered = public_queries.contracts(warehouse, year_from=2026)["value_bands"]

    assert [b["band_label"] for b in full] == labels
    assert [b["band_label"] for b in filtered] == labels
    # The £50k notice is in "£10k–£100k" whether or not the framework notice
    # is in the corpus, and a band nobody falls in renders as 0, not as gone.
    by_label = {b["band_label"]: b["count"] for b in filtered}
    assert by_label["£10k–£100k"] == 1
    assert by_label["£1bn and above"] == 0


def test_the_contracts_payload_carries_the_three_shape_charts(warehouse):
    payload = public_queries.contracts(warehouse)

    quarters = {q["quarter"]: q for q in payload["by_quarter"]}
    assert quarters["2025-Q4"]["count"] == 1
    assert quarters["2026-Q1"]["count"] == 2
    assert quarters["2026-Q1"]["priced"] == 2
    assert quarters["2026-Q2"]["priced"] == 1  # n5 has no value

    runway = payload["ending_soon"]
    assert runway["rows"]  # n1 (2027-03-31) and n2 (2026-09-30) end within it
    assert all(r["count"] for r in runway["rows"])
    assert runway["caveat"]
    assert runway["window_start"] <= "2026-09-30" <= runway["window_end"]
    # The framework notice ends in 2031: outside the window.
    assert not any(r["quarter"].startswith("2031") for r in runway["rows"])

    assert payload["caveats"]["contract_end"]


def test_the_runway_matched_count_is_the_provider_match_floor(warehouse):
    runway = public_queries.contracts(warehouse)["ending_soon"]
    # n1 is matched (Change Grow Live), n2 is not, n5 is not.
    assert sum(r["matched"] for r in runway["rows"]) == 1


# --- W-26: the overview shows the funnel and the freshness -------------------


def test_the_funnel_counts_match_the_candidate_tables(warehouse):
    funnel = public_queries.summary(warehouse)["funnel"]

    assert funnel["discovered"] == 3
    assert funnel["promoted"] == 1
    assert funnel["rejected"] == 1
    assert funnel["undecided"] == 1
    assert funnel["evidence_rows"] == 1
    assert funnel["caveat"]


def test_a_zero_funnel_is_a_zero_not_an_absence(warehouse):
    """The finding's browser check in payload form: with nothing promoted,
    the keys are present and equal to zero — the page cannot render an empty
    chart for them because the numbers are there to draw."""
    funnel = public_queries.summary(warehouse)["funnel"]
    assert funnel["promoted"] == 1  # the fixture promotes one; take it away:
    warehouse.execute("DELETE FROM cdp_documents")
    warehouse.execute("DELETE FROM evidence_promotions")
    warehouse.execute("UPDATE cdp_document_candidates SET verified = 0")
    warehouse.commit()

    funnel = public_queries.summary(warehouse)["funnel"]
    assert funnel["promoted"] == 0
    assert funnel["evidence_rows"] == 0
    assert "promoted" in funnel and funnel["promoted"] is not None


def test_freshness_lists_every_source_table(warehouse):
    payload = public_queries.freshness(warehouse)

    by_table = {t["table_name"]: t for t in payload["tables"]}
    declared = {table for _label, table in public_queries.FRESHNESS_TABLES}
    assert set(by_table) == declared
    # The contracts rows were retrieved at the fixture's stamp.
    assert by_table["contracts"]["retrieved_at"] == "2026-08-01T00:00:00Z"
    assert payload["caveat"]


def test_freshness_includes_the_newer_collection_modules():
    declared = {table for _label, table in public_queries.FRESHNESS_TABLES}
    assert {
        "statutory_pay_rates",
        "living_wage_accreditations",
        "data_gov_uk_datasets",
        "gender_pay_gap_reports",
        "ons_ashe_observations",
        "provider_pay_pages",
        "council_spend_files",
        "skills_for_care_files",
    } <= declared


# --- W-25: PFD becomes visible -----------------------------------------------


def test_pfd_cannot_reach_either_restricted_table():
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["pfd_reports", "restricted_pfd_report_text"])
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["restricted_pfd_persons"])


def test_sent_and_named_are_separate_series_in_the_pfd_payload(warehouse):
    mentions = public_queries.pfd(warehouse)["mentions"]

    assert mentions["sent_to_providers"] == 1
    assert mentions["naming_providers"] == 1
    assert mentions["recipient_organisations"] == 2
    # Separate keys, never one summed series. A summed key would be a third
    # key with the sum of the two, and its absence here is the point.
    assert "sent_to_providers" in mentions
    assert "naming_providers" in mentions
    assert not any(k in mentions for k in ("total", "mentions_total"))


def test_the_pfd_year_chart_carries_the_stub_share(warehouse):
    payload = public_queries.pfd(warehouse)

    assert payload["totals"]["reports"] == 3
    assert payload["totals"]["with_concerns"] == 2
    assert payload["totals"]["stubs"] == 1
    # '10/04/2026' and 'March 2024' and '12 March 2025' all yield their years.
    by_year = {y["year"]: y for y in payload["by_year"]}
    assert by_year[2026]["reports"] == 1
    assert by_year[2025]["reports"] == 1
    assert by_year[2025]["with_concerns"] == 0
    assert by_year[2024]["with_concerns"] == 1

    assert payload["caveats"]["stubs"]


def test_the_pfd_payload_names_no_personal_data_columns(warehouse):
    """The payload carries the coroner's fields and the report's own words —
    and no key that could be a person's name. The restricted tables hold the
    names, and this route never reads them."""
    payload = public_queries.pfd(warehouse)
    keys = {key for row in payload["recent"] for key in row}
    assert "deceased_name" not in keys
    assert "page_title_raw" not in keys
    assert "matters_of_concern" not in keys  # verbatim text stays in the warehouse


# --- Safeguarding Adult Reviews, alongside PFD on the same page --------------


def test_sar_cannot_reach_either_restricted_table():
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["sar_documents", "restricted_sar_report_text"])
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["restricted_sar_persons"])


def test_the_sar_payload_sits_under_the_pfd_payload(warehouse):
    sar = public_queries.pfd(warehouse)["sar"]

    assert sar["totals"]["documents"] == 2
    assert sar["totals"]["with_text"] == 1
    assert sar["totals"]["with_board_name"] == 1

    by_year = {y["year"]: y for y in sar["by_year"]}
    assert by_year[2026]["documents"] == 1
    assert by_year[2026]["with_text"] == 1
    assert by_year[2025]["with_text"] == 0

    boards = {b["sab_name"]: b["documents"] for b in sar["by_board"]}
    assert boards == {"Hertfordshire Safeguarding Adults Board": 1}

    assert sar["mentions"]["naming_providers"] == 1
    terms = {t["term"]: t["occurrences"] for t in sar["concern_terms"]}
    assert terms["staffing"] == 2

    for key in ("scope", "board", "mentions", "terms"):
        assert sar["caveats"][key]


def test_the_sar_payload_names_no_personal_data_columns(warehouse):
    payload = public_queries.pfd(warehouse)["sar"]
    keys = {key for row in payload["recent"] for key in row}
    assert "title_raw" not in keys
    assert "body_text" not in keys


# --- W-24: the provider deep dive gains four sources -------------------------


def test_the_disclosure_matrix_keeps_not_matched_apart_from_not_searched(warehouse):
    disclosure = public_queries.provider_timeline(warehouse, "change_grow_live")[
        "disclosure"]

    gap = next(g for g in disclosure["gaps"]
               if g["financial_year_end"] == "2024-03-31"
               and g["topic"] == "recruitment")
    # Not matched: the terms were searched and did not appear. The view's
    # caveat and the search terms travel with the cell — and a gap never
    # claims a matched flag, because the two states are different facts.
    assert "matched" not in gap
    assert gap["search_terms"] == "recruitment of staff"
    assert gap["caveat"]

    assert any(c["topic"] == "retention" for c in disclosure["disclosed"])
    # 2025-03-31 has an annual report and no disclosure rows at all: never
    # searched, and carrying a document URL rather than search terms.
    not_searched = next(n for n in disclosure["not_searched"]
                        if n["financial_year_end"] == "2025-03-31")
    assert not_searched["document_url"]
    assert "search_terms" not in not_searched

    # A cell can be one of the three, never two.
    gap_keys = {(g["financial_year_end"], g["topic"]) for g in disclosure["gaps"]}
    disclosed_keys = {(c["financial_year_end"], c["topic"])
                      for c in disclosure["disclosed"]}
    assert not gap_keys & disclosed_keys


def test_the_charity_share_is_within_a_single_row(warehouse):
    row = public_queries.provider_timeline(warehouse, "change_grow_live")[
        "charity_finance"][0]

    assert row["govt_contracts_share"] == 0.7
    assert row["govt_grants_share"] == 0.05
    # Both shares are of that row's own income, not of any other figure.
    assert row["govt_contracts_share"] + row["govt_grants_share"] < 1


def test_the_deep_dive_carries_all_four_new_sections(warehouse):
    payload = public_queries.provider_timeline(warehouse, "change_grow_live")

    assert payload["cqc_inspections"][0]["report_date"] == "2023-09-12"
    assert payload["filings"][0]["document_url"].startswith("https://")
    assert payload["caveats"]["cqc_inspection_dates"]
    assert payload["caveats"]["charity_share"]
    assert payload["caveats"]["filing_records"]
    # W-25's half: the mentions with their report details.
    assert payload["pfd_mentions"][0]["report_url"]
    assert payload["caveats"]["pfd_mentions"]
