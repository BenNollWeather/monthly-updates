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
"""Auto-converted from ecmwf_snow.ipynb.

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

import pygrib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
import pandas as pd
import numpy as np

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
from metpy.plots import USCOUNTIES

# %% Notebook cell 2

import xarray as xr

# %% Notebook cell 3

import cmocean

# %% Notebook cell 4

from dateparser import parse

# %% Notebook cell 5

import cfgrib

# %% Notebook cell 6

import pathlib

# %% Notebook cell 8

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 9

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 10

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 11

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

last_month = parse('-1 months ago')
last_month = last_month.strftime("%m")

# %% Notebook cell 13

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 14

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 15

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 17

names = ['1','2','3','4','5','6']

# %% Notebook cell 19

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/snow").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/snow/{}").format(dl_month)

# %% Notebook cell 20

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 21

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 22

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 24

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': [
            'ecmwf',
        ],
        'system': ECMWF_SYSTEM,
        'variable': 'snowfall_anomalous_rate_of_accumulation',
        'product_type': 'ensemble_mean',
        'year': '{}'.format(current_year),
        'month': '{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    dl_path/'snow.grib')

# %% Notebook cell 25

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['snowfall_anomalous_rate_of_accumulation'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'snow.grib')

# %% Notebook cell 26

# this loads all dfs at once
df = cfgrib.open_datasets(dl_path/"snow.grib")
lats = np.linspace(-90, 90, 181)
lons = np.linspace(0, 359, 360)
dsets = []
for dataset in df:
    dataset = dataset.interp(latitude = lats,
                   longitude = lons,
                   method ='nearest')
    dataset['sfara'] = dataset['sfara'].expand_dims({"GCM":1})
    dataset['GCM'] = (('GCM'),[dataset.attrs['institution']] )
    dsets.append(dataset)
concats = xr.concat(dsets, dim ="GCM")
snow = concats.mean("GCM")

# %% Notebook cell 28

snow['step'] = pd.to_datetime((pd.to_datetime(snow['valid_time'].to_index()) - pd.Timedelta(days = 20)).strftime("%Y-%m-01"))

# %% Notebook cell 29

snow['valid_time'] = snow['step']

# %% Notebook cell 30

valid_time = snow['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 31

valid_time = valid_time.values

# %% Notebook cell 33

lon = snow['longitude']
lat = snow['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 34

snow.load()

# %% Notebook cell 35

snow = snow['sfara'].data

# %% Notebook cell 36

snow, cyclic_lons = add_cyclic_point(snow, coord=lon)

# %% Notebook cell 37

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 38

season1 = (snow[0]+snow[1]+snow[2])/3
season2 = (snow[3]+snow[4]+snow[5])/3
winter = (snow[2]+snow[3]+snow[4])/3

# %% Notebook cell 40

for i in range(len(snow)):

    fig = plt.figure(figsize=(25, 15))

    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([205, 315, 20, 60])

    levels = np.linspace(-0.000000002, 0.000000002, 50)

    data = plt.contourf(lons, lats, snow[i], levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

    states_provinces = cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_1_states_provinces_lines',
    scale='50m',
    facecolor='none')

    ax.add_feature(cfeature.LAND)
    ax.coastlines(resolution='50m', color='k', linewidth=1)
    ax.add_feature(cfeature.BORDERS)
    ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
    ax.add_feature(states_provinces, edgecolor='k')

    for scale, axis in zip(['20m'], [ax]):
        axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

    plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=24, color='white', weight="bold")

    # Add a legend for labels
    legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

    patches = [Patch(color=color, label=label)
              for color, label in legend_labels.items()]

    # Add the legend
    legend = ax.legend(handles=patches,
                   facecolor="k",
                   prop=dict(size=26),           # Set the font size
                   frameon=True,                 # Set frameon to True to have a box around the legend
                   edgecolor='black',            # Set the edge color of the legend box to black
                   fancybox=False,               # Disable rounded corners (use squared style)
                   loc='lower right',            # Position the legend to the bottom right
                   labelcolor='white',           # Set the font color of the legend labels
                   ncol=len(legend_labels)      # Set the number of columns in the legend
                   ).set_zorder(21)

    # Set the font color of the legend title (if required)
    if legend is not None:
        legend.get_title().set_color('white')

    ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

    fig.patch.set_facecolor('k')
    
    try:
    
        fig.subplots_adjust(bottom=0.12)
    
    except Exception:
    
        pass
    
    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow/ecmwf-snow_usa_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'{}_usa.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

    plt.close("all")

# %% Notebook cell 41

for i in range(len(snow)):

    fig = plt.figure(figsize=(25, 15))

    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

    levels = np.linspace(-0.000000002, 0.000000002, 50)

    data = plt.contourf(lons, lats, snow[i], levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

    states_provinces = cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_1_states_provinces_lines',
    scale='50m',
    facecolor='none')

    ax.add_feature(cfeature.LAND)
    ax.coastlines(resolution='50m', color='k', linewidth=1)
    ax.add_feature(cfeature.BORDERS)
    ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
    ax.add_feature(states_provinces, edgecolor='k')

    plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=24, color='white', weight="bold")

    # Add a legend for labels
    legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

    patches = [Patch(color=color, label=label)
               for color, label in legend_labels.items()]

    ax.legend(handles=patches,
              bbox_to_anchor=(0.993, 0.09),
              facecolor="white",
              prop=dict(size=16))
    
    # Add a legend for labels
    legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

    patches = [Patch(color=color, label=label)
              for color, label in legend_labels.items()]

    # Add the legend
    legend = ax.legend(handles=patches,
                   facecolor="k",
                   prop=dict(size=26),           # Set the font size
                   frameon=True,                 # Set frameon to True to have a box around the legend
                   edgecolor='black',            # Set the edge color of the legend box to black
                   fancybox=False,               # Disable rounded corners (use squared style)
                   loc='lower right',            # Position the legend to the bottom right
                   labelcolor='white',           # Set the font color of the legend labels
                   ncol=len(legend_labels)      # Set the number of columns in the legend
                   ).set_zorder(21)

    # Set the font color of the legend title (if required)
    if legend is not None:
        legend.get_title().set_color('white')

    ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

    fig.patch.set_facecolor('k')
    
    try:
    
        fig.subplots_adjust(bottom=0.12)
    
    except Exception:
    
        pass
    
    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow/ecmwf-snow_globe_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'{}_globe.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

    plt.close("all")

# %% Notebook cell 42

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-0.000000002, 0.000000002, 50)

data = plt.contourf(lons, lats, season1, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month1, month3), loc='right', fontsize=24, color='white', weight="bold")

# Add a legend for labels
legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

patches = [Patch(color=color, label=label)
          for color, label in legend_labels.items()]

# Add the legend
legend = ax.legend(handles=patches,
               facecolor="k",
               prop=dict(size=26),           # Set the font size
               frameon=True,                 # Set frameon to True to have a box around the legend
               edgecolor='black',            # Set the edge color of the legend box to black
               fancybox=False,               # Disable rounded corners (use squared style)
               loc='lower right',            # Position the legend to the bottom right
               labelcolor='white',           # Set the font color of the legend labels
               ncol=len(legend_labels)      # Set the number of columns in the legend
               ).set_zorder(21)

# Set the font color of the legend title (if required)
if legend is not None:
    legend.get_title().set_color('white')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(current_month, second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_globe.png'.format(valid_time[0], valid_time[2]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 43

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-0.000000002, 0.000000002, 50)

data = plt.contourf(lons, lats, season2, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=24, color='white', weight="bold")

# Add a legend for labels
legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

patches = [Patch(color=color, label=label)
          for color, label in legend_labels.items()]

# Add the legend
legend = ax.legend(handles=patches,
               facecolor="k",
               prop=dict(size=26),           # Set the font size
               frameon=True,                 # Set frameon to True to have a box around the legend
               edgecolor='black',            # Set the edge color of the legend box to black
               fancybox=False,               # Disable rounded corners (use squared style)
               loc='lower right',            # Position the legend to the bottom right
               labelcolor='white',           # Set the font color of the legend labels
               ncol=len(legend_labels)      # Set the number of columns in the legend
               ).set_zorder(21)

# Set the font color of the legend title (if required)
if legend is not None:
    legend.get_title().set_color('white')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_globe.png'.format(valid_time[3], valid_time[5]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 44

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-0.000000002, 0.000000002, 50)

data = plt.contourf(lons, lats, season1, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

for scale, axis in zip(['20m'], [ax]):
    axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month1, month3), loc='right', fontsize=24, color='white', weight="bold")

# Add a legend for labels
legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

patches = [Patch(color=color, label=label)
          for color, label in legend_labels.items()]

# Add the legend
legend = ax.legend(handles=patches,
               facecolor="k",
               prop=dict(size=26),           # Set the font size
               frameon=True,                 # Set frameon to True to have a box around the legend
               edgecolor='black',            # Set the edge color of the legend box to black
               fancybox=False,               # Disable rounded corners (use squared style)
               loc='lower right',            # Position the legend to the bottom right
               labelcolor='white',           # Set the font color of the legend labels
               ncol=len(legend_labels)      # Set the number of columns in the legend
               ).set_zorder(21)

# Set the font color of the legend title (if required)
if legend is not None:
    legend.get_title().set_color('white')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_usa.png'.format(valid_time[0], valid_time[2]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 45

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-0.000000002, 0.000000002, 50)

data = plt.contourf(lons, lats, season2, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
ax.add_feature(states_provinces, edgecolor='k')

for scale, axis in zip(['20m'], [ax]):
    axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

plt.title('ECMWF Snowfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=24, color='white', weight="bold")

# Add a legend for labels
legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

patches = [Patch(color=color, label=label)
          for color, label in legend_labels.items()]

# Add the legend
legend = ax.legend(handles=patches,
               facecolor="k",
               prop=dict(size=26),           # Set the font size
               frameon=True,                 # Set frameon to True to have a box around the legend
               edgecolor='black',            # Set the edge color of the legend box to black
               fancybox=False,               # Disable rounded corners (use squared style)
               loc='lower right',            # Position the legend to the bottom right
               labelcolor='white',           # Set the font color of the legend labels
               ncol=len(legend_labels)      # Set the number of columns in the legend
               ).set_zorder(21)

# Set the font color of the legend title (if required)
if legend is not None:
    legend.get_title().set_color('white')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_usa.png'.format(valid_time[3], valid_time[5]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 47

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
# ax.set_extent([205, 315, 20, 60])

# levels = np.linspace(-0.000000002, 0.000000002, 50)

# data = plt.contourf(lons, lats, winter, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

# states_provinces = cfeature.NaturalEarthFeature(
# category='cultural',
# name='admin_1_states_provinces_lines',
# scale='50m',
# facecolor='none')

# ax.add_feature(cfeature.LAND)
# ax.coastlines(resolution='50m', color='k', linewidth=1)
# ax.add_feature(cfeature.BORDERS)
# ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
# ax.add_feature(states_provinces, edgecolor='k')

# for scale, axis in zip(['20m'], [ax]):
#     axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

# plt.title('C3S Snowfall Anomaly\n[ECMWF+UKMET+Météo-France+DWD+CMCC+ECCC]', loc='left', fontsize=24, color='white')
# plt.title('{}-{}'.format(month3, month5), loc='right', fontsize=24, color='white')

# # Add a legend for labels
# legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

# patches = [Patch(color=color, label=label)
#           for color, label in legend_labels.items()]

# # Add the legend
# legend = ax.legend(handles=patches,
#                facecolor="k",
#                prop=dict(size=26),           # Set the font size
#                frameon=True,                 # Set frameon to True to have a box around the legend
#                edgecolor='black',            # Set the edge color of the legend box to black
#                fancybox=False,               # Disable rounded corners (use squared style)
#                loc='lower right',            # Position the legend to the bottom right
#                labelcolor='white',           # Set the font color of the legend labels
#                ncol=len(legend_labels)      # Set the number of columns in the legend
#                ).set_zorder(21)

# # Set the font color of the legend title (if required)
# if legend is not None:
# legend.get_title().set_color('white')

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(second_month, fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'{}-{}_usa.png'.format(valid_time[2], valid_time[4]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 49

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection = ccrs.Robinson(central_longitude=270, globe=None, false_easting=None, false_northing=None))

# levels = np.linspace(-0.000000002, 0.000000002, 50)

# data = plt.contourf(lons, lats, winter, levels=levels, cmap=cmocean.cm.curl_r, transform=ccrs.PlateCarree(), extend='both')

# states_provinces = cfeature.NaturalEarthFeature(
# category='cultural',
# name='admin_1_states_provinces_lines',
# scale='50m',
# facecolor='none')

# ax.add_feature(cfeature.LAND)
# ax.coastlines(resolution='50m', color='k', linewidth=1)
# ax.add_feature(cfeature.BORDERS)
# ax.add_feature(cfeature.LAKES, zorder=10, alpha=0.3)
# ax.add_feature(states_provinces, edgecolor='k')

# for scale, axis in zip(['20m'], [ax]):
#     axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

# plt.title('C3S Snowfall Anomaly\n[ECMWF+UKMET+Météo-France+DWD+CMCC+ECCC]', loc='left', fontsize=24, color='white')
# plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=24, color='white')

# # Add a legend for labels
# legend_labels = {"#178c7c": "Above normal","#bf5160": "Below normal"}

# patches = [Patch(color=color, label=label)
#           for color, label in legend_labels.items()]

# # Add the legend
# legend = ax.legend(handles=patches,
#                facecolor="k",
#                prop=dict(size=26),           # Set the font size
#                frameon=True,                 # Set frameon to True to have a box around the legend
#                edgecolor='black',            # Set the edge color of the legend box to black
#                fancybox=False,               # Disable rounded corners (use squared style)
#                loc='lower right',            # Position the legend to the bottom right
#                labelcolor='white',           # Set the font color of the legend labels
#                ncol=len(legend_labels)      # Set the number of columns in the legend
#                ).set_zorder(21)

# # Set the font color of the legend title (if required)
# if legend is not None:
# legend.get_title().set_color('white')

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# #plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/snow_{}_{}.png').format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'{}-{}_globe.png'.format(valid_time[1], valid_time[3]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()