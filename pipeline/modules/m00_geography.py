"""Module 0 — geography reference spine.

Builds `authorities` (every English local authority with public health
responsibility — county, unitary, London borough, metropolitan district —
plus the non-metropolitan districts nested inside two-tier counties, needed
because buyer/committee names in later modules are often district-level)
and `authority_successors` (local government reorganisation edges).

Source: ONS Open Geography Portal, published as ArcGIS Online feature
services under the ONSGeography_data organisation. Layer item ids and even
field names (e.g. CTYUA25CD -> CTYUA26CD) are versioned per release, so
everything here is discovered by searching ArcGIS Online content at run
time rather than hardcoded — per the brief, because "these are versioned by
year and the IDs change."

LGR handling: a retired ons_code's successor(s) are resolved by measuring
the actual geometric overlap between its last-known boundary and the
boundaries newly appearing in the same transition — never guessed from
names or from general knowledge of which reorganisations happened. County
(E10) and non-metropolitan-district (E07) retirements/additions are pooled
across both the Counties-and-Unitary-Authorities and Local-Authority-
Districts series so a county abolished alongside its districts (e.g. a
county replaced by unitary authorities) resolves against candidates from
either series. Where no successor clears the overlap threshold, the
predecessor is still recorded (active_to set) and a review_queue entry
captures the gap — never a fabricated edge.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import structlog
from shapely.geometry import shape

from pipeline import db
from pipeline.http import PipelineHTTPClient
from pipeline.registry import ModuleContext, register_module

log = structlog.get_logger()

SOURCE_SYSTEM = "ons_open_geography_portal"
ARCGIS_SEARCH_URL = "https://www.arcgis.com/sharing/rest/search"
ARCGIS_ITEM_URL = "https://www.arcgis.com/sharing/rest/content/items/{item_id}"
ONS_OWNER = "ONSGeography_data"

# Local government reorganisation only matters to us from the window the
# brief cares about onward; older vintages exist but add nothing.
MIN_VINTAGE_DATE = date(2020, 1, 1)

# Fraction of a retired authority's area that must be covered by a new
# authority's boundary before we record it as a successor.
OVERLAP_THRESHOLD = 0.05

TYPE_BY_PREFIX = {
    "E10": "county",
    "E06": "unitary",
    "E08": "metropolitan_district",
    "E09": "london_borough",
    "E07": "non_metropolitan_district",
}

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}

# "{geography} (Month Year) Boundaries {extent} {resolution}", optionally
# with a trailing "(V2)"-style correction suffix.
TITLE_RE = re.compile(
    r"^(?P<geography>.+?)\s*\((?P<month>[A-Za-z]+)\s+(?P<year>20\d{2})\)\s*Boundaries\s+"
    r"(?P<extent>UK|EW|GB|EN)\s+(?P<resolution>BUC|BGC|BFC|BFE|BSC)(?:\s*\(V\d+\))?$"
)

FIELD_PATTERNS = {
    "lad_code": re.compile(r"^LAD\d{2}CD$"),
    "lad_name": re.compile(r"^LAD\d{2}NM$"),
    "rgn_code": re.compile(r"^RGN\d{2}CD$"),
    "rgn_name": re.compile(r"^RGN\d{2}NM$"),
    "ctyua_code": re.compile(r"^CTYUA\d{2}CD$"),
    "ctyua_name": re.compile(r"^CTYUA\d{2}NM$"),
}


class DiscoveryError(RuntimeError):
    """Raised when the expected ONS layer/field shape can't be found. This
    should stop the run rather than silently fall back to a guess.
    """


def _find_field(field_names: list[str], key: str) -> str:
    pattern = FIELD_PATTERNS[key]
    matches = [f for f in field_names if pattern.match(f)]
    if len(matches) != 1:
        raise DiscoveryError(
            f"Expected exactly one field matching {pattern.pattern!r}, found {matches} in {field_names}"
        )
    return matches[0]


def _authority_type(ons_code: str) -> str | None:
    return TYPE_BY_PREFIX.get(ons_code[:3])


def _arcgis_search(client: PipelineHTTPClient, query: str, num: int = 100) -> list[dict]:
    result = client.get(ARCGIS_SEARCH_URL, params={
        "q": query, "f": "json", "num": num, "sortField": "created", "sortOrder": "desc",
    })
    if not result.ok:
        raise DiscoveryError(f"ArcGIS search failed ({result.status_code}) for query: {query}")
    return json.loads(result.body).get("results", [])


def _item_service_url(client: PipelineHTTPClient, item_id: str) -> str:
    result = client.get(ARCGIS_ITEM_URL.format(item_id=item_id), params={"f": "json"})
    if not result.ok:
        raise DiscoveryError(f"Failed to fetch ArcGIS item {item_id} ({result.status_code})")
    data = json.loads(result.body)
    url = data.get("url")
    if not url:
        raise DiscoveryError(f"ArcGIS item {item_id} ({data.get('title')!r}) has no service url")
    return url


@dataclass
class Vintage:
    item_id: str
    title: str
    vintage_label: str
    vintage_date: date
    service_url: str | None = None


def _discover_boundary_series(client: PipelineHTTPClient, geography_phrase: str, resolution: str) -> list[Vintage]:
    """Every distinct vintage of a boundary series (e.g. Counties and
    Unitary Authorities, BGC resolution), oldest first, deduped so a
    "(V2)" correction replaces the original for the same vintage label.
    """
    query = f'owner:{ONS_OWNER} AND title:"{geography_phrase}" AND title:{resolution} AND type:"Feature Service"'
    results = _arcgis_search(client, query)

    by_label: dict[str, dict] = {}
    for r in results:
        if r.get("type") != "Feature Service":
            continue
        m = TITLE_RE.match(r["title"].strip())
        if not m or m.group("resolution") != resolution:
            continue
        if m.group("geography").strip().lower() != geography_phrase.lower():
            continue
        month = _MONTHS.get(m.group("month").lower())
        if month is None:
            continue
        year = int(m.group("year"))
        vintage_date = date(year, month, 1)
        if vintage_date < MIN_VINTAGE_DATE:
            continue
        label = f"{m.group('month')[:3].upper()}_{year}"
        existing = by_label.get(label)
        if existing is None or r["created"] > existing["created"]:
            by_label[label] = {"item_id": r["id"], "title": r["title"], "created": r["created"],
                                "vintage_label": label, "vintage_date": vintage_date}

    series = sorted(by_label.values(), key=lambda e: e["vintage_date"])
    return [Vintage(item_id=e["item_id"], title=e["title"], vintage_label=e["vintage_label"],
                     vintage_date=e["vintage_date"]) for e in series]


def _discover_latest_lookup(client: PipelineHTTPClient, phrase: str) -> Vintage:
    query = f'owner:{ONS_OWNER} AND title:"{phrase}" AND title:Lookup AND type:"Feature Service"'
    results = [r for r in _arcgis_search(client, query, num=50)
               if r.get("type") == "Feature Service" and r["title"].lower().startswith(phrase.lower())]
    if not results:
        raise DiscoveryError(f"No current ArcGIS lookup found matching {phrase!r}")
    results.sort(key=lambda r: r["created"], reverse=True)
    top = results[0]
    return Vintage(item_id=top["id"], title=top["title"], vintage_label="current", vintage_date=date.today())


def _layer_field_names(client: PipelineHTTPClient, service_url: str) -> list[str]:
    result = client.get(f"{service_url}/0", params={"f": "json"})
    if not result.ok:
        raise DiscoveryError(f"Failed to fetch layer metadata for {service_url}")
    return [f["name"] for f in json.loads(result.body).get("fields", [])]


def _code_field_for(client: PipelineHTTPClient, vintage: Vintage, key: str, field_cache: dict[tuple[str, str], str]) -> str:
    if vintage.service_url is None:
        vintage.service_url = _item_service_url(client, vintage.item_id)
    cache_key = (vintage.service_url, key)
    if cache_key not in field_cache:
        field_cache[cache_key] = _find_field(_layer_field_names(client, vintage.service_url), key)
    return field_cache[cache_key]


def _query_paged(client: PipelineHTTPClient, service_url: str, params_base: dict, page_size: int = 2000):
    """Yields (feature, fetch_result) pairs — fetch_result is the page's own
    FetchResult, so each row's provenance is the exact response it came from.
    """
    offset = 0
    while True:
        params = dict(params_base, resultOffset=offset, resultRecordCount=page_size)
        result = client.get(f"{service_url}/0/query", params=params)
        if not result.ok:
            raise DiscoveryError(f"ArcGIS query failed ({result.status_code}) for {service_url}: {params}")
        data = json.loads(result.body)
        if isinstance(data, dict) and data.get("error"):
            raise DiscoveryError(f"ArcGIS query error for {service_url}: {data['error']}")
        batch = data.get("features", [])
        for feature in batch:
            yield feature, result
        if len(batch) < page_size:
            return
        offset += page_size


def _provenance(result) -> dict:
    return {
        "source_url": result.url,
        "retrieved_at": result.retrieved_at.isoformat(),
        "http_status": result.status_code,
        "source_system": SOURCE_SYSTEM,
        "payload_sha256": result.payload_sha256,
    }


def _fetch_vintage_snapshot(
    client: PipelineHTTPClient, vintage: Vintage, code_field_key: str, code_prefixes: set[str],
    field_cache: dict[tuple[str, str], str],
) -> dict[str, dict]:
    """Attribute-only {code: {"name":..., "provenance":...}} for one vintage,
    filtered to the given ONS code prefixes.
    """
    code_field = _code_field_for(client, vintage, code_field_key, field_cache)
    name_field = code_field.replace("CD", "NM")

    snapshot: dict[str, dict] = {}
    for feature, result in _query_paged(client, vintage.service_url, {
        "where": "1=1", "outFields": f"{code_field},{name_field}", "f": "json", "returnGeometry": "false",
    }):
        attrs = feature["attributes"]
        code = attrs[code_field]
        if code[:3] not in code_prefixes:
            continue
        snapshot[code] = {"name": attrs[name_field], "provenance": _provenance(result)}
    return snapshot


def _fetch_geometry_by_codes(client: PipelineHTTPClient, service_url: str, code_field: str, codes: list[str]) -> dict[str, dict]:
    """GeoJSON geometry (WGS84) for the given codes, as {code: geometry}."""
    if not codes:
        return {}
    geometries: dict[str, dict] = {}
    # ArcGIS 'IN' clauses have a practical length limit; chunk defensively.
    for chunk_start in range(0, len(codes), 100):
        chunk = codes[chunk_start:chunk_start + 100]
        where = f"{code_field} IN ({', '.join(repr(c) for c in chunk)})"
        result = client.get(f"{service_url}/0/query", params={
            "where": where, "outFields": code_field, "outSR": 4326, "f": "geojson",
        })
        if not result.ok:
            raise DiscoveryError(f"Geometry query failed ({result.status_code}) for {service_url}: {where}")
        data = json.loads(result.body)
        for feat in data.get("features", []):
            code = feat["properties"][code_field]
            geometries[code] = feat["geometry"]
    return geometries


def _overlap_fraction(predecessor_geom: dict, candidate_geom: dict) -> float:
    pred_shape = shape(predecessor_geom)
    cand_shape = shape(candidate_geom)
    if not pred_shape.is_valid:
        pred_shape = pred_shape.buffer(0)
    if not cand_shape.is_valid:
        cand_shape = cand_shape.buffer(0)
    if pred_shape.area == 0:
        return 0.0
    return pred_shape.intersection(cand_shape).area / pred_shape.area


def _resolve_successors(
    conn,
    client: PipelineHTTPClient,
    module_name: str,
    retired_ref: dict[str, tuple[Vintage, str]],
    added_ref: dict[str, tuple[Vintage, str]],
    field_cache: dict[tuple[str, str], str],
    from_label: str,
    to_label: str,
) -> None:
    """For each retired code, measure geometric overlap against every code
    newly added in the same transition (pooled across both boundary
    series) and record edges above threshold. A retired code with no
    candidate clearing the bar gets a review_queue entry, never a guess.
    """
    if not retired_ref:
        return
    if not added_ref:
        for code in retired_ref:
            db.record_review_item(
                conn, module_name, "unresolved_successor", code,
                json.dumps({"reason": "no new codes appeared in this transition", "from": from_label, "to": to_label}),
            )
        return

    added_by_service: dict[tuple[str, str], list[str]] = {}
    for code, (vintage, key) in added_ref.items():
        code_field = _code_field_for(client, vintage, key, field_cache)
        added_by_service.setdefault((vintage.service_url, code_field), []).append(code)

    added_geometries: dict[str, dict] = {}
    for (service_url, code_field), codes in added_by_service.items():
        added_geometries.update(_fetch_geometry_by_codes(client, service_url, code_field, codes))

    for pred_code, (vintage, key) in retired_ref.items():
        code_field = _code_field_for(client, vintage, key, field_cache)
        pred_geom_map = _fetch_geometry_by_codes(client, vintage.service_url, code_field, [pred_code])
        pred_geom = pred_geom_map.get(pred_code)
        if pred_geom is None:
            db.record_parse_failure(
                conn, module_name, "geometry", pred_code,
                "could not fetch predecessor geometry for successor resolution", source_url=vintage.service_url,
            )
            continue

        candidates = [(c, _overlap_fraction(pred_geom, g)) for c, g in added_geometries.items()]
        candidates = [(c, f) for c, f in candidates if f >= OVERLAP_THRESHOLD]

        if not candidates:
            db.record_review_item(
                conn, module_name, "unresolved_successor", pred_code,
                json.dumps({"reason": "no candidate cleared overlap threshold", "from": from_label, "to": to_label}),
            )
            continue

        for succ_code, fraction in candidates:
            row = {
                "predecessor_code": pred_code,
                "successor_code": succ_code,
                "overlap_fraction": fraction,
                "method": "geometry_overlap",
                "transition_from_vintage": from_label,
                "transition_to_vintage": to_label,
                "source_url": vintage.service_url,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "http_status": 200,
                "source_system": SOURCE_SYSTEM,
                "payload_sha256": "",
            }
            db.upsert(conn, "authority_successors", row, natural_key=["predecessor_code", "successor_code"])


def _snapshot_and_vintage_as_of(series: list[Vintage], snapshots: dict[str, dict], as_of: date) -> tuple[dict[str, dict], Vintage | None]:
    candidates = [v for v in series if v.vintage_date <= as_of]
    if not candidates:
        return {}, None
    v = max(candidates, key=lambda x: x.vintage_date)
    return snapshots[v.vintage_label], v


@register_module(
    "m00_geography",
    supports_since=False,
    since_note="reference geography: fetches the current ONS vintages plus reorganisation history, which is not a date-filterable stream",
)
def run(ctx: ModuleContext) -> None:
    module_name = "m00_geography"
    conn = ctx.conn

    ctx.phase("finding layers")
    with PipelineHTTPClient(SOURCE_SYSTEM, settings=ctx.settings, conn=conn) as client:
        cty_series = _discover_boundary_series(client, "Counties and Unitary Authorities", "BGC")
        lad_series = _discover_boundary_series(client, "Local Authority Districts", "BGC")
        if not cty_series or not lad_series:
            raise DiscoveryError(
                "Could not discover current ONS boundary layers — the ArcGIS Online "
                "search query may need updating to match a title format change."
            )

        log.info("geography.discovered_series", cty_vintages=[v.vintage_label for v in cty_series],
                  lad_vintages=[v.vintage_label for v in lad_series])

        field_cache: dict[tuple[str, str], str] = {}

        # --- Current state: full attribute + geometry for active authorities ---
        latest_cty = cty_series[-1]
        latest_lad = lad_series[-1]
        cty_code_field = _code_field_for(client, latest_cty, "ctyua_code", field_cache)
        cty_name_field = cty_code_field.replace("CD", "NM")
        lad_code_field = _code_field_for(client, latest_lad, "lad_code", field_cache)
        lad_name_field = lad_code_field.replace("CD", "NM")

        region_item = _discover_latest_lookup(client, "Local Authority District to Region")
        region_item.service_url = _item_service_url(client, region_item.item_id)
        region_fields = _layer_field_names(client, region_item.service_url)
        region_lad_field = _find_field(region_fields, "lad_code")
        region_code_field = _find_field(region_fields, "rgn_code")
        region_name_field = _find_field(region_fields, "rgn_name")

        county_item = _discover_latest_lookup(client, "Local Authority District to County and Unitary Authority")
        county_item.service_url = _item_service_url(client, county_item.item_id)
        county_fields = _layer_field_names(client, county_item.service_url)
        county_lad_field = _find_field(county_fields, "lad_code")
        county_ctyua_field = _find_field(county_fields, "ctyua_code")

        region_by_code: dict[str, tuple[str, str]] = {}
        for feature, _result in _query_paged(client, region_item.service_url, {
            "where": "1=1", "outFields": "*", "f": "json", "returnGeometry": "false",
        }):
            attrs = feature["attributes"]
            region_by_code[attrs[region_lad_field]] = (attrs[region_code_field], attrs[region_name_field])

        parent_by_code: dict[str, str | None] = {}
        for feature, _result in _query_paged(client, county_item.service_url, {
            "where": "1=1", "outFields": "*", "f": "json", "returnGeometry": "false",
        }):
            attrs = feature["attributes"]
            lad_code = attrs[county_lad_field]
            ctyua_code = attrs[county_ctyua_field]
            parent_by_code[lad_code] = ctyua_code if ctyua_code != lad_code else None

        # Counties (E10) aren't LAD-tier, so they never appear in the
        # LAD-to-region lookup directly. Derive a county's region from any
        # one of its child non-metropolitan districts instead — England's
        # counties don't span more than one region, so any child will do.
        county_region_by_code: dict[str, tuple[str, str]] = {}
        for lad_code, ctyua_code in parent_by_code.items():
            if ctyua_code and ctyua_code not in county_region_by_code and lad_code in region_by_code:
                county_region_by_code[ctyua_code] = region_by_code[lad_code]

        # English upper-tier authorities (county/unitary/london borough/metropolitan district).
        current_rows: dict[str, dict] = {}
        for feature, result in _query_paged(client, latest_cty.service_url, {
            "where": f"{cty_code_field} LIKE 'E%'", "outFields": f"{cty_code_field},{cty_name_field}",
            "f": "json", "returnGeometry": "false",
        }):
            attrs = feature["attributes"]
            code = attrs[cty_code_field]
            authority_type = _authority_type(code)
            if authority_type is None:
                db.record_parse_failure(conn, module_name, "type", code,
                                         "unrecognised ONS code prefix for a CTYUA row", source_url=result.url)
                continue
            region_code, region_name = region_by_code.get(code) or county_region_by_code.get(code, (None, None))
            if region_code is None:
                db.record_parse_failure(conn, module_name, "region", code,
                                         "no region resolvable directly or via a child district", source_url=result.url)
            current_rows[code] = {
                "row": {
                    "ons_code": code, "name": attrs[cty_name_field], "type": authority_type,
                    "region_code": region_code, "region": region_name, "parent_code": None,
                },
                "vintage": latest_cty, "provenance": _provenance(result),
            }

        # English non-metropolitan districts (lower tier, nested in a county).
        for feature, result in _query_paged(client, latest_lad.service_url, {
            "where": f"{lad_code_field} LIKE 'E07%'", "outFields": f"{lad_code_field},{lad_name_field}",
            "f": "json", "returnGeometry": "false",
        }):
            attrs = feature["attributes"]
            code = attrs[lad_code_field]
            region_code, region_name = region_by_code.get(code, (None, None))
            current_rows[code] = {
                "row": {
                    "ons_code": code, "name": attrs[lad_name_field], "type": "non_metropolitan_district",
                    "region_code": region_code, "region": region_name, "parent_code": parent_by_code.get(code),
                },
                "vintage": latest_lad, "provenance": _provenance(result),
            }

        # Geometry for currently-active codes only (this is for map use; historical
        # predecessor geometry isn't fetched — retired rows carry NULL geometry).
        cty_codes = [c for c, r in current_rows.items() if r["vintage"] is latest_cty]
        lad_codes = [c for c, r in current_rows.items() if r["vintage"] is latest_lad]
        geometries: dict[str, dict] = {}
        geometries.update(_fetch_geometry_by_codes(client, latest_cty.service_url, cty_code_field, cty_codes))
        geometries.update(_fetch_geometry_by_codes(client, latest_lad.service_url, lad_code_field, lad_codes))

        for code, entry in ctx.track(list(current_rows.items()), "authorities"):
            vintage: Vintage = entry["vintage"]
            geom = geometries.get(code)
            db.upsert(conn, "authorities", {
                **entry["row"],
                "active_from": vintage.vintage_date.isoformat(),
                "active_to": None,
                "first_seen_vintage": vintage.vintage_label,
                "last_seen_vintage": vintage.vintage_label,
                "geometry_geojson": json.dumps(geom) if geom else None,
                **entry["provenance"],
            }, natural_key=["ons_code"])

        log.info("geography.current_authorities_loaded", count=len(current_rows))

        # Hand the write slot back before the historical phase starts.
        #
        # SQLite allows one writer, and Python's sqlite3 opens a transaction on
        # the first write and holds it until commit. Everything below this line
        # fetches: a snapshot per vintage in both series, then boundary
        # geometry for every retired and added code at every transition. Those
        # requests took three minutes on the last full run, and without this
        # commit all of them happened inside the transaction opened by the
        # authorities upsert above.
        #
        # Serially that is invisible. In a wave it is fatal to everything else:
        # m00 shares wave 1 with m02, m03, m06, m08 and m16, each of which
        # seeds provider reference data in its opening lines. They waited out
        # the full two-minute busy timeout and failed with "database is locked"
        # having fetched nothing — five modules lost to one module's open
        # transaction. This is the same fault m11 had, in the one module that
        # had no commit of its own at all.
        if not ctx.dry_run:
            conn.commit()

        # --- Historical vintages: detect retirements and resolve successors ---
        # Snapshots are pooled by calendar epoch across both series so a
        # county retiring alongside its districts resolves against
        # candidates from either series in the same transition.
        cty_snapshots = {v.vintage_label: _fetch_vintage_snapshot(client, v, "ctyua_code", {"E06", "E08", "E09", "E10"}, field_cache)
                          for v in cty_series}
        lad_snapshots = {v.vintage_label: _fetch_vintage_snapshot(client, v, "lad_code", {"E07"}, field_cache)
                          for v in lad_series}

        epoch_dates = sorted({v.vintage_date for v in cty_series} | {v.vintage_date for v in lad_series})

        for prev_date, next_date in zip(epoch_dates, epoch_dates[1:]):
            prev_cty, prev_cty_v = _snapshot_and_vintage_as_of(cty_series, cty_snapshots, prev_date)
            prev_lad, prev_lad_v = _snapshot_and_vintage_as_of(lad_series, lad_snapshots, prev_date)
            next_cty, next_cty_v = _snapshot_and_vintage_as_of(cty_series, cty_snapshots, next_date)
            next_lad, next_lad_v = _snapshot_and_vintage_as_of(lad_series, lad_snapshots, next_date)

            prev_codes = {**prev_cty, **prev_lad}
            next_codes = {**next_cty, **next_lad}

            retired = {c: prev_codes[c] for c in prev_codes if c not in next_codes}
            added = {c: next_codes[c] for c in next_codes if c not in prev_codes}
            if not retired and not added:
                continue

            from_label = "+".join(sorted({v.vintage_label for v in (prev_cty_v, prev_lad_v) if v}))
            to_label = "+".join(sorted({v.vintage_label for v in (next_cty_v, next_lad_v) if v}))

            log.info("geography.transition_detected", from_vintage=from_label, to_vintage=to_label,
                      retired=list(retired), added=list(added))

            for code, info in retired.items():
                authority_type = _authority_type(code)
                db.upsert(conn, "authorities", {
                    "ons_code": code, "name": info["name"], "type": authority_type,
                    "region_code": None, "region": None, "parent_code": None,
                    "active_from": prev_date.isoformat(),
                    "active_to": next_date.isoformat(),
                    "first_seen_vintage": from_label, "last_seen_vintage": from_label,
                    "geometry_geojson": None,
                    **info["provenance"],
                }, natural_key=["ons_code"])

            retired_ref: dict[str, tuple[Vintage, str]] = {}
            for code in retired:
                v = prev_lad_v if code[:3] == "E07" else prev_cty_v
                if v is None:
                    db.record_parse_failure(conn, module_name, "vintage_ref", code,
                                             "no source vintage available for retired code at this epoch")
                    continue
                retired_ref[code] = (v, "lad_code" if code[:3] == "E07" else "ctyua_code")

            added_ref: dict[str, tuple[Vintage, str]] = {}
            for code in added:
                v = next_lad_v if code[:3] == "E07" else next_cty_v
                if v is None:
                    db.record_parse_failure(conn, module_name, "vintage_ref", code,
                                             "no source vintage available for added code at this epoch")
                    continue
                added_ref[code] = (v, "lad_code" if code[:3] == "E07" else "ctyua_code")

            _resolve_successors(conn, client, module_name, retired_ref, added_ref, field_cache, from_label, to_label)

            # One transition is a complete unit of work: the retirements and
            # the successor rows that explain them. _resolve_successors fetches
            # geometry for every code involved, so committing per transition
            # keeps the write slot held for one epoch rather than all of them.
            if not ctx.dry_run:
                conn.commit()

        total = conn.execute("SELECT COUNT(*) AS n FROM authorities").fetchone()["n"]
        log.info("geography.run_complete", total_authority_rows=total)
