"""Module 19 — data.gov.uk CKAN catalogue.

The central open-data catalogue: datasets searchable by organisation and
keyword, with resource URLs. Discovery metadata, not the data itself — this
module records what datasets exist and where their resources live, which is
what G5 (spend files), B4 (website coverage), W-13 (what an authority
publishes) and F1 (the sector universe) each need to find their raw material.

Two passes, both over the documented CKAN `package_search` action:

  * **Keyword pass** — the substance-misuse vocabulary already defined in
    `pipeline/keywords.py`. A dataset found this way is stored with the terms
    that found it; the terms accumulate across runs and across passes, so a
    row's `matched_terms` says everything this pipeline has found it under.
  * **Organisation pass** — the catalogue's organisation list is fetched
    once, and each organisation title is normalise-matched against the
    authorities and providers tables. Only exact matches are queried; a
    council whose catalogue sits under a differently-spelled organisation is
    not guessed, and is not a review item — the universe work (F1) owns
    reconciling names at scale.

Bound and honest:

  * `package_search` is paged; each query is read to the catalogue's own
    `count`, capped at MAX_PAGES a query. A query that hits the cap raises a
    review item naming the cap, so "this catalogue has N relevant datasets"
    is never silently "the first 300".
  * The catalogue is only what data.gov.uk harvests. A dataset that exists
    but is not catalogued is invisible here, and absence must never be read
    as absence of the data — only as absence from this index.
  * Licences are stored per dataset as the catalogue publishes them, because
    the catalogue mixes OGL and non-OGL datasets. The module itself records
    metadata under OGL; each dataset's own terms travel on its row.
"""
from __future__ import annotations

import json
import re

import structlog

from pipeline import db, providers
from pipeline.http import PipelineHTTPClient
from pipeline.keywords import SUBSTANCE_MISUSE_KEYWORDS
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "data_gov_uk"
API_BASE = "https://www.data.gov.uk/api/3/action"
PACKAGE_SEARCH = f"{API_BASE}/package_search"
ORGANIZATION_LIST = f"{API_BASE}/organization_list"
PAGE_SIZE = 100
MAX_PAGES = 3  # 300 datasets per query before the cap review item fires


def _normalise_org_name(name: str) -> str:
    text = re.sub(r"[^\w\s]", " ", (name or "").lower())
    text = re.sub(r"\b(the|council|councils|borough|metropolitan|city|county)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _existing(conn, table: str, key: dict) -> dict | None:
    row = conn.execute(
        f"SELECT * FROM {table} WHERE {' AND '.join(f'{k} = ?' for k in key)}",
        tuple(key.values())).fetchone()
    return dict(row) if row else None


def _merge_row(existing: dict | None, additions: dict) -> dict:
    """Merge across passes: matched_terms, matched_ons_code and
    matched_provider_key accumulate rather than overwrite."""
    merged = dict(additions)
    if not existing:
        return merged
    for field in ("matched_terms", "matched_ons_code", "matched_provider_key"):
        old = existing.get(field)
        new = additions.get(field)
        if old and new:
            values = [v for v in (str(old), str(new)) if v]
            merged[field] = ",".join(dict.fromkeys(
                item for v in values for item in v.split(",") if item))
        elif old:
            merged[field] = old
    return merged


def _terms_from(terms: str | None, extra: str) -> str | None:
    """Comma-joined matched terms, or None when there are none — a dataset
    found only by the organisation pass must read as having no keyword terms,
    not an empty string that looks like a term."""
    values = [v for v in (terms or "").split(",") if v]
    if extra and extra not in values:
        values.append(extra)
    return ",".join(values) or None


def _store_dataset(conn, module_name: str, dataset: dict, result, *,
                   matched_term: str | None, ons_code: str | None,
                   provider_key: str | None) -> int:
    """One dataset row, merged with whatever earlier passes found it."""
    dataset_id = dataset.get("id")
    if not dataset_id:
        return 0
    organisation = dataset.get("organization") or {}
    existing = _existing(conn, "data_gov_uk_datasets", {"dataset_id": dataset_id})
    row = _merge_row(existing, {
        "dataset_id": dataset_id,
        "title": dataset.get("title"),
        "notes": dataset.get("notes"),
        "organisation_name": organisation.get("title"),
        "organisation_id": organisation.get("id"),
        "license_id": dataset.get("license_id"),
        "license_title": dataset.get("license_title"),
        "license_url": dataset.get("license_url"),
        "url": dataset.get("url"),
        "date_released": dataset.get("date_released"),
        "date_updated": dataset.get("date_updated"),
        "metadata_modified": dataset.get("metadata_modified"),
        "dataset_state": dataset.get("state"),
        "matched_terms": _terms_from(existing.get("matched_terms") if existing else None,
                                     matched_term or ""),
        "matched_ons_code": ons_code,
        "matched_provider_key": provider_key,
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    })
    db.upsert(conn, "data_gov_uk_datasets", row, natural_key=["dataset_id"])

    for resource in dataset.get("resources") or []:
        resource_id = resource.get("id")
        if not resource_id:
            continue
        db.upsert(conn, "data_gov_uk_resources", {
            "dataset_id": dataset_id,
            "resource_id": resource_id,
            "resource_name": resource.get("name"),
            "resource_format": resource.get("format"),
            "resource_url": resource.get("url"),
            "resource_description": resource.get("description"),
            "resource_position": resource.get("position"),
            "source_url": result.url,
            "retrieved_at": result.retrieved_at.isoformat(),
            "http_status": result.status_code,
            "source_system": SOURCE_SYSTEM,
            "payload_sha256": result.payload_sha256,
        }, natural_key=["dataset_id", "resource_id"])
    return 1


def _search(client, conn, module_name: str, *, term: str | None = None,
            org: str | None = None,
            ons_code: str | None = None, provider_key: str | None = None) -> int:
    """One paged query. Returns rows written. Raises nothing; a failed page
    stops the query and is recorded."""
    params = {"rows": PAGE_SIZE, "start": 0}
    if term:
        params["q"] = term
    if org:
        params["fq"] = f"organization:{org}"
        params["q"] = ""

    written = 0
    for _page in range(MAX_PAGES):
        result = client.get(PACKAGE_SEARCH, params=params)
        if not result.ok:
            db.record_review_item(
                conn, module_name, "data_gov_uk_search_failed",
                term or org or "", json.dumps({"status": result.status_code,
                                                "params": params}))
            return written
        payload = json.loads(result.body)
        if not payload.get("success"):
            db.record_review_item(
                conn, module_name, "data_gov_uk_search_failed",
                term or org or "", json.dumps({"error": payload.get("error")}))
            return written
        result_data = payload.get("result") or {}
        for dataset in result_data.get("results") or []:
            written += _store_dataset(conn, module_name, dataset, result,
                                      matched_term=term, ons_code=ons_code,
                                      provider_key=provider_key)
        count = result_data.get("count", 0)
        params["start"] += len(result_data.get("results") or [])
        if params["start"] >= count or not result_data.get("results"):
            break
    else:
        if term:
            db.record_review_item(
                conn, module_name, "data_gov_uk_query_capped", term or org or "",
                json.dumps({"note": f"results exceed {MAX_PAGES} pages of {PAGE_SIZE}; "
                                     "stored only the first 300"}))
    return written


@register_module(
    "m19_data_gov_uk",
    supports_since=False,
    depends_on=("m00_geography",),
    depends_note="the per-authority pass reads the authorities table",
    since_note="the catalogue is a discovery index of current metadata, not a dated stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m19_data_gov_uk"
    conn = ctx.conn
    providers.seed_providers(conn, commit=not ctx.dry_run)

    written = 0
    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        ctx.phase("searching the catalogue by keyword")
        for term in ctx.track(SUBSTANCE_MISUSE_KEYWORDS, "keywords"):
            written += _search(client, conn, module_name, term=term)
            if not ctx.dry_run:
                conn.commit()

        ctx.phase("matching catalogue organisations to authorities and providers")
        # CKAN's default organization_list response is a list of names.  The
        # organisation pass needs titles and slugs for exact matching, so ask
        # explicitly for the full records rather than indexing strings as
        # though they were dictionaries.
        org_result = client.get(ORGANIZATION_LIST, params={"all_fields": "true"})
        if org_result.ok:
            payload = json.loads(org_result.body)
            if payload.get("success"):
                orgs = {_normalise_org_name(o["title"]): o["name"]
                        for o in payload.get("result", [])}

                authority_rows = conn.execute(
                    "SELECT ons_code, name FROM authorities WHERE name IS NOT NULL").fetchall()
                provider_rows = conn.execute(
                    "SELECT provider_key, canonical_name FROM providers").fetchall()

                matched: set[str] = set()
                for row in authority_rows:
                    key = _normalise_org_name(row["name"])
                    org_name = orgs.get(key)
                    if org_name and org_name not in matched:
                        matched.add(org_name)
                        written += _search(client, conn, module_name, org=org_name,
                                           ons_code=row["ons_code"])
                        if not ctx.dry_run:
                            conn.commit()
                for row in provider_rows:
                    key = _normalise_org_name(row["canonical_name"])
                    org_name = orgs.get(key)
                    if org_name and org_name not in matched:
                        matched.add(org_name)
                        written += _search(client, conn, module_name, org=org_name,
                                           provider_key=row["provider_key"])
                        if not ctx.dry_run:
                            conn.commit()
        else:
            db.record_review_item(
                conn, module_name, "data_gov_uk_organisations_unavailable", ORGANIZATION_LIST,
                json.dumps({"status": org_result.status_code}))

    log.info("data_gov_uk.run_complete", datasets=written)
