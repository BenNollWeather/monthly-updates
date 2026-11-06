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


def pack_snow(
    inches,
    lat,
    lon,
    land,
    extent=EXTENT,
    classify=None,
    empty=0.0,
    vector_land: bool = False,
) -> tuple[dict, str]:
    """North-to-south category PNG. 0 is uncolored, including water and totals under 0.5 inch.

    Inches are resampled to a finer grid first. Categories are chosen after that,
    so a boundary can curve through a model cell instead of filling the whole cell.
    The model land mask is the default. Temperature passes vector_land so a cell
    on the drawn shore stays colored when the coarser mask calls it water.
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
    return meta, payload


def snow_scale_html(hidden: bool = True, colors=None, labels=None) -> str:
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
    return (
        f'<div class="scale snow-scale{wide}" style="--legend-min:{track:.1f}ch" id="snow-scale"{hidden_attr}>'
        f'<div class="legend-track">'
        f'<div class="swatches">{"".join(cells)}</div>'
        f'<div class="ticks">{"".join(ticks)}</div>'
        "</div></div>"
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
