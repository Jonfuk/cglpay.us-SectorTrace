"""`GET /api/v1/provider_compare` — 2 to 4 providers, four separate layers (BETA-045).

The point of this endpoint is what it refuses to do. It lays Living Wage
accreditation, the latest gender pay gap filing, provider-published pay and
recent NHS Jobs adverts side by side and never combines them: no ranking, no
score, no difference, no ratio, and no flat CSV that would imply the four are
one measure. These tests pin that absence as much as the presence.
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest

from pipeline.config import Settings
from pipeline.web import public_export
from pipeline.web.server import build_server

CGL = "change-grow-live"
TP = "turning-point"


@pytest.fixture
def warehouse(conn: sqlite3.Connection) -> sqlite3.Connection:
    for key, nm in [(CGL, "Change Grow Live"), (TP, "Turning Point")]:
        conn.execute("INSERT INTO providers (provider_key, canonical_name, "
                     "is_target, notes) VALUES (?, ?, 1, NULL)", (key, nm))
    conn.execute(
        "INSERT INTO living_wage_accreditations (provider_key, searched_variant, "
        " accredited, employer_name, match_basis, pages_checked, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        " (?, 'Change Grow Live', 1, 'Change Grow Live', 'exact', 1, "
        " 'https://lw.example/a', '2026-07-01T00:00:00Z', 200, 'lwf', 'lw1')",
        (CGL,))
    conn.execute(
        "INSERT INTO living_wage_accreditations (provider_key, searched_variant, "
        " accredited, employer_name, match_basis, pages_checked, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        " (?, 'Turning Point', 0, NULL, NULL, 3, 'https://lw.example/b', "
        " '2026-07-01T00:00:00Z', 200, 'lwf', 'lw2')",
        (TP,))
    # Two gender pay gap years for CGL — only the newest must come back.
    for year, mean, median in [("2022", 9.1, 7.0), ("2024", 4.2, 3.1)]:
        conn.execute(
            "INSERT INTO gender_pay_gap_reports (provider_key, reporting_year, "
            " reporting_year_label, employer_id, match_basis, employer_name, "
            " diff_mean_hourly_percent, diff_median_hourly_percent, "
            " written_statement_url, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) VALUES (?, ?, ?, 'E1', 'exact', "
            " 'Change Grow Live', ?, ?, 'https://gpg.example/s', "
            " 'https://gpg.example/r', '2026-06-01T00:00:00Z', 200, 'gpg', ?)",
            (CGL, year, f"{year} to {int(year) + 1}", mean, median, f"gpg-{year}"))
    conn.execute(
        "INSERT INTO provider_pay_mentions (page_url, mention_index, provider_key, "
        " mention_text, salary_basis, match_basis, salary_period, source_url, "
        " retrieved_at, http_status, source_system, payload_sha256) VALUES "
        " ('https://cgl.example/careers', 0, ?, 'Band 5 from £28,407', 'band', "
        " 'exact', 'year', 'https://cgl.example/careers', "
        " '2026-05-01T00:00:00Z', 200, 'provider_site', 'pm1')",
        (CGL,))
    for i, dt in enumerate(["2026-08-01", "2026-07-15", "2026-06-01"]):
        conn.execute(
            "INSERT INTO nhs_job_adverts (job_reference, provider_key, "
            " provider_match_basis, employer_name_raw, job_title, advert_url, "
            " salary_raw, salary_basis, searched_variant, source_url, "
            " retrieved_at, http_status, source_system, payload_sha256, posted_date) "
            " VALUES (?, ?, 'exact', 'Turning Point', 'Recovery Worker', "
            " 'https://jobs.example/x', '£24,071 to £25,674 a year', 'range', "
            " 'Turning Point', 'https://jobs.example/x', '2026-08-05T00:00:00Z', "
            " 200, 'nhs_jobs', ?, ?)",
            (f"job-{i}", TP, f"adv-{i}", dt))
    conn.commit()
    return conn


@pytest.fixture
def client(warehouse, settings: Settings):
    warehouse.close()
    server = build_server(settings, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{server.server_address[1]}",
                           timeout=10.0) as http:
            yield http
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(client, *keys):
    return client.get("/api/v1/provider_compare",
                      params=[("provider_key", k) for k in keys])


def test_lays_out_four_separate_layers_each_with_its_own_unit_and_caveat(client):
    body = _get(client, CGL, TP).json()
    assert [p["provider_key"] for p in body["providers"]] == [CGL, TP]
    assert set(body["layers"]) == {
        "living_wage", "gender_pay_gap", "provider_pay", "nhs_jobs"}
    for layer in body["layers"].values():
        assert layer["unit"] and layer["caveat"]
        assert layer["temporal"] is False
        assert set(layer["by_provider"]) == {CGL, TP}
    assert body["caveat"]


def test_gender_pay_gap_layer_is_the_latest_year_only(client):
    body = _get(client, CGL, TP).json()
    cgl = body["layers"]["gender_pay_gap"]["by_provider"][CGL]
    assert [r["reporting_year"] for r in cgl] == ["2024"]
    assert cgl[0]["diff_mean_hourly_percent"] == 4.2


def test_a_provider_absent_from_a_layer_is_an_empty_list_not_an_omission(client):
    body = _get(client, CGL, TP).json()
    assert body["layers"]["provider_pay"]["by_provider"][TP] == []
    assert body["layers"]["nhs_jobs"]["by_provider"][CGL] == []


def test_the_payload_carries_no_ranking_score_difference_or_ratio(client):
    raw = _get(client, CGL, TP).text.lower()
    for forbidden in ('"rank"', '"score"', '"ratio"', '"difference"',
                      '"delta"', '"composite"', '"index"', '"percentile"'):
        assert forbidden not in raw, f"{forbidden} leaked into provider_compare"


def test_between_two_and_four_providers_are_required(client):
    assert _get(client, CGL).status_code == 400
    assert _get(client, CGL, TP, "a", "b", "c").status_code == 400
    # Duplicates collapse before the count check.
    assert _get(client, CGL, CGL).status_code == 400


def test_an_unknown_provider_key_is_a_clean_400(client):
    response = _get(client, CGL, "no-such-provider")
    assert response.status_code == 400
    assert "no-such-provider" in response.json()["error"]


def test_there_is_no_csv_export_for_this_endpoint():
    """Unlike measures must not be flattened into one table. The endpoint is
    absent from the export registry that drives every CSV/JSON download."""
    assert "provider_compare" not in public_export.EXPORTABLE
    assert "provider_compare" not in public_export.WINDOWED


def test_the_route_is_on_the_frozen_public_surface():
    from tests.test_portal_isolation import PUBLIC_API_ROUTES
    assert "provider_compare" in PUBLIC_API_ROUTES
