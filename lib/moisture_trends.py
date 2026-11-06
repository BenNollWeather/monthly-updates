#!/usr/bin/env python3
"""Annual precipitable water and vapor transport for one place.

Two CDS downloads, and no precipitation. The first request is every month of
total column water from 1940 through the last finished year. The second is
every month of the eastward and northward vapor-flux components. Integrated
vapor transport is the annual mean of the monthly magnitudes, sqrt(u^2 + v^2).

The page stores a 1° grid. Each cell is the annual mean. The browser opens on
the global average, weighted by the area of each latitude band, and a search
replaces that with one place. That global series is embedded in the page. The
grid is fetched only when someone looks up a place.
Charts show the percent difference from the 1991–2020 average there.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import struct
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.c3s_globes import _seo, _site_nav  # noqa: E402
from lib.release_wait import exit_not_ready  # noqa: E402

DATASET = "reanalysis-era5-single-levels-monthly-means"
START_YEAR = 1940
PWAT_VARIABLE = "total_column_water"
FLUX_VARIABLES = (
    "vertical_integral_of_eastward_water_vapour_flux",
    "vertical_integral_of_northward_water_vapour_flux",
)
GROUPS = (
    ("pwat", (PWAT_VARIABLE,)),
    ("flux", FLUX_VARIABLES),
)
MAGIC = b"MTR1"
MISSING = 65535
INCHES_PER_KG_M2 = 1.0 / 25.4
TARGET_LAT = np.array([90 - i for i in range(181)], dtype=float)
TARGET_LON = np.arange(360, dtype=float)


def end_year(today: date) -> int:
    """The previous calendar year, which has all twelve months."""
    return today.year - 1


def _request(variables, years, months, grid: float) -> dict:
    return {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": list(variables),
        "year": [str(year) for year in years],
        "month": [str(month) for month in months],
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "grid": [float(grid), float(grid)],
    }


def build_requests(start: int, end: int, grid: float = 1.0) -> list[dict]:
    """One full-span precipitable-water request, then one full-span flux request."""
    if start > end:
        raise ValueError(f"start year {start} is after end year {end}")
    months = [f"{month:02d}" for month in range(1, 13)]
    years = [str(year) for year in range(start, end + 1)]
    return [_request(variables, years, months, grid) for _, variables in GROUPS]


def _request_too_large(exc: BaseException) -> bool:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current).lower()
        if "too large" in text or "cost limits exceeded" in text:
            return True
        current = current.__cause__ or current.__context__
    return False


def _retrieve_netcdf(client, request: dict, target: Path) -> None:
    partial = target.with_name(f"{target.name}.part")
    partial.unlink(missing_ok=True)
    client.retrieve(DATASET, request, str(partial))
    try:
        with xr.open_dataset(partial) as downloaded:
            if not downloaded.data_vars:
                raise ValueError("the downloaded dataset contains no data variables")
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"CDS did not return a readable NetCDF for {target.name}") from exc
    partial.replace(target)


def _retrieve_with_retries(client, request: dict, target: Path, attempts: int = 3) -> None:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _retrieve_netcdf(client, request, target)
            return
        except Exception as exc:
            last_error = exc
            target.unlink(missing_ok=True)
            print(f"CDS download failed for {target.name} ({attempt}/{attempts}): {exc}", flush=True)
            if _request_too_large(exc):
                break
            if attempt < attempts:
                time.sleep(20)
    raise RuntimeError(f"CDS download failed for {target.name}") from last_error


def _combine_netcdf(parts: list[Path], target: Path) -> None:
    datasets = []
    try:
        for path in parts:
            dataset = xr.open_dataset(path)
            if "valid_time" in dataset.coords and "time" not in dataset.coords:
                dataset = dataset.rename({"valid_time": "time"})
            datasets.append(dataset)
        combined = xr.concat(datasets, dim="time").sortby("time")
        times = pd.to_datetime(combined.time.values)
        _, keep = np.unique(times, return_index=True)
        combined = combined.isel(time=np.sort(keep)).load()
        target.parent.mkdir(parents=True, exist_ok=True)
        combined.to_netcdf(target)
        combined.close()
    finally:
        for dataset in datasets:
            dataset.close()


def _download_or_split(client, variables, years, months, target: Path, grid: float, retrieve) -> None:
    """Retrieve one field group. Halve the years only when CDS rejects the span."""
    request = _request(variables, years, months, grid)
    label = f"{years[0]}" if years[0] == years[-1] else f"{years[0]}-{years[-1]}"
    print(
        f"requesting {', '.join(variables)} {label} months {months[0]}-{months[-1]} -> {target.name}",
        flush=True,
    )
    try:
        retrieve(client, request, target)
        return
    except Exception as exc:
        target.unlink(missing_ok=True)
        if not _request_too_large(exc) or len(years) < 2:
            raise
    print(f"CDS rejected {label} as too large; splitting that year range.", flush=True)
    midpoint = len(years) // 2
    scratch = target.parent / f".{target.stem}"
    scratch.mkdir(parents=True, exist_ok=True)
    left = scratch / f"{years[0]}_{years[midpoint - 1]}.nc"
    right = scratch / f"{years[midpoint]}_{years[-1]}.nc"
    try:
        _download_or_split(client, variables, years[:midpoint], months, left, grid, retrieve)
        _download_or_split(client, variables, years[midpoint:], months, right, grid, retrieve)
        _combine_netcdf([left, right], target)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def download_groups(client, dest: Path, start: int, end: int, grid: float = 1.0, retrieve=None) -> dict[str, Path]:
    """Download precipitable water, then the vapor-flux pair. No precipitation."""
    retrieve = retrieve or _retrieve_with_retries
    months = [f"{month:02d}" for month in range(1, 13)]
    years = list(range(start, end + 1))
    dest.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for kind, variables in GROUPS:
        target = dest / f"era5_{kind}_monthly_{start}_{end}.nc"
        target.unlink(missing_ok=True)
        _download_or_split(client, variables, years, months, target, grid, retrieve)
        paths[kind] = target
    return paths


def _find(dataset: xr.Dataset, names: tuple[str, ...]) -> xr.DataArray:
    for name in names:
        if name in dataset.data_vars:
            return dataset[name]
    lower = {name.lower(): name for name in dataset.data_vars}
    for name in names:
        if name.lower() in lower:
            return dataset[lower[name.lower()]]
    raise KeyError(f"Could not find any of {names}; found {list(dataset.data_vars)}")


def _normalize(field: xr.DataArray) -> xr.DataArray:
    if "valid_time" in field.dims or "valid_time" in field.coords:
        field = field.rename({"valid_time": "time"})
    renames = {}
    if "lat" in field.dims:
        renames["lat"] = "latitude"
    if "lon" in field.dims:
        renames["lon"] = "longitude"
    if renames:
        field = field.rename(renames)
    if "expver" in field.dims:
        merged = None
        for value in field.expver.values:
            piece = field.sel(expver=value, drop=True)
            merged = piece if merged is None else merged.combine_first(piece)
        field = merged
    for dim in list(field.dims):
        if dim not in {"time", "latitude", "longitude"} and field.sizes.get(dim) == 1:
            field = field.squeeze(dim, drop=True)
    extra = set(field.dims) - {"time", "latitude", "longitude"}
    if extra:
        raise ValueError(f"Unexpected moisture dimensions: {sorted(extra)}")
    longitude = np.mod(np.asarray(field.longitude.values, dtype=float), 360.0)
    longitude = np.where(np.isclose(longitude, 360.0), 0.0, longitude)
    field = field.assign_coords(
        longitude=np.round(longitude, 6),
        latitude=np.round(np.asarray(field.latitude.values, dtype=float), 6),
    )
    field = field.sortby("latitude").sortby("longitude")
    _, keep = np.unique(np.asarray(field.longitude.values, dtype=float), return_index=True)
    if len(keep) != field.sizes["longitude"]:
        field = field.isel(longitude=np.sort(keep))
    return field


def _monthly(field: xr.DataArray) -> xr.DataArray:
    field = _normalize(field)
    stamps = pd.to_datetime(np.asarray(field.time.values)).to_period("M").to_timestamp()
    field = field.assign_coords(time=stamps)
    if pd.DatetimeIndex(field.time.values).duplicated().any():
        field = field.groupby("time").mean(skipna=True)
    return field


def _on_grid(field: xr.DataArray) -> xr.DataArray:
    return field.reindex(
        latitude=TARGET_LAT,
        longitude=TARGET_LON,
        method="nearest",
        tolerance=0.51,
    )


def _annual_mean(field: xr.DataArray, start: int, end: int) -> xr.DataArray:
    times = pd.DatetimeIndex(pd.to_datetime(np.asarray(field.time.values)))
    layers = []
    for year in range(start, end + 1):
        chosen = times.year == year
        have = {int(month) for month in times.month[chosen]}
        if have != set(range(1, 13)):
            missing = [f"{month:02d}" for month in range(1, 13) if month not in have]
            exit_not_ready(
                f"ERA5 moisture for {year} is missing month(s) {', '.join(missing)}. "
                "Moisture trends needs every month of the finished year."
            )
        layers.append(field.isel(time=np.flatnonzero(chosen)).mean("time", skipna=True))
    return xr.concat(layers, dim="year")


def annual_pair(pwat, east, north, start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
    """Annual inches of precipitable water, and the mean of the monthly IVT magnitudes."""
    pwat = _on_grid(_monthly(pwat))
    east = _on_grid(_monthly(east))
    north = _on_grid(_monthly(north))
    ivt = xr.apply_ufunc(np.hypot, east, north)
    inches = _annual_mean(pwat, start, end) * INCHES_PER_KG_M2
    transport = _annual_mean(ivt, start, end)
    return (
        np.asarray(inches.values, dtype=np.float64),
        np.asarray(transport.values, dtype=np.float64),
    )


def annual_fields(pwat_path: Path, flux_path: Path, start: int, end: int) -> tuple[np.ndarray, np.ndarray]:
    pwat_ds = xr.open_dataset(pwat_path)
    flux_ds = xr.open_dataset(flux_path)
    try:
        pwat = _find(pwat_ds, ("tcw", PWAT_VARIABLE)).load()
        east = _find(flux_ds, ("viwve", "p71.162", FLUX_VARIABLES[0])).load()
        north = _find(flux_ds, ("viwvn", "p72.162", FLUX_VARIABLES[1])).load()
    finally:
        pwat_ds.close()
        flux_ds.close()
    return annual_pair(pwat, east, north, start, end)


def _quantize(values: np.ndarray, scale: float) -> np.ndarray:
    scaled = np.rint(np.asarray(values, dtype=np.float64) * scale)
    out = np.full(values.shape, MISSING, dtype="<u2")
    ok = np.isfinite(values) & (scaled >= 0) & (scaled < MISSING)
    out[ok] = scaled[ok].astype(np.uint16)
    return out


def pack_grid(pwat: np.ndarray, ivt: np.ndarray, start: int, end: int) -> bytes:
    """Little-endian MTR1 record. PWAT is inches times 100. IVT is rounded kg/m/s."""
    if pwat.shape != ivt.shape or pwat.ndim != 3:
        raise ValueError("PWAT and IVT grids must match")
    nyear, nlat, nlon = pwat.shape
    if nyear != end - start + 1 or nlat != len(TARGET_LAT) or nlon != len(TARGET_LON):
        raise ValueError("Moisture grid must be one row per year on the 1 degree grid")
    header = struct.pack("<4sHHHH", MAGIC, int(start), int(end), int(nlat), int(nlon))
    return header + _quantize(pwat, 100.0).tobytes() + _quantize(ivt, 1.0).tobytes()


def global_series(pwat: np.ndarray, ivt: np.ndarray, start: int) -> dict:
    """Area-weighted annual means.

    Row 0 is 90°N, the same index the page uses. Each latitude is weighted by
    the sine of its half-degree cap, and a missing cell drops out of the weight.
    """
    years, nlat, _nlon = pwat.shape
    weights = np.empty(nlat, dtype=np.float64)
    for i_lat in range(nlat):
        lat = 90.0 - i_lat
        south = math.radians(max(-90.0, lat - 0.5))
        north = math.radians(min(90.0, lat + 0.5))
        weights[i_lat] = max(0.0, math.sin(north) - math.sin(south))
    band = weights[:, None]
    pwat_out: list[float | None] = []
    ivt_out: list[float | None] = []
    for year in range(years):
        water = pwat[year]
        transport = ivt[year]
        water_ok = water != MISSING
        transport_ok = transport != MISSING
        water_weight = float(np.sum(np.where(water_ok, band, 0.0)))
        transport_weight = float(np.sum(np.where(transport_ok, band, 0.0)))
        if water_weight:
            total = float(np.sum(np.where(water_ok, water.astype(np.float64) / 100.0, 0.0) * band))
            pwat_out.append(round(total / water_weight, 6))
        else:
            pwat_out.append(None)
        if transport_weight:
            total = float(np.sum(np.where(transport_ok, transport.astype(np.float64), 0.0) * band))
            ivt_out.append(round(total / transport_weight, 4))
        else:
            ivt_out.append(None)
    return {"start": int(start), "end": int(start + years - 1), "pwat": pwat_out, "ivt": ivt_out}


def unpack_grid(blob: bytes) -> dict:
    magic, start, end, nlat, nlon = struct.unpack_from("<4sHHHH", blob, 0)
    if magic != MAGIC:
        raise ValueError(f"Not a moisture record: {magic!r}")
    count = (end - start + 1) * nlat * nlon
    pwat = np.frombuffer(blob, dtype="<u2", count=count, offset=12).reshape(end - start + 1, nlat, nlon)
    ivt = np.frombuffer(blob, dtype="<u2", count=count, offset=12 + count * 2).reshape(end - start + 1, nlat, nlon)
    return {"start": start, "end": end, "pwat": pwat, "ivt": ivt}


def load_saved_series() -> dict | None:
    path = ROOT / "lib" / "moisture_global.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_page(series: dict | None = None) -> str:
    template = (ROOT / "lib" / "moisture_trends_page.html").read_text(encoding="utf-8")
    title = "Moisture trends"
    if series is None:
        series = load_saved_series()
    payload = "null" if not series else json.dumps(series, separators=(",", ":"), allow_nan=False)
    return (
        template.replace("__TITLE__", title)
        .replace("__SEO__", _seo("/climate/moisture-trends", title))
        .replace("__NAV__", _site_nav("/climate/moisture-trends"))
        .replace("__SERIES__", payload)
    )


def _open_client():
    try:
        import cdsapi
    except ImportError as exc:
        raise SystemExit("Install cdsapi first: pip install cdsapi") from exc
    return cdsapi.Client()


def build(work: Path, start: int, end: int, grid: float = 1.0) -> None:
    download_dir = work / "downloads"
    client = _open_client()
    paths = download_groups(client, download_dir, start, end, grid)
    pwat, ivt = annual_fields(paths["pwat"], paths["flux"], start, end)
    blob = pack_grid(pwat, ivt, start, end)
    work.mkdir(parents=True, exist_ok=True)
    (work / "data.bin").write_bytes(blob)
    unpacked = unpack_grid(blob)
    series = global_series(unpacked["pwat"], unpacked["ivt"], start)
    (work / "index.html").write_text(render_page(series), encoding="utf-8")
    shutil.rmtree(download_dir, ignore_errors=True)
    print(f"page written {work / 'index.html'}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Moisture trends page from ERA5.")
    parser.add_argument("--work", default="", help="Directory for the page and the record.")
    parser.add_argument("--today", default="", help="Override the calendar date used for the end year.")
    parser.add_argument("--end-year", type=int, default=0, help="Last finished year. Defaults to last year.")
    parser.add_argument("--start-year", type=int, default=START_YEAR)
    parser.add_argument("--grid", type=float, default=1.0)
    args = parser.parse_args(argv)
    today = date.fromisoformat(args.today) if args.today.strip() else datetime.now(timezone.utc).date()
    end = args.end_year or int(os.environ.get("TARGET_YEAR") or 0) or end_year(today)
    work = Path(args.work or os.environ.get("WORK_ROOT") or "/tmp/monthly-updates/moisture-trends").expanduser()
    print(f"moisture trends {args.start_year}-{end}", flush=True)
    build(work, args.start_year, end, args.grid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
