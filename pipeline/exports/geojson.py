"""GeoJSON export for Leaflet — one FeatureCollection per evidence layer.

Separate files, never a merged layer, so the map can toggle them
independently and so a reader cannot mistake one kind of evidence for
another. Each file gets its own .provenance.json and carries its caveats in
the FeatureCollection's own metadata, because a layer that travels without
its caveat will eventually be read without it.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import structlog

from pipeline.exports import guard_columns
from pipeline.exports.provenance import write_export

log = structlog.get_logger()


def _feature(geometry: dict | None, properties: dict) -> dict:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _point(longitude, latitude) -> dict | None:
    if longitude is None or latitude is None:
        return None
    return {"type": "Point", "coordinates": [float(longitude), float(latitude)]}


def _collection(features: list[dict], layer: str, caveats: list[str]) -> dict:
    return {
        "type": "FeatureCollection",
        "name": layer,
        # Non-standard but harmless top-level keys; Leaflet ignores them and
        # a UI can surface them next to the layer toggle.
        "metadata": {"layer": layer, "caveats": caveats, "feature_count": len(features)},
        "features": features,
    }


def _write(path: Path, collection: dict) -> None:
    path.write_text(json.dumps(collection), encoding="utf-8")


def export_contracts(conn: sqlite3.Connection, output_dir: Path) -> Path:
    """Contracts, positioned on their buyer authority's centroid.

    Contracts have no geometry of their own; they are placed on the
    commissioning authority's boundary centroid, which is a presentational
    choice and is stated in the layer caveats.
    """
    caveats = [
        "Contracts have no location of their own. Each is placed at the centroid of the "
        "commissioning authority's boundary — this shows who commissioned it, not where "
        "the service is delivered.",
        "Contract values are estimates at notice stage and may differ from actual spend.",
        "Notices whose buyer could not be matched to an authority are omitted from this "
        "layer; they are in the Contracts tab with a NULL buyer_ons_code.",
    ]
    cursor = conn.execute("""
        SELECT c.notice_id, c.title, c.buyer_name, c.buyer_ons_code,
               c.supplier_name_raw, c.value_core, c.currency, c.date_published,
               c.procedure_type, c.source_url, a.name AS authority_name,
               a.geometry_geojson
          FROM contracts c
          JOIN authorities a ON a.ons_code = c.buyer_ons_code
         WHERE a.geometry_geojson IS NOT NULL
    """)
    guard_columns("contracts_layer", [d[0] for d in cursor.description])

    features = []
    for row in cursor.fetchall():
        centroid = _centroid(row["geometry_geojson"])
        features.append(_feature(centroid, {
            "notice_id": row["notice_id"], "title": row["title"],
            "buyer_name": row["buyer_name"], "ons_code": row["buyer_ons_code"],
            "authority_name": row["authority_name"],
            "supplier": row["supplier_name_raw"], "value_core": row["value_core"],
            "currency": row["currency"], "date_published": row["date_published"],
            "procedure_type": row["procedure_type"], "source_url": row["source_url"],
        }))

    path = output_dir / "contracts.geojson"
    write_export(path, lambda p: _write(p, _collection(features, "contracts", caveats)),
                  conn, ["contracts", "authorities"], "geojson_layer", len(features), caveats)
    return path


def export_cqc_locations(conn: sqlite3.Connection, output_dir: Path) -> Path:
    caveats = [
        "CQC registration covers only some service types — residential detoxification, "
        "inpatient and certain prescribing services. Most community drug and alcohol "
        "provision is NOT CQC-registered, so this layer is a map of regulated locations "
        "and NOT a map of services.",
        "Absence of a pin does not mean absence of a service.",
    ]
    cursor = conn.execute("""
        SELECT location_id, provider_key, location_name, postal_code, latitude, longitude,
               local_authority_ons_code, region, overall_rating, last_inspection_date,
               service_types, source_url
          FROM cqc_locations
         WHERE latitude IS NOT NULL AND longitude IS NOT NULL
    """)
    guard_columns("cqc_layer", [d[0] for d in cursor.description])

    features = [
        _feature(_point(row["longitude"], row["latitude"]), {
            "location_id": row["location_id"], "provider_key": row["provider_key"],
            "location_name": row["location_name"], "postal_code": row["postal_code"],
            "ons_code": row["local_authority_ons_code"], "region": row["region"],
            "overall_rating": row["overall_rating"],
            "last_inspection_date": row["last_inspection_date"],
            "service_types": row["service_types"], "source_url": row["source_url"],
        })
        for row in cursor.fetchall()
    ]

    path = output_dir / "cqc_locations.geojson"
    write_export(path, lambda p: _write(p, _collection(features, "cqc_locations", caveats)),
                  conn, ["cqc_locations"], "geojson_layer", len(features), caveats)
    return path


def export_treatment_numbers(conn: sqlite3.Connection, output_dir: Path) -> Path:
    """Authority polygons carrying their latest treatment-rate value."""
    caveats = [
        "Service-demand data, not workforce data. It must not be combined with workforce "
        "figures to produce caseload-per-worker style ratios.",
        "Values are the most recent published period per authority; periods differ between "
        "authorities and are given per feature.",
        "Rates are per 1,000 population and are not counts of people.",
    ]
    cursor = conn.execute("""
        SELECT v.ons_code, a.name AS authority_name, a.geometry_geojson,
               v.indicator_id, i.slug, i.topic, v.time_period, v.value
          FROM fingertips_la_values v
          JOIN fingertips_indicators i ON i.indicator_id = v.indicator_id
          JOIN authorities a ON a.ons_code = v.ons_code
         WHERE v.area_level = 'local_authority'
           AND i.topic = 'numbers_in_treatment'
           AND a.geometry_geojson IS NOT NULL
           AND v.value IS NOT NULL
           AND v.time_period = (
               SELECT MAX(v2.time_period) FROM fingertips_la_values v2
                WHERE v2.indicator_id = v.indicator_id AND v2.ons_code = v.ons_code)
    """)
    guard_columns("treatment_layer", [d[0] for d in cursor.description])

    features = []
    for row in cursor.fetchall():
        try:
            geometry = json.loads(row["geometry_geojson"])
        except (TypeError, json.JSONDecodeError):
            continue
        features.append(_feature(geometry, {
            "ons_code": row["ons_code"], "authority_name": row["authority_name"],
            "indicator": row["slug"], "topic": row["topic"],
            "time_period": row["time_period"], "value": row["value"],
            "unit": "rate per 1,000 population",
        }))

    path = output_dir / "treatment_numbers.geojson"
    write_export(path, lambda p: _write(p, _collection(features, "treatment_numbers", caveats)),
                  conn, ["fingertips_la_values", "authorities"], "geojson_layer",
                  len(features), caveats)
    return path


def export_pfd_reports(conn: sqlite3.Connection, output_dir: Path) -> Path:
    """PFD reports grouped by coroner area.

    Coroner areas are not local authorities and have no boundary geometry in
    this warehouse, so features are emitted without geometry and carry the
    coroner area as a property. A UI can group by it; it must not be drawn as
    if it were an authority boundary.
    """
    caveats = [
        "Coroner areas are NOT local authorities and do not share their boundaries. These "
        "features carry no geometry for that reason — grouping is by coroner area name.",
        "A report being sent to a provider and a provider being named in one are different "
        "facts and are given as separate properties.",
        "The deceased is never named. Reports are keyed on the coroner's own reference.",
    ]
    cursor = conn.execute("""
        SELECT r.report_ref, r.report_date, r.coroner_area, r.coroner_name, r.categories,
               r.report_url,
               (SELECT GROUP_CONCAT(m.provider_key, ', ') FROM pfd_provider_mentions m
                 WHERE m.report_ref = r.report_ref AND m.mention_type = 'recipient')
                   AS provider_recipients,
               (SELECT GROUP_CONCAT(t.term, ', ') FROM pfd_concern_terms t
                 WHERE t.report_ref = r.report_ref) AS concern_terms
          FROM pfd_reports r
         WHERE r.coroner_area IS NOT NULL
    """)
    guard_columns("pfd_layer", [d[0] for d in cursor.description])

    features = [
        _feature(None, {
            "report_ref": row["report_ref"], "report_date": row["report_date"],
            "coroner_area": row["coroner_area"], "coroner_name": row["coroner_name"],
            "categories": row["categories"], "report_url": row["report_url"],
            "provider_recipients": row["provider_recipients"],
            "concern_terms": row["concern_terms"],
        })
        for row in cursor.fetchall()
    ]

    path = output_dir / "pfd_reports.geojson"
    write_export(path, lambda p: _write(p, _collection(features, "pfd_reports", caveats)),
                  conn, ["pfd_reports", "pfd_provider_mentions", "pfd_concern_terms"],
                  "geojson_layer", len(features), caveats)
    return path


def _centroid(geometry_json: str) -> dict | None:
    """Representative point for a polygon, used to place non-spatial records."""
    try:
        from shapely.geometry import shape

        geometry = shape(json.loads(geometry_json))
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        point = geometry.representative_point()
        return {"type": "Point", "coordinates": [point.x, point.y]}
    except Exception:
        return None


def export_all(conn: sqlite3.Connection, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        export_contracts(conn, output_dir),
        export_cqc_locations(conn, output_dir),
        export_treatment_numbers(conn, output_dir),
        export_pfd_reports(conn, output_dir),
    ]
    for path in paths:
        log.info("geojson.layer_written", path=str(path))
    return paths
