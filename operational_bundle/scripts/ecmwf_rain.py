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
"""Auto-converted from ecmwf_rain.ipynb.

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
import xarray as xr
import cfgrib
import dataframe_image as dfi 

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from shapely.geometry import box
from cartopy.io import shapereader

# %% Notebook cell 2

from metpy.plots import USCOUNTIES
import cmocean

# %% Notebook cell 3

from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator

# %% Notebook cell 4

from glob import glob
import os
import pathlib
from dateparser import parse

# %% Notebook cell 6

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

# %% Notebook cell 7

shape1 = get_shp(os.path.join(shapefiles, 'nino34'))
shape2 = get_shp(os.path.join(shapefiles, 'nino3'))
shape3 = get_shp(os.path.join(shapefiles, 'nino4'))
shape4 = get_shp(os.path.join(shapefiles, 'nino12'))
shape5 = get_shp(os.path.join(shapefiles, 'iode'))
shape6 = get_shp(os.path.join(shapefiles, 'iodw'))
shape7 = get_shp(os.path.join(shapefiles, 'atlantic'))

# %% Notebook cell 9

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 10

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 11

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 12

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 14

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 15

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 16

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 18

names = ['1','2','3','4','5','6']

# %% Notebook cell 20

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/precip").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/precip/{}").format(dl_month)

# %% Notebook cell 21

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 22

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 23

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 25

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-postprocessed-single-levels',
    {
        'originating_centre':'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable':'total_precipitation_anomalous_rate_of_accumulation',
        'product_type':'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month':[
            '1','2','3',
            '4','5','6'
        ],
        'format':'grib'
    },
    dl_path/'ecmwf_rain.grib')

# %% Notebook cell 26

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['total_precipitation_anomalous_rate_of_accumulation'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ecmwf_rain.grib')

# %% Notebook cell 27

ecmwf = (dl_path/'ecmwf_rain.grib')

# %% Notebook cell 28

ecmwf = xr.open_dataset(ecmwf, engine='cfgrib')

# %% Notebook cell 30

ecmwf1 = ecmwf.isel(step=0)

# %% Notebook cell 31

month_one = (ecmwf1['tpara'])

# %% Notebook cell 32

month_one = month_one*86400*1000*0.0394*90

# %% Notebook cell 34

ecmwf2 = ecmwf.isel(step=1)

# %% Notebook cell 35

month_two = (ecmwf2['tpara'])

# %% Notebook cell 36

month_two = month_two*86400*1000*0.0394*90

# %% Notebook cell 38

ecmwf3 = ecmwf.isel(step=2)

# %% Notebook cell 39

month_three = (ecmwf3['tpara'])

# %% Notebook cell 40

month_three = month_three*86400*1000*0.0394*90

# %% Notebook cell 42

ecmwf4 = ecmwf.isel(step=3)

# %% Notebook cell 43

month_four = (ecmwf4['tpara'])

# %% Notebook cell 44

month_four = month_four*86400*1000*0.0394*90

# %% Notebook cell 46

ecmwf5 = ecmwf.isel(step=4)

# %% Notebook cell 47

month_five = (ecmwf5['tpara'])

# %% Notebook cell 48

month_five = month_five*86400*1000*0.0394*90

# %% Notebook cell 50

ecmwf6 = ecmwf.isel(step=5)

# %% Notebook cell 51

month_six = (ecmwf6['tpara'])

# %% Notebook cell 52

month_six = month_six*86400*1000*0.0394*90

# %% Notebook cell 54

season1 = (month_two+month_three+month_four)/3

# %% Notebook cell 55

season2 = (month_four+month_five+month_six)/3

# %% Notebook cell 56

# custom = (month_two+month_three+month_four)/3
# custom = (month_three+month_four+month_five)/3

# %% Notebook cell 57

lon = season1['longitude']
lat = season1['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 58

#super.to_netcdf('super.nc')

# %% Notebook cell 61

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season1, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_globe_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_globe.png'.format(next_month, third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 62

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season2, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_globe_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_globe.png'.format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 64

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([240, 358, -5, 40])

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season1, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)


plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=20, color='white', weight="bold")

mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_atlantic_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_atlantic.png'.format(next_month, third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 65

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([240, 358, -5, 40])

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season2, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)


plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")

mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')
    
# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_atlantic_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_atlantic.png'.format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 67

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season1, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

for scale, axis in zip(['20m'], [ax]):
    axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_usa_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_usa.png'.format(next_month, third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 68

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
ax.set_extent([205, 315, 20, 60])

levels = np.linspace(-4, 4, 9)

data = plt.contourf(lons, lats, season2, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

ax.add_feature(cfeature.LAND)
ax.coastlines(resolution='50m', color='k', linewidth=1)
ax.add_feature(cfeature.BORDERS)
ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

for scale, axis in zip(['20m'], [ax]):
    axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

plt.title('ECMWF rainfall anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")

cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], pad=0.01, shrink=0.4, aspect=20, drawedges=True)
cbar.ax.tick_params(labelsize=20, labelcolor="white") 

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#1a7e76": "Wetter than average", "#a5691b": "Drier"}

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

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/superblend_precip_usa_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}_{}_usa.png'.format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 70

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
# ax.set_extent([205, 315, 20, 60])

# levels = np.linspace(-4, 4, 9)

# data = plt.contourf(lons, lats, custom, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

# states_provinces = cfeature.NaturalEarthFeature(
# category='cultural',
# name='admin_1_states_provinces_lines',
# scale='50m',
# facecolor='none')

# ax.add_feature(cfeature.LAND)
# ax.coastlines(resolution='50m', color='k', linewidth=1)
# ax.add_feature(cfeature.BORDERS)
# ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
# ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

# for scale, axis in zip(['20m'], [ax]):
#     axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

# plt.title('ECMWF+UKMET "Superblend" Rainfall Anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
# plt.title('{}-{}'.format(month3, month5), loc='right', fontsize=24, color='white', weight="bold")

# cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], drawedges=True, pad=0.01, shrink=0.65, aspect=60)
# cbar.ax.tick_params(labelsize=20, labelcolor="white") 

# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#2166AC": "Wetter", "#B35806": "Drier"}

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
#     legend.get_title().set_color('white')

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/precip_usa_{}_{}.png').format(second_month, fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'{}_{}_usa.png'.format(second_month, fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 72

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# levels = np.linspace(-4, 4, 9)

# data = plt.contourf(lons, lats, custom, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

# states_provinces = cfeature.NaturalEarthFeature(
# category='cultural',
# name='admin_1_states_provinces_lines',
# scale='50m',
# facecolor='none')

# ax.add_feature(cfeature.LAND)
# ax.coastlines(resolution='50m', color='k', linewidth=1)
# ax.add_feature(cfeature.BORDERS)
# ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
# ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

# plt.title('ECMWF+UKMET "Superblend" Rainfall Anomaly (inches)', loc='left', fontsize=24, color='white', weight="bold")
# plt.title('{}-{}'.format(month3, month5), loc='right', fontsize=24, color='white', weight="bold")

# cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], drawedges=True, pad=0.01, shrink=0.65, aspect=60)
# cbar.ax.tick_params(labelsize=20, labelcolor="white") 

# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#2166AC": "Wetter", "#B35806": "Drier"}

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
#     legend.get_title().set_color('white')

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/precip_globe_{}_{}.png').format(second_month, fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'{}_{}_globe.png'.format(second_month, fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 74

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
# ax.set_extent([240, 358, -5, 40])

# levels = np.linspace(-4, 4, 9)

# data = plt.contourf(lons, lats, custom, cmap='BrBG', levels=levels, extend='both', transform=ccrs.PlateCarree())

# #ax.coastlines()

# states_provinces = cfeature.NaturalEarthFeature(
# category='cultural',
# name='admin_1_states_provinces_lines',
# scale='50m',
# facecolor='none')

# gl = ax.gridlines(crs=ccrs.PlateCarree(), draw_labels=True, linewidth=1, color='white', alpha=0.5, linestyle='--')
# gl.xlabels_top = False
# gl.xlabels_bottom = True
# gl.ylabels_right = False
# gl.xlines = True
# gl.ylocator = mticker.FixedLocator([0, 10, 20, 30, 40, 50])
# gl.xlocator = mticker.FixedLocator([-180, -160, -140, -120, -100, -80, -60, -40, -20, 0])
# gl.xformatter = LONGITUDE_FORMATTER
# gl.yformatter = LATITUDE_FORMATTER
# gl.xlabel_style = {'size': 16, 'color': 'white'}
# gl.ylabel_style = {'size': 16, 'color': 'white'}

# ax.add_feature(cfeature.LAND)
# ax.coastlines(resolution='50m', color='k', linewidth=1)
# ax.add_feature(cfeature.BORDERS)
# ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
# ax.add_feature(states_provinces, edgecolor='k', linewidth=1)

# for scale, axis in zip(['20m'], [ax]):
#     axis.add_feature(USCOUNTIES.with_scale(scale), linestyle='-', edgecolor='k', alpha=0.1)

# plt.title('ECMWF+UKMET "Superblend" Rainfall Anomaly', loc='left', fontsize=24, color='white', weight="bold")
# plt.title('{}-{} {}'.format(next_month, third_month, current_year), loc='right', fontsize=24, color='white', weight="bold")

# cbar = plt.colorbar(data, ax=ax, ticks=[-4,-2,0,2,4], drawedges=True, pad=0.01, shrink=0.75, aspect=60)
# cbar.ax.tick_params(labelsize=20, labelcolor="white") 

# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#2166AC": "Wetter", "#B35806": "Drier"}

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
#     legend.get_title().set_color('white')

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'downloads/super_atlantic_{}_{}.png').format(next_month, third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 76

dset_concat = xr.concat([month_one, month_two, month_three, month_four, month_five, month_six], "valid_time")

# %% Notebook cell 77

dset_concat['step'] = pd.to_datetime((pd.to_datetime(dset_concat['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01")) 

# %% Notebook cell 78

dset_concat['valid_time'] = dset_concat['step'] 

# %% Notebook cell 79

valid_time = dset_concat['valid_time'].dt.strftime('%Y-%m') 

# %% Notebook cell 80

valid_time = valid_time.values 

# %% Notebook cell 81

for i in range(len(dset_concat)):
    hv = dset_concat.sel(longitude=slice(285, 286.5), latitude=slice(41.9, 40.9)).mean('longitude').mean('latitude')

# %% Notebook cell 82

hv = hv.to_dataframe() 

# %% Notebook cell 83

hv = hv.reset_index() 

# %% Notebook cell 84

hv = hv.drop(columns=['number','time','step','surface']) 

# %% Notebook cell 85

hv = hv.rename(columns={'valid_time': 'Month', 'tpara': 'Precipitation Anomaly (in)'}) 

# %% Notebook cell 86

hv['Month'] = hv['Month'].dt.to_period('M') 

# %% Notebook cell 87

hv = (
    hv.style
    .background_gradient(cmap='BrBG', vmin=-2, vmax=2)
    .hide(axis="index")
    .set_caption("Hudson Valley precipitation anomalies over the next 6 months")
    .format("{:.2f}", subset=hv.select_dtypes(include="number").columns)
    .set_properties(**{
        'text-align': 'center',
        'font-size': '24px',
        'font-weight': 'bold',
        'color': 'black'
    })
)

# %% Notebook cell 88

import matplotlib
matplotlib.colormaps.get_cmap = lambda name: matplotlib.colormaps[name]

# %% Notebook cell 89

dfi.export(hv,_os.path.join(_WORK, 'downloads/precip_table_{}.png').format(this_month))