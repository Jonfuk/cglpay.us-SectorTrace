"""The public evidence portal's API.

The portal is the copy of this warehouse that gets handed to people outside
the team, so the tests that matter most are about what it refuses to do:
publish personal data, publish a figure without its caveat, or publish a
number the pipeline's own caveats say must not be computed.
"""
from __future__ import annotations

import json
import sqlite3
import threading

import httpx
import pytest

from pipeline.web import public_export, public_queries, queries
from pipeline.web.server import build_server


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    """A small but structurally real warehouse: a provider, an authority, a
    contract, a framework-sized notice, and a personal-data table."""
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target, notes) "
                  "VALUES ('change_grow_live', 'Change Grow Live', 1, 'Campaign subject.')")
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target) "
                  "VALUES ('turning_point', 'Turning Point', 0)")
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

    for notice_id, supplier, value in [
        ("n1", "Change Grow Live", 4_200_000),
        ("n2", "Someone Else Ltd", 15_000_000),
        ("n3", "Big Framework Ltd", 120_000_000_000),
    ]:
        conn.execute(
            "INSERT INTO contracts (notice_id, ocid, buyer_name, buyer_ons_code, "
            " supplier_name_raw, title, value_core, currency, date_published, "
            " procedure_type, psr_basis, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) "
            "VALUES (?, ?, 'Birmingham City Council', 'E08000025', ?, "
            " 'Treatment services', ?, 'GBP', '2026-03-01', 'open', 'psr', "
            " 'https://find.example/n', '2026-08-01T00:00:00Z', 200, "
            " 'find_a_tender', 'abc123')",
            (notice_id, f"ocds-{notice_id}", supplier, value))

    conn.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, workforce_segment, "
        " value, unit, verified, raw_text, source_url, retrieved_at, http_status, "
        " source_system, payload_sha256) "
        "VALUES (2024, 'vacancy_rate', 'all_staff', 7.0, 'percent', 0, "
        " 'Vacancy rate 7.0%', 'https://nhsbn.example/census', "
        " '2026-08-01T00:00:00Z', 200, 'nhs_benchmarking', 'cen123')")

    conn.execute("CREATE TABLE IF NOT EXISTS restricted_people "
                  "(id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO restricted_people (name) VALUES ('A Person')")
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


# --- the guarantee that matters ----------------------------------------------


def test_no_public_query_touches_a_restricted_table(ro):
    """Every function declares the tables it reads and the declaration is
    enforced, so this is a property of the code rather than a claim."""
    public_queries.summary(ro)
    public_queries.providers(ro)
    public_queries.contracts(ro)
    public_queries.pay(ro)
    public_queries.geography(ro, metric="grant_total")
    public_queries.fingertips(ro)
    public_queries.boundaries(ro)
    public_queries.authorities(ro)
    public_queries.authority(ro, "E08000025")


def test_the_guard_actually_refuses_a_restricted_table():
    """If _public() could be handed a restricted table without complaint, every
    test above would be worthless."""
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["restricted_people"])
    with pytest.raises(Exception, match="restricted"):
        public_queries._public(["contracts", "restricted_pfd_persons"])


def test_no_public_endpoint_serves_a_restricted_table(client):
    """Reachability, from the outside. A restricted table must not be
    addressable through the portal's API at all."""
    for path in ["/api/v1/restricted_people", "/api/v1/table/restricted_people",
                  "/api/v1/summary/restricted_people"]:
        assert client.get(path).status_code == 404

    body = json.dumps(client.get("/api/v1/summary").json())
    assert "restricted_" not in body
    assert "A Person" not in body


# --- caveats travel with figures ---------------------------------------------


def test_every_headline_payload_carries_its_caveat(ro):
    assert public_queries.summary(ro)["contracts"]["caveat"]
    assert public_queries.contracts(ro)["caveats"]["value"]
    assert public_queries.pay(ro)["caveats"]["indicative_wage_note"]
    assert public_queries.geography(ro, metric="grant_total")["caveat"]
    assert public_queries.fingertips(ro)["caveat"]


def test_unverified_census_figures_are_marked_as_such(ro):
    """docs/CAVEATS.md says to filter on `verified` before publishing. The
    portal cannot do that unless the API tells it which rows are unverified."""
    summary = public_queries.summary(ro)
    assert summary["workforce"]["all_unverified"] is True
    assert summary["workforce"]["caveat"]

    pay = public_queries.pay(ro)
    assert pay["census_all_unverified"] is True
    assert all(row["verified"] == 0 for row in pay["workforce_census"])


def test_a_partly_checked_census_still_says_so(warehouse, settings):
    """Phase 8 made verification something a person does one figure at a time,
    so partly-checked is the state this corpus will be in for most of its life.

    The chart draws every figure whatever its flag. `census_all_unverified`
    going false the moment one figure was checked would have taken the pinned
    caveat off the other sixty-seven, which is the failure the portal's whole
    "no figure without its caveat" rule exists to prevent.
    """
    from pipeline import census_verify

    warehouse.execute(
        "INSERT INTO workforce_census_metrics (census_year, metric, "
        " workforce_segment, value, unit, verified, raw_text, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) "
        "VALUES (2024, 'turnover_rate', 'all_staff', 19.0, 'percent', 0, "
        " 'a 19% turnover rate for all staff', 'https://nhsbn.example/census', "
        " '2026-08-01T00:00:00Z', 200, 'nhs_benchmarking', 'cen123')")
    warehouse.commit()

    key = census_verify.metric_key(dict(warehouse.execute(
        "SELECT * FROM workforce_census_metrics WHERE metric = 'vacancy_rate'"
    ).fetchone()))
    census_verify.verify(warehouse, key, verified_by="Jon")

    ro = queries.readonly_connection(settings)
    try:
        pay = public_queries.pay(ro)
    finally:
        ro.close()

    assert pay["census_all_unverified"] is False
    assert (pay["census_verified_count"], pay["census_total"]) == (1, 2)
    assert pay["caveats"]["census_partly_verified_note"]


def test_the_comparability_caveat_survives_verification(warehouse, settings):
    """Verified means transcribed correctly. It has never meant comparable, and
    checking every figure in a census round does not make its years
    differenceable — provider participation still varies between rounds and the
    reports still say so themselves (docs/CAVEATS.md).
    """
    from pipeline import census_verify

    key = census_verify.metric_key(dict(warehouse.execute(
        "SELECT * FROM workforce_census_metrics").fetchone()))
    census_verify.verify(warehouse, key, verified_by="Jon")

    ro = queries.readonly_connection(settings)
    try:
        pay = public_queries.pay(ro)
        summary = public_queries.summary(ro)
    finally:
        ro.close()

    # Every figure checked, so the unverified caveat is legitimately gone.
    assert pay["census_verified_count"] == pay["census_total"]
    # This one is not, and must not be.
    assert "must not be used to infer" in pay["caveats"]["census_comparability_note"]
    assert summary["workforce"]["caveat"]


# --- NDTMS: bounds must stay attached to their own estimate --------------------
#
# These figures are modelled estimates published with 95% confidence
# intervals. Pairing a bound to the wrong measure would silently widen or
# narrow somebody's interval, which is a worse failure than showing no
# interval at all -- so the pairing refuses ambiguity rather than resolving it.


def _ndtms_row(**overrides):
    row = {"publication_slug": "/p", "table_ref": "Table_9_2", "ons_code": "E06000001",
            "area_name_raw": "Hartlepool", "authority_name": "Hartlepool",
            "age_group": "18+", "time_period": "April 2022 to March 2025",
            "indicator": "Point estimate", "value": 1.36, "value_text": "1.36",
            "financial_year": "2024-25", "source_url": "https://ndtms.example/x",
            "retrieved_at": "2026-08-12T00:00:00Z"}
    row.update(overrides)
    return row


@pytest.mark.parametrize("indicator, expected", [
    ("Point estimate", ("Point estimate", "point")),
    ("Lower bound to confidence interval (CI)", ("", "lower")),
    ("Upper bound 95% CI", ("", "upper")),
    ("Crack cocaine (number) lower bound 95% CI", ("Crack cocaine (number)", "lower")),
    ("Crack cocaine (rate) upper bound 95% CI", ("Crack cocaine (rate)", "upper")),
    ("15-64 population", ("15-64 population", "point")),
])
def test_a_published_indicator_name_resolves_to_a_measure_and_a_role(indicator, expected):
    assert public_queries._ndtms_role(indicator) == expected


def test_a_suffixed_bound_attaches_to_its_own_measure():
    estimates, _ = public_queries._ndtms_pair([
        _ndtms_row(table_ref="Table_2_1", indicator="Crack cocaine (number)", value=263),
        _ndtms_row(table_ref="Table_2_1",
                    indicator="Crack cocaine (number) lower bound 95% CI", value=161),
        _ndtms_row(table_ref="Table_2_1",
                    indicator="Crack cocaine (number) upper bound 95% CI", value=371),
        _ndtms_row(table_ref="Table_2_1", indicator="Opiate (number)", value=500),
    ])
    by_measure = {e["measure"]: e for e in estimates}

    assert by_measure["Crack cocaine (number)"]["lower"] == 161
    assert by_measure["Crack cocaine (number)"]["upper"] == 371
    assert by_measure["Crack cocaine (number)"]["has_interval"] is True
    # The other measure in the same sheet must not inherit them.
    assert by_measure["Opiate (number)"]["lower"] is None
    assert by_measure["Opiate (number)"]["has_interval"] is False


def test_a_standalone_bound_attaches_to_the_one_point_estimate():
    estimates, _ = public_queries._ndtms_pair([
        _ndtms_row(indicator="Point estimate", value=1.36),
        _ndtms_row(indicator="Lower bound to confidence interval (CI)", value=0.98),
        _ndtms_row(indicator="Upper bound to confidence interval (CI)", value=1.86),
        _ndtms_row(indicator="Observed", value=43),
        _ndtms_row(indicator="Expected", value=31.7),
    ])
    by_measure = {e["measure"]: e for e in estimates}

    assert (by_measure["Point estimate"]["lower"],
             by_measure["Point estimate"]["upper"]) == (0.98, 1.86)
    assert by_measure["Observed"]["has_interval"] is False
    assert by_measure["Expected"]["has_interval"] is False


def test_an_ambiguous_standalone_bound_is_left_unattached():
    """Two measures that could own the bounds means the source did not say
    which, and a confidence interval put on the wrong estimate is invented."""
    estimates, _ = public_queries._ndtms_pair([
        _ndtms_row(indicator="Drug point estimate", value=10),
        _ndtms_row(indicator="Alcohol point estimate", value=20),
        _ndtms_row(indicator="Lower bound 95% CI", value=5),
        _ndtms_row(indicator="Upper bound 95% CI", value=25),
    ])

    assert estimates
    assert all(e["has_interval"] is False for e in estimates)
    assert all(e["lower"] is None and e["upper"] is None for e in estimates)


def test_bounds_do_not_cross_a_period_boundary():
    estimates, _ = public_queries._ndtms_pair([
        _ndtms_row(time_period="April 2021 to March 2024", indicator="Point estimate", value=1.37),
        _ndtms_row(time_period="April 2022 to March 2025", indicator="Point estimate", value=1.36),
        _ndtms_row(time_period="April 2022 to March 2025",
                    indicator="Lower bound to confidence interval (CI)", value=0.98),
        _ndtms_row(time_period="April 2022 to March 2025",
                    indicator="Upper bound to confidence interval (CI)", value=1.86),
    ])
    by_period = {e["time_period"]: e for e in estimates}

    assert by_period["April 2022 to March 2025"]["has_interval"] is True
    assert by_period["April 2021 to March 2024"]["has_interval"] is False


def test_a_suppressed_cell_keeps_its_marker_and_never_becomes_a_number():
    """`c` and `*` are disclosure controls. docs/CAVEATS.md: they do not mean
    zero, so they must not reach a chart as a value at all."""
    estimates, other = public_queries._ndtms_pair([
        _ndtms_row(indicator="Point estimate", value=None, value_text="c"),
    ])

    assert estimates == []
    assert other[0]["value_text"] == "c"
    assert "value" not in other[0]


def test_the_ndtms_endpoint_carries_all_three_of_its_caveats(ro):
    payload = public_queries.ndtms(ro)

    assert payload["caveats"]["estimates"]
    assert payload["caveats"]["coverage"]
    assert payload["caveats"]["suppressed"]
    assert payload["estimates"] == [], "no authority asked for, no rows returned"


# --- the address a reader follows ---------------------------------------------


def test_a_notice_link_is_offered_and_the_provenance_is_left_alone(ro):
    """`source_url` is the API cursor these bytes came from. It is provenance,
    it is not a destination, and for five years it was the only link the
    portal offered."""
    notices = public_queries.contracts(ro)["notices"]
    assert notices

    for notice in notices:
        assert notice["source_url"] == "https://find.example/n", (
            "the provenance column must survive untouched")
        assert notice["notice_link"] == (
            f"https://www.find-tender.service.gov.uk/Notice/{notice['notice_id']}")


def test_a_constructed_link_says_that_it_is_constructed(ro):
    """The fixture rows publish no notice URL of their own, which is the
    ordinary case -- 84% of the collected corpus. The link is still built, and
    still labelled, because a reader about to cite one deserves to know which
    of the two they followed."""
    for notice in public_queries.contracts(ro)["notices"]:
        assert notice["notice_web_url"] is None
        assert notice["notice_link_basis"] == "constructed"


def test_a_published_notice_url_is_preferred_and_marked_as_published(warehouse, settings):
    warehouse.execute(
        "UPDATE contracts SET notice_web_url = "
        "'https://www.find-tender.service.gov.uk/Notice/n1' WHERE notice_id = 'n1'")
    warehouse.commit()

    connection = queries.readonly_connection(settings)
    try:
        notices = {n["notice_id"]: n
                    for n in public_queries.contracts(connection)["notices"]}
    finally:
        connection.close()

    assert notices["n1"]["notice_link_basis"] == "published"
    assert notices["n2"]["notice_link_basis"] == "constructed"


def test_the_export_keeps_its_existing_columns_where_they_were(ro):
    """A CSV consumer who counted columns must not have them move. New fields
    are appended; nothing is inserted before them."""
    from pipeline.web import public_export

    rows, _ = public_export.rows_for("contracts", public_queries.contracts(ro))
    columns = list(rows[0])

    expected_prefix = [
        "notice_id", "title", "buyer_name", "buyer_ons_code", "supplier_name_raw",
        "value_core", "value_max", "currency", "date_published", "date_start",
        "date_end", "procedure_type", "psr_basis", "psr_direct_award_option",
        "source_url", "retrieved_at", "payload_sha256",
    ]
    assert columns[:len(expected_prefix)] == expected_prefix
    assert set(columns[len(expected_prefix):]) == {
        "source_system", "notice_web_url", "notice_link", "notice_link_basis"}


# --- the framework-ceiling problem -------------------------------------------


def test_a_corpus_dominated_by_framework_ceilings_is_reported_as_such(ro):
    """One £120bn framework notice among three makes the sum meaningless. The
    API has to say so, or the portal will headline it."""
    data = public_queries.contracts(ro)
    concentration = data["value_concentration"]

    assert concentration["notices_over_1bn"] == 1
    assert concentration["share_over_1bn"] > 0.99
    assert concentration["median_value_gbp"] == 15_000_000
    # The mean is three orders of magnitude above the middle notice.
    assert concentration["mean_to_median_ratio"] > 100
    assert public_queries.summary(ro)["contracts"]["value_is_concentrated"] is True


def test_a_corpus_without_ceilings_keeps_its_headline(warehouse, settings):
    """The warning is measured per request, so a corpus that does not have the
    problem does not carry the warning."""
    warehouse.execute("DELETE FROM contracts WHERE notice_id = 'n3'")
    warehouse.commit()
    connection = queries.readonly_connection(settings)
    assert public_queries.summary(connection)["contracts"]["value_is_concentrated"] is False
    connection.close()


def test_provider_matching_is_reported_as_a_floor(ro):
    data = public_queries.contracts(ro)
    assert data["matched_to_provider"] == 1
    assert data["total"] == 3
    assert "floor" in data["caveats"]["provider_match"]


# --- shapes the portal depends on --------------------------------------------


def test_geography_returns_one_row_per_authority(ro):
    """A choropleth needs one value per area. Without a year default, these
    queries return a row per authority per year and the map colours each area
    by whichever row was drawn last."""
    data = public_queries.geography(ro, metric="contract_value")
    codes = [f["ons_code"] for f in data["features"]]
    assert len(codes) == len(set(codes))


def test_an_unknown_geography_metric_is_refused(ro):
    with pytest.raises(queries.QueryError, match="Unknown metric"):
        public_queries.geography(ro, metric="whatever_i_like")


def test_boundaries_come_from_the_warehouse_with_provenance(ro):
    geo = public_queries.boundaries(ro)
    assert geo["type"] == "FeatureCollection"
    assert geo["features"][0]["properties"]["ons_code"] == "E08000025"
    assert geo["features"][0]["geometry"]["type"] == "Polygon"
    assert geo["meta"]["source_url"] == "https://ons.example/boundaries"


def test_providers_carry_their_counts(ro):
    providers = {p["provider_key"]: p for p in public_queries.providers(ro)}
    assert providers["change_grow_live"]["is_target"] == 1
    assert providers["change_grow_live"]["contract_count"] == 1
    assert providers["turning_point"]["contract_count"] == 0


def test_an_unknown_provider_timeline_is_refused(ro):
    with pytest.raises(queries.QueryError, match="No provider"):
        public_queries.provider_timeline(ro, "not_a_provider")


# --- over HTTP ----------------------------------------------------------------


def test_the_portal_and_the_operator_ui_are_both_served(client):
    portal = client.get("/")
    admin = client.get("/admin/")
    assert portal.status_code == 200
    assert admin.status_code == 200
    assert "SectorTrace" in portal.text
    assert portal.text != admin.text


def test_public_endpoints_answer(client):
    for path in ["/api/v1/summary", "/api/v1/providers", "/api/v1/contracts",
                  "/api/v1/pay", "/api/v1/geography", "/api/v1/fingertips",
                  "/api/v1/authorities", "/api/v1/boundaries"]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["cache-control"] == "max-age=300, private"


def test_operator_answers_are_never_cached(client):
    """The review queue changes as it is worked on; a cached page would show
    decisions that are not there."""
    assert client.get("/api/overview").headers["cache-control"] == "no-store"


def test_the_public_api_is_read_only(client):
    """No write route exists under /api/v1, whatever is posted at it."""
    for path in ["/api/v1/summary", "/api/v1/contracts"]:
        assert client.post(path, json={"anything": 1}).status_code == 404


# --- exports ------------------------------------------------------------------


def test_a_csv_export_carries_its_provenance(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "providers", "format": "csv"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]

    body = response.text
    assert body.startswith("# SectorTrace export")
    assert "# exported_at:" in body
    assert "docs/CAVEATS.md" in body
    assert "change_grow_live" in body

    # And in a header, for anything reading the response rather than the file.
    provenance = json.loads(response.headers["x-provenance"])
    assert provenance["source_endpoint"] == "/api/v1/providers"


def test_a_json_export_carries_its_provenance(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "contracts", "format": "json",
                                    "provider_key": "change_grow_live"})
    payload = response.json()
    assert payload["_provenance"]["filters_applied"] == {"provider_key": "change_grow_live"}
    assert isinstance(payload["contracts"], list)


def test_export_refuses_an_endpoint_it_cannot_flatten(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "boundaries", "format": "csv"})
    assert response.status_code == 400
    assert "cannot be exported" in response.json()["error"]


def test_export_refuses_an_unknown_format(client):
    response = client.get("/api/v1/export",
                           params={"endpoint": "providers", "format": "xlsx"})
    assert response.status_code == 400


def test_csv_export_keeps_columns_that_only_later_rows_have():
    """Rows from a view can legitimately differ in shape. Taking the header
    from row one would silently truncate the export."""
    csv = public_export.to_csv(
        [{"a": 1}, {"a": 2, "b": 3}],
        public_export.provenance("providers", {}))
    assert "a,b" in csv
    assert "2,3" in csv
