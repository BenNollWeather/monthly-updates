#!/usr/bin/env python3
"""Season-to-date snowfall percentage of average for benweather.com/weather/snow-anomaly.

NOHRSC publishes one CONUS file per day, valid at 12 UTC, from Sept. 30.
Completed seasons from 2008 through the year before the current one are the
average. A day with more than a few missing seasons is skipped for the latest
day that still has the current file and enough history.

The page draws the map on a canvas. Brown is below average, blue is above,
and places whose average season-to-date snow is under an inch stay uncolored
so a trace does not become a huge percent.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.ap_dates import _ABBR  # noqa: E402
from lib.c3s_globes import _seo, _site_nav  # noqa: E402

SEASON_START = (9, 30)
VALID_HOUR = 12
CLIMATOLOGY_FIRST_YEAR = 2008
MAX_MISSING_YEARS = 3
LOOKBACK_DAYS = 45
MIN_CLIM_INCHES = 1.0
# 100% opens the first blue band, so a cell at 100% is above average.
ABOVE_PERCENT = 100.0
METERS_TO_INCHES = 39.3701
PAGE_PATH = "/weather/snow-anomaly"
FORECAST_PATH = "/weather/snow-forecast"
TITLE = "Snowfall percentage of average"
FORECAST_TITLE = "Weekly snowfall forecast"
BASEMAP_URL = "/climate_imagery/snow_basemap.js?v=4"
_LAND_BOUNDS = None
SCALE_MAX = 300
SCALE_STEP = 25

# west, east, south, north. Lower 48, with the Great Lakes inside the frame.
# The county image and the packed grids use this extent.
EXTENT = (-125.6, -66.5, 24.0, 49.8)
# The canvas is wider than EXTENT, and it stays inside the terrain JPEG, so the
# drop shadow can fade on every side of the country before it meets the map edge.
FRAME = (-126.55, -65.38, 23.05, 50.92)

# Twelve flat bands. A breakpoint belongs to the band above it, so 100% is the
# first blue and the legend tick sits on that edge. 300% and above uses OVER.
COLORS = [
    "#A56B4A",
    "#C48A55",
    "#E0B56A",
    "#F3E6C4",
    "#D4E8F4",
    "#A9D0EA",
    "#6AADD8",
    "#3B8CC4",
    "#246EAB",
    "#1A548E",
    "#163E74",
    "#122E5C",
]
OVER = "#0C2248"
BELOW_LABEL = "#8A5A43"
ABOVE_LABEL = "#1A548E"

LAKE_NAMES = {
    "Lake Superior",
    "Lake Michigan",
    "Lake Huron",
    "Lake Erie",
    "Lake Ontario",
    "Georgian Bay",
    "Lake Saint Clair",
}
HEADERS = {"User-Agent": "benweather-snow-anomaly/1.0 (https://benweather.com/weather/snow-anomaly)"}

# Uppercase AP abbreviations. The first point sits inside the state, off the
# border. A small state may add a second point; the page draws a leader when
# the name would cover the state. Michigan stays on the lower peninsula.
STATE_LABELS = (
    ("WASH.", -120.5, 47.4, False),
    ("ORE.", -120.6, 44.0, False),
    ("CALIF.", -119.7, 37.2, False),
    ("IDAHO", -114.5, 44.4, False),
    ("NEV.", -117.0, 39.3, False),
    ("UTAH", -111.6, 39.3, False),
    ("ARIZ.", -111.6, 34.3, False),
    ("MONT.", -109.6, 47.0, False),
    ("WYO.", -107.6, 43.0, False),
    ("COLO.", -105.6, 39.0, False),
    ("N.M.", -106.1, 34.4, False),
    ("N.D.", -100.5, 47.4, False),
    ("S.D.", -100.3, 44.4, False),
    ("NEB.", -99.8, 41.5, False),
    ("KAN.", -98.3, 38.5, False),
    ("OKLA.", -97.5, 35.5, False),
    ("TEXAS", -99.4, 31.4, False),
    ("MINN.", -94.3, 46.3, False),
    ("IOWA", -93.5, 42.0, False),
    ("MO.", -92.5, 38.4, False),
    ("ARK.", -92.4, 34.9, False),
    ("LA.", -92.55, 31.3, False),
    ("WIS.", -89.8, 44.6, False),
    ("ILL.", -89.2, 40.1, False),
    ("MISS.", -89.7, 32.7, False),
    ("MICH.", -84.9, 43.05, True),
    ("IND.", -86.3, 39.9, False),
    ("KY.", -85.3, 37.5, False),
    ("TENN.", -86.3, 35.8, False),
    ("ALA.", -86.8, 32.7, False),
    ("OHIO", -82.7, 40.3, False),
    ("GA.", -83.4, 32.6, False),
    ("FLA.", -81.6, 28.1, False),
    ("PA.", -77.6, 40.9, False),
    ("N.Y.", -75.5, 43.0, False),
    ("N.C.", -79.4, 35.5, False),
    ("S.C.", -80.9, 33.8, False),
    ("VA.", -78.5, 37.5, False),
    ("W.VA.", -80.9, 38.5, True),
    ("MD.", -76.97, 39.35, True, -75.05, 37.35),
    ("DEL.", -75.45, 38.71, True, -74.15, 38.5),
    ("N.J.", -74.55, 40.2, True, -72.95, 39.2),
    ("CONN.", -72.7, 41.6, True, -71.25, 40.45),
    ("R.I.", -71.6, 41.81, True, -69.35, 40.75),
    ("MASS.", -71.85, 42.25, True, -68.6, 41.85),
    ("VT.", -72.68, 44.29, True, -73.05, 45.35),
    ("N.H.", -71.55, 43.7, True, -68.6, 43.05),
    ("MAINE", -69.2, 45.4, False),
)


@dataclass(frozen=True)
class ChosenDay:
    target: date
    current_year: int
    climatology_years: tuple[int, ...]
    missing_years: tuple[int, ...]

    @property
    def season_start(self) -> date:
        start_year = self.target.year if (self.target.month, self.target.day) >= SEASON_START else self.target.year - 1
        return date(start_year, SEASON_START[0], SEASON_START[1])


@dataclass(frozen=True)
class SeasonRank:
    year: int
    percent: int
    rank: int
    current: bool


def format_span(start: date, end: date) -> str:
    """AP dates joined by an en dash. The year is repeated only when it changes."""
    if start.year == end.year:
        return f"{_ABBR[start.month]} {start.day}–{_ABBR[end.month]} {end.day}, {end.year}"
    return (
        f"{_ABBR[start.month]} {start.day}, {start.year}–"
        f"{_ABBR[end.month]} {end.day}, {end.year}"
    )


def season_name(file_year: int, on: date) -> str:
    """Season label such as 2026-27.

    The NOAA file year is the end date of the window. On or after Sept. 30 that
    year is the season start. In January the file year is the second calendar
    year, so the label steps back to the Sept. 30 that opened the season.
    """
    start = file_year if (on.month, on.day) >= SEASON_START else file_year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def _label_row(item: tuple) -> list:
    text, lon, lat, small = item[:4]
    label_lon, label_lat = (item[4], item[5]) if len(item) >= 6 else (lon, lat)
    return [text, lon, lat, 1 if small else 0, label_lon, label_lat]


def season_end_stamp(end_year: int, target: date) -> tuple[datetime, datetime] | None:
    """Return the 12 UTC season window for one end year, or None on Feb. 29 of a non-leap year."""
    start_year = end_year if (target.month, target.day) >= SEASON_START else end_year - 1
    start = datetime(start_year, SEASON_START[0], SEASON_START[1], VALID_HOUR)
    try:
        end = datetime(end_year, target.month, target.day, VALID_HOUR)
    except ValueError:
        return None
    return start, end


def nohrsc_url(end_year: int, target: date) -> str | None:
    bounds = season_end_stamp(end_year, target)
    if bounds is None:
        return None
    start, end = bounds
    folder = f"{end_year}{target.month:02d}"
    return (
        "https://www.nohrsc.noaa.gov/snowfall/data/"
        f"{folder}/sfav2_CONUS_{start:%Y%m%d%H}_to_{end:%Y%m%d%H}.nc"
    )


def climatology_years(target: date) -> list[int]:
    """Completed seasons only. The current end year is the comparison, not the average."""
    return list(range(CLIMATOLOGY_FIRST_YEAR, target.year))


def _request(url: str, method: str) -> urllib.request.Request:
    return urllib.request.Request(url, method=method, headers=HEADERS)


def url_exists(url: str) -> bool:
    """True on HTTP 200. A 404 is a missing year. Other errors are retried, then raised."""
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(_request(url, "HEAD"), timeout=40) as response:
                return 200 <= int(response.status) < 300
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return False
            last = exc
        except urllib.error.URLError as exc:
            last = exc
        time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"Could not check {url}: {last}")


def download(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(_request(url, "GET"), timeout=120) as response:
                path.write_bytes(response.read())
            return
        except urllib.error.URLError as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Could not download {url}: {last}")


def choose_target(
    today: date,
    exists,
    *,
    lookback_days: int = LOOKBACK_DAYS,
    max_missing: int = MAX_MISSING_YEARS,
) -> ChosenDay:
    """Latest day, starting at yesterday, with the current file and few enough gaps.

    `exists` takes a URL and returns False when that season file is absent.
    """
    yesterday = today - timedelta(days=1)
    for offset in range(lookback_days):
        target = yesterday - timedelta(days=offset)
        chosen = evaluate_day(target, exists)
        if chosen is None:
            continue
        if len(chosen.missing_years) <= max_missing:
            return chosen
    raise RuntimeError(
        f"No day in the last {lookback_days} days has the current snowfall file "
        f"and at most {max_missing} missing climatology years."
    )


def evaluate_day(target: date, exists) -> ChosenDay | None:
    years = climatology_years(target)
    urls: dict[int, str] = {}
    for year in [*years, target.year]:
        url = nohrsc_url(year, target)
        if url is None:
            continue
        urls[year] = url
    if target.year not in urls:
        return None

    flags: dict[int, bool] = {}
    workers = min(8, len(urls))
    with ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(exists, url): year for year, url in urls.items()}
        for future in as_completed(futures):
            flags[futures[future]] = bool(future.result())
    if not flags.get(target.year, False):
        return None
    have = tuple(year for year in years if flags.get(year, False))
    missing = tuple(year for year in years if year not in have)
    if not have:
        return None
    return ChosenDay(target, target.year, have, missing)


def open_inches(path: Path) -> xr.DataArray:
    with xr.open_dataset(path) as ds:
        if "Data" not in ds:
            raise KeyError(f"Expected variable 'Data' in {path}")
        data = ds["Data"].load().astype("float32") * np.float32(METERS_TO_INCHES)
    data.name = "snowfall_inches"
    return data


def align(data: xr.DataArray, template: xr.DataArray) -> xr.DataArray:
    same_shape = data.sizes.get("lat") == template.sizes.get("lat") and data.sizes.get("lon") == template.sizes.get("lon")
    same_grid = same_shape and np.allclose(data.lat.values, template.lat.values) and np.allclose(data.lon.values, template.lon.values)
    if same_grid:
        return data
    return data.interp(lat=template.lat, lon=template.lon, method="nearest")


def percent_field(current: xr.DataArray, clim: xr.DataArray) -> xr.DataArray:
    """Percent of average. Cells below the inch threshold, and invalid cells, are NaN."""
    perc = (current / clim) * 100
    keep = (clim >= MIN_CLIM_INCHES) & np.isfinite(current) & np.isfinite(clim)
    return perc.where(keep)


def domain_percent(snowfall: xr.DataArray, clim: xr.DataArray) -> int:
    """Unweighted mean of the percent field, rounded, matching the anomaly runner."""
    values = percent_field(snowfall, clim).values
    valid = values[np.isfinite(values)]
    if valid.size == 0:
        raise RuntimeError("No snowfall cells met the 1 inch average threshold")
    return int(np.round(float(valid.mean())))


def rank_seasons(pairs: list[tuple[int, float]], current_year: int) -> list[SeasonRank]:
    """Rank 1 is the highest percent. A tie goes to the newer season."""
    ordered = sorted(pairs, key=lambda item: (-int(np.round(item[1])), -int(item[0])))
    rows = []
    for index, (year, percent) in enumerate(ordered, start=1):
        rows.append(
            SeasonRank(
                year=int(year),
                percent=int(np.round(percent)),
                rank=index,
                current=int(year) == int(current_year),
            )
        )
    return rows


def color_index(percent: float) -> int:
    """Band index. len(COLORS) means the 300% extension. A breakpoint opens the next band."""
    if percent >= SCALE_MAX:
        return len(COLORS)
    if percent <= 0:
        return 0
    return min(len(COLORS) - 1, int(percent // SCALE_STEP))


def color_for(percent: float) -> str:
    index = color_index(percent)
    if index >= len(COLORS):
        return OVER
    return COLORS[index]


def pack_field(perc: xr.DataArray) -> tuple[dict, str]:
    """North-to-south uint8 bins as a grayscale PNG. 0 is uncolored."""
    from PIL import Image

    if float(perc.lat.values[0]) < float(perc.lat.values[-1]):
        perc = perc.sortby("lat", ascending=False)
    if float(perc.lon.values[0]) > float(perc.lon.values[-1]):
        perc = perc.sortby("lon")
    values = np.asarray(perc.values, dtype=np.float32)
    bins = np.zeros(values.shape, dtype=np.uint8)
    finite = np.isfinite(values)
    with np.errstate(invalid="ignore"):
        raw = np.floor(values / np.float32(SCALE_STEP))
    raw = np.nan_to_num(raw, nan=0.0)
    indexes = np.where(
        values >= SCALE_MAX,
        len(COLORS),
        np.where(values <= 0, 0, np.minimum(len(COLORS) - 1, raw)),
    ).astype(np.int16)
    bins[finite] = (indexes[finite] + 1).astype(np.uint8)
    buffer = BytesIO()
    Image.fromarray(bins, mode="L").save(buffer, format="PNG", optimize=True)
    payload = base64.b64encode(buffer.getvalue()).decode("ascii")
    lat = perc.lat.values
    lon = perc.lon.values
    meta = {
        "nlat": int(values.shape[0]),
        "nlon": int(values.shape[1]),
        "latNorth": float(lat[0]),
        "latSouth": float(lat[-1]),
        "lonWest": float(lon[0]),
        "lonEast": float(lon[-1]),
    }
    return meta, payload


def source_line(years: tuple[int, ...] | list[int]) -> str:
    first, last = years[0], years[-1]
    expected = list(range(CLIMATOLOGY_FIRST_YEAR, last + 1))
    if list(years) == expected:
        return (
            "NOAA/NOHRSC season-to-date snowfall, compared with the "
            f"{first}–{last} average where that average is at least 1 inch."
        )
    return (
        "NOAA/NOHRSC season-to-date snowfall, compared with "
        f"{len(years)} seasons from {first} to {last} where that average is at least 1 inch."
    )



def scale_html(hidden: bool = False) -> str:
    bands = len(COLORS)
    cells = []
    for index, color in enumerate(COLORS):
        left = index / bands * 100
        width = 100 / bands
        cells.append(
            f'<i style="left:{left:.4f}%;width:calc({width:.4f}% - 1px);background:{color}"></i>'
        )
    ticks = []
    for value in (0, 50, 100, 150, 200, 250, SCALE_MAX):
        label = "300%+" if value == SCALE_MAX else f"{value}%"
        classes = []
        if value % 100:
            classes.append("minor")
        if value == SCALE_MAX:
            classes.append("break")
        attr = f' class="{" ".join(classes)}"' if classes else ""
        ticks.append(
            f'<span{attr} style="left:{value / SCALE_MAX * 100:.4f}%">{label}</span>'
        )
    hidden_attr = " hidden" if hidden else ""
    return (
        f'<div class="scale" id="anomaly-scale"{hidden_attr}>'
        '<div class="scale-top"><span class="below">Below average</span><span class="above">Above average</span></div>'
        f'<div class="swatches">{"".join(cells)}</div>'
        f'<div class="ticks">{"".join(ticks)}</div>'
        "</div>"
    )


def _sample_nearest(values, src_lat, src_lon, dst_lat, dst_lon) -> np.ndarray:
    """Sample cell centers onto destination centers. Off-grid centers are NaN."""
    from lib.snow_forecast import _shift_lon

    src_lat = np.asarray(src_lat, dtype=np.float64)
    src_lon = _shift_lon(src_lon)
    dst_lat = np.asarray(dst_lat, dtype=np.float64)
    dst_lon = _shift_lon(dst_lon)
    field = np.asarray(values, dtype=np.float64)
    if field.shape != (src_lat.size, src_lon.size):
        raise ValueError(f"Field shape {field.shape} does not match lat/lon sizes")
    if src_lat.size < 2 or src_lon.size < 2:
        raise ValueError("The snowfall field needs at least two rows and two columns")
    lat_order = np.argsort(src_lat)
    lon_order = np.argsort(src_lon)
    lat_values = src_lat[lat_order]
    lon_values = src_lon[lon_order]
    field = field[lat_order][:, lon_order]
    dlat = float(np.median(np.diff(lat_values)))
    dlon = float(np.median(np.diff(lon_values)))
    if dlat <= 0.0 or dlon <= 0.0:
        raise ValueError("The snowfall axes are not spaced")
    y_raw = (dst_lat - lat_values[0]) / dlat
    x_raw = (dst_lon - lon_values[0]) / dlon
    valid_y = (y_raw >= -0.5) & (y_raw <= lat_values.size - 0.5)
    valid_x = (x_raw >= -0.5) & (x_raw <= lon_values.size - 0.5)
    y = np.clip(np.rint(y_raw), 0, lat_values.size - 1).astype(np.int32)
    x = np.clip(np.rint(x_raw), 0, lon_values.size - 1).astype(np.int32)
    sampled = field[y[:, None], x[None, :]]
    return np.where(valid_y[:, None] & valid_x[None, :], sampled, np.nan)


def coverage_shares(field: xr.DataArray, clim: xr.DataArray, *, grid=None, land=None) -> tuple[int, int]:
    """Population and land-area shares at or above 100% of average.

    Both shares use drawn lower-48 land where the average is at least 1 inch.
    Land area is weighted by the cosine of latitude. Population is the 2020
    WorldPop count on those cells. The return is (population, land), each an
    integer percent.
    """
    perc = percent_field(field, clim)
    if grid is None:
        from lib.population import population_grid

        plat, plon, people = population_grid()
    else:
        plat, plon, people = grid
    people = np.asarray(people, dtype=np.float64)
    plat = np.asarray(plat, dtype=np.float64)
    plon = np.asarray(plon, dtype=np.float64)
    if land is None:
        from lib.snow_forecast import _drawn_land_mask

        land = _drawn_land_mask(plat, plon)
    land = np.asarray(land, dtype=bool)
    if land.shape != people.shape:
        raise ValueError(f"Land mask shape {land.shape} does not match the population grid")
    sampled = _sample_nearest(perc.values, perc.lat.values, perc.lon.values, plat, plon)
    if sampled.shape != people.shape:
        raise ValueError(f"Sampled field shape {sampled.shape} does not match the population grid")
    eligible = land & np.isfinite(sampled)
    if not np.any(eligible):
        raise RuntimeError("No snowfall cells met the 1 inch average threshold on drawn land")
    above = eligible & (sampled >= ABOVE_PERCENT)
    weights = np.cos(np.deg2rad(plat))[:, None]
    land_share = float((weights * above).sum() / (weights * eligible).sum() * 100.0)
    counted = float(people[eligible].sum())
    if counted <= 0.0:
        raise RuntimeError("No population sits where average snowfall is at least 1 inch")
    pop_share = float(people[above].sum() / counted * 100.0)
    return int(np.round(pop_share)), int(np.round(land_share))


def _rank_list(rows: list[SeasonRank], on: date, *, scale_to_max: bool, color: str | None) -> str:
    top = max(max(row.percent for row in rows), 100 if scale_to_max else 1)
    items = []
    for row in rows:
        if scale_to_max:
            width = 0 if row.percent <= 0 else max(1, round(row.percent / top * 100))
            bar = color_for(row.percent)
        else:
            width = 0 if row.percent <= 0 else min(100, row.percent)
            bar = color or ABOVE_LABEL
        attr = ' class="now"' if row.current else ""
        items.append(
            f"<li{attr}>"
            f'<span class="n">{row.rank}</span>'
            f'<span class="year">{season_name(row.year, on)}</span>'
            f'<span class="track"><span class="bar" data-color="{bar}" data-width="{width}" '
            f'style="width:{width}%;background:{bar}"></span></span>'
            f'<span class="pct">{row.percent}%</span>'
            "</li>"
        )
    return '<ol class="rank-list">' + "".join(items) + "</ol>"


def _from_to(span: str) -> str:
    """The en-dash window as words, such as 'Sept. 30 to Nov. 4, 2026'."""
    return span.replace("–", " to ")


def _chart_section(
    title: str,
    filename: str,
    download_label: str,
    rows: list[SeasonRank],
    on: date,
    *,
    scale_to_max: bool,
    dek: str = "",
    credit: str = "",
    color: str | None = None,
) -> str:
    dek_html = f'<p class="chart-dek">{html.escape(dek)}</p>' if dek else ""
    credit_html = f'<p class="chart-credit">{html.escape(credit)}</p>' if credit else ""
    return (
        '<section class="rank-chart" '
        f'data-file="{html.escape(filename, quote=True)}" '
        f'data-dek="{html.escape(dek, quote=True)}" '
        f'data-credit="{html.escape(credit, quote=True)}">'
        '<div class="chart-head">'
        f'<h2 class="compare">{html.escape(title)}</h2>'
        f'<button class="download" type="button" aria-label="{html.escape(download_label, quote=True)}">Download</button>'
        "</div>"
        f"{dek_html}"
        f"{_rank_list(rows, on, scale_to_max=scale_to_max, color=color)}"
        f"{credit_html}"
        "</section>"
    )


def charts_html(
    rows: list[SeasonRank],
    on: date,
    span: str,
    pop_rows: list[SeasonRank] | None = None,
    land_rows: list[SeasonRank] | None = None,
) -> str:
    """The season chart, plus population and land-area coverage when those rows exist."""
    window = _from_to(span)
    parts = [
        _chart_section(
            f"Percentage of average snowfall from {window}",
            "snowfall-percent-of-average-by-season.png",
            "Download the percentage of average snowfall chart",
            rows,
            on,
            scale_to_max=True,
            credit="Data: NOAA/NOHRSC",
        )
    ]
    if pop_rows:
        parts.append(
            _chart_section(
                "Percentage of population with above-average snowfall",
                "snowfall-population-above-average.png",
                "Download the population chart",
                pop_rows,
                on,
                scale_to_max=False,
                dek=f"From {window}",
                credit="Population where the average is at least 1 inch. Above average is 100% or more.",
                color=ABOVE_LABEL,
            )
        )
    if land_rows:
        parts.append(
            _chart_section(
                "Percentage of land area with above-average snowfall",
                "snowfall-land-area-above-average.png",
                "Download the land area chart",
                land_rows,
                on,
                scale_to_max=False,
                dek=f"From {window}",
                credit="Land area where the average is at least 1 inch. Above average is 100% or more.",
                color=ABOVE_LABEL,
            )
        )
    return "".join(parts)


def _anomaly_view(span: str, rank_label: str, meta: dict, alt: str, source: str) -> dict:
    return {
        "button": "Anomaly",
        "title": TITLE,
        "span": span,
        "rank": rank_label,
        "source": source,
        "alt": alt,
        "kind": "anomaly",
        "smooth": True,
        "filename": "snowfall-percentage-of-average.png",
        "colors": COLORS,
        "over": OVER,
        "pin": None,
        "nlat": meta["nlat"],
        "nlon": meta["nlon"],
        "latNorth": round(meta["latNorth"], 5),
        "latSouth": round(meta["latSouth"], 5),
        "lonWest": round(meta["lonWest"], 5),
        "lonEast": round(meta["lonEast"], 5),
    }


def land_bounds() -> tuple[float, float, float, float]:
    """West, east, south, north of the basemap land, including every island."""
    global _LAND_BOUNDS
    if _LAND_BOUNDS is None:
        script = (ROOT / "lib" / "snow_basemap.js").read_text(encoding="utf-8")
        data = json.loads(script[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))
        lons = []
        lats = []
        for poly in data["land"]:
            for ring in poly:
                lons.extend(ring[0::2])
                lats.extend(ring[1::2])
        _LAND_BOUNDS = (min(lons), max(lons), min(lats), max(lats))
    return _LAND_BOUNDS


def _view_buttons(forecasts: dict, *, open_forecast: bool = False) -> str:
    ecmwf = forecasts["ecmwf"]["button"]
    aifs = forecasts["aifs"]["button"]
    hidden = "" if open_forecast else " hidden"
    return (
        f'<div class="snow-controls" id="snow-controls"{hidden}>'
        f'<div class="model-row" id="model-row"{hidden}>'
        f'<button type="button" id="view-ecmwf" data-view="ecmwf" aria-selected="true" disabled>{ecmwf}</button>'
        f'<button type="button" id="view-aifs" data-view="aifs" aria-selected="false" disabled>{aifs}</button>'
        "</div>"
        "</div>"
    )


def _forecast_images(forecasts: dict) -> str:
    images = []
    for key in ("ecmwf", "aifs"):
        images.append(
            f'<img id="field-{key}" alt="" hidden src="data:image/png;base64,{forecasts[key]["field"]}">'
        )
    return "".join(images)


def render_page(
    *,
    span: str,
    rank_label: str,
    rows: list[SeasonRank],
    meta: dict,
    field: str,
    alt: str,
    source: str,
    on: date,
    forecasts: dict | None = None,
    kind: str = "anomaly",
    pop_rows: list[SeasonRank] | None = None,
    land_rows: list[SeasonRank] | None = None,
) -> str:
    from lib.snow_forecast import snow_scale_html

    forecast_page = kind == "forecast"
    if forecast_page and not forecasts:
        raise ValueError("The forecast page needs both model views")
    path = FORECAST_PATH if forecast_page else PAGE_PATH
    title = FORECAST_TITLE if forecast_page else TITLE
    shown = forecasts["ecmwf"] if forecast_page else None
    template = (ROOT / "lib" / "snow_anomaly_page.html").read_text(encoding="utf-8")
    nav = _site_nav(path)
    seo = _seo(path, title)
    payload = {
        "span": span,
        "rank": rank_label,
        "source": source,
        "alt": alt,
        "extent": [EXTENT[0], EXTENT[1], EXTENT[2], EXTENT[3]],
        "frame": [FRAME[0], FRAME[1], FRAME[2], FRAME[3]],
        "landBounds": [round(value, 4) for value in land_bounds()],
        "nlat": meta["nlat"],
        "nlon": meta["nlon"],
        "latNorth": round(meta["latNorth"], 5),
        "latSouth": round(meta["latSouth"], 5),
        "lonWest": round(meta["lonWest"], 5),
        "lonEast": round(meta["lonEast"], 5),
        "colors": COLORS,
        "over": OVER,
        "below": BELOW_LABEL,
        "above": ABOVE_LABEL,
        "labels": [_label_row(item) for item in STATE_LABELS],
    }
    buttons = ""
    images = ""
    if forecasts:
        payload["views"] = {
            "anomaly": _anomaly_view(span, rank_label, meta, alt, source),
            "ecmwf": {key: value for key, value in forecasts["ecmwf"].items() if key != "field"},
            "aifs": {key: value for key, value in forecasts["aifs"].items() if key != "field"},
        }
        buttons = _view_buttons(forecasts, open_forecast=forecast_page)
        images = _forecast_images(forecasts)
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (
        template.replace("__TITLE__", title)
        .replace("__H2__", title)
        .replace("__SEO__", seo)
        .replace("__NAV__", nav)
        .replace("__VIEW_BUTTONS__", buttons)
        .replace("__SPAN__", shown["span"] if shown else span)
        .replace("__RANK__", shown["rank"] if shown else rank_label)
        .replace("__BASEMAP__", BASEMAP_URL)
        .replace("__FORECAST_FIELDS__", images)
        .replace("__FIELD__", field)
        .replace("__DATA__", data)
        .replace("__SNOW_SCALE__", snow_scale_html(hidden=not forecast_page))
        .replace("__SCALE__", scale_html(hidden=forecast_page))
        .replace("__RANKS_HIDDEN__", " hidden" if forecast_page else "")
        .replace("__RANKS__", "" if forecast_page else charts_html(rows, on, span, pop_rows, land_rows))
        .replace("__SOURCE__", shown["source"] if shown else source)
    )


def _load_season(year: int, target: date, directory: Path, template: xr.DataArray | None) -> xr.DataArray:
    url = nohrsc_url(year, target)
    if url is None:
        raise RuntimeError(f"No NOAA file name for {year} on {target.isoformat()}")
    path = directory / f"snowfall_{year}.nc"
    if not path.exists() or path.stat().st_size < 1000:
        print(f"Downloading {year}")
        download(url, path)
    data = open_inches(path)
    if template is not None:
        data = align(data, template)
    return data


def build(today: date, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    data_dir = work / "nc"
    chosen = choose_target(today, url_exists)
    if chosen.missing_years:
        print(f"Using {chosen.target.isoformat()} with missing years {', '.join(map(str, chosen.missing_years))}")
    else:
        print(f"Using {chosen.target.isoformat()} with all {len(chosen.climatology_years)} climatology years")

    current = _load_season(chosen.current_year, chosen.target, data_dir, None)
    seasons = []
    for year in chosen.climatology_years:
        seasons.append(_load_season(year, chosen.target, data_dir, current))
    clim = xr.concat(seasons, dim="year").mean("year")
    pairs = []
    pop_pairs = []
    land_pairs = []
    for year, field in zip(chosen.climatology_years, seasons):
        pairs.append((year, domain_percent(field, clim)))
        population, area = coverage_shares(field, clim)
        pop_pairs.append((year, population))
        land_pairs.append((year, area))
    current_percent = domain_percent(current, clim)
    population, area = coverage_shares(current, clim)
    pairs.append((chosen.current_year, current_percent))
    pop_pairs.append((chosen.current_year, population))
    land_pairs.append((chosen.current_year, area))
    rows = rank_seasons(pairs, chosen.current_year)
    pop_rows = rank_seasons(pop_pairs, chosen.current_year)
    land_rows = rank_seasons(land_pairs, chosen.current_year)
    current_row = next(row for row in rows if row.current)
    perc = percent_field(current, clim)
    colored = float(np.isfinite(perc.values).mean())
    print(f"Colored cells: {colored:.1%} of the grid")
    print(f"Rank {current_row.rank} of {len(rows)} at {current_row.percent}% of average")
    print(f"Population above average: {population}% ; land area above average: {area}%")

    meta, field = pack_field(perc)
    span = format_span(chosen.season_start, chosen.target)
    rank_label = f"Rank {current_row.rank} of {len(rows)} · {current_row.percent}% of average"
    alt = f"Snowfall percentage of average from {span}. Brown is below average and blue is above average."
    from lib.snow_forecast import load_forecasts

    forecasts = load_forecasts(work)
    page_args = dict(
        span=span,
        rank_label=rank_label,
        rows=rows,
        meta=meta,
        field=field,
        alt=alt,
        source=source_line(chosen.climatology_years),
        on=chosen.target,
        forecasts=forecasts,
        pop_rows=pop_rows,
        land_rows=land_rows,
    )
    page = work / "index.html"
    page.write_text(render_page(**page_args), encoding="utf-8")
    forecast_page = work / "forecast.html"
    forecast_page.write_text(render_page(**page_args, kind="forecast"), encoding="utf-8")
    print(f"Page: {page} ({page.stat().st_size:,} bytes)")
    print(f"Forecast: {forecast_page} ({forecast_page.stat().st_size:,} bytes)")
    return page


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the snowfall percentage-of-average page")
    parser.add_argument("--work", required=True, help="Directory for downloads and the finished page")
    parser.add_argument("--today", default="", help="UTC date YYYY-MM-DD. The search starts the day before.")
    args = parser.parse_args(argv)
    if args.today.strip():
        today = datetime.strptime(args.today.strip(), "%Y-%m-%d").date()
    else:
        today = datetime.now(timezone.utc).date()
    build(today, Path(args.work).expanduser())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
