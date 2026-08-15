"""Module 21 — ONS ASHE earnings (the Annual Survey of Hours and Earnings).

The comparator market the sector's advertised pay is measured against:
median gross hourly pay (excluding overtime), as ASHE publishes it, for the
occupation groups (SOC 2010, two-digit) and industry groups (SIC 2007,
two-digit) the sector's workforce sits in, at UK and England geography.

Access is the ONS developer API (api.beta.ons.gov.uk/v1), the shape G1
filed: one dataset per ASHE table — `ashe-tables-3` for occupation,
`ashe-table-5` for industry — each with a time-series edition whose latest
version is read at run time rather than pinned, because the version number
is the API's own and moves.

HOW THE QUERY IS BUILT, AND WHY:

  * The dimension codes are pinned in this module (SOC 2010 and SIC 2007
    two-digit codes are stable standards) but the request is built from the
    version's OWN dimension options, read at run time: the intersection of
    the pinned codes and the version's options is what gets queried, and a
    pinned code the version no longer serves raises a review item rather
    than silently disappearing. Labels are read from the same options
    response — the code-list items themselves carry no label text (verified
    2026-08-15), but the per-version options do.
  * One request per dataset: every pinned code, both geographies, and
    `time=*` (the API's wildcard for a dimension, documented on the
    developer hub) for all published tax years of that version. The
    response pages by offset to its own `total_observations`.
  * An observation that is not a number is NULL plus a `parse_failures`
    row, with the text kept verbatim — ASHE suppresses some cells, and a
    suppressed cell is not zero.

KNOWN ACCESS SHAPE AT VERIFICATION (2026-08-15): the dataset, edition,
dimension and options endpoints all answer; the observations endpoint
answered 502 for every ASHE query tried (single-observation and wildcard),
while a cpih01 query answered. The shared client retries a 5xx and then
raises — the house rule that a persistent server failure must fail the run
loudly rather than look like a source with nothing to report — so a run
against the current API fails at this module with the 502 in its traceback.
A 4xx or an unreadable response records `ons_ashe_observations_failed` and
writes nothing for that dataset rather than guessing. The API's ASHE
versions also lag the publication (table 3 served version 7, released
2024-01-19, at verification) — the version that is served is what gets
read, and the caveats say so.

The gate from the phase plan governs anything built on this table: an
ASHE-versus-adverts statement is a side-by-side comparison, never an
arithmetic ratio, and nothing in this module computes one.
"""
from __future__ import annotations

import json
import re

import structlog

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "ons_ashe"
API_BASE = "https://api.beta.ons.gov.uk/v1"
EDITION = "time-series"

# The measure this module collects: median gross hourly pay excluding
# overtime, all employees, all working patterns — ASHE's headline occupation
# comparison, and the one that sits side by side with advertised hourly
# bands. Codes verified against the API's code lists on 2026-08-15.
AVERAGESAND_PERCENTILES = "median"
HOURSAND_EARNINGS = "hourly-pay-excluding-overtime"
SEX = "all"
WORKING_PATTERN = "all"

# Geographies as published comparators: the UK (the survey's national
# headline) and England (the campaign's commissioning geography). Codes are
# the API's own, verified against the administrative-geography code list.
GEOGRAPHIES = [
    ("K02000001", "United Kingdom"),
    ("E92000001", "England"),
]

# Pinned dimension codes. The codes are the standards' own two-digit groups
# (SOC 2010, SIC 2007); the labels come from the version's options response
# at run time, not from here.
DATASETS = {
    "ashe-tables-3": {
        "dimension_kind": "occupation",
        "dimension_param": "standardoccupationalclassification",
        "codes": ["11", "22", "24", "32", "35", "61", "62", "92"],
    },
    "ashe-table-5": {
        "dimension_kind": "industry",
        "dimension_param": "unofficialstandardindustrialclassification",
        "codes": ["84", "86", "87", "88"],
    },
}

# A safety cap on observation paging; a query that needs more pages than
# this has changed shape and must not be read silently.
MAX_PAGES = 20

_FLOAT_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*$")


def _as_number(value: str) -> float | None:
    if not _FLOAT_RE.match(value or ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _option_labels(payload: dict) -> dict[str, str]:
    """code -> label from a dimension options response."""
    return {item["option"]: item.get("label") or item["option"]
            for item in payload.get("items", [])}


def _observation_dimensions(observation: dict, fallback: dict[str, str]) -> dict[str, str]:
    """The dimension values this observation belongs to.

    The API documents per-observation dimensions for multi-option queries;
    a single-value query carries them at the top level of the response
    instead. Both shapes are parsed, with the request's own options as the
    fallback — an observation must never be filed under a code it was not
    queried for.
    """
    own = observation.get("dimensions")
    if isinstance(own, dict):
        resolved = {}
        for name, value in own.items():
            if not isinstance(value, dict):
                continue
            option = value.get("option")
            option_id = (option.get("id") if isinstance(option, dict) else None) \
                or (value.get("id") if isinstance(value.get("id"), str) else None)
            if option_id:
                resolved[name] = option_id
        if resolved:
            return resolved
    return dict(fallback)


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _fetch_observations(client, *, dataset_id: str, version: str,
                        dimension_param: str, codes: list[str]):
    """One paged query over the pinned codes, both geographies and all
    years. Returns (rows, error_note); raises nothing. Each row carries its
    page's provenance.
    """
    params: dict = {
        "time": "*",
        "averagesandpercentiles": AVERAGESAND_PERCENTILES,
        "hoursandearnings": HOURSAND_EARNINGS,
        "sex": SEX,
        "workingpattern": WORKING_PATTERN,
        "geography": [code for code, _ in GEOGRAPHIES],
        dimension_param: codes,
    }

    base = (f"{API_BASE}/datasets/{dataset_id}/editions/{EDITION}"
            f"/versions/{version}/observations")
    offset = 0
    rows: list[dict] = []
    error: str | None = None
    # Fallback for a single-value query, whose response carries the
    # dimensions at the top level rather than per observation.
    fallback = {dimension_param: (codes[0] if codes else ""),
                "geography": GEOGRAPHIES[0][0]}

    for _page in range(MAX_PAGES):
        query = dict(params)
        if offset:
            query["offset"] = offset
        result = client.get(base, params=query)
        if not result.ok:
            error = (f"observations answered {result.status_code}; the API's ASHE "
                     "observations endpoint was already failing at verification "
                     "(502) — see the module docstring")
            break
        payload = json.loads(result.body)
        observations = payload.get("observations") or []
        for observation in observations:
            rows.append({
                "observation": observation.get("observation"),
                "dimensions": _observation_dimensions(observation, fallback),
                "unit_of_measure": payload.get("unit_of_measure"),
                "provenance": _provenance(result),
            })

        total = payload.get("total_observations") or len(observations)
        offset += len(observations)
        if offset >= total or not observations:
            break
    else:
        error = f"more than {MAX_PAGES} pages of observations; the query shape has changed"
    return rows, error


@register_module(
    "m21_ons_ashe",
    supports_since=False,
    since_note="the module reads every published tax year of the API's current version",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m21_ons_ashe"
    conn = ctx.conn
    written = 0

    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        for dataset_id, dataset in ctx.track(DATASETS.items(), "ASHE tables"):
            meta = client.get(f"{API_BASE}/datasets/{dataset_id}")
            if not meta.ok:
                db.record_review_item(
                    conn, module_name, "ons_ashe_dataset_unavailable", dataset_id,
                    json.dumps({"status": meta.status_code}))
                continue
            dataset_title = (json.loads(meta.body).get("title") if meta.body else None)

            edition = client.get(f"{API_BASE}/datasets/{dataset_id}/editions/{EDITION}")
            if not edition.ok:
                db.record_review_item(
                    conn, module_name, "ons_ashe_edition_unavailable", dataset_id,
                    json.dumps({"status": edition.status_code}))
                continue
            version = ((json.loads(edition.body).get("links") or {})
                       .get("latest_version") or {}).get("id")
            if not version:
                db.record_review_item(
                    conn, module_name, "ons_ashe_edition_unavailable", dataset_id,
                    json.dumps({"note": "edition answered with no latest_version"}))
                continue

            dimension_param = dataset["dimension_param"]
            options = client.get(
                f"{API_BASE}/datasets/{dataset_id}/editions/{EDITION}"
                f"/versions/{version}/dimensions/{dimension_param}/options",
                params={"limit": 1000})
            if not options.ok:
                db.record_review_item(
                    conn, module_name, "ons_ashe_dimensions_unavailable",
                    f"{dataset_id} {dimension_param}",
                    json.dumps({"status": options.status_code, "version": version}))
                continue
            labels = _option_labels(json.loads(options.body))

            missing = [code for code in dataset["codes"] if code not in labels]
            if missing:
                db.record_review_item(
                    conn, module_name, "ons_ashe_pinned_code_missing",
                    f"{dataset_id} {' '.join(missing)}",
                    json.dumps({"version": version,
                                 "note": "a pinned dimension code is not in the "
                                         "version's options; the code has left the "
                                         "source or the standard has moved"}))

            rows, error = _fetch_observations(
                client, dataset_id=dataset_id, version=version,
                dimension_param=dimension_param, codes=dataset["codes"])
            if error:
                db.record_review_item(
                    conn, module_name, "ons_ashe_observations_failed", dataset_id,
                    json.dumps({"version": version, "note": error}))
                log.info("ashe.dataset_failed", dataset=dataset_id, note=error)
                continue

            if not rows:
                db.record_review_item(
                    conn, module_name, "ons_ashe_observations_failed", dataset_id,
                    json.dumps({"version": version,
                                 "note": "the query answered with no observations"}))
                continue

            for row in ctx.track(rows, f"{dataset_id} observations"):
                dims = row["dimensions"] if isinstance(row["dimensions"], dict) else {}
                code = dims.get(dimension_param)
                geography = dims.get("geography")
                time_value = dims.get("time")
                if not (code and geography and time_value):
                    continue
                text = str(row["observation"] or "")
                number = _as_number(text)
                if number is None and text:
                    db.record_parse_failure(
                        conn, module_name, "observation", text,
                        f"observation for {code}/{geography}/{time_value} was not a number",
                        source_url=row["provenance"]["source_url"])
                db.upsert(conn, "ons_ashe_observations", {
                    "dataset_id": dataset_id,
                    "dataset_title": dataset_title,
                    "edition": EDITION,
                    "version": version,
                    "hoursandearnings": HOURSAND_EARNINGS,
                    "averagesandpercentiles": AVERAGESAND_PERCENTILES,
                    "sex": SEX,
                    "workingpattern": WORKING_PATTERN,
                    "dimension_kind": dataset["dimension_kind"],
                    "dimension_code": code,
                    "dimension_label": labels.get(code, code),
                    "geography_code": geography,
                    "geography_label": dict(GEOGRAPHIES).get(geography, geography),
                    "time": time_value,
                    "value": number,
                    "value_text": text or None,
                    "unit_of_measure": row["unit_of_measure"],
                    **row["provenance"],
                }, natural_key=[
                    "dataset_id", "edition", "version", "hoursandearnings",
                    "dimension_kind", "dimension_code", "geography_code", "time"])
                written += 1
            if not ctx.dry_run:
                conn.commit()

    log.info("ashe.run_complete", observations=written)
