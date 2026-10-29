#!/usr/bin/env python3

import os as _os
_WORK = _os.environ.get("WORK_ROOT", _os.path.join(_os.environ.get("TMPDIR", "/tmp"), "monthly-updates", "operational"))
_SHAPES = _os.environ.get("SHAPEFILES_DIR", _os.path.join(_WORK, "shapefiles"))

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
"""Hudson Valley climate-change chart pipeline.

Refactored from climate_change-hv.ipynb.

Outputs PNG imagery to a disposable work folder and leaves
uploading to AWS to the bash runner.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import os
import ssl
import time
import zipfile
from pathlib import Path
from shutil import copyfileobj

os.environ.setdefault("MPLBACKEND", "Agg")
os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
os.environ.setdefault("CURL_CA_BUNDLE", "")
os.environ.setdefault("REQUESTS_CA_BUNDLE", "")

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

import numpy as np
import pandas as pd
import xarray as xr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

try:
    import cmocean  # noqa: F401 - registers cmocean colormaps
except Exception:
    cmocean = None


DEFAULT_WORK_ROOT = Path("DISPOSABLE/hv_climate_change_work")
DEFAULT_IMAGE_DIR = DEFAULT_WORK_ROOT / "imagery"
DEFAULT_DATA_DIR = DEFAULT_WORK_ROOT / "data"

AREA = [41.9, -74.8, 40.9, -73.5]
AREA_LABEL = "Data: ERA5 | [-74.8°W to -73.5°W, 40.9°N to 41.9°N]"

VARIABLES = [
    "2m_dewpoint_temperature",
    "2m_temperature",
    "convective_available_potential_energy",
    "instantaneous_10m_wind_gust",
    "snowfall",
    "total_cloud_cover",
    "total_column_water",
    "total_precipitation",
]

CHARTS = [
    {
        "key": "t2m",
        "source": "t2m",
        "outfile": "temperature.png",
        "title": "Annual average temperatures",
        "superlative": "Warmest",
        "low_superlative": "Coolest",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.thermal",
        "units_label": "°F",
        "top_with_values": True,
        "transform": lambda da: ((da - 273.15) * 1.8) + 32,
        "ascending": False,
    },
    {
        "key": "d2m",
        "source": "d2m",
        "outfile": "dew_point.png",
        "title": "Annual average dew point temperatures",
        "superlative": "Most humid",
        "low_superlative": "Least humid",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.thermal",
        "units_label": "°F",
        "top_with_values": False,
        "transform": lambda da: ((da - 273.15) * 1.8) + 32,
        "ascending": False,
    },
    {
        "key": "tp",
        "source": "tp",
        "outfile": "rainfall.png",
        "title": "Annual rainfall",
        "superlative": "Wettest",
        "low_superlative": "Driest",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.rain",
        "units_label": "in",
        "top_with_values": True,
        "transform": lambda da: (da * 39.3701) * 365.0,
        "ascending": False,
    },
    {
        "key": "tcw",
        "source": "tcw",
        "outfile": "tcw.png",
        "title": "Annual average atmospheric moisture levels",
        "superlative": "Moistest",
        "low_superlative": "Least moist",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.algae",
        "units_label": "in",
        "top_with_values": False,
        "transform": lambda da: da * 0.0393701,
        "ascending": False,
    },
    {
        "key": "sf",
        "source": "sf",
        "outfile": "snow.png",
        "title": "Annual snowfall",
        "superlative": "Snowiest",
        "low_superlative": "Least snowy",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.ice",
        "units_label": "in",
        "top_with_values": False,
        "transform": lambda da: (da * 39.3701) * 365.0 * 10.0,
        "ascending": False,
    },
    {
        "key": "i10fg",
        "source": "i10fg",
        "outfile": "wind.png",
        "title": "Annual average wind gust speeds",
        "superlative": "Windiest",
        "low_superlative": "Least windy",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.solar",
        "units_label": "mph",
        "top_with_values": False,
        "transform": lambda da: da * 2.23694,
        "ascending": False,
    },
    {
        "key": "cape",
        "source": "cape",
        "outfile": "storm.png",
        "title": "Annual average thunderstorm fuel levels",
        "superlative": "Most fuel",
        "low_superlative": "Least fuel",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.amp",
        "units_label": "J/kg",
        "top_with_values": False,
        "transform": lambda da: da,
        "ascending": False,
    },
    {
        "key": "tcc",
        "source": "tcc",
        "outfile": "clouds.png",
        "title": "Annual average cloud cover",
        "superlative": "Cloudiest",
        "low_superlative": "Least cloudy",
        "ranking_label": "{year} ranking: {ranking} out of {num_years}",
        "palette": "cmo.delta",
        "units_label": "%",
        "top_with_values": False,
        "transform": lambda da: da * 100.0,
        "ascending": False,
    },
]


def download_era5(data_dir: Path, target_year: int, retries: int, retry_sleep: int, skip_download: bool) -> Path:
    """Download ERA5 Hudson Valley data one variable at a time, then merge locally.

    This checks for already-downloaded valid files first. If the merged file exists
    and validates, it is reused automatically. If individual variable files exist
    and validate, they are reused and only missing/corrupt variables are downloaded.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    merged_target = data_dir / "hv_cc_era5_merged.nc"
    variable_dir = data_dir / "variables"
    variable_dir.mkdir(parents=True, exist_ok=True)

    if merged_target.exists() and merged_target.stat().st_size > 0:
        try:
            validate_download(merged_target)
            print(f"Using existing validated merged ERA5 file: {merged_target}")
            return merged_target
        except Exception as exc:
            print(f"Existing merged file failed validation and will be rebuilt: {merged_target} ({exc})")
            with contextlib.suppress(Exception):
                merged_target.unlink()

    import cdsapi

    years = [str(y) for y in range(1940, target_year + 1)]
    dataset = "reanalysis-era5-single-levels-monthly-means"
    client = cdsapi.Client()

    variable_files: list[Path] = []

    for variable in VARIABLES:
        target = variable_dir / f"{variable}.nc"
        variable_files.append(target)

        if target.exists() and target.stat().st_size > 0:
            try:
                validate_download(target)
                print(f"Using existing validated variable file: {target}")
                continue
            except Exception as exc:
                print(f"Existing variable file failed validation and will be redownloaded: {target} ({exc})")
                with contextlib.suppress(Exception):
                    target.unlink()

        if skip_download:
            raise FileNotFoundError(
                f"--skip-download was set, but valid cached file is missing for {variable}: {target}"
            )

        request = {
            "product_type": ["monthly_averaged_reanalysis"],
            "variable": [variable],
            "year": years,
            "month": [f"{m:02d}" for m in range(1, 13)],
            "time": ["00:00"],
            "area": AREA,
            "data_format": "netcdf",
            "download_format": "unarchived",
        }

        last_error = None
        for attempt in range(1, retries + 1):
            try:
                if target.exists():
                    target.unlink()
                print(f"Downloading ERA5 variable {variable} attempt {attempt}/{retries}: {target}")
                client.retrieve(dataset, request).download(str(target))
                validate_download(target)
                print(f"Download complete and validated: {target}")
                break
            except Exception as exc:
                last_error = exc
                print(f"Download attempt {attempt}/{retries} failed for {variable}: {exc}")
                with contextlib.suppress(Exception):
                    if target.exists():
                        target.unlink()
                if attempt < retries:
                    print(f"Retrying in {retry_sleep} seconds")
                    time.sleep(retry_sleep)
                else:
                    raise RuntimeError(f"ERA5 download failed for {variable} after {retries} attempts") from last_error

    print("Merging variable NetCDF files")
    datasets = []
    for file in variable_files:
        if not file.exists() or file.stat().st_size == 0:
            raise FileNotFoundError(f"Missing variable file after download/cache check: {file}")
        ds = xr.open_dataset(file)
        ds = normalize_dataset(ds)
        datasets.append(ds)

    merged = xr.merge(datasets, compat="override", join="outer")
    if "expver" in merged.dims:
        merged = merged.mean("expver", skipna=True)

    if merged_target.exists():
        merged_target.unlink()
    merged.to_netcdf(merged_target)
    for ds in datasets:
        with contextlib.suppress(Exception):
            ds.close()
    with contextlib.suppress(Exception):
        merged.close()

    validate_download(merged_target)
    print(f"Merged ERA5 file written: {merged_target}")
    return merged_target

def validate_download(path: Path) -> None:
    """Validate that a downloaded file can be opened as NetCDF or ZIP of NetCDFs."""
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"Downloaded file is missing or empty: {path}")

    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            nc_names = [n for n in z.namelist() if n.endswith(".nc")]
            if not nc_names:
                raise RuntimeError(f"ZIP has no .nc files: {path}")
        return

    with xr.open_dataset(path) as ds:
        if not ds.data_vars:
            raise RuntimeError(f"No data variables found in: {path}")


def find_or_open_dataset(download_path: Path, data_dir: Path, input_file: str | None = None) -> xr.Dataset:
    """Open downloaded ERA5 data, supporting one NetCDF, zip of NetCDFs, or user-supplied files."""
    if input_file:
        path = Path(input_file).expanduser()
    else:
        path = download_path

    if not path.exists():
        raise FileNotFoundError(path)

    files: list[Path]
    if path.is_dir():
        files = sorted(path.rglob("*.nc"))
    elif zipfile.is_zipfile(path):
        extract_dir = data_dir / "extracted"
        if extract_dir.exists():
            import shutil
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as z:
            z.extractall(extract_dir)
        files = sorted(extract_dir.rglob("*.nc"))
    else:
        files = [path]

    if not files:
        raise FileNotFoundError(f"No NetCDF files found in {path}")

    datasets = []
    for file in files:
        print(f"Opening dataset: {file}")
        ds = xr.open_dataset(file)
        ds = normalize_dataset(ds)
        datasets.append(ds)

    if len(datasets) == 1:
        return datasets[0]

    # CDS sometimes returns split files; merge variables with compatible coords.
    merged = xr.merge(datasets, compat="override", join="outer")
    return merged


def normalize_dataset(ds: xr.Dataset) -> xr.Dataset:
    """Normalize ERA5 coordinate names/dims and remove expver if present."""
    rename_map = {}
    if "time" in ds.coords and "valid_time" not in ds.coords:
        rename_map["time"] = "valid_time"
    if rename_map:
        ds = ds.rename(rename_map)

    if "expver" in ds.dims:
        ds = ds.mean("expver", skipna=True)

    return ds


def annual_area_mean(ds: xr.Dataset) -> xr.Dataset:
    """Annual mean over time, latitude, and longitude."""
    time_dim = "valid_time" if "valid_time" in ds.coords or "valid_time" in ds.dims else "time"
    ds = ds.resample({time_dim: "YE"}).mean(time_dim, skipna=True)

    for dim in ("latitude", "longitude"):
        if dim in ds.dims:
            ds = ds.mean(dim, skipna=True)

    return ds


def series_from_dataset(ds: xr.Dataset, chart: dict) -> pd.DataFrame:
    """Return chronological annual dataframe for one chart."""
    source = chart["source"]
    if source not in ds:
        raise KeyError(f"Variable {source!r} not found. Available variables: {list(ds.data_vars)}")

    da = chart["transform"](ds[source])
    time_dim = "valid_time" if "valid_time" in da.coords else "time"

    df = da.to_dataframe(name=chart["key"]).reset_index()
    if time_dim not in df:
        # Some xarray conversions use index name
        time_candidates = [c for c in df.columns if "time" in str(c)]
        if not time_candidates:
            raise KeyError(f"Could not find time column in dataframe columns: {df.columns}")
        time_dim = time_candidates[0]

    df["year"] = pd.to_datetime(df[time_dim]).dt.year
    df = df[["year", chart["key"]]].dropna()
    df = df.groupby("year", as_index=False)[chart["key"]].mean()
    df = df.sort_values("year").reset_index(drop=True)
    df["x"] = np.arange(len(df))
    return df


def rank_info(df: pd.DataFrame, value_col: str, year: int, ascending: bool = False) -> tuple[pd.DataFrame, int, int]:
    ranked = df.sort_values(value_col, ascending=ascending).reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)

    if year not in set(ranked["year"]):
        year = int(ranked["year"].max())

    ranking = int(ranked.loc[ranked["year"] == year, "rank"].iloc[0])
    return ranked, ranking, len(ranked)


def build_xtick_labels(years: pd.Series) -> tuple[list[int], list[str]]:
    ticks = []
    labels = []
    for idx, year in enumerate(years):
        if year == years.iloc[0] or year % 10 == 0:
            ticks.append(idx)
            labels.append(str(int(year)))
    return ticks, labels


def nice_axis_limits(values: pd.Series, lower_floor: float | None = None) -> tuple[float, float]:
    """Return compact y-axis limits with padding based on the actual data range."""
    arr = pd.to_numeric(values, errors="coerce").dropna().to_numpy(dtype=float)
    if arr.size == 0:
        return 0.0, 1.0

    vmin = float(np.nanmin(arr))
    vmax = float(np.nanmax(arr))
    data_range = vmax - vmin

    if data_range <= 0:
        pad = max(abs(vmax) * 0.05, 1.0)
    else:
        pad = max(data_range * 0.18, data_range * 0.08)

    ymin = vmin - pad
    ymax = vmax + pad

    if lower_floor is not None:
        ymin = max(lower_floor, ymin)

    # Avoid forcing zero onto charts like cloud cover where it wastes space.
    return ymin, ymax


def format_top_years(ranked: pd.DataFrame, value_col: str, units_label: str, include_values: bool = False) -> str:
    pieces = []
    for _, row in ranked.head(4).iterrows():
        year = int(row.year)
        if include_values and units_label:
            spacer = "" if units_label in {"°F", "%"} else " "
            pieces.append(f"{year} ({row[value_col]:.1f}{spacer}{units_label})")
        elif include_values:
            pieces.append(f"{year} ({row[value_col]:.1f})")
        else:
            pieces.append(str(year))
    return ", ".join(pieces)



def trend_values(df: pd.DataFrame, value_col: str) -> np.ndarray:
    """Return linear trendline values across the chart x-axis."""
    valid = df[["x", value_col]].dropna()
    if len(valid) < 2:
        return np.full(len(df), np.nan)
    coef = np.polyfit(valid["x"].to_numpy(dtype=float), valid[value_col].to_numpy(dtype=float), 1)
    return np.polyval(coef, df["x"].to_numpy(dtype=float))


def lowest_years(df: pd.DataFrame, value_col: str, units_label: str, include_values: bool = False) -> str:
    low = df.sort_values(value_col, ascending=True).head(4)
    pieces = []
    for _, row in low.iterrows():
        year = int(row.year)
        if include_values and units_label:
            spacer = "" if units_label in {"°F", "%"} else " "
            pieces.append(f"{year} ({row[value_col]:.1f}{spacer}{units_label})")
        elif include_values:
            pieces.append(f"{year} ({row[value_col]:.1f})")
        else:
            pieces.append(str(year))
    return ", ".join(pieces)



def ytick_formatter_for_chart(chart: dict, ax):
    """Return formatter that appends units only to the top-most visible y tick label."""
    from matplotlib.ticker import FuncFormatter

    units_label = chart.get("units_label", "")
    is_decimal_chart = chart.get("key") in {"tcw"}

    def _formatter(value, pos):
        ticks = [t for t in ax.get_yticks() if np.isfinite(t)]
        top_tick = max(ticks) if ticks else value

        if is_decimal_chart:
            label = f"{value:.2f}".rstrip("0").rstrip(".")
        else:
            label = f"{value:.0f}"

        if units_label and np.isclose(value, top_tick, rtol=0, atol=1e-9):
            label = f"{label} {units_label}"

        return label

    return FuncFormatter(_formatter)



def draw_custom_y_labels(ax, chart: dict) -> None:
    """Draw y-axis labels manually inside the axes so they always render."""
    ticks = [t for t in ax.get_yticks() if np.isfinite(t)]
    if not ticks:
        return

    ymin, ymax = ax.get_ylim()
    visible_ticks = [t for t in ticks if ymin <= t <= ymax]
    if not visible_ticks:
        visible_ticks = ticks

    top_tick = max(visible_ticks)
    units_label = chart.get("units_label", "")
    is_decimal_chart = chart.get("key") in {"tcw"}

    # Hide native y labels to avoid duplication; custom labels below are inside axes.
    ax.tick_params(axis="y", which="both", labelleft=False, left=False)

    for tick in visible_ticks:
        if is_decimal_chart:
            label = f"{tick:.2f}".rstrip("0").rstrip(".")
        else:
            label = f"{tick:.0f}"

        if units_label and np.isclose(tick, top_tick, rtol=0, atol=1e-9):
            spacer = "" if units_label in {"°F", "%"} else " "
            label = f"{label}{spacer}{units_label}"

        ax.text(
            -0.006,
            tick,
            label,
            transform=ax.get_yaxis_transform(),
            ha="right",
            va="center",
            color="white",
            fontsize=28,
            fontweight="bold",
            clip_on=False,
            zorder=130,
        )



def plot_chart(df: pd.DataFrame, ranked: pd.DataFrame, ranking: int, num_years: int, chart: dict, output_dir: Path, current_year: int) -> Path:
    """Plot a compact, data-scaled chart with trendline and in-axes info boxes."""
    plt.close("all")
    sns.reset_defaults()
    sns.set(rc={"axes.facecolor": "k", "figure.facecolor": "k"})

    value_col = chart["key"]
    units_label = chart.get("units_label", "")

    fig, ax = plt.subplots(figsize=(25, 15))
    ax.set_facecolor("k")

    trend = trend_values(df, value_col)
    y_values_for_limits = pd.concat([df[value_col], pd.Series(trend).dropna()], ignore_index=True)
    ymin, ymax = nice_axis_limits(
        y_values_for_limits,
        lower_floor=0.0 if chart["key"] in {"tcc", "cape", "sf", "tp", "tcw", "i10fg"} else None,
    )
    ax.set_ylim(ymin, ymax)

    ax.plot(df["x"], df[value_col], color="white", linewidth=8, zorder=100)

    if np.isfinite(trend).any():
        ax.plot(df["x"], trend, color="white", linewidth=5, linestyle=":", alpha=0.85, zorder=99)

    try:
        cmap = sns.color_palette(chart["palette"], as_cmap=True)
    except Exception:
        cmap = chart["palette"]

    ax.scatter(
        df["x"],
        df[value_col],
        c=df[value_col],
        cmap=cmap,
        s=300,
        edgecolors="white",
        linewidths=1,
        zorder=101,
    )

    ax.axhline(0, color="white", linewidth=2, alpha=0.7)
    ax.tick_params(left=True, bottom=True)
    ax.yaxis.set_tick_params(labelleft=False, left=False)
    ax.xaxis.set_tick_params(labelbottom=True, labelcolor="white", labelsize=28)

    ticks, labels = build_xtick_labels(df["year"])
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels)

    # Y-axis ticks: labels are drawn manually inside the axes below.
    from matplotlib.ticker import MaxNLocator
    if chart["key"] == "tcw":
        ax.yaxis.set_major_locator(MaxNLocator(nbins=7))
    else:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=7, integer=True))

    for tick in ax.xaxis.get_major_ticks():
        tick.label1.set_fontweight("bold")
    for tick in ax.yaxis.get_major_ticks():
        tick.label1.set_fontweight("bold")

    ax.set_xlabel("")
    ax.set_ylabel("")

    ax.yaxis.grid(False)
    ax.xaxis.grid(False)
    for spine in ["top", "bottom", "left", "right"]:
        ax.spines[spine].set_visible(False)

    ax.set_title(chart["title"], loc="left", color="white", weight="bold", fontsize=38, pad=22)

    top_years = format_top_years(
        ranked,
        value_col,
        units_label,
        include_values=bool(chart.get("top_with_values", False)),
    )
    low_years = lowest_years(
        df,
        value_col,
        units_label,
        include_values=bool(chart.get("top_with_values", False)),
    )

    info_lines = [
        f"{chart['superlative']}: {top_years}",
        f"{chart.get('low_superlative', 'Lowest years')}: {low_years}",
        chart["ranking_label"].format(year=current_year, ranking=ranking, num_years=num_years),
    ]

    # Keep info box inside axes bounds so saved image size does not expand.
    ax.text(
        0.985,
        0.965,
        "\n".join(info_lines),
        transform=ax.transAxes,
        horizontalalignment="right",
        verticalalignment="top",
        color="white",
        weight="bold",
        fontsize=20,
        linespacing=1.25,
        zorder=120,
        bbox=dict(facecolor="dimgray", alpha=0.72, edgecolor="black", boxstyle="round,pad=0.35"),
    )

    # Keep attribution inside axes bounds.
    ax.text(
        0.985,
        0.025,
        "@BenNollWeather",
        transform=ax.transAxes,
        horizontalalignment="right",
        verticalalignment="bottom",
        color="white",
        weight="bold",
        fontsize=18,
        bbox=dict(facecolor="dimgray", alpha=0.55, edgecolor="black", boxstyle="round,pad=0.25"),
        zorder=120,
    )

    fig.set_facecolor("k")
    fig.tight_layout(rect=[0.06, 0.0, 1.0, 0.965])
    fig.canvas.draw()
    draw_custom_y_labels(ax, chart)
    fig.canvas.draw()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / chart["outfile"]
    fig.savefig(out_path, facecolor=fig.get_facecolor(), dpi=100)
    plt.close(fig)
    print(f"Saved: {out_path}")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Hudson Valley climate-change charts from ERA5.")
    parser.add_argument("--work-root", default=str(DEFAULT_WORK_ROOT), help="Disposable work root.")
    parser.add_argument("--image-dir", default=None, help="Output image directory. Default: <work-root>/imagery")
    parser.add_argument("--input-file", default=None, help="Optional existing NetCDF file or folder of NetCDF files.")
    parser.add_argument("--skip-download", action="store_true", help="Skip CDS download and use existing download/input.")
    parser.add_argument("--download-retries", type=int, default=int(os.environ.get("DOWNLOAD_RETRIES", "3")))
    parser.add_argument("--retry-sleep", type=int, default=int(os.environ.get("RETRY_SLEEP", "60")))
    parser.add_argument("--target-year", type=int, default=dt.datetime.now().year - 1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    work_root = Path(args.work_root).expanduser()
    data_dir = work_root / "data"
    image_dir = Path(args.image_dir).expanduser() if args.image_dir else work_root / "imagery"

    data_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)

    if args.input_file:
        download_path = Path(args.input_file).expanduser()
    else:
        download_path = download_era5(
            data_dir=data_dir,
            target_year=args.target_year,
            retries=args.download_retries,
            retry_sleep=args.retry_sleep,
            skip_download=args.skip_download,
        )

    ds = find_or_open_dataset(download_path, data_dir, input_file=args.input_file)
    ds = annual_area_mean(ds)

    available_years = None
    generated = []
    for chart in CHARTS:
        df = series_from_dataset(ds, chart)
        if df.empty:
            print(f"Skipping {chart['key']}: no data")
            continue

        current_year = min(args.target_year, int(df["year"].max()))
        ranked, ranking, num_years = rank_info(df, chart["key"], current_year, ascending=chart.get("ascending", False))
        generated.append(plot_chart(df, ranked, ranking, num_years, chart, image_dir, current_year))

    print("\nGenerated image files:")
    for path in generated:
        print(path)


if __name__ == "__main__":
    main()
