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
"""Auto-converted from wind.ipynb.

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

import pygrib
import matplotlib as matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as colors
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER

# %% Notebook cell 2

from metpy.plots import USCOUNTIES

# %% Notebook cell 3

from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator

# %% Notebook cell 4

import xarray as xr

# %% Notebook cell 5

import os

# %% Notebook cell 6

from glob import glob

# %% Notebook cell 7

import cmocean

# %% Notebook cell 8

from dateparser import parse

# %% Notebook cell 10

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 11

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 12

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 13

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 15

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 16

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 18

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable':'10m_wind_gust_anomaly',
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    'ecmwf_wind.grib')

# %% Notebook cell 19

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['10m_wind_gust_anomaly'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ecmwf_wind.grib')

# %% Notebook cell 20

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ukmo',
        'system': C3S_UKMO_SYSTEM,
        'variable':'10m_wind_gust_anomaly',
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    'ukmet_wind.grib')

# %% Notebook cell 21

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ukmo'],
#         'variable': ['10m_wind_gust_anomaly'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ukmet_wind.grib')

# %% Notebook cell 22

ecmwf = 'ecmwf_wind.grib'
ukmet = 'ukmet_wind.grib'

# %% Notebook cell 23

ecmwf = xr.open_dataset(ecmwf, engine='cfgrib')
ukmet = xr.open_dataset(ukmet, engine='cfgrib')

# %% Notebook cell 25

ecmwf1 = ecmwf.isel(step=0)
ukmet1 = ukmet.isel(step=0)

# %% Notebook cell 26

ecmwf1 = ecmwf1.interp_like(ukmet1)

# %% Notebook cell 27

month_one = (ecmwf1['fga10'] + ukmet1['fga10'])/2

# %% Notebook cell 29

ecmwf2 = ecmwf.isel(step=1)
ukmet2 = ukmet.isel(step=1)

# %% Notebook cell 30

ecmwf2 = ecmwf2.interp_like(ukmet2)

# %% Notebook cell 31

month_two = (ecmwf2['fga10'] + ukmet2['fga10'])/2

# %% Notebook cell 33

ecmwf3 = ecmwf.isel(step=2)
ukmet3 = ukmet.isel(step=2)

# %% Notebook cell 34

ecmwf3 = ecmwf3.interp_like(ukmet3)

# %% Notebook cell 35

month_three = (ecmwf3['fga10'] + ukmet3['fga10'])/2

# %% Notebook cell 37

ecmwf4 = ecmwf.isel(step=3)
ukmet4 = ukmet.isel(step=3)

# %% Notebook cell 38

ecmwf4 = ecmwf4.interp_like(ukmet4)

# %% Notebook cell 39

month_four = (ecmwf4['fga10'] + ukmet4['fga10'])/2

# %% Notebook cell 41

ecmwf5 = ecmwf.isel(step=4)
ukmet5 = ukmet.isel(step=4)

# %% Notebook cell 42

ecmwf5 = ecmwf5.interp_like(ukmet5)

# %% Notebook cell 43

month_five = (ecmwf5['fga10'] + ukmet5['fga10'])/2

# %% Notebook cell 45

ecmwf6 = ecmwf.isel(step=5)
ukmet6 = ukmet.isel(step=5)

# %% Notebook cell 46

ecmwf6 = ecmwf6.interp_like(ukmet6)

# %% Notebook cell 47

month_six = (ecmwf6['fga10'] + ukmet6['fga10'])/2

# %% Notebook cell 49

season1 = (month_two+month_three+month_four)/3
season1 = season1*2.23694

# %% Notebook cell 50

season2 = (month_four+month_five+month_six)/3
season2 = season2*2.23694

# %% Notebook cell 51

lon = month_one['longitude']
lat = month_one['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 52

#super.to_netcdf('super.nc')

# %% Notebook cell 54

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-2, 2, 9)

data = plt.contourf(lons, lats, season1, levels=levels, cmap="RdYlBu_r", extend='both', transform=ccrs.PlateCarree())
cs = plt.contour(lons, lats, season1, np.arange(0, 0+0.01, 0.01), colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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

plt.title('ECMWF+UKMET "superblend" wind gust anomaly (mph)', loc='left', fontsize=24, color='white', weight="bold")

plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-2,-1,0,1,2], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
# Add a legend for labels
legend_labels = {"#6da7cd": "Less windy", "#f16341": "Windier"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_wind_usa_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 55

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-2, 2, 9)

data = plt.contourf(lons, lats, season2, levels=levels, cmap="RdYlBu_r", extend='both', transform=ccrs.PlateCarree())
cs = plt.contour(lons, lats, season2, np.arange(0, 0+0.01, 0.01), colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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

plt.title('ECMWF+UKMET "superblend" wind gust anomaly (mph)', loc='left', fontsize=24, color='white', weight="bold")

plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-2,-1,0,1,2], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
# Add a legend for labels
legend_labels = {"#6da7cd": "Less windy", "#f16341": "Windier"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_wind_usa_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 56

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-2, 2, 9)

data = plt.contourf(lons, lats, season1, levels=levels, cmap="RdYlBu_r", extend='both', transform=ccrs.PlateCarree())
cs = plt.contour(lons, lats, season1, np.arange(0, 0+0.01, 0.01), colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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


plt.title('ECMWF+UKMET "superblend" wind gust anomaly (mph)', loc='left', fontsize=24, color='white', weight="bold")

plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-2,-1,0,1,2], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
# Add a legend for labels
legend_labels = {"#6da7cd": "Less windy", "#f16341": "Windier"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_wind_globe_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 57

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-2, 2, 9)

data = plt.contourf(lons, lats, season2, levels=levels, cmap="RdYlBu_r", extend='both', transform=ccrs.PlateCarree())
cs = plt.contour(lons, lats, season2, np.arange(0, 0+0.01, 0.01), colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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


plt.title('ECMWF+UKMET "superblend" wind gust anomaly (mph)', loc='left', fontsize=24, color='white', weight="bold")

plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-2,-1,0,1,2], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
# Add a legend for labels
legend_labels = {"#6da7cd": "Less windy", "#f16341": "Windier"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_wind_globe_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")