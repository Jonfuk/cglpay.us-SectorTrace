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
  * One request per (geography, code) pair, `time=*` (the API's wildcard for
    a dimension, documented on the developer hub) for all published tax
    years of that version. NOT one request naming every code and both
    geographies at once — verified 2026-08-22, the API now answers a
    multi-valued query with 400 "multi-valued query parameters for the
    following dimensions", which it did not at the 2026-08-15 verification.
    Each combination's response pages by offset to its own
    `total_observations`.
  * An observation that is not a number is NULL plus a `parse_failures`
    row, with the text kept verbatim — ASHE suppresses some cells, and a
    suppressed cell is not zero.
  * `ashe-table-5`'s industry dimension has two names depending on which
    endpoint is asked (verified 2026-08-22): `/dimensions/{name}/options`
    answers under `unofficialstandardindustrialclassification` with real
    codes and labels (code list `sic-unofficial`) and answers empty under
    `standardindustrialclassification`; `/observations` is the other way
    round — it 400s on the "unofficial" name ("these dimensions do not
    exist for this version") and wants the name without it. So the module
    tracks both names for this dataset: `dimension_param` for options and
    labels, `observations_dimension_param` for the query itself.

KNOWN ACCESS SHAPE AT VERIFICATION (2026-08-15, re-verified 2026-08-22): the
dataset, edition, dimension and options endpoints all answer; the
observations endpoint does not serve ASHE data at all right now, whatever
the query looks like. At 2026-08-15 a multi-valued query answered 502; at
2026-08-22 the same shape answers a fast 400 (the new multi-value
validation above), but a corrected single-valued, single-year query —
tested against every published version of ashe-tables-3, 1 through 7 —
still just hangs (30-90s, no bytes) or answers 502. The identical shape
against a known-good dataset (`cpih01`) answers in well under a second.
This is a source-side outage specific to the ASHE observations endpoint,
not a symptom of the query shape, and no version pin or retry policy on our
side will make it answer. The per-combination loop below fails fast on the
first transport-level failure (timeout or persistent 5xx) for a dataset
rather than repeating a multi-minute retry-and-backoff cycle across every
remaining code and geography — that would be several minutes of politely-
paced requests against a host that is not going to answer, for a beta API
whose own docs warn it changes without notice. A 4xx on an individual
combination is cheap and does not stop the others; it records
`ons_ashe_observations_failed` and moves on. The API's ASHE versions also
lag the publication (table 3 served version 7, released 2024-01-19, at
verification) — the version that is served is what gets read, and the
caveats say so.

The gate from the phase plan governs anything built on this table: an
ASHE-versus-adverts statement is a side-by-side comparison, never an
arithmetic ratio, and nothing in this module computes one.
"""
from __future__ import annotations

import json
import re

import httpx
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
        # See the module docstring: /observations rejects the name above
        # (which is what /dimensions/{name}/options needs) and wants this
        # one instead. Verified 2026-08-22.
        "observations_dimension_param": "standardindustrialclassification",
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
    """One paged query per (geography, code) pair — see the module docstring
    for why: the API now 400s a request naming every code and both
    geographies at once. Returns (rows, errors); raises nothing itself, but
    stops issuing further combinations for this dataset the moment one
    raises rather than answers (a timeout or a persistent 5xx, after the
    shared client's own retries are exhausted) — that is the endpoint not
    answering at all, and repeating a multi-minute retry cycle across every
    remaining combination would not change that. Each row carries its own
    request's provenance.
    """
    base = (f"{API_BASE}/datasets/{dataset_id}/editions/{EDITION}"
            f"/versions/{version}/observations")
    rows: list[dict] = []
    errors: list[str] = []

    for geography, _ in GEOGRAPHIES:
        for code in codes:
            params: dict = {
                "time": "*",
                "averagesandpercentiles": AVERAGESAND_PERCENTILES,
                "hoursandearnings": HOURSAND_EARNINGS,
                "sex": SEX,
                "workingpattern": WORKING_PATTERN,
                "geography": geography,
                dimension_param: code,
            }
            # Fallback for this single-value query, whose response carries
            # the dimensions at the top level rather than per observation.
            fallback = {dimension_param: code, "geography": geography}
            offset = 0

            for _page in range(MAX_PAGES):
                query = dict(params)
                if offset:
                    query["offset"] = offset
                try:
                    result = client.get(base, params=query)
                except httpx.HTTPError as exc:
                    errors.append(
                        f"{geography}/{code}: request raised {exc.__class__.__name__} "
                        "rather than answering — the observations endpoint is not "
                        "responding; not trying the remaining combinations for this dataset")
                    return rows, errors
                if not result.ok:
                    errors.append(f"{geography}/{code}: observations answered {result.status_code}")
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
                errors.append(f"{geography}/{code}: more than {MAX_PAGES} pages of "
                               "observations; the query shape has changed")

    return rows, errors


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

            # See the module docstring: ashe-table-5's dimension has a
            # different name on /observations than the one that answers
            # /dimensions/{name}/options above.
            obs_dimension_param = dataset.get("observations_dimension_param", dimension_param)
            rows, errors = _fetch_observations(
                client, dataset_id=dataset_id, version=version,
                dimension_param=obs_dimension_param, codes=dataset["codes"])

            if not rows and not errors:
                db.record_review_item(
                    conn, module_name, "ons_ashe_observations_failed", dataset_id,
                    json.dumps({"version": version,
                                 "note": "the query answered with no observations"}))
                continue

            if errors:
                # Real, validated rows (if any) are still written below — a
                # failure on one geography/code combination is not a reason
                # to discard the ones that answered. See the docstring for
                # why the endpoint currently fails at all.
                db.record_review_item(
                    conn, module_name, "ons_ashe_observations_failed", dataset_id,
                    json.dumps({"version": version, "failed_combinations": len(errors),
                                 "rows_recovered": len(rows), "notes": errors[:5]}))
                log.info("ashe.dataset_partial_failure", dataset=dataset_id,
                          failed_combinations=len(errors), rows_recovered=len(rows))

            for row in ctx.track(rows, f"{dataset_id} observations"):
                dims = row["dimensions"] if isinstance(row["dimensions"], dict) else {}
                code = dims.get(obs_dimension_param)
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
