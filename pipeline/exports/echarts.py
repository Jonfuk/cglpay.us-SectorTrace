"""ECharts-ready JSON for the dashboard.

Every series ships with a `meta` block carrying its source system, retrieval
date and caveat text, so no chart can render without its provenance being
available to the UI. That is the point of the shape: a series object without
meta is not producible by this module.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import structlog

from pipeline.exports import guard_columns
from pipeline.exports.provenance import write_export

log = structlog.get_logger()


def _series_meta(conn: sqlite3.Connection, tables: list[str], caveats: list[str],
                  unit: str, source_note: str) -> dict:
    sources, retrieved = set(), []
    for table in tables:
        try:
            row = conn.execute(
                f"SELECT GROUP_CONCAT(DISTINCT source_system) AS s, MAX(retrieved_at) AS r "
                f"FROM {table}").fetchone()
            if row["s"]:
                sources.update(row["s"].split(","))
            if row["r"]:
                retrieved.append(row["r"])
        except Exception:
            continue
    return {
        "source_systems": sorted(sources),
        "source_tables": tables,
        "retrieved_at": max(retrieved) if retrieved else None,
        "unit": unit,
        "source_note": source_note,
        "caveats": caveats,
    }


def _series(conn, name, tables, caveats, unit, source_note, categories, values) -> dict:
    return {
        "name": name,
        "categories": categories,
        "values": values,
        "meta": _series_meta(conn, tables, caveats, unit, source_note),
    }


def build_charity_wage_series(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute("""
        SELECT financial_year_end, indicative_wage_per_head, indicative_wage_per_fte
          FROM v_wage_per_employee ORDER BY financial_year_end
    """)
    guard_columns("wage_series", [d[0] for d in cursor.description])
    rows = cursor.fetchall()
    years = [r["financial_year_end"] for r in rows]

    shared = [
        "NOT an average salary. The denominator is an average employee count published by "
        "the charity, and the numerator is total wages for all grades including senior staff, "
        "before employer NI and pension costs.",
        "Per-head and per-FTE differ materially because a headcount average counts part-time "
        "staff as whole people.",
    ]
    return [
        _series(conn, "Indicative wage per head",
                 ["charity_accounts_extracts"], shared, "GBP",
                 "Charity Commission filed accounts, staff costs note",
                 years, [r["indicative_wage_per_head"] for r in rows]),
        _series(conn, "Indicative wage per FTE",
                 ["charity_accounts_extracts"], shared, "GBP",
                 "Charity Commission filed accounts, staff costs note",
                 years, [r["indicative_wage_per_fte"] for r in rows]),
    ]


def build_agency_spend_series(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute("""
        SELECT financial_year_end, agency_and_third_party, wages_and_salaries
          FROM charity_accounts_extracts
         WHERE agency_and_third_party IS NOT NULL
         ORDER BY financial_year_end
    """)
    rows = cursor.fetchall()
    years = [r["financial_year_end"] for r in rows]
    caveats = [
        "Agency and third-party spend as published in the charity's own staff costs note.",
        "Shown alongside wages from the same note and the same year — both come from one "
        "document, so this is a comparison within a source, not across sources.",
    ]
    return [
        _series(conn, "Agency and third-party spend", ["charity_accounts_extracts"],
                 caveats, "GBP", "Charity Commission filed accounts, staff costs note",
                 years, [r["agency_and_third_party"] for r in rows]),
        _series(conn, "Wages and salaries", ["charity_accounts_extracts"],
                 caveats, "GBP", "Charity Commission filed accounts, staff costs note",
                 years, [r["wages_and_salaries"] for r in rows]),
    ]


def build_workforce_census_series(conn: sqlite3.Connection) -> list[dict]:
    caveats = [
        "Provider participation varies between census rounds, so these points are NOT "
        "like-for-like and the line between them does not measure change.",
        "Values are unverified until a human checks them against the source line; see "
        "docs/verification/census_{year}_tables.md.",
        "Sector aggregates only — no figure can be attributed to a named provider.",
    ]
    out = []
    for metric, unit in (("vacancy_rate", "percent"), ("turnover_rate", "percent")):
        cursor = conn.execute("""
            SELECT census_year, value FROM workforce_census_metrics
             WHERE metric = ? AND workforce_segment = 'delivery'
             ORDER BY census_year
        """, (metric,))
        rows = cursor.fetchall()
        if not rows:
            continue
        out.append(_series(
            conn, metric.replace("_", " ").title() + " (delivery workforce)",
            ["workforce_census_metrics"], caveats, unit,
            "National Drug and Alcohol Treatment and Recovery Services Workforce Census",
            [r["census_year"] for r in rows], [r["value"] for r in rows]))
    return out


def build_public_health_grant_series(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute("""
        SELECT financial_year, SUM(amount) AS total
          FROM public_health_grants
         WHERE grant_type LIKE '%drug%alcohol%' AND unit = 'gbp'
         GROUP BY financial_year ORDER BY financial_year
    """)
    rows = cursor.fetchall()
    caveats = [
        "Sum of the drug and alcohol ring-fenced allocation across all authorities, as "
        "published by DHSC.",
        "Later years are indicative allocations, not confirmed funding.",
        "Cash figures. No inflation adjustment is applied — applying one is a decision for "
        "whoever publishes it to document.",
    ]
    if not rows:
        return []
    return [_series(
        conn, "Drug and alcohol ring-fenced grant (England total)",
        ["public_health_grants"], caveats, "GBP",
        "DHSC public health grant allocations",
        [r["financial_year"] for r in rows], [r["total"] for r in rows])]


def build_treatment_numbers_series(conn: sqlite3.Connection) -> list[dict]:
    cursor = conn.execute("""
        SELECT v.time_period, AVG(v.value) AS mean_rate
          FROM fingertips_la_values v
          JOIN fingertips_indicators i ON i.indicator_id = v.indicator_id
         WHERE i.slug = 'adults_in_drug_treatment_rate'
           AND v.area_level = 'local_authority' AND v.value IS NOT NULL
         GROUP BY v.time_period ORDER BY v.time_period
    """)
    rows = cursor.fetchall()
    if not rows:
        return []
    caveats = [
        "Mean of the published local-authority rates, not a national rate — an unweighted "
        "mean of authority rates is not the same as England's own figure, which is published "
        "separately.",
        "Service-demand data, not workforce data. Do not divide by workforce figures.",
    ]
    return [_series(
        conn, "Adults in drug treatment, mean of LA rates",
        ["fingertips_la_values"], caveats, "rate per 1,000 population",
        "OHID Fingertips",
        [r["time_period"] for r in rows], [round(r["mean_rate"], 3) for r in rows])]


def export_all(conn: sqlite3.Connection, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    builders = {
        "charity_wage": build_charity_wage_series,
        "agency_spend": build_agency_spend_series,
        "workforce_census": build_workforce_census_series,
        "public_health_grant": build_public_health_grant_series,
        "treatment_numbers": build_treatment_numbers_series,
    }
    written: list[Path] = []

    for name, builder in builders.items():
        series = builder(conn)
        if not series:
            log.info("echarts.series_empty", chart=name)
            continue
        for entry in series:
            if not entry.get("meta"):
                raise ValueError(f"series {entry.get('name')!r} has no meta block")

        payload = {"chart": name, "series": series}
        tables = sorted({t for s in series for t in s["meta"]["source_tables"]})
        caveats = sorted({c for s in series for c in s["meta"]["caveats"]})
        path = output_dir / f"{name}.json"
        write_export(path, lambda p, d=payload: p.write_text(json.dumps(d, indent=2), encoding="utf-8"),
                      conn, tables, "echarts_series", sum(len(s["values"]) for s in series), caveats)
        written.append(path)
        log.info("echarts.chart_written", chart=name, series=len(series), path=str(path))

    return written
