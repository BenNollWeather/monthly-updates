#!/usr/bin/env python3
from __future__ import annotations

def _apply_house_style() -> None:
    import sys
    from pathlib import Path
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
"""Run ERA5 monthly extremes workflow.

Converted from era5_extremes.ipynb.
All downloads, extracted files, plots, and upload-staging copies are kept under
one disposable folder by default: DISPOSABLE/era5_extremes_work
"""


import argparse
import os
import subprocess
import time
import zipfile
from pathlib import Path


def _parse_cli():
    parser = argparse.ArgumentParser(description="Download and plot ERA5 monthly extremes.")
    parser.add_argument("--work-dir", default="DISPOSABLE/era5_extremes_work", help="Single folder for all downloads and outputs.")
    parser.add_argument("--skip-download", action="store_true", help="Reuse existing ERA5 zip/extracted NetCDF files in work-dir.")
    parser.add_argument("--no-upload-copy", action="store_true", help="Do not make web-named copies in the upload_ready folder.")
    parser.add_argument("--skip-upload", action="store_true", help="Do not upload upload_ready imagery to S3.")
    parser.add_argument("--download-retries", type=int, default=3, help="Number of CDS download attempts before failing.")
    parser.add_argument("--retry-sleep", type=int, default=30, help="Seconds to wait between failed CDS download attempts.")
    parser.add_argument("--aws-bin", default="aws", help="Path to the AWS CLI executable.")
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""), help="AWS profile to use for upload. Empty uses the ambient credentials.")
    parser.add_argument("--bucket", default="bennollweather", help="S3 bucket name.")
    parser.add_argument("--prefix", default="atmospheric_moisture", help="S3 prefix for uploaded imagery.")
    parser.add_argument("--target-month", default=None, help="Force a specific month (YYYY-MM) instead of auto-detecting the latest available month.")
    parser.add_argument("--skip-datawrapper", action="store_true", help="Skip the upper-decile precipitation CSV/GeoJSON exports.")
    parser.add_argument("--geojson-simplify", type=float, default=0.1, help="Douglas-Peucker tolerance (degrees) for the upper-decile GeoJSON; 0 disables.")
    parser.add_argument("--geojson-min-area", type=float, default=0.0, help="Drop GeoJSON polygons smaller than this many square degrees.")
    parser.add_argument("--max-lookback", type=int, default=6, help="How many months back to search for the latest available ERA5 month.")
    return parser.parse_args()

ARGS = _parse_cli()
WORK_DIR = Path(ARGS.work_dir).expanduser().resolve()
IMAGERY_DIR = WORK_DIR / "imagery"
UPLOAD_READY_DIR = WORK_DIR / "upload_ready"
EXTRACT_DIR = WORK_DIR / "output_directory"
# ZIP_PATH is set per target month once the latest available month is known
# (era5_extremes_YYYY_MM.zip) so a stale download from an earlier month is never reused.
WORK_DIR.mkdir(parents=True, exist_ok=True)
IMAGERY_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_READY_DIR.mkdir(parents=True, exist_ok=True)
EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(WORK_DIR)

# Force all notebook-era hardcoded saves into the single disposable work folder.
# The first save in the notebook keeps a dated filename; the second save keeps
# the web/static filename. Both are redirected under WORK_DIR.
_ORIG_SAVEFIG = None

def _install_savefig_redirect():
    import matplotlib.pyplot as _plt
    global _ORIG_SAVEFIG
    _ORIG_SAVEFIG = _plt.savefig

    def _redirected_savefig(fname, *args, **kwargs):
        if isinstance(fname, (str, os.PathLike)):
            raw = Path(str(fname))
            name = raw.name
            old = str(fname)
            if old.startswith("DISPOSABLE/") or old.startswith("DISPOSABLE/"):
                fname = IMAGERY_DIR / name
            elif old.startswith("PUBLISH/") or old.startswith("PUBLISH/"):
                fname = UPLOAD_READY_DIR / name
            else:
                fname = raw
                if not fname.is_absolute():
                    fname = IMAGERY_DIR / fname.name
        Path(fname).parent.mkdir(parents=True, exist_ok=True)
        return _ORIG_SAVEFIG(fname, *args, **kwargs)

    _plt.savefig = _redirected_savefig




def _zip_is_valid(path: Path) -> bool:
    """Return True only when path exists and is a readable, complete ZIP file."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    if not zipfile.is_zipfile(path):
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None
    except zipfile.BadZipFile:
        return False


def download_cds_with_retries(client, dataset: str, request: dict, target: Path, retries: int = 3, sleep_seconds: int = 30) -> None:
    """Download from CDS with guardrails for partial/incomplete downloads."""
    target = Path(target)
    partial_candidates = [
        target,
        target.with_suffix(target.suffix + ".part"),
        target.with_suffix(target.suffix + ".tmp"),
        target.with_name(target.name + ".part"),
        target.with_name(target.name + ".tmp"),
    ]

    for attempt in range(1, retries + 1):
        if _zip_is_valid(target):
            print(f"Valid existing ZIP found: {target}")
            return

        for candidate in partial_candidates:
            if candidate.exists():
                print(f"Removing incomplete/invalid download: {candidate}")
                candidate.unlink()

        print(f"Downloading ERA5 data to {target} (attempt {attempt}/{retries})")
        try:
            client.retrieve(dataset, request).download(str(target))
            if _zip_is_valid(target):
                print(f"Download complete and ZIP validated: {target}")
                return
            raise RuntimeError(f"Downloaded file is not a valid complete ZIP: {target}")
        except Exception as exc:
            print(f"Download attempt {attempt} failed: {exc}")
            if target.exists():
                print(f"Removing failed partial file: {target}")
                target.unlink()
            if attempt == retries:
                raise
            print(f"Retrying in {sleep_seconds} seconds...")
            time.sleep(sleep_seconds)


# %% Notebook cell 0
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.ticker as mticker
import scipy.ndimage as ndimage

_install_savefig_redirect()

# %% Notebook cell 1
from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.util import add_cyclic_point
from metpy.plots import USCOUNTIES
import matplotlib.patheffects as pe
import seaborn as sns

# %% Notebook cell 2
import cmocean
import xarray as xr
import numpy as np
import pandas as pd
import pathlib
import sys
import os

# %% Notebook cell 3
from dateparser import parse

# ---------------------------------------------------------------------------
# Latest-available-month detection
# ---------------------------------------------------------------------------
# ERA5 monthly means are published a few days after the month ends, so
# "last month" is not always available yet. Instead of assuming it is (and
# silently ending up with the same month from the previous year), probe CDS
# with a tiny request, stepping back one month at a time until data is found.
# The full download then requests that month for 1940..that year, and the
# result is checked to make sure the final time step really is that month.

ERA5_MONTHLY_DATASET = "reanalysis-era5-single-levels-monthly-means"
_NO_DATA_PATTERNS = (
    "no data",
    "nodata",
    "not available",
    "not yet available",
    "is not available yet",
    "valid combination",
    "none of the data",
    "empty",
)


def _parse_year_month(value: str) -> pd.Timestamp:
    """Parse 'YYYY-MM' into a first-of-month Timestamp."""
    try:
        ts = pd.Timestamp(f"{value}-01") if len(value) == 7 else pd.Timestamp(value)
    except Exception as exc:
        raise SystemExit(f"Invalid --target-month {value!r}; expected YYYY-MM") from exc
    return pd.Timestamp(year=ts.year, month=ts.month, day=1)


def _times_in_download(path: Path) -> pd.DatetimeIndex:
    """Return all valid_time/time values in a CDS download (NetCDF or ZIP of NetCDFs)."""
    import tempfile
    import zipfile as _zipfile

    path = Path(path)
    nc_paths: list[Path] = []
    tmpdir = None
    if _zipfile.is_zipfile(path):
        tmpdir = tempfile.TemporaryDirectory()
        with _zipfile.ZipFile(path) as zf:
            zf.extractall(tmpdir.name)
        nc_paths = sorted(Path(tmpdir.name).rglob("*.nc"))
    else:
        nc_paths = [path]

    times: list[pd.Timestamp] = []
    try:
        for nc in nc_paths:
            with xr.open_dataset(nc) as probe_ds:
                for name in ("valid_time", "time"):
                    if name in probe_ds.coords or name in probe_ds.variables:
                        vals = pd.to_datetime(np.asarray(probe_ds[name].values).ravel())
                        times.extend(v for v in vals if not pd.isna(v))
                        break
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()
    return pd.DatetimeIndex(times)


def _month_is_available(client, year: int, month: int, probe_dir: Path, attempts: int = 2, sleep_seconds: int = 15) -> bool:
    """Request one variable over a tiny box for a single year/month and check data comes back."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    target = probe_dir / f"probe_{year}_{month:02d}.nc"
    request = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["2m_temperature"],
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "time": ["00:00"],
        "area": [1, 0, 0, 1],  # N, W, S, E — tiny box keeps the probe fast
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    for attempt in range(1, attempts + 1):
        if target.exists():
            target.unlink()
        try:
            client.retrieve(ERA5_MONTHLY_DATASET, request).download(str(target))
            times = _times_in_download(target)
            return any(t.year == year and t.month == month for t in times)
        except Exception as exc:
            msg = str(exc).lower()
            if any(p in msg for p in _NO_DATA_PATTERNS):
                return False
            print(f"Availability probe for {year}-{month:02d} failed (attempt {attempt}/{attempts}): {exc}")
            if attempt < attempts:
                time.sleep(sleep_seconds)
        finally:
            if target.exists():
                target.unlink()
    print(f"Treating {year}-{month:02d} as unavailable after {attempts} failed probes.")
    return False


def find_latest_available_month(client, probe_dir: Path, max_lookback: int = 6) -> pd.Timestamp:
    """Return the most recent month (first-of-month Timestamp) with ERA5 monthly-mean data on CDS."""
    today = pd.Timestamp.today().normalize()
    first_of_this_month = pd.Timestamp(year=today.year, month=today.month, day=1)
    for back in range(1, max_lookback + 1):
        candidate = first_of_this_month - pd.DateOffset(months=back)
        print(f"Checking CDS for ERA5 monthly data: {candidate:%B %Y} ...")
        if _month_is_available(client, candidate.year, candidate.month, probe_dir):
            print(f"Latest available ERA5 month: {candidate:%B %Y}")
            return candidate
        print(f"  {candidate:%B %Y} not available yet.")
    raise RuntimeError(f"No ERA5 monthly data found in the last {max_lookback} months.")


def verify_latest_month(times, target: pd.Timestamp, label: str = "ERA5 data") -> None:
    """Fail loudly if the data does not end at the target month (prevents previous-year fallback)."""
    times = pd.DatetimeIndex(pd.to_datetime(np.asarray(times).ravel()))
    times = times[~pd.isna(times)]
    if times.empty:
        raise RuntimeError(f"{label} has no time values.")
    latest = times.max()
    if (latest.year, latest.month) != (target.year, target.month):
        raise RuntimeError(
            f"{label} ends at {latest:%B %Y}, expected {target:%B %Y}. "
            "Refusing to continue so a previous year is not mislabeled as the current one."
        )


def _latest_local_month() -> pd.Timestamp | None:
    """For --skip-download: newest month that already has a valid ZIP or extracted files in WORK_DIR."""
    found = []
    for zp in WORK_DIR.glob("era5_extremes_*_*.zip"):
        if _zip_is_valid(zp):
            found.append(zp.stem.replace("era5_extremes_", ""))
    for d in EXTRACT_DIR.glob("*_*"):
        if d.is_dir() and any(d.glob("*.nc")):
            found.append(d.name)
    stamps = []
    for tag in found:
        try:
            stamps.append(pd.Timestamp(f"{tag.replace('_', '-')}-01"))
        except Exception:
            pass
    return max(stamps) if stamps else None


# %% Notebook cell 5
import cdsapi

client = cdsapi.Client()
if ARGS.target_month:
    target_month = _parse_year_month(ARGS.target_month)
    print(f"Using requested target month: {target_month:%B %Y}")
elif ARGS.skip_download:
    target_month = _latest_local_month()
    if target_month is None:
        raise SystemExit("--skip-download was given but no previous download was found; pass --target-month YYYY-MM.")
    print(f"Using latest locally downloaded month: {target_month:%B %Y}")
else:
    target_month = find_latest_available_month(client, WORK_DIR / "probe", max_lookback=ARGS.max_lookback)

month = target_month
month_tag = target_month.strftime("%Y_%m")
ZIP_PATH = WORK_DIR / f"era5_extremes_{month_tag}.zip"
EXTRACT_DIR = EXTRACT_DIR / month_tag
EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

# %% Notebook cell 6
download_month = month.strftime("%m")
download_year = month.strftime("%Y")

# %% Notebook cell 7
print(f"Requesting month {download_month} for 1940-{download_year}")

# %% Notebook cell 10
dataset = ERA5_MONTHLY_DATASET
request = {
    "product_type": ["monthly_averaged_reanalysis"],
    "variable": [
        "2m_dewpoint_temperature",
        "2m_temperature",
        "sea_surface_temperature",
        "total_precipitation",
        "10m_wind_speed",
        "total_cloud_cover",
        "snowfall"
    ],
    # 1940 through the year of the latest available month, so every year is
    # matched to that same calendar month.
    "year": [str(y) for y in range(1940, target_month.year + 1)],
    "month": [download_month],
    "time": ["00:00"],
    "data_format": "netcdf",
    "download_format": "unarchived"
}

if ARGS.skip_download and _zip_is_valid(ZIP_PATH):
    print(f"Skipping CDS download; using valid existing {ZIP_PATH}")
else:
    if ARGS.skip_download and ZIP_PATH.exists() and not _zip_is_valid(ZIP_PATH):
        print(f"Existing ZIP is invalid/incomplete despite --skip-download: {ZIP_PATH}")
    download_cds_with_retries(
        client,
        dataset,
        request,
        ZIP_PATH,
        retries=ARGS.download_retries,
        sleep_seconds=ARGS.retry_sleep,
    )

# %% Notebook cell 11

if ARGS.skip_download and any(EXTRACT_DIR.glob("*.nc")):
    print(f"Skipping unzip; NetCDF files already exist in {EXTRACT_DIR}")
else:
    if not _zip_is_valid(ZIP_PATH):
        raise RuntimeError(f"Cannot extract invalid/incomplete ZIP: {ZIP_PATH}")
    print(f"Extracting {ZIP_PATH} to {EXTRACT_DIR}")
    with zipfile.ZipFile(ZIP_PATH, "r") as zip_ref:
        zip_ref.extractall(EXTRACT_DIR)

# %% Notebook cell 12
# Paths to the NetCDF files
file_0 = str(EXTRACT_DIR / "data_stream-moda_stepType-avgad.nc")
file_1 = str(EXTRACT_DIR / "data_stream-moda_stepType-avgua.nc")

# Open the datasets
ds_0 = xr.open_dataset(file_0)# Keep as datetime64 but set time to 00:00
ds_0['valid_time'] = ds_0['valid_time'].dt.floor('D')

ds_1 = xr.open_dataset(file_1)

# Merge the datasets
merged = xr.merge([ds_0, ds_1])

# Concatenate along the 'valid_time' dimension
ds = merged

# Build the plot source label from the actual downloaded data range.
valid_times = pd.to_datetime(ds['valid_time'].values.ravel())
valid_times = valid_times[~pd.isna(valid_times)]
if valid_times.empty:
    raise RuntimeError("Downloaded ERA5 data has no valid_time values.")
# The last time step must be the target month; otherwise [-1] would silently
# be the same month from the previous year.
verify_latest_month(valid_times, target_month, label="Downloaded ERA5 extremes data")
if set(valid_times.month) != {target_month.month}:
    raise RuntimeError(f"Downloaded data contains months other than {target_month:%B}: {sorted(set(valid_times.month))}")
start_time = valid_times.min()
end_time = valid_times.max()
data_period_label = (
    f"Data: ERA5; {start_time.strftime('%B')} "
    f"{start_time.year} to {end_time.year}"
)

# ds

# %% Notebook cell 13
ds_0 = merged
ds_1 = merged

# %% Notebook cell 15
current_month = target_month

current_month = current_month.strftime("%B %Y")

# %% Notebook cell 16
current_month

# %% Notebook cell 17
current_month_no_year = target_month

current_month_no_year = current_month_no_year.strftime("%B")

# %% Notebook cell 18
date = parse('today GMT')

date = date.strftime("%Y%m%d")

# %% Notebook cell 20
# ds = xr.open_dataset("DISPOSABLE/era5_extremes.nc")

# %% Notebook cell 22
# # Convert the 'date' variable to datetime format
# dates = pd.to_datetime(ds.date.values, format='%Y%m%d')

# # Assign the new datetime index to the dataset
# ds = ds.assign_coords(date=dates)

# # Rename date to time
# ds = ds.rename({'date': 'valid_time'})

# %% Area-weighting helpers
# Grid cells on a regular lat/lon grid shrink toward the poles (area ~ cos(lat)),
# so every "% of the planet" figure below is weighted by cos(latitude) instead
# of counting grid squares.
def pct_of_planet(mask, valid=None) -> float:
    """Percent of the globe (or of `valid` cells, e.g. ocean) where a 2-D lat/lon mask is True."""
    da = mask.transpose(..., "latitude", "longitude")
    m = np.asarray(da.values).astype(bool)
    while m.ndim > 2:  # collapse any leftover singleton/extra dims
        m = m.any(axis=0)
    w = np.clip(np.cos(np.deg2rad(da["latitude"].values.astype(float))), 0.0, None)[:, np.newaxis]
    w = np.broadcast_to(w, m.shape)
    if valid is None:
        v = np.ones(m.shape, dtype=bool)
    else:
        v = np.asarray(valid.transpose(..., "latitude", "longitude").values).astype(bool)
        while v.ndim > 2:
            v = v.any(axis=0)
    # np.float64 so the existing `percentage.item()` calls keep working.
    return np.float64(100.0 * np.sum(w * (m & v)) / np.sum(w * v))


def _tp_time_lat_lon(da):
    """Return precipitation as (valid_time, latitude, longitude), collapsing any extra dims (e.g. expver)."""
    extra = [d for d in da.dims if d not in ("valid_time", "latitude", "longitude")]
    if extra:
        da = da.max(extra)
    return da.transpose("valid_time", "latitude", "longitude")


def upper_decile_mask(tp_values: np.ndarray) -> np.ndarray:
    """Boolean (time, lat, lon): value above that grid cell's 90th percentile across all years."""
    q90 = np.nanquantile(tp_values, 0.90, axis=0)  # same linear method as xarray .quantile
    with np.errstate(invalid="ignore"):
        return tp_values > q90[np.newaxis, ...]


def area_weighted_pct(mask: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Percent of the planet covered by mask for each time step (cos-latitude weights)."""
    w = np.cos(np.deg2rad(np.asarray(lats, dtype=float)))
    w = np.clip(w, 0.0, None)
    covered = mask.sum(axis=-1) @ w  # (time,)
    return 100.0 * covered / (mask.shape[-1] * w.sum())


# %% Notebook cell 23
t2m_q90 = ds_0['t2m'].quantile(q=0.90, dim='valid_time')
t2m_q10 = ds_0['t2m'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 24
t2m_q90 = ds_0['t2m'][-1] - t2m_q90
t2m_q10 = t2m_q10 - ds_0['t2m'][-1]

# %% Notebook cell 25
t2m_q90 = t2m_q90.where(t2m_q90 > 0)
t2m_q10 = t2m_q10.where(t2m_q10 > 0)

# %% Notebook cell 26
t2m_q90 = (t2m_q90 > 0)
t2m_q10 = (t2m_q10 > 0)

# %% Notebook cell 28
lats = t2m_q90['latitude'][:]  
lons = t2m_q90['longitude'][:]

# %% Notebook cell 29
lats2 = t2m_q10['latitude'][:]  
lons2 = t2m_q10['longitude'][:]

# %% Notebook cell 30
# Define the colors
colors = ['dimgray', 'crimson']

# Create a colormap
cmap_custom_t2m_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'aqua']

# Create a colormap
cmap_custom_t2m_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 31
latitude = t2m_q90['latitude'].values  # Latitude values
longitude = t2m_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(t2m_q90)

t2m_q90_value = percentage.item()
t2m_q90_value = int(round(t2m_q90_value))
t2m_q90_value

# %% Notebook cell 32
latitude = t2m_q10['latitude'].values  # Latitude values
longitude = t2m_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(t2m_q10)

t2m_q10_value = percentage.item()
t2m_q10_value = int(round(t2m_q10_value))
t2m_q10_value

# %% Notebook cell 33
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, t2m_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_t2m_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, t2m_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_t2m_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, t2m_q90, vmin=1, vmax=1, cmap=cmap_custom_t2m_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, t2m_q10, vmin=1, vmax=1, cmap=cmap_custom_t2m_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Air temperature > 90th percentile (red, {}%) | < 10th percentile (blue, {}%)'.format(t2m_q90_value, t2m_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_temp_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_temp_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 35
tp_q90 = ds_1['tp'].quantile(q=0.90, dim='valid_time')
tp_q10 = ds_1['tp'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 36
tp_q90 = ds_1['tp'][-1] - tp_q90
tp_q10 = tp_q10 - ds_1['tp'][-1]

# %% Notebook cell 37
tp_q90 = tp_q90.where(tp_q90 > 0)
tp_q10 = tp_q10.where(tp_q10 > 0)

# %% Notebook cell 38
tp_q90 = (tp_q90 > 0)
tp_q10 = (tp_q10 > 0)

# %% Notebook cell 40
lats = tp_q90['latitude'][:]  
lons = tp_q90['longitude'][:]

# %% Notebook cell 41
lats2 = tp_q10['latitude'][:]  
lons2 = tp_q10['longitude'][:]

# %% Notebook cell 42
# Define the colors
colors = ['dimgray', 'lime']

# Create a colormap
cmap_custom_tp_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'darkgoldenrod']

# Create a colormap
cmap_custom_tp_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 43
latitude = tp_q90['latitude'].values  # Latitude values
longitude = tp_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(tp_q90)

tp_q90_value = percentage.item()
tp_q90_value = int(round(tp_q90_value))
tp_q90_value

# %% Notebook cell 44
latitude = tp_q10['latitude'].values  # Latitude values
longitude = tp_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(tp_q10)

tp_q10_value = percentage.item()
tp_q10_value = int(round(tp_q10_value))
tp_q10_value

# %% Notebook cell 45
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, tp_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_tp_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, tp_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_tp_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, tp_q90, vmin=1, vmax=1, cmap=cmap_custom_tp_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, tp_q10, vmin=1, vmax=1, cmap=cmap_custom_tp_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Total precipitation > 90th percentile (green, {}%) | < 10th percentile (brown, {}%)'.format(tp_q90_value, tp_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_precip_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_precip_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 47
wind_q90 = ds_0['si10'].quantile(q=0.90, dim='valid_time')
wind_q10 = ds_0['si10'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 48
wind_q90 = ds_0['si10'][-1] - wind_q90
wind_q10 = wind_q10 - ds_0['si10'][-1]

# %% Notebook cell 49
wind_q90 = wind_q90.where(wind_q90 > 0)
wind_q10 = wind_q10.where(wind_q10 > 0)

# %% Notebook cell 50
wind_q90 = (wind_q90 > 0)
wind_q10 = (wind_q10 > 0)

# %% Notebook cell 52
lats = wind_q90['latitude'][:]  
lons = wind_q90['longitude'][:]

# %% Notebook cell 53
lats2 = wind_q10['latitude'][:]  
lons2 = wind_q10['longitude'][:]

# %% Notebook cell 54
# Define the colors
colors = ['dimgray', 'mediumorchid']

# Create a colormap
cmap_custom_wind_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'khaki']

# Create a colormap
cmap_custom_wind_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 55
latitude = wind_q90['latitude'].values  # Latitude values
longitude = wind_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(wind_q90)

wind_q90_value = percentage.item()
wind_q90_value = int(round(wind_q90_value))
wind_q90_value

# %% Notebook cell 56
latitude = wind_q10['latitude'].values  # Latitude values
longitude = wind_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(wind_q10)

wind_q10_value = percentage.item()
wind_q10_value = int(round(wind_q10_value))
wind_q10_value

# %% Notebook cell 57
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, wind_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_wind_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, wind_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_wind_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, wind_q90, vmin=1, vmax=1, cmap=cmap_custom_wind_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, wind_q10, vmin=1, vmax=1, cmap=cmap_custom_wind_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Wind speed > 90th percentile (purple, {}%) | < 10th percentile (tan, {}%)'.format(wind_q90_value, wind_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_wind_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_wind_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 59
dew_q90 = ds_0['d2m'].quantile(q=0.90, dim='valid_time')
dew_q10 = ds_0['d2m'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 60
dew_q90 = ds_0['d2m'][-1] - dew_q90
dew_q10 = dew_q10 - ds_0['d2m'][-1]

# %% Notebook cell 61
dew_q90 = dew_q90.where(dew_q90 > 0)
dew_q10 = dew_q10.where(dew_q10 > 0)

# %% Notebook cell 62
dew_q90 = (dew_q90 > 0)
dew_q10 = (dew_q10 > 0)

# %% Notebook cell 64
lats = dew_q90['latitude'][:]  
lons = dew_q90['longitude'][:]

# %% Notebook cell 65
lats2 = dew_q10['latitude'][:]  
lons2 = dew_q10['longitude'][:]

# %% Notebook cell 66
# Define the colors
colors = ['dimgray', 'limegreen']

# Create a colormap
cmap_custom_humidity_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'cornflowerblue']

# Create a colormap
cmap_custom_humidity_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 67
latitude = dew_q90['latitude'].values  # Latitude values
longitude = dew_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(dew_q90)

dew_q90_value = percentage.item()
dew_q90_value = int(round(dew_q90_value))
dew_q90_value

# %% Notebook cell 68
latitude = dew_q10['latitude'].values  # Latitude values
longitude = dew_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(dew_q10)

dew_q10_value = percentage.item()
dew_q10_value = int(round(dew_q10_value))
dew_q10_value

# %% Notebook cell 69
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, dew_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_humidity_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, dew_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_humidity_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, dew_q90, vmin=1, vmax=1, cmap=cmap_custom_humidity_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, dew_q10, vmin=1, vmax=1, cmap=cmap_custom_humidity_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Humidity > 90th percentile (green, {}%) | < 10th percentile (blue, {}%)'.format(dew_q90_value, dew_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_humidity_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_humidity_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 71
cloud_q90 = ds_0['tcc'].quantile(q=0.90, dim='valid_time')
cloud_q10 = ds_0['tcc'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 72
cloud_q90 = ds_0['tcc'][-1] - cloud_q90
cloud_q10 = cloud_q10 - ds_0['tcc'][-1]

# %% Notebook cell 73
cloud_q90 = cloud_q90.where(cloud_q90 > 0)
cloud_q10 = cloud_q10.where(cloud_q10 > 0)

# %% Notebook cell 74
cloud_q90 = (cloud_q90 > 0)
cloud_q10 = (cloud_q10 > 0)

# %% Notebook cell 76
lats = cloud_q90['latitude'][:]  
lons = cloud_q90['longitude'][:]

# %% Notebook cell 77
lats2 = cloud_q10['latitude'][:]  
lons2 = cloud_q10['longitude'][:]

# %% Notebook cell 78
# Define the colors
colors = ['dimgray', 'dimgray']

# Create a colormap
cmap_custom_cloud_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'yellow']

# Create a colormap
cmap_custom_cloud_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 79
latitude = cloud_q90['latitude'].values  # Latitude values
longitude = cloud_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(cloud_q90)

cloud_q90_value = percentage.item()
cloud_q90_value = int(round(cloud_q90_value))
cloud_q90_value

# %% Notebook cell 80
latitude = cloud_q10['latitude'].values  # Latitude values
longitude = cloud_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(cloud_q10)

cloud_q10_value = percentage.item()
cloud_q10_value = int(round(cloud_q10_value))
cloud_q10_value

# %% Notebook cell 81
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, cloud_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_cloud_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, cloud_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_cloud_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, cloud_q90, vmin=1, vmax=1, cmap=cmap_custom_cloud_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, cloud_q10, vmin=1, vmax=1, cmap=cmap_custom_cloud_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Cloud cover > 90th percentile (gray, {}%) | < 10th percentile (yellow, {}%)'.format(cloud_q90_value, cloud_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_cloud_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_cloud_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 83
snow_q90 = ds_1['sf'].quantile(q=0.90, dim='valid_time')
snow_q10 = ds_1['sf'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 84
snow_q90 = ds_1['sf'][-1] - snow_q90
snow_q10 = snow_q10 - ds_1['sf'][-1]

# %% Notebook cell 85
snow_q90 = snow_q90.where(snow_q90 > 0)
snow_q10 = snow_q10.where(snow_q10 > 0)

# %% Notebook cell 86
snow_q90 = (snow_q90 > 0)
snow_q10 = (snow_q10 > 0)

# %% Notebook cell 88
lats = snow_q90['latitude'][:]  
lons = snow_q90['longitude'][:]

# %% Notebook cell 89
lats2 = snow_q10['latitude'][:]  
lons2 = snow_q10['longitude'][:]

# %% Notebook cell 90
# Define the colors
colors = ['dimgray', 'cyan']

# Create a colormap
cmap_custom_snow_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'orangered']

# Create a colormap
cmap_custom_snow_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 91
latitude = snow_q90['latitude'].values  # Latitude values
longitude = snow_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(snow_q90)

snow_q90_value = percentage.item()
snow_q90_value = int(round(snow_q90_value))
snow_q90_value

# %% Notebook cell 92
latitude = snow_q10['latitude'].values  # Latitude values
longitude = snow_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(snow_q10)

snow_q10_value = percentage.item()
snow_q10_value = int(round(snow_q10_value))
snow_q10_value

# %% Notebook cell 93
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, snow_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_snow_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, snow_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_snow_q10(0.5)], transform=ccrs.PlateCarree())

# data = ax.pcolormesh(lons, lats, snow_q90, vmin=1, vmax=1, cmap=cmap_custom_snow_q90, alpha=1, transform=ccrs.PlateCarree())
# data2 = ax.pcolormesh(lons2, lats2, snow_q10, vmin=1, vmax=1, cmap=cmap_custom_snow_q10, alpha=0.6, transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Snowfall > 90th percentile (blue, {}%) | < 10th percentile (orange, {}%)'.format(snow_q90_value, snow_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_snow_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_snow_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 95
sst_q90 = ds_0['sst'].quantile(q=0.90, dim='valid_time')
sst_q10 = ds_0['sst'].quantile(q=0.10, dim='valid_time')

# %% Notebook cell 96
sst_q90 = ds_0['sst'][-1] - sst_q90
sst_q10 = sst_q10 - ds_0['sst'][-1]

# %% Notebook cell 97
sst_q90 = sst_q90.where(sst_q90 > 0)
sst_q10 = sst_q10.where(sst_q10 > 0)

# %% Notebook cell 98
sst_q90 = (sst_q90 > 0)
sst_q10 = (sst_q10 > 0)

# %% Notebook cell 100
lats = sst_q90['latitude'][:]  
lons = sst_q90['longitude'][:]

# %% Notebook cell 101
lats2 = sst_q10['latitude'][:]  
lons2 = sst_q10['longitude'][:]

# %% Notebook cell 102
# Define the colors
colors = ['dimgray', 'crimson']

# Create a colormap
cmap_custom_t2m_q90 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# Define the colors
colors = ['dimgray', 'aqua']

# Create a colormap
cmap_custom_t2m_q10 = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 103
latitude = sst_q90['latitude'].values  # Latitude values
longitude = sst_q90['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

# Share of the ocean: area-weighted over grid cells with valid SST.
percentage = pct_of_planet(sst_q90, valid=ds_0['sst'][-1].notnull())

sst_q90_value = percentage.item()
sst_q90_value = int(round(sst_q90_value))
sst_q90_value

# %% Notebook cell 104
latitude = sst_q10['latitude'].values  # Latitude values
longitude = sst_q10['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

# Share of the ocean: area-weighted over grid cells with valid SST.
percentage = pct_of_planet(sst_q10, valid=ds_0['sst'][-1].notnull())

sst_q10_value = percentage.item()
sst_q10_value = int(round(sst_q10_value))
sst_q10_value

# %% Notebook cell 105
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, sst_q90, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_t2m_q90(0.5)], transform=ccrs.PlateCarree())
contourf2 = ax.contourf(lons2, lats2, sst_q10, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_custom_t2m_q10(0.5)], transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Sea surface temperature > 90th percentile (red, {}%) | < 10th percentile (blue, {}%)'.format(sst_q90_value, sst_q10_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

cbar = plt.colorbar(contourf1, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar.remove()

cbar2 = plt.colorbar(contourf2, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.65, aspect=60)
cbar2.remove()

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_sst_percentile_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_sst_percentile.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 107
merged_data = t2m_q90 * dew_q90

# %% Notebook cell 108
# Define the colors
colors = ['dimgray', 'hotpink']

# Create a colormap
cmap_heat_stress = LinearSegmentedColormap.from_list('custom_cmap', colors)

# %% Notebook cell 109
latitude = merged_data['latitude'].values  # Latitude values
longitude = merged_data['longitude'].values  # Longitude values

grid_size = 111.0  # in km

weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))

grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))

grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])

conversion_factor = 1.0

percentage = pct_of_planet(merged_data)

merged_data_value = percentage.item()
merged_data_value = int(round(merged_data_value))
merged_data_value

# %% Notebook cell 110
fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree())

contourf1 = ax.contourf(lons, lats, merged_data, levels=[-0.5, 0.5, 1.5], colors=['none', cmap_heat_stress(0.5)], transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.coastlines(resolution='10m', color='k', linewidth=1)
ax.add_feature(cfeature.LAND, color="gainsboro")
ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=1)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('Air temperature & humidity > 90th percentile (pink, {}%)'.format(merged_data_value), loc='left', fontsize=36, color='white', weight="bold")
plt.title('{}'.format(current_month), loc='right', color='white', fontsize=32, weight="bold")

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'), zorder=21)
ax.text(0.01, -0.03, data_period_label, color='white', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, fontsize=12, weight="bold")

fig.patch.set_facecolor('k')

# cbar.ax.set_facecolor([1,1,1,0])

plt.savefig('DISPOSABLE/era5_heat_stress_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/era5_heat_stress.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cells 112-117 (rewritten: area-weighted)
# Upper decile = tp above that grid cell's 90th percentile for this calendar
# month across all downloaded years (same threshold as the precip map).
# Coverage is weighted by cos(latitude) so it is a true share of the planet.
tp_all = _tp_time_lat_lon(ds_1['tp'])
tp_times = pd.DatetimeIndex(pd.to_datetime(tp_all['valid_time'].values))
tp_upper_decile_mask = upper_decile_mask(tp_all.values)
tp_q90_pct = area_weighted_pct(tp_upper_decile_mask, tp_all['latitude'].values)
tp_q90_values = [round(float(v), 1) for v in tp_q90_pct]
print(tp_q90_values)

# %% Notebook cell 118
# Upper-decile precipitation coverage chart
fig, ax = plt.subplots(figsize=(25, 15))

# Generate a list of years for the x-axis
years = np.asarray(tp_times.year)

# Plot the data
ax.plot(
    years,
    tp_q90_values,
    marker='o',
    linestyle='-',
    linewidth=5,
    color='mediumseagreen',
    markersize=15,
    markeredgecolor='gainsboro',
    markeredgewidth=3,
    zorder=3,
)

# Axes formatting
ax.set_xticks(np.arange(years[0], years[-1] + 1, 10))
ax.tick_params(axis='x', labelrotation=45, labelsize=21, colors='white', width=2, pad=8)
ax.tick_params(axis='y', labelsize=21, colors='white', width=2, length=0)
for label in ax.get_xticklabels():
    label.set_ha('right')
    label.set_fontweight('bold')
for label in ax.get_yticklabels():
    label.set_fontweight('bold')

ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
ax.set_ylim(min(tp_q90_values) - 1, max(tp_q90_values) + 1)
ax.margins(x=0.02)
ax.grid(axis='y', color='white', alpha=0.14, linewidth=1)

# Title includes the full month name and latest coverage value.
ax.set_title(
    f'Global upper-decile precipitation coverage — {current_month_no_year}, {tp_q90_values[-1]:.1f}%',
    fontsize=28,
    color='white',
    weight='bold',
    loc='left',
    pad=28,
)

# Credit is anchored in the upper-right where the separate value callout used to be.
ax.text(
    0.99,
    1.015,
    '@BenNollWeather',
    transform=ax.transAxes,
    ha='right',
    va='bottom',
    fontsize=14,
    color='white',
    weight='bold',
    bbox=dict(facecolor='dimgray', alpha=0.75, edgecolor='none', boxstyle='round,pad=0.3'),
)
ax.text(
    0.015,
    0.02,
    data_period_label,
    transform=ax.transAxes,
    ha='left',
    va='bottom',
    fontsize=12,
    color='white',
    weight='bold',
)

# Styling
ax.set_facecolor('black')
fig.set_facecolor('black')
for spine in ax.spines.values():
    spine.set_visible(False)
fig.subplots_adjust(left=0.07, right=0.97, top=0.87, bottom=0.12)

# Save the plot
plt.savefig('DISPOSABLE/upper_decile_chart_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
plt.savefig('PUBLISH/upper_decile_chart.png', facecolor=fig.get_facecolor(), bbox_inches='tight', dpi=100)
# %% Notebook cell 121





def upload_ready_imagery(local_dir: Path, aws_bin: str, aws_profile: str, bucket: str, prefix: str) -> list[str]:
    """Upload publish-ready imagery to S3 and print URLs for newly uploaded files."""
    local_dir = Path(local_dir)
    if not local_dir.exists():
        print(f"Upload skipped: directory does not exist: {local_dir}")
        return []

    s3_path = f"s3://{bucket}/{prefix.strip('/')}/"
    cmd_sync = [
        aws_bin, "s3", "sync",
        str(local_dir),
        s3_path,
        "--exclude", ".git/*",
        "--exclude", ".gitignore",
        "--exclude", ".DS_Store",
        "--exclude", ".gitattributes",
    ]

    result = subprocess.run(
        cmd_sync,
        env={**os.environ, "AWS_PROFILE": aws_profile},
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("AWS sync failed:")
        print(result.stderr)
        raise SystemExit(result.returncode)

    base_url = f"https://{bucket}.s3.amazonaws.com/{prefix.strip('/')}/"
    urls: list[str] = []

    for line in result.stdout.splitlines():
        if "upload:" in line:
            s3_file = line.split(" to ")[-1].strip()
            relative_path = s3_file.replace(s3_path, "")
            urls.append(base_url + relative_path)

    print("\nUploaded file URLs:\n")
    if urls:
        for url in urls:
            print(url)
    else:
        print("No new or updated files were uploaded by aws s3 sync.")

    return urls


# %% Datawrapper exports: upper-decile precipitation coverage + areas
# CSV: share of the planet (cos-latitude area weighted) with upper-decile
# precipitation for every year's target month in the download.
# GeoJSON: the upper-decile areas for the target (latest) month.
# Upper decile uses the same rule as the maps/chart above: tp > the 90th
# percentile of that calendar month across all downloaded years.
# Written into upload_ready/datawrapper so they sync to S3 with the imagery.
import json as _json

DATAWRAPPER_DIR = UPLOAD_READY_DIR / "datawrapper"
UPPER_DECILE_COLOR = "#3cb371"  # mediumseagreen, matches the coverage chart


def _ring_signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.sum(x[:-1] * y[1:] - x[1:] * y[:-1]))


def _simplify_ring(ring: np.ndarray, tol: float) -> np.ndarray:
    """Douglas-Peucker on a closed ring (first point == last point)."""
    if tol <= 0 or len(ring) <= 5:
        return ring
    pts = ring[:-1]
    # Anchor on the point farthest from the start so the closed ring splits cleanly.
    far = int(np.argmax(np.sum((pts - pts[0]) ** 2, axis=1)))
    keep = np.zeros(len(pts) + 1, dtype=bool)
    keep[[0, far, len(pts)]] = True
    closed = np.vstack([pts, pts[:1]])
    stack = [(0, far), (far, len(pts))]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = closed[i], closed[j]
        seg = closed[i + 1 : j]
        ab = b - a
        denom = np.hypot(*ab)
        if denom == 0:
            d = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            d = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / denom
        k = int(np.argmax(d))
        if d[k] > tol:
            idx = i + 1 + k
            keep[idx] = True
            stack.extend([(i, idx), (idx, j)])
    return closed[keep]


def _clean_ring(ring: np.ndarray, tol: float, decimals: int, ccw: bool) -> list[list[float]] | None:
    ring = np.asarray(ring, dtype=float)
    if not np.allclose(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[:1]])
    ring = _simplify_ring(ring, tol)
    ring = np.round(ring, decimals)
    # Drop consecutive duplicates created by rounding.
    keep = np.ones(len(ring), dtype=bool)
    keep[1:] = np.any(np.diff(ring, axis=0) != 0, axis=1)
    ring = ring[keep]
    if not np.array_equal(ring[0], ring[-1]):
        ring = np.vstack([ring, ring[:1]])
    if len(ring) < 4 or abs(_ring_signed_area(ring)) == 0:
        return None
    if (_ring_signed_area(ring) > 0) != ccw:
        ring = ring[::-1]
    return ring.tolist()


def category_polygons(
    category: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    lower: float,
    upper: float,
    simplify_tol: float = 0.1,
    min_area: float = 0.0,
    decimals: int = 3,
) -> list[list[list[list[float]]]]:
    """Filled-contour polygons (GeoJSON MultiPolygon coordinates) for lower <= category < upper.

    Rings follow RFC 7946: exterior counter-clockwise, holes clockwise.
    """
    import contourpy

    lats = np.asarray(lats, dtype=float)
    lons = np.asarray(lons, dtype=float)
    field = np.asarray(category, dtype=float)

    # Longitudes to -180..180, sorted, then close the wrap at +180.
    lons = ((lons + 180.0) % 360.0) - 180.0
    order = np.argsort(lons)
    lons, field = lons[order], field[:, order]
    if np.isclose(lons[0], -180.0):
        lons = np.append(lons, 180.0)
        field = np.hstack([field, field[:, :1]])
    # Latitude ascending for contourpy.
    if lats[0] > lats[-1]:
        lats, field = lats[::-1], field[::-1, :]

    gen = contourpy.contour_generator(lons, lats, field, fill_type=contourpy.FillType.OuterOffset)
    points_list, offsets_list = gen.filled(lower, upper)

    polygons = []
    for pts, offs in zip(points_list, offsets_list):
        rings = [pts[offs[i] : offs[i + 1]] for i in range(len(offs) - 1)]
        if not rings:
            continue
        exterior = _clean_ring(rings[0], simplify_tol, decimals, ccw=True)
        if exterior is None or abs(_ring_signed_area(np.asarray(exterior))) < min_area:
            continue
        holes = [h for h in (_clean_ring(r, simplify_tol, decimals, ccw=False) for r in rings[1:]) if h is not None]
        polygons.append([exterior, *holes])
    return polygons


def write_upper_decile_exports(times, lats, lons, mask, pct, target, out_dir: Path, simplify_tol: float, min_area: float) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "upper_decile_precip_coverage.csv"
    pd.DataFrame(
        {"date": times.strftime("%Y-%m-01"), "pct_of_planet": np.round(pct, 2)}
    ).to_csv(csv_path, index=False)
    print(f"Saved: {csv_path} ({len(times)} months, {times.min():%B %Y} to {times.max():%B %Y})")

    # Target month = last time step (verified earlier to be the target month).
    latest = mask[-1].astype(np.int8)
    polys = category_polygons(latest, lats, lons, 0.5, 1.5, simplify_tol, min_area)
    features = []
    if polys:
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "category": "upper_decile",
                    "label": "Upper-decile precipitation",
                    "month": target.strftime("%B %Y"),
                    "compared_to": f"{target:%B} {times.min().year}-{times.max().year}",
                    "pct_of_planet": round(float(pct[-1]), 2),
                    "title": "Upper-decile precipitation",
                    "fill": UPPER_DECILE_COLOR,
                    "fill-opacity": 0.85,
                    "stroke": UPPER_DECILE_COLOR,
                    "stroke-width": 0,
                    "stroke-opacity": 0,
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            }
        )
    geojson_path = out_dir / "upper_decile_precip_areas.geojson"
    with open(geojson_path, "w") as f:
        _json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    print(
        f"Saved: {geojson_path} ({geojson_path.stat().st_size / 1e6:.2f} MB, {len(polys)} polygons; "
        f"{target:%B %Y} upper-decile coverage {pct[-1]:.2f}% of planet)"
    )
    return csv_path, geojson_path


if not ARGS.skip_datawrapper:
    write_upper_decile_exports(
        tp_times, tp_all["latitude"].values, tp_all["longitude"].values,
        tp_upper_decile_mask, tp_q90_pct, target_month, DATAWRAPPER_DIR, ARGS.geojson_simplify, ARGS.geojson_min_area)


if not ARGS.skip_upload:
    upload_ready_imagery(UPLOAD_READY_DIR, ARGS.aws_bin, ARGS.aws_profile, ARGS.bucket, ARGS.prefix)

print("\nERA5 extremes workflow complete.")
print(f"All files are under: {WORK_DIR}")
print(f"Dated imagery: {IMAGERY_DIR}")
print(f"Upload-ready static filenames: {UPLOAD_READY_DIR}")
