#!/usr/bin/env python3
from __future__ import annotations

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
"""Download, plot, and optionally upload NMME imagery.

This script is a cleaned, runnable version of download-plot_nmme.ipynb.
It preserves the notebook's map styling and output naming, while centralizing
paths, downloads, shapefile discovery, plotting helpers, and S3 sync.
"""


import argparse
import os
import ssl
import subprocess
from dataclasses import dataclass
from pathlib import Path
import shutil
from shutil import copyfileobj
from urllib.parse import urlparse
from urllib.request import urlopen

import cmocean
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.colors import BoundaryNorm
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import xarray as xr

import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.feature import ShapelyFeature
from cartopy.io.shapereader import Reader
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from cartopy.util import add_cyclic_point
from metpy.plots import USCOUNTIES


@dataclass(frozen=True)
class Paths:
    base_download: Path
    shapefiles: Path

    @property
    def imagery(self) -> Path:
        return self.base_download / "imagery"

    def data_dir(self, variable: str, dl_month: str) -> Path:
        return self.base_download / variable / dl_month

    def imagery_dir(self, *parts: str) -> Path:
        path = self.imagery.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download, plot, and upload NMME imagery.")
    parser.add_argument("--base-download", default="DISPOSABLE/nmme")
    parser.add_argument("--shapefiles", default=_SHAPES)
    parser.add_argument("--aws-bin", default="aws")
    parser.add_argument("--aws-profile", default=os.environ.get("AWS_PROFILE", ""))
    parser.add_argument("--bucket", default="bennollweather")
    parser.add_argument("--prefix", default="nmme/imagery")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument(
        "--plot-method",
        choices=["pcolormesh", "contourf"],
        default="pcolormesh",
        help="pcolormesh is faster; contourf is closest to the original notebook.",
    )
    return parser.parse_args()


def get_shp(folder: Path) -> Path:
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Folder does not exist: {folder}")
    shp_files = sorted(folder.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in {folder}")
    if len(shp_files) > 1:
        print(f"Warning: multiple .shp files found in {folder}; using {shp_files[0].name}")
    return shp_files[0]


def build_run_dates() -> tuple[str, str, str, list[str], list[str]]:
    now = pd.Timestamp.today()
    current_year = now.strftime("%Y")
    this_month = now.strftime("%m")
    dl_month = now.strftime("%Y-%m")
    run = f"{current_year}{this_month}0800"
    month = f"{current_year}{this_month}"
    dates = [(now + pd.DateOffset(months=i)).strftime("%b %Y") for i in range(9)]
    names = [str(i) for i in range(1, 10)]
    return run, month, dl_month, dates, names


def build_urls(run: str, month: str) -> dict[str, str]:
    base = f"https://ftp.cpc.ncep.noaa.gov/NMME/realtime_anom/ENSMEAN/{run}"
    return {
        "sst": f"{base}/NMME.tmpsfc.{month}.ENSMEAN.anom.nc",
        "precip": f"{base}/NMME.prate.{month}.ENSMEAN.anom.nc",
        "temps": f"{base}/NMME.tmp2m.{month}.ENSMEAN.anom.nc",
    }


def download_files(urls: dict[str, str], paths: Paths, dl_month: str) -> dict[str, Path]:
    context = ssl._create_unverified_context()
    files: dict[str, Path] = {}
    for variable, url in urls.items():
        out_dir = paths.data_dir(variable, dl_month)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / Path(urlparse(url).path).name
        files[variable] = out_path
        if out_path.exists() and out_path.stat().st_size > 0:
            print(f"Already exists: {out_path}")
            continue
        print(f"Downloading {url}")
        with urlopen(url, context=context) as response:
            with open(out_path, "wb") as out_file:
                copyfileobj(response, out_file)
        print(f"Downloaded: {out_path}")
    return files


def expected_files(urls: dict[str, str], paths: Paths, dl_month: str) -> dict[str, Path]:
    return {
        variable: paths.data_dir(variable, dl_month) / Path(urlparse(url).path).name
        for variable, url in urls.items()
    }


def open_datasets(files: dict[str, Path]) -> tuple[xr.Dataset, xr.Dataset, xr.Dataset]:
    dset_sst = xr.open_dataset(files["sst"], decode_times=False)
    dset_precip = xr.open_dataset(files["precip"], decode_times=False)
    dset_temps = xr.open_dataset(files["temps"], decode_times=False)

    dset_sst = dset_sst.where(dset_sst["fcst"] < 10)
    dset_sst = dset_sst.ffill(dim="latitude", limit=100).ffill(dim="longitude", limit=100)
    dset_sst = dset_sst.bfill(dim="latitude", limit=100).bfill(dim="longitude", limit=100)

    # Preserve the notebook's unit conversions for precip and monthly temps.
    dset_precip["fcst"] = dset_precip["fcst"] * (86400 * 0.0394 * 90)
    dset_temps["fcst"] = dset_temps["fcst"] * 1.8
    return dset_sst, dset_precip, dset_temps


def target_months(dataset: xr.Dataset) -> list[xr.DataArray]:
    return [dataset.sel(lat=slice(90, -90), lon=slice(0, 360)).isel(target=i)["fcst"].squeeze() for i in range(9)]


def pcolor_or_contourf(ax, lons, lats, field, levels, cmap, transform, extend="both", method="pcolormesh"):
    if method == "contourf":
        return ax.contourf(lons, lats, field, levels=levels, cmap=cmap, extend=extend, transform=transform)
    cmap_obj = plt.get_cmap(cmap) if isinstance(cmap, str) else cmap
    norm = BoundaryNorm(levels, ncolors=cmap_obj.N, extend=extend)
    return ax.pcolormesh(lons, lats, field, cmap=cmap_obj, norm=norm, shading="auto", transform=transform)


def finish_colorbar(cbar):
    cbar.ax.set_facecolor([1, 1, 1, 0])
    for label in cbar.ax.get_yticklabels():
        label.set_weight("bold")


def add_signature(ax, fig):
    ax.text(
        0.01, 0.02, "@BenNollWeather",
        horizontalalignment="left", verticalalignment="bottom",
        transform=ax.transAxes, color="white", weight="bold", fontsize=20,
        bbox=dict(facecolor="k", alpha=0.5, edgecolor="black", boxstyle="round"),
        zorder=100,
    )
    fig.patch.set_facecolor("k")


def add_wet_dry_legend(ax):
    legend_labels = {"#2166AC": "Wetter", "#B35806": "Drier"}
    patches = [Patch(color=color, label=label) for color, label in legend_labels.items()]
    legend = ax.legend(
        handles=patches,
        facecolor="k",
        prop=dict(size=26),
        frameon=True,
        edgecolor="black",
        fancybox=False,
        loc="lower right",
        labelcolor="white",
        ncol=len(legend_labels),
    )
    legend.set_zorder(21)
    if legend is not None:
        legend.get_title().set_color("white")


def add_usa_base_features(ax, state_scale="10m", county_alpha=0.15, lake_kwargs=None, coast_resolution="10m"):
    if lake_kwargs is None:
        lake_kwargs = {"edgecolor": "black", "alpha": 0.2}
    states_provinces = cfeature.NaturalEarthFeature(
        category="cultural",
        name="admin_1_states_provinces_lines",
        scale=state_scale,
        facecolor="none",
    )
    ax.add_feature(cfeature.LAND)
    ax.coastlines(resolution=coast_resolution, color="k", linewidth=1)
    ax.add_feature(cfeature.BORDERS)
    ax.add_feature(cfeature.LAKES, **lake_kwargs)
    ax.add_feature(states_provinces, edgecolor="k")
    ax.add_feature(USCOUNTIES.with_scale("20m"), linestyle="-", edgecolor="k", alpha=county_alpha)


def add_global_precip_features(ax, state_scale="50m"):
    states_provinces = cfeature.NaturalEarthFeature(
        category="cultural",
        name="admin_1_states_provinces_lines",
        scale=state_scale,
        facecolor="none",
    )
    ax.add_feature(cfeature.LAND)
    ax.coastlines(resolution="50m", color="k", linewidth=1)
    ax.add_feature(cfeature.BORDERS)
    ax.add_feature(cfeature.LAKES, edgecolor="black", alpha=0.2)
    ax.add_feature(states_provinces, edgecolor="gray")


def plot_sst_monthly(dset_concat_sst, lons2, lats2, dates, names, paths: Paths, method: str):
    out_dir = paths.imagery_dir("sst")
    for i in range(len(dset_concat_sst)):
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        levels = np.linspace(-2, 2, 60)
        data = pcolor_or_contourf(ax, lons2, lats2, dset_concat_sst[i], levels, cmocean.cm.balance, ccrs.PlateCarree(), method=method)

        ax.add_feature(cfeature.NaturalEarthFeature(
            category="cultural", name="admin_0_countries", scale="10m",
            facecolor="none", edgecolor="k", linewidth=1,
        ), zorder=21)
        gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=1, color="white", alpha=0.5, linestyle="--")
        gl.xlabels_top = False
        gl.ylabels_right = False
        gl.xlines = True
        gl.ylocator = mticker.FixedLocator([-90, -60, -30, 0, 30, 60, 90])
        gl.xlocator = mticker.FixedLocator([0, 60, 120, 180, -120, -60, 0])
        gl.xformatter = LONGITUDE_FORMATTER
        gl.yformatter = LATITUDE_FORMATTER
        gl.xlabel_style = {"size": 12, "color": "white"}
        gl.ylabel_style = {"size": 12, "color": "white"}

        ax.add_feature(cfeature.LAND.with_scale("50m"), color="dimgray", edgecolor="k", zorder=20)
        ax.add_feature(cfeature.COASTLINE, edgecolor="k", linewidth=1, zorder=21)
        ax.add_feature(cfeature.LAKES, edgecolor="k", alpha=0.4, zorder=21)

        plt.title("NMME Sea Surface Temperature Anomaly (°C)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title(f"{dates[i]}", loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-2, 0, 2], pad=0.01, shrink=0.7, aspect=50, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        finish_colorbar(cbar)
        add_signature(ax, fig)
        plt.savefig(out_dir / f"sst_{names[i]}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def plot_precip_monthly(dset_concat_precip, lons, lats, dates, names, paths: Paths, method: str):
    out_dir = paths.imagery_dir("precip")
    levels = np.linspace(-2, 2, 100)
    for i in range(len(dset_concat_precip)):
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([205, 315, 20, 60])
        data = pcolor_or_contourf(ax, lons, lats, dset_concat_precip[i], levels, "cmo.tarn", ccrs.PlateCarree(), method=method)
        add_usa_base_features(ax)
        plt.title("NMME Precipitation Anomaly (inches)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title(f"{dates[i]}", loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-2, 0, 2], pad=0.01, shrink=0.65, aspect=60, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_wet_dry_legend(ax)
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"precip_{names[i]}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def plot_precip_usa_seasonal(seasons, lons, lats, dates, paths: Paths, method: str):
    out_dir = paths.imagery_dir("precip")
    levels = np.linspace(-2, 2, 100)
    titles = [(dates[1], dates[3]), (dates[4], dates[6]), (dates[6], dates[8])]
    for idx, (season, title_dates) in enumerate(zip(seasons, titles), start=1):
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([205, 315, 20, 60])
        data = pcolor_or_contourf(ax, lons, lats, season, levels, "cmo.tarn", ccrs.PlateCarree(), method=method)
        add_usa_base_features(ax)
        plt.title("NMME Precipitation Anomaly (inches)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title("{}-{}".format(*title_dates), loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-2, 0, 2], pad=0.01, shrink=0.65, aspect=60, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_wet_dry_legend(ax)
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"nmme_precip_usa_season{idx}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def plot_precip_global_atlantic(seasons, lon, lat, dates, paths: Paths, shapefiles: Path, method: str):
    out_dir = paths.imagery_dir("precip")
    levels = np.linspace(-2, 2, 100)
    titles = [(dates[1], dates[3]), (dates[4], dates[6]), (dates[6], dates[8])]
    atlantic_shp = get_shp(shapefiles / "atlantic")

    for idx, (season, title_dates) in enumerate(zip(seasons, titles), start=1):
        cyclic_data, cyclic_lons = add_cyclic_point(season.data, coord=lon)
        lons_cyc, lats_cyc = np.meshgrid(cyclic_lons, lat)

        # Globe
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        data = pcolor_or_contourf(ax, lons_cyc, lats_cyc, cyclic_data, levels, "cmo.tarn", ccrs.PlateCarree(), method=method)
        add_global_precip_features(ax)
        plt.title("NMME Precipitation Anomaly (inches)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title("{}-{}".format(*title_dates), loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-2, 0, 2], pad=0.01, shrink=0.7, aspect=60, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_wet_dry_legend(ax)
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"nmme_precip_globe_season{idx}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)

        # Atlantic
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([240, 358, -5, 40])
        data = pcolor_or_contourf(ax, lons_cyc, lats_cyc, cyclic_data, levels, "cmo.tarn", ccrs.PlateCarree(), method=method)
        add_global_precip_features(ax)
        shape_feature = ShapelyFeature(Reader(str(atlantic_shp)).geometries(), ccrs.PlateCarree(), facecolor="none", edgecolor="k")
        ax.add_feature(shape_feature, linewidth=3, zorder=22)
        plt.title("NMME Precipitation Anomaly (inches)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title("{}-{}".format(*title_dates), loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-2, 0, 2], pad=0.01, shrink=0.75, aspect=60, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_wet_dry_legend(ax)
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"nmme_precip_atlantic_season{idx}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def plot_temps_monthly(dset_concat_temps, lons, lats, dates, names, paths: Paths, method: str):
    out_dir = paths.imagery_dir("temps")
    levels = np.linspace(-5, 5, 11)
    for i in range(len(dset_concat_temps)):
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([205, 315, 20, 60])
        field = dset_concat_temps[i]
        data = pcolor_or_contourf(ax, lons, lats, field, levels, "cmo.balance", ccrs.PlateCarree(), method=method)
        ax.contour(lons, lats, field, np.arange(0, 0 + 0.01, 0.01), colors="k", linewidths=0.5, transform=ccrs.PlateCarree())
        add_usa_base_features(ax, county_alpha=0.1, lake_kwargs={"zorder": 10, "alpha": 0.3}, coast_resolution="50m")
        plt.title("NMME 2m Temperature Anomaly (°F)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title(f"{dates[i]}", loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5], pad=0.01, shrink=0.65, aspect=30, drawedges=True, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"temps_{names[i]}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def plot_temps_usa_seasonal(seasons, lons, lats, dates, paths: Paths, method: str):
    out_dir = paths.imagery_dir("temps", "usa")
    levels = np.linspace(-5, 5, 11)
    titles = [(dates[1], dates[3]), (dates[4], dates[6]), (dates[6], dates[8])]
    for idx, (season, title_dates) in enumerate(zip(seasons, titles), start=1):
        fig = plt.figure(figsize=(25, 15))
        ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([205, 315, 20, 60])
        data = pcolor_or_contourf(ax, lons, lats, season, levels, "cmo.balance", ccrs.PlateCarree(), method=method)
        ax.contour(lons, lats, season, np.arange(0, 0 + 0.01, 0.01), colors="k", linewidths=0.5, transform=ccrs.PlateCarree())
        add_usa_base_features(ax, county_alpha=0.1, lake_kwargs={"zorder": 10, "alpha": 0.3}, coast_resolution="50m")
        plt.title("NMME 2m Temperature Anomaly (°F)", loc="left", fontsize=24, color="white", weight="bold")
        plt.title("{}-{}".format(*title_dates), loc="right", fontsize=24, color="white", weight="bold")
        cbar = plt.colorbar(data, ax=ax, ticks=[-5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5], pad=0.01, shrink=0.65, aspect=30, drawedges=True, extend="both" if method == "pcolormesh" else None)
        cbar.ax.tick_params(labelsize=24, labelcolor="white")
        add_signature(ax, fig)
        finish_colorbar(cbar)
        plt.savefig(out_dir / f"nmme_temps_usa_season{idx}.png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
        plt.close(fig)


def make_nino34_table(dset_concat_sst, dl_month: str) -> pd.DataFrame:
    dset_concat = xr.concat([dset_concat_sst.isel(step=i) for i in range(len(dset_concat_sst))], "valid_time")
    nino34 = dset_concat.sel(lon=slice(190.0, 240.0), lat=slice(5.0, -5.0)).mean("lon").mean("lat")
    df = nino34.to_dataframe(name="SST Anomaly (°C)").reset_index()
    drop_cols = [col for col in ["valid_time", "target", "step"] if col in df.columns]
    df = df.drop(columns=drop_cols)
    df["SST Anomaly (°C)"] = df["SST Anomaly (°C)"].round(2)
    df["Month"] = pd.date_range(start=dl_month, periods=len(df), freq="M").to_period("M")
    return df[["Month", "SST Anomaly (°C)"]]


def upload_imagery(paths: Paths, aws_bin: str, aws_profile: str, bucket: str, prefix: str) -> list[str]:
    local_dir = paths.imagery
    s3_path = f"s3://{bucket}/{prefix}/"
    cmd_sync = [
        aws_bin, "s3", "sync", str(local_dir), s3_path,
        "--exclude", ".git/*",
        "--exclude", ".gitignore",
        "--exclude", ".DS_Store",
        "--exclude", ".gitattributes",
    ]
    result = subprocess.run(
        cmd_sync,
        env=(lambda env: (env.pop("AWS_PROFILE", None), env)[1] if not aws_profile else {**env, "AWS_PROFILE": aws_profile})(os.environ.copy()),
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
    paths = Paths(base_download=Path(args.base_download), shapefiles=Path(args.shapefiles))
    run, month, dl_month, dates, names = build_run_dates()
    urls = build_urls(run, month)

    files = expected_files(urls, paths, dl_month) if args.skip_download else download_files(urls, paths, dl_month)
    dset_sst, dset_precip, dset_temps = open_datasets(files)

    sst_months = target_months(dset_sst)
    precip_months = target_months(dset_precip)
    temps_months = target_months(dset_temps)

    dset_concat_sst = xr.concat(sst_months, "step").where(lambda x: x < 5.0, drop=True)
    dset_concat_precip = xr.concat(precip_months, "step")
    dset_concat_temps = xr.concat(temps_months, "step")

    season1_precip = (precip_months[1] + precip_months[2] + precip_months[3]) / 3
    season2_precip = (precip_months[4] + precip_months[5] + precip_months[6]) / 3
    season3_precip = (precip_months[6] + precip_months[7] + precip_months[8]) / 3
    precip_seasons = [season1_precip, season2_precip, season3_precip]

    # The source dataset was already converted from C to F above, so these seasonal means stay in F.
    season1_temps = (temps_months[1] + temps_months[2] + temps_months[3]) / 3
    season2_temps = (temps_months[4] + temps_months[5] + temps_months[6]) / 3
    season3_temps = (temps_months[6] + temps_months[7] + temps_months[8]) / 3
    temps_seasons = [season1_temps, season2_temps, season3_temps]

    lon_sst = dset_concat_sst["lon"]
    lat_sst = dset_concat_sst["lat"]
    lons_sst, lats_sst = np.meshgrid(lon_sst, lat_sst)

    lon = sst_months[0]["lon"]
    lat = sst_months[0]["lat"]
    lons, lats = np.meshgrid(lon, lat)

    print(f"Plot method: {args.plot_method}")
    plot_sst_monthly(dset_concat_sst, lons_sst, lats_sst, dates, names, paths, args.plot_method)
    plot_precip_monthly(dset_concat_precip, lons, lats, dates, names, paths, args.plot_method)
    plot_precip_usa_seasonal(precip_seasons, lons, lats, dates, paths, args.plot_method)
    plot_precip_global_atlantic(precip_seasons, lon, lat, dates, paths, paths.shapefiles, args.plot_method)
    plot_temps_monthly(dset_concat_temps, lons, lats, dates, names, paths, args.plot_method)
    plot_temps_usa_seasonal(temps_seasons, lons, lats, dates, paths, args.plot_method)

    nino34 = make_nino34_table(dset_concat_sst, dl_month)
    nino34_path = paths.imagery_dir("sst") / "nino34_index.csv"
    nino34.to_csv(nino34_path, index=False)
    print(f"Saved: {nino34_path}")

    for dataset in (dset_sst, dset_precip, dset_temps):
        dataset.close()
    for variable in ("sst", "precip", "temps"):
        shutil.rmtree(paths.data_dir(variable, dl_month), ignore_errors=True)

    if not args.skip_upload:
        upload_imagery(paths, args.aws_bin, args.aws_profile, args.bucket, args.prefix)


if __name__ == "__main__":
    main()
