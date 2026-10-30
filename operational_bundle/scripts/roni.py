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
"""Auto-converted from roni.ipynb.

Generated for the operational monthly runner. Styling and output filenames are preserved as much as possible.
"""

# SSL no-verify patch for company TLS interception / broken local CA chains.
import os as _ssl_os
_ssl_os.environ.setdefault("PYTHONHTTPSVERIFY", "0")
_ssl_os.environ.setdefault("CURL_CA_BUNDLE", "")
_ssl_os.environ.setdefault("REQUESTS_CA_BUNDLE", "")

try:
    import ssl as _ssl
    _ssl._create_default_https_context = _ssl._create_unverified_context
except Exception:
    pass

try:
    import urllib3 as _urllib3
    _urllib3.disable_warnings(_urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

try:
    import requests as _requests
    _requests_old_request = _requests.sessions.Session.request
    def _requests_noverify_request(self, method, url, **kwargs):
        kwargs.setdefault("verify", False)
        return _requests_old_request(self, method, url, **kwargs)
    if not getattr(_requests.sessions.Session.request, "_noverify_patched", False):
        _requests_noverify_request._noverify_patched = True
        _requests.sessions.Session.request = _requests_noverify_request
except Exception:
    pass

try:
    import pooch as _pooch
    from pooch import downloaders as _pooch_downloaders
    _pooch_old_http_downloader_call = _pooch_downloaders.HTTPDownloader.__call__
    def _pooch_noverify_http_call(self, url, output_file, pooch, check_only=False):
        self.kwargs.setdefault("verify", False)
        return _pooch_old_http_downloader_call(self, url, output_file, pooch, check_only=check_only)
    if not getattr(_pooch_downloaders.HTTPDownloader.__call__, "_noverify_patched", False):
        _pooch_noverify_http_call._noverify_patched = True
        _pooch_downloaders.HTTPDownloader.__call__ = _pooch_noverify_http_call
except Exception:
    pass

import os
os.environ.setdefault("MPLBACKEND", "Agg")
try:
    import matplotlib
    matplotlib.use("Agg")
except Exception:
    pass



# Ensure savefig parent directories exist before writing images.
try:
    from pathlib import Path as _savefig_Path
    import matplotlib.pyplot as _savefig_plt
    from matplotlib.figure import Figure as _savefig_Figure

    _old_pyplot_savefig = _savefig_plt.savefig
    def _mkdir_pyplot_savefig(fname, *args, **kwargs):
        try:
            _savefig_Path(fname).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return _old_pyplot_savefig(fname, *args, **kwargs)

    if not getattr(_savefig_plt.savefig, "_mkdir_patched", False):
        _mkdir_pyplot_savefig._mkdir_patched = True
        _savefig_plt.savefig = _mkdir_pyplot_savefig

    _old_figure_savefig = _savefig_Figure.savefig
    def _mkdir_figure_savefig(self, fname, *args, **kwargs):
        try:
            _savefig_Path(fname).parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return _old_figure_savefig(self, fname, *args, **kwargs)

    if not getattr(_savefig_Figure.savefig, "_mkdir_patched", False):
        _mkdir_figure_savefig._mkdir_patched = True
        _savefig_Figure.savefig = _mkdir_figure_savefig
except Exception:
    pass


def download_noaa_ersst_noverify():
    """Download NOAA ERSST locally with SSL verification disabled and return local NetCDF path."""
    from pathlib import Path
    from lib.roni_scaling import download_ersst

    local_path = Path(_os.path.join(_WORK, "data/noaa/ersst/sst.mnmean.nc"))
    return str(download_ersst(local_path))

# %% Notebook cell 1

import xarray as xr
import numpy as np
from matplotlib import pyplot as plt
import cfgrib
import os
import pathlib
from dateparser import parse
import pandas as pd

# %% Notebook cell 3

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 4

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 5

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 7

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/sst").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/sst/{}").format(dl_month)

# %% Notebook cell 8

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 9

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 10

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 12

df = cfgrib.open_datasets(dl_path/"sst.grib")
lats = np.linspace(-90, 90, 181)
lons = np.linspace(0, 359, 360)
dsets = []
for dataset in df:
    dataset = dataset.interp(latitude = lats,
                   longitude = lons,
                   method ='nearest')
    dataset['ssta'] = dataset['ssta'].expand_dims({"GCM":1})
    dataset['GCM'] = (('GCM'),[dataset.attrs['institution']] )
    dsets.append(dataset)
concats = xr.concat(dsets, dim ="GCM")
var = concats.mean("GCM")

# %% Notebook cell 13

var['step'] = pd.to_datetime((pd.to_datetime(var['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

# %% Notebook cell 14

var['valid_time'] = var['step']

# %% Notebook cell 15

valid_time = var['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 16

valid_time = valid_time.values

# %% Notebook cell 17

var = var['ssta']

# %% Notebook cell 18

var = var.ffill(dim='latitude', limit = 100).ffill(dim='longitude', limit = 100).bfill(dim='latitude', limit = 100).bfill(dim='longitude', limit = 100)

# %% Notebook cell 20

url = 'http://psl.noaa.gov/thredds/dodsC/Datasets/noaa.ersst.v5/sst.mnmean.nc'
local_ersst = download_noaa_ersst_noverify()
dat = xr.open_dataset(local_ersst)
# drop time_bnds
dat = dat.drop_vars("time_bnds")

# %% Notebook cell 22

# Assuming 'dat' is a pandas DataFrame or another appropriate data structure

# Calculate the last possible time step
last_time_step = dat['time'].max()

# Use the calculated end date in the slice
dat = dat.sel(time=slice('1950-01-01', last_time_step))

# %% Notebook cell 23

import datetime

# Assuming dat.time is an xarray DataArray
last_time = dat.time.values[-1]
formatted_date = datetime.datetime.utcfromtimestamp(last_time.tolist()/1e9).strftime('%Y-%m')

print("Formatted Date:", formatted_date)

# %% Notebook cell 25

# tropdomain = dat.sel(lat=slice(20, -20), lon=slice(0, 360))
# tropav = tropdomain.mean(dim=('lat','lon'))
# tropav = tropav.rename({'sst':'tropav'})

# %% Notebook cell 26

os.environ["CURL_HTTP_VERSION"] = "1.1"

url = "http://psl.noaa.gov/thredds/dodsC/Datasets/noaa.ersst.v5/sst.mnmean.nc"

local_ersst = download_noaa_ersst_noverify()
dat = xr.open_dataset(local_ersst, chunks={"time": 12})

from lib.roni_scaling import nino34_scaling_factors

# Same month-of-year factors as the ECMWF relative Niño 3.4 column.
scaling_nino34 = nino34_scaling_factors(dat)

# %% Notebook cell 33

# scaling_factor = scaling_factor.compute()
# print(scaling_factor)

# %% Notebook cell 34

# scaling_factor['nino34']

# %% Notebook cell 36

tropdomain = var.sel(latitude=slice(-20, 20), longitude=slice(0, 360))
tropav = tropdomain.mean(dim=('latitude','longitude'))

ninodomain = var.sel(latitude=slice(-5, 5), longitude=slice(190, 240))
nino34 = ninodomain.mean(dim=('latitude','longitude'))

diff_idx_forecast = nino34 - tropav

# %% Notebook cell 37

# Extract the months present in the 'ssta' variable
months_present = diff_idx_forecast.coords['valid_time.month']

# Select the scaling factor for the corresponding months
scaling_factor_selected = scaling_nino34.sel(month=months_present)

# Apply scaling to the 'ssta' variable
scaled_nino34 = diff_idx_forecast * scaling_factor_selected
scaled_nino34 = scaled_nino34.to_dataframe(name="scaled_nino34")

# Specify the columns to drop
columns_to_drop = ['number', 'time', 'surface', 'valid_time', 'month']

# Drop the specified columns
scaled_nino34 = scaled_nino34.drop(columns=columns_to_drop)

scaled_nino34 = scaled_nino34.reset_index()

# %% Notebook cell 38

for i in range(len(concats)):
    nino34 = concats.sel(longitude=slice(190., 240.), latitude=slice(-5., 5.)).mean('latitude').mean('longitude')

nino34['step'] = pd.to_datetime((pd.to_datetime(nino34['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))
nino34['valid_time'] = nino34['step']
nino34 = nino34.mean("GCM")
nino34 = nino34.to_dataframe()

# Specify the columns to drop
columns_to_drop = ['number', 'time', 'surface', 'valid_time']

nino34 = nino34.drop(columns=columns_to_drop)
nino34 = nino34.rename(columns={'ssta': 'nino34'})

nino34 = nino34.reset_index()

# %% Notebook cell 39

merged_df = pd.merge(scaled_nino34, nino34, on='step')

# %% Notebook cell 40

merged_df.to_csv(_os.path.join(_WORK, "downloads/roni.csv"))

# %% Notebook cell 42

import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from lib.ap_dates import ap_rewrite

_MONTHS = (
    "",
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


def _month_year(value, _pos):
    stamp = mdates.num2date(value)
    return ap_rewrite(f"{_MONTHS[stamp.month]} {stamp.year}")


def _celsius(value, _pos):
    return f"{value:.1f}°C"


def _pin_left_credit(figure, axes, y=0.035):
    """Put @BenNollWeather on the left edge of the y-axis labels."""
    figure.canvas.draw()
    plt.setp(axes.get_xticklabels(), fontweight="bold", color="white")
    plt.setp(axes.get_yticklabels(), fontweight="bold", color="white")
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    tick_labels = [label for label in axes.get_yticklabels() if label.get_text().strip()]
    left_px = min(label.get_window_extent(renderer).x0 for label in tick_labels)
    credit_x, _ = figure.transFigure.inverted().transform((left_px, 0))
    figure.text(
        credit_x,
        y,
        "@BenNollWeather",
        color="white",
        weight="bold",
        fontsize=18,
        ha="left",
        va="center",
    )


sns.set(style="darkgrid", rc={"axes.facecolor": "#000000", "figure.facecolor": "#000000", "savefig.facecolor": "#000000"})

fig, ax = plt.subplots(figsize=(25, 15))
fig.patch.set_facecolor("#000000")
ax.set_facecolor("#000000")
sns.lineplot(data=merged_df, x="step", y="scaled_nino34", color="orange", linewidth=10, ax=ax, legend=False)
sns.lineplot(data=merged_df, x="step", y="nino34", color="green", linewidth=10, ax=ax, legend=False)
ax.axhline(y=0.5, color="lightsalmon", linestyle="--", linewidth=4)
ax.axhline(y=-0.5, color="aqua", linestyle="--", linewidth=4)
ax.set_ylim(merged_df["scaled_nino34"].min() - 0.5, merged_df["nino34"].max() + 0.5)

ax.set_title(
    "Traditional Niño 3.4 index & relative Niño 3.4 index C3S forecast",
    loc="left",
    color="white",
    weight="bold",
    fontsize=32,
    pad=18,
)
ax.set_title("Init: {}".format(month1), loc="right", color="white", weight="bold", fontsize=26, pad=18)
ax.set_xlabel("")
ax.set_ylabel("")
for spine in ("top", "bottom", "left", "right"):
    ax.spines[spine].set_visible(False)
ax.tick_params(axis="both", colors="white", labelsize=28, length=0)
ax.yaxis.grid(True, color="white", linewidth=0.6, alpha=0.28)
ax.xaxis.grid(False)
ax.set_axisbelow(True)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(_celsius))
ax.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1))
ax.xaxis.set_major_formatter(mticker.FuncFormatter(_month_year))

handles = [
    Line2D([0], [0], color="orange", linewidth=8, label="Relative Niño 3.4"),
    Line2D([0], [0], color="green", linewidth=8, label="Traditional Niño 3.4"),
    Line2D([0], [0], color="lightsalmon", linestyle="--", linewidth=3, label="El Niño threshold"),
    Line2D([0], [0], color="aqua", linestyle="--", linewidth=3, label="La Niña threshold"),
]
ax.legend(
    handles=handles,
    loc="upper center",
    bbox_to_anchor=(0.5, -0.12),
    ncol=4,
    frameon=False,
    fontsize=24,
    labelcolor="white",
    borderaxespad=0.0,
    columnspacing=1.4,
    handlelength=2.4,
    handletextpad=0.5,
)

fig.patch.set_facecolor("#000000")
ax.set_facecolor("#000000")
fig.subplots_adjust(left=0.10, right=0.98, top=0.90, bottom=0.20)
fig.text(0.98, 0.035, "Data: C3S", color="white", weight="bold", fontsize=18, ha="right", va="center")
_pin_left_credit(fig, ax)

fig.savefig(_os.path.join(_WORK, "copernicus_imagery/experimental_roni_forecast.png"), facecolor="#000000", bbox_inches="tight", pad_inches=0.18, dpi=200)
fig.savefig(_os.path.join(_WORK, "downloads/experimental_roni_forecast.png"), facecolor="#000000", bbox_inches="tight", pad_inches=0.18, dpi=200)

plt.close("all")