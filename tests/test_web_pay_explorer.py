"""Workforce pay explorer filters (BETA-070).

The pay endpoint already returned every pay layer as its own array. This pins
the additive narrowing — one source group, a role substring, a pay unit — and
the explorer index (`source_groups`, `filters_available`) built beside it. The
filters must never combine sources or produce a rate: a narrowed view is a
subset of the same rows, nothing more.
"""
from __future__ import annotations

import sqlite3

import pytest

from pipeline.web import public_queries as pq
from pipeline.web.queries import QueryError


@pytest.fixture
def paydata(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("INSERT INTO providers (provider_key, canonical_name, is_target) "
                  "VALUES ('cgl', 'Change Grow Live', 1)")
    for ref, title, period, smin in [
        ("a1", "Registered Nurse", "year", 35000),
        ("a2", "Recovery Worker", "year", 24000),
        ("a3", "Bank Nurse", "hour", None),
    ]:
        conn.execute(
            "INSERT INTO nhs_job_adverts (job_reference, provider_key, "
            " provider_match_basis, employer_name_raw, job_title, advert_url, "
            " salary_raw, salary_min, salary_max, salary_period, salary_basis, "
            " searched_variant, source_url, retrieved_at, http_status, "
            " source_system, payload_sha256) VALUES "
            "(%s, 'cgl', 'exact', 'CGL', %s, 'https://jobs.example/a', "
            " 'see advert', %s, %s, %s, 'single', 'CGL', 'https://jobs.example/a', "
            " '2026-08-01T00:00:00Z', 200, 'nhs_jobs', 'h')",
            (ref, title, smin, smin, period))
    conn.execute(
        "INSERT INTO statutory_pay_rates (period_label, effective_from, "
        " band_label, band_role, amount, value_text, source_url, retrieved_at, "
        " http_status, source_system, payload_sha256) VALUES "
        "('April 2026', '2026-04-01', '21 and over', 'National Living Wage', "
        " 12.21, '£12.21', 'https://gov.example/nmw', '2026-08-01T00:00:00Z', "
        " 200, 'gov_uk', 's')")
    conn.commit()
    return conn


def test_baseline_returns_every_group_and_the_pickers(paydata) -> None:
    out = pq.pay(paydata)
    groups = {g["key"]: g for g in out["source_groups"]}
    assert set(groups) == {
        "indicative_wage", "advertised_roles", "published_statutory",
        "workforce_census", "external_comparators",
    }
    assert groups["advertised_roles"]["count"] == 3   # 3 adverts
    assert groups["published_statutory"]["count"] == 1  # 1 statutory rate
    roles = out["filters_available"]["roles"]
    assert "Registered Nurse" in roles and "National Living Wage" in roles
    assert out["filters_available"]["pay_units"] == ["hourly", "annual", "other"]


def test_source_filter_shows_one_group_and_empties_the_rest(paydata) -> None:
    out = pq.pay(paydata, source="advertised_roles")
    assert len(out["nhs_job_adverts"]) == 3
    assert out["statutory_pay_rates"] == []
    # shape is unchanged: the key is still present, just empty
    assert "statutory_pay_rates" in out
    groups = {g["key"]: g["count"] for g in out["source_groups"]}
    assert groups["advertised_roles"] == 3
    assert groups["published_statutory"] == 0


def test_role_filter_is_a_case_insensitive_substring(paydata) -> None:
    out = pq.pay(paydata, role="nurse")
    titles = sorted(r["job_title"] for r in out["nhs_job_adverts"])
    assert titles == ["Bank Nurse", "Registered Nurse"]
    # the statutory row's band_role is "National Living Wage" — no "nurse"
    assert out["statutory_pay_rates"] == []


def test_pay_unit_filter_keeps_only_rows_carrying_that_unit(paydata) -> None:
    hourly = pq.pay(paydata, pay_unit="hourly")
    assert [r["job_reference"] for r in hourly["nhs_job_adverts"]] == ["a3"]
    # statutory rates are always hourly, so they survive
    assert len(hourly["statutory_pay_rates"]) == 1

    annual = pq.pay(paydata, pay_unit="annual")
    assert sorted(r["job_reference"] for r in annual["nhs_job_adverts"]) == ["a1", "a2"]
    assert annual["statutory_pay_rates"] == []


def test_filters_compose_without_combining_sources(paydata) -> None:
    out = pq.pay(paydata, source="advertised_roles", role="nurse", pay_unit="annual")
    assert [r["job_reference"] for r in out["nhs_job_adverts"]] == ["a1"]
    assert out["statutory_pay_rates"] == []
    # no rate/ratio/score keys were introduced
    assert "pay_score" not in out and "ratio" not in out


def test_bad_filter_values_are_refused(paydata) -> None:
    with pytest.raises(QueryError):
        pq.pay(paydata, source="not-a-group")
    with pytest.raises(QueryError):
        pq.pay(paydata, pay_unit="weekly")


def test_role_picker_is_not_shrunk_by_an_active_role_filter(paydata) -> None:
    out = pq.pay(paydata, role="nurse")
    # the picker still offers every role at this scope, so a reader can switch
    assert "Recovery Worker" in out["filters_available"]["roles"]
