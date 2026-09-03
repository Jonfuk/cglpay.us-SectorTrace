"""The compare view (Phase 13: W-11).

"Two authorities on shared axes" is the first thing the portal does that is
an inference, and the pins here are that the inference stays the reader's:

  * every series is the existing endpoint's series, composed rather than
    re-written, so a number here cannot disagree with the page it came from;
  * each series carries the caveat of the layer it came from, and the
    cross-layer caveat that the charts never combine with each other;
  * no series carries a derived number — grant and budget stay separate
    payload keys, and nothing is per-capita, deflated or divided;
  * an unknown or missing entity is refused rather than silently dropped,
    because a comparison that quietly loses an authority is a comparison
    that lies about its own axes.

The browser half — a two-area comparison rendering with the cross-layer
caveat present — is a deliberate human check, the same decision as the
authority page's pins (see the module docstring of test_web_authority.py).
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

import httpx
import pytest

from pipeline.web import public_queries, queries
from pipeline.web.server import build_server

PORTAL = Path(__file__).resolve().parent.parent / "pipeline" / "web" / "static" / "public"

BIRMINGHAM = "E08000025"
STAFFORDSHIRE = "E10000028"


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Two authorities with every authority series, and two providers with
    charity accounts and contracts, so every compare chart has data."""
    for ons_code, name in [(BIRMINGHAM, "Birmingham"), (STAFFORDSHIRE, "Staffordshire")]:
        conn.execute(
            "INSERT INTO authorities (ons_code, name, type, region, active_from, "
            " first_seen_vintage, last_seen_vintage, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (%s, %s, 'county', 'West Midlands', '2021-04-01', '2024', '2026', "
            " 'https://ons.example/b', '2026-08-01T00:00:00Z', 200, 'ons', 'x')",
            (ons_code, name))
        conn.execute(
            "INSERT INTO public_health_grants (ons_code, financial_year, grant_type, "
            " allocation_status, unit, amount, source_column_header, source_document, "
            " source_url, retrieved_at, http_status, source_system, payload_sha256) "
            "VALUES (%s, '2024-25', 'allocation', 'confirmed', 'gbp', %s, 'alloc', "
            " 'alloc.xlsx', 'https://gov.example/g', '2026-08-01T00:00:00Z', 200, "
            " 'dhsc', 'y')",
            (ons_code, 8_000_000 if ons_code == BIRMINGHAM else 4_000_000))
        conn.execute(
            "INSERT INTO la_revenue_budgets (ons_code, financial_year, line_code, "
            " section, line_number, column_label, amounts_multiplier, amount, "
            " value_text, source_document, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (%s, '2024-25', 'transpblopr', 'Public Health', '271', "
            " 'Public health (operational)', 1000, %s, '9000', 'b.xlsx', "
            " 'https://gov.example/b', '2026-08-01T00:00:00Z', 200, 'mhclg', 'z')",
            (ons_code, 9_000_000 if ons_code == BIRMINGHAM else 5_000_000))

    conn.execute(
        "INSERT INTO fingertips_indicators (indicator_id, indicator_name, topic, "
        " unit, source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (92454, 'Numbers in treatment', 'numbers_in_treatment', 'count', "
        " 'https://fingertips.example/i', '2026-08-01T00:00:00Z', 200, 'ohid', 'f')")
    for ons_code, value, lower, upper in [
        (BIRMINGHAM, 1200, 1150, 1250), (STAFFORDSHIRE, 900, 860, 940)]:
        conn.execute(
            "INSERT INTO fingertips_la_values (indicator_id, area_code, area_type_id, "
            " time_period, area_name, ons_code, area_level, value, lower_ci_95, "
            " upper_ci_95, time_period_sortable, source_url, retrieved_at, "
            " http_status, source_system, payload_sha256) "
            "VALUES (92454, %s, 102, '2024-25', 'Birmingham', %s, 'local_authority', "
            " %s, %s, %s, '2024-25', 'https://fingertips.example/v', "
            " '2026-08-01T00:00:00Z', 200, 'ohid', 'f')",
            (ons_code, ons_code, value, lower, upper))
    conn.execute(
        "INSERT INTO fingertips_la_values (indicator_id, area_code, area_type_id, "
        " time_period, area_name, area_level, value, time_period_sortable, "
        " source_url, retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (92454, 'E92000001', 102, '2024-25', 'England', 'england', 60000, "
        " '2024-25', 'https://fingertips.example/v', '2026-08-01T00:00:00Z', "
        " 200, 'ohid', 'f')")

    for ons_code, value in [(BIRMINGHAM, 4_200_000), (STAFFORDSHIRE, 1_100_000)]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (%s, %s, 'A Council', %s, 'Supplier Ltd', 'Treatment services', "
            " %s, 'GBP', '2025-06-01', 'open', 0, 'https://find.example/n', "
            " '2026-08-01T00:00:00Z', 200, 'find_a_tender', 'abc123')",
            (f"n-{ons_code}", f"ocds-{ons_code}", ons_code, value))

    for key, name, target in [("change_grow_live", "Change Grow Live", 1),
                              ("turning_point", "Turning Point", 0)]:
        conn.execute(
            "INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
            "VALUES (%s, %s, %s, 'Campaign subject.')",
            (key, name, target))
        conn.execute(
            "INSERT INTO provider_identifiers (provider_key, scheme, identifier, "
            " role, status) "
            "VALUES (%s, 'charity_number', %s, 'registered charity', 'verified')",
            (key, "1000001" if key == "change_grow_live" else "1000002"))
        for year_end, income, expenditure in [("2023-03-31", 20_000_000, 19_000_000),
                                              ("2024-03-31", 21_000_000, 20_500_000)]:
            conn.execute(
                "INSERT INTO charity_financials (charity_number, financial_year_end, "
                " total_income, total_expenditure, source_url, retrieved_at, "
                " http_status, source_system, payload_sha256) "
                "VALUES (%s, %s, %s, %s, 'https://ccew.example/f', "
                " '2026-08-01T00:00:00Z', 200, 'ccew', 'p')",
                ("1000001" if key == "change_grow_live" else "1000002",
                 year_end, income, expenditure))
        conn.execute(
            "INSERT INTO supplier_aliases (alias_raw, supplier_key, canonical_name) "
            "VALUES (%s, %s, %s)", (f"{name} (alias)", key, name))

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


# --- W-11: the series are the existing endpoints' series ----------------------


def test_compare_series_are_the_existing_endpoints_series(ro):
    payload = public_queries.compare(ro, ons_codes=[BIRMINGHAM, STAFFORDSHIRE])
    series = payload["series"]

    for code in (BIRMINGHAM, STAFFORDSHIRE):
        page = public_queries.authority(ro, code)

        # Grant: the allocation rows are the authority page's allocation rows.
        expected = {(r["financial_year"], r["amount"]) for r in page["grant"]["rows"]
                    if r["grant_type"] == "allocation" and r["unit"] == "gbp"}
        got = {(r["financial_year"], r["amount"]) for r in series["grant"]["rows"]
               if r["ons_code"] == code}
        assert got == expected

        # Budget: the authority page's budgeted spend per year.
        expected = {(r["financial_year"], r["amount"]) for r in page["budget"]["rows"]}
        got = {(r["financial_year"], r["amount"]) for r in series["budget"]["rows"]
               if r["ons_code"] == code}
        assert got == expected

        # Treatment: the treatment page's own payload for this authority,
        # indicators, series and England figures included.
        ft = public_queries.fingertips(ro, topic="numbers_in_treatment",
                                       ons_code=code)
        expected = {(r["time_period"], r["value"]) for r in ft["series"]}
        got = {(r["time_period"], r["value"]) for r in series["treatment"]["rows"]
               if r["ons_code"] == code}
        assert got == expected
        assert {i["indicator_id"] for i in series["treatment"]["indicators"]} \
            == {i["indicator_id"] for i in ft["indicators"]}
        assert {(r["time_period"], r["value"]) for r in series["treatment"]["england"]} \
            == {(r["time_period"], r["value"]) for r in ft["england_series"]}

        # Contracts: the contracts endpoint's by_year for this buyer.
        expected = {(r["year"], r["count"], r["value_gbp"])
                    for r in public_queries.contracts(ro, buyer_ons_code=code)["by_year"]}
        got = {(r["year"], r["count"], r["value_gbp"]) for r in series["contracts"]["rows"]
               if r["ons_code"] == code}
        assert got == expected


def test_compare_series_for_providers(ro):
    payload = public_queries.compare(ro, provider_keys=["change_grow_live",
                                                        "turning_point"])
    series = payload["series"]

    # A provider comparison has no authority series — grant, budget and
    # treatment are authority figures a provider cannot be plotted against.
    assert set(series) == {"charity", "provider_contracts"}
    assert not payload["authorities"]

    # Charity: the accounts rows the timeline reads.
    timeline = public_queries.provider_timeline(ro, "change_grow_live")
    expected = {(e["date"], e["value_summary"]) for e in timeline["events"]
                if e["event_type"] == "charity_accounts"}
    got = {(r["financial_year_end"],
            f"Income £{r['total_income'] or 0:,.0f}")
           for r in series["charity"]["rows"]
           if r["provider_key"] == "change_grow_live"}
    assert got == expected

    # Contracts: the contracts endpoint's by_year for this provider.
    expected = {(r["year"], r["count"], r["value_gbp"])
                for r in public_queries.contracts(ro, provider_key="turning_point")["by_year"]}
    got = {(r["year"], r["count"], r["value_gbp"]) for r in series["provider_contracts"]["rows"]
           if r["provider_key"] == "turning_point"}
    assert got == expected


# --- entities are named, and unknown ones are refused -------------------------


def test_compare_names_the_selected_entities(ro):
    payload = public_queries.compare(ro, ons_codes=[BIRMINGHAM],
                                     provider_keys=["change_grow_live"])
    assert payload["authorities"] == [{
        "ons_code": BIRMINGHAM, "name": "Birmingham",
        "region": "West Midlands", "type": "county"}]
    assert payload["providers"] == [{
        "provider_key": "change_grow_live", "canonical_name": "Change Grow Live",
        "is_target": 1}]


def test_compare_requires_an_entity(ro):
    with pytest.raises(queries.QueryError, match="at least one"):
        public_queries.compare(ro)


def test_compare_refuses_unknown_entities(ro):
    with pytest.raises(queries.QueryError, match="No authority"):
        public_queries.compare(ro, ons_codes=["E99999999"])
    with pytest.raises(queries.QueryError, match="No provider"):
        public_queries.compare(ro, provider_keys=["nonesuch"])
    # One known and one unknown: the unknown is named, not silently dropped.
    with pytest.raises(queries.QueryError, match="No authority"):
        public_queries.compare(ro, ons_codes=[BIRMINGHAM, "E99999999"])


# --- no derived numbers, no missing caveats -----------------------------------


def test_no_series_carries_a_derived_number(ro):
    """Each series' rows are exactly the published columns of its own layer.
    There is no key a per-capita, deflated or cross-layer figure could hide
    in, and grant and budget are separate series that never touch."""
    payload = public_queries.compare(ro, ons_codes=[BIRMINGHAM, STAFFORDSHIRE],
                                     provider_keys=["change_grow_live"])
    expected_keys = {
        "grant": {"ons_code", "authority_name", "financial_year",
                  "allocation_status", "amount", "source_url", "retrieved_at",
                  "payload_sha256"},
        "budget": {"ons_code", "authority_name", "financial_year", "amount"},
        "treatment": {"indicator_id", "ons_code", "authority_name", "time_period",
                      "time_period_sortable", "value", "lower_ci_95", "upper_ci_95",
                      "value_note", "source_url", "retrieved_at"},
        "contracts": {"ons_code", "authority_name", "year", "count", "value_gbp"},
        "charity": {"provider_key", "canonical_name", "financial_year_end",
                    "total_income", "total_expenditure", "source_url",
                    "retrieved_at", "payload_sha256"},
        "provider_contracts": {"provider_key", "provider_name", "year", "count",
                               "value_gbp"},
    }
    for key, columns in expected_keys.items():
        for row in payload["series"][key]["rows"]:
            assert set(row) == columns, f"{key}: a row carries a key it should not"

    assert "grant" in payload["series"] and "budget" in payload["series"]
    assert all("ratio" not in key for key in payload["caveats"])


def test_every_series_carries_its_caveat(ro):
    payload = public_queries.compare(ro, ons_codes=[BIRMINGHAM, STAFFORDSHIRE],
                                     provider_keys=["change_grow_live"])
    for key, spec in payload["series"].items():
        if "caveat" in spec:
            assert spec["caveat"], f"{key} has an empty caveat"
        else:
            assert all(spec["caveats"].values()), f"{key} has an empty caveat"
    cross_layer = payload["caveats"]["cross_layer"]
    assert cross_layer
    assert "never" in cross_layer.lower()


# --- over HTTP ----------------------------------------------------------------


def test_the_compare_route_answers_over_http(client):
    response = client.get(
        f"/api/v1/compare?ons_code={BIRMINGHAM}&ons_code={STAFFORDSHIRE}")
    assert response.status_code == 200
    body = response.json()
    assert [a["ons_code"] for a in body["authorities"]] == [BIRMINGHAM, STAFFORDSHIRE]
    assert body["series"]["grant"]["rows"]
    assert "max-age" in response.headers["Cache-Control"]

    # A comparison without entities is refused; one with an unknown code is
    # refused with the code named.
    assert client.get("/api/v1/compare").status_code == 400
    assert client.get(f"/api/v1/compare?ons_code={BIRMINGHAM}&ons_code=E99999999") \
        .status_code == 400


# --- the page is a payload-driven reader of its own URL -----------------------


@pytest.fixture(scope="module")
def comparejs() -> str:
    return (PORTAL / "js" / "pages" / "compare.js").read_text(encoding="utf-8")


def test_the_compare_page_reads_caveats_from_the_payload(comparejs):
    """Every caveat the page pins arrives in the payload: the cross-layer one
    from `caveats.cross_layer`, each chart's from its series. A hardcoded
    caveat text would be a second copy free to drift."""
    assert "data.caveats.cross_layer" in comparejs
    assert "pinnedCaveat(opts.caveat" in comparejs
    assert "pinnedCaveat(data.caveat" in comparejs
    assert "data.series.grant.caveat" in comparejs
    assert "data.series.budget.caveat" in comparejs


def test_the_compare_page_url_is_the_selection(comparejs):
    """The URL is the comparison: `#/compare?ons_code=...&ons_code=...`, with
    the same parameter names the API takes, so a comparison is a shareable
    address and the page never holds selection state the URL does not."""
    assert re.search(r"location\.hash = `#/compare\?\{query\}`", comparejs) or \
        re.search(r"location\.hash = `#/compare", comparejs)
    assert "appendToUrl('ons_code'" in comparejs
    assert "appendToUrl('provider_key'" in comparejs
    assert "location.hash.split('?')[1]" in comparejs
