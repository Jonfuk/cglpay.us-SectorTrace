"""Module 42 — Nomis labour-market context.

Collects the first implementation slice agreed in JON-16: Annual Survey of
Hours and Earnings (ASHE) headline observations for English local authorities,
from both the residence-based (ASHER) and workplace-based (ASHE) Nomis
datasets.

This is context, not provider pay. It is kept in its own table and evidence
layer and is never joined to advertised pay to create a ratio or a ranking.
The existing m21_ons_ashe module remains the direct ONS comparator for the
occupation and industry slices that Nomis does not publish at local-authority
level.

Nomis's ASHE query dimensions are stable on the dataset pages: total sex (7),
median item (2), hourly pay excluding overtime (6), and total hours worked
(9). The local-authority selector TYPE424 is Nomis's "district / unitary as
of April 2023" geography. The query asks for all published time periods and
pages CSV responses so a future release cannot silently truncate the result.

APSNEW is intentionally not collected here yet. Its 2,054-variable catalogue
needs a named, reviewed selection before it can become evidence; the source
and this deferral are recorded in the public caveat and review metadata.
"""
from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Iterable

import httpx
import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "nomis_labour_market_context"
API_BASE = "https://www.nomisweb.co.uk/api/v01/dataset"

# Nomis codes verified through the ASHE resident/workplace query interface.
SEX_TOTAL = "7"
ITEM_MEDIAN = "2"
PAY_HOURLY_EXCLUDING_OVERTIME = "6"
PAY_HOURS_WORKED_TOTAL = "9"
PAY_CODES = (PAY_HOURLY_EXCLUDING_OVERTIME, PAY_HOURS_WORKED_TOTAL)
GEOGRAPHY_SELECTOR = "TYPE424"
PAGE_SIZE = 5000
MAX_PAGES = 20

# Nomis exposes the same headline dimensions for both analysis bases.
DATASETS = (
    {
        "dataset_id": "ASHER",
        "analysis": "resident",
        "title": "Annual Survey of Hours and Earnings — resident analysis",
        "official_url": "https://www.nomisweb.co.uk/datasets/asher",
    },
    {
        "dataset_id": "ASHE",
        "analysis": "workplace",
        "title": "Annual Survey of Hours and Earnings — workplace analysis",
        "official_url": "https://www.nomisweb.co.uk/datasets/ashe",
    },
)

_MISSING_VALUES = {"", "-", "–", "—", "..", ":", "na", "n/a", "null"}
_NUMBER_RE = re.compile(r"^[-+]?\d+(?:\.\d+)?$")

_SELECT = ",".join((
    "GEOGRAPHY_CODE",
    "GEOGRAPHY_NAME",
    "SEX",
    "SEX_NAME",
    "ITEM",
    "ITEM_NAME",
    "PAY",
    "PAY_NAME",
    "TIME",
    "OBS_VALUE",
    "OBS_STATUS",
    "OBS_CONF",
    "RECORD_OFFSET",
    "RECORD_COUNT",
))


def _value(raw: str | None) -> float | None:
    """Parse an observation without turning suppression into zero."""
    text = (raw or "").strip().replace(",", "")
    if text.casefold() in _MISSING_VALUES:
        return None
    if not _NUMBER_RE.fullmatch(text):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _field(row: dict[str, str], name: str) -> str:
    """Read a Nomis CSV field case-insensitively and trim it."""
    return (row.get(name) or "").strip()


def parse_csv(text: str) -> tuple[list[dict[str, str]], int | None]:
    """Parse one Nomis CSV page.

    Column order is deliberately ignored: Nomis can add output columns and
    callers may change Select without moving the evidence fields. The returned
    count is the API's full result count when it supplies RECORD_COUNT.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows: list[dict[str, str]] = []
    total: int | None = None
    for raw in reader:
        row = {str(key).strip().upper(): (value or "").strip()
               for key, value in raw.items() if key is not None}
        count = _field(row, "RECORD_COUNT")
        if count.isdigit():
            total = int(count)
        if any(_field(row, key) for key in ("GEOGRAPHY_CODE", "OBS_VALUE", "TIME")):
            rows.append(row)
    return rows, total


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _query_params(offset: int) -> dict[str, str]:
    params = {
        "geography": GEOGRAPHY_SELECTOR,
        "sex": SEX_TOTAL,
        "item": ITEM_MEDIAN,
        "pay": ",".join(PAY_CODES),
        "time": "first,latest",
        "select": _SELECT,
        "RecordLimit": str(PAGE_SIZE),
    }
    if offset:
        params["RecordOffset"] = str(offset)
    return params


def _fetch_dataset(client, dataset_id: str) -> tuple[list[dict], list[str]]:
    """Fetch all pages for one Nomis dataset, retaining page provenance."""
    rows: list[dict] = []
    errors: list[str] = []
    url = f"{API_BASE}/{dataset_id}.data.csv"
    offset = 0

    for _page in range(MAX_PAGES):
        try:
            result = client.get(url, params=_query_params(offset))
        except httpx.HTTPError as exc:
            errors.append(f"request raised {type(exc).__name__}: {exc}")
            break
        if not result.ok:
            errors.append(f"HTTP {result.status_code}")
            break

        try:
            page_rows, total = parse_csv(result.body.decode("utf-8-sig", errors="replace"))
        except (AttributeError, UnicodeError, csv.Error) as exc:
            errors.append(f"CSV parse failed: {type(exc).__name__}: {exc}")
            break

        if not page_rows:
            if not rows:
                errors.append("response contained no data rows")
            break

        provenance = _provenance(result)
        rows.extend({"data": row, "provenance": provenance} for row in page_rows)
        next_offset = offset + len(page_rows)

        if total is None or next_offset >= total:
            break
        if next_offset <= offset:
            errors.append("pagination did not advance")
            break
        offset = next_offset
    else:
        errors.append(f"more than {MAX_PAGES} pages; result may be truncated")

    return rows, errors


def _rows_for_storage(
    dataset: dict,
    fetched_rows: Iterable[dict],
    conn,
    module_name: str,
) -> list[dict]:
    output: list[dict] = []
    for wrapped in fetched_rows:
        raw = wrapped["data"]
        geography_code = _field(raw, "GEOGRAPHY_CODE")
        time_value = _field(raw, "TIME")
        pay = _field(raw, "PAY")
        if not (geography_code and time_value and pay):
            db.record_parse_failure(
                conn, module_name, "nomis_row",
                json.dumps(raw, sort_keys=True)[:2000],
                "row lacked GEOGRAPHY_CODE, TIME or PAY",
                source_url=wrapped["provenance"]["source_url"],
            )
            continue

        raw_value = _field(raw, "OBS_VALUE")
        value = _value(raw_value)
        status = _field(raw, "OBS_STATUS") or None
        if raw_value and value is None and raw_value.casefold() not in _MISSING_VALUES:
            db.record_parse_failure(
                conn, module_name, "OBS_VALUE", raw_value,
                f"Nomis {dataset['dataset_id']} observation was not numeric",
                source_url=wrapped["provenance"]["source_url"],
            )

        output.append({
            "dataset_id": dataset["dataset_id"],
            "analysis": dataset["analysis"],
            "dataset_title": dataset["title"],
            "geography_selector": GEOGRAPHY_SELECTOR,
            "geography_code": geography_code,
            "geography_name": _field(raw, "GEOGRAPHY_NAME") or None,
            "sex": _field(raw, "SEX") or SEX_TOTAL,
            "sex_name": _field(raw, "SEX_NAME") or None,
            "item": _field(raw, "ITEM") or ITEM_MEDIAN,
            "item_name": _field(raw, "ITEM_NAME") or None,
            "pay": pay,
            "pay_name": _field(raw, "PAY_NAME") or None,
            "time": time_value,
            "value": value,
            "value_text": raw_value or None,
            "observation_status": status,
            "observation_confidence": _field(raw, "OBS_CONF") or None,
            **wrapped["provenance"],
        })
    return output


@register_module(
    "m42_nomis_context",
    supports_since=False,
    depends_on=("m00_geography",),
    depends_note="Nomis local-authority observations are collected as published; geography joins are resolved by ONS code in downstream queries",
    since_note="the ASHE datasets are revised and the collector retains the full published time series",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m42_nomis_context"
    datasets = DATASETS[:ctx.limit] if ctx.limit else DATASETS
    written = 0

    # Keep this decision visible in the review queue: APSNEW is available but
    # has no single agreed variable for this product yet.
    db.record_review_item(
        ctx.conn,
        module_name,
        "nomis_dataset_deferred",
        "APSNEW",
        json.dumps({
            "reason": "variable catalogue is broad; implement a named slice only",
            "source_url": "https://www.nomisweb.co.uk/datasets/apsnew",
        }),
    )

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=ctx.conn) as client:
        for dataset in ctx.track(datasets, "Nomis ASHE datasets"):
            fetched, errors = _fetch_dataset(client, dataset["dataset_id"])
            if errors:
                db.record_review_item(
                    ctx.conn, module_name, "nomis_dataset_fetch_failed",
                    dataset["dataset_id"],
                    json.dumps({"errors": errors[:5], "rows_recovered": len(fetched)}),
                )
            storage_rows = _rows_for_storage(dataset, fetched, ctx.conn, module_name)
            if storage_rows:
                db.upsert_many(
                    ctx.conn,
                    "nomis_labour_market_observations",
                    storage_rows,
                    natural_key=[
                        "dataset_id", "geography_code", "sex", "item", "pay", "time",
                    ],
                )
                written += len(storage_rows)
            elif not errors:
                db.record_review_item(
                    ctx.conn, module_name, "nomis_dataset_empty",
                    dataset["dataset_id"],
                    json.dumps({"note": "successful response contained no usable rows"}),
                )
            if not ctx.dry_run:
                ctx.conn.commit()

    log.info("nomis_context.run_complete", datasets=len(datasets), observations=written)
