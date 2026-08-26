"""Generates the England region silhouette used by the overview page's hero.

Run manually and commit the output — these are administrative region
boundaries, not evidence, and they change on the order of "never" rather
than per pipeline run:

    uv run python scripts/generate_region_outline.py

Regenerate only if Module 0 re-collects authority boundaries from a new ONS
boundary vintage (region names or shapes changing).

Dissolves the already-collected, already-provenanced authority polygons in
`authorities.geometry_geojson` into one polygon per region and simplifies
the result, because the hero draws a glanceable silhouette of England, not
an analysable map. The full authority boundaries are 14MB and belong to
`/api/v1/boundaries`, fetched on demand by the geography workspace — not
something every homepage visitor should download before the hero paints.
"""
from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import MultiPolygon, mapping, shape
from shapely.ops import unary_union

from pipeline.config import get_settings
from pipeline.web import queries

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent
    / "pipeline" / "web" / "static" / "public" / "assets" / "england-regions.json"
)

# Degrees, not metres — these coordinates are WGS84 lon/lat. Coarse enough to
# cut a coastline's vertex count down for a decorative hero shape, fine
# enough that England's outline and each region's shape are still
# recognisable at hero scale (checked by eye against the rendered SVG, not
# just by output size).
SIMPLIFY_TOLERANCE_DEGREES = 0.04

# Adjacent authority polygons rarely share byte-identical edges, so a union
# of ~300 of them leaves hundreds of sliver polygons a fraction of a square
# metre in size at every near-miss seam -- East of England alone dissolved to
# 490 sub-polygons before this filter, 441 of them under 1e-5 sq degrees. A
# hero silhouette wants England's real islands, not seam artefacts, so
# anything under this fraction of the region's total dissolved area is
# dropped. 0.05% keeps genuine secondary landmasses (e.g. the Isle of Wight
# within the South East) while clearing every seam sliver observed.
MIN_ISLAND_AREA_FRACTION = 0.0005


def _drop_slivers(geometry):
    if geometry.geom_type != "MultiPolygon":
        return geometry
    threshold = geometry.area * MIN_ISLAND_AREA_FRACTION
    kept = [poly for poly in geometry.geoms if poly.area >= threshold]
    return kept[0] if len(kept) == 1 else MultiPolygon(kept)


def _region_geometry(geojson_strings: list[str]):
    polygons = []
    for raw in geojson_strings:
        try:
            geometry = shape(json.loads(raw))
        except (TypeError, ValueError):
            continue
        # Same invalid-geometry recovery as pipeline/exports/geojson.py's
        # _centroid: a self-intersecting ring from source data would
        # otherwise raise inside unary_union rather than dissolve cleanly.
        if not geometry.is_valid:
            geometry = geometry.buffer(0)
        polygons.append(geometry)
    dissolved = unary_union(polygons)
    return _drop_slivers(dissolved).simplify(SIMPLIFY_TOLERANCE_DEGREES, preserve_topology=True)


def main() -> None:
    conn = queries.readonly_connection(get_settings())
    try:
        rows = [
            dict(row) for row in conn.execute(
                "SELECT region, geometry_geojson, source_url, retrieved_at "
                "FROM authorities "
                "WHERE geometry_geojson IS NOT NULL AND region IS NOT NULL"
            ).fetchall()
        ]
    finally:
        conn.close()

    by_region: dict[str, list[str]] = {}
    source_url = None
    retrieved_at = None
    for row in rows:
        by_region.setdefault(row["region"], []).append(row["geometry_geojson"])
        source_url = source_url or row["source_url"]
        if row["retrieved_at"] and (retrieved_at is None or row["retrieved_at"] > retrieved_at):
            retrieved_at = row["retrieved_at"]

    features = []
    all_bounds = []
    for region in sorted(by_region):
        geometry = _region_geometry(by_region[region])
        all_bounds.append(geometry.bounds)
        features.append({
            "type": "Feature",
            "properties": {"region": region},
            "geometry": mapping(geometry),
        })

    if not all_bounds:
        raise SystemExit("No authorities carry both region and geometry_geojson — nothing to dissolve.")

    min_lon = min(b[0] for b in all_bounds)
    min_lat = min(b[1] for b in all_bounds)
    max_lon = max(b[2] for b in all_bounds)
    max_lat = max(b[3] for b in all_bounds)

    payload = {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "note": (
                "Simplified region dissolve for the overview hero visual "
                "only — not boundary-accurate enough for analysis. "
                "Regenerate with scripts/generate_region_outline.py if "
                "Module 0 re-collects authority boundaries."
            ),
            "source_url": source_url,
            "retrieved_at": retrieved_at,
            "simplify_tolerance_degrees": SIMPLIFY_TOLERANCE_DEGREES,
            "bbox": [min_lon, min_lat, max_lon, max_lat],
        },
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, separators=(",", ":")))
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"Wrote {len(features)} regions to {OUTPUT_PATH} ({size_kb:.1f} KB)")
    print("Regions:", ", ".join(sorted(by_region)))


if __name__ == "__main__":
    main()
