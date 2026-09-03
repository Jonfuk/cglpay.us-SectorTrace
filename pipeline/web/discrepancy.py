"""Evidence discrepancy explorer (BETA-096).

Where two or more public sources report a *different* value for the same
verified entity and field, both values are shown side by side — with their
source and retrieval date — and neither is resolved, ranked, or labelled an
error. Disagreement between sources is evidence context.

This is not cross-source arithmetic (docs/CAVEATS.md forbids that): nothing
here adds, averages, or reconciles. It only says "source A says X, source B
says Y" and lets the reader see both.

A **closed registry** of comparable field pairs — `_PROVIDER_CHECKS` /
`_AUTHORITY_CHECKS` — decides what is compared. Each check names the sources
and the exact column each reports the field in; a check with fewer than two
distinct values across its sources simply agrees, and is listed as such.
"""
from __future__ import annotations

import sqlite3

from pipeline.web.public_queries import _one, _public, _rows
from pipeline.web.queries import QueryError

# id, label, and per source: a name and a query returning
# {value, as_of, source_url} rows for the entity id bound to `?`.
_PROVIDER_CHECKS = (
    {"id": "legal_name", "label": "Provider / employer name", "sources": (
        {"source": "SectorTrace canonical",
         "sql": "SELECT canonical_name AS value, NULL AS as_of, NULL AS source_url "
                "FROM providers WHERE provider_key = %s"},
        {"source": "Companies House",
         "sql": "SELECT DISTINCT company_name AS value, retrieved_at AS as_of, "
                "source_url FROM companies WHERE provider_key = %s "
                "AND company_name IS NOT NULL"},
        {"source": "CQC provider register",
         "sql": "SELECT DISTINCT provider_name AS value, retrieved_at AS as_of, "
                "source_url FROM cqc_providers WHERE provider_key = %s "
                "AND provider_name IS NOT NULL"},
        {"source": "Gender pay gap filing",
         "sql": "SELECT DISTINCT employer_name AS value, retrieved_at AS as_of, "
                "source_url FROM gender_pay_gap_reports WHERE provider_key = %s "
                "AND employer_name IS NOT NULL"},
    )},
    {"id": "company_number", "label": "Company number", "sources": (
        {"source": "SectorTrace identifier register",
         "sql": "SELECT DISTINCT identifier AS value, NULL AS as_of, "
                "NULL AS source_url FROM provider_identifiers "
                "WHERE provider_key = %s AND scheme = 'company_number'"},
        {"source": "Companies House",
         "sql": "SELECT DISTINCT company_number AS value, retrieved_at AS as_of, "
                "source_url FROM companies WHERE provider_key = %s "
                "AND company_number IS NOT NULL"},
        {"source": "Gender pay gap filing",
         "sql": "SELECT DISTINCT company_number AS value, retrieved_at AS as_of, "
                "source_url FROM gender_pay_gap_reports WHERE provider_key = %s "
                "AND company_number IS NOT NULL"},
    )},
)

_AUTHORITY_CHECKS = (
    {"id": "authority_name", "label": "Authority name", "sources": (
        {"source": "ONS geography",
         "sql": "SELECT name AS value, retrieved_at AS as_of, source_url "
                "FROM authorities WHERE ons_code = %s"},
        {"source": "Procurement notices (buyer)",
         "sql": "SELECT DISTINCT buyer_name AS value, MAX(retrieved_at) AS as_of, "
                "MIN(source_url) AS source_url FROM contracts "
                "WHERE buyer_ons_code = %s AND buyer_name IS NOT NULL "
                "GROUP BY buyer_name"},
        {"source": "NDTMS statistics",
         "sql": "SELECT DISTINCT area_name_raw AS value, MAX(retrieved_at) AS as_of, "
                "MIN(source_url) AS source_url FROM ndtms_la_statistics "
                "WHERE ons_code = %s AND area_name_raw IS NOT NULL "
                "GROUP BY area_name_raw"},
    )},
)

_TABLES = (
    "providers", "companies", "cqc_providers", "gender_pay_gap_reports",
    "provider_identifiers", "cqc_locations", "authorities", "contracts",
    "ndtms_la_statistics",
)

_NOTE = (
    "Each row is a field two or more public sources report differently for "
    "this entity. Nothing is reconciled: a difference may be a spelling, a "
    "legal form, a snapshot from a different date, or a genuine "
    "disagreement — this view does not judge which value is right, and a "
    "difference is never called an error."
)


def _observations(conn: sqlite3.Connection, check: dict, ident: str) -> list[dict]:
    seen: list[dict] = []
    for src in check["sources"]:
        for row in _rows(conn, src["sql"], (ident,)):
            value = row["value"]
            if value in (None, ""):
                continue
            seen.append({"source": src["source"], "value": str(value),
                          "as_of": row["as_of"], "source_url": row["source_url"]})
    return seen


def _cqc_rating_rows(conn: sqlite3.Connection, provider_key: str) -> list[dict]:
    """The schema's own flagged case: a location whose CQC syndication-API
    rating and CQC bulk-export rating disagree (migration 0055)."""
    out = []
    for row in _rows(conn, """
        SELECT location_id, location_name, overall_rating, overall_rating_date,
               bulk_overall_rating, bulk_overall_rating_date, source_url, retrieved_at
        FROM cqc_locations
        WHERE provider_key = %s AND overall_rating IS NOT NULL
          AND bulk_overall_rating IS NOT NULL
          AND overall_rating <> bulk_overall_rating""", (provider_key,)):
        out.append({
            "id": f"cqc_rating:{row['location_id']}",
            "label": f"CQC overall rating — {row['location_name'] or row['location_id']}",
            "observations": [
                {"source": "CQC syndication API", "value": row["overall_rating"],
                 "as_of": row["overall_rating_date"], "source_url": row["source_url"]},
                {"source": "CQC bulk export", "value": row["bulk_overall_rating"],
                 "as_of": row["bulk_overall_rating_date"], "source_url": row["source_url"]},
            ],
            "distinct_values": sorted({row["overall_rating"], row["bulk_overall_rating"]}),
        })
    return out


def check(conn: sqlite3.Connection, *, provider_key: str | None = None,
          ons_code: str | None = None) -> dict:
    _public(list(_TABLES))
    if bool(provider_key) == bool(ons_code):
        raise QueryError("give exactly one of provider_key or ons_code")

    if provider_key:
        row = _one(conn, "SELECT canonical_name FROM providers WHERE provider_key = %s",
                   (provider_key,))
        if not row:
            raise QueryError(f"No provider {provider_key!r}.")
        entity = {"kind": "provider", "id": provider_key, "name": row["canonical_name"]}
        checks_def, ident = _PROVIDER_CHECKS, provider_key
    else:
        row = _one(conn, "SELECT name FROM authorities WHERE ons_code = %s", (ons_code,))
        if not row:
            raise QueryError(f"No authority {ons_code!r}.")
        entity = {"kind": "authority", "id": ons_code, "name": row["name"]}
        checks_def, ident = _AUTHORITY_CHECKS, ons_code

    discrepancies: list[dict] = []
    agreed: list[dict] = []
    for cdef in checks_def:
        obs = _observations(conn, cdef, ident)
        values = sorted({o["value"] for o in obs})
        if len(values) >= 2:
            discrepancies.append({
                "id": cdef["id"], "label": cdef["label"],
                "observations": obs, "distinct_values": values,
            })
        elif obs:
            agreed.append({"id": cdef["id"], "label": cdef["label"],
                            "value": values[0],
                            "sources": sorted({o["source"] for o in obs})})
        else:
            agreed.append({"id": cdef["id"], "label": cdef["label"],
                            "value": None, "sources": []})

    if provider_key:
        discrepancies.extend(_cqc_rating_rows(conn, provider_key))

    return {
        "entity": entity,
        "discrepancies": discrepancies,
        "agreed": agreed,
        "checked": len(checks_def) + (1 if provider_key else 0),
        "note": _NOTE,
        "caveat": "Only identity-level fields are compared in this version "
                  "(name, number, rating). Period-scoped figures — income, "
                  "grant, budget — are shown on their own pages with their own "
                  "caveats and are not reconciled here either.",
    }
