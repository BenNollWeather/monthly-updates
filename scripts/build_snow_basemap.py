#!/usr/bin/env python3
"""Build the static basemap for the in-page snowfall canvas.

The daily page paints the anomaly on a canvas. Terrain, county lines, state
outlines, and the Great Lakes are static, so they are written once:

  lib/snow_basemap.js
  lib/snow_terrain.jpg
  lib/snow_counties.png

The workflow copies those three files to climate_imagery/.
"""

from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image
from shapely.geometry import box
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.snow_anomaly import EXTENT, LAKE_NAMES  # noqa: E402

CACHE = Path("/tmp/monthly-updates/snow-anomaly/cache")
FRAME = box(EXTENT[0] - 0.4, EXTENT[2] - 0.4, EXTENT[1] + 0.4, EXTENT[3] + 0.4)
DROP_STATE = {"Alaska", "Hawaii"}
DROP_FP = {"02", "15", "60", "66", "69", "72", "78"}
# Natural Earth 10m, kept to about 0.001°. Coarser than this, the Great Lakes
# lose their bays and a state line can stop short of the shore.
SHORE_TOL = 0.001
PLACES = 3


def _round_ring(coords, places: int = 2) -> list[float]:
    flat: list[float] = []
    last = None
    for lon, lat in coords:
        point = (round(float(lon), places), round(float(lat), places))
        if point == last:
            continue
        last = point
        flat.extend(point)
    if len(flat) >= 4 and (flat[0], flat[1]) != (flat[-2], flat[-1]):
        flat.extend(flat[:2])
    return flat


def _polys(geom, places: int = PLACES) -> list[list[list[float]]]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "GeometryCollection":
        pieces = []
        for part in geom.geoms:
            pieces.extend(_polys(part, places))
        return pieces
    if geom.geom_type == "MultiPolygon":
        pieces = []
        for part in geom.geoms:
            pieces.extend(_polys(part, places))
        return pieces
    if geom.geom_type != "Polygon":
        return []
    rings = [_round_ring(geom.exterior.coords, places)]
    rings.extend(_round_ring(ring.coords, places) for ring in geom.interiors)
    rings = [ring for ring in rings if len(ring) >= 8]
    if not rings:
        return []
    return [rings]


def _keep_conus(geom) -> bool:
    if geom is None or geom.is_empty:
        return False
    centroid = geom.centroid
    return -130 < centroid.x < -65 and 23 < centroid.y < 50


def _records(resolution: str, category: str, name: str):
    import cartopy.io.shapereader as shpreader

    path = shpreader.natural_earth(resolution=resolution, category=category, name=name)
    return list(shpreader.Reader(path).records())


def _states():
    geoms = []
    for record in _records("10m", "cultural", "admin_1_states_provinces"):
        admin = record.attributes.get("admin") or record.attributes.get("adm0_name") or ""
        name = record.attributes.get("name") or ""
        if admin != "United States of America" or name in DROP_STATE:
            continue
        geom = record.geometry.intersection(FRAME)
        if not _keep_conus(geom):
            continue
        geoms.append(geom.simplify(SHORE_TOL, preserve_topology=True))
    return geoms


def _counties():
    import cartopy.io.shapereader as shpreader

    path = CACHE / "cb_2023_us_county_20m.shp"
    if not path.exists():
        raise SystemExit(f"Missing county shapefile at {path}")
    geoms = []
    for record in shpreader.Reader(str(path)).records():
        fp = str(record.attributes.get("STATEFP") or "")
        if fp in DROP_FP:
            continue
        geom = record.geometry
        if geom is None or not geom.intersects(FRAME):
            continue
        if not _keep_conus(geom):
            continue
        geoms.append(geom.simplify(0.012, preserve_topology=True))
    return geoms


def _lakes():
    found = []
    geoms = []
    for record in _records("10m", "physical", "lakes"):
        name = ""
        for key in ("name", "name_en", "NAME"):
            value = record.attributes.get(key)
            if value:
                name = str(value)
                break
        if name not in LAKE_NAMES:
            continue
        geom = record.geometry.intersection(FRAME)
        if geom.is_empty:
            continue
        found.append(name)
        geoms.append(geom.simplify(SHORE_TOL, preserve_topology=True))
    print("Lakes:", ", ".join(sorted(set(found))))
    return geoms


def _lines(geoms) -> list[np.ndarray]:
    lines = []
    for geom in geoms:
        polygons = []
        if geom.geom_type == "Polygon":
            polygons = [geom]
        elif geom.geom_type == "MultiPolygon":
            polygons = list(geom.geoms)
        elif geom.geom_type == "GeometryCollection":
            for part in geom.geoms:
                polygons.extend(_lines([part]) and [])
                if part.geom_type == "Polygon":
                    polygons.append(part)
                elif part.geom_type == "MultiPolygon":
                    polygons.extend(part.geoms)
        for poly in polygons:
            coords = np.asarray(poly.exterior.coords, dtype=float)
            if len(coords) >= 2:
                lines.append(coords)
    return lines


def _county_png(geoms) -> bytes:
    west, east, south, north = EXTENT
    aspect = (east - west) / (north - south)
    width_in = 16
    dpi = 180
    fig = plt.figure(figsize=(width_in, width_in / aspect), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_axis_off()
    ax.add_collection(
        LineCollection(
            _lines(geoms),
            colors="#d4d4d4",
            linewidths=0.45,
            capstyle="round",
            joinstyle="round",
        )
    )
    fig.patch.set_alpha(0)
    buffer = BytesIO()
    fig.savefig(buffer, dpi=dpi, format="png", transparent=True)
    plt.close(fig)
    return buffer.getvalue()


def _terrain() -> tuple[bytes, list[float]]:
    tif = CACHE / "GRAY_50M_SR_W.tif"
    tfw = CACHE / "GRAY_50M_SR_W.tfw"
    if not tif.exists():
        raise SystemExit(f"Missing terrain raster at {tif}")
    Image.MAX_IMAGE_PIXELS = None
    raw = np.asarray(Image.open(tif).convert("L"), dtype=np.float32)
    light = 255 - (255 - raw) * np.float32(0.30)
    pixel_w, _rot_x, _rot_y, pixel_h, origin_x, origin_y = (float(part) for part in tfw.read_text().split())
    height, width = light.shape
    full_west = origin_x - pixel_w / 2
    full_north = origin_y - pixel_h / 2
    full_east = full_west + pixel_w * width
    full_south = full_north + pixel_h * height
    pad = 1.2
    west, east, south, north = EXTENT
    west, east, south, north = west - pad, east + pad, south - pad, north + pad

    def col(lon: float) -> int:
        return int(round((lon - full_west) / (full_east - full_west) * width))

    def row(lat: float) -> int:
        return int(round((full_north - lat) / (full_north - full_south) * height))

    c0, c1 = max(0, col(west)), min(width, col(east))
    r0, r1 = max(0, row(north)), min(height, row(south))
    cropped = np.clip(light[r0:r1, c0:c1], 0, 255).astype(np.uint8)
    crop_west = full_west + c0 / width * (full_east - full_west)
    crop_east = full_west + c1 / width * (full_east - full_west)
    crop_north = full_north - r0 / height * (full_north - full_south)
    crop_south = full_north - r1 / height * (full_north - full_south)
    buffer = BytesIO()
    Image.fromarray(cropped, mode="L").save(buffer, format="JPEG", quality=74, optimize=True)
    return buffer.getvalue(), [crop_west, crop_east, crop_south, crop_north]


def main(vectors_only: bool = False) -> None:
    print("Reading states")
    states = _states()
    print("Reading counties")
    counties = _counties()
    print("Reading lakes")
    lakes = _lakes()
    # Cut the lakes out of the states. The remaining edge is the U.S. shoreline.
    # The Canadian shore is outside these polygons and is not stroked.
    print("Cutting the Great Lakes out of the states")
    water = unary_union([geom for geom in lakes if geom is not None and not geom.is_empty])
    states = [geom.difference(water) for geom in states]
    states = [geom for geom in states if geom is not None and not geom.is_empty]
    print("Union of the states")
    land = unary_union(states)
    out_js = ROOT / "lib" / "snow_basemap.js"
    out_terrain = ROOT / "lib" / "snow_terrain.jpg"
    out_counties = ROOT / "lib" / "snow_counties.png"
    if vectors_only:
        previous = json.loads(out_js.read_text(encoding="utf-8")[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))
        terrain_url = previous["terrain"]
        terrain_extent = previous["terrainExtent"]
        counties_url = previous["counties"]
    else:
        print("County lines")
        county_png = _county_png(counties)
        print("Terrain")
        terrain_jpg, terrain_extent = _terrain()
        terrain_extent = [round(value, 4) for value in terrain_extent]
        terrain_url = "/climate_imagery/snow_terrain.jpg?v=1"
        counties_url = "/climate_imagery/snow_counties.png?v=1"
        out_terrain.write_bytes(terrain_jpg)
        out_counties.write_bytes(county_png)
    payload = {
        "terrain": terrain_url,
        "terrainExtent": terrain_extent,
        "counties": counties_url,
        "land": _polys(land),
        "states": [poly for geom in states for poly in _polys(geom)],
        "lakes": [poly for geom in lakes for poly in _polys(geom)],
    }
    out_js.write_text("const SNOW_BASE = " + json.dumps(payload, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"terrain {out_terrain.stat().st_size:,} bytes")
    print(f"counties {out_counties.stat().st_size:,} bytes")
    print(f"basemap {out_js.stat().st_size:,} bytes")
    print(f"states {len(payload['states'])} lakes {len(payload['lakes'])} land {len(payload['land'])}")


if __name__ == "__main__":
    main(vectors_only="--vectors-only" in sys.argv)
