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
"""Auto-converted from ecmwf_sst.ipynb.

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
import matplotlib as matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
import numpy as np
import xarray as xr
import pandas as pd
import cfgrib
import dataframe_image as dfi

# %% Notebook cell 1

from matplotlib import rcParams
from matplotlib.ticker import MultipleLocator
import matplotlib.ticker as mticker

# %% Notebook cell 2

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
from cartopy.util import add_cyclic_point
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.io import shapereader
from metpy.plots import USCOUNTIES
import cmocean

# %% Notebook cell 3

from glob import glob
import os
import pathlib
from dateparser import parse
import urllib.request

# %% Notebook cell 4

import seaborn as sns

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

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/ecmwf_sst").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/ecmwf_sst/{}").format(dl_month)

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
        'originating_centre': [
            'ecmwf',
        ],
        'system': ECMWF_SYSTEM,
#         'system': [
#             '1', '2', '5',
#             '8', '21', '35',
#             '600',
#         ],
        'variable': 'sea_surface_temperature_anomaly',
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    dl_path/'sst.grib')

# %% Notebook cell 26

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-single-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         # 'system': ['1', '2', '5', '8', '21', '35', '600'],
#         'variable': ['sea_surface_temperature_anomaly'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'sst.grib')

# %% Notebook cell 27

# this loads all dfs at once
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
sst = concats.mean("GCM")

# %% Notebook cell 29

sst['step'] = pd.to_datetime((pd.to_datetime(sst['valid_time'].to_index()) - pd.Timedelta(days = 20)).strftime("%Y-%m-01"))

# %% Notebook cell 30

sst['valid_time'] = sst['step']

# %% Notebook cell 31

valid_time = sst['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 32

valid_time = valid_time.values

# %% Notebook cell 33

import bottleneck

# %% Notebook cell 34

sst = sst.ffill(dim='latitude', limit = 100).ffill(dim='longitude', limit = 100).bfill(dim='latitude', limit = 100).bfill(dim='longitude', limit = 100)

# %% Notebook cell 35

sst

# %% Notebook cell 37

lon = sst['longitude']
lat = sst['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 38

sst.load()

# %% Notebook cell 39

sst = sst['ssta'].data

# %% Notebook cell 40

sst, cyclic_lons = add_cyclic_point(sst, coord=lon)

# %% Notebook cell 41

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 42

season1 = (sst[1]+sst[2]+sst[3])/3
season2 = (sst[3]+sst[4]+sst[5])/3

# %% Notebook cell 44

for i in range(len(sst)):

    fig = plt.figure(figsize=(25, 15))

    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

    levels = np.linspace(-2, 2, 60)

    data = plt.contourf(lons, lats, sst[i], levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

    ax.add_feature(cfeature.NaturalEarthFeature(
        category='cultural',
        name='admin_0_countries',
        scale='10m',
        facecolor='none',
        edgecolor='k',
        linewidth=1
    ), zorder=21)

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

    # Add shapefiles
    shape1 = shape1
    shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

#     ax.text(.5425, .485, '3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

    shape2 = shape2
    shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

#     ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
#     ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

    shape3 = shape3
    shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

#     ax.text(.46, .485, 'Niño 4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

    shape4 = shape4
    shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

#     ax.text(.7545, .455, '12', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, zorder=100, bbox=dict(facecolor='k', alpha=0, edgecolor='black', boxstyle='square', pad=0.1))

    shape5 = shape5
    shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

#     ax.text(.253, .455, 'IOD-E', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, zorder=100, bbox=dict(facecolor='k', alpha=0, edgecolor='black', boxstyle='square', pad=0.1))

    shape6 = shape6
    shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

#     ax.text(.141, .479, 'IOD-W', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, zorder=100, bbox=dict(facecolor='k', alpha=0, edgecolor='black', boxstyle='square', pad=0.1))

    shape7 = shape7
    shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

#     ax.text(.8, .566, 'Atlantic MDR', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, zorder=100, bbox=dict(facecolor='k', alpha=0, edgecolor='black', boxstyle='square', pad=0.1))

    ax.add_feature(cfeature.LAND.with_scale('50m'), color='dimgray', edgecolor='k', zorder = 20)
    ax.add_feature(cfeature.COASTLINE, edgecolor='k', linewidth=1, zorder = 21)
    ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.4, zorder = 21)

    plt.title('ECMWF Sea Surface Temperature Anomaly (°C)', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=24, color='white', weight="bold")
    cbar = plt.colorbar(data, ax=ax, ticks=[-2,0,2], pad=0.01, shrink=0.5, aspect=20)
    cbar.ax.tick_params(labelsize=24, labelcolor="white") 
    cbar.ax.set_facecolor([1,1,1,0])

    for label in cbar.ax.get_yticklabels():
        label.set_weight('bold')
    
    ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
    fig.patch.set_facecolor('k')

    try:

        fig.subplots_adjust(bottom=0.12)

    except Exception:

        pass

    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/sst_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'{}_globe.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

    plt.close("all")

# %% Notebook cell 45

for i in range(len(sst)):

    fig = plt.figure(figsize=(25, 15))

    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([240, 358, -5, 40])

    levels = np.linspace(-2, 2, 60)

    data = plt.contourf(lons, lats, sst[i], levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

    ax.add_feature(cfeature.NaturalEarthFeature(
        category='cultural',
        name='admin_0_countries',
        scale='10m',
        facecolor='none',
        edgecolor='k',
        linewidth=1
    ), zorder=21)
    
#     states_provinces = cfeature.NaturalEarthFeature(
#     category='cultural',
#     name='admin_1_states_provinces_lines',
#     scale='50m',
#     facecolor='none')

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

    ax.add_feature(cfeature.LAND.with_scale('50m'), color='dimgray', edgecolor='k', zorder=20)
    ax.add_feature(cfeature.COASTLINE, edgecolor='k', linewidth=1, zorder=21)
    ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.4, zorder=21)

    plt.title('ECMWF Sea Surface Temperature Anomaly (°C)', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=24, color='white', weight="bold")
    cbar = plt.colorbar(data, ax=ax, ticks=[-2,0,2], pad=0.01, shrink=0.5, aspect=20)
    cbar.ax.tick_params(labelsize=24, labelcolor="white") 
    cbar.ax.set_facecolor([1,1,1,0])

    for label in cbar.ax.get_yticklabels():
        label.set_weight('bold')
    
    ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
    fig.patch.set_facecolor('k')

    try:

        fig.subplots_adjust(bottom=0.12)

    except Exception:

        pass

    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/sst_atlantic_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'{}_atlantic.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

    plt.close("all")

# %% Notebook cell 46

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-2, 2, 60)

data = plt.contourf(lons, lats, season1, levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

ax.add_feature(cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_0_countries',
    scale='10m',
    facecolor='none',
    edgecolor='k',
    linewidth=1
), zorder=21)

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

ax.add_feature(cfeature.LAND.with_scale('50m'), color='dimgray', edgecolor='k', zorder=20)
ax.add_feature(cfeature.COASTLINE, edgecolor='k', linewidth=1, zorder=21)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.4, zorder=21)

plt.title('ECMWF Sea Surface Temperature Anomaly (°C)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month2, month4), loc='right', fontsize=24, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-2,0,2], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=24, labelcolor="white") 
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/sst_{}-{}.png').format(current_month, second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_globe.png'.format(valid_time[1], valid_time[3]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 47

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

levels = np.linspace(-2, 2, 60)

data = plt.contourf(lons, lats, season2, levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

ax.add_feature(cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_0_countries',
    scale='10m',
    facecolor='none',
    edgecolor='k',
    linewidth=1
), zorder=21)

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

ax.add_feature(cfeature.LAND.with_scale('50m'), color='dimgray', edgecolor='k', zorder=20)
ax.add_feature(cfeature.COASTLINE, edgecolor='k', linewidth=1, zorder=21)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.4, zorder=21)

# ax.add_feature(cfeature.COASTLINE, edgecolor='white', zorder = 21)
# ax.add_feature(cfeature.BORDERS, edgecolor='white', zorder = 21)
# ax.add_feature(states_provinces, edgecolor='white', zorder = 21)
# ax.add_feature(cfeature.LAND.with_scale('50m'), color='k', edgecolor='k', zorder = 20)

plt.title('ECMWF Sea Surface Temperature Anomaly (°C)', loc='left', fontsize=24, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=24, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-2,0,2], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=24, labelcolor="white") 
cbar.ax.set_facecolor([1,1,1,0])

for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/sst_{}-{}.png').format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'{}-{}_globe.png'.format(valid_time[3], valid_time[5]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 48

fig = plt.figure(figsize=(30, 20))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=270))

levels = np.linspace(-2, 2, 60)

data = plt.contourf(lons, lats, season1, levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

ax.add_feature(cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_0_countries',
    scale='10m',
    facecolor='none',
    edgecolor='k',
    linewidth=1
), zorder=21)

ax.add_feature(cfeature.LAND.with_scale('50m'), color='dimgray', edgecolor='k', zorder=20)
ax.add_feature(cfeature.COASTLINE, edgecolor='k', linewidth=1, zorder=21)
ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.4, zorder=21)

# ax.add_feature(cfeature.COASTLINE, edgecolor='white', zorder = 21)
# ax.add_feature(cfeature.BORDERS, edgecolor='white', zorder = 21)
# ax.add_feature(states_provinces, edgecolor='white', zorder = 21)
# ax.add_feature(cfeature.LAND.with_scale('50m'), color='k', edgecolor='k', zorder = 20)

ax.text(0.01, 0.02, 'BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, backgroundcolor='.75', fontsize=20)
fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'downloads/sst_{}-{}.png').format(next_month, third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 50

# this loads all dfs at once
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

# %% Notebook cell 51

concats = xr.concat(dsets, dim ="GCM")
sst = concats.mean("GCM")

# %% Notebook cell 52

sst['step'] = pd.to_datetime((pd.to_datetime(sst['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

# %% Notebook cell 53

sst['valid_time'] = sst['step']

# %% Notebook cell 54

sst = sst['ssta']

# %% Notebook cell 55

for i in range(len(sst)):
    nino34 = sst.sel(longitude=slice(190., 240.), latitude=slice(-5., 5.)).mean('latitude').mean('longitude')

# %% Notebook cell 56

nino34 = nino34.to_dataframe()

# %% Notebook cell 57

nino34 = nino34.reset_index()

# %% Notebook cell 58

nino34 = nino34.drop(columns=['step','number','surface','time'])

# %% Notebook cell 59

nino34 = nino34.rename(columns={'valid_time': 'Month', 'ssta': 'SST Anomaly (°C)'})

# %% Notebook cell 60

nino34['Month'] = nino34['Month'].dt.to_period('M')

# %% Notebook cell 61

nino34.to_csv(_os.path.join(_WORK, 'downloads/ecmwf_sst.csv'))

# %% Notebook cell 62

nino34 = (
    nino34.style
    .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2)
    .hide(axis="index")
    .set_caption("Niño 3.4 index anomalies (°C) over the next 6 months")
    .format("{:.2f}", subset=nino34.select_dtypes(include="number").columns)
    .set_properties(**{
        'text-align': 'center',
        'font-size': '24px',
        'font-weight': 'bold',
        'color': 'black'
    })
)

# %% Notebook cell 63

# nino34

# %% Notebook cell 64

import matplotlib
matplotlib.colormaps.get_cmap = lambda name: matplotlib.colormaps[name]

# %% Notebook cell 65

dfi.export(nino34,_os.path.join(_WORK, 'downloads/ecmwf_nino34_{}.png').format(this_month))
#dfi.export(nino34, fig_path/'nino34_{}.png'.format(this_month))