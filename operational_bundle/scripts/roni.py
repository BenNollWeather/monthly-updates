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

# Assuming your DataFrame is named merged_df

# Set up the plot
sns.set(style="darkgrid", rc={'axes.facecolor': 'k', 'figure.facecolor': 'k'})

# Create the plot
plt.figure(figsize=(25, 15))
ax = sns.lineplot(data=merged_df, x="step", y="scaled_nino34", label="Relative Niño 3.4", color='orange', linewidth=20, zorder=10)
sns.lineplot(data=merged_df, x="step", y="nino34", label="Traditional Niño 3.4", color='green', linewidth=20, zorder=10)
ax.set_xlabel(" ", color='white', fontsize=14)
ax.set_ylabel(" ", color='white', fontsize=14)
ax.tick_params(axis='both', colors='white', labelsize=30)  # Adjusted
plt.title("Traditional Niño 3.4 index & relative Niño 3.4 index C3S forecast", fontsize=40, loc="left", color='white', weight="bold", bbox=dict(facecolor='dimgray', alpha=0.5, edgecolor='k', boxstyle='round'))
plt.title("Init: {}".format(month1), fontsize=30, loc="right", color='white', weight="bold", bbox=dict(facecolor='dimgray', alpha=0.5, edgecolor='k', boxstyle='round'))

ax.tick_params(left=False, bottom=False, right=False, top=False, width=2, colors="white")  # Remove tick marks
ax.spines['top'].set_visible(False)  # Hide top spine
ax.spines['bottom'].set_visible(False)  # Hide bottom spine
ax.spines['left'].set_visible(False)  # Hide left spine
ax.spines['right'].set_visible(False)  # Hide right spine

# Set y-axis limits using Matplotlib
ax.set_ylim(merged_df['scaled_nino34'].min()-0.5, merged_df['nino34'].max()+0.5)

# Customize the legend
legend = ax.legend(loc='lower left', title="")
legend_title = legend.get_title()
legend_title.set_fontsize(30)  # Adjusted text size
legend_title.set_color('white')  # Adjusted text color
legend.get_frame().set_edgecolor('none')  # Remove legend border

# Add El Niño and La Niña threshold to the legend
el_nino_line = ax.plot([], [], color='lightsalmon', linestyle='--', linewidth=10, label='El Niño Threshold')
la_nina_line = ax.plot([], [], color='aqua', linestyle='--', linewidth=10, label='La Niña Threshold')

# Adjust legend item font size and color
for text in legend.get_texts():
    text.set_fontsize(30)
    text.set_color('white')

plt.xticks(rotation=45)

# Make the axes tick labels bold
for tick in ax.xaxis.get_major_ticks():
    tick.label1.set_fontweight('bold')

for tick in ax.yaxis.get_major_ticks():
    tick.label1.set_fontweight('bold')

# Add horizontal lines at 0.5 and -0.5
ax.axhline(y=0.5, color='lightsalmon', linestyle='--', linewidth=4)
ax.axhline(y=-0.5, color='aqua', linestyle='--', linewidth=4)

# Ensure the legend includes the threshold lines and set text properties
legend = ax.legend(loc='lower left')
for text in legend.get_texts():
    text.set_color('white')
    text.set_fontsize(30)

ax.text(0.91, 0.96, '@BenNollWeather', horizontalalignment='left', verticalalignment='bottom',
          transform=ax.transAxes, color='white', weight="bold", fontsize=16,
          bbox=dict(facecolor='dimgray', alpha=0.5, edgecolor='black', boxstyle='round'))


plt.tight_layout()

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/experimental_roni_forecast.png'), facecolor='k', bbox_inches="tight", pad_inches=0.18, dpi=200)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(_os.path.join(_WORK, 'downloads/experimental_roni_forecast.png'), facecolor='k', bbox_inches="tight", pad_inches=0.18, dpi=200)

plt.close("all")