"""Build a deterministic PMTiles archive for authority boundaries.

The warehouse's ``authorities.geometry_geojson`` column remains the canonical
source. This module only derives display tiles from it: it never writes back
to the warehouse and it does not change the public ``/api/v1/boundaries``
response. The generated archive is content-addressed, so a changed boundary
set produces a new URL and old immutable assets remain safe to cache.

The optional ``maps`` extra supplies ``mapbox-vector-tile`` and ``mercantile``.
They are intentionally build-time dependencies; the Python web runtime serves
the resulting bytes but never needs to import either package.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import struct
from pathlib import Path

import structlog

log = structlog.get_logger()

GENERATOR_VERSION = "sectortrace-pmtiles/1"
LAYER_NAME = "authorities"
EXTENT = 4096
DEFAULT_MIN_ZOOM = 0
DEFAULT_MAX_ZOOM = 9
_HEADER_LENGTH = 127


class PmtilesError(RuntimeError):
    """The boundary archive could not be built safely."""


def _varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("PMTiles varints cannot be negative")
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _directory(entries: list[tuple[int, int, int, int]]) -> bytes:
    """Serialize a PMTiles directory with stable gzip bytes.

    Each tuple is ``(tile_id, offset, length, run_length)``. The layout is
    deliberately kept here rather than delegated to a third-party writer so
    gzip timestamps cannot make identical source data produce different
    archive digests.
    """
    out = bytearray(_varint(len(entries)))
    previous = 0
    for tile_id, _offset, _length, _run in entries:
        out.extend(_varint(tile_id - previous))
        previous = tile_id
    for _tile_id, _offset, _length, run_length in entries:
        out.extend(_varint(run_length))
    for _tile_id, _offset, length, _run in entries:
        out.extend(_varint(length))
    for index, (_tile_id, offset, _length, _run) in enumerate(entries):
        if index and offset == entries[index - 1][1] + entries[index - 1][2]:
            out.extend(b"\x00")
        else:
            out.extend(_varint(offset + 1))
    return gzip.compress(bytes(out), mtime=0)


def _directories(entries: list[tuple[int, int, int, int]]) -> tuple[bytes, bytes]:
    """Return root and leaf directory bytes, keeping the root under 16 KiB."""
    root = _directory(entries)
    if len(root) < 16 * 1024 - _HEADER_LENGTH:
        return root, b""

    leaf_size = 4096
    while True:
        leaves = bytearray()
        root_entries: list[tuple[int, int, int, int]] = []
        for start in range(0, len(entries), leaf_size):
            leaf = _directory(entries[start:start + leaf_size])
            root_entries.append((entries[start][0], len(leaves), len(leaf), 0))
            leaves.extend(leaf)
        root = _directory(root_entries)
        if len(root) < 16 * 1024 - _HEADER_LENGTH:
            return root, bytes(leaves)
        leaf_size *= 2


def _tile_id(z: int, x: int, y: int) -> int:
    """PMTiles' Hilbert-ordered Z/X/Y tile identifier."""
    if z > 31 or x < 0 or y < 0 or x >= 1 << z or y >= 1 << z:
        raise ValueError(f"invalid tile coordinate z={z} x={x} y={y}")

    def rotate(size: int, px: int, py: int, rx: int, ry: int) -> tuple[int, int]:
        if ry == 0:
            if rx:
                px, py = size - 1 - px, size - 1 - py
            px, py = py, px
        return px, py

    tile_id = ((1 << (z * 2)) - 1) // 3
    level = z - 1
    while level >= 0:
        size = 1 << level
        rx = size & x
        ry = size & y
        tile_id += ((3 * rx) ^ ry) << level
        x, y = rotate(size, x, y, rx, ry)
        level -= 1
    return tile_id


def _header(values: dict[str, int | bool]) -> bytes:
    """Serialize the fixed 127-byte PMTiles v3 header."""
    out = bytearray(b"PMTiles\x03")
    for key in (
        "root_offset", "root_length", "metadata_offset", "metadata_length",
        "leaf_directory_offset", "leaf_directory_length", "tile_data_offset",
        "tile_data_length", "addressed_tiles_count", "tile_entries_count",
        "tile_contents_count",
    ):
        out.extend(struct.pack("<Q", int(values.get(key, 0))))
    out.extend(b"\x01" if values.get("clustered", True) else b"\x00")
    # Internal directory gzip, uncompressed MVT tile payload, tile type MVT.
    out.extend(bytes((2, 1, 1, int(values["min_zoom"]), int(values["max_zoom"]))))
    for key in ("min_lon_e7", "min_lat_e7", "max_lon_e7", "max_lat_e7"):
        out.extend(struct.pack("<i", int(values[key])))
    out.extend(bytes((int(values["center_zoom"]),)))
    out.extend(struct.pack("<i", int(values["center_lon_e7"])))
    out.extend(struct.pack("<i", int(values["center_lat_e7"])))
    if len(out) != _HEADER_LENGTH:  # pragma: no cover - format invariant
        raise PmtilesError(f"PMTiles header is {len(out)} bytes, expected 127")
    return bytes(out)


def _source_digest(rows: list[dict]) -> str:
    canonical = json.dumps(rows, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_rows(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT ons_code, name, region, geometry_geojson, source_url, "
        "retrieved_at FROM authorities WHERE geometry_geojson IS NOT NULL "
        "ORDER BY ons_code").fetchall()
    output = []
    for row in rows:
        record = dict(row)
        try:
            geometry = json.loads(record["geometry_geojson"])
        except (TypeError, ValueError) as exc:
            raise PmtilesError(
                f"authority {record.get('ons_code')} has invalid geometry JSON") from exc
        if not isinstance(geometry, dict) or not geometry.get("type"):
            raise PmtilesError(f"authority {record.get('ons_code')} has no GeoJSON geometry")
        output.append({
            "ons_code": record["ons_code"],
            "name": record["name"],
            "region": record["region"],
            "geometry": geometry,
            "source_url": record["source_url"],
            "retrieved_at": record["retrieved_at"],
        })
    return output


def _tile_bounds(tile) -> tuple[float, float, float, float]:
    import mercantile

    bounds = mercantile.bounds(tile)
    return bounds.west, bounds.south, bounds.east, bounds.north


def _build_tiles(rows: list[dict], min_zoom: int, max_zoom: int) -> dict[int, bytes]:
    """Clip each authority to the tiles it intersects and encode MVT bytes."""
    import mapbox_vector_tile
    import mercantile
    from shapely.geometry import box, shape
    from shapely.validation import make_valid

    tile_features: dict[tuple[int, int, int], list[dict]] = {}
    for row in rows:
        geometry = shape(row["geometry"])
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        if geometry.is_empty:
            continue
        west, south, east, north = geometry.bounds
        west = max(-180.0, west)
        east = min(180.0, east)
        south = max(-85.051129, south)
        north = min(85.051129, north)
        if west >= east or south >= north:
            continue
        for zoom in range(min_zoom, max_zoom + 1):
            for tile in mercantile.tiles(west, south, east, north, [zoom]):
                tile_box = box(*_tile_bounds(tile))
                clipped = geometry.intersection(tile_box)
                if clipped.is_empty:
                    continue
                # Reduce vertex pressure at the overview zooms while keeping
                # topology valid. The source geometry itself is untouched.
                tolerance = 360.0 / (EXTENT * (1 << (zoom + 1)))
                if tolerance and not clipped.is_empty:
                    clipped = clipped.simplify(tolerance, preserve_topology=True)
                tile_features.setdefault((zoom, tile.x, tile.y), []).append({
                    "geometry": clipped,
                    "properties": {
                        "ons_code": row["ons_code"],
                        "name": row["name"],
                        "region": row["region"],
                    },
                })

    encoded: dict[int, bytes] = {}
    for (zoom, x, y), features in sorted(tile_features.items()):
        encoded[_tile_id(zoom, x, y)] = mapbox_vector_tile.encode(
            [{"name": LAYER_NAME, "features": features}],
            default_options={
                "quantize_bounds": _tile_bounds(mercantile.Tile(x, y, zoom)),
                "extents": EXTENT,
                "on_invalid_geometry": make_valid,
            },
        )
    return encoded


def _write_archive(path: Path, tiles: dict[int, bytes], metadata: dict,
                   bounds: tuple[float, float, float, float],
                   min_zoom: int, max_zoom: int) -> tuple[str, int]:
    """Write a PMTiles v3 archive and return its digest and tile count."""
    contents = bytearray()
    content_offsets: dict[str, tuple[int, int]] = {}
    entries: list[tuple[int, int, int, int]] = []
    for tile_id, data in sorted(tiles.items()):
        digest = hashlib.sha256(data).hexdigest()
        found = content_offsets.get(digest)
        if found is None:
            found = (len(contents), len(data))
            content_offsets[digest] = found
            contents.extend(data)
        offset, length = found
        if entries and entries[-1][0] + entries[-1][3] == tile_id \
                and entries[-1][1] == offset and entries[-1][2] == length:
            old = entries[-1]
            entries[-1] = (old[0], old[1], old[2], old[3] + 1)
        else:
            entries.append((tile_id, offset, length, 1))

    root, leaves = _directories(entries)
    metadata_bytes = gzip.compress(
        json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8"), mtime=0)
    leaf_offset = _HEADER_LENGTH + len(root) + len(metadata_bytes)
    tile_offset = leaf_offset + len(leaves)
    west, south, east, north = bounds
    header_values = {
        "root_offset": _HEADER_LENGTH,
        "root_length": len(root),
        "metadata_offset": _HEADER_LENGTH + len(root),
        "metadata_length": len(metadata_bytes),
        "leaf_directory_offset": leaf_offset if leaves else 0,
        "leaf_directory_length": len(leaves),
        "tile_data_offset": tile_offset,
        "tile_data_length": len(contents),
        "addressed_tiles_count": len(tiles),
        "tile_entries_count": len(entries),
        "tile_contents_count": len(content_offsets),
        "clustered": True,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "min_lon_e7": round(west * 10_000_000),
        "min_lat_e7": round(south * 10_000_000),
        "max_lon_e7": round(east * 10_000_000),
        "max_lat_e7": round(north * 10_000_000),
        "center_zoom": min_zoom,
        "center_lon_e7": round((west + east) / 2 * 10_000_000),
        "center_lat_e7": round((south + north) / 2 * 10_000_000),
    }
    payload = _header(header_values) + root + metadata_bytes + leaves + bytes(contents)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest(), len(tiles)


def build_authority_archive(conn, output_dir: Path,
                            min_zoom: int = DEFAULT_MIN_ZOOM,
                            max_zoom: int = DEFAULT_MAX_ZOOM) -> dict:
    """Build the archive and deterministic manifest from canonical boundaries."""
    if min_zoom < 0 or max_zoom < min_zoom or max_zoom > 14:
        raise PmtilesError("zoom range must be 0 <= min_zoom <= max_zoom <= 14")
    rows = _load_rows(conn)
    if not rows:
        raise PmtilesError("cannot build a boundary archive with no geometries")
    source_rows = [{key: row[key] for key in (
        "ons_code", "name", "region", "geometry", "source_url", "retrieved_at")}
                   for row in rows]
    source_digest = _source_digest(source_rows)
    from shapely.geometry import shape

    bounds_list = [shape(row["geometry"]).bounds for row in rows]
    bounds = (
        min(item[0] for item in bounds_list),
        min(item[1] for item in bounds_list),
        max(item[2] for item in bounds_list),
        max(item[3] for item in bounds_list),
    )
    tiles = _build_tiles(rows, min_zoom, max_zoom)
    metadata = {
        "tilejson": "3.0.0",
        "name": "SectorTrace authority boundaries",
        "format": "pbf",
        "version": source_digest,
        "generator": GENERATOR_VERSION,
        "bounds": list(bounds),
        "center": [(bounds[0] + bounds[2]) / 2,
                   (bounds[1] + bounds[3]) / 2, min_zoom],
        "vector_layers": [{
            "id": LAYER_NAME,
            "description": "Canonical ONS authority boundaries",
            "minzoom": min_zoom,
            "maxzoom": max_zoom,
            "fields": {"ons_code": "String", "name": "String", "region": "String"},
        }],
    }
    archive = output_dir / f"boundaries-{source_digest}.pmtiles"
    output_digest, tile_count = _write_archive(
        archive, tiles, metadata, bounds, min_zoom, max_zoom)
    manifest = {
        "archive": f"/map/{archive.name}",
        "source_digest": source_digest,
        "boundary_version": source_digest,
        "generator_version": GENERATOR_VERSION,
        "feature_count": len(rows),
        "bounds": list(bounds),
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "zoom_range": [min_zoom, max_zoom],
        "output_digest": output_digest,
        "tile_count": tile_count,
    }
    (output_dir / "boundaries.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    log.info("pmtiles.boundaries_written", archive=str(archive),
             feature_count=len(rows), tile_count=tile_count,
             source_digest=source_digest, output_digest=output_digest)
    return manifest
