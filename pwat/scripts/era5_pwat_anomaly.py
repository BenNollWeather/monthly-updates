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
"""Download, plot, and optionally upload ERA5 precipitable-water imagery.

Cleaned script version of era5_pwat_anomaly.ipynb.

Outputs, styling, and annotations are preserved from the notebook while
centralizing paths, CDS downloads, plotting, and S3 upload URL printing.
"""


import argparse
import datetime as dt
import os
import subprocess
import time
from pathlib import Path

import cmocean
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import BoundaryNorm, Normalize
from matplotlib.lines import Line2D
from matplotlib.transforms import blended_transform_factory
import numpy as np
import pandas as pd
import seaborn as sns
import xarray as xr

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER


DEFAULT_IMAGE_DIR = Path(os.environ.get("WORK_ROOT", "/tmp/monthly-updates/pwat")) / "imagery"
DEFAULT_DOWNLOAD_DIR = Path(os.environ.get("WORK_ROOT", "/tmp/monthly-updates/pwat")) / "downloads"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create ERA5 atmospheric moisture imagery.")
    parser.add_argument("--image-dir", default=str(DEFAULT_IMAGE_DIR), help="Directory for output imagery.")
    parser.add_argument("--download-dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Directory for ERA5 NetCDF downloads.")
    parser.add_argument("--aws-bin", default="aws", help="Path to AWS CLI executable.")
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""), help="AWS profile for upload. Empty uses the ambient credentials.")
    parser.add_argument("--bucket", default="bennollweather", help="S3 bucket name.")
    parser.add_argument("--prefix", default="atmospheric_moisture", help="S3 prefix.")
    parser.add_argument("--skip-download", action="store_true", help="Use existing NetCDF files instead of downloading from CDS.")
    parser.add_argument("--skip-upload", action="store_true", help="Skip S3 upload.")
    parser.add_argument("--download-retries", type=int, default=3, help="Number of CDS download attempts before failing.")
    parser.add_argument("--retry-sleep", type=int, default=30, help="Seconds to wait between failed CDS download attempts.")
    parser.add_argument("--target-month", default=None, help="Force a specific month (YYYY-MM) instead of auto-detecting the latest available month.")
    parser.add_argument("--max-lookback", type=int, default=6, help="How many months back to search for the latest available ERA5 month.")
    parser.add_argument(
        "--plot-method",
        choices=("pcolormesh", "contourf"),
        default="pcolormesh",
        help="Use pcolormesh for faster map rendering or contourf for the closest notebook match.",
    )
    parser.add_argument(
        "--datawrapper-dir",
        default=None,
        help="Directory for Datawrapper CSV/GeoJSON exports (default: <image-dir>/datawrapper, so they sync to S3 too).",
    )
    parser.add_argument("--skip-datawrapper", action="store_true", help="Skip the Datawrapper CSV/GeoJSON exports.")
    parser.add_argument(
        "--geojson-simplify",
        type=float,
        default=0.1,
        help="Douglas-Peucker tolerance in degrees for the extremes GeoJSON (0 = no simplification).",
    )
    parser.add_argument(
        "--geojson-min-area",
        type=float,
        default=0.0,
        help="Drop polygons smaller than this many square degrees from the extremes GeoJSON.",
    )
    return parser.parse_args()


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


def target_month_info(target: pd.Timestamp) -> tuple[pd.Timestamp, str, str, str, str]:
    month1 = target.strftime("%b %Y")
    month2 = target.strftime("%B")
    download_month = target.strftime("%m")
    download_year = target.strftime("%Y")
    return target, month1, month2, download_month, download_year


def era5_years(end_year: int) -> list[str]:
    """1940 through the year of the latest available month."""
    return [str(year) for year in range(1940, end_year + 1)]


def _month_tag(target: pd.Timestamp) -> str:
    return target.strftime("%Y_%m")


def latest_local_month(download_dir: Path) -> pd.Timestamp | None:
    """For --skip-download: newest month with a valid single-month PWAT file already on disk."""
    stamps = []
    for path in download_dir.glob("pwat_*_*.nc"):
        tag = path.stem.replace("pwat_", "")
        try:
            stamp = pd.Timestamp(f"{tag.replace('_', '-')}-01")
        except Exception:
            continue
        if netcdf_is_valid(path):
            stamps.append(stamp)
    return max(stamps) if stamps else None


def resolve_target_month(args: argparse.Namespace, download_dir: Path) -> pd.Timestamp:
    if args.target_month:
        target = _parse_year_month(args.target_month)
        print(f"Using requested target month: {target:%B %Y}")
        return target
    if args.skip_download:
        target = latest_local_month(download_dir)
        if target is None:
            raise SystemExit("--skip-download was given but no previous download was found; pass --target-month YYYY-MM.")
        print(f"Using latest locally downloaded month: {target:%B %Y}")
        return target
    import cdsapi

    return find_latest_available_month(cdsapi.Client(), download_dir / "era5_probe", max_lookback=args.max_lookback)




def netcdf_is_valid(path: Path) -> bool:
    """Return True only when path exists and xarray can open it as a complete NetCDF file."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with xr.open_dataset(path) as ds:
            # Force a tiny metadata/data touch so truncated files fail early.
            _ = list(ds.data_vars)
            _ = dict(ds.sizes)
        return True
    except Exception:
        return False


def retrieve_with_retries(client, dataset: str, request: dict, target: Path, retries: int = 3, sleep_seconds: int = 30) -> None:
    """Retrieve a CDS NetCDF file with safeguards for incomplete chunked downloads."""
    target = Path(target)
    partial_candidates = [
        target,
        target.with_suffix(target.suffix + ".part"),
        target.with_suffix(target.suffix + ".tmp"),
        target.with_name(target.name + ".part"),
        target.with_name(target.name + ".tmp"),
    ]

    for attempt in range(1, retries + 1):
        if netcdf_is_valid(target):
            print(f"Valid existing NetCDF found: {target}")
            return

        for candidate in partial_candidates:
            if candidate.exists():
                print(f"Removing incomplete/invalid download: {candidate}")
                candidate.unlink()

        print(f"CDS download attempt {attempt}/{retries}: {target}")
        try:
            client.retrieve(dataset, request, str(target))
            if netcdf_is_valid(target):
                print(f"Download complete and NetCDF validated: {target}")
                return
            raise RuntimeError(f"Downloaded file is not a valid complete NetCDF: {target}")
        except Exception as exc:
            print(f"Download attempt {attempt} failed: {exc}")
            if target.exists():
                print(f"Removing failed partial file: {target}")
                target.unlink()
            if attempt == retries:
                raise
            print(f"Retrying in {sleep_seconds} seconds...")
            time.sleep(sleep_seconds)


def download_single_month_pwat(download_dir: Path, target: pd.Timestamp, skip_download: bool, retries: int, retry_sleep: int) -> Path:
    # File name includes the target month so a stale file from an earlier month is never reused.
    out_path = download_dir / f"pwat_{_month_tag(target)}.nc"
    download_month = target.strftime("%m")
    if skip_download and netcdf_is_valid(out_path):
        print(f"Using valid existing file: {out_path}")
        return out_path
    if skip_download and out_path.exists() and not netcdf_is_valid(out_path):
        print(f"Existing file is invalid/incomplete despite --skip-download: {out_path}")

    import cdsapi

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading ERA5 monthly total column water for month {download_month} to {out_path}")
    c = cdsapi.Client()
    retrieve_with_retries(
        c,
        "reanalysis-era5-single-levels-monthly-means",
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": "total_column_water",
            "year": era5_years(target.year),
            "month": download_month,
            "time": "00:00",
            "format": "netcdf",
        },
        out_path,
        retries=retries,
        sleep_seconds=retry_sleep,
    )
    return out_path


def download_all_month_pwat(download_dir: Path, target: pd.Timestamp, skip_download: bool, retries: int, retry_sleep: int) -> Path:
    out_path = download_dir / f"monthly_pwat_{_month_tag(target)}.nc"
    if skip_download and netcdf_is_valid(out_path):
        print(f"Using valid existing file: {out_path}")
        return out_path
    if skip_download and out_path.exists() and not netcdf_is_valid(out_path):
        print(f"Existing file is invalid/incomplete despite --skip-download: {out_path}")

    import cdsapi

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading ERA5 monthly total column water for all months to {out_path}")
    c = cdsapi.Client()
    retrieve_with_retries(
        c,
        "reanalysis-era5-single-levels-monthly-means",
        {
            "product_type": "monthly_averaged_reanalysis",
            "variable": "total_column_water",
            "year": era5_years(target.year),
            "month": [f"{month:02d}" for month in range(1, 13)],
            "time": "00:00",
            "format": "netcdf",
        },
        out_path,
        retries=retries,
        sleep_seconds=retry_sleep,
    )
    return out_path


def pcolor_or_contourf(ax, lons, lats, field, levels, cmap, transform, extend="both", method="pcolormesh"):
    if method == "contourf":
        return ax.contourf(lons, lats, field, levels=levels, extend=extend, cmap=cmap, transform=transform)
    cmap_obj = cmap if not isinstance(cmap, str) else plt.get_cmap(cmap)
    norm = BoundaryNorm(levels, ncolors=cmap_obj.N, extend=extend)
    return ax.pcolormesh(lons, lats, field, cmap=cmap_obj, norm=norm, shading="auto", transform=transform)


def add_bennoll_map_stamp(ax, fig):
    ax.text(
        0.01,
        0.02,
        "@BenNollWeather",
        horizontalalignment="left",
        verticalalignment="bottom",
        transform=ax.transAxes,
        color="white",
        weight="bold",
        fontsize=20,
        bbox=dict(facecolor="k", alpha=0.5, edgecolor="black", boxstyle="round"),
        zorder=100,
    )
    fig.patch.set_facecolor("k")


def make_monthly_anomaly(ds: xr.Dataset, target: pd.Timestamp) -> tuple[xr.DataArray, xr.DataArray, xr.DataArray]:
    clim = ds.sel(valid_time=slice("1991-01-01", "2020-12-31"))

    start_date = pd.Timestamp(year=target.year, month=target.month, day=1)
    end_date = start_date + pd.DateOffset(months=1) - pd.DateOffset(days=1)

    current_month_data = ds.sel(valid_time=slice(start_date, end_date))
    if current_month_data.sizes.get("valid_time", 0) == 0:
        raise RuntimeError(f"No data for {target:%B %Y} in the downloaded file.")

    clim_mean = clim.mean("valid_time")
    current_mean = current_month_data.mean("valid_time")

    anom = current_mean["tcw"] - clim_mean["tcw"]
    perc = (current_mean["tcw"] / clim_mean["tcw"]) * 100
    return clim_mean["tcw"], anom, perc


def plot_tcw_map(perc: xr.DataArray, anom: xr.DataArray, month1: str, image_dir: Path, method: str) -> Path:
    lon = perc["longitude"]
    lat = perc["latitude"]
    lons, lats = np.meshgrid(lon, lat)

    fig = plt.figure(figsize=(25, 15))
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

    levels = np.linspace(80, 120, 9)
    data = pcolor_or_contourf(
        ax,
        lons,
        lats,
        perc,
        levels=levels,
        extend="both",
        cmap=cmocean.cm.diff_r,
        transform=ccrs.PlateCarree(),
        method=method,
    )
    ax.contour(lons, lats, anom, np.arange(0, 0 + 0.01, 0.01), colors="k", linewidths=0.5, transform=ccrs.PlateCarree())

    states_provinces = cfeature.NaturalEarthFeature(
        category="cultural",
        name="admin_1_states_provinces_lines",
        scale="50m",
        facecolor="none",
    )

    ax.add_feature(cfeature.LAND)
    ax.coastlines(resolution="50m", color="k", linewidth=2)
    ax.add_feature(cfeature.BORDERS)
    ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
    ax.add_feature(states_provinces, edgecolor="k")

    gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=False, linewidth=1, color="k", alpha=0.5, linestyle="--")
    gl.xlabels_top = False
    gl.ylabels_right = False
    gl.xlines = True
    gl.ylocator = mticker.FixedLocator([-90, -60, -30, 0, 30, 60, 90])
    gl.xlocator = mticker.FixedLocator([0, 60, 120, 180, -120, -60, 0])
    gl.xformatter = LONGITUDE_FORMATTER
    gl.yformatter = LATITUDE_FORMATTER
    gl.xlabel_style = {"size": 12, "color": "white"}
    gl.ylabel_style = {"size": 12, "color": "white"}

    plt.title("ERA5 Total Column Water Anomaly (% of normal)", loc="left", fontsize=24, color="white", weight="bold")
    plt.title(f"{month1}", loc="right", fontsize=24, color="white", weight="bold")
    cbar = plt.colorbar(data, ax=ax, ticks=[80, 90, 100, 110, 120], pad=0.01, shrink=0.5, aspect=20)
    cbar.ax.tick_params(labelsize=20, color="white", labelcolor="white")
    cbar.ax.set_facecolor([1, 1, 1, 0])
    for label in cbar.ax.get_yticklabels():
        label.set_weight("bold")

    add_bennoll_map_stamp(ax, fig)
    ax.text(
        0.01,
        -0.03,
        "Climo: 1991-2020 ERA5",
        color="white",
        horizontalalignment="left",
        verticalalignment="bottom",
        transform=ax.transAxes,
        fontsize=12,
        weight="bold",
    )

    image_dir.mkdir(parents=True, exist_ok=True)
    out_path = image_dir / "tcw_map.png"
    plt.savefig(out_path, facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(f"Saved: {out_path}")
    return out_path


def print_moisture_anomaly_area(anom: xr.DataArray) -> None:
    latitude = anom["latitude"].values
    longitude = anom["longitude"].values
    grid_size = 111.0
    weighted_grid_size = grid_size * np.cos(np.deg2rad(latitude))
    grid_area = weighted_grid_size[:, np.newaxis] * np.deg2rad(np.diff(longitude))
    grid_area = np.hstack([grid_area, grid_area[:, -1][:, np.newaxis]])
    weighted_anom = anom * grid_area
    count = np.sum(weighted_anom > 0)
    total_grid_squares = np.prod(anom.shape)
    percentage = (count / total_grid_squares) * 100
    percentage_scalar = percentage.item()
    print(f"Percentage of grid squares with moisture anomalies greater than 0: {percentage_scalar:.2f}%")


def annual_weighted_series(ds: xr.Dataset) -> xr.Dataset:
    latitudes = ds["latitude"]
    cos_lat = np.cos(np.deg2rad(latitudes))
    weights = cos_lat / cos_lat.sum()
    annual = ds.resample(valid_time="YE").mean("valid_time")
    return annual.weighted(weights).mean("latitude").mean("longitude")


def prepare_ranked_annual_dataframe(annual: xr.Dataset, target_year: int) -> tuple[pd.DataFrame, int, int, float, float, float]:
    var = annual["tcw"] * 0.0393701
    var_df = var.to_dataframe().reset_index()

    sorted_df = var_df.sort_values("tcw", ascending=False).reset_index()
    sorted_df["valid_time"] = sorted_df["valid_time"].dt.year

    df_zeros = sorted_df * 0
    df_zeros.rename({"tcw": "zero", "index": "zero2", "valid_time": "zero3"}, axis=1, inplace=True)
    sorted_df = pd.concat([sorted_df, df_zeros], axis=1)

    median = var_df.tcw.median()
    p90 = var_df.tcw.quantile(0.9)
    p10 = var_df.tcw.quantile(0.1)
    print(median)
    print(p90)
    print(p10)

    min_val = np.around(var_df["tcw"].min(), 2)
    max_val = np.around(var_df["tcw"].max(), 2)
    print(min_val, max_val)

    current_year = target_year
    print(current_year)

    # No fallback to an earlier year: if the target year is missing, stop.
    df_current = sorted_df[sorted_df["valid_time"] == current_year]
    if df_current.empty:
        raise RuntimeError(f"{current_year} is missing from the annual series; refusing to rank a different year.")
    ranking = int(df_current.index[0]) + 1
    num_years = int(sorted_df.shape[0])
    print("Total number of years in annual ranking:", num_years)

    return sorted_df, current_year, ranking, num_years, min_val, max_val


def year_tick_labels(years: list[int]) -> list[str]:
    labels = []
    for year in years:
        if year % 10 == 0 or year == years[-1]:
            labels.append(str(year))
        else:
            labels.append("")
    return labels


def plot_ranked_annual_chart(sorted_df: pd.DataFrame, current_year: int, ranking: int, num_years: int, month2: str, image_dir: Path) -> Path:
    # Start from a clean plotting state so this chart renders correctly on the first run.
    plt.close("all")
    sns.reset_defaults()
    sns.set_theme(
        style="dark",
        rc={
            "axes.facecolor": "k",
            "figure.facecolor": "k",
            "savefig.facecolor": "k",
            "axes.edgecolor": "k",
            "text.color": "white",
            "axes.labelcolor": "white",
            "xtick.color": "white",
            "ytick.color": "white",
        },
    )
    plt.rcParams["font.family"] = "Libre Franklin"

    # sorted_df is ranked from moistest to driest for the ranking text.
    # For the chart itself, plot chronologically so the x-axis starts at 1940.
    chart_df = (
        sorted_df[["valid_time", "tcw"]]
        .dropna()
        .copy()
        .sort_values("valid_time")
        .reset_index(drop=True)
    )
    chart_df["valid_time"] = chart_df["valid_time"].astype(int)

    figure, axes = plt.subplots(figsize=(25, 15))
    figure.patch.set_facecolor("#000000")
    axes.set_facecolor("#000000")

    p = sns.lineplot(
        data=chart_df,
        x="valid_time",
        y="tcw",
        linewidth=10,
        color="white",
        ax=axes,
        zorder=100,
    )

    sns.scatterplot(
        data=chart_df,
        x="valid_time",
        y="tcw",
        hue="tcw",
        palette="Greens",
        s=325,
        edgecolor="white",
        linewidth=1,
        legend=False,
        ax=axes,
        zorder=101,
    )

    y_lo = float(chart_df["tcw"].min()) - 0.008
    y_hi = float(chart_df["tcw"].max()) + 0.016
    axes.set_ylim(y_lo, y_hi)
    # Keep the lowest label off the year labels along the bottom spine.
    y_start = np.ceil((y_lo + 0.012) * 50) / 50
    y_stop = np.floor((y_hi - 0.006) * 50) / 50
    axes.set_yticks(np.round(np.arange(y_start, y_stop + 0.001, 0.02), 2))

    median = chart_df["tcw"].median()
    p.axhline(median, linewidth=10, color="white", linestyle="--", alpha=0.5, zorder=90)
    p90 = chart_df["tcw"].quantile(0.9)
    p.axhline(p90, linewidth=10, color="white", linestyle="--", alpha=0.5, zorder=90)
    p10 = chart_df["tcw"].quantile(0.1)
    p.axhline(p10, linewidth=10, color="white", linestyle="--", alpha=0.5, zorder=90)

    min_year = int(chart_df["valid_time"].min())
    max_year = int(chart_df["valid_time"].max())
    # Names sit just to the right of the axes, on the line they describe.
    line_label = blended_transform_factory(axes.transAxes, axes.transData)
    for level, name in ((p90, "90th percentile"), (median, "Median"), (p10, "10th percentile")):
        axes.text(
            1.015,
            level,
            name,
            transform=line_label,
            color="white",
            weight="bold",
            fontsize=18,
            va="center",
            ha="left",
            clip_on=False,
            zorder=102,
        )

    first_tick = (min_year // 10) * 10
    if first_tick < min_year:
        first_tick += 10
    xticks = list(range(first_tick, max_year, 10))  # stop before current/latest year
    if min_year not in xticks:
        xticks = [min_year] + xticks

    p.set_xlim(min_year - 1, max_year + 1)
    p.set_xticks(xticks)
    p.set_xticklabels([str(year) for year in xticks])

    p.yaxis.set_tick_params(labelcolor="white", labelsize=30)
    p.xaxis.set_tick_params(labelcolor="white", labelsize=30)
    p.tick_params(left=True, bottom=True, right=False, top=False, width=2, colors="white")
    for spine in ["top", "bottom", "left", "right"]:
        p.spines[spine].set_visible(False)

    p.set_xlabel("")
    p.set_ylabel(
        "in.",
        color="white",
        fontsize=26,
        weight="bold",
        rotation=0,
        ha="right",
        va="center",
        labelpad=18,
    )
    p.yaxis.grid(False)
    p.xaxis.grid(False)

    moistest = "Moistest years: {}, {}, {}, {}".format(
        int(sorted_df["valid_time"].iloc[0]),
        int(sorted_df["valid_time"].iloc[1]),
        int(sorted_df["valid_time"].iloc[2]),
        int(sorted_df["valid_time"].iloc[3]),
    )
    figure.subplots_adjust(left=0.08, right=0.84, top=0.88, bottom=0.14)
    figure.text(
        0.08,
        0.945,
        f"Average Global Atmospheric Moisture during {month2}",
        color="white",
        weight="bold",
        fontsize=32,
        ha="left",
        va="center",
    )
    figure.text(
        0.98,
        0.945,
        moistest,
        color="white",
        weight="bold",
        fontsize=22,
        ha="right",
        va="center",
    )
    figure.text(0.08, 0.035, "Data: ERA5", color="white", weight="bold", fontsize=18, ha="left", va="center")
    figure.text(0.20, 0.035, "@BenNollWeather", color="white", weight="bold", fontsize=18, ha="left", va="center")
    figure.text(
        0.98,
        0.035,
        f"{current_year} ranking: {ranking} out of {num_years}",
        color="white",
        weight="bold",
        fontsize=26,
        ha="right",
        va="center",
    )

    plt.setp(p.get_xticklabels(), fontweight="bold")
    plt.setp(p.get_yticklabels(), fontweight="bold")
    # Seaborn remaps the shorthand "k" to a dark gray. Use real black.
    figure.patch.set_facecolor("#000000")
    axes.set_facecolor("#000000")

    image_dir.mkdir(parents=True, exist_ok=True)
    out_path = image_dir / "tcw_chart.png"
    figure.savefig(out_path, dpi=200, facecolor="#000000", bbox_inches="tight")
    plt.close(figure)
    print(f"Saved: {out_path}")
    return out_path

def plot_moistening_stripes(annual: xr.Dataset, image_dir: Path) -> Path:
    tcw = annual["tcw"].values
    norm = Normalize(vmin=np.percentile(tcw, 2), vmax=np.percentile(tcw, 98))
    tcw_smooth = np.convolve(tcw, np.ones(1) / 1, mode="same")

    fig = plt.figure(figsize=(12, 6), dpi=300)
    ax = plt.gca()
    ax.imshow(tcw_smooth.reshape(1, -1), aspect="auto", cmap=cmocean.cm.diff_r, interpolation="none", norm=norm)
    ax.axis("off")
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    image_dir.mkdir(parents=True, exist_ok=True)
    out_path = image_dir / "moistening_stripes.png"
    plt.savefig(out_path, dpi=300, bbox_inches="tight", pad_inches=0, transparent=True)
    plt.close(fig)
    print(f"Saved: {out_path}")
    return out_path


def open_monthly_dataset(path: Path) -> xr.Dataset:
    dset = xr.open_dataset(path)
    if "valid_time" in dset.coords or "valid_time" in dset.dims:
        dset = dset.rename({"valid_time": "time"})
    dset["year_month"] = dset["time"].dt.strftime("%Y-%m")
    dset = dset.assign_coords({"year_month": dset["year_month"]})
    return dset


def weighted_monthly_series_for_year(dset: xr.Dataset, year: int, months: np.ndarray, cos_lat: xr.DataArray) -> np.ndarray | None:
    year_month_str = [f"{year}-{str(month).zfill(2)}" for month in months]
    valid_year_month_str = [ym for ym in year_month_str if ym in dset["year_month"].values]
    if not valid_year_month_str:
        return None

    indices = [np.where(dset["year_month"].values == ym)[0][0] for ym in valid_year_month_str]

    # Dimension-aware weighting avoids xarray's "too many indices" error.
    weights = cos_lat
    if "latitude" not in weights.dims:
        weights = xr.DataArray(weights.values, dims=("latitude",), coords={"latitude": dset["latitude"]})

    selected = dset["tcw"].isel(time=indices)
    tcw_weighted_mean = selected.weighted(weights).mean(dim=("latitude", "longitude"))
    return tcw_weighted_mean.values / 25.4


def plot_monthly_comparison(dset: xr.Dataset, image_dir: Path) -> Path:
    sns.set(
        rc={
            "axes.facecolor": "k",
            "figure.facecolor": "k",
            "savefig.facecolor": "k",
            "text.color": "white",
            "axes.labelcolor": "white",
            "xtick.color": "white",
            "ytick.color": "white",
        }
    )
    figure, axes = plt.subplots(figsize=(25, 15))
    figure.patch.set_facecolor("#000000")
    axes.set_facecolor("#000000")

    years = np.unique(dset["time"].dt.year.values)
    months = np.arange(1, 13)
    latitudes = dset["latitude"]
    cos_lat = np.cos(np.deg2rad(latitudes))

    highlight_years = [2023, 2024, 2025, 2026]
    highlight_colors = ["#E69F00", "#D55E00", "#0072B2", "#CC79A7"]

    # Keep the historical comparison lines separate from the highlighted years.
    for year in years:
        if int(year) <= 2022:
            try:
                tcw_mean_inch = weighted_monthly_series_for_year(dset, int(year), months, cos_lat)
                if tcw_mean_inch is not None:
                    sns.lineplot(x=months[: len(tcw_mean_inch)], y=tcw_mean_inch, ax=axes, color="lightgray", alpha=0.4, linewidth=2)
            except KeyError as exc:
                print(f"KeyError while selecting year {year}: {exc}")

    # Calculate the monthly 1991-2020 average from the same area-weighted series.
    climatology_series = []
    for year in range(1991, 2021):
        tcw_mean_inch = weighted_monthly_series_for_year(dset, year, months, cos_lat)
        if tcw_mean_inch is not None and len(tcw_mean_inch) == len(months):
            climatology_series.append(tcw_mean_inch)
    if not climatology_series:
        raise ValueError("No complete 1991-2020 monthly series were available for the climatology.")
    climatology_mean = np.nanmean(np.vstack(climatology_series), axis=0)
    sns.lineplot(
        x=months,
        y=climatology_mean,
        ax=axes,
        color="white",
        linestyle="--",
        linewidth=6,
        zorder=90,
    )

    for year, color in zip(highlight_years, highlight_colors):
        try:
            tcw_mean_inch = weighted_monthly_series_for_year(dset, year, months, cos_lat)
            if tcw_mean_inch is not None:
                sns.lineplot(x=months[: len(tcw_mean_inch)], y=tcw_mean_inch, ax=axes, color=color, label=str(year), linewidth=10)
        except KeyError as exc:
            print(f"KeyError while selecting year {year}: {exc}")

    axes.yaxis.set_tick_params(labelcolor="white", labelsize=30)
    axes.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))
    axes.set_ylabel(
        "in.",
        color="white",
        fontsize=26,
        weight="bold",
        rotation=0,
        ha="right",
        va="center",
        labelpad=18,
    )
    axes.xaxis.set_tick_params(labelcolor="white", labelsize=30)
    axes.set_xticks(months)
    axes.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], fontsize=30, fontweight="bold")
    axes.tick_params(axis="y", left=False, right=False, length=0, colors="white")
    axes.tick_params(axis="x", bottom=True, top=False, width=2, colors="white")

    for spine in ["top", "bottom", "left", "right"]:
        axes.spines[spine].set_visible(False)
    axes.yaxis.grid(True, color="white", linewidth=0.5, alpha=0.3)
    axes.xaxis.grid(False)
    axes.set_axisbelow(True)

    axes.set_title(
        "Monthly global precipitable water",
        loc="left",
        color="white",
        weight="bold",
        fontsize=36,
        pad=16,
    )

    legend_handles = [
        Line2D([0], [0], color="white", linestyle="--", linewidth=6, label="1991-2020 average"),
        Line2D([0], [0], color="lightgray", alpha=0.8, linewidth=2, label="1940-2022"),
        *[
            Line2D([0], [0], color=color, linewidth=10, label=str(year))
            for year, color in zip(highlight_years, highlight_colors)
        ],
    ]
    axes.legend(
        handles=legend_handles[::-1],
        fontsize=22,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=6,
        frameon=False,
        labelcolor="white",
        borderaxespad=0.0,
        columnspacing=1.2,
        handlelength=2.2,
        handletextpad=0.5,
    )

    figure.patch.set_facecolor("#000000")
    axes.set_facecolor("#000000")
    plt.setp(axes.get_xticklabels(), fontweight="bold")
    plt.setp(axes.get_yticklabels(), fontweight="bold")
    figure.subplots_adjust(left=0.08, right=0.98, top=0.90, bottom=0.22)
    figure.text(0.08, 0.035, "Data: ERA5", color="white", weight="bold", fontsize=18, ha="left", va="center")
    figure.text(0.20, 0.035, "@BenNollWeather", color="white", weight="bold", fontsize=18, ha="left", va="center")

    image_dir.mkdir(parents=True, exist_ok=True)
    out_path = image_dir / "tcw_monthly_chart.png"
    figure.savefig(out_path, dpi=200, facecolor="#000000", bbox_inches="tight")
    plt.close(figure)
    print(f"Saved: {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Datawrapper exports
# ---------------------------------------------------------------------------
# Two wide CSVs (rows = month dated in the target year, columns = years), in
# the same layout as nino34_wide_new_baseline.csv, plus a GeoJSON of grid
# areas where the target month ranked as a record / top-5% / top-10% month.

DATAWRAPPER_DATE_COL = "this_year_date"
CLIM_START, CLIM_END = 1991, 2020

# Exclusive bands so the polygons never overlap in Datawrapper.
EXTREME_BANDS = (
    # (code, key, label, fill colour)
    (1, "p90", "90th-95th percentile", "#a1d99b"),
    (2, "p95", "95th percentile or higher", "#31a354"),
    (3, "record", "Record high", "#00441b"),
)


def global_monthly_series_inches(dset: xr.Dataset) -> pd.Series:
    """Cos(lat)-weighted global-mean TCW for every month in the file, in inches."""
    weights = np.cos(np.deg2rad(dset["latitude"]))
    weights = xr.DataArray(weights.values, dims=("latitude",), coords={"latitude": dset["latitude"]})
    times = pd.DatetimeIndex(pd.to_datetime(dset["time"].values))
    pieces = []
    # One year at a time keeps memory bounded for the full 0.25-degree grid.
    for year in np.unique(times.year):
        idx = np.where(times.year == year)[0]
        tcw = dset["tcw"].isel(time=idx)
        extra_dims = [d for d in tcw.dims if d not in ("time", "latitude", "longitude")]
        if extra_dims:  # e.g. legacy expver dimension
            tcw = tcw.max(extra_dims)
        vals = tcw.weighted(weights).mean(dim=("latitude", "longitude")).values / 25.4
        pieces.append(pd.Series(np.asarray(vals, dtype=float), index=times[idx]))
    series = pd.concat(pieces).sort_index()
    series = series.groupby(series.index).mean()
    series.index = pd.DatetimeIndex(series.index)
    return series


def monthly_wide_tables(series: pd.Series, target_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pivot a monthly series to Datawrapper-wide raw and anomaly tables."""
    df = pd.DataFrame({"year": series.index.year, "month": series.index.month, "value": series.values})
    raw = df.pivot_table(index="month", columns="year", values="value", aggfunc="mean").reindex(range(1, 13))

    clim_cols = [y for y in raw.columns if CLIM_START <= y <= CLIM_END]
    if len(clim_cols) < (CLIM_END - CLIM_START + 1):
        print(f"Warning: only {len(clim_cols)} climatology years available for {CLIM_START}-{CLIM_END}.")
    clim = raw[clim_cols].mean(axis=1)
    # Percent difference from the 1991-2020 mean for each calendar month.
    anom = raw.sub(clim, axis=0).div(clim, axis=0) * 100.0

    def _fmt(table: pd.DataFrame) -> pd.DataFrame:
        out = table.copy()
        out.index = [f"{target_year}-{m:02d}-01" for m in out.index]
        out.index.name = DATAWRAPPER_DATE_COL
        out.columns = [str(c) for c in out.columns]
        return out

    return _fmt(raw), _fmt(anom)


def write_datawrapper_csvs(series: pd.Series, target_year: int, out_dir: Path) -> tuple[Path, Path]:
    raw, anom = monthly_wide_tables(series, target_year)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "pwat_monthly_inches_wide.csv"
    anom_path = out_dir / "pwat_monthly_anomaly_pct_wide.csv"
    raw.to_csv(raw_path, float_format="%.3f")
    anom.to_csv(anom_path, float_format="%.2f")
    print(f"Saved: {raw_path}")
    print(f"Saved: {anom_path} (% difference from {CLIM_START}-{CLIM_END} monthly mean)")
    return raw_path, anom_path


def classify_extremes(current: np.ndarray, prior: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Classify each grid cell of `current` against the same month in prior years.

    Returns (category, percentile_rank). percentile_rank is the share of prior
    years with a lower value. Categories: 0 none, 1 >=90th, 2 >=95th, 3 record.
    """
    n_valid = np.sum(np.isfinite(prior), axis=0)
    below = np.sum(prior < current[np.newaxis, ...], axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        pct_rank = np.where(n_valid > 0, 100.0 * below / n_valid, np.nan)
    prior_max = np.nanmax(np.where(np.isfinite(prior), prior, -np.inf), axis=0)

    category = np.zeros(current.shape, dtype=np.int8)
    category[pct_rank >= 90] = 1
    category[pct_rank >= 95] = 2
    category[(current > prior_max) & (n_valid > 0)] = 3
    category[~np.isfinite(current)] = 0
    return category, pct_rank


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


def area_fraction(mask: np.ndarray, lats: np.ndarray) -> float:
    """Share of the globe's surface (cos-lat weighted) covered by mask, in percent."""
    w = np.cos(np.deg2rad(np.asarray(lats, dtype=float)))[:, np.newaxis] * np.ones(mask.shape[1])
    return float(100.0 * np.sum(w * mask) / np.sum(w))


def build_extremes_geojson(
    category: np.ndarray,
    lats: np.ndarray,
    lons: np.ndarray,
    target: pd.Timestamp,
    first_year: int,
    simplify_tol: float = 0.1,
    min_area: float = 0.0,
) -> dict:
    features = []
    for code, key, label, color in EXTREME_BANDS:
        mask = category == code
        if not mask.any():
            print(f"  {label}: no grid cells")
            continue
        pct_globe = area_fraction(mask, lats)
        polys = category_polygons(category, lats, lons, code - 0.5, code + 0.5, simplify_tol, min_area)
        if not polys:
            continue
        print(f"  {label}: {pct_globe:.2f}% of globe, {len(polys)} polygons")
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "category": key,
                    "label": label,
                    "month": target.strftime("%B %Y"),
                    "compared_to": f"{target:%B} {first_year}-{target.year - 1}",
                    "pct_of_globe": round(pct_globe, 2),
                    # simplestyle-spec properties (read by Datawrapper locator maps)
                    "title": label,
                    "fill": color,
                    "fill-opacity": 0.85,
                    "stroke": color,
                    "stroke-width": 0,
                    "stroke-opacity": 0,
                },
                "geometry": {"type": "MultiPolygon", "coordinates": polys},
            }
        )
    # Combined top-10% footprint, handy for a single highlight layer.
    any_mask = category >= 1
    print(f"  Any (>= 90th percentile): {area_fraction(any_mask, lats):.2f}% of globe")
    return {"type": "FeatureCollection", "features": features}


def record_high_share_by_year(values: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Share of the planet (cos-lat weighted, %) where each year holds the all-time record high.

    values: (year, lat, lon) for one calendar month. Every grid cell is credited
    to the single year with its highest value across the whole record (latest
    year included), so the shares sum to 100. Cells with no data are excluded.
    """
    valid = np.any(np.isfinite(values), axis=0)
    filled = np.where(np.isfinite(values), values, -np.inf)
    record_year_idx = np.argmax(filled, axis=0)  # ties go to the earliest year
    w2d = np.clip(np.cos(np.deg2rad(np.asarray(lats, dtype=float))), 0.0, None)[:, np.newaxis] * np.ones(values.shape[-1])
    w2d = np.where(valid, w2d, 0.0)
    share = np.bincount(record_year_idx.ravel(), weights=w2d.ravel(), minlength=values.shape[0])
    return 100.0 * share / w2d.sum()


def write_record_high_csv(ds: xr.Dataset, target: pd.Timestamp, out_dir: Path) -> Path:
    """CSV of the share of the planet where each year holds the record-high PWAT for the target month."""
    tcw = ds["tcw"]
    time_dim = "valid_time" if "valid_time" in tcw.dims else "time"
    extra_dims = [d for d in tcw.dims if d not in (time_dim, "latitude", "longitude")]
    if extra_dims:
        tcw = tcw.max(extra_dims)
    times = pd.DatetimeIndex(pd.to_datetime(tcw[time_dim].values))
    idx = np.where(times.month == target.month)[0]
    idx = idx[np.argsort(times[idx])]
    times = times[idx]
    values = tcw.isel({time_dim: idx}).transpose(time_dim, "latitude", "longitude").values

    share = record_high_share_by_year(values, tcw["latitude"].values)
    df = pd.DataFrame({"date": times.strftime("%Y-%m-01"), "pct_of_planet_record_high": np.round(share, 2)})

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pwat_record_high_coverage.csv"
    df.to_csv(out_path, index=False)
    print(
        f"Saved: {out_path} ({target:%B} {times.year.min()}-{target.year}; shares sum to {share.sum():.2f}%; "
        f"{target:%B %Y} holds the record over {share[-1]:.2f}% of the planet)"
    )
    return out_path


def write_extremes_geojson(
    ds: xr.Dataset,
    target: pd.Timestamp,
    out_dir: Path,
    simplify_tol: float,
    min_area: float,
) -> Path:
    import json

    tcw = ds["tcw"]
    time_dim = "valid_time" if "valid_time" in tcw.dims else "time"
    extra_dims = [d for d in tcw.dims if d not in (time_dim, "latitude", "longitude")]
    if extra_dims:
        tcw = tcw.max(extra_dims)
    times = pd.DatetimeIndex(pd.to_datetime(tcw[time_dim].values))
    same_month = times.month == target.month
    cur_idx = np.where(same_month & (times.year == target.year))[0]
    prior_idx = np.where(same_month & (times.year < target.year))[0]
    if len(cur_idx) == 0 or len(prior_idx) == 0:
        raise RuntimeError(f"Need {target:%B %Y} and earlier {target:%B}s to rank extremes.")

    current = tcw.isel({time_dim: cur_idx}).mean(time_dim).transpose("latitude", "longitude").values
    prior = tcw.isel({time_dim: prior_idx}).transpose(time_dim, "latitude", "longitude").values
    category, _ = classify_extremes(current, prior)

    first_year = int(times[prior_idx].year.min())
    print(f"Ranking {target:%B %Y} PWAT against {target:%B} {first_year}-{target.year - 1}:")
    gj = build_extremes_geojson(
        category, tcw["latitude"].values, tcw["longitude"].values, target, first_year, simplify_tol, min_area
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pwat_extremes.geojson"
    with open(out_path, "w") as f:
        json.dump(gj, f, separators=(",", ":"))
    print(f"Saved: {out_path} ({out_path.stat().st_size / 1e6:.2f} MB)")
    return out_path


def upload_imagery(image_dir: Path, aws_bin: str, aws_profile: str, bucket: str, prefix: str) -> list[str]:
    s3_path = f"s3://{bucket}/{prefix}/"
    cmd_sync = [
        aws_bin,
        "s3",
        "sync",
        str(image_dir),
        s3_path,
        "--exclude",
        ".git/*",
        "--exclude",
        ".gitignore",
        "--exclude",
        ".DS_Store",
        "--exclude",
        ".gitattributes",
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

    base_url = f"https://{bucket}.s3.amazonaws.com/{prefix}/"
    urls: list[str] = []
    for line in result.stdout.splitlines():
        if "upload:" in line:
            s3_file = line.split(" to ")[-1].strip()
            relative_path = s3_file.replace(s3_path, "")
            urls.append(base_url + relative_path)

    print("\nUploaded file URLs:\n")
    for url in urls:
        print(url)
    if not urls:
        print("No new or updated files were uploaded by aws s3 sync.")
    return urls


def main() -> None:
    args = parse_args()
    image_dir = Path(args.image_dir)
    download_dir = Path(args.download_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    target = resolve_target_month(args, download_dir)
    target, month1, month2, _, _ = target_month_info(target)

    single_month_path = download_single_month_pwat(download_dir, target, args.skip_download, args.download_retries, args.retry_sleep)
    ds = xr.open_dataset(single_month_path)
    # The last time step must be the target month, so preceding years are all
    # matched to that month and nothing falls back to the previous year.
    verify_latest_month(ds["valid_time"].values, target, label=f"{single_month_path.name}")
    _, anom, perc = make_monthly_anomaly(ds, target)
    plot_tcw_map(perc, anom, month1, image_dir, args.plot_method)
    print_moisture_anomaly_area(anom)

    datawrapper_dir = Path(args.datawrapper_dir) if args.datawrapper_dir else image_dir / "datawrapper"
    if not args.skip_datawrapper:
        write_extremes_geojson(ds, target, datawrapper_dir, args.geojson_simplify, args.geojson_min_area)
        write_record_high_csv(ds, target, datawrapper_dir)

    annual = annual_weighted_series(xr.open_dataset(single_month_path))
    sorted_df, current_year, ranking, num_years, _, _ = prepare_ranked_annual_dataframe(annual, target.year)
    plot_ranked_annual_chart(sorted_df, current_year, ranking, num_years, month2, image_dir)
    plot_moistening_stripes(annual, image_dir)

    monthly_path = download_all_month_pwat(download_dir, target, args.skip_download, args.download_retries, args.retry_sleep)
    monthly = open_monthly_dataset(monthly_path)
    # Keep the monthly comparison consistent with the target month.
    monthly = monthly.isel(time=(monthly["time"] < target + pd.DateOffset(months=1)).values)
    verify_latest_month(monthly["time"].values, target, label=f"{monthly_path.name}")
    plot_monthly_comparison(monthly, image_dir)

    if not args.skip_datawrapper:
        series = global_monthly_series_inches(monthly)
        write_datawrapper_csvs(series, target.year, datawrapper_dir)

    if not args.skip_upload:
        upload_imagery(image_dir, args.aws_bin, args.aws_profile, args.bucket, args.prefix)


if __name__ == "__main__":
    main()
