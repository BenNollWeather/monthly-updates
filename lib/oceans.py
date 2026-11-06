#!/usr/bin/env python3
"""Daily global ocean maps for /climate/oceans.

NASA MUR supplies sea-surface temperature and the anomaly from the 2003–2014
day-of-year average. NOAA Coral Reef Watch supplies marine-heatwave categories.
Each map is an Equal Earth oval centered on the Pacific. Land is NASA's Blue
Marble. Ice is gray, not a temperature. The nominal analysis day is the UTC
date on the file. A 09:00 UTC MUR field stays on that calendar day.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.ap_dates import ap_rewrite  # noqa: E402
from lib.c3s_globes import _seo, _site_nav  # noqa: E402

PAGE_PATH = "/climate/oceans"
TITLE = "Oceans"
USER_AGENT = "benweather-oceans/1.0 (https://benweather.com/climate/oceans)"
MUR_DATASET = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST42"
MHW_DATASET = "https://pae-paha.pacioos.hawaii.edu/erddap/griddap/mhw_5km"
# Coral Reef Watch 5 km axis. Stride must land on the last requested point.
MHW_LAT0 = -89.975
MHW_LON0 = -179.975
MHW_SPACING = 0.05
MHW_NLAT = 3600
MHW_NLON = 7200
ICE_FRACTION = 0.15
ICE_HEX = "#d9e2ea"
# Heatwave cells with no category, including ice, use this flat gray.
NODATA_HEX = "#e6e9ef"
# Displayed anomaly bar. Values outside it use the end-cap color.
ANOMALY_RANGE = (-3.0, 5.0)
SST_RANGE = (0.0, 32.0)
CENTRAL_LONGITUDE = 180
WEB_OVAL = 2400
CARD_WIDTH = 3840
CARD_MARGIN = 115
DPI = 100
INK = (23, 23, 23, 255)
MUTED = (92, 101, 110, 255)
COAST = (74, 74, 74, 255)
LOGO_PATH = ROOT / "assets" / "brand" / "bnw-brick-black.png"
MARBLE_PATH = ROOT / "assets" / "land" / "blue_marble.jpg"
# White pixels are the Antarctic continent and Greenland.
# Sea ice is black, including Antarctic pack ice, so a heatwave hole there stays gray.
POLAR_LAND_PATH = ROOT / "assets" / "land" / "polar_land.png"
# Bump when a map is republished for the same analysis day. The date query
# alone stays cached by browsers until the next UTC day.
MAP_REV = 6
# NASA SVS 5688, sampled from the -5 to +5 anomaly bar. The displayed bar is
# -3 to +5, and each temperature keeps that NASA color. Zero stays neutral.
ANOMALY_STOPS = (
    (-5.0, (0, 36, 63)),
    (-4.0, (1, 70, 122)),
    (-3.0, (1, 121, 194)),
    (-2.0, (40, 157, 219)),
    (-1.0, (140, 198, 238)),
    (0.0, (229, 226, 221)),
    (1.0, (241, 198, 145)),
    (2.0, (207, 143, 98)),
    (3.0, (175, 78, 59)),
    (4.0, (124, 42, 43)),
    (5.0, (73, 25, 27)),
)
# NASA SVS 5600. Light blue, white near 15°C, then orange and red. -5 to 35.
SST_STOPS = (
    (-5.0, (0, 35, 63)),
    (0.0, (0, 82, 142)),
    (5.0, (3, 138, 207)),
    (10.0, (116, 188, 233)),
    (15.0, (224, 224, 213)),
    (20.0, (233, 185, 133)),
    (25.0, (193, 112, 78)),
    (30.0, (139, 48, 46)),
    (35.0, (72, 25, 27)),
)
MHW_COLORS = {
    0: NODATA_HEX,
    1: "#fee090",
    2: "#fc8d59",
    3: "#e34a33",
    4: "#b30000",
    5: "#7a0177",
}
MHW_LABELS = (
    ("Moderate", "Mod."),
    ("Strong", "Strong"),
    ("Severe", "Severe"),
    ("Extreme", "Extr."),
    ("Beyond", "Beyond"),
)
LAYERS = (
    {"id": "anomaly", "label": "Sea temperature anomalies", "title": "Sea surface temperature anomalies", "web": "anomaly.png", "card": "anomaly-4k.png", "stem": "ocean-sst-anomaly"},
    {"id": "sst", "label": "Sea temperatures", "title": "Sea surface temperatures", "web": "sst.png", "card": "sst-4k.png", "stem": "ocean-sst"},
    {"id": "heatwaves", "label": "Marine heatwaves", "title": "Marine heatwaves", "web": "heatwaves.png", "card": "heatwaves-4k.png", "stem": "ocean-marine-heatwaves"},
)
_CMAPS: dict = {}


def _hex_rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def _cmap(kind: str):
    if kind not in _CMAPS:
        from matplotlib.colors import LinearSegmentedColormap

        stops = ANOMALY_STOPS if kind == "anomaly" else SST_STOPS
        vmin, vmax = stops[0][0], stops[-1][0]
        segments = [
            ((value - vmin) / (vmax - vmin), tuple(channel / 255 for channel in rgb))
            for value, rgb in stops
        ]
        _CMAPS[kind] = LinearSegmentedColormap.from_list(kind, segments)
    return _CMAPS[kind]


def _color_span(kind: str, values: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Map values onto the NASA color tables. Ends clamp, so the caps match."""
    if kind == "anomaly":
        shown = np.clip(np.where(valid, values, 0.0), ANOMALY_RANGE[0], ANOMALY_RANGE[1])
        span = (shown + 5.0) / 10.0
    else:
        # Keep the NASA color of each temperature. The bar shows 0 to 32.
        shown = np.clip(np.where(valid, values, 0.0), SST_RANGE[0], SST_RANGE[1])
        span = (shown - SST_STOPS[0][0]) / (SST_STOPS[-1][0] - SST_STOPS[0][0])
    return np.where(valid, span, 0.0)


def paint(kind: str, values: np.ndarray, ice: np.ndarray | None = None) -> np.ndarray:
    """RGBA floats. Land and unknown heatwave cells are transparent. Ice is gray."""
    values = np.asarray(values, dtype=np.float64)
    rgba = np.zeros(values.shape + (4,), dtype=np.float32)
    if kind == "heatwaves":
        table = np.zeros((6, 3), dtype=np.float32)
        for category, color in MHW_COLORS.items():
            table[category] = np.array(_hex_rgb(color), dtype=np.float32) / 255
        rounded = np.rint(values)
        valid = np.isfinite(values) & (np.abs(values - rounded) < 0.01)
        valid &= (rounded >= 0) & (rounded <= 5)
        index = np.clip(np.where(valid, rounded, 0), 0, 5).astype(np.int32)
        rgba[..., :3] = table[index]
        rgba[..., 3] = valid.astype(np.float32)
        return rgba

    valid = np.isfinite(values)
    span = _color_span(kind, values, valid)
    colored = np.asarray(_cmap(kind)(np.clip(span, 0, 1)), dtype=np.float32)
    rgba[..., :3] = colored[..., :3]
    rgba[..., 3] = valid.astype(np.float32)
    if ice is not None:
        cover = np.asarray(ice, dtype=np.float64)
        finite = cover[np.isfinite(cover)]
        if finite.size and float(finite.max()) > 1.5:
            cover = cover / 100.0
        frozen = np.isfinite(cover) & (cover >= ICE_FRACTION)
        rgba[frozen, :3] = np.array(_hex_rgb(ICE_HEX), dtype=np.float32) / 255
        rgba[frozen, 3] = 1
    return rgba


def sample_color(kind: str, value: float) -> tuple[int, int, int, int]:
    pixel = paint(kind, np.array([value]))[0]
    return tuple(int(round(float(channel) * 255)) for channel in pixel)


def ap_day(day: date) -> str:
    return ap_rewrite(f"{day:%B} {day.day}, {day.year}")


def day_from_stamp(stamp: str) -> date:
    """UTC calendar day. A 09:00Z analysis is not moved to the previous evening."""
    return datetime.strptime(stamp[:10], "%Y-%m-%d").date()


def layer_text(kind: str, day: date) -> dict[str, str]:
    when = ap_day(day)
    spec = next(item for item in LAYERS if item["id"] == kind)
    if kind == "anomaly":
        source = (
            f"NASA MUR sea surface temperature anomaly for {when}. "
            "The average is the 2003–2014 day-of-year climatology. "
            "Ice is gray."
        )
        alt = (
            f"Global sea surface temperature anomaly for {when}. "
            "Blue is cooler than the 2003–2014 average and red is warmer. Ice is gray."
        )
    elif kind == "sst":
        source = f"NASA MUR sea surface temperatures for {when}. Ice is gray."
        alt = (
            f"Global sea surface temperatures for {when}. "
            "Blue is cold and red is warm. Ice is gray."
        )
    elif kind == "heatwaves":
        source = (
            f"NOAA Coral Reef Watch marine heatwaves for {when}. "
            "Categories are moderate, strong, severe, extreme, and beyond extreme."
        )
        alt = (
            f"Global marine heatwaves for {when}. "
            "NOAA Coral Reef Watch categories run from moderate through beyond extreme."
        )
    else:
        raise KeyError(kind)
    return {
        "dek": f"{spec['title']} for {when}",
        "source": source,
        "alt": alt,
        "date": when,
        "title": spec["title"],
    }


def legend_for(kind: str) -> dict:
    if kind == "heatwaves":
        swatches = []
        count = len(MHW_LABELS)
        for index, labels in enumerate(MHW_LABELS):
            color = MHW_COLORS[index + 1]
            swatches.append(
                {"color": color, "label": labels[0], "short": labels[1], "left": index / count}
            )
        return {"kind": "swatch", "swatches": swatches, "ice": False}
    if kind == "anomaly":
        low, high = "Cooler", "Warmer"
        vmin, vmax = ANOMALY_RANGE
        marks = (-3, 0, 5)
    else:
        low, high = "Cold", "Warm"
        vmin, vmax = SST_RANGE
        marks = (0, 8, 16, 24, 32)
    ticks = []
    for value in marks:
        place = (value - vmin) / (vmax - vmin)
        ticks.append({"label": _tick_label(value, plus=kind == "anomaly"), "t": place})
    low_rgb = sample_color(kind, vmin)
    high_rgb = sample_color(kind, vmax)
    return {
        "kind": "gradient",
        "low": low,
        "high": high,
        "cap_low": "#%02x%02x%02x" % low_rgb[:3],
        "cap_high": "#%02x%02x%02x" % high_rgb[:3],
        "gradient": _gradient_css(kind),
        "ticks": ticks,
        "ice": True,
    }


def _tick_label(value: float, *, plus: bool = False) -> str:
    rounded = int(value) if float(value).is_integer() else value
    text = str(rounded).replace("-", "−")
    if plus and value > 0:
        text = f"+{text}"
    return f"{text}°C"


def _gradient_css(kind: str) -> str:
    vmin, vmax = ANOMALY_RANGE if kind == "anomaly" else SST_RANGE
    stops = []
    for step in range(17):
        place = step / 16
        red, green, blue, _alpha = sample_color(kind, vmin + place * (vmax - vmin))
        stops.append(f"rgb({red},{green},{blue}) {place * 100:.2f}%")
    return "linear-gradient(90deg, " + ", ".join(stops) + ")"


def legend_html(kind: str) -> str:
    legend = legend_for(kind)
    if legend["kind"] == "swatch":
        chips = []
        labels = []
        for item in legend["swatches"]:
            chips.append(f'<i style="background:{item["color"]}"></i>')
            labels.append(
                f'<span><span class="long">{item["label"]}</span>'
                f'<span class="short">{item["short"]}</span></span>'
            )
        return (
            '<div class="scale mhw">'
            '<div class="swatches">' + "".join(chips) + "</div>"
            '<div class="ticks">' + "".join(labels) + "</div>"
            "</div>"
        )
    ticks = []
    for item in legend["ticks"]:
        place = float(item["t"])
        style = f"left:{place * 100:.2f}%;transform:translateX(-50%)"
        ticks.append(f'<span style="{style}">{item["label"]}</span>')
    ice = '<span class="ice"><i></i>Ice</span>' if legend["ice"] else ""
    return (
        '<div class="scale">'
        '<div class="bar-row"><div class="bar-wrap">'
        f'<div class="scale-top"><span>{legend["low"]}</span><span>{legend["high"]}</span></div>'
        '<div class="meter">'
        f'<i class="cap cap-low" style="border-right-color:{legend["cap_low"]}"></i>'
        '<div class="fill-wrap">'
        f'<i class="fill" style="background:{legend["gradient"]}"></i>'
        f'<div class="ticks">{"".join(ticks)}</div>'
        "</div>"
        f'<i class="cap cap-high" style="border-left-color:{legend["cap_high"]}"></i>'
        f"</div></div>{ice}</div></div>"
    )


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attr(value: str) -> str:
    return _escape(value).replace('"', "&quot;")


def make_view(kind: str, day: date) -> dict:
    spec = next(item for item in LAYERS if item["id"] == kind)
    text = layer_text(kind, day)
    stamp = day.strftime("%Y%m%d")
    return {
        "id": kind,
        "label": spec["label"],
        "title": spec["title"],
        "dek": text["dek"],
        "source": text["source"],
        "alt": text["alt"],
        "date": text["date"],
        "src": f"{PAGE_PATH}/{spec['web']}?d={stamp}&r={MAP_REV}",
        "card": f"{PAGE_PATH}/{spec['card']}?d={stamp}&r={MAP_REV}",
        "filename": f"{spec['stem']}-{day:%Y-%m-%d}.png",
        "legend": legend_html(kind),
    }


def render_page(views: list[dict], *, width: int, height: int) -> str:
    current = next(item for item in views if item["id"] == "anomaly")
    buttons = ['<div class="model-row" id="view-row" role="tablist" aria-label="Ocean maps">']
    payload = {}
    preloads = []
    for item in views:
        selected = "true" if item["id"] == current["id"] else "false"
        buttons.append(
            f'<button type="button" role="tab" data-view="{item["id"]}" aria-selected="{selected}">'
            f'{_escape(item["label"])}</button>'
        )
        payload[item["id"]] = {
            "src": item["src"],
            "card": item["card"],
            "filename": item["filename"],
            "dek": item["dek"],
            "source": item["source"],
            "alt": item["alt"],
            "legend": item["legend"],
        }
        preloads.append(f'<link rel="preload" as="image" href="{_attr(item["src"])}">')
    buttons.append("</div>")
    template = (ROOT / "lib" / "oceans_page.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (
        template.replace("__TITLE__", TITLE)
        .replace("__SEO__", _seo(PAGE_PATH, TITLE))
        .replace("__NAV__", _site_nav(PAGE_PATH))
        .replace("__PRELOAD__", "\n  ".join(preloads))
        .replace("__BUTTONS__", "".join(buttons))
        .replace("__DEK__", _escape(current["dek"]))
        .replace("__LEGEND__", current["legend"])
        .replace("__DOWNLOAD_HREF__", _attr(current["card"]))
        .replace("__DOWNLOAD_NAME__", _attr(current["filename"]))
        .replace("__IMAGE__", _attr(current["src"]))
        .replace("__ALT__", _attr(current["alt"]))
        .replace("__WIDTH__", str(width))
        .replace("__HEIGHT__", str(height))
        .replace("__SOURCE__", _escape(current["source"]))
        .replace("__VIEWS__", data)
    )


def parse_latest_time(text: str) -> str:
    for line in reversed(text.splitlines()):
        token = line.strip().split(",")[-1].strip().strip('"')
        if len(token) >= 20 and token[4] == "-" and "T" in token[:20]:
            return token
    raise ValueError("The time index did not include a timestamp")


def mur_url(stamp: str) -> str:
    slot = f"[({stamp})]"
    names = ("analysed_sst", "sst_anomaly", "sea_ice_fraction")
    query = ",".join(f"{name}{slot}[][]" for name in names)
    return f"{MUR_DATASET}.nc?{query}"


def _axis_stop(start: float, count: int, stride: int) -> float:
    last = count - 1
    index = last - (last % stride)
    return round(start + index * MHW_SPACING, 3)


def mhw_url(stamp: str, stride: int) -> str:
    lat_stop = _axis_stop(MHW_LAT0, MHW_NLAT, stride)
    lon_stop = _axis_stop(MHW_LON0, MHW_NLON, stride)
    return (
        f"{MHW_DATASET}.nc?heatwave_category[({stamp})]"
        f"[({MHW_LAT0}):{stride}:({lat_stop})]"
        f"[({MHW_LON0}):{stride}:({lon_stop})]"
    )


def _prefer_ipv4() -> None:
    """Use an IPv4 address when the host has one. An IPv6 route can sit in SYN_SENT."""
    if getattr(socket.getaddrinfo, "_oceans_ipv4", False):
        return
    original = socket.getaddrinfo

    def getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        infos = original(host, port, family, type, proto, flags)
        return sorted(infos, key=lambda item: item[0] != socket.AF_INET)

    getaddrinfo._oceans_ipv4 = True
    socket.getaddrinfo = getaddrinfo


def _fetch(url: str, dest: Path | None = None) -> bytes:
    _prefer_ipv4()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = response.read()
            if dest is not None:
                dest.write_bytes(payload)
            return payload
        except urllib.error.HTTPError as exc:
            detail = exc.read(500).decode("utf-8", "replace").replace("\n", " ")
            last_error = RuntimeError(f"HTTP {exc.code}: {detail[:280]}")
            print(f"fetch failed ({attempt + 1}/3) {url[:140]} {last_error}", flush=True)
        except Exception as exc:
            last_error = exc
            print(f"fetch failed ({attempt + 1}/3) {url[:140]} {exc}", flush=True)
    raise RuntimeError(f"Could not download {url[:180]}: {last_error}")


def latest_time(dataset: str) -> str:
    payload = _fetch(f"{dataset}.csv?time[(last)]")
    return parse_latest_time(payload.decode("utf-8", errors="replace"))


def _coords(dataset):
    if "time" in dataset.dims and dataset.sizes.get("time") == 1:
        dataset = dataset.isel(time=0, drop=True)
    lat_name = "latitude" if "latitude" in dataset.dims or "latitude" in dataset.coords else "lat"
    lon_name = "longitude" if "longitude" in dataset.dims or "longitude" in dataset.coords else "lon"
    dataset = dataset.sortby(lat_name).sortby(lon_name)
    latitude = np.asarray(dataset[lat_name].values, dtype=np.float64)
    longitude = np.asarray(dataset[lon_name].values, dtype=np.float64)
    return dataset, latitude, longitude


def _values(dataset, name: str) -> np.ndarray:
    field = np.asarray(dataset[name].values, dtype=np.float64)
    if field.ndim == 3:
        field = field[0]
    return field


def _signed_longitude(longitude: np.ndarray, fields: tuple[np.ndarray, ...]) -> tuple[np.ndarray, tuple[np.ndarray, ...]]:
    """Shift a 0–360 axis onto −180–180 and keep every field on that axis."""
    if float(np.nanmin(longitude)) < 0 or float(np.nanmax(longitude)) <= 180:
        return longitude, fields
    shifted = ((longitude + 180.0) % 360.0) - 180.0
    order = np.argsort(shifted)
    return shifted[order], tuple(field[:, order] for field in fields)


def read_mur(path: Path) -> dict:
    import xarray as xr

    with xr.open_dataset(path, mask_and_scale=True) as dataset:
        frame, latitude, longitude = _coords(dataset)
        sst = _values(frame, "analysed_sst")
        anomaly = _values(frame, "sst_anomaly")
        ice = _values(frame, "sea_ice_fraction")
    longitude, (sst, anomaly, ice) = _signed_longitude(longitude, (sst, anomaly, ice))
    land = ~np.isfinite(sst) | (sst < -5) | (sst > 45)
    anomaly = np.where(land, np.nan, anomaly)
    sst = np.where(land, np.nan, sst)
    print(
        f"MUR grid {latitude.size} x {longitude.size} "
        f"lat {latitude[0]:.3f}..{latitude[-1]:.3f} lon {longitude[0]:.3f}..{longitude[-1]:.3f}",
        flush=True,
    )
    return {"lat": latitude, "lon": longitude, "sst": sst, "anomaly": anomaly, "ice": ice}


def read_mhw(path: Path) -> dict:
    import xarray as xr

    with xr.open_dataset(path, mask_and_scale=True) as dataset:
        frame, latitude, longitude = _coords(dataset)
        category = _values(frame, "heatwave_category")
    longitude, (category,) = _signed_longitude(longitude, (category,))
    print(
        f"MHW grid {latitude.size} x {longitude.size} "
        f"lat {latitude[0]:.3f}..{latitude[-1]:.3f} lon {longitude[0]:.3f}..{longitude[-1]:.3f}",
        flush=True,
    )
    if latitude.size < 100 or longitude.size < 200:
        raise ValueError(f"Marine heatwave grid is too coarse ({latitude.size} x {longitude.size})")
    return {"lat": latitude, "lon": longitude, "category": category}


def _projection():
    import cartopy.crs as ccrs

    return ccrs.EqualEarth(central_longitude=CENTRAL_LONGITUDE)


def _pad(oval_w: int) -> int:
    inch = oval_w / 13.8
    reach = (8 / 72) * inch + 0.04 * inch
    return max(8, int(math.ceil(reach + 6)))


def _oval_for_raster(raster_w: int) -> int:
    oval = raster_w
    for _ in range(4):
        oval = raster_w - 2 * _pad(max(oval, 32))
    return max(oval, 32)


@dataclass
class Frame:
    ocean_shape: tuple[int, int]
    origin: tuple[int, int]
    lons: np.ndarray
    lats: np.ndarray
    inside: np.ndarray
    mask: Image.Image
    coast: Image.Image
    oval_box: tuple[int, int, int, int]


def _line_width(oval_w: int) -> float:
    pixels = 2.15 * (oval_w / WEB_OVAL)
    return pixels * 72.0 / DPI


def _coast_canvas(oval_w: int, *, coasts: bool):
    os.environ.setdefault("MPLBACKEND", "Agg")
    import matplotlib

    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    proj = _projection()
    x0, x1 = (float(proj.x_limits[0]), float(proj.x_limits[1]))
    y0, y1 = (float(proj.y_limits[0]), float(proj.y_limits[1]))
    aspect = (x1 - x0) / (y1 - y0)
    map_h = max(2, int(round(oval_w / aspect)))
    pad = _pad(oval_w)
    fig_w = oval_w + 2 * pad
    fig_h = map_h + 2 * pad
    figure = plt.figure(figsize=(fig_w / DPI, fig_h / DPI), dpi=DPI)
    figure.patch.set_alpha(0)
    axes = figure.add_axes(
        [pad / fig_w, pad / fig_h, oval_w / fig_w, map_h / fig_h],
        projection=proj,
    )
    axes.set_global()
    axes.patch.set_alpha(0)
    axes.spines["geo"].set_visible(False)
    if coasts:
        axes.coastlines(resolution="50m", color="#4a4a4a", linewidth=_line_width(oval_w) * 0.85)
    figure.canvas.draw()
    canvas = np.asarray(figure.canvas.buffer_rgba()).copy()
    extent = axes.get_window_extent()
    height, width = canvas.shape[:2]
    plt.close(figure)
    left = int(round(extent.x0))
    right = int(round(extent.x1))
    top = int(round(height - extent.y1))
    bottom = int(round(height - extent.y0))
    box = (left, top, max(1, right - left), max(1, bottom - top))
    return canvas, box, (x0, x1, y0, y1), proj


def _sample_indices(lon: np.ndarray, lat: np.ndarray, lons: np.ndarray, lats: np.ndarray):
    dlon = float(lon[1] - lon[0])
    dlat = float(lat[1] - lat[0])
    wraps = abs((lon[-1] + dlon) - (lon[0] + 360.0)) < abs(dlon) * 0.25
    fx = (lons - float(lon[0])) / dlon
    if wraps:
        fx = np.mod(fx, lon.size)
    else:
        fx = np.clip(fx, 0, lon.size - 1)
    if lat.size == 1:
        fy = np.zeros_like(lats)
    else:
        fy = np.clip((lats - float(lat[0])) / dlat, 0, lat.size - 1.000001)
    return fx, fy, wraps


def _resample(rgba: np.ndarray, lon: np.ndarray, lat: np.ndarray, lons: np.ndarray, lats: np.ndarray, inside: np.ndarray) -> np.ndarray:
    fx, fy, wraps = _sample_indices(lon, lat, lons, lats)
    nlon = lon.size
    nlat = lat.size
    x0 = np.floor(fx).astype(np.int32)
    y0 = np.floor(fy).astype(np.int32)
    wx = (fx - x0).astype(np.float32)
    wy = (fy - y0).astype(np.float32)
    if wraps:
        x0 = np.mod(x0, nlon)
        x1 = np.mod(x0 + 1, nlon)
    else:
        x0 = np.clip(x0, 0, nlon - 1)
        x1 = np.clip(x0 + 1, 0, nlon - 1)
    y0 = np.clip(y0, 0, nlat - 1)
    y1 = np.clip(y0 + 1, 0, nlat - 1)
    c00 = rgba[y0, x0]
    c10 = rgba[y0, x1]
    c01 = rgba[y1, x0]
    c11 = rgba[y1, x1]
    a00 = c00[..., 3] > 0.5
    a10 = c10[..., 3] > 0.5
    a01 = c01[..., 3] > 0.5
    a11 = c11[..., 3] > 0.5
    w00 = (1 - wx) * (1 - wy) * a00
    w10 = wx * (1 - wy) * a10
    w01 = (1 - wx) * wy * a01
    w11 = wx * wy * a11
    weight = w00 + w10 + w01 + w11
    rgb = (
        c00[..., :3] * w00[..., None]
        + c10[..., :3] * w10[..., None]
        + c01[..., :3] * w01[..., None]
        + c11[..., :3] * w11[..., None]
    )
    rgb = rgb / np.maximum(weight, 1e-6)[..., None]
    nearest_x = np.mod(np.rint(fx).astype(np.int32), nlon) if wraps else np.clip(np.rint(fx).astype(np.int32), 0, nlon - 1)
    nearest_y = np.clip(np.rint(fy).astype(np.int32), 0, nlat - 1)
    ocean = inside & (rgba[nearest_y, nearest_x, 3] > 0.5) & (weight > 0)
    out = np.zeros(lons.shape + (4,), dtype=np.float32)
    out[ocean, :3] = rgb[ocean]
    out[ocean, 3] = 1
    return out


def _oval_mask(proj, box: tuple[int, int, int, int], limits, size: tuple[int, int]):
    from matplotlib.path import Path as MplPath

    left, top, width, height = box
    x0, x1, y0, y1 = limits
    ring = np.asarray(proj.boundary.coords)[:, :2]
    scale = 4
    big = Image.new("L", (size[0] * scale, size[1] * scale), 0)
    draw = ImageDraw.Draw(big)
    polygon = []
    for x_value, y_value in ring:
        column = left + (x_value - x0) / (x1 - x0) * width
        row = top + (y1 - y_value) / (y1 - y0) * height
        polygon.append((column * scale, row * scale))
    draw.polygon(polygon, fill=255)
    mask = big.resize(size, Image.Resampling.BOX)
    # Keep the hard test on the same ring. Inverse projection outside the oval
    # is clamped to the pole, so those pixels must not be sampled.
    codes = np.full(len(ring), MplPath.LINETO, dtype=np.uint8)
    codes[0] = MplPath.MOVETO
    codes[-1] = MplPath.CLOSEPOLY
    return mask, MplPath(ring, codes)


def prepare(oval_w: int, *, coasts: bool) -> Frame:
    import cartopy.crs as ccrs

    canvas, box, limits, proj = _coast_canvas(oval_w, coasts=coasts)
    height, width = canvas.shape[:2]
    mask, path = _oval_mask(proj, box, limits, (width, height))
    left, top, box_w, box_h = box
    columns = np.arange(box_w, dtype=np.float64) + 0.5
    rows = np.arange(box_h, dtype=np.float64) + 0.5
    x0, x1, y0, y1 = limits
    x_values = x0 + columns / box_w * (x1 - x0)
    y_values = y1 - rows / box_h * (y1 - y0)
    xx, yy = np.meshgrid(x_values, y_values)
    inside = path.contains_points(np.column_stack((xx.ravel(), yy.ravel())), radius=0.0).reshape(xx.shape)
    plate = ccrs.PlateCarree()
    transformed = plate.transform_points(proj, xx[inside], yy[inside])
    lons = np.full(xx.shape, np.nan, dtype=np.float64)
    lats = np.full(xx.shape, np.nan, dtype=np.float64)
    lons[inside] = transformed[:, 0]
    lats[inside] = transformed[:, 1]
    # Points outside the oval are left out of the inverse projection. Cartopy
    # clamps those to the pole, which would paint the corners as arctic water.
    lons = np.where(inside, ((lons + 180.0) % 360.0) - 180.0, 0.0)
    lats = np.where(inside, lats, 0.0)
    mask_array = np.asarray(mask)
    mask_array = np.where(mask_array > 8, mask_array, 0).astype(np.uint8)
    mask = Image.fromarray(mask_array, "L")
    oval_box = mask.point(lambda value: 255 if value > 128 else 0).getbbox() or (0, 0, width, height)
    coast = Image.fromarray(canvas, "RGBA")
    return Frame((box_h, box_w), (left, top), lons, lats, inside, mask, coast, oval_box)


_MARBLE: np.ndarray | None = None


def _marble() -> np.ndarray:
    global _MARBLE
    if _MARBLE is None:
        image = Image.open(MARBLE_PATH).convert("RGB")
        _MARBLE = np.asarray(image)
    return _MARBLE


def _sample_marble(lons: np.ndarray, lats: np.ndarray, need: np.ndarray) -> np.ndarray:
    """Equirectangular Blue Marble, north up, longitude -180 to 180."""
    marble = _marble()
    height, width = marble.shape[:2]
    out = np.zeros(lons.shape + (3,), dtype=np.float32)
    if not np.any(need):
        return out
    cols = np.mod((lons[need] + 180.0) / 360.0 * width, width)
    rows = np.clip((90.0 - lats[need]) / 180.0 * height, 0, height - 1.000001)
    x0 = np.floor(cols).astype(np.int32)
    y0 = np.floor(rows).astype(np.int32)
    wx = (cols - x0).astype(np.float32)
    wy = (rows - y0).astype(np.float32)
    x1 = (x0 + 1) % width
    y1 = np.clip(y0 + 1, 0, height - 1)
    c00 = marble[y0, x0].astype(np.float32)
    c10 = marble[y0, x1].astype(np.float32)
    c01 = marble[y1, x0].astype(np.float32)
    c11 = marble[y1, x1].astype(np.float32)
    rgb = (
        c00 * ((1 - wx) * (1 - wy))[:, None]
        + c10 * (wx * (1 - wy))[:, None]
        + c01 * ((1 - wx) * wy)[:, None]
        + c11 * (wx * wy)[:, None]
    )
    out[need] = rgb / 255.0
    return out


_POLAR: np.ndarray | None = None


def _polar_land() -> np.ndarray:
    global _POLAR
    if _POLAR is None:
        image = Image.open(POLAR_LAND_PATH).convert("L")
        _POLAR = np.asarray(image) > 127
    return _POLAR


def _sample_polar_land(lons: np.ndarray, lats: np.ndarray, need: np.ndarray) -> np.ndarray:
    """Nearest pixel of the Antarctica and Greenland mask. Same grid as Blue Marble."""
    mask = _polar_land()
    height, width = mask.shape
    out = np.zeros(lons.shape, dtype=bool)
    if not np.any(need):
        return out
    cols = np.mod((lons[need] + 180.0) / 360.0 * width, width).astype(np.int32)
    rows = np.clip((90.0 - lats[need]) / 180.0 * height, 0, height - 1).astype(np.int32)
    cols = np.clip(cols, 0, width - 1)
    out[need] = mask[rows, cols]
    return out


def land_cells(sst: np.ndarray, ice: np.ndarray) -> np.ndarray:
    """True on land. Sea ice stays out of this mask so it is not drawn as land."""
    cover = np.asarray(ice, dtype=np.float64)
    finite = cover[np.isfinite(cover)]
    if finite.size and float(finite.max()) > 1.5:
        cover = cover / 100.0
    frozen = np.isfinite(cover) & (cover >= ICE_FRACTION)
    water = np.asarray(sst, dtype=np.float64)
    missing = ~np.isfinite(water) | (water < -5) | (water > 45)
    return missing & ~frozen


def _resample_flag(flag: np.ndarray, lon: np.ndarray, lat: np.ndarray, frame: Frame) -> np.ndarray:
    rgba = np.zeros(flag.shape + (4,), dtype=np.float32)
    rgba[np.asarray(flag, dtype=bool), 3] = 1
    sampled = _resample(rgba, lon, lat, frame.lons, frame.lats, frame.inside)
    return sampled[..., 3] > 0.5


def project(
    frame: Frame,
    rgba: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    *,
    land: np.ndarray | None = None,
    hole: str | None = None,
) -> Image.Image:
    """Paint Blue Marble on land. `hole` fills the remaining empty ocean, such as missing heatwave data.

    Heatwave holes on the Antarctic continent and on Greenland use Blue Marble.
    Sea ice on that map stays the flat gray, including Antarctic pack ice.
    """
    left, top = frame.origin
    sampled = _resample(rgba, lon, lat, frame.lons, frame.lats, frame.inside)
    gap = frame.inside & (sampled[..., 3] < 0.5)
    if land is None:
        on_land = gap
        empty = np.zeros(gap.shape, dtype=bool)
    else:
        on_land = gap & land
        empty = gap & ~land
    if np.any(on_land):
        marble = _sample_marble(frame.lons, frame.lats, on_land)
        sampled[on_land, :3] = marble[on_land]
        sampled[on_land, 3] = 1
    if hole is not None and np.any(empty):
        sampled[empty, :3] = np.array(_hex_rgb(hole), dtype=np.float32) / 255
        sampled[empty, 3] = 1
        polar = empty & _sample_polar_land(frame.lons, frame.lats, empty)
        if np.any(polar):
            marble = _sample_marble(frame.lons, frame.lats, polar)
            sampled[polar, :3] = marble[polar]
            sampled[polar, 3] = 1
    height, width = frame.coast.size[1], frame.coast.size[0]
    canvas = np.zeros((height, width, 4), dtype=np.float32)
    canvas[top : top + sampled.shape[0], left : left + sampled.shape[1]] = sampled
    mask = np.asarray(frame.mask, dtype=np.float32) / 255.0
    canvas[..., 3] *= mask
    image = Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA")
    shadowed = _outer_shadow(image, frame.mask)
    return Image.alpha_composite(shadowed, frame.coast)


def _outer_shadow(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Southeast shadow of the oval only. The interior, including land, stays clear."""
    hard = mask.point(lambda value: 255 if value > 200 else 0)
    bbox = hard.getbbox()
    if bbox is None:
        return image
    oval_w = max(1, bbox[2] - bbox[0])
    inch = oval_w / 13.8
    shift_x = int(round(0.025 * inch))
    shift_y = int(round(0.04 * inch))
    shadow = Image.new("L", mask.size, 0)
    for alpha, points in zip((0.07, 0.045, 0.03, 0.02, 0.012), (0, 2, 4, 6, 8)):
        layer = mask
        radius = points / 72.0 * inch
        if radius > 0:
            layer = mask.filter(ImageFilter.GaussianBlur(radius=radius))
        shifted = Image.new("L", mask.size, 0)
        shifted.paste(layer, (shift_x, shift_y))
        shadow = ImageChops.add(shadow, shifted.point(lambda value, scale=alpha: int(value * scale)))
    shadow = ImageChops.subtract(shadow, hard)
    plate = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    plate.putalpha(shadow)
    return Image.alpha_composite(plate, image)


def render_map(lon: np.ndarray, lat: np.ndarray, rgba: np.ndarray, *, width: int, coasts: bool = True) -> Image.Image:
    frame = prepare(width, coasts=coasts)
    return project(frame, rgba, lon, lat)


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    name = {
        "regular": "LibreFranklin-Regular.ttf",
        "semibold": "LibreFranklin-SemiBold.ttf",
        "bold": "LibreFranklin-Bold.ttf",
    }[weight]
    return ImageFont.truetype(str(ROOT / "assets" / "fonts" / name), size)


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = word if not current else f"{current} {word}"
        if font.getlength(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def _legend_bar_width(legend: dict, tick_font: ImageFont.FreeTypeFont, limit: int) -> int:
    """Wide enough that neighboring labels stay apart, and no wider than the card."""
    labels = [item["label"] for item in legend["ticks"]] if legend["kind"] == "gradient" else [
        item["label"] for item in legend["swatches"]
    ]
    widths = [tick_font.getlength(label) for label in labels]
    gap = tick_font.size * 0.55
    if legend["kind"] == "swatch":
        return min(limit, int(math.ceil(max(widths) * len(widths) + gap * (len(widths) - 1))))
    bar = 720
    places = [float(item["t"]) for item in legend["ticks"]]
    for _ in range(8):
        crowded = False
        for index in range(len(labels) - 1):
            right = bar * places[index] + widths[index] / 2
            left = bar * places[index + 1] - widths[index + 1] / 2
            if left < right + gap:
                crowded = True
                break
        if not crowded or bar >= limit:
            break
        bar = min(limit, int(bar * 1.2) + 40)
    return bar


def render_card(ocean: Image.Image, kind: str, day: date) -> Image.Image:
    text = layer_text(kind, day)
    legend = legend_for(kind)
    pad = CARD_MARGIN
    title_font = _font("bold", 110)
    date_font = _font("semibold", 60)
    edge_font = _font("semibold", 48)
    tick_font = _font("bold", 48)
    source_font = _font("regular", 41)
    content_w = CARD_WIDTH - 2 * pad
    title_h = _line_height(title_font)
    date_h = _line_height(date_font)
    bar_h = 36
    tick_h = _line_height(tick_font)
    edge_h = _line_height(edge_font) if legend["kind"] == "gradient" else 0
    legend_h = (edge_h + 16 if edge_h else 0) + bar_h + 14 + tick_h + 8
    map_top = pad + title_h + 22 + date_h + 34 + legend_h + 20
    map_h = ocean.height
    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo_h = 115
    logo_w = int(round(logo_h * logo.width / logo.height))
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    logo.putalpha(logo.getchannel("A").point(lambda value: int(value * 0.72)))
    source_h = 58
    source_lines = _wrap(text["source"], source_font, content_w - logo_w - 48)
    source_top = map_top + map_h + 44
    source_block = max(len(source_lines) * source_h, logo_h)
    height = source_top + source_block + pad
    card = Image.new("RGB", (CARD_WIDTH, height), "white")
    plate = Image.new("RGBA", ocean.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(plate, ocean.convert("RGBA")).convert("RGB")
    card.paste(flat, (pad, map_top))
    draw = ImageDraw.Draw(card)
    draw.text((pad, pad), text["title"], font=title_font, fill=INK)
    draw.text((pad, pad + title_h + 22), text["date"], font=date_font, fill=MUTED)
    bar_w = _legend_bar_width(legend, tick_font, content_w - 280)
    _draw_legend(draw, card, legend, kind, pad, pad + title_h + 22 + date_h + 34, bar_w, bar_h, edge_font, tick_font)
    for index, line in enumerate(source_lines):
        draw.text((pad, source_top + index * source_h), line, font=source_font, fill=MUTED)
    card.paste(logo, (CARD_WIDTH - pad - logo_w, source_top + max(0, (source_block - logo_h) // 2)), logo)
    return card


def _draw_legend(draw, card, legend, kind: str, x: int, y: int, bar_w: int, bar_h: int, edge_font, tick_font) -> None:
    if legend["kind"] == "gradient":
        arrow = max(16, int(round(bar_h * 0.72)))
        draw.text((x, y), legend["low"], font=edge_font, fill=INK)
        high_w = edge_font.getlength(legend["high"])
        draw.text((x + bar_w + 2 * arrow - high_w, y), legend["high"], font=edge_font, fill=INK)
        bar_top = y + _line_height(edge_font) + 16
        colors = _gradient_row(kind, bar_w)
        bar = Image.fromarray(np.repeat(colors[None, :, :], bar_h, axis=0), "RGB")
        card.paste(bar, (x + arrow, bar_top))
        low = _hex_rgb(legend["cap_low"])
        high = _hex_rgb(legend["cap_high"])
        mid = bar_top + bar_h / 2
        draw.polygon([(x + arrow, bar_top), (x, mid), (x + arrow, bar_top + bar_h)], fill=low)
        right = x + arrow + bar_w
        draw.polygon([(right, bar_top), (right + arrow, mid), (right, bar_top + bar_h)], fill=high)
        chip = bar_h
        chip_x = right + arrow + 28
        draw.rounded_rectangle((chip_x, bar_top, chip_x + chip, bar_top + bar_h), radius=6, fill=_hex_rgb(ICE_HEX), outline=(180, 188, 196))
        draw.text((chip_x + chip + 16, bar_top + (bar_h - tick_font.size) / 2), "Ice", font=tick_font, fill=MUTED)
        tick_y = bar_top + bar_h + 14
        for item in legend["ticks"]:
            label = item["label"]
            place = float(item["t"])
            label_w = tick_font.getlength(label)
            left = x + arrow + bar_w * place - label_w / 2
            draw.text((left, tick_y), label, font=tick_font, fill=MUTED)
        return
    count = len(legend["swatches"])
    swatch_w = bar_w / count
    for index, item in enumerate(legend["swatches"]):
        left = int(round(x + index * swatch_w))
        right = int(round(x + (index + 1) * swatch_w))
        draw.rectangle((left, y, right, y + bar_h), fill=_hex_rgb(item["color"]))
        label_w = tick_font.getlength(item["label"])
        draw.text((left + (swatch_w - label_w) / 2, y + bar_h + 14), item["label"], font=tick_font, fill=MUTED)


def _gradient_row(kind: str, width: int) -> np.ndarray:
    vmin, vmax = ANOMALY_RANGE if kind == "anomaly" else SST_RANGE
    values = np.linspace(vmin, vmax, width)
    rgba = paint(kind, values)
    return (np.clip(rgba[:, :3], 0, 1) * 255).astype(np.uint8)


def _save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", compress_level=6)


def build(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    mur_stamp = latest_time(MUR_DATASET)
    mhw_stamp = latest_time(MHW_DATASET)
    print(f"MUR {mur_stamp}", flush=True)
    print(f"MHW {mhw_stamp}", flush=True)
    mur_path = work / "mur.nc"
    _fetch(mur_url(mur_stamp), mur_path)
    mur = read_mur(mur_path)
    heat = None
    last_error: Exception | None = None
    for stride in (5, 10, 8, 4):
        try:
            path = work / f"mhw-s{stride}.nc"
            _fetch(mhw_url(mhw_stamp, stride), path)
            heat = read_mhw(path)
            print(f"MHW stride {stride}", flush=True)
            break
        except Exception as exc:
            last_error = exc
            print(f"MHW stride {stride} failed: {exc}", flush=True)
    if heat is None:
        raise SystemExit(f"Marine heatwave grid failed: {last_error}")
    mur_day = day_from_stamp(mur_stamp)
    mhw_day = day_from_stamp(mhw_stamp)
    fields = {
        "anomaly": (paint("anomaly", mur["anomaly"], mur["ice"]), mur["lon"], mur["lat"], mur_day),
        "sst": (paint("sst", mur["sst"], mur["ice"]), mur["lon"], mur["lat"], mur_day),
        "heatwaves": (paint("heatwaves", heat["category"]), heat["lon"], heat["lat"], mhw_day),
    }
    web = prepare(WEB_OVAL, coasts=False)
    card_oval = _oval_for_raster(CARD_WIDTH - 2 * CARD_MARGIN)
    card = prepare(card_oval, coasts=False)
    land = land_cells(mur["sst"], mur["ice"])
    web_land = _resample_flag(land, mur["lon"], mur["lat"], web)
    card_land = _resample_flag(land, mur["lon"], mur["lat"], card)
    views = []
    for spec in LAYERS:
        rgba, lon, lat, day = fields[spec["id"]]
        hole = NODATA_HEX if spec["id"] == "heatwaves" else None
        page_map = project(web, rgba, lon, lat, land=web_land, hole=hole)
        _save(page_map, work / spec["web"])
        card_map = project(card, rgba, lon, lat, land=card_land, hole=hole)
        _save(render_card(card_map, spec["id"], day), work / spec["card"])
        views.append(make_view(spec["id"], day))
        print(f"rendered {spec['id']} {day.isoformat()}", flush=True)
    html = render_page(views, width=web.coast.size[0], height=web.coast.size[1])
    (work / "index.html").write_text(html, encoding="utf-8")
    print(f"page written {work / 'index.html'}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Oceans page.")
    parser.add_argument("--work", default="", help="Directory for the download and the page.")
    args = parser.parse_args(argv)
    work = Path(args.work or os.environ.get("WORK_ROOT") or "/tmp/monthly-updates/oceans").expanduser()
    build(work)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
