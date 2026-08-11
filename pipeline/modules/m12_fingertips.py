"""Module 12 — OHID Fingertips local-authority indicators.

Fills the gap Module 7 exposed. The GOV.UK NDTMS data tables publish numbers
in treatment, waiting times and successful completions nationally, with just
one local-authority sheet; Fingertips carries the same measures per
authority and — unlike the NDTMS spreadsheets, which give area names only —
keys them by ONS area code, so they join to `authorities` with no name
matching.

Indicators are listed explicitly in pipeline/fingertips_indicators.py rather
than discovered by keyword search: a search would silently change the
collected set whenever OHID adds or renames an indicator, and a series that
quietly gains or loses a measure between runs is not defensible evidence.

Unmet need is not published by Fingertips and is not derived here. Prevalence
and numbers in treatment are stored as published; subtracting one from the
other would manufacture a figure from two different estimation methods.

England and region rows are kept alongside the local-authority rows, flagged
by area_level, because they are the comparators the LA figures are published
against — but the v_fingertips_la_latest view exposes LA rows only, so a
national row cannot be mistaken for an authority's own value.
"""
from __future__ import annotations

import csv
import io
import json
import re

import structlog

from pipeline import db
from pipeline.fingertips_indicators import (
    INDICATORS,
    PARENT_AREA_TYPE_ID,
    area_type_ids_for,
)
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "ohid_fingertips"
API_BASE = "https://fingertips.phe.org.uk/api"
DATA_URL = f"{API_BASE}/all_data/csv/by_indicator_id"
METADATA_URL = f"{API_BASE}/indicator_metadata/by_indicator_id"

# ONS entity-code prefixes: E92 England, E12 Government Office Region.
_ENGLAND_RE = re.compile(r"^E92\d{6}$")
_REGION_RE = re.compile(r"^E12\d{6}$")
_LA_RE = re.compile(r"^E0[6-9]\d{6}$|^E10\d{6}$")


def classify_area_level(area_code: str) -> str:
    """England / region / local authority, from the ONS entity code prefix.

    Done on the code rather than the 'Area Type' text column because the
    text varies between indicator releases while the code prefixes do not.
    """
    code = (area_code or "").strip().upper()
    if _ENGLAND_RE.match(code):
        return "england"
    if _REGION_RE.match(code):
        return "region"
    if _LA_RE.match(code):
        return "local_authority"
    return "other"


def _to_number(raw: str) -> float | None:
    text = (raw or "").strip().replace(",", "")
    if text in {"", "-", "–", "—", "*", "c", "z", "x", ":"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_indicator_csv(csv_text: str) -> list[dict]:
    """Rows from a Fingertips all_data CSV export.

    Column names are read from the header rather than assumed by position:
    the export has gained columns over time (a 'Compared to goal' column
    appears in recent releases), so fixed indices would silently shift.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows: list[dict] = []
    for raw in reader:
        area_code = (raw.get("Area Code") or "").strip()
        if not area_code:
            continue
        indicator_id = _to_number(raw.get("Indicator ID") or "")
        if indicator_id is None:
            continue
        rows.append({
            "indicator_id": int(indicator_id),
            "indicator_name": (raw.get("Indicator Name") or "").strip(),
            "area_code": area_code,
            "area_name": (raw.get("Area Name") or "").strip() or None,
            "sex": (raw.get("Sex") or "").strip(),
            "age": (raw.get("Age") or "").strip(),
            "category_type": (raw.get("Category Type") or "").strip(),
            "category": (raw.get("Category") or "").strip(),
            "time_period": (raw.get("Time period") or "").strip(),
            "value": _to_number(raw.get("Value") or ""),
            "lower_ci_95": _to_number(raw.get("Lower CI 95.0 limit") or ""),
            "upper_ci_95": _to_number(raw.get("Upper CI 95.0 limit") or ""),
            "count_numerator": _to_number(raw.get("Count") or ""),
            "denominator": _to_number(raw.get("Denominator") or ""),
            "value_note": (raw.get("Value note") or "").strip() or None,
            "time_period_sortable": (raw.get("Time period Sortable") or "").strip() or None,
        })
    return rows


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _known_ons_codes(conn) -> set[str]:
    return {r["ons_code"] for r in conn.execute("SELECT ons_code FROM authorities")}


def _store_metadata(conn, client, module_name: str) -> None:
    ids = ",".join(str(i) for i in sorted(INDICATORS))
    result = client.get(METADATA_URL, params={"indicator_ids": ids})
    if not result.ok:
        db.record_review_item(conn, module_name, "fingertips_metadata_unavailable", ids,
                               json.dumps({"status": result.status_code}))
        return
    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError:
        db.record_parse_failure(conn, module_name, "metadata", ids[:200],
                                 "metadata response was not valid JSON", source_url=result.url)
        return

    provenance = _provenance(result)
    for key, meta in payload.items():
        try:
            indicator_id = int(key)
        except (TypeError, ValueError):
            continue
        descriptive = meta.get("Descriptive") or {}
        config = INDICATORS.get(indicator_id, {})
        db.upsert(conn, "fingertips_indicators", {
            "indicator_id": indicator_id,
            "indicator_name": descriptive.get("Name") or f"indicator {indicator_id}",
            "slug": config.get("slug"),
            "topic": config.get("topic"),
            "substance": config.get("substance"),
            "definition": descriptive.get("Definition"),
            "unit": (meta.get("Unit") or {}).get("Label"),
            **provenance,
        }, natural_key=["indicator_id"])


@register_module(
    "m12_fingertips",
    supports_since=False,
    depends_on=("m00_geography",),
    depends_note="resolves each indicator row to a known authority",
    since_note="Fingertips returns each indicator's full published series; filtering by year would discard the comparative history the series exists for",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m12_fingertips"
    conn = ctx.conn
    known_codes = _known_ons_codes(conn)
    if not known_codes:
        log.info("fingertips.no_authorities",
                  note="run m00_geography first or no row will resolve to an authority")

    indicator_ids = sorted(INDICATORS)
    if ctx.limit:
        indicator_ids = indicator_ids[:ctx.limit]

    values_written = 0
    la_rows = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        _store_metadata(conn, client, module_name)
        if not ctx.dry_run:
            conn.commit()

        for indicator_id in indicator_ids:
            for area_type_id in area_type_ids_for(indicator_id):
                result = client.get(DATA_URL, params={
                    "indicator_ids": indicator_id,
                    "child_area_type_id": area_type_id,
                    "parent_area_type_id": PARENT_AREA_TYPE_ID,
                })
                if not result.ok:
                    db.record_review_item(
                        conn, module_name, "fingertips_indicator_unavailable", str(indicator_id),
                        json.dumps({"area_type_id": area_type_id, "status": result.status_code}))
                    continue

                try:
                    rows = parse_indicator_csv(result.body.decode("utf-8-sig", errors="replace"))
                except Exception as exc:
                    db.record_parse_failure(
                        conn, module_name, "csv", str(indicator_id),
                        f"{type(exc).__name__}: {exc}", source_url=result.url)
                    continue

                if not rows:
                    db.record_parse_failure(
                        conn, module_name, "csv", str(indicator_id),
                        "indicator returned no rows for this area type",
                        source_url=result.url)
                    continue

                provenance = _provenance(result)
                indicator_la_rows = 0
                for row in rows:
                    area_level = classify_area_level(row["area_code"])
                    ons_code = row["area_code"] if (
                        area_level == "local_authority" and row["area_code"] in known_codes) else None
                    if area_level == "local_authority":
                        indicator_la_rows += 1

                    db.upsert(conn, "fingertips_la_values", {
                        "indicator_id": row["indicator_id"],
                        "area_code": row["area_code"],
                        "area_type_id": area_type_id,
                        "sex": row["sex"],
                        "age": row["age"],
                        "category_type": row["category_type"],
                        "category": row["category"],
                        "time_period": row["time_period"],
                        "area_name": row["area_name"],
                        "ons_code": ons_code,
                        "area_level": area_level,
                        "value": row["value"],
                        "lower_ci_95": row["lower_ci_95"],
                        "upper_ci_95": row["upper_ci_95"],
                        "count_numerator": row["count_numerator"],
                        "denominator": row["denominator"],
                        "value_note": row["value_note"],
                        "time_period_sortable": row["time_period_sortable"],
                        **provenance,
                    }, natural_key=["indicator_id", "area_code", "area_type_id", "sex",
                                     "age", "category_type", "category", "time_period"])
                    values_written += 1

                la_rows += indicator_la_rows
                log.info("fingertips.indicator_processed", indicator_id=indicator_id,
                          area_type_id=area_type_id, rows=len(rows),
                          local_authority_rows=indicator_la_rows)

                if not ctx.dry_run:
                    conn.commit()

    log.info("fingertips.run_complete", indicators=len(indicator_ids),
              values=values_written, local_authority_values=la_rows)
