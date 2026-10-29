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
"""Auto-converted from sst_heatmap.ipynb.

Generated for the operational monthly runner. Styling and output filenames are preserved as much as possible.
"""
from __future__ import annotations

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
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable': 'sea_surface_temperature_anomaly',
        'product_type': 'monthly_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
        dl_path/'ecmwf_sst-members.grib')

# %% Notebook cell 17

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels', 
#     {
#         'originating_centre': 'ecmwf',
#         'variable': ['sea_surface_temperature_anomaly'],
#         'product_type': ['monthly_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ecmwf_sst-members.grib')

# %% Notebook cell 18

df = xr.open_dataset(dl_path/"ecmwf_sst-members.grib")

# %% Notebook cell 19

ecmwf = df

# %% Notebook cell 20

ecmwf['step'] = pd.to_datetime((pd.to_datetime(ecmwf['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf['valid_time'] = ecmwf['step']

valid_time = ecmwf['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

ecmwf = ecmwf['ssta']

# %% Notebook cell 21

nino34 = ecmwf.sel(latitude=slice(5., -5.), longitude=slice(190., 240))
nino34 = nino34.mean('latitude').mean('longitude')

# %% Notebook cell 22

iode = ecmwf.sel(latitude=slice(0., -10.), longitude=slice(90., 110))
iode = iode.mean('latitude').mean('longitude')

# %% Notebook cell 23

gulf = ecmwf.sel(latitude=slice(31., 20.), longitude=slice(262., 278))
gulf = gulf.mean('latitude').mean('longitude')

# %% Notebook cell 24

nino = (nino34 > 1)
nina = (nino34 < -1)

# %% Notebook cell 25

nino_strong = (nino34 > 1.49)
nina_strong = (nino34 < -1.49)

# %% Notebook cell 26

nino_extra_strong = (nino34 > 2.0)
nina_extra_strong = (nino34 < -2.0)

# %% Notebook cell 27

# Computes stats
count_true = sum(nino_extra_strong)
perc_true = ((count_true.values)/51)*100
print(perc_true)

# %% Notebook cell 28

iod_pos = (iode < -0.5)
iod_neg = (iode > 0.5)

# %% Notebook cell 29

nino34_max = np.max(nino34, axis=0).values
nino34_min = np.min(nino34, axis=0).values

nino34_max = round(np.max(nino34_max), 2)
nino34_min = round(np.min(nino34_min), 2)

print("Maximum value:", nino34_max)
print("Minimum value:", nino34_min)

# %% Notebook cell 31

# calculate the median
median = np.median(nino34, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(nino_extra_strong, linewidth=.5, cmap="cmo.amp", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly >2.0°C in NINO34 region", loc="left", color='k', fontsize=24)

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in NINO34 region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {nino34_max:.2f}°C | Min: {nino34_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/nino_very_strong_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"nino_very_strong_heatmap.png")

# %% Notebook cell 32

median

# %% Notebook cell 33

# calculate the median
median = np.median(nino34, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(nino, linewidth=.5, cmap="cmo.amp", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly >1.0°C in NINO34 region", loc="left", color='k', fontsize=24)

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in NINO34 region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {nino34_max:.2f}°C | Min: {nino34_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/nino_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"nino_heatmap.png")

# %% Notebook cell 34

# calculate the median
median = np.median(nino34, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(nino_strong, linewidth=.5, cmap="cmo.amp", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly >1.5°C in NINO34 region", loc="left", color='k', fontsize=24)

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in NINO34 region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {nino34_max:.2f}°C | Min: {nino34_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/nino_strong_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"nino_strong_heatmap.png")

# %% Notebook cell 35

# calculate the median
median = np.median(nino34, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(nina, linewidth=.5, cmap="cmo.ice", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly <-1.0°C in NINO34 region", loc="left", color='k', fontsize=24)

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in NINO34 region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {nino34_max:.2f}°C | Min: {nino34_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/nina_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"nina_heatmap.png")

# %% Notebook cell 36

iode_max = np.max(iode, axis=0).values
iode_min = np.min(iode, axis=0).values

iode_max = round(np.max(iode_max), 2)
iode_min = round(np.min(iode_min), 2)

print("Maximum value:", iode_max)
print("Minimum value:", iode_min)

# %% Notebook cell 38

# calculate the median
median = np.median(iode, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(iod_neg, linewidth=.5, cmap="cmo.amp", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly >0.5°C in IOD east region", loc="left", color='k', fontsize=24)

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
dsq_10 = iode.quantile(q=0.1, dim='number')
dsq_90 = iode.quantile(q=0.9, dim='number')

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in IOD east region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {iode_max:.2f}°C | Min: {iode_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/iod_neg_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"iod_neg_heatmap.png")

# %% Notebook cell 39

# calculate the median
median = np.median(iode, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(iod_pos, linewidth=.5, cmap="cmo.ice", vmin=0, vmax=1.5, cbar=False, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members with Sea Surface Temperature Anomaly <-0.5°C in IOD east region", loc="left", color='k', fontsize=24)

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
dsq_10 = iode.quantile(q=0.1, dim='number')
dsq_90 = iode.quantile(q=0.9, dim='number')

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in IOD east region | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {iode_max:.2f}°C | Min: {iode_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.5, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/iod_pos_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"iod_pos_heatmap.png")

# %% Notebook cell 40

median

# %% Notebook cell 42

box_max = np.max(gulf, axis=0).values
box_min = np.min(gulf, axis=0).values

box_max = round(np.max(box_max), 2)
box_min = round(np.min(box_min), 2)

print("Maximum value:", box_max)
print("Minimum value:", box_min)

# %% Notebook cell 43

# calculate the median
box_median = np.median(gulf, axis=0)

# create the figure and axes objects
fig, ax = plt.subplots(2,1, figsize=(25, 15), sharex='col', gridspec_kw={'height_ratios': [3, 1]})

# create heatmap
xticklabels = [month1, month2, month3, month4, month5, month6]
sns.heatmap(gulf, linewidth=.5, cmap="cmo.balance", vmin=-2, vmax=2, xticklabels=xticklabels, ax=ax[0],  cbar_kws={'orientation': 'horizontal', 'location': 'bottom', 'shrink': 0.8, 'pad': 0.05, 'aspect': 105})
cbar = ax[0].collections[0].colorbar
cbar.ax.tick_params(labelsize=20, length=0)

# set y-axis label for the heatmap
ax[0].set_ylabel("Ensemble member",fontsize=16)

# set title for the heatmap
ax[0].set_title("ECMWF Ensemble Members' Sea Surface Temperature Anomaly (°C) in Gulf of Mexico [98-82W, 20-31N]", loc="left", color='k', fontsize=24)

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
colors = np.where(box_median > 0, 'red', 'blue')

ax[1].plot(np.arange(len(box_median))+0.5, box_median, color='black', linewidth=8, marker='o', markersize=20, zorder=100)

for i, y in enumerate(box_median):
    color = 'red' if colors[i] == 'red' else 'blue'
    ax[1].plot(i+0.5, y, color=color, marker='o', markersize=15, zorder=100)
    
# calculate percentiles

dsq_10 = gulf.quantile(q=0.1, dim='number')
dsq_90 = gulf.quantile(q=0.9, dim='number')

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
ax[1].set_title('Median Sea Surface Temperature Anomaly (°C, black) in Gulf of Mexico [98-82W, 20-31N] | 10th & 90th percentile (gray)', loc='left', color='k', fontsize=20)
ax[1].set_title(f'{month1}-{month6} - Max: {box_max:.2f}°C | Min: {box_min:.2f}°C', loc='right', color='k', fontsize=20)

# adjust the layout of the figure
fig.tight_layout()

ax[0].text(5.28, -0.6, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# set the background color of the figure to white
fig.patch.set_facecolor('white')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/heatmaps/gulf_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/"gulf_heatmap.png")