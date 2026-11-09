#!/usr/bin/env python3
"""7-day snowfall from the latest ECMWF open-data IFS and AIFS runs.

The field is accumulated snowfall (param sf), not snow depth. IFS stores
metres of water equivalent and AIFS stores kg m**-2. The GRIB units attribute
chooses the conversion. Inches of snow use a 10:1 snow-to-liquid ratio.
The newest cycle whose 7-day file is already published is the one drawn.
A missing file steps back one cycle. Some 06z and 18z runs do not reach 7 days.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from lib.ap_dates import _ABBR
from lib.snow_anomaly import EXTENT

EASTERN = ZoneInfo("America/New_York")
_CONUS = None
_VECTOR_MASKS: dict = {}

HOURS = 168
# Split each model cell before choosing a category. The browser then draws
# those finer cells as-is, so the bands follow the snowfall instead of the
# model grid and the category colors stay unmixed.
FINE = 8
EDGES = (0.5, 1.0, 3.0, 6.0, 9.0, 12.0, 18.0, 24.0)
SNOW_COLORS = [
    "#D4E8F4",
    "#A9D0EA",
    "#6AADD8",
    "#3B8CC4",
    "#246EAB",
    "#1A548E",
    "#122E5C",
    "#0C2248",
]
SNOW_LABELS = ["0.5–1 in.", "1–3", "3–6", "6–9", "9–12", "12–18", "18–24", "24+"]
# Google answered when the AWS replica was returning 503. The portal is the
# second try, then the other public replicas.
SOURCES = ("google", "ecmwf", "aws", "azure")
MODELS = (
    {
        "key": "ecmwf",
        "model": "ifs",
        "name": "IFS",
        "button": "ECMWF",
        "filename": "ecmwf-predicted-snowfall.png",
    },
    {
        "key": "aifs",
        "model": "aifs-single",
        "name": "AIFS",
        "button": "ECMWF-AIFS",
        "filename": "ecmwf-aifs-predicted-snowfall.png",
    },
)


def swe_to_inches(values, units: str) -> np.ndarray:
    """Convert snowfall water equivalent to inches of snow at 10:1.

    Metres (the IFS packing) use 39.3701 inches per metre. kg m**-2 and
    millimetres are the same depth of water and use 0.0393701.
    """
    key = units.strip().lower().replace("**", "").replace("^", "").replace(" ", "")
    if key in {"m", "metre", "metres", "meter", "meters", "mofwaterequivalent"}:
        factor = 39.3701 * 10.0
    elif key in {"kgm-2", "kgm2", "kg/m2"} or key.startswith("kgm") or key in {
        "mm",
        "millimetre",
        "millimetres",
        "millimeter",
        "millimeters",
    }:
        factor = 0.0393701 * 10.0
    else:
        raise ValueError(f"Unrecognized snowfall units: {units!r}")
    return np.asarray(values, dtype=np.float64) * factor


def snow_bin(inches) -> np.ndarray:
    """Category index. 0 is under 0.5 inch. A breakpoint opens the next category.

    Edges are 0.5, 1, 3, 6, 9, 12, 18, and 24. A value of 24 is category 8,
    which is the 24+ swatch.
    """
    values = np.atleast_1d(np.asarray(inches, dtype=np.float64))
    bins = np.zeros(values.shape, dtype=np.uint8)
    finite = np.isfinite(values)
    if finite.any():
        found = np.searchsorted(EDGES, values[finite], side="right").astype(np.uint8)
        bins[finite] = found
    if np.asarray(inches).ndim == 0:
        return bins[0]
    return bins


def _shift_lon(lon: np.ndarray) -> np.ndarray:
    shifted = np.asarray(lon, dtype=np.float64).copy()
    shifted[shifted > 180.0] = shifted[shifted > 180.0] - 360.0
    return shifted


def _conus_land():
    """United States land drawn on the snow map, including the Great Lakes holes."""
    global _CONUS
    if _CONUS is not None:
        return _CONUS
    import json

    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    from shapely.validation import make_valid

    path = Path(__file__).resolve().parent / "snow_basemap.js"
    script = path.read_text(encoding="utf-8")
    data = json.loads(script[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))
    geoms = []
    for poly in data["land"]:
        rings = []
        for ring in poly:
            coords = list(zip(ring[0::2], ring[1::2]))
            if len(coords) >= 4:
                rings.append(coords)
        if not rings:
            continue
        geom = Polygon(rings[0], rings[1:] if len(rings) > 1 else None)
        geoms.append(geom if geom.is_valid else make_valid(geom))
    _CONUS = unary_union(geoms)
    return _CONUS


def domain_max(inches, lat, lon, land, extent=EXTENT, highest: bool = True) -> dict:
    """Highest total on the contiguous U.S. land drawn on the map.

    Water and Canadian land inside the frame are ignored, so the marker stays
    off the Canadian side of the border. The colored field is unchanged.
    A tie goes to the northernmost cell, then the westernmost. Longitude may
    arrive as 0–360; values west of the antimeridian are shifted before the cut.
    """
    west, east, south, north = extent
    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = _shift_lon(lon)
    snow = np.asarray(inches, dtype=np.float64)
    mask_values = np.asarray(land, dtype=np.float64)
    if snow.shape != mask_values.shape:
        raise ValueError(f"Snowfall shape {snow.shape} does not match the land mask {mask_values.shape}")
    if snow.shape != (lat_values.size, lon_values.size):
        raise ValueError(f"Snowfall shape {snow.shape} does not match lat/lon sizes")
    inside = (
        (mask_values >= 0.5)
        & np.isfinite(snow)
        & (lat_values[:, None] >= south)
        & (lat_values[:, None] <= north)
        & (lon_values[None, :] >= west)
        & (lon_values[None, :] <= east)
    )
    rows, cols = np.nonzero(inside)
    if rows.size:
        from shapely import covers, points

        on_land = np.asarray(
            covers(_conus_land(), points(lon_values[cols], lat_values[rows])),
            dtype=bool,
        )
        inside = np.zeros(inside.shape, dtype=bool)
        inside[rows[on_land], cols[on_land]] = True
    if not inside.any():
        raise RuntimeError("No land cells in the snowfall domain")
    order = np.argsort(lat_values)[::-1]
    lon_order = np.argsort(lon_values)
    fill = -np.inf if highest else np.inf
    ranked = np.where(inside[order][:, lon_order], snow[order][:, lon_order], fill)
    index = int(np.argmax(ranked) if highest else np.argmin(ranked))
    row, col = np.unravel_index(index, ranked.shape)
    value = float(snow[order][:, lon_order][row, col])
    return {
        "lat": float(lat_values[order][row]),
        "lon": float(lon_values[lon_order][col]),
        "inches": value,
        "label": f"{value:.1f} in.",
    }


def _axis_step(centers: np.ndarray) -> float:
    if centers.size < 2:
        return 0.25
    return float(np.median(np.diff(centers)))


def _refine_centers(centers: np.ndarray, factor: int) -> np.ndarray:
    """Cell centers that cover the same outer edges as centers, factor times finer."""
    step = _axis_step(centers)
    first_edge = float(centers[0]) - step / 2.0
    last_edge = float(centers[-1]) + step / 2.0
    count = int(centers.size * factor)
    fine = (last_edge - first_edge) / count
    return first_edge + (np.arange(count) + 0.5) * fine


def _bilinear(values: np.ndarray, factor: int) -> np.ndarray:
    """Sample values at the centers of factor-by-factor cells inside each source cell."""
    src = np.asarray(values, dtype=np.float64)
    rows, cols = src.shape
    if factor <= 1:
        return src.copy()
    ys = np.clip((np.arange(rows * factor) + 0.5) / factor - 0.5, 0, rows - 1)
    xs = np.clip((np.arange(cols * factor) + 0.5) / factor - 0.5, 0, cols - 1)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, rows - 1)
    x1 = np.minimum(x0 + 1, cols - 1)
    wy = (ys - y0)[:, None]
    wx = (xs - x0)[None, :]
    north = src[y0[:, None], x0[None, :]] * (1.0 - wx) + src[y0[:, None], x1[None, :]] * wx
    south = src[y1[:, None], x0[None, :]] * (1.0 - wx) + src[y1[:, None], x1[None, :]] * wx
    return north * (1.0 - wy) + south * wy


def _drawn_land_mask(lat_values: np.ndarray, lon_values: np.ndarray) -> np.ndarray:
    """True where a fine-cell center lies on the United States land drawn on the map.

    Lake holes and everything outside that shoreline are false. The same grid
    is reused, because the temperature pages share one map frame.
    """
    key = (
        round(float(lat_values[0]), 6),
        round(float(lat_values[-1]), 6),
        int(lat_values.size),
        round(float(lon_values[0]), 6),
        round(float(lon_values[-1]), 6),
        int(lon_values.size),
    )
    cached = _VECTOR_MASKS.get(key)
    if cached is not None and cached.shape == (lat_values.size, lon_values.size):
        return cached
    from shapely import covers, points

    lon_grid, lat_grid = np.meshgrid(lon_values, lat_values)
    on_land = np.asarray(covers(_conus_land(), points(lon_grid, lat_grid)), dtype=bool)
    _VECTOR_MASKS[key] = on_land
    return on_land


def _simplify_line(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Douglas-Peucker. Distance is in degrees, which matches the map's linear projection."""
    count = len(points)
    if count <= 2:
        return points
    keep = [False] * count
    keep[0] = True
    keep[-1] = True
    stack = [(0, count - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        x1, y1 = points[start]
        x2, y2 = points[end]
        dx = x2 - x1
        dy = y2 - y1
        span = (dx * dx + dy * dy) ** 0.5
        farthest = 0.0
        index = -1
        for at in range(start + 1, end):
            x_value, y_value = points[at]
            if span == 0.0:
                distance = ((x_value - x1) ** 2 + (y_value - y1) ** 2) ** 0.5
            else:
                distance = abs(dy * x_value - dx * y_value + x2 * y1 - y2 * x1) / span
            if distance > farthest:
                farthest = distance
                index = at
        if farthest > tolerance and index >= 0:
            keep[index] = True
            stack.append((start, index))
            stack.append((index, end))
    return [points[at] for at in range(count) if keep[at]]


def _stitch_segments(segments: list[tuple]) -> list[list[tuple[float, float]]]:
    """Join marching-squares segments that share an edge. Edge identity, not coordinates."""
    adjacency: dict[tuple, list[tuple[int, tuple[float, float]]]] = {}
    for index, (edge_a, point_a, edge_b, point_b) in enumerate(segments):
        adjacency.setdefault(edge_a, []).append((index, point_a))
        adjacency.setdefault(edge_b, []).append((index, point_b))
    unused = set(range(len(segments)))

    def follow(start_edge: tuple, start_index: int) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        edge = start_edge
        index = start_index
        first = True
        while index in unused:
            unused.discard(index)
            edge_a, point_a, edge_b, point_b = segments[index]
            if edge == edge_a:
                near, far, nxt = point_a, point_b, edge_b
            else:
                near, far, nxt = point_b, point_a, edge_a
            if first:
                points.append(near)
                first = False
            points.append(far)
            edge = nxt
            index = -1
            for candidate, _point in adjacency[edge]:
                if candidate in unused:
                    index = candidate
                    break
            if index < 0:
                break
        return points

    lines: list[list[tuple[float, float]]] = []
    for edge, links in list(adjacency.items()):
        if sum(1 for index, _point in links if index in unused) != 1:
            continue
        index = next(index for index, _point in links if index in unused)
        lines.append(follow(edge, index))
    while unused:
        index = next(iter(unused))
        lines.append(follow(segments[index][0], index))
    return lines


def smooth_contour_field(values, lat, lon, on_land, sigma_deg: float) -> np.ndarray:
    """Gaussian smooth in degrees. Off-land cells do not pull the line.

    The kernel is normalized by the land weight, so a lake or a coast
    contributes no temperature. sigma_deg is the same distance on every model.
    """
    grid = np.asarray(values, dtype=np.float64)
    if sigma_deg <= 0:
        return grid.copy()
    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = np.asarray(lon, dtype=np.float64)
    dlat = abs(float(np.median(np.diff(lat_values)))) if lat_values.size > 1 else float(sigma_deg)
    dlon = abs(float(np.median(np.diff(lon_values)))) if lon_values.size > 1 else float(sigma_deg)
    sigma_y = float(sigma_deg) / dlat if dlat else 0.0
    sigma_x = float(sigma_deg) / dlon if dlon else 0.0
    land = np.asarray(on_land, dtype=bool) & np.isfinite(grid)
    if not land.any() or (sigma_y < 0.35 and sigma_x < 0.35):
        return grid.copy()
    from scipy.ndimage import gaussian_filter

    weight = land.astype(np.float64)
    filled = np.where(land, grid, 0.0)
    number = gaussian_filter(filled, sigma=(sigma_y, sigma_x), mode="constant", cval=0.0)
    denom = gaussian_filter(weight, sigma=(sigma_y, sigma_x), mode="constant", cval=0.0)
    smoothed = grid.copy()
    good = land & (denom > 1e-3)
    smoothed[good] = number[good] / denom[good]
    return smoothed


def contour_lines(values, lat, lon, level: float, on_land=None) -> list[list[float]]:
    """Lon/lat polylines where the refined field crosses level.

    lat is north-to-south and lon is west-to-east, matching the packed grid.
    An edge is kept only when both ends are finite and on land, so the line
    stops at the drawn shore and at lake holes. A node that sits on the level
    is nudged just above it, and a four-crossing cell uses the center average.
    Each line is [lon, lat, lon, lat, ...], simplified to about 0.02°.
    """
    grid = np.asarray(values, dtype=np.float64)
    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = np.asarray(lon, dtype=np.float64)
    if grid.ndim != 2 or grid.shape != (lat_values.size, lon_values.size):
        raise ValueError("contour grid does not match lat and lon")
    if grid.shape[0] < 2 or grid.shape[1] < 2:
        return []
    nudged = grid.copy()
    hit = np.isfinite(nudged) & (nudged == level)
    nudged[hit] += max(abs(float(level)), 1.0) * 1e-8
    finite = np.isfinite(nudged)
    below = nudged < level
    h_cross = finite[:, :-1] & finite[:, 1:] & (below[:, :-1] != below[:, 1:])
    v_cross = finite[:-1, :] & finite[1:, :] & (below[:-1, :] != below[1:, :])
    if on_land is None:
        h_ok = h_cross
        v_ok = v_cross
    else:
        land = np.asarray(on_land, dtype=bool)
        if land.shape != grid.shape:
            raise ValueError("land mask does not match the contour grid")
        h_ok = h_cross & land[:, :-1] & land[:, 1:]
        v_ok = v_cross & land[:-1, :] & land[1:, :]

    def edge_points(mask: np.ndarray, horizontal: bool) -> dict[tuple, tuple[float, float]]:
        rows, cols = np.nonzero(mask)
        if rows.size == 0:
            return {}
        if horizontal:
            v0 = nudged[rows, cols]
            v1 = nudged[rows, cols + 1]
            fraction = np.clip((level - v0) / (v1 - v0), 0.0, 1.0)
            point_lon = lon_values[cols] + fraction * (lon_values[cols + 1] - lon_values[cols])
            point_lat = lat_values[rows]
            kind = "h"
        else:
            v0 = nudged[rows, cols]
            v1 = nudged[rows + 1, cols]
            fraction = np.clip((level - v0) / (v1 - v0), 0.0, 1.0)
            point_lon = lon_values[cols]
            point_lat = lat_values[rows] + fraction * (lat_values[rows + 1] - lat_values[rows])
            kind = "v"
        return {
            (kind, int(row), int(col)): (float(lon_p), float(lat_p))
            for row, col, lon_p, lat_p in zip(
                rows.tolist(), cols.tolist(), point_lon.tolist(), point_lat.tolist()
            )
        }

    def edge_keys(mask: np.ndarray, kind: str) -> set[tuple]:
        found_rows, found_cols = np.nonzero(mask)
        return {(kind, int(row), int(col)) for row, col in zip(found_rows.tolist(), found_cols.tolist())}

    points = edge_points(h_cross, True)
    points.update(edge_points(v_cross, False))
    valid = edge_keys(h_ok, "h") | edge_keys(v_ok, "v")
    rows, cols = np.nonzero(
        h_cross[:-1, :] | h_cross[1:, :] | v_cross[:, :-1] | v_cross[:, 1:]
    )
    segments = []
    for row, col in zip(rows.tolist(), cols.tolist()):
        names = {
            "top": ("h", row, col),
            "right": ("v", row, col + 1),
            "bottom": ("h", row + 1, col),
            "left": ("v", row, col),
        }
        crossed = [name for name in ("top", "right", "bottom", "left") if names[name] in points]
        if len(crossed) == 2:
            pairs = ((crossed[0], crossed[1]),)
        elif len(crossed) == 4:
            center = float(nudged[row : row + 2, col : col + 2].mean())
            # The center joins one diagonal. Pair the edges so that diagonal stays connected.
            if bool(below[row, col]) == (center < level):
                pairs = (("top", "right"), ("left", "bottom"))
            else:
                pairs = (("top", "left"), ("right", "bottom"))
        else:
            continue
        for first_name, second_name in pairs:
            key_a = names[first_name]
            key_b = names[second_name]
            if key_a in valid and key_b in valid:
                segments.append((key_a, points[key_a], key_b, points[key_b]))
    lines = []
    for line in _stitch_segments(segments):
        flat: list[float] = []
        previous = None
        for lon_p, lat_p in _simplify_line(line, 0.02):
            point = (round(float(lon_p), 3), round(float(lat_p), 3))
            if point == previous:
                continue
            flat.extend(point)
            previous = point
        if len(flat) >= 4:
            lines.append(flat)
    return lines


def pack_snow(
    inches,
    lat,
    lon,
    land,
    extent=EXTENT,
    classify=None,
    empty=0.0,
    vector_land: bool = False,
    contour: float | None = None,
    contour_sigma: float = 0.0,
) -> tuple[dict, str]:
    """North-to-south category PNG. 0 is uncolored, including water and totals under 0.5 inch.

    Inches are resampled to a finer grid first. Categories are chosen after that,
    so a boundary can curve through a model cell instead of filling the whole cell.
    The model land mask is the default. Temperature passes vector_land so a cell
    on the drawn shore stays colored when the coarser mask calls it water.
    A contour level is traced on that same refined field after the land mask.
    contour_sigma, in degrees, smooths the field before the line is traced.
    """
    import base64
    from io import BytesIO

    from PIL import Image

    west, east, south, north = extent
    lat_values = np.asarray(lat, dtype=np.float64)
    lon_values = _shift_lon(lon)
    snow = np.asarray(inches, dtype=np.float64)
    mask_values = np.asarray(land, dtype=np.float64)
    lat_order = np.argsort(lat_values)[::-1]
    lon_order = np.argsort(lon_values)
    lat_values = lat_values[lat_order]
    lon_values = lon_values[lon_order]
    snow = snow[lat_order][:, lon_order]
    mask_values = mask_values[lat_order][:, lon_order]
    dlat = abs(float(lat_values[1] - lat_values[0])) if lat_values.size > 1 else 0.25
    dlon = abs(float(lon_values[1] - lon_values[0])) if lon_values.size > 1 else 0.25
    lat_keep = (lat_values >= south - dlat) & (lat_values <= north + dlat)
    lon_keep = (lon_values >= west - dlon) & (lon_values <= east + dlon)
    if not lat_keep.any() or not lon_keep.any():
        raise RuntimeError("Snowfall grid does not cover the map")
    snow = snow[lat_keep][:, lon_keep]
    mask_values = mask_values[lat_keep][:, lon_keep]
    lat_values = lat_values[lat_keep]
    lon_values = lon_values[lon_keep]
    filled = snow if empty is None else np.nan_to_num(snow, nan=empty)
    snow = _bilinear(filled, FINE)
    lat_values = _refine_centers(lat_values, FINE)
    lon_values = _refine_centers(lon_values, FINE)
    bins = np.asarray((classify or snow_bin)(snow), dtype=np.uint8)
    if vector_land:
        bins[~_drawn_land_mask(lat_values, lon_values)] = 0
    else:
        mask_values = _bilinear(mask_values, FINE)
        bins[~(mask_values >= 0.5)] = 0
    buffer = BytesIO()
    Image.fromarray(bins, mode="L").save(buffer, format="PNG", optimize=True)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    meta = {
        "nlat": int(bins.shape[0]),
        "nlon": int(bins.shape[1]),
        "latNorth": float(lat_values[0]),
        "latSouth": float(lat_values[-1]),
        "lonWest": float(lon_values[0]),
        "lonEast": float(lon_values[-1]),
    }
    if contour is not None:
        field = snow
        if contour_sigma:
            field = smooth_contour_field(
                snow, lat_values, lon_values, bins > 0, float(contour_sigma)
            )
        meta["contour"] = contour_lines(
            field, lat_values, lon_values, float(contour), on_land=bins > 0
        )
    return meta, payload


def snow_scale_html(hidden: bool = True, colors=None, labels=None, freeze: dict | None = None) -> str:
    """Equal-width category blocks. Each label is centered, and the last block has no arrow."""
    palette = list(SNOW_COLORS if colors is None else colors)
    names = list(SNOW_LABELS if labels is None else labels)
    if len(palette) != len(names):
        raise ValueError(f"{len(palette)} colors for {len(names)} labels")
    bands = len(palette)
    wide = " wide" if bands > 8 else ""
    # Equal blocks, each at least as wide as the longest label, so the words
    # stay apart. A narrow phone scrolls the row instead of stacking them.
    longest = max((len(label) for label in names), default=2)
    track = (max(longest, 2) + 2.2) * bands
    cells = []
    ticks = []
    for index, color in enumerate(palette):
        left = index / bands * 100
        width = 100 / bands
        center = (index + 0.5) / bands * 100
        cells.append(
            f'<i style="left:{left:.4f}%;width:calc({width:.4f}% - 1px);background:{color}"></i>'
        )
        label = names[index].replace("&", "&amp;").replace("<", "&lt;")
        ticks.append(f'<span style="left:{center:.4f}%">{label}</span>')
    hidden_attr = " hidden" if hidden else ""
    key = ""
    if freeze:
        label = str(freeze["label"]).replace("&", "&amp;").replace("<", "&lt;")
        casing = freeze["casing"]
        color = freeze["color"]
        key = (
            f'<div class="freeze-key"><svg width="64" height="14" viewBox="0 0 64 14" aria-hidden="true">'
            f'<line x1="2" y1="7" x2="62" y2="7" stroke="{casing}" stroke-width="9" stroke-dasharray="16 11"/>'
            f'<line x1="2" y1="7" x2="62" y2="7" stroke="{color}" stroke-width="5" stroke-dasharray="16 11"/>'
            f"</svg><span>{label}</span></div>"
        )
    return (
        f'<div class="scale snow-scale{wide}" style="--legend-min:{track:.1f}ch" id="snow-scale"{hidden_attr}>'
        f'<div class="legend-track">'
        f'<div class="swatches">{"".join(cells)}</div>'
        f'<div class="ticks">{"".join(ticks)}</div>'
        f"</div>{key}</div>"
    )


def _eastern(moment: datetime) -> datetime:
    """Forecast cycles are UTC. A naive datetime is that cycle, not local time."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(EASTERN)


def _clock(moment: datetime) -> str:
    if moment.minute == 0 and moment.hour in (0, 12):
        return "midnight" if moment.hour == 0 else "noon"
    suffix = "a.m." if moment.hour < 12 else "p.m."
    hour = moment.hour % 12 or 12
    if moment.minute:
        return f"{hour}:{moment.minute:02d} {suffix}"
    return f"{hour} {suffix}"


def _day(moment: datetime) -> str:
    return f"{_ABBR[moment.month]} {moment.day}"


def _cycle_phrase(cycle: datetime) -> str:
    moment = _eastern(cycle)
    return f"{_clock(moment)} ET {_day(moment)}, {moment.year}"


def _window_phrase(cycle: datetime) -> str:
    start = _eastern(cycle)
    end = _eastern(cycle + timedelta(hours=HOURS))
    if start.year == end.year:
        return (
            f"{_clock(start)} {_day(start)} through "
            f"{_clock(end)} {_day(end)}, {end.year} ET"
        )
    return (
        f"{_clock(start)} ET {_day(start)}, {start.year} through "
        f"{_clock(end)} ET {_day(end)}, {end.year}"
    )


def forecast_source(name: str, cycle: datetime) -> str:
    return (
        f"ECMWF {name} open data snowfall, accumulated over the 7 days "
        f"from the {_cycle_phrase(cycle)} run and shown as inches of snow "
        "at a 10:1 snow-to-liquid ratio."
    )


def make_view(spec: dict, cycle: datetime, inches, lat, lon, land) -> dict:
    """One forecast the page can switch to. The PNG is separate from the JSON fields."""
    pin = domain_max(inches, lat, lon, land)
    meta, field = pack_snow(inches, lat, lon, land)
    window = _window_phrase(cycle)
    return {
        "key": spec["key"],
        "button": spec["button"],
        "title": "Weekly snowfall forecast",
        "span": f"From {window}",
        "rank": f"Maximum {pin['label']}",
        "source": forecast_source(spec["name"], cycle),
        "alt": (
            f"Weekly snowfall forecast from ECMWF {spec['name']} "
            f"from {window}. The most in this map is {pin['label']}."
        ),
        "filename": spec["filename"],
        "kind": "snow",
        # The category grid is several pixels finer than the map, so smoothing
        # only softens the boundary. It does not blend a whole model cell.
        "smooth": True,
        "colors": list(SNOW_COLORS),
        "over": SNOW_COLORS[-1],
        "pin": {
            "lon": round(pin["lon"], 4),
            "lat": round(pin["lat"], 4),
            "inches": round(pin["inches"], 2),
            "label": pin["label"],
        },
        "field": field,
        "nlat": meta["nlat"],
        "nlon": meta["nlon"],
        "latNorth": round(meta["latNorth"], 5),
        "latSouth": round(meta["latSouth"], 5),
        "lonWest": round(meta["lonWest"], 5),
        "lonEast": round(meta["lonEast"], 5),
    }


def _surface_request(model: str) -> dict:
    """Extra open-data request keys for this model.

    IFS at 0.1° is published as separate surface and pressure-level files.
    Without levtype the client asks for both. Surface parameters are in the
    -sfc file. AIFS is one 0.25° file and does not take levtype.
    """
    if model == "ifs":
        return {"levtype": "sfc"}
    return {}


def _client(source: str, model: str):
    from ecmwf.opendata import Client

    # 0p1 is the 0.1° IFS open-data grid, about 9 km, interpolated from the
    # native forecast. 0p25 is the 25 km grid. AIFS open data is 0.25° only.
    resol = "0p1" if model == "ifs" else "0p25"
    return Client(
        source=source,
        model=model,
        resol=resol,
        maximum_retries=4,
        retry_after=8,
    )


def _as_cycle(value) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    raise RuntimeError(f"Unexpected cycle value {value!r}")


def _latest_cycle(model: str) -> datetime:
    errors = []
    for source in SOURCES:
        try:
            found = _client(source, model).latest(
                type="fc", stream="oper", step=HOURS, param="sf", **_surface_request(model)
            )
            cycle = _as_cycle(found)
            print(f"{model} latest 7-day file is {cycle:%Y-%m-%d %H}z via {source}")
            return cycle
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            print(f"{source} has no {model} 7-day file yet: {exc}")
    raise RuntimeError(f"No recent {model} snowfall run ({'; '.join(errors)})")


def _retrieve(model: str, param: str, step: int, target: Path, cycle: datetime, sources: tuple[str, ...]) -> str:
    errors = []
    for source in sources:
        if target.exists():
            target.unlink()
        try:
            _client(source, model).retrieve(
                type="fc",
                stream="oper",
                step=step,
                param=param,
                date=cycle.strftime("%Y-%m-%d"),
                time=cycle.hour,
                target=str(target),
                **_surface_request(model),
            )
            print(f"Downloaded {model} {param} step {step} from {source} at {cycle:%Y-%m-%d %H}z")
            return source
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            print(f"{source} {model} {param} step {step} failed: {exc}")
            if target.exists():
                target.unlink()
    raise RuntimeError(f"Could not download {model} {param} step {step} ({'; '.join(errors)})")


def _read_pair(sf_path: Path, lsm_path: Path):
    import xarray as xr

    snow_ds = xr.open_dataset(sf_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    mask_ds = xr.open_dataset(lsm_path, engine="cfgrib", backend_kwargs={"indexpath": ""})
    try:
        snow = snow_ds["sf"]
        mask = mask_ds["lsm"]
        units = snow.attrs.get("units") or snow.attrs.get("GRIB_units")
        if not units:
            raise ValueError(f"{sf_path.name} has no snowfall units")
        lat = np.asarray(snow.latitude.values, dtype=np.float64)
        lon = np.asarray(snow.longitude.values, dtype=np.float64)
        if snow.shape != mask.shape:
            raise ValueError(f"Land mask shape {mask.shape} does not match snowfall {snow.shape}")
        if not np.allclose(lat, np.asarray(mask.latitude.values)) or not np.allclose(
            lon, np.asarray(mask.longitude.values)
        ):
            raise ValueError(f"Land mask grid does not match snowfall for {sf_path.name}")
        print(f"{sf_path.name} units {units}")
        return swe_to_inches(snow.values, str(units)), lat, lon, np.asarray(mask.values, dtype=np.float64)
    finally:
        snow_ds.close()
        mask_ds.close()


def _download_model(spec: dict, directory: Path) -> dict:
    model = spec["model"]
    cycle = _latest_cycle(model)
    errors = []
    for _attempt in range(4):
        sf_path = directory / f"{model}-sf.grib2"
        lsm_path = directory / f"{model}-lsm.grib2"
        try:
            source = _retrieve(model, "sf", HOURS, sf_path, cycle, SOURCES)
            _retrieve(model, "lsm", 0, lsm_path, cycle, (source, *SOURCES))
            inches, lat, lon, land = _read_pair(sf_path, lsm_path)
            view = make_view(spec, cycle, inches, lat, lon, land)
            print(f"{spec['button']}: {view['rank']}")
            return view
        except Exception as exc:
            errors.append(f"{cycle:%Y-%m-%d %H}z: {exc}")
            print(f"{model} {cycle:%Y-%m-%d %H}z failed: {exc}")
            cycle = cycle - timedelta(hours=6)
    raise RuntimeError(f"No usable {spec['button']} snowfall run ({'; '.join(errors)})")


def load_forecasts(work: Path) -> dict[str, dict]:
    """Download both models into work/grib and return their page records."""
    directory = work / "grib"
    directory.mkdir(parents=True, exist_ok=True)
    return {spec["key"]: _download_model(spec, directory) for spec in MODELS}
