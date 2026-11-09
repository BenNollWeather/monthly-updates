#!/usr/bin/env python3
"""7-day precipitation and temperature from the latest ECMWF open-data IFS and AIFS runs.

Precipitation is the 7-day total, drawn in inches. Totals under 0.1 inch stay
uncolored. IFS temperature is the highest and lowest 2 m temperature since the
previous step: 3-hour extremes through 144 hours, then 6-hour extremes through
168 hours. AIFS open data has no period extremes, so those maps use the highest
and lowest 2 m temperature at 6-hour steps. Both temperature maps share one
scale of 10°F bins, from −10°F and lower through 110°F and higher.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.c3s_globes import _seo, _site_nav  # noqa: E402
from lib.snow_anomaly import (  # noqa: E402
    BASEMAP_URL,
    EXTENT,
    FRAME,
    STATE_LABELS,
    _forecast_images,
    _label_row,
    _view_buttons,
    land_bounds,
    scale_html,
)
from lib.population import freezing_population_note  # noqa: E402
from lib.snow_forecast import (  # noqa: E402
    HOURS,
    SOURCES,
    _as_cycle,
    _client,
    _cycle_phrase,
    _retrieve,
    _surface_request,
    _window_phrase,
    domain_max,
    pack_snow,
    snow_scale_html,
)

# AIFS publishes instantaneous 2 m temperature every 6 hours.
AIFS_TEMP_STEPS = tuple(range(6, HOURS + 1, 6))
# IFS 00/12 files are 3-hourly through 144 hours and 6-hourly after that.
# mx2t3/mn2t3 cover the previous 3 hours. mx2t6/mn2t6 cover the previous 6 hours.
IFS_TEMP_3H = tuple(range(3, 145, 3))
IFS_TEMP_6H = (150, 156, 162, 168)
RAIN_PATH = "/weather/rain"
MAX_PATH = "/weather/temperature-maximum"
MIN_PATH = "/weather/temperature-minimum"
RAIN_TITLE = "Weekly precipitation forecast"
MAX_TITLE = "Weekly maximum temperature"
MIN_TITLE = "Weekly minimum temperature"
# A 1×1 image keeps the shared page template valid. Forecast-only pages do not paint it.
BLANK_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# Seven-day totals. A breakpoint opens the next bin, and 8 inches is the 8+ swatch.
RAIN_EDGES = (0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 8.0)
# Sampled from the NASA precipitation map on the crops-and-forests article, cool to warm.
RAIN_COLORS = ["#00546C", "#039DC4", "#7EF5E2", "#25C403", "#F7F700", "#FF8400", "#FF1E00"]
RAIN_LABELS = ["0.1–0.25 in.", "0.25–0.50", "0.50–1.00", "1.00–2.00", "2–4", "4–8", "8+"]

# 10°F bins from −10°F downward through 110°F upward. The label is the lower
# bound of the bin, so 70 is 70 up to but not including 80. Everything below
# 0°F shares the −10 color, and 110°F and warmer share the last color.
TEMP_EDGES = (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110)
# Esri meaningful-temperature colors. The pale and near-black ends are the
# open bins, and 30°F keeps the navy band that contains freezing.
TEMP_COLORS = [
    "#E4F0FF",
    "#A7BFE3",
    "#7F9BC3",
    "#4D6591",
    "#26436F",
    "#275B80",
    "#287593",
    "#648D89",
    "#ABA87D",
    "#C19D61",
    "#BE704C",
    "#9F294C",
    "#3D0216",
]
TEMP_LABELS = [
    "−10°F",
    "0s",
    "10s",
    "20s",
    "30s",
    "40s",
    "50s",
    "60s",
    "70s",
    "80s",
    "90s",
    "100s",
    "110s",
]
MODELS = (
    {"key": "ecmwf", "model": "ifs", "name": "IFS", "button": "ECMWF"},
    {"key": "aifs", "model": "aifs-single", "name": "AIFS", "button": "ECMWF-AIFS"},
)


def liquid_inches(values, units: str) -> np.ndarray:
    """Convert accumulated precipitation to inches. There is no snow ratio."""
    key = units.strip().lower().replace("**", "").replace("^", "").replace(" ", "")
    if key in {"m", "metre", "metres", "meter", "meters", "mofwaterequivalent"}:
        factor = 39.3701
    elif key in {"kgm-2", "kgm2", "kg/m2"} or key.startswith("kgm") or key in {
        "mm",
        "millimetre",
        "millimetres",
        "millimeter",
        "millimeters",
    }:
        factor = 0.0393701
    else:
        raise ValueError(f"Unrecognized precipitation units: {units!r}")
    return np.asarray(values, dtype=np.float64) * factor


def to_fahrenheit(values, units: str) -> np.ndarray:
    key = units.strip().lower().replace(" ", "")
    data = np.asarray(values, dtype=np.float64)
    if key in {"k", "kelvin"}:
        return (data - 273.15) * 9.0 / 5.0 + 32.0
    if key in {"c", "celsius", "degc", "°c"}:
        return data * 9.0 / 5.0 + 32.0
    raise ValueError(f"Unrecognized temperature units: {units!r}")


def rain_bin(inches) -> np.ndarray:
    """Category index. 0 is under 0.1 inch. 8 inches and above is the 8+ swatch."""
    values = np.atleast_1d(np.asarray(inches, dtype=np.float64))
    bins = np.zeros(values.shape, dtype=np.uint8)
    finite = np.isfinite(values)
    if finite.any():
        bins[finite] = np.searchsorted(RAIN_EDGES, values[finite], side="right").astype(np.uint8)
    if np.asarray(inches).ndim == 0:
        return bins[0]
    return bins


def temp_bin(degrees) -> np.ndarray:
    """Category index. 0 is missing. 1 is below 0°F and the last index is 110°F and above.

    A breakpoint opens the next 10°F bin, so 70°F is the 70 color and 32°F stays on 30.
    """
    values = np.atleast_1d(np.asarray(degrees, dtype=np.float64))
    bins = np.zeros(values.shape, dtype=np.uint8)
    finite = np.isfinite(values)
    if finite.any():
        found = np.searchsorted(TEMP_EDGES, values[finite], side="right").astype(np.uint8) + 1
        bins[finite] = found
    if np.asarray(degrees).ndim == 0:
        return bins[0]
    return bins


def format_temp(value: float) -> str:
    rounded = int(np.round(float(value)))
    if rounded < 0:
        return f"−{abs(rounded)}°F"
    return f"{rounded}°F"


def _latest_cycle(model: str, param: str) -> datetime:
    errors = []
    for source in SOURCES:
        try:
            found = _client(source, model).latest(
                type="fc", stream="oper", step=HOURS, param=param, **_surface_request(model)
            )
            cycle = _as_cycle(found)
            print(f"{model} latest 7-day {param} file is {cycle:%Y-%m-%d %H}z via {source}")
            return cycle
        except Exception as exc:
            errors.append(f"{source}: {exc}")
            print(f"{source} has no {model} 7-day {param} file yet: {exc}")
    raise RuntimeError(f"No recent {model} {param} run ({'; '.join(errors)})")


def _retrieve_steps(model: str, param: str, steps: tuple[int, ...], target: Path, cycle: datetime) -> None:
    """One GRIB message per step, concatenated in step order.

    A multi-step open-data request keeps only the steps the index contains and
    still reports success. Each step is fetched on its own so a short file
    cannot pass for a full week.
    """
    if target.exists():
        target.unlink()
    if len(steps) == 1:
        _retrieve(model, param, steps[0], target, cycle, SOURCES)
        return
    parts = []
    missing = []
    preferred: tuple[str, ...] = SOURCES
    for step in steps:
        part = target.with_name(f"{target.stem}-step-{step}.grib2")
        try:
            source = _retrieve(model, param, step, part, cycle, preferred)
            parts.append(part.read_bytes())
            preferred = (source, *tuple(item for item in SOURCES if item != source))
        except Exception as exc:
            missing.append(f"{step}: {exc}")
        finally:
            if part.exists():
                part.unlink()
    if missing or len(parts) != len(steps):
        if target.exists():
            target.unlink()
        detail = "; ".join(missing[:4]) if missing else "no steps"
        raise RuntimeError(f"Incomplete {model} {param} download ({detail})")
    target.write_bytes(b"".join(parts))


def _data_var(dataset, short_name: str):
    if short_name in dataset.data_vars:
        return dataset[short_name]
    aliases = {short_name}
    if short_name == "2t":
        aliases.add("t2m")
    for variable in dataset.data_vars.values():
        grib_name = str(variable.attrs.get("GRIB_shortName") or variable.attrs.get("shortName") or "")
        if grib_name == short_name or variable.name in aliases:
            return variable
    if len(dataset.data_vars) == 1:
        return next(iter(dataset.data_vars.values()))
    raise KeyError(short_name)


def _iter_planes(field):
    """Yield one latitude/longitude grid at a time.

    A 0.1° stack of 52 temperature steps is several gigabytes. Indexing one
    leading coordinate at a time keeps a single grid in memory. The order
    matches the flattened stack from _read_stack.
    """
    if field.ndim < 2:
        raise ValueError(f"{field.name} is not a grid")
    leading = field.dims[:-2]
    if not leading:
        yield np.asarray(field.values, dtype=np.float64)
        return
    sizes = tuple(int(field.sizes[dim]) for dim in leading)
    for index in np.ndindex(sizes):
        selection = {dim: int(at) for dim, at in zip(leading, index)}
        yield np.asarray(field.isel(selection).values, dtype=np.float64)


def _accumulate(planes, combine):
    """Fold grids with np.fmax or np.fmin. That matches nanmax or nanmin of the stack."""
    reduced = None
    count = 0
    for plane in planes:
        values = np.asarray(plane, dtype=np.float64)
        reduced = values if reduced is None else combine(reduced, values)
        count += 1
    if reduced is None:
        raise ValueError("No grids to fold")
    return reduced, count


def _read_stack(path: Path, short_name: str):
    import cfgrib

    datasets = cfgrib.open_datasets(str(path), backend_kwargs={"indexpath": ""})
    planes = []
    lat = lon = None
    units = ""
    try:
        for dataset in datasets:
            try:
                field = _data_var(dataset, short_name)
            except KeyError:
                continue
            units = str(field.attrs.get("units") or field.attrs.get("GRIB_units") or units)
            lat = np.asarray(field.latitude.values, dtype=np.float64)
            lon = np.asarray(field.longitude.values, dtype=np.float64)
            values = np.asarray(field.values, dtype=np.float64)
            if values.ndim < 2:
                raise ValueError(f"{path.name} {short_name} is not a grid")
            planes.append(values.reshape(-1, values.shape[-2], values.shape[-1]))
    finally:
        for dataset in datasets:
            dataset.close()
    if not planes or lat is None or lon is None:
        raise ValueError(f"{path.name} has no {short_name} grid")
    if not units:
        raise ValueError(f"{path.name} has no {short_name} units")
    stack = np.concatenate(planes, axis=0)
    print(f"{path.name} {short_name} {stack.shape[0]} step(s), units {units}")
    return stack, lat, lon, units


def _same_grid(lat, lon, other_lat, other_lon, what: str) -> None:
    if not np.allclose(lat, other_lat) or not np.allclose(lon, other_lon):
        raise ValueError(f"{what} grid does not match the land mask")


def _fold_stack(path: Path, short_name: str, combine):
    """Running nanmax or nanmin, one GRIB message at a time."""
    import cfgrib

    datasets = cfgrib.open_datasets(str(path), backend_kwargs={"indexpath": ""})
    reduced = None
    lat = lon = None
    units = ""
    count = 0
    try:
        for dataset in datasets:
            try:
                field = _data_var(dataset, short_name)
            except KeyError:
                continue
            found_units = str(field.attrs.get("units") or field.attrs.get("GRIB_units") or "")
            if units and found_units and found_units != units:
                raise ValueError(f"{path.name} {short_name} units change from {units!r} to {found_units!r}")
            if found_units:
                units = found_units
            lat_i = np.asarray(field.latitude.values, dtype=np.float64)
            lon_i = np.asarray(field.longitude.values, dtype=np.float64)
            if lat is None:
                lat, lon = lat_i, lon_i
            elif not np.allclose(lat, lat_i) or not np.allclose(lon, lon_i):
                raise ValueError(f"{path.name} {short_name} grid changes between messages")
            try:
                piece, piece_count = _accumulate(_iter_planes(field), combine)
            except ValueError as exc:
                if str(exc) != "No grids to fold":
                    raise
                raise ValueError(f"{path.name} {short_name} added no grids") from exc
            count += piece_count
            reduced = piece if reduced is None else combine(reduced, piece)
    finally:
        for dataset in datasets:
            dataset.close()
    if reduced is None or lat is None or lon is None:
        raise ValueError(f"{path.name} has no {short_name} grid")
    if not units:
        raise ValueError(f"{path.name} has no {short_name} units")
    print(f"{path.name} {short_name} folded {count} step(s), units {units}")
    return reduced, lat, lon, units, count


def _ifs_extreme(model: str, fine_name: str, tail_name: str, directory: Path, cycle: datetime, combine):
    """Fold the 3-hour extremes through 144 hours with the 6-hour extremes after that.

    combine is np.fmax for the weekly maximum and np.fmin for the weekly minimum.
    One message is decoded at a time. The result matches nanmax or nanmin of the
    concatenated stack.
    """
    fine_path = directory / f"{model}-{fine_name}.grib2"
    tail_path = directory / f"{model}-{tail_name}.grib2"
    _retrieve_steps(model, fine_name, IFS_TEMP_3H, fine_path, cycle)
    _retrieve_steps(model, tail_name, IFS_TEMP_6H, tail_path, cycle)
    fine, lat, lon, units, fine_count = _fold_stack(fine_path, fine_name, combine)
    tail, tail_lat, tail_lon, tail_units, tail_count = _fold_stack(tail_path, tail_name, combine)
    _same_grid(tail_lat, tail_lon, lat, lon, tail_name)
    if fine_count != len(IFS_TEMP_3H) or tail_count != len(IFS_TEMP_6H):
        raise RuntimeError(
            f"{model} {fine_name}/{tail_name} steps are {fine_count} and {tail_count}, "
            f"expected {len(IFS_TEMP_3H)} and {len(IFS_TEMP_6H)}"
        )
    if units != tail_units:
        raise ValueError(f"{model} {fine_name} units {units!r} differ from {tail_name} units {tail_units!r}")
    return combine(fine, tail), lat, lon, units


def _read_cycle(spec: dict, directory: Path, cycle: datetime) -> dict:
    model = spec["model"]
    instant = model == "aifs-single"
    lsm_path = directory / f"{model}-lsm.grib2"
    tp_path = directory / f"{model}-tp.grib2"
    _retrieve_steps(model, "lsm", (0,), lsm_path, cycle)
    _retrieve_steps(model, "tp", (HOURS,), tp_path, cycle)
    mask_stack, mask_lat, mask_lon, _mask_units = _read_stack(lsm_path, "lsm")
    rain_stack, rain_lat, rain_lon, rain_units = _read_stack(tp_path, "tp")
    _same_grid(rain_lat, rain_lon, mask_lat, mask_lon, "Precipitation")
    rain = liquid_inches(rain_stack[-1], rain_units)
    land = np.asarray(mask_stack[0], dtype=np.float64)
    if instant:
        sample_path = directory / f"{model}-2t.grib2"
        _retrieve_steps(model, "2t", AIFS_TEMP_STEPS, sample_path, cycle)
        stack, lat, lon, units = _read_stack(sample_path, "2t")
        _same_grid(lat, lon, mask_lat, mask_lon, "Temperature")
        if stack.shape[0] != len(AIFS_TEMP_STEPS):
            raise RuntimeError(f"{model} 2t has {stack.shape[0]} steps, expected {len(AIFS_TEMP_STEPS)}")
        tmax = to_fahrenheit(np.nanmax(stack, axis=0), units)
        tmin = to_fahrenheit(np.nanmin(stack, axis=0), units)
    else:
        max_field, max_lat, max_lon, max_units = _ifs_extreme(
            model, "mx2t3", "mx2t6", directory, cycle, np.fmax
        )
        min_field, min_lat, min_lon, min_units = _ifs_extreme(
            model, "mn2t3", "mn2t6", directory, cycle, np.fmin
        )
        _same_grid(max_lat, max_lon, mask_lat, mask_lon, "Maximum temperature")
        _same_grid(min_lat, min_lon, mask_lat, mask_lon, "Minimum temperature")
        tmax = to_fahrenheit(max_field, max_units)
        tmin = to_fahrenheit(min_field, min_units)
        lat, lon = max_lat, max_lon
    if rain.shape != land.shape or tmax.shape != land.shape or tmin.shape != land.shape:
        raise ValueError(f"{model} field shapes do not match the land mask")
    return {
        "spec": spec,
        "cycle": cycle,
        "instant": instant,
        "rain": rain,
        "tmax": tmax,
        "tmin": tmin,
        "lat": rain_lat,
        "lon": rain_lon,
        "land": land,
    }


def _download_model(spec: dict, directory: Path) -> dict:
    model = spec["model"]
    probe = "2t" if model == "aifs-single" else "tp"
    cycle = _latest_cycle(model, probe)
    errors = []
    for _attempt in range(4):
        try:
            loaded = _read_cycle(spec, directory, cycle)
            print(
                f"{spec['button']} {cycle:%Y-%m-%d %H}z rain max "
                f"{float(np.nanmax(loaded['rain'])):.2f} in., "
                f"temperature {float(np.nanmin(loaded['tmin'])):.1f} to {float(np.nanmax(loaded['tmax'])):.1f}°F"
            )
            return loaded
        except Exception as exc:
            errors.append(f"{cycle:%Y-%m-%d %H}z: {exc}")
            print(f"{model} {cycle:%Y-%m-%d %H}z failed: {exc}")
            cycle = cycle - timedelta(hours=6)
    raise RuntimeError(f"No usable {spec['button']} rainfall and temperature run ({'; '.join(errors)})")


def _source(spec: dict, cycle: datetime, product: str) -> str:
    when = _cycle_phrase(cycle)
    if product == "rain":
        return (
            f"ECMWF {spec['name']} open data total precipitation, accumulated over the 7 days "
            f"from the {when} run and shown in inches."
        )
    if spec["model"] == "aifs-single":
        extreme = "highest" if product == "max" else "lowest"
        return (
            f"ECMWF {spec['name']} open data 2 m temperature, the {extreme} value at 6-hour steps "
            f"over the 7 days from the {when} run."
        )
    kind = "maximum" if product == "max" else "minimum"
    extreme = "highest" if product == "max" else "lowest"
    return (
        f"ECMWF {spec['name']} open data {kind} 2 m temperature since the previous step, "
        f"the {extreme} value over the 7 days from the {when} run."
    )


def _view_record(
    loaded: dict,
    *,
    product: str,
    title: str,
    rank_word: str,
    values,
    colors: list[str],
    labels: list[str],
    kind: str,
    classify,
    filename: str,
    empty,
    vector_land: bool = False,
    contour: float | None = None,
    contour_sigma: float = 0.0,
) -> dict:
    spec = loaded["spec"]
    highest = rank_word == "Maximum"
    pin = domain_max(values, loaded["lat"], loaded["lon"], loaded["land"], highest=highest)
    number = float(pin["inches"])
    text = f"{number:.1f} in." if product == "rain" else format_temp(number)
    meta, field = pack_snow(
        values,
        loaded["lat"],
        loaded["lon"],
        loaded["land"],
        classify=classify,
        empty=empty,
        vector_land=vector_land,
        contour=contour,
        contour_sigma=contour_sigma,
    )
    window = _window_phrase(loaded["cycle"])
    place = "most" if highest else "lowest"
    record = {
        "key": spec["key"],
        "button": spec["button"],
        "title": title,
        "span": f"From {window}",
        "rank": f"{rank_word} {text}",
        "source": _source(spec, loaded["cycle"], product),
        "alt": (
            f"{title} from ECMWF {spec['name']} from {window}. "
            f"The {place} in this map is {text}."
        ),
        "filename": filename,
        "kind": kind,
        "smooth": True,
        "colors": list(colors),
        "over": colors[-1],
        "ticks": list(labels),
        "pin": {
            "lon": round(pin["lon"], 4),
            "lat": round(pin["lat"], 4),
            "label": text,
        },
        "field": field,
        "nlat": meta["nlat"],
        "nlon": meta["nlon"],
        "latNorth": round(meta["latNorth"], 5),
        "latSouth": round(meta["latSouth"], 5),
        "lonWest": round(meta["lonWest"], 5),
        "lonEast": round(meta["lonEast"], 5),
    }
    if contour is not None:
        record["freeze"] = meta["contour"]
    if product == "min":
        record["cardNote"] = freezing_population_note(values, loaded["lat"], loaded["lon"])
    return record


def product_views(loaded: dict[str, dict], product: str) -> dict[str, dict]:
    if product == "rain":
        return {
            key: _view_record(
                item,
                product="rain",
                title=RAIN_TITLE,
                rank_word="Maximum",
                values=item["rain"],
                colors=RAIN_COLORS,
                labels=RAIN_LABELS,
                kind="rain",
                classify=rain_bin,
                filename=f"{key}-weekly-precipitation.png",
                empty=0.0,
            )
            for key, item in loaded.items()
        }
    if product == "max":
        return {
            key: _view_record(
                item,
                product="max",
                title=MAX_TITLE,
                rank_word="Maximum",
                values=item["tmax"],
                colors=TEMP_COLORS,
                labels=TEMP_LABELS,
                kind="temp",
                classify=temp_bin,
                filename=f"{key}-weekly-maximum-temperature.png",
                empty=None,
                vector_land=True,
            )
            for key, item in loaded.items()
        }
    if product == "min":
        return {
            key: _view_record(
                item,
                product="min",
                title=MIN_TITLE,
                rank_word="Minimum",
                values=item["tmin"],
                colors=TEMP_COLORS,
                labels=TEMP_LABELS,
                kind="temp",
                classify=temp_bin,
                filename=f"{key}-weekly-minimum-temperature.png",
                empty=None,
                vector_land=True,
            )
            for key, item in loaded.items()
        }
    raise ValueError(product)


def render_forecast_page(views: dict[str, dict], path: str, title: str) -> str:
    """One forecast page with ECMWF and ECMWF-AIFS buttons. There is no anomaly view."""
    if "ecmwf" not in views or "aifs" not in views:
        raise ValueError("The forecast page needs both model views")
    shown = views["ecmwf"]
    template = (ROOT / "lib" / "snow_anomaly_page.html").read_text(encoding="utf-8")
    payload = {
        "span": shown["span"],
        "rank": shown["rank"],
        "source": shown["source"],
        "alt": shown["alt"],
        "extent": [EXTENT[0], EXTENT[1], EXTENT[2], EXTENT[3]],
        "frame": [FRAME[0], FRAME[1], FRAME[2], FRAME[3]],
        "landBounds": [round(value, 4) for value in land_bounds()],
        "nlat": shown["nlat"],
        "nlon": shown["nlon"],
        "latNorth": shown["latNorth"],
        "latSouth": shown["latSouth"],
        "lonWest": shown["lonWest"],
        "lonEast": shown["lonEast"],
        "colors": shown["colors"],
        "over": shown["over"],
        "below": "#8A5A43",
        "above": "#1A548E",
        "labels": [_label_row(item) for item in STATE_LABELS],
        # The weekly minimum is mostly the 20°F to 40°F blues. The shared
        # #4a4a4a state line has almost no contrast there. The shore uses the
        # same ink, so it stays visible with the state lines.
        **({"line": "#e7eef6"} if path == MIN_PATH else {}),
        "views": {
            "ecmwf": {key: value for key, value in views["ecmwf"].items() if key != "field"},
            "aifs": {key: value for key, value in views["aifs"].items() if key != "field"},
        },
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (
        template.replace("__TITLE__", title)
        .replace("__H2__", title)
        .replace("__SEO__", _seo(path, title))
        .replace("__NAV__", _site_nav(path))
        .replace("__VIEW_BUTTONS__", _view_buttons(views, open_forecast=True))
        .replace("__SPAN__", shown["span"])
        .replace("__RANK__", shown["rank"])
        .replace("__BASEMAP__", BASEMAP_URL)
        .replace("__FORECAST_FIELDS__", _forecast_images(views))
        .replace("__FIELD__", BLANK_PNG)
        .replace("__DATA__", data)
        .replace("__SNOW_SCALE__", snow_scale_html(hidden=False, colors=shown["colors"], labels=shown["ticks"]))
        .replace("__SCALE__", scale_html(hidden=True))
        .replace("__RANKS_HIDDEN__", " hidden")
        .replace("__RANKS__", "")
        .replace("__SOURCE__", shown["source"])
    )


def load_forecasts(work: Path) -> dict[str, dict]:
    directory = work / "grib"
    directory.mkdir(parents=True, exist_ok=True)
    loaded = [_download_model(spec, directory) for spec in MODELS]
    return {item["spec"]["key"]: item for item in loaded}


def build(work: Path) -> dict[str, Path]:
    work.mkdir(parents=True, exist_ok=True)
    loaded = load_forecasts(work)
    pages = {
        RAIN_PATH: (work / "rain.html", product_views(loaded, "rain"), RAIN_TITLE),
        MAX_PATH: (work / "temperature-maximum.html", product_views(loaded, "max"), MAX_TITLE),
        MIN_PATH: (work / "temperature-minimum.html", product_views(loaded, "min"), MIN_TITLE),
    }
    written = {}
    for path, (target, views, title) in pages.items():
        target.write_text(render_forecast_page(views, path, title), encoding="utf-8")
        print(f"Page: {target} ({target.stat().st_size:,} bytes)")
        written[path] = target
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the weekly precipitation and temperature pages")
    parser.add_argument("--work", required=True, help="Directory for downloads and the finished pages")
    args = parser.parse_args(argv)
    build(Path(args.work).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
