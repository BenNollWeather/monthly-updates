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
"""Auto-converted from atmo_heatmap.ipynb.

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
import warnings
warnings.filterwarnings("ignore", message="The .xlabels_top attribute is deprecated.*")
warnings.filterwarnings("ignore", message="The .ylabels_right attribute is deprecated.*")
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

from model_versions import ECMWF_SYSTEM, C3S_MULTI_MODEL_SYSTEMS, C3S_STRATOSPHERE_SYSTEMS, C3S_SNOW_SYSTEMS, C3S_HEIGHT_SYSTEMS, C3S_UKMO_SYSTEM
# %% Notebook cell 0

import xarray as xr
import cfgrib
import cdsapi
import pandas as pd
import numpy as np
from dateparser import parse

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.image as image

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature

import cmocean

import dataframe_image as dfi

from glob import glob
import os
import pathlib
import urllib.request
from pathlib import Path

import os

import seaborn as sns

# %% Notebook cell 2

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 3

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 4

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 5

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 7

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 8

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 9

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 11

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/heatmaps").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/heatmaps/{}").format(dl_month)

# %% Notebook cell 12

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 13

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 14

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 16

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-pressure-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': 'u_component_of_wind_anomaly',
        'pressure_level': '850',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'c3s_zonal-members.grib')

# %% Notebook cell 17

# import cdsapi

# dataset = "seasonal-postprocessed-pressure-levels"
# request = {
#     'originating_centre': 'ecmwf',
#     'system': ECMWF_SYSTEM,
#     'variable': ['u_component_of_wind_anomaly'],
#     'pressure_level': ['850'],
#     'product_type': ['ensemble_mean'],
#     'year': [current_year],
#     'month': [this_month],
#     'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#     'data_format': 'grib'
# }

# client = cdsapi.Client()
# client.retrieve(dataset, request).download(dl_path/'c3s_zonal-members.grib')

# %% Notebook cell 18

df = xr.open_dataset(dl_path/"c3s_zonal-members.grib")

# %% Notebook cell 19

ecmwf = df

# %% Notebook cell 20

ecmwf['step'] = pd.to_datetime((pd.to_datetime(ecmwf['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf['valid_time'] = ecmwf['step']

valid_time = ecmwf['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

ecmwf = ecmwf['ua']*1.94384

# %% Notebook cell 21

nino34 = ecmwf.sel(latitude=slice(5., -5.), longitude=slice(190., 240))
nino34 = nino34.mean('latitude').mean('longitude')

# %% Notebook cell 23

# calculate the median
median = np.median(nino34, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]

sns.heatmap(nino34, linewidth=.5, cmap="RdBu_r", vmin=-8, vmax=8, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar
cbar.ax.tick_params(labelsize=20, length=0)

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Average Zonal Wind Speed Anomaly (kts) in NINO34 Region", loc="left", color='k', fontsize=24)

# set y-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_yticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("12")

# set x-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_xticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("16")

ax[0].set_xticks(np.arange(len(xticklabels))+0.5)
ax[0].set_xticklabels(xticklabels, fontsize=16, color='black')
ax[0].tick_params(axis='x', length=8)
    
# plot the line
colors = np.where(median > 0, 'red', 'blue')

ax[1].plot(np.arange(len(median))+0.5, median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)

for i, y in enumerate(median):
    color = 'red' if colors[i] == 'red' else 'blue'
    ax[1].plot(i+0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
# calculate percentiles

dsq_10 = nino34.quantile(q=0.1, dim='number')
dsq_90 = nino34.quantile(q=0.9, dim='number')

ax[1].plot(np.arange(len(dsq_10))+0.5, dsq_10, color='gray', linewidth=4, zorder=99)
ax[1].plot(np.arange(len(dsq_90))+0.5, dsq_90, color='gray', linewidth=4, zorder=99)

# set y-axis limits for the line plot
ax[1].set_ylim([dsq_10.min()-0.5, dsq_90.max()+0.5])

# set y-axis tick parameters for the line plot
ax[1].tick_params(axis='y', length=0, labelsize=16, colors='black')

# set x-axis tick parameters for the line plot
ax[1].set_xticks(np.arange(len(xticklabels))+0.5)
ax[1].set_xticklabels(xticklabels, fontsize=24, color='black')
ax[1].tick_params(axis='x', length=0, labelsize=26)

# add axis lines to the line plot
ax[1].axhline(y=0, color='black', linestyle='-', linewidth=3)
ax[1].spines['right'].set_visible(False)
ax[1].spines['top'].set_visible(False)

# add grid lines to the y-axis
ax[1].grid(axis='y')

# adjust the position of the line plot relative to the heatmap
ax[1].spines['bottom'].set_position(('axes', -0.1))

# set the title for the line plot
ax[1].set_title('Median Zonal Wind Speed Anomaly (kts, black) in NINO34 Region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/zonal_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"zonal_heatmap.png")

# %% Notebook cell 26

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': '10m_wind_gust_anomaly',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'c3s_wind-members.grib')

# %% Notebook cell 27

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels', 
#     {
#         'originating_centre': 'ecmwf',
#         'variable': ['10m_wind_gust_anomaly'],
#         'product_type': ['monthly_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_wind-members.grib')

# %% Notebook cell 28

df2 = xr.open_dataset(dl_path/"c3s_wind-members.grib")

# %% Notebook cell 29

ecmwf2 = df2

# %% Notebook cell 30

ecmwf2['step'] = pd.to_datetime((pd.to_datetime(ecmwf2['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf2['valid_time'] = ecmwf2['step']

valid_time = ecmwf2['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

# %% Notebook cell 31

hv_wind = ecmwf2['fga10'].sel(latitude=slice(41.9, 40.9), longitude=slice(285, 286.5))
hv_wind = hv_wind.mean('latitude').mean('longitude')
hv_wind = hv_wind*2.23694

# %% Notebook cell 32

# calculate the median
median = np.median(hv_wind, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]

sns.heatmap(hv_wind, linewidth=.5, cmap="RdBu_r", vmin=-5, vmax=5, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar
cbar.ax.tick_params(labelsize=20, length=0)

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members' Wind Gust Anomaly (mph) in the Hudson Valley", loc="left", color='k', fontsize=24)

# set y-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_yticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("12")

# set x-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_xticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("16")

ax[0].set_xticks(np.arange(len(xticklabels))+0.5)
ax[0].set_xticklabels(xticklabels, fontsize=16, color='black')
ax[0].tick_params(axis='x', length=8)
    
# plot the line
colors = np.where(median > 0, 'red', 'blue')

ax[1].plot(np.arange(len(median))+0.5, median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)

for i, y in enumerate(median):
    color = 'red' if colors[i] == 'red' else 'blue'
    ax[1].plot(i+0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
# calculate percentiles

dsq_10 = hv_wind.quantile(q=0.25, dim='number')
dsq_90 = hv_wind.quantile(q=0.75, dim='number')

ax[1].plot(np.arange(len(dsq_10))+0.5, dsq_10, color='gray', linewidth=4, zorder=99)
ax[1].plot(np.arange(len(dsq_90))+0.5, dsq_90, color='gray', linewidth=4, zorder=99)

# set y-axis limits for the line plot
ax[1].set_ylim([dsq_10.min()-0.5, dsq_90.max()+0.5])

# set y-axis tick parameters for the line plot
ax[1].tick_params(axis='y', length=0, labelsize=16, colors='black')

# set x-axis tick parameters for the line plot
ax[1].set_xticks(np.arange(len(xticklabels))+0.5)
ax[1].set_xticklabels(xticklabels, fontsize=24, color='black')
ax[1].tick_params(axis='x', length=0, labelsize=26)

# add axis lines to the line plot
ax[1].axhline(y=0, color='black', linestyle='-', linewidth=3)
ax[1].spines['right'].set_visible(False)
ax[1].spines['top'].set_visible(False)

# add grid lines to the y-axis
ax[1].grid(axis='y')

# adjust the position of the line plot relative to the heatmap
ax[1].spines['bottom'].set_position(('axes', -0.1))

# set the title for the line plot
ax[1].set_title('Median Wind Gust Anomaly (mph, black) in the Hudson Valley | 25th & 75th percentile (gray)', loc='left', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.75, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(fig_path/"gust_heatmap.png")

# %% Notebook cell 34

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': '2m_temperature_anomaly',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'c3s_temp-members.grib')

# %% Notebook cell 35

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels', 
#     {
#         'originating_centre': 'ecmwf',
#         'variable': ['2m_temperature_anomaly'],
#         'product_type': ['monthly_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_temp-members.grib')

# %% Notebook cell 36

df2 = xr.open_dataset(dl_path/"c3s_temp-members.grib")

# %% Notebook cell 37

ecmwf2 = df2

# %% Notebook cell 38

ecmwf2['step'] = pd.to_datetime((pd.to_datetime(ecmwf2['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf2['valid_time'] = ecmwf2['step']

valid_time = ecmwf2['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

# %% Notebook cell 39

hv_temp = ecmwf2['t2a'].sel(latitude=slice(41.9, 40.9), longitude=slice(285, 286.5))
hv_temp = hv_temp.mean('latitude').mean('longitude')

# %% Notebook cell 40

# calculate the median
median = np.median(hv_temp, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]

sns.heatmap(hv_temp, linewidth=.5, cmap="coolwarm", vmin=-3, vmax=3, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar
cbar.ax.tick_params(labelsize=20, length=0)

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members' Temperature Anomaly (°C) in the Hudson Valley", loc="left", color='k', fontsize=24)

# set y-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_yticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("12")

# set x-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_xticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("16")

ax[0].set_xticks(np.arange(len(xticklabels))+0.5)
ax[0].set_xticklabels(xticklabels, fontsize=16, color='black')
ax[0].tick_params(axis='x', length=8)
    
# plot the line
colors = np.where(median > 0, 'red', 'blue')

ax[1].plot(np.arange(len(median))+0.5, median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)

for i, y in enumerate(median):
    color = 'red' if colors[i] == 'red' else 'blue'
    ax[1].plot(i+0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
# calculate percentiles

dsq_10 = hv_temp.quantile(q=0.25, dim='number')
dsq_90 = hv_temp.quantile(q=0.75, dim='number')

ax[1].plot(np.arange(len(dsq_10))+0.5, dsq_10, color='gray', linewidth=4, zorder=99)
ax[1].plot(np.arange(len(dsq_90))+0.5, dsq_90, color='gray', linewidth=4, zorder=99)

# set y-axis limits for the line plot
ax[1].set_ylim([dsq_10.min()-0.5, dsq_90.max()+0.5])

# set y-axis tick parameters for the line plot
ax[1].tick_params(axis='y', length=0, labelsize=16, colors='black')

# set x-axis tick parameters for the line plot
ax[1].set_xticks(np.arange(len(xticklabels))+0.5)
ax[1].set_xticklabels(xticklabels, fontsize=24, color='black')
ax[1].tick_params(axis='x', length=0, labelsize=26)

# add axis lines to the line plot
ax[1].axhline(y=0, color='black', linestyle='-', linewidth=3)
ax[1].spines['right'].set_visible(False)
ax[1].spines['top'].set_visible(False)

# add grid lines to the y-axis
ax[1].grid(axis='y')

# adjust the position of the line plot relative to the heatmap
ax[1].spines['bottom'].set_position(('axes', -0.1))

# set the title for the line plot
ax[1].set_title('Median Temperature Anomaly (°C, black) in the Hudson Valley  | 25th & 75th percentile (gray)', loc='left', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.75, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(fig_path/"temp_heatmap.png")

# %% Notebook cell 42

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': 'total_precipitation_anomalous_rate_of_accumulation',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'c3s_precip-members.grib')

# %% Notebook cell 43

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels', 
#     {
#         'originating_centre': 'ecmwf',
#         'variable': ['total_precipitation_anomalous_rate_of_accumulation'],
#         'product_type': ['monthly_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_precip-members.grib')

# %% Notebook cell 44

df2 = xr.open_dataset(dl_path/"c3s_precip-members.grib")

# %% Notebook cell 45

ecmwf2 = df2

# %% Notebook cell 46

ecmwf2['step'] = pd.to_datetime((pd.to_datetime(ecmwf2['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf2['valid_time'] = ecmwf2['step']

valid_time = ecmwf2['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

# %% Notebook cell 47

hv_precip = ecmwf2['tpara'].sel(latitude=slice(41.9, 40.9), longitude=slice(285, 286.5))
hv_precip = hv_precip.mean('latitude').mean('longitude')
hv_precip = hv_precip*86400*1000*0.0394*90

# %% Notebook cell 48

# calculate the median
median = np.median(hv_precip, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]

sns.heatmap(hv_precip, linewidth=.5, cmap="BrBG", vmin=-3, vmax=3, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar
cbar.ax.tick_params(labelsize=20, length=0)

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members' Precipitation Anomaly (in/day) in the Hudson Valley", loc="left", color='k', fontsize=24)

# set y-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_yticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("12")

# set x-axis tick parameters for the heatmap
for tick_label in ax[0].axes.get_xticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("16")

ax[0].set_xticks(np.arange(len(xticklabels))+0.5)
ax[0].set_xticklabels(xticklabels, fontsize=16, color='black')
ax[0].tick_params(axis='x', length=8)
    
# plot the line
colors = np.where(median > 0, 'green', 'brown')

ax[1].plot(np.arange(len(median))+0.5, median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)

for i, y in enumerate(median):
    color = 'green' if colors[i] == 'green' else 'brown'
    ax[1].plot(i+0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
# calculate percentiles

dsq_10 = hv_precip.quantile(q=0.25, dim='number')
dsq_90 = hv_precip.quantile(q=0.75, dim='number')

ax[1].plot(np.arange(len(dsq_10))+0.5, dsq_10, color='gray', linewidth=4, zorder=99)
ax[1].plot(np.arange(len(dsq_90))+0.5, dsq_90, color='gray', linewidth=4, zorder=99)

# set y-axis limits for the line plot
ax[1].set_ylim([dsq_10.min()-0.5, dsq_90.max()+0.5])

# set y-axis tick parameters for the line plot
ax[1].tick_params(axis='y', length=0, labelsize=16, colors='black')

# set x-axis tick parameters for the line plot
ax[1].set_xticks(np.arange(len(xticklabels))+0.5)
ax[1].set_xticklabels(xticklabels, fontsize=24, color='black')
ax[1].tick_params(axis='x', length=0, labelsize=26)

# add axis lines to the line plot
ax[1].axhline(y=0, color='black', linestyle='-', linewidth=3)
ax[1].spines['right'].set_visible(False)
ax[1].spines['top'].set_visible(False)

# add grid lines to the y-axis
ax[1].grid(axis='y')

# adjust the position of the line plot relative to the heatmap
ax[1].spines['bottom'].set_position(('axes', -0.1))

# set the title for the line plot
ax[1].set_title('Median Precipitation Anomaly (in/day, black) in the Hudson Valley | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

# set the background color of the figure to white
fig.patch.set_facecolor('white')

ax[0].text(5.28, -0.75, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(fig_path/"hv_precip_heatmap.png")

# %% Notebook cell 50

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': 'snowfall_anomalous_rate_of_accumulation',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'c3s_snow-members.grib')

# %% Notebook cell 51

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels', 
#     {
#         'originating_centre': 'ecmwf',
#         'variable': ['snowfall_anomalous_rate_of_accumulation'],
#         'product_type': ['monthly_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_snow-members.grib')

# %% Notebook cell 52

df2 = xr.open_dataset(dl_path/"c3s_snow-members.grib")

# %% Notebook cell 53

ecmwf2 = df2

# %% Notebook cell 54

ecmwf2['step'] = pd.to_datetime((pd.to_datetime(ecmwf2['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf2['valid_time'] = ecmwf2['step']

valid_time = ecmwf2['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

# %% Notebook cell 55

# City coordinates
cities = {
    "NYC": (40.7128, 360 - 74.0060),
    "Philadelphia": (39.9526, 360 - 75.1652),
    "Washington D.C.": (38.9072, 360 - 77.0369),
    "Montgomery, NY": (41.5276, 360 - 74.2393),
    "Boston, MA": (42.3601, 360 - 71.0589),
    "Buffalo, NY": (42.8864, 360 - 78.8784),
    "Chicago, IL": (41.8781, 360 - 87.6298),
    "Minneapolis, MN": (44.9778, 360 - 93.2650),
    "Denver, CO": (39.7392, 360 - 104.9903),
    "Seattle, WA": (47.6062, 360 - 122.3321),
    "Atlanta, GA": (33.7490, 360 - 84.3880),
    "Raleigh, NC": (35.7796, 360 - 78.6382),
    "Cleveland, OH": (41.4993, 360 - 81.6944),
    "Detroit, MI": (42.3314, 360 - 83.0458)
}

# Example: process each city's data
for city, (lat, lon) in cities.items():
    # Select snowfall data for the specific city
    snow = ecmwf2['sfara'].sel(latitude=lat, longitude=lon, method='nearest')
    snow = snow * 86400 * 1000 * 0.0394 * 90
    
    # Calculate the median
    median = np.median(snow, axis=0)
    
    # Create the figure and axes objects
    fig, ax = plt.subplots(3, 1, figsize=(25, 20), sharex='col', gridspec_kw={'height_ratios': [3, -0.3, 1]})
    
    # Create heatmap
    xticklabels = [month1, month2, month3, month4, month5, month6]
    
    sns.heatmap(snow, linewidth=.5, cmap="RdBu", vmin=-1, vmax=1, xticklabels=xticklabels, ax=ax[0], 
                cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
    cbar = ax[0].collections[0].colorbar
    cbar.ax.tick_params(labelsize=20, length=0)
    
    # Set y-axis label for the heatmap
    ax[0].set_ylabel("Ensemble member", fontsize=16)
    
    # Set title for the heatmap
    ax[0].set_title(f"ECMWF Ensemble Members' Snowfall Anomaly (inches) in {city}", loc="left", color='k', fontsize=24, weight="bold")
    
    # Set y-axis tick parameters for the heatmap
    for tick_label in ax[0].axes.get_yticklabels():
        tick_label.set_color("k")
        tick_label.set_fontsize("12")
    
    # Set x-axis tick parameters for the heatmap
    for tick_label in ax[0].axes.get_xticklabels():
        tick_label.set_color("k")
        tick_label.set_fontsize("16")
    
    ax[0].set_xticks(np.arange(len(xticklabels)) + 0.5)
    ax[0].set_xticklabels(xticklabels, fontsize=16, color='black')
    ax[0].tick_params(axis='x', length=8)
    
    # Calculate the percent chance of above-normal snowfall
    above_normal_percent = (snow > 0).mean(dim='number').values * 100
    
    # Plot the percentage chance of above-normal snowfall
    for i, percent in enumerate(above_normal_percent):
        # Extract the month part from the label (e.g., "May" from "May 2024")
        month_only = xticklabels[i].split()[0]
        
        # Check if the month is not May to September
        if month_only not in ['May', 'Jun', 'Jul', 'Aug', 'Sep']:
            ax[0].text(i + 0.5, len(snow['number']) + 2, f"{percent:.0f}%", ha='center', va='center', fontsize=16, color='black', weight='bold')
            
    ax[1].set_xlim(ax[0].get_xlim())
    # Add title to ax[1] and set it as very narrow
    ax[1].set_title("Chance\nabove\nnormal", fontsize=16, weight='bold', loc='left', pad=180)
    ax[1].axis('off')
    
    # Plot the line
    colors = np.where(median > 0, 'blue', 'red')
    
    ax[2].plot(np.arange(len(median)) + 0.5, median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)
    
    for i, y in enumerate(median):
        color = 'blue' if colors[i] == 'blue' else 'red'
        ax[2].plot(i + 0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
    # Calculate percentiles
    dsq_10 = snow.quantile(q=0.25, dim='number')
    dsq_90 = snow.quantile(q=0.75, dim='number')
    
    ax[2].plot(np.arange(len(dsq_10)) + 0.5, dsq_10, color='gray', linewidth=4, zorder=99)
    ax[2].plot(np.arange(len(dsq_90)) + 0.5, dsq_90, color='gray', linewidth=4, zorder=99)
    
    # Set y-axis limits for the line plot
    ax[2].set_ylim([dsq_10.min() - 0.1, dsq_90.max() + 0.1])
    
    # Set y-axis tick parameters for the line plot
    ax[2].tick_params(axis='y', length=0, labelsize=16, colors='black')
    
    # Set x-axis tick parameters for the line plot
    ax[2].set_xticks(np.arange(len(xticklabels)) + 0.5)
    ax[2].set_xticklabels(xticklabels, fontsize=24, color='black')
    ax[2].tick_params(axis='x', length=0, labelsize=26)
    
    # Add axis lines to the line plot
    ax[2].axhline(y=0, color='black', linestyle='-', linewidth=3)
    ax[2].spines['right'].set_visible(False)
    ax[2].spines['top'].set_visible(False)
    
    # Add grid lines to the y-axis
    ax[2].grid(axis='y')
    
    # Adjust the position of the line plot relative to the heatmap
    ax[2].spines['bottom'].set_position(('axes', -0.1))
    
    # Set the title for the line plot
    ax[2].set_title(f'Median Snowfall Anomaly (inches, black) in {city} | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20, weight="bold")
    
    # Adjust the position of the heatmap and line plot
    fig.tight_layout(rect=[0, 0.01, 1, 0.99])

    # Adjust the space between the plots
    plt.subplots_adjust(hspace=0.1)
    
    # Set the background color of the figure to white
    fig.patch.set_facecolor('white')
    
    ax[0].text(5.28, -0.75, '@BenNollWeather', horizontalalignment='left', verticalalignment='bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

    # Save the figure
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path / f"{city.lower().replace(' ', '_').replace(',', '')}_snowfall_heatmap.png")
    plt.close()