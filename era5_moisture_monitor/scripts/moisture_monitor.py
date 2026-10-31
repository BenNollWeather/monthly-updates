#!/usr/bin/env python3
"""ERA5 global moisture monitor.

Produces ONE composite dashboard PNG from ERA5 monthly single-level fields:
- total_column_water (TCW; kg m-2)
- vertical_integral_of_eastward_water_vapour_flux (VIWVE; kg m-1 s-1)
- vertical_integral_of_northward_water_vapour_flux (VIWVN; kg m-1 s-1)
- total_precipitation (TP; ERA5 monthly accumulation/rate field)

The dashboard summarizes the latest available month on monthly, trailing
3-month, and rolling 12-month bases, with spatial percentile maps, global ranks,
Tufte-like sparklines, and TCW/IVT/precipitation historical decile stripes.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Tuple

import matplotlib
matplotlib.use("Agg")


def _apply_house_style() -> None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "lib" / "map_style.py").is_file():
            root = str(parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            break
    from lib.map_style import apply
    apply()


_apply_house_style()

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from matplotlib.gridspec import GridSpec
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

try:
    import cartopy.crs as ccrs
    import cartopy.feature as cfeature
except ImportError as exc:
    raise SystemExit("Cartopy is required for map geography: pip install cartopy") from exc

DATASET = "reanalysis-era5-single-levels-monthly-means"
MOISTURE_VARIABLES = [
    "total_column_water",
    "vertical_integral_of_eastward_water_vapour_flux",
    "vertical_integral_of_northward_water_vapour_flux",
]
ALIASES = {
    "tcw": ["tcw", "total_column_water"],
    "uivt": ["viwve", "p71.162", "vertical_integral_of_eastward_water_vapour_flux"],
    "vivt": ["viwvn", "p72.162", "vertical_integral_of_northward_water_vapour_flux"],
    "tp": ["tp", "total_precipitation"],
}
MONTH_LABELS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
BASELINE_START = 1991
BASELINE_END = 2020


def _find_var(ds: xr.Dataset, candidates):
    for name in candidates:
        if name in ds.data_vars:
            return ds[name]
    lower = {k.lower(): k for k in ds.data_vars}
    for name in candidates:
        if name.lower() in lower:
            return ds[lower[name.lower()]]
    raise KeyError(f"Could not find any of {candidates}; found {list(ds.data_vars)}")


def _standardize_time(ds: xr.Dataset) -> xr.Dataset:
    if "valid_time" in ds.coords and "time" not in ds.coords:
        ds = ds.rename({"valid_time": "time"})
    if "date" in ds.coords and "time" not in ds.coords:
        ds = ds.rename({"date": "time"})
    if "time" not in ds.coords:
        raise KeyError("ERA5 file has no time/valid_time coordinate")
    return ds.sortby("time")


def _canonicalize_grid(ds: xr.Dataset) -> xr.Dataset:
    """Normalize time/lat/lon coordinates without altering the data fields."""
    ds = _standardize_time(ds)

    lon_name = "longitude" if "longitude" in ds.coords else "lon"
    lat_name = "latitude" if "latitude" in ds.coords else "lat"
    rename = {}
    if lon_name != "longitude":
        rename[lon_name] = "longitude"
    if lat_name != "latitude":
        rename[lat_name] = "latitude"
    if rename:
        ds = ds.rename(rename)

    # Normalize monthly timestamps to month-start. This avoids harmless CDS
    # timestamp differences between moisture files and precipitation sidecars
    # from collapsing an inner merge to zero time steps.
    month_start = pd.to_datetime(ds.time.values).to_period("M").to_timestamp()
    ds = ds.assign_coords(time=month_start)

    # Normalize coordinate precision and longitude convention so nearest-grid
    # alignment is deterministic across separately downloaded files.
    ds = ds.assign_coords(
        latitude=np.round(np.asarray(ds.latitude.values, dtype=float), 6),
        longitude=np.round(np.asarray(ds.longitude.values, dtype=float), 6),
    )
    if float(ds.longitude.max()) > 180:
        ds = ds.assign_coords(
            longitude=((ds.longitude + 180) % 360) - 180
        ).sortby("longitude")
    if ds.latitude[0] < ds.latitude[-1]:
        ds = ds.sortby("latitude", ascending=False)

    return ds.sortby("time")


def _align_precip_to_moisture(tp: xr.DataArray, ds: xr.Dataset) -> xr.DataArray:
    """Align precipitation sidecars to the moisture grid without touching TCW/IVT."""
    tp_ds = _canonicalize_grid(tp.to_dataset(name="tp"))
    tp = tp_ds["tp"]

    # First align time by month. Then use nearest-neighbor coordinate matching
    # only to absorb tiny floating-point differences in otherwise identical CDS
    # grids. No interpolation is performed on the moisture variables.
    tp = tp.reindex(
        time=ds.time,
        method="nearest",
        tolerance=np.timedelta64(20, "D"),
    )

    lat_step = float(np.nanmedian(np.abs(np.diff(np.asarray(ds.latitude.values, dtype=float))))) if ds.sizes.get("latitude", 0) > 1 else 1.0
    lon_step = float(np.nanmedian(np.abs(np.diff(np.asarray(ds.longitude.values, dtype=float))))) if ds.sizes.get("longitude", 0) > 1 else 1.0
    tp = tp.reindex(
        latitude=ds.latitude,
        longitude=ds.longitude,
        method="nearest",
        tolerance={
            "latitude": max(lat_step * 0.51, 1e-5),
            "longitude": max(lon_step * 0.51, 1e-5),
        },
    )
    return tp


def open_era5(path_glob: str) -> xr.Dataset:
    if os.path.isabs(path_glob):
        base_dir = Path(path_glob).parent
        paths = sorted(base_dir.glob(Path(path_glob).name))
    else:
        base_dir = Path(path_glob).parent if str(Path(path_glob).parent) != "." else Path()
        paths = sorted(Path().glob(path_glob))
    if not paths:
        raise FileNotFoundError(f"No files matched: {path_glob}")

    pieces = [_canonicalize_grid(xr.open_dataset(p)) for p in paths]
    ds = xr.concat(pieces, dim="time").sortby("time")
    _, keep = np.unique(pd.to_datetime(ds.time.values), return_index=True)
    ds = ds.isel(time=np.sort(keep))

    # IMPORTANT: do not xr.merge(..., join="inner") the precipitation sidecars
    # into the full moisture Dataset. A coordinate mismatch can make every
    # VIWVE/VIWVN value disappear. Instead, align only TP to the already-valid
    # moisture grid and assign that single variable afterward.
    existing_tp = None
    try:
        existing_tp = _find_var(ds, ALIASES["tp"]).astype("float32")
    except KeyError:
        pass

    precip_paths = sorted(base_dir.glob("era5_precip_monthly_*.nc"))
    sidecar_tp = None
    if precip_paths:
        precip_pieces = [_canonicalize_grid(xr.open_dataset(p)) for p in precip_paths]
        precip = xr.concat(precip_pieces, dim="time").sortby("time")
        _, pkeep = np.unique(pd.to_datetime(precip.time.values), return_index=True)
        precip = precip.isel(time=np.sort(pkeep))
        sidecar_tp = _align_precip_to_moisture(
            _find_var(precip, ALIASES["tp"]).astype("float32"),
            ds,
        )

    if existing_tp is not None:
        existing_tp = _align_precip_to_moisture(existing_tp, ds)
        tp = existing_tp if sidecar_tp is None else existing_tp.combine_first(sidecar_tp)
    elif sidecar_tp is not None:
        tp = sidecar_tp
    else:
        raise KeyError(
            "Total precipitation is missing from the ERA5 cache. "
            "Run the download step once to fetch precipitation sidecars."
        )

    if not bool(np.isfinite(tp).any()):
        raise ValueError(
            "Total precipitation could not be aligned to the moisture cache. "
            "Check the precipitation sidecar grid/time coordinates."
        )

    ds = ds.assign(tp=tp.astype("float32"))
    return ds


def extract_fields(ds: xr.Dataset) -> xr.Dataset:
    tcw = _find_var(ds, ALIASES["tcw"]).astype("float32")
    u = _find_var(ds, ALIASES["uivt"]).astype("float32")
    v = _find_var(ds, ALIASES["vivt"]).astype("float32")
    tp = _find_var(ds, ALIASES["tp"]).astype("float32")
    out = xr.Dataset({
        "tcw": tcw,
        "ivt": np.hypot(u, v).astype("float32"),
        "tp": tp,
    })
    lon_name = "longitude" if "longitude" in out.coords else "lon"
    lat_name = "latitude" if "latitude" in out.coords else "lat"
    if lon_name != "longitude":
        out = out.rename({lon_name: "longitude"})
    if lat_name != "latitude":
        out = out.rename({lat_name: "latitude"})
    if float(out.longitude.max()) > 180:
        out = out.assign_coords(longitude=((out.longitude + 180) % 360) - 180).sortby("longitude")
    if out.latitude[0] < out.latitude[-1]:
        out = out.sortby("latitude", ascending=False)
    return out

def validate_ivt(fields: xr.Dataset) -> None:
    """Basic sanity checks for the ERA5 IVT magnitude field.

    ERA5 provides vertically integrated eastward and northward water-vapor flux
    components. IVT magnitude is therefore sqrt(u^2 + v^2). This diagnostic
    checks for impossible negatives and prints robust global summaries so large
    TCW/IVT rank differences can be distinguished from a calculation problem.
    """
    ivt = fields["ivt"]
    if bool((ivt < 0).any()):
        raise ValueError("IVT magnitude contains negative values; check component decoding")
    finite = np.asarray(ivt.values[np.isfinite(ivt.values)], dtype=float)
    if finite.size == 0:
        raise ValueError(
            "IVT field contains no finite values. This usually indicates a coordinate "
            "alignment problem or an incomplete/corrupt VIWVE/VIWVN cache file."
        )
    q50, q95, q99 = np.nanpercentile(finite, [50, 95, 99])
    print(f"IVT sanity check: median={q50:.1f}, p95={q95:.1f}, p99={q99:.1f} kg m^-1 s^-1")


def _retrieve_netcdf(client, request: Dict, target: Path) -> None:
    """Download to a temporary path and accept only a readable NetCDF file."""
    partial = target.with_name(f"{target.name}.part")
    partial.unlink(missing_ok=True)
    client.retrieve(DATASET, request, str(partial))

    try:
        with xr.open_dataset(partial) as downloaded:
            if not downloaded.data_vars:
                raise ValueError("the downloaded dataset contains no data variables")
    except Exception as exc:
        header = partial.read_bytes()[:8] if partial.exists() else b""
        if header.startswith(b"PK"):
            detected = "a ZIP archive"
        elif header.startswith(b"GRIB"):
            detected = "GRIB data"
        elif not header:
            detected = "an empty file"
        else:
            detected = f"an unknown payload (first bytes: {header!r})"
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"CDS did not return a readable NetCDF for {target.name}; received {detected}. "
            "The incomplete download was removed."
        ) from exc

    partial.replace(target)


def _retrieve_with_retries(client, request: Dict, target: Path, attempts: int = 3) -> None:
    """Retry one CDS retrieve. A single rejected year should not end the whole run."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _retrieve_netcdf(client, request, target)
            return
        except Exception as exc:
            last_error = exc
            target.unlink(missing_ok=True)
            print(f"CDS download failed for {target.name} ({attempt}/{attempts}): {exc}")
            if attempt < attempts:
                time.sleep(20)
    raise RuntimeError(f"CDS download failed for {target.name}") from last_error


def _download_spans(start_year: int, end_year: int, end_month: int):
    """Year ranges that can share one CDS request.

    CDS applies the month list to every selected year. A finished history can
    travel in one request. An unfinished final year needs its own request so
    the earlier years still include October through December.
    """
    if start_year > end_year:
        raise SystemExit(f"start year {start_year} is after end year {end_year}")
    if end_month == 12 or start_year == end_year:
        last_month = end_month if start_year == end_year else 12
        return [(start_year, end_year, last_month)]
    spans = []
    if start_year < end_year:
        spans.append((start_year, end_year - 1, 12))
    spans.append((end_year, end_year, end_month))
    return spans


def _span_path(out_dir: Path, kind: str, first_year: int, last_year: int) -> Path:
    if first_year == last_year:
        return out_dir / f"era5_{kind}_monthly_{first_year}.nc"
    return out_dir / f"era5_{kind}_monthly_{first_year}_{last_year}.nc"


def download_era5(
    out_dir: Path,
    start_year: int,
    end_year: int,
    grid: float = 1.0,
    overwrite: bool = False,
    end_month: int = 12,
):
    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit("Install cdsapi first: pip install cdsapi") from exc
    if not 1 <= int(end_month) <= 12:
        raise SystemExit(f"end month must be 1-12; got {end_month}")
    out_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    for first_year, last_year, last_month in _download_spans(start_year, end_year, end_month):
        months = [f"{month:02d}" for month in range(1, last_month + 1)]
        years = [str(year) for year in range(first_year, last_year + 1)]
        target = _span_path(out_dir, "moisture", first_year, last_year)
        precip_target = _span_path(out_dir, "precip", first_year, last_year)
        label = f"{first_year}" if first_year == last_year else f"{first_year}-{last_year}"
        moisture_has_tp = False

        if target.exists() and not overwrite:
            with xr.open_dataset(target) as existing:
                moisture_has_tp = any(name in existing.data_vars for name in ALIASES["tp"])
            print(f"skip {target.name}")
        else:
            moisture_request = {
                "product_type": ["monthly_averaged_reanalysis"],
                "variable": MOISTURE_VARIABLES,
                "year": years,
                "month": months,
                "time": ["00:00"],
                "data_format": "netcdf",
                "download_format": "unarchived",
                "grid": [grid, grid],
            }
            print(f"requesting moisture {label} months {months[0]}-{months[-1]} -> {target.name}")
            _retrieve_with_retries(client, moisture_request, target)

        # Precipitation uses a different ERA5 step type, so request it in a
        # separate NetCDF. Combining it with TCW/IVT can make CDS return ZIP
        # content even when the destination filename ends in .nc.
        if moisture_has_tp and not overwrite:
            continue
        if precip_target.exists() and not overwrite:
            print(f"skip {precip_target.name}")
            continue

        precip_request = {
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": ["total_precipitation"],
            "year": years,
            "month": months,
            "time": ["00:00"],
            "data_format": "netcdf",
            "download_format": "unarchived",
            "grid": [grid, grid],
        }
        print(f"requesting precipitation {label} months {months[0]}-{months[-1]} -> {precip_target.name}")
        _retrieve_with_retries(client, precip_request, precip_target)


def assert_expected_month(fields: xr.Dataset, expect: str) -> None:
    """Stop with exit 75 when the series does not end on the requested month."""
    latest = pd.Timestamp(fields.time.values[-1])
    wanted = pd.Timestamp(f"{expect}-01")
    if (latest.year, latest.month) != (wanted.year, wanted.month):
        from lib.release_wait import exit_not_ready

        exit_not_ready(f"ERA5 moisture ends at {latest:%Y-%m}, which is not {wanted:%Y-%m}.")


def area_weighted_mean(da: xr.DataArray) -> xr.DataArray:
    """Cosine-latitude weighted global mean.

    This is used for every global ranking, trace, and stripe calculation so
    high-latitude grid cells do not receive the same weight as tropical cells.
    """
    weights = np.cos(np.deg2rad(da.latitude))
    return da.weighted(weights).mean(("latitude", "longitude"))


def _ap_span(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """AP month range. Same-year ranges keep one year; cross-year ranges keep both."""
    left = MONTH_LABELS[start.month - 1]
    right = MONTH_LABELS[end.month - 1]
    if start.year == end.year:
        return f"{left}-{right} {end.year}"
    return f"{left} {start.year}-{right} {end.year}"


def basis_cube(da: xr.DataArray, basis: str, latest: pd.Timestamp) -> Tuple[xr.DataArray, str]:
    month = latest.month
    if basis == "month":
        cube = da.where(da.time.dt.month == month, drop=True)
        label = f"{MONTH_LABELS[month - 1]} {latest.year}"
    elif basis == "3m":
        roll = da.rolling(time=3, min_periods=3).mean()
        cube = roll.where(roll.time.dt.month == month, drop=True)
        start = latest - pd.DateOffset(months=2)
        label = _ap_span(pd.Timestamp(start), latest)
    elif basis == "12m":
        roll = da.rolling(time=12, min_periods=12).mean()
        cube = roll.where(roll.time.dt.month == month, drop=True)
        if cube.sizes.get("time", 0) == 0:
            raise ValueError("No complete rolling 12-month windows")
        start = latest - pd.DateOffset(months=11)
        label = _ap_span(pd.Timestamp(start), latest)
    else:
        raise ValueError(basis)
    return cube, label


def baseline_mean(cube: xr.DataArray, start: int = BASELINE_START, end: int = BASELINE_END) -> xr.DataArray:
    """Like-for-like 1991–2020 climatology for a basis cube."""
    years = cube.time.dt.year
    baseline = cube.where((years >= start) & (years <= end), drop=True)
    if baseline.sizes.get("time", 0) == 0:
        raise ValueError(f"No baseline data available for {start}–{end}")
    return baseline.mean("time")


def spatial_percent_anomaly(cube: xr.DataArray, start: int = BASELINE_START, end: int = BASELINE_END) -> xr.DataArray:
    """Current field as percent above/below its like-for-like baseline mean."""
    current = cube.isel(time=-1)
    clim = baseline_mean(cube, start, end)
    safe = clim.where(np.abs(clim) > 1e-6)
    return (100.0 * (current - clim) / safe).astype("float32")


def spatial_decile(cube: xr.DataArray) -> xr.DataArray:
    """Local historical decile for the current like-for-like window.

    Decile 1 is the driest/lowest 10% of the local historical distribution and
    decile 10 is the wettest/highest 10%. Because this is rank based, TCW and
    IVT, and month/3-month/rolling-12-month windows, all share the same standardized scale.
    """
    current = cube.isel(time=-1)
    less = (cube < current).sum("time")
    equal = (cube == current).sum("time")
    percentile = 100.0 * (less + 0.5 * equal) / cube.sizes["time"]
    return xr.apply_ufunc(np.ceil, percentile / 10.0).clip(1, 10).astype("int8")


def spatial_record_masks(cube: xr.DataArray) -> Tuple[xr.DataArray, xr.DataArray]:
    """Return strict wet/high and dry/low record masks versus all prior years."""
    if cube.sizes.get("time", 0) < 2:
        shape = cube.isel(time=-1)
        false = xr.zeros_like(shape, dtype=bool)
        return false, false
    current = cube.isel(time=-1)
    history = cube.isel(time=slice(None, -1))
    wet_record = current > history.max("time")
    dry_record = current < history.min("time")
    return wet_record, dry_record


def global_percent_anomaly_series(cube: xr.DataArray, start: int = BASELINE_START, end: int = BASELINE_END) -> pd.Series:
    """Area-weighted like-for-like global percent anomaly time series."""
    s = area_weighted_mean(cube).to_series().dropna()
    baseline = s[(s.index.year >= start) & (s.index.year <= end)]
    if baseline.empty:
        raise ValueError(f"No global baseline data available for {start}–{end}")
    clim = float(baseline.mean())
    return 100.0 * (s - clim) / clim

def global_rank(cube: xr.DataArray) -> Dict:
    s = area_weighted_mean(cube).to_series().dropna()
    current_value = float(s.iloc[-1])
    ordered = s.sort_values(ascending=False)
    rank = int(np.where(ordered.index == s.index[-1])[0][0] + 1)
    n = len(s)
    percentile = 100.0 * (n - rank + 0.5) / n
    top = [(int(idx.year), float(val)) for idx, val in ordered.iloc[:5].items()]
    return {
        "value": current_value,
        "rank": rank,
        "n": n,
        "percentile": percentile,
        "year": int(s.index[-1].year),
        "top": top,
        "series": s,
    }


def monthly_percent_anomaly_series(da: xr.DataArray, start: int = BASELINE_START, end: int = BASELINE_END) -> pd.Series:
    """Global monthly percent anomalies relative to calendar-month 1991–2020 means."""
    s = area_weighted_mean(da).to_series().dropna()
    baseline = s[(s.index.year >= start) & (s.index.year <= end)]
    if baseline.empty:
        raise ValueError(f"No monthly baseline data available for {start}–{end}")
    monthly_clim = baseline.groupby(baseline.index.month).mean()
    clim = np.asarray([monthly_clim.loc[m] for m in s.index.month], dtype=float)
    return pd.Series(100.0 * (s.values - clim) / clim, index=s.index)


def annual_stripe_series(da: xr.DataArray) -> pd.Series:
    """Annual mean of monthly global percent anomalies."""
    pct = monthly_percent_anomaly_series(da)
    return pct.groupby(pct.index.year).mean()


def annual_decile_series(
    da: xr.DataArray,
    latest_month: int,
    accumulation: bool = False,
) -> pd.Series:
    """Like-for-like annual/YTD deciles of a latitude-weighted global series.

    Every year uses January through the latest available calendar month so the
    current partial year is compared with the same months in history. For
    accumulated quantities such as total precipitation, monthly ERA5 values
    are weighted by the number of days in each month before summing.
    """
    monthly_global = area_weighted_mean(da).to_series().dropna()
    monthly_global = monthly_global[monthly_global.index.month <= latest_month]

    if accumulation:
        days = monthly_global.index.days_in_month.to_numpy(dtype=float)
        annual = pd.Series(
            monthly_global.to_numpy(dtype=float) * days,
            index=monthly_global.index,
        ).groupby(monthly_global.index.year).sum().dropna()
    else:
        annual = monthly_global.groupby(monthly_global.index.year).mean().dropna()

    ranks = annual.rank(method="average", pct=True)
    deciles = np.ceil(ranks * 10.0).clip(1, 10).astype(int)
    return pd.Series(deciles.values, index=annual.index)

def _theme(mode: str):
    if mode == "light":
        return dict(bg="#f4f5f7", panel="#ffffff", fg="#111418", muted="#5c656e", grid="#d8dde0", cyan="#007d91", magenta="#9a2c79", accent="#176c55")
    return dict(bg="#000000", panel="#000000", fg="#ffffff", muted="#c5c9ce", grid="#2a2e33", cyan="#d9ddda", magenta="#d9ddda", accent="#ffffff")


def _glass(ax, c):
    ax.set_facecolor(c["panel"])
    for spine in ax.spines.values():
        spine.set_visible(False)


def _sparkline(ax, series: pd.Series, color: str, c, label: str):
    years = np.asarray([x.year for x in series.index])
    values = series.values.astype(float)

    # Neutral trace with directional fill: green above zero, brown below zero.
    line_color = "#d9ddda" if c["bg"] != "#f7f8f7" else "#343a3d"
    pos_fill = "#4f9c61"
    neg_fill = "#aa7943"

    ax.axhline(0, color=c["muted"], lw=0.50, alpha=0.52, zorder=1)
    ax.fill_between(years, 0, values, where=values >= 0, interpolate=True,
                    color=pos_fill, alpha=0.72, linewidth=0, zorder=1.5)
    ax.fill_between(years, 0, values, where=values < 0, interpolate=True,
                    color=neg_fill, alpha=0.72, linewidth=0, zorder=1.5)
    ax.plot(years, values, lw=1.05, color=line_color, zorder=3)
    ax.scatter(years[-1], values[-1], s=13, color=line_color, zorder=4)

    # Leave a right gutter for the current-value callout and extra vertical
    # breathing room so the trace never collides with the year labels.
    x_extra = max(3.0, 0.05 * (years.max() - years.min()))
    ax.set_xlim(years.min(), years.max() + x_extra)
    raw_range = max(np.nanmax(values) - np.nanmin(values), 1.0)
    pad = max(np.nanstd(values) * 0.75, raw_range * 0.15, 1.25)
    ax.set_ylim(np.nanmin(values) - pad, np.nanmax(values) + pad)
    ax.set_xticks([]); ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor("none")

    ax.text(0.00, 0.96, label, transform=ax.transAxes, ha="left", va="top",
            fontsize=8.0, color=c["muted"])

    y0 = values[-1]
    yrange = max(ax.get_ylim()[1] - ax.get_ylim()[0], 1e-6)
    offset = -0.10 * yrange if y0 >= 0 else 0.10 * yrange
    ax.annotate(
        f"{y0:+.1f}%",
        xy=(years[-1], y0),
        xytext=(years[-1] + 0.68 * x_extra, y0 + offset),
        ha="left", va="center", fontsize=8.2, color=line_color, fontweight="bold",
        arrowprops=dict(arrowstyle="-", color=line_color, lw=0.5, alpha=0.85),
        annotation_clip=False, zorder=5,
    )

    # Put years below the plotting region rather than inside it.
    ax.text(0.00, -0.10, str(years.min()), transform=ax.transAxes, ha="left", va="top",
            fontsize=6.8, color=c["muted"], clip_on=False)
    ax.text(0.955, -0.10, str(years.max()), transform=ax.transAxes, ha="right", va="top",
            fontsize=6.8, color=c["muted"], clip_on=False)


def _rank_block(ax, metric: str, rank: Dict, pct_anom: float, color: str, c, y: float):
    """Compact rank block with deliberately separated text zones."""
    ax.text(0.05, y + 0.095, metric, fontsize=8.6, fontweight="bold", color=c["fg"], va="center")

    # Rank is isolated in the left half; sample size sits below it rather than
    # on the same baseline, which prevents #29/#31/#52 from colliding with "of N".
    ax.text(0.05, y + 0.012, f"#{rank['rank']}", fontsize=18.5, fontweight="bold",
            color=c["fg"], va="center", ha="left")
    ax.text(0.055, y - 0.058, f"of {rank['n']} years", fontsize=6.5,
            color=c["muted"], va="center", ha="left")

    # Put percentile and anomaly in a right-aligned information column.
    ordinal = int(round(rank["percentile"]))
    suffix = "th" if 10 <= ordinal % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(ordinal % 10, "th")
    ax.text(0.95, y + 0.052, f"{ordinal}{suffix} percentile", fontsize=8.3, color=c["fg"],
            fontweight="bold", va="center", ha="right")
    ax.text(0.95, y - 0.015, f"{pct_anom:+.1f}% vs 1991-2020", fontsize=6.7,
            color=c["fg"], va="center", ha="right")

    leaders = " · ".join(str(yr) for yr, _ in rank["top"][:3])
    ax.text(0.05, y - 0.125, f"Top years  {leaders}", fontsize=6.1,
            color=c["muted"], va="center", ha="left")

def _draw_decile_stripe(ax, series: pd.Series, cmap, norm, c, show_years: bool = False):
    vals = np.asarray(series.values, dtype=float)
    years = np.asarray(series.index, dtype=int)
    ax.imshow(vals[np.newaxis, :], aspect="auto", interpolation="nearest", cmap=cmap, norm=norm,
              extent=[years.min() - 0.5, years.max() + 0.5, 0, 1])
    ax.set_yticks([])
    ax.set_xlim(years.min() - 0.5, years.max() + 0.5)
    ticks = [y for y in [1940, 1960, 1980, 2000, 2020, years.max()] if years.min() <= y <= years.max()]
    ax.set_xticks(sorted(set(ticks)))
    if show_years:
        ax.tick_params(axis="x", labelsize=8.3, length=0, colors=c["muted"], pad=3)
    else:
        ax.tick_params(axis="x", labelbottom=False, length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)

def render_dashboard(fields: xr.Dataset, output: Path, mode: str = "dark", dpi: int = 300):
    latest = pd.Timestamp(fields.time.values[-1])
    c = _theme(mode)
    plt.rcParams.update({
        "font.family": "Libre Franklin",
        "axes.labelcolor": c["muted"],
        "xtick.color": c["muted"],
        "ytick.color": c["muted"],
        "text.color": c["fg"],
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
    })

    # A single rank-based map scale works for TCW, IVT, monthly, 3-month and rolling-12-month.
    # D1 = driest/lowest 10%; D10 = wettest/highest 10%.
    # Shared decile palette. D4-D6 are intentionally neutral/blank so
    # near-normal areas recede and the tails carry the visual story.
    decile_colors = [
        "#8b5d2e", "#aa7943", "#c89b62",  # D1-D3 dry/low: tan
        "#f7f7f5", "#f7f7f5", "#f7f7f5",  # D4-D6 neutral
        "#b9d9a7", "#86bf7a", "#4f9c61", "#216e3f",  # D7-D10 wet/high: green
    ]
    decile_cmap = ListedColormap(decile_colors, name="moisture_deciles")
    decile_bounds = np.arange(0.5, 11.5, 1.0)
    decile_norm = BoundaryNorm(decile_bounds, decile_cmap.N, clip=True)


    fig = plt.figure(figsize=(20, 13.333333), dpi=dpi, facecolor=c["bg"])
    gs = GridSpec(
        5, 5, figure=fig,
        height_ratios=[0.25, 1, 1, 1, 0.72],
        width_ratios=[1, 1, 0.072, 0.48, 0.60],
        left=0.055, right=0.985, top=0.965, bottom=0.052,
        hspace=0.28, wspace=0.075,
    )

    header = fig.add_subplot(gs[0, :]); header.axis("off")
    title_date = f"{MONTH_LABELS[latest.month - 1]} {latest.year}"
    header.text(0.000, 0.74, "ERA5 planetary moisture monitor", fontsize=26, fontweight="bold", color=c["fg"], va="center")
    header.text(0.995, 0.74, title_date, fontsize=26, fontweight="bold", color=c["fg"], va="center", ha="right")
    header.text(0.000, 0.18, "Total column water and integrated vapor transport",
                fontsize=13.0, color=c["muted"], va="center")

    basis_names = [("month", "Month"), ("3m", "Trailing 3 months"), ("12m", "Rolling 12 months")]
    lon, lat = fields.longitude.values, fields.latitude.values

    prepared = []
    for basis, basis_title in basis_names:
        tcw_cube, period_label = basis_cube(fields.tcw, basis, latest)
        ivt_cube, _ = basis_cube(fields.ivt, basis, latest)
        prepared.append((basis, basis_title, period_label, tcw_cube, ivt_cube))

    # One shared vertical legend, positioned between the maps and statistics.
    legend_ax = fig.add_subplot(gs[1:4, 2])
    legend_ax.set_facecolor(c["bg"])
    for spine in legend_ax.spines.values():
        spine.set_visible(False)
    sm = plt.cm.ScalarMappable(norm=decile_norm, cmap=decile_cmap)
    cbar = fig.colorbar(
        sm, cax=legend_ax, orientation="vertical", boundaries=decile_bounds,
        ticks=[], spacing="uniform"
    )
    # Do not use colorbar ticks at all: draw decile labels manually so there
    # are no tick marks/dashes for Matplotlib to render.
    cbar.ax.set_yticks([])
    cbar.ax.tick_params(axis="y", which="both", left=False, right=False,
                        labelleft=False, labelright=False, length=0, width=0)
    cbar.outline.set_visible(False)
    for decile_i in range(1, 11):
        y = (decile_i - 0.5) / 10.0
        legend_ax.text(-0.08, y, f"{decile_i}", transform=legend_ax.transAxes,
                       fontsize=9.5, color=c["fg"], ha="right", va="center",
                       clip_on=False)

    for row, (_, basis_title, period_label, tcw_cube, ivt_cube) in enumerate(prepared, start=1):
        tcw_rank, ivt_rank = global_rank(tcw_cube), global_rank(ivt_cube)
        tcw_series = global_percent_anomaly_series(tcw_cube)
        ivt_series = global_percent_anomaly_series(ivt_cube)

        pairs = [(tcw_cube, "TCW"), (ivt_cube, "IVT")]
        for col, (cube, name) in enumerate(pairs):
            decile = spatial_decile(cube)
            wet_record, dry_record = spatial_record_masks(cube)

            ax = fig.add_subplot(gs[row, col], projection=ccrs.PlateCarree())
            ax.set_facecolor(c["panel"])
            ax.pcolormesh(
                lon, lat, decile.values, shading="auto", cmap=decile_cmap, norm=decile_norm,
                transform=ccrs.PlateCarree(), rasterized=True, zorder=1
            )
            ax.set_global()

            # Strong coastlines + borders keep land masses legible over every decile color.
            ax.coastlines(resolution="50m", color=c["bg"], linewidth=1.15, alpha=0.95, zorder=6)
            ax.coastlines(resolution="50m", color=c["fg"], linewidth=0.52, alpha=0.96, zorder=7)
            ax.add_feature(cfeature.BORDERS.with_scale("50m"), edgecolor=c["fg"], linewidth=0.22, alpha=0.44, zorder=7)
            ax.add_feature(cfeature.LAKES.with_scale("50m"), facecolor="none", edgecolor=c["fg"], linewidth=0.20, alpha=0.42, zorder=7)

            # Strict record-breakers versus all prior like-for-like years.
            # Use sparse stippling so record areas read immediately without outlining
            # every noisy grid-cell boundary.
            lon2d, lat2d = np.meshgrid(lon, lat)
            stride = 2
            wet_mask = wet_record.values[::stride, ::stride]
            dry_mask = dry_record.values[::stride, ::stride]
            if np.any(wet_mask):
                ax.scatter(
                    lon2d[::stride, ::stride][wet_mask], lat2d[::stride, ::stride][wet_mask],
                    s=4.0, marker=".", color="#ffe66d", alpha=0.92, linewidths=0,
                    transform=ccrs.PlateCarree(), zorder=9
                )
            if np.any(dry_mask):
                ax.scatter(
                    lon2d[::stride, ::stride][dry_mask], lat2d[::stride, ::stride][dry_mask],
                    s=4.0, marker=".", color="#72ddf7", alpha=0.92, linewidths=0,
                    transform=ccrs.PlateCarree(), zorder=9
                )

            ax.set_title(f"{basis_title} · {name} local decile", fontsize=11, loc="left", pad=6, fontweight="bold", color=c["fg"])
            # Show the period once per row, in the gutter left of the first map.
            if col == 0:
                ax.text(-0.018, 0.965, period_label, transform=ax.transAxes,
                        ha="right", va="top", fontsize=11, color=c["fg"],
                        fontweight="bold", zorder=12, clip_on=False)

        rank_ax = fig.add_subplot(gs[row, 3]); _glass(rank_ax, c)
        rank_ax.set_xticks([]); rank_ax.set_yticks([]); rank_ax.set_xlim(0, 1); rank_ax.set_ylim(0, 1)
        rank_ax.text(0.045, 0.94, "Global rank", fontsize=11, fontweight="bold", color=c["fg"])
        _rank_block(rank_ax, "TCW", tcw_rank, float(tcw_series.iloc[-1]), c["cyan"], c, 0.69)
        _rank_block(rank_ax, "IVT", ivt_rank, float(ivt_series.iloc[-1]), c["magenta"], c, 0.27)

        spark_panel = fig.add_subplot(gs[row, 4]); _glass(spark_panel, c)
        spark_panel.set_xticks([]); spark_panel.set_yticks([])
        spark_panel.text(0.04, 0.94, "Historical trace", fontsize=11, fontweight="bold", color=c["fg"], transform=spark_panel.transAxes)
        ax1 = spark_panel.inset_axes([0.04, 0.53, 0.92, 0.31])
        ax2 = spark_panel.inset_axes([0.04, 0.10, 0.92, 0.31])
        _sparkline(ax1, tcw_series, c["cyan"], c, "TCW")
        _sparkline(ax2, ivt_series, c["magenta"], c, "IVT")

    # Record legend sits directly below the lower-left map and shares that
    # panel's left edge. Typography matches the postage-map titles.
    map_left = fig.add_subplot(gs[3, 0])
    map_pos = map_left.get_position()
    fig.delaxes(map_left)
    record_legend_ax = fig.add_axes([
        map_pos.x0 + 0.004,  # slight right nudge while staying aligned to first-column map
        map_pos.y0 - 0.034,
        map_pos.width * 0.94,
        0.028,
    ])
    record_legend_ax.axis("off")
    record_legend_ax.legend(
        handles=[
            Line2D([0], [0], marker=".", linestyle="None", markersize=8.0,
                   color="#ffe66d", label="Record high"),
            Line2D([0], [0], marker=".", linestyle="None", markersize=8.0,
                   color="#72ddf7", label="Record low"),
        ],
        loc="upper left", ncol=2, frameon=False, fontsize=9.5,
        labelcolor=c["fg"], handlelength=0.8, columnspacing=1.8, borderaxespad=0,
    )

    stripe_panel = fig.add_subplot(gs[4, :]); _glass(stripe_panel, c)
    stripe_panel.set_facecolor(c["bg"])
    stripe_panel.set_xticks([]); stripe_panel.set_yticks([])
    stripe_panel.text(0.012, 0.88, "Planetary moisture stripes", fontsize=14, fontweight="bold", color=c["fg"], transform=stripe_panel.transAxes)
    # Use the same January-through-latest-month window for every historical year.
    # That keeps the current partial year directly comparable with all prior years.
    tcw_stripes = annual_decile_series(fields.tcw, latest.month)
    ivt_stripes = annual_decile_series(fields.ivt, latest.month)
    precip_stripes = annual_decile_series(fields.tp, latest.month, accumulation=True)

    stripe_panel.text(0.012, 0.56, "TCW", fontsize=9.5, fontweight="bold", color=c["fg"],
                      transform=stripe_panel.transAxes, ha="left", va="center")
    stripe_panel.text(0.012, 0.34, "IVT", fontsize=9.5, fontweight="bold", color=c["fg"],
                      transform=stripe_panel.transAxes, ha="left", va="center")
    stripe_panel.text(0.012, 0.12, "Precip.", fontsize=9.5, fontweight="bold", color=c["fg"],
                      transform=stripe_panel.transAxes, ha="left", va="center")

    ax_t = stripe_panel.inset_axes([0.065, 0.50, 0.923, 0.14])
    ax_i = stripe_panel.inset_axes([0.065, 0.28, 0.923, 0.14])
    ax_p = stripe_panel.inset_axes([0.065, 0.06, 0.923, 0.14])
    _draw_decile_stripe(ax_t, tcw_stripes, decile_cmap, decile_norm, c, show_years=False)
    _draw_decile_stripe(ax_i, ivt_stripes, decile_cmap, decile_norm, c, show_years=False)
    _draw_decile_stripe(ax_p, precip_stripes, decile_cmap, decile_norm, c, show_years=True)

    fig.text(0.055, 0.014, "@BenNollWeather", fontsize=14, color=c["fg"], ha="left", fontweight="bold")
    fig.text(0.985, 0.014, "Data: ERA5", fontsize=14, color=c["fg"], ha="right", fontweight="bold")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.14)
    plt.close(fig)
    print(f"Saved: {output}")

def upload_dashboard(output: Path, aws_bin: str, aws_profile: str, bucket: str, prefix: str) -> str:
    resolved = shutil.which(aws_bin) if not os.path.isabs(aws_bin) else (aws_bin if Path(aws_bin).exists() else None)
    if not resolved:
        raise SystemExit(f"AWS CLI not found: {aws_bin}")
    s3_uri = f"s3://{bucket}/{prefix}/{output.name}"
    env = os.environ.copy()
    if aws_profile:
        env["AWS_PROFILE"] = aws_profile
    elif not env.get("AWS_PROFILE"):
        env.pop("AWS_PROFILE", None)
    for name in ("REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "AWS_CA_BUNDLE"):
        if not env.get(name):
            env.pop(name, None)
    cmd = [resolved, "s3", "cp", str(output), s3_uri, "--content-type", "image/png"]
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        print("AWS upload failed:")
        print(result.stderr)
        raise SystemExit(result.returncode)
    url = f"https://{bucket}.s3.amazonaws.com/{prefix}/{output.name}"
    print(f"Uploaded: {s3_uri}")
    print(f"Public URL: {url}")
    return url


def synthetic_dataset(start=1940, end=2026, latest_month=7, seed=7) -> xr.Dataset:
    """Low-resolution deterministic data for visualization smoke tests only."""
    rng = np.random.default_rng(seed)
    times = pd.date_range(f"{start}-01-01", f"{end}-{latest_month:02d}-01", freq="MS")
    lat = np.linspace(87.5, -87.5, 36)
    lon = np.linspace(-177.5, 177.5, 72)
    lon2, lat2 = np.meshgrid(lon, lat)
    tcw = np.empty((len(times), len(lat), len(lon)), dtype=np.float32)
    ivt = np.empty_like(tcw)
    tp = np.empty_like(tcw)
    for i, t in enumerate(times):
        season = np.sin(2 * np.pi * (t.month - 1) / 12)
        trend = (t.year - start) / (end - start + 1)
        # A slow cycle keeps the global trace from reading as a straight wedge.
        cycle = np.sin(2 * np.pi * (t.year - start) / 17.0)
        year_jitter = float(rng.normal(0, 0.55))
        trop = np.exp(-(lat2 / 34) ** 2)
        wave = np.sin(np.deg2rad(lon2 * 1.6 + t.month * 12)) * np.cos(np.deg2rad(lat2))
        # Opposite basins drift apart, so the latest map shows dry, neutral, and wet deciles.
        basin = np.sin(np.deg2rad(lon2 * 0.9)) * np.cos(np.deg2rad(lat2 * 0.7))
        tcw[i] = (
            16 + 20 * trop + 2.5 * season * np.sin(np.deg2rad(lat2)) + 1.6 * wave
            + 0.6 * trend + 2.2 * cycle + year_jitter + 6.0 * basin * trend
            + rng.normal(0, 0.45, lat2.shape)
        )
        storm = np.exp(-((np.abs(lat2) - 42) / 18) ** 2)
        ivt[i] = (
            80 + 140 * storm + 60 * trop + 20 * wave
            + 8 * trend + 22 * cycle + year_jitter * 8 + 55 * basin * trend
            + rng.normal(0, 4.0, lat2.shape)
        )
        # Synthetic precipitation is in arbitrary positive units; only ranks are
        # used in the smoke-test stripe.
        tp[i] = np.clip(
            0.002 + 0.004 * trop + 0.0012 * wave + 0.0006 * season
            + 0.0004 * cycle + 0.0015 * basin * trend
            + rng.normal(0, 0.00025, lat2.shape),
            0,
            None,
        )
    return xr.Dataset(
        {
            "tcw": (("time", "latitude", "longitude"), tcw),
            "ivt": (("time", "latitude", "longitude"), ivt),
            "tp": (("time", "latitude", "longitude"), tp),
        },
        coords={"time": times, "latitude": lat, "longitude": lon},
    )


def main():
    ap = argparse.ArgumentParser(description="ERA5 planetary moisture monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("download", help="Download yearly ERA5 monthly files via CDS API")
    d.add_argument("--out-dir", default="data/raw")
    d.add_argument("--start-year", type=int, default=1940)
    d.add_argument("--end-year", type=int, default=pd.Timestamp.now("UTC").year)
    d.add_argument("--end-month", type=int, default=12)
    d.add_argument("--grid", type=float, default=1.0)
    d.add_argument("--overwrite", action="store_true")

    b = sub.add_parser("build", help="Build ONE dashboard PNG from downloaded NetCDF files")
    b.add_argument("--input", default="data/raw/era5_moisture_monthly_*.nc")
    b.add_argument("--output", default="output/era5_moisture_monitor.png")
    b.add_argument("--mode", choices=["dark", "light"], default="dark")
    b.add_argument("--dpi", type=int, default=300)
    b.add_argument("--expect-month", default="", help="YYYY-MM the series must end on")

    u = sub.add_parser("upload", help="Upload the dashboard to the PWAT atmospheric_moisture S3 location")
    u.add_argument("--output", default="output/era5_moisture_monitor.png")
    u.add_argument("--aws-bin", default="aws")
    u.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""))
    u.add_argument("--bucket", default="bennollweather")
    u.add_argument("--prefix", default="atmospheric_moisture")

    s = sub.add_parser("smoke-test", help="Generate a deterministic synthetic demo image")
    s.add_argument("--output", default="output/era5_moisture_monitor_demo.png")
    s.add_argument("--mode", choices=["dark", "light"], default="dark")
    s.add_argument("--dpi", type=int, default=160)

    args = ap.parse_args()
    if args.cmd == "download":
        download_era5(
            Path(args.out_dir), args.start_year, args.end_year, args.grid, args.overwrite, args.end_month
        )
    elif args.cmd == "build":
        fields = extract_fields(open_era5(args.input))
        validate_ivt(fields)
        if args.expect_month:
            assert_expected_month(fields, args.expect_month)
        render_dashboard(fields, Path(args.output), args.mode, args.dpi)
    elif args.cmd == "upload":
        upload_dashboard(Path(args.output), args.aws_bin, args.aws_profile, args.bucket, args.prefix)
    else:
        render_dashboard(synthetic_dataset(), Path(args.output), args.mode, args.dpi)


if __name__ == "__main__":
    main()
