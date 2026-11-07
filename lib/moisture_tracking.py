"""Moisture tracking page for the precipitable-water update.

The page is built from the two ERA5 files that update already downloads.
"""

from __future__ import annotations

import base64
import json
import math
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from lib.c3s_globes import _seo, _site_nav

ROOT = Path(__file__).resolve().parents[1]
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
HIGHLIGHT_COLORS = ("#E69F00", "#D55E00", "#0072B2", "#CC79A7")
HTML_CACHE = "no-cache, no-store, must-revalidate"
HTML_TYPE = "text/html; charset=utf-8"
COASTS_URL = "/climate_imagery/moisture_coasts.js?v=1"
COASTS_KEY = "climate_imagery/moisture_coasts.js"
COASTS_CACHE = "public, max-age=2592000"
COASTS_TYPE = "application/javascript; charset=utf-8"


def js_round(value: float, digits: int = 2) -> float:
    """Round a positive number the way JavaScript Math.round does."""
    factor = 10 ** digits
    return math.floor(float(value) * factor + 0.5) / factor


def inches_text(value: float) -> str:
    return f"{js_round(value):.2f} in."


def year_labels(year: int, month: int) -> tuple[str, str]:
    month_name = MONTHS[month - 1]
    month_title = f"Precipitable water in {month_name}"
    year_title = f"Precipitable water in {month_name} {year} compared to historical levels"
    return month_title, year_title


def _variable(ds: xr.Dataset) -> xr.DataArray:
    for name in ("tcw", "total_column_water"):
        if name in ds.data_vars:
            return ds[name]
    raise KeyError("total column water")


def _collapse(field: xr.DataArray) -> xr.DataArray:
    extra = [dim for dim in field.dims if dim not in ("time", "valid_time", "latitude", "longitude")]
    if extra:
        field = field.max(extra)
    return field


def _time_dim(field: xr.DataArray) -> str:
    if "valid_time" in field.dims:
        return "valid_time"
    if "time" in field.dims:
        return "time"
    raise KeyError("no time dimension")


def _weights(latitude: xr.DataArray) -> xr.DataArray:
    weights = np.clip(np.cos(np.deg2rad(np.asarray(latitude.values, dtype=float))), 0, None)
    return xr.DataArray(weights, dims=("latitude",), coords={"latitude": latitude})


def _lookup(ds: xr.Dataset) -> dict[tuple[int, int], float]:
    """Cosine-weighted global mean, in inches, for each year and month in the file."""
    field = _collapse(_variable(ds))
    time_dim = _time_dim(field)
    times = pd.DatetimeIndex(pd.to_datetime(field[time_dim].values))
    weights = _weights(field["latitude"])
    found: dict[tuple[int, int], list[float]] = {}
    for year in sorted(set(int(item) for item in times.year)):
        idx = np.where(times.year == year)[0]
        piece = field.isel({time_dim: idx})
        means = np.asarray(piece.weighted(weights).mean(dim=("latitude", "longitude")).values, dtype=float) / 25.4
        for stamp, value in zip(times[idx], means):
            if not np.isfinite(value):
                continue
            found.setdefault((int(stamp.year), int(stamp.month)), []).append(float(value))
    return {key: float(np.mean(values)) for key, values in found.items()}


def _num(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    return round(float(value), 6)


def pack_percent(perc: xr.DataArray) -> dict:
    """Coarsen a percent-of-average grid to about 1 degree and pack it as uint8."""
    field = _collapse(perc)
    extra = [dim for dim in field.dims if dim not in ("latitude", "longitude")]
    if extra:
        field = field.max(extra)
    field = field.transpose("latitude", "longitude")
    lat = np.asarray(field["latitude"].values, dtype=float)
    lon = np.mod(np.asarray(field["longitude"].values, dtype=float), 360.0)
    values = np.asarray(field.values, dtype=float)
    values = values[:, np.argsort(lon, kind="mergesort")]
    lon = lon[np.argsort(lon, kind="mergesort")]
    lat_order = np.argsort(-lat, kind="mergesort")
    lat = lat[lat_order]
    values = values[lat_order, :]
    spacing = float(np.median(np.abs(np.diff(lat)))) if len(lat) > 1 else 1.0
    factor = max(1, int(round(1.0 / spacing))) if spacing else 1
    nlat = (len(lat) // factor) * factor
    nlon = (len(lon) // factor) * factor
    if nlat == 0 or nlon == 0:
        raise ValueError("Percent grid is empty")
    lat = lat[:nlat]
    lon = lon[:nlon]
    values = values[:nlat, :nlon]
    if factor > 1:
        values = values.reshape(nlat // factor, factor, nlon // factor, factor)
        with np.errstate(all="ignore"):
            values = np.nanmean(values, axis=(1, 3))
        lat = lat.reshape(-1, factor).mean(axis=1)
        lon = lon.reshape(-1, factor).mean(axis=1)
    packed = np.full(values.shape, 255, dtype=np.uint8)
    ok = np.isfinite(values)
    packed[ok] = np.floor(np.clip(values[ok], 0, 254) + 0.5).astype(np.uint8)
    dlat = float(lat[1] - lat[0]) if len(lat) > 1 else -1.0
    dlon = float(lon[1] - lon[0]) if len(lon) > 1 else 1.0
    return {
        "lat0": float(lat[0]),
        "dlat": dlat,
        "lon0": float(lon[0]),
        "dlon": dlon,
        "nlat": int(packed.shape[0]),
        "nlon": int(packed.shape[1]),
        "grid": base64.b64encode(packed.tobytes()).decode("ascii"),
    }


def _cycle(monthly: dict[tuple[int, int], float], target: pd.Timestamp, start: int) -> dict:
    highlight = list(range(int(target.year) - 3, int(target.year) + 1))
    envelope_years = [year for year in range(start, highlight[0]) if any((year, month) in monthly for month in range(1, 13))]
    lo, hi, avg = [], [], []
    for month in range(1, 13):
        band = [monthly[(year, month)] for year in envelope_years if (year, month) in monthly]
        lo.append(_num(min(band) if band else None))
        hi.append(_num(max(band) if band else None))
        clim = [monthly[(year, month)] for year in range(1991, 2021) if (year, month) in monthly]
        avg.append(_num(float(np.mean(clim)) if clim else None))
    series = []
    for year, color in zip(highlight, HIGHLIGHT_COLORS):
        values = [_num(monthly.get((year, month))) for month in range(1, 13)]
        if year == int(target.year):
            values = values[: int(target.month)]
        if any(value is not None for value in values):
            series.append({"year": year, "color": color, "values": values})
    envelope = ""
    if envelope_years:
        envelope = f"{start}\u2013{highlight[0] - 1}"
    return {"lo": lo, "hi": hi, "avg": avg, "series": series, "envelope": envelope}


def month_history(monthly: dict[tuple[int, int], float], start: int, target: pd.Timestamp) -> list[list]:
    """Every month's global precipitable water, in inches, from the start year through the target month."""
    rows = []
    end_year = int(target.year)
    end_month = int(target.month)
    for year in range(int(start), end_year + 1):
        last_month = end_month if year == end_year else 12
        for month in range(1, last_month + 1):
            rows.append([year, month, _num(monthly.get((year, month)))])
    return rows


def build_payload(perc: xr.DataArray, month_ds: xr.Dataset, monthly_ds: xr.Dataset, target: pd.Timestamp) -> dict:
    target = pd.Timestamp(year=int(target.year), month=int(target.month), day=1)
    month_values = {year: value for (year, month), value in _lookup(month_ds).items() if month == int(target.month)}
    if int(target.year) not in month_values:
        raise RuntimeError(f"No global {MONTHS[target.month - 1]} {target.year} value to rank.")
    start = min(month_values)
    ordered = []
    finite = []
    dip_year = None
    dip_value = None
    for year in range(start, int(target.year) + 1):
        value = month_values.get(year)
        ordered.append(_num(value))
        if value is None or not np.isfinite(value):
            continue
        finite.append(float(value))
        if dip_value is None or value < dip_value:
            dip_value = float(value)
            dip_year = year
    latest = float(month_values[int(target.year)])
    place = 1 + sum(1 for value in finite if value > latest)
    month_name = MONTHS[int(target.month) - 1]
    month_title, year_title = year_labels(int(target.year), int(target.month))
    monthly = _lookup(monthly_ds)
    cycle = _cycle(monthly, target, start)
    return {
        "month": month_name,
        "year": int(target.year),
        "monthNumber": int(target.month),
        "start": int(start),
        "inches": ordered,
        "rankPlace": int(place),
        "rankCount": int(len(finite)),
        "rank": f"Rank {place} of {len(finite)} in {int(target.year)}",
        "inchesText": inches_text(latest),
        "dipYear": dip_year,
        "range": f"{month_name} moistening stripes",
        "monthYear": f"{month_name} {int(target.year)}",
        "mapTitle": "Precipitable water percentage of average",
        "monthTitle": month_title,
        "yearTitle": year_title,
        "envelope": cycle.pop("envelope"),
        "map": pack_percent(perc),
        "cycle": cycle,
        "history": month_history(monthly, start, target),
    }


def coasts_script() -> str:
    """Coast assignments as globals, so the page script can draw after the file loads."""
    text = (ROOT / "lib" / "moisture_tracking_coasts.js").read_text(encoding="utf-8").strip()
    if not text.startswith("const COASTS =") or not text.endswith(";"):
        raise RuntimeError("Coast file is not a complete COASTS assignment")
    for name in ("COASTS", "COUNTRIES", "STATES", "LAKES"):
        token = f"const {name} ="
        if token not in text:
            raise RuntimeError(f"Coast file is missing {token}")
        text = text.replace(token, f"var {name} =", 1)
    return text


def render(payload: dict) -> str:
    template = (ROOT / "lib" / "moisture_tracking_page.html").read_text(encoding="utf-8")
    title = "Moisture tracking"
    data = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    return (
        template.replace("__TITLE__", title)
        .replace("__SEO__", _seo("/climate/moisture-tracking", title))
        .replace("__NAV__", _site_nav("/climate/moisture-tracking"))
        .replace("__MONTH_YEAR__", payload["monthYear"])
        .replace("__MONTH_NAME__", payload["month"])
        .replace("__RANK__", payload["rank"])
        .replace("__MAP_TITLE__", payload["mapTitle"])
        .replace("__MONTH_TITLE__", payload["monthTitle"])
        .replace("__YEAR_TITLE__", payload["yearTitle"])
        .replace("__RANGE__", payload["range"])
        .replace("__COASTS_URL__", COASTS_URL)
        .replace("__DATA__", data)
    )


def _upload_html(path: Path, key: str, aws_bin: str, aws_profile: str, bucket: str) -> None:
    cmd = [
        aws_bin,
        "s3",
        "cp",
        str(path),
        f"s3://{bucket}/{key}",
        "--content-type",
        HTML_TYPE,
        "--cache-control",
        HTML_CACHE,
        "--only-show-errors",
    ]
    result = subprocess.run(cmd, env={**os.environ, "AWS_PROFILE": aws_profile}, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        raise SystemExit(result.returncode)
    print(f"Uploaded: s3://{bucket}/{key}")


def _upload_bytes(body: bytes, key: str, content_type: str, cache: str, aws_bin: str, aws_profile: str, bucket: str) -> None:
    cmd = [
        aws_bin,
        "s3",
        "cp",
        "-",
        f"s3://{bucket}/{key}",
        "--content-type",
        content_type,
        "--cache-control",
        cache,
        "--only-show-errors",
    ]
    result = subprocess.run(cmd, input=body, env={**os.environ, "AWS_PROFILE": aws_profile}, capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", "replace"))
        raise SystemExit(result.returncode)
    print(f"Uploaded: s3://{bucket}/{key}")


def publish(
    perc: xr.DataArray,
    month_ds: xr.Dataset,
    monthly_ds: xr.Dataset,
    target: pd.Timestamp,
    image_dir: Path,
    skip_upload: bool,
    aws_bin: str,
    aws_profile: str,
    bucket: str,
) -> Path:
    """Write the tracking page. Trends keeps its own annual publish."""
    payload = build_payload(perc, month_ds, monthly_ds, target)
    publish_dir = Path(image_dir).parent / "publish"
    publish_dir.mkdir(parents=True, exist_ok=True)
    tracking = publish_dir / "moisture-tracking.html"
    coasts = publish_dir / "moisture_coasts.js"
    tracking.write_text(render(payload), encoding="utf-8")
    coasts.write_bytes(coasts_script().encode("utf-8"))
    print(f"Saved: {tracking}")
    print(f"Saved: {coasts}")
    if not skip_upload:
        _upload_html(tracking, "moisture-tracking", aws_bin, aws_profile, bucket)
        _upload_bytes(coasts.read_bytes(), COASTS_KEY, COASTS_TYPE, COASTS_CACHE, aws_bin, aws_profile, bucket)
    return tracking
