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
"""Auto-converted from olr.ipynb.

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
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.io import shapereader

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

from pathlib import Path

def get_shp(folder_or_file):
    """Return a concrete .shp path from either a .shp path or a folder containing one."""
    p = Path(folder_or_file)
    if p.suffix.lower() == ".shp":
        if not p.exists():
            raise FileNotFoundError(f"Shapefile does not exist: {p}")
        return str(p)
    if not p.exists():
        raise FileNotFoundError(f"Shapefile folder does not exist: {p}")
    shp_files = sorted(p.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No .shp file found in shapefile folder: {p}")
    if len(shp_files) > 1:
        print(f"Warning: multiple .shp files found in {p}; using {shp_files[0].name}")
    return str(shp_files[0])

def shp_geometries(shp_path):
    """Return geometries from a shapefile, falling back to shp/shx-only read if DBF is corrupt."""
    shp_path = Path(shp_path)
    try:
        return list(Reader(str(shp_path)).geometries())
    except Exception as exc:
        print(f"Warning: standard shapefile read failed for {shp_path}: {exc}")
        print("Falling back to geometry-only shapefile read using .shp/.shx.")
        import shapefile as pyshp
        import shapely.geometry as sgeom

        shx_path = shp_path.with_suffix(".shx")
        if not shx_path.exists():
            raise FileNotFoundError(f"Cannot fallback without .shx file: {shx_path}") from exc

        with open(shp_path, "rb") as shp_f, open(shx_path, "rb") as shx_f:
            reader = pyshp.Reader(shp=shp_f, shx=shx_f)
            return [sgeom.shape(shape.__geo_interface__) for shape in reader.shapes()]

shapefiles = _SHAPES

# %% Notebook cell 11

shape1 = get_shp(os.path.join(shapefiles, 'nino34'))
shape2 = get_shp(os.path.join(shapefiles, 'nino3'))
shape3 = get_shp(os.path.join(shapefiles, 'nino4'))
shape4 = get_shp(os.path.join(shapefiles, 'nino12'))
shape5 = get_shp(os.path.join(shapefiles, 'iode'))
shape6 = get_shp(os.path.join(shapefiles, 'iodw'))
shape7 = get_shp(os.path.join(shapefiles, 'atlantic'))

# %% Notebook cell 13

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 14

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 15

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 16

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 18

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 19

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 21

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ecmwf',
        'variable': [
            'top_solar_radiation_anomalous_rate_of_accumulation', 'top_thermal_radiation_anomalous_rate_of_accumulation',
        ],
        'system': ECMWF_SYSTEM,
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    'ecmwf_solar.grib')

# %% Notebook cell 22

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['top_solar_radiation_anomalous_rate_of_accumulation', 'top_thermal_radiation_anomalous_rate_of_accumulation'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download('ecmwf_solar.grib')

# %% Notebook cell 23

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre': 'ukmo',
        'variable': [
            'top_solar_radiation_anomalous_rate_of_accumulation', 'top_thermal_radiation_anomalous_rate_of_accumulation',
        ],
        'system': C3S_UKMO_SYSTEM,
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    'ukmet_solar.grib')

# %% Notebook cell 24

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ukmo'],
#         'variable': ['top_solar_radiation_anomalous_rate_of_accumulation', 'top_thermal_radiation_anomalous_rate_of_accumulation'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download('ukmet_solar.grib')

# %% Notebook cell 25

ecmwf = 'ecmwf_solar.grib'
ukmet = 'ukmet_solar.grib'

# %% Notebook cell 26

ecmwf = xr.open_dataset(ecmwf, engine='cfgrib')
ukmet = xr.open_dataset(ukmet, engine='cfgrib')

# %% Notebook cell 27

ecmwf

# %% Notebook cell 29

ecmwf1 = ecmwf.isel(step=0)
ukmet1 = ukmet.isel(step=0)

# %% Notebook cell 30

ecmwf1 = ecmwf1.interp_like(ukmet1)

# %% Notebook cell 31

month_one = ((ecmwf1['tsrara']-ecmwf1['ttrara']) + (ukmet1['tsrara']-ukmet1['ttrara'])/2)

# %% Notebook cell 33

ecmwf2 = ecmwf.isel(step=1)
ukmet2 = ukmet.isel(step=1)

# %% Notebook cell 34

ecmwf2 = ecmwf2.interp_like(ukmet2)

# %% Notebook cell 35

month_two = ((ecmwf2['tsrara']-ecmwf2['ttrara']) + (ukmet2['tsrara']-ukmet2['ttrara'])/2)

# %% Notebook cell 37

ecmwf3 = ecmwf.isel(step=2)
ukmet3 = ukmet.isel(step=2)

# %% Notebook cell 38

ecmwf3 = ecmwf3.interp_like(ukmet3)

# %% Notebook cell 39

month_three = ((ecmwf3['tsrara']-ecmwf3['ttrara']) + (ukmet3['tsrara']-ukmet3['ttrara'])/2)

# %% Notebook cell 41

ecmwf4 = ecmwf.isel(step=3)
ukmet4 = ukmet.isel(step=3)

# %% Notebook cell 42

ecmwf4 = ecmwf4.interp_like(ukmet4)

# %% Notebook cell 43

month_four = ((ecmwf4['tsrara']-ecmwf4['ttrara']) + (ukmet4['tsrara']-ukmet4['ttrara'])/2)

# %% Notebook cell 45

ecmwf5 = ecmwf.isel(step=4)
ukmet5 = ukmet.isel(step=4)

# %% Notebook cell 46

ecmwf5 = ecmwf5.interp_like(ukmet5)

# %% Notebook cell 47

month_five = ((ecmwf5['tsrara']-ecmwf5['ttrara']) + (ukmet5['tsrara']-ukmet5['ttrara'])/2)

# %% Notebook cell 49

ecmwf6 = ecmwf.isel(step=5)
ukmet6 = ukmet.isel(step=5)

# %% Notebook cell 50

ecmwf6 = ecmwf6.interp_like(ukmet6)

# %% Notebook cell 51

month_six = ((ecmwf6['tsrara']-ecmwf6['ttrara']) + (ukmet6['tsrara']-ukmet6['ttrara'])/2)

# %% Notebook cell 53

season1 = (month_two+month_three+month_four)/3

# %% Notebook cell 54

season2 = (month_four+month_five+month_six)/3

# %% Notebook cell 55

lon = month_one['longitude']
lat = month_one['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 56

#super.to_netcdf('super.nc')

# %% Notebook cell 58

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([240, 358, -5, 40])

levels = np.linspace(-30, 30, 13)

data = plt.contourf(lons, lats, season1, levels=levels, cmap="PuOr_r", extend='both', transform=ccrs.PlateCarree())
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

plt.title('ECMWF+UKMET "Superblend" Outgoing Longwave Radiation Anomaly (W/m²)', loc='left', fontsize=20, color='white', weight="bold")

plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=18, color='white', weight="bold")

shape7 = shape7
shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

cbar = plt.colorbar(data, ax=ax, ticks=[-30,-20,-10,0,10,20,30], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_olr_usa_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 59

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([240, 358, -5, 40])

levels = np.linspace(-30, 30, 13)

data = plt.contourf(lons, lats, season2, levels=levels, cmap="PuOr_r", extend='both', transform=ccrs.PlateCarree())
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

plt.title('ECMWF+UKMET "Superblend" Outgoing Longwave Radiation Anomaly (W/m²)', loc='left', fontsize=20, color='white', weight="bold")

plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=18, color='white', weight="bold")

shape7 = shape7
shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

cbar = plt.colorbar(data, ax=ax, ticks=[-30,-20,-10,0,10,20,30], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_olr_usa_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 60

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-30, 30, 13)

data = plt.contourf(lons, lats, season1, levels=levels, cmap="PuOr_r", extend='both', transform=ccrs.PlateCarree())
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

gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=1, color='white', alpha=0.5, linestyle='--')
gl.xlabels_top = False
gl.top_labels = False
gl.ylabels_right = False
gl.right_labels = False
gl.xlines = True
gl.ylocator = mticker.FixedLocator([-90, -60, -30, 0, 30, 60, 90])
gl.xlocator = mticker.FixedLocator([0, 60, 120, 180, -120, -60, 0])
gl.xformatter = LONGITUDE_FORMATTER
gl.yformatter = LATITUDE_FORMATTER
gl.xlabel_style = {'size': 12, 'color': 'white'}
gl.ylabel_style = {'size': 12, 'color': 'white'}

plt.title('ECMWF+UKMET "Superblend" Outgoing Longwave Radiation Anomaly (W/m²)', loc='left', fontsize=20, color='white', weight="bold")

plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=18, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-30,-20,-10,0,10,20,30], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_olr_globe_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 61

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-30, 30, 13)

data = plt.contourf(lons, lats, season2, levels=levels, cmap="PuOr_r", extend='both', transform=ccrs.PlateCarree())
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

gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=1, color='white', alpha=0.5, linestyle='--')
gl.xlabels_top = False
gl.top_labels = False
gl.ylabels_right = False
gl.right_labels = False
gl.xlines = True
gl.ylocator = mticker.FixedLocator([-90, -60, -30, 0, 30, 60, 90])
gl.xlocator = mticker.FixedLocator([0, 60, 120, 180, -120, -60, 0])
gl.xformatter = LONGITUDE_FORMATTER
gl.yformatter = LATITUDE_FORMATTER
gl.xlabel_style = {'size': 12, 'color': 'white'}
gl.ylabel_style = {'size': 12, 'color': 'white'}

plt.title('ECMWF+UKMET "Superblend" Outgoing Longwave Radiation Anomaly (W/m²)', loc='left', fontsize=20, color='white', weight="bold")

plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=18, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-30,-20,-10,0,10,20,30], pad=0.01, shrink=0.5, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white")
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_olr_globe_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")