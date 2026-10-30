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
"""Auto-converted from zonal.ipynb.

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

# %% Notebook cell 1

from matplotlib import rcParams
from cartopy.util import add_cyclic_point
from cartopy.io.shapereader import Reader

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

from cartopy.feature import ShapelyFeature

# %% Notebook cell 2

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from metpy.plots import USCOUNTIES
import cmocean

# %% Notebook cell 3

from glob import glob
import os
import pathlib
from dateparser import parse
import urllib.request

# %% Notebook cell 4

from glob import glob

# %% Notebook cell 5

import seaborn as sns

# %% Notebook cell 7

from dateparser import parse

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

# %% Notebook cell 13

names = ['1','2','3','4','5','6']

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

# %% Notebook cell 17

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 19

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/zonal").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/zonal/{}").format(dl_month)

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
    'seasonal-postprocessed-pressure-levels',
    {
        'originating_centre': [
            'cmcc', 'dwd', 'eccc',
            'ecmwf', 'jma', 'meteo_france',
            'ncep', 'ukmo', 'bom'
        ],
        'system': C3S_MULTI_MODEL_SYSTEMS,
        'variable': 'u_component_of_wind_anomaly',
        'pressure_level': '850',
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    dl_path/'c3s_zonal.grib')

# %% Notebook cell 25

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-pressure-levels',
#     {
#         'originating_centre': [
#             'cmcc', 'dwd', 'eccc',
#             'ecmwf', 'jma', 'meteo_france',
#             'ncep', 'ukmo'
#         ],
#         'variable': ['u_component_of_wind_anomaly'],
#         'pressure_level': ['850'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_zonal.grib')

# %% Notebook cell 26

# this loads all dfs at once
df = cfgrib.open_datasets(dl_path/"c3s_zonal.grib")
lats = np.linspace(-90, 90, 181)
lons = np.linspace(0, 359, 360)
dsets = []
for dataset in df:
    dataset = dataset.interp(latitude = lats,
                   longitude = lons,
                   method ='nearest')
    dataset['ua'] = dataset['ua'].expand_dims({"GCM":1})
    dataset['GCM'] = (('GCM'),[dataset.attrs['institution']] )
    dsets.append(dataset)
concats = xr.concat(dsets, dim ="GCM")
u850 = concats.mean("GCM")

# %% Notebook cell 28

u850['step'] = pd.to_datetime((pd.to_datetime(u850['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

# %% Notebook cell 29

u850['valid_time'] = u850['step']

# %% Notebook cell 30

valid_time = u850['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 31

valid_time = valid_time.values

# %% Notebook cell 32

u850 = u850['ua']*1.94384

# %% Notebook cell 34

lon = u850['longitude']
lat = u850['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 35

u850.load()

# %% Notebook cell 36

u850 = u850.data

# %% Notebook cell 37

u850, cyclic_lons = add_cyclic_point(u850, coord=lon)

# %% Notebook cell 38

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 40

cmap = "RdBu_r"

# %% Notebook cell 42

for i in range(len(u850)):
    fig = plt.figure(figsize=[25,15])
    
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
    
    data = ax.pcolormesh(lons, lats, u850[i], vmin=-3, vmax=3, cmap='RdBu_r', transform=ccrs.PlateCarree())
    
    states_provinces = cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_1_states_provinces_lines',
    scale='50m',
    facecolor='none')
    

    ax.coastlines(resolution='10m', color='k', linewidth=2)
    ax.add_feature(cfeature.LAND)
    ax.add_feature(cfeature.BORDERS, edgecolor='k', linewidth=2)
    ax.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.3)
    ax.add_feature(states_provinces, edgecolor='k')
    
    shape1 = get_shp(_os.path.join(_SHAPES, "nino34"))
    shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
    ax.add_feature(shape1_feature, linewidth=5, zorder = 22)
        
    plt.title('C3S 850 hPa zonal wind anomaly (kts)', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=20, color='white', weight="bold")
    
    cbar = plt.colorbar(data, ax=ax, ticks=[-3,0,3], pad=0.01, shrink=0.5, aspect=20)
    cbar.ax.tick_params(labelsize=18, labelcolor="white")
    cbar.ax.set_facecolor([1,1,1,0])
    
    for label in cbar.ax.get_yticklabels():
        label.set_weight('bold')
    
    ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

    fig.patch.set_facecolor('k')
    
    try:
    
        fig.subplots_adjust(bottom=0.12)
    
    except Exception:
    
        pass
    
    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_zonal_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'zonal_{}.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)    

# %% Notebook cell 44

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

# %% Notebook cell 45

df = xr.open_dataset(dl_path/"c3s_zonal-members.grib")

# %% Notebook cell 46

ecmwf = df

# %% Notebook cell 47

ecmwf['step'] = pd.to_datetime((pd.to_datetime(ecmwf['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

ecmwf['valid_time'] = ecmwf['step']

valid_time = ecmwf['valid_time'].dt.strftime('%Y-%m')

valid_time = valid_time.values

ecmwf = ecmwf['ua']*1.94384

# %% Notebook cell 48

nino34 = ecmwf.sel(latitude=slice(5., -5.), longitude=slice(190., 240))
nino34 = nino34.mean('latitude').mean('longitude')

# %% Notebook cell 49

nino34.plot()

# %% Notebook cell 50

fig, axes = plt.subplots(figsize=(25, 15))

xticklabels = [month1, month2, month3, month4, month5, month6]

ax = sns.heatmap(nino34, linewidth=.5, cmap="RdBu_r", vmin=-8, vmax=8, xticklabels=xticklabels)

# ax.set_xlabel("Forecast step",fontsize=20)
ax.set_ylabel("Ensemble member",fontsize=20)

ax.set_title("ECMWF average zonal wind speed anomaly (kts) in NINO34 region", loc="left", color='k', fontsize=24)

for tick_label in ax.axes.get_yticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("12")
  
for tick_label in ax.axes.get_xticklabels():
    tick_label.set_color("k")
    tick_label.set_fontsize("24")

cbar = ax.collections[0].colorbar
cbar.ax.tick_params(labelsize=20)

ax.text(0.85, 1.01, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('white')
plt.tight_layout()
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(_os.path.join(_WORK, "downloads/ecmwf_zonal_{}.png").format(dl_month))
# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/ecmwf_zonal_heatmap.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)