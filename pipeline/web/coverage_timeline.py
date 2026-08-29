"""Temporal coverage navigator (BETA-097).

For one selected provider or authority, exactly which periods each source
holds — so a reader discovers a gap before opening a section, and a period
absent from a list stays "not collected / not published", never a zero.

Nothing here is gap-filled. Each source's `periods` list is exactly the
distinct periods the warehouse holds for that entity. The only synthesised
value is `span` / `years` — the axis a timeline is drawn against — and it is
labelled as the axis, not as data.
"""
from __future__ import annotations

import re
import sqlite3

from pipeline.web.public_queries import _one, _public, _rows
from pipeline.web.queries import QueryError

_YEAR = re.compile(r"(19|20)\d{2}")

# Closed registry of source probes. Each runs one query with a single `?`
# bound to the entity id and returns the distinct periods held. `link` is a
# hash route into the view that shows that source; `{id}` is substituted.
_PROVIDER_SOURCES = (
    {"dataset_id": "charity-finance", "title": "Charity accounts",
     "period_kind": "financial year", "link": "#/providers/{id}",
     "sql": "SELECT DISTINCT substr(cf.financial_year_end, 1, 4) AS p "
            "FROM charity_financials cf JOIN provider_identifiers pi "
            "  ON pi.identifier = cf.charity_number AND pi.scheme = 'charity_number' "
            "WHERE pi.provider_key = ? AND cf.financial_year_end IS NOT NULL"},
    {"dataset_id": "nhs-job-adverts", "title": "NHS Jobs adverts",
     "period_kind": "year", "link": "#/pay",
     "sql": "SELECT DISTINCT substr(posted_date, 1, 4) AS p FROM nhs_job_adverts "
            "WHERE provider_key = ? AND posted_date IS NOT NULL"},
    {"dataset_id": "gender-pay-gap", "title": "Gender pay gap reports",
     "period_kind": "reporting year", "link": "#/pay",
     "sql": "SELECT DISTINCT reporting_year AS p FROM gender_pay_gap_reports "
            "WHERE provider_key = ? AND reporting_year IS NOT NULL"},
    {"dataset_id": "tribunals", "title": "Employment tribunal decisions",
     "period_kind": "year", "link": "#/providers/{id}",
     "sql": "SELECT DISTINCT substr(decision_date, 1, 4) AS p FROM tribunal_cases "
            "WHERE provider_key = ? AND decision_date IS NOT NULL"},
    {"dataset_id": "pfd-reports", "title": "Prevention of Future Deaths reports",
     "period_kind": "year", "link": "#/pfd",
     "sql": "SELECT DISTINCT substr(r.report_date, 1, 4) AS p "
            "FROM pfd_provider_mentions m "
            "JOIN pfd_reports r ON r.report_ref = m.report_ref "
            "WHERE m.provider_key = ? AND r.report_date IS NOT NULL"},
    {"dataset_id": "procurement-notices", "title": "Procurement notices (as supplier)",
     "period_kind": "year", "link": "#/contracts?provider={id}",
     "sql": "SELECT DISTINCT substr(c.date_published, 1, 4) AS p "
            "FROM contracts c "
            "JOIN supplier_aliases sa ON sa.alias_raw = c.supplier_name_raw "
            "WHERE sa.supplier_key = ? AND c.date_published IS NOT NULL"},
)

_AUTHORITY_SOURCES = (
    {"dataset_id": "public-health-grant", "title": "Public health grant",
     "period_kind": "financial year", "link": "#/geography?metric=grant_total",
     "sql": "SELECT DISTINCT financial_year AS p FROM public_health_grants "
            "WHERE ons_code = ? AND financial_year IS NOT NULL"},
    {"dataset_id": "la-revenue-budgets", "title": "Revenue budgets",
     "period_kind": "financial year", "link": "#/geography?metric=budget_public_health",
     "sql": "SELECT DISTINCT financial_year AS p FROM la_revenue_budgets "
            "WHERE ons_code = ? AND financial_year IS NOT NULL"},
    {"dataset_id": "ndtms-annual", "title": "NDTMS annual statistics",
     "period_kind": "financial year", "link": "#/authorities/{id}",
     "sql": "SELECT DISTINCT financial_year AS p FROM ndtms_la_statistics "
            "WHERE ons_code = ? AND financial_year IS NOT NULL"},
    {"dataset_id": "fingertips", "title": "Fingertips indicators",
     "period_kind": "period", "link": "#/authorities/{id}",
     "sql": "SELECT DISTINCT time_period AS p FROM fingertips_la_values "
            "WHERE ons_code = ? AND area_level = 'local_authority' "
            "  AND time_period IS NOT NULL"},
    {"dataset_id": "procurement-notices", "title": "Procurement notices (as buyer)",
     "period_kind": "year", "link": "#/authorities/{id}",
     "sql": "SELECT DISTINCT substr(date_published, 1, 4) AS p FROM contracts "
            "WHERE buyer_ons_code = ? AND date_published IS NOT NULL"},
    {"dataset_id": "council-spend", "title": "Council spend files",
     "period_kind": "period", "link": "#/authorities/{id}",
     "sql": "SELECT DISTINCT period AS p FROM council_spend "
            "WHERE authority_ons_code = ? AND period IS NOT NULL"},
)

_TABLES = (
    "charity_financials", "provider_identifiers", "nhs_job_adverts",
    "gender_pay_gap_reports", "tribunal_cases", "pfd_provider_mentions",
    "pfd_reports", "contracts", "supplier_aliases", "public_health_grants",
    "la_revenue_budgets", "ndtms_la_statistics", "fingertips_la_values",
    "council_spend", "providers", "authorities",
)

_NOTE = (
    "Each list is the periods this warehouse actually holds for this entity — "
    "never gap-filled. A period missing from a list is not a zero: it means "
    "the source did not publish it, or this pipeline has not collected it. "
    "The year axis is drawn for alignment only and is not itself evidence."
)


def _periods_for(conn: sqlite3.Connection, source: dict, entity_id: str) -> list[str]:
    rows = _rows(conn, source["sql"], (entity_id,))
    seen = sorted({str(r["p"]) for r in rows if r["p"] not in (None, "")})
    return seen


def timeline(conn: sqlite3.Connection, *, provider_key: str | None = None,
             ons_code: str | None = None) -> dict:
    _public(list(_TABLES))
    if bool(provider_key) == bool(ons_code):
        raise QueryError("give exactly one of provider_key or ons_code")

    if provider_key:
        row = _one(conn, "SELECT canonical_name FROM providers WHERE provider_key = ?",
                   (provider_key,))
        if not row:
            raise QueryError(f"No provider {provider_key!r}.")
        entity = {"kind": "provider", "id": provider_key,
                  "name": row["canonical_name"]}
        probes, ident = _PROVIDER_SOURCES, provider_key
    else:
        row = _one(conn, "SELECT name FROM authorities WHERE ons_code = ?",
                   (ons_code,))
        if not row:
            raise QueryError(f"No authority {ons_code!r}.")
        entity = {"kind": "authority", "id": ons_code, "name": row["name"]}
        probes, ident = _AUTHORITY_SOURCES, ons_code

    sources: list[dict] = []
    years: set[int] = set()
    for probe in probes:
        periods = _periods_for(conn, probe, ident)
        for period in periods:
            match = _YEAR.search(period)
            if match:
                years.add(int(match.group(0)))
        sources.append({
            "dataset_id": probe["dataset_id"],
            "title": probe["title"],
            "period_kind": probe["period_kind"],
            "periods": periods,
            "held": bool(periods),
            "link": probe["link"].replace("{id}", ident),
        })

    span = ({"min": min(years), "max": max(years)} if years else None)
    year_axis = list(range(span["min"], span["max"] + 1)) if span else []

    return {
        "entity": entity,
        "span": span,
        "years": year_axis,
        "sources": sources,
        "held_count": sum(1 for s in sources if s["held"]),
        "note": _NOTE,
        "caveat": "Coverage here is discovery plus collection: a source this "
                  "pipeline does not yet collect for this entity shows as "
                  "empty, which is not the same as the source holding nothing.",
    }
