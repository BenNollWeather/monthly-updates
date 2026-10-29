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
"""Auto-converted from ecmwf_sst-relative.ipynb.

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
from shapely.geometry import box

# Canonical climate-index regions in east-longitude coordinates (0-360).
# Defining these boxes in code avoids malformed or inconsistently wrapped
# local shapefiles, especially around the dateline in the central Pacific.
CLIMATE_REGIONS = {
    "nino34": {"label": "Niño 3.4", "bounds": (190.0, -5.0, 240.0, 5.0), "group": "enso"},
    "nino3":  {"label": "Niño 3",   "bounds": (210.0, -5.0, 270.0, 5.0), "group": "enso"},
    "nino4":  {"label": "Niño 4",   "bounds": (160.0, -5.0, 210.0, 5.0), "group": "enso"},
    "nino12": {"label": "Niño 1+2", "bounds": (270.0, -10.0, 280.0, 0.0), "group": "enso"},
    "iode":   {"label": "IOD-E",     "bounds": (90.0, -10.0, 110.0, 0.0), "group": "other"},
    "iodw":   {"label": "IOD-W",     "bounds": (50.0, -10.0, 70.0, 10.0), "group": "other"},
    "atlantic": {"label": "Atlantic MDR", "bounds": (280.0, 10.0, 340.0, 20.0), "group": "other"},
}

SHOW_REGION_LABELS = True
SHOW_NON_ENSO_REGIONS = True


def climate_region_geometries(include_non_enso=True):
    """Build canonical climate-region polygons directly from lon/lat bounds."""
    regions = []
    for key, spec in CLIMATE_REGIONS.items():
        if not include_non_enso and spec["group"] != "enso":
            continue
        west, south, east, north = spec["bounds"]
        regions.append((key, spec, box(west, south, east, north)))
    return regions


def add_climate_regions(ax):
    """Draw climate-index boxes with a high-contrast two-pass outline."""
    for key, spec, geometry in climate_region_geometries(SHOW_NON_ENSO_REGIONS):
        is_enso = spec["group"] == "enso"

        # White halo keeps the boxes visible over both warm and cool anomalies.
        halo = ShapelyFeature(
            [geometry],
            ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="white",
        )
        ax.add_feature(halo, linewidth=5.0 if is_enso else 3.5, zorder=30)

        outline = ShapelyFeature(
            [geometry],
            ccrs.PlateCarree(),
            facecolor="none",
            edgecolor="black",
        )
        ax.add_feature(outline, linewidth=2.6 if is_enso else 1.8, zorder=31)

        if SHOW_REGION_LABELS:
            west, south, east, north = spec["bounds"]
            ax.text(
                (west + east) / 2.0,
                north - 0.7,
                spec["label"],
                transform=ccrs.PlateCarree(),
                ha="center",
                va="top",
                fontsize=11 if is_enso else 9,
                fontweight="bold",
                color="white",
                zorder=32,
                bbox=dict(
                    facecolor="black",
                    edgecolor="white",
                    linewidth=0.8,
                    alpha=0.78,
                    boxstyle="round,pad=0.18",
                ),
            )

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

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/ecmwf_sst-relative").format(dl_month)
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

# %% Notebook cell 36

tropics_mean = sst.sel(longitude=slice(0., 360.), latitude=slice(-20., 20.)).mean('latitude').mean('longitude')

# %% Notebook cell 37

relative_sst = sst - tropics_mean

# %% Notebook cell 39

lon = relative_sst['longitude']
lat = relative_sst['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 40

relative_sst.load()

# %% Notebook cell 41

relative_sst = relative_sst['ssta'].data

# %% Notebook cell 42

relative_sst, cyclic_lons = add_cyclic_point(relative_sst, coord=lon)

# %% Notebook cell 43

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 44

season1 = (relative_sst[0]+relative_sst[1]+relative_sst[2])/3
season2 = (relative_sst[3]+relative_sst[4]+relative_sst[5])/3

# %% Notebook cell 46

for i in range(len(relative_sst)):

    fig = plt.figure(figsize=(25, 15))

    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([0, 359.9, -20, 20])
    
    levels = np.linspace(-2, 2, 17)

    data = plt.contourf(lons, lats, relative_sst[i], levels=levels, cmap=cmocean.cm.balance, transform=ccrs.PlateCarree(), extend='both')

    states_provinces = cfeature.NaturalEarthFeature(
    category='cultural',
    name='admin_1_states_provinces_lines',
    scale='50m',
    facecolor='none')

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

    # Add canonical ENSO/IOD/Atlantic climate-region boxes.
    add_climate_regions(ax)

    ax.add_feature(cfeature.COASTLINE, edgecolor='white', zorder = 21)
    ax.add_feature(cfeature.BORDERS, edgecolor='white', zorder = 21)
    ax.add_feature(states_provinces, edgecolor='white', zorder = 21)
    ax.add_feature(cfeature.LAND.with_scale('50m'), color='k', edgecolor='k', zorder = 20)
    ax.add_feature(cfeature.LAKES,alpha=0.3, zorder = 21)

    plt.title('ECMWF Relative Sea Surface Temperature Anomaly (°C)', loc='left', fontsize=20, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=20, color='white', weight="bold")
    cbar = plt.colorbar(data, ax=ax, ticks=[-2,0,2], pad=0.01, shrink=0.15, aspect=20)
    cbar.ax.tick_params(labelsize=16, labelcolor="white") 
    cbar.ax.set_facecolor([1,1,1,0])

    for label in cbar.ax.get_yticklabels():
        label.set_weight('bold')
    
    ax.text(0.01, 0.04, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, zorder=22, color='white', weight="bold", fontsize=14, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
    fig.patch.set_facecolor('k')

    try:

        fig.subplots_adjust(bottom=0.12)

    except Exception:

        pass

    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/sst_{}-relative.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'{}_globe-relative.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

    plt.close("all")

# %% Notebook cell 48

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

# %% Notebook cell 49

concats = xr.concat(dsets, dim ="GCM")
sst = concats.mean("GCM")

# %% Notebook cell 50

sst['step'] = pd.to_datetime((pd.to_datetime(sst['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

# %% Notebook cell 51

sst['valid_time'] = sst['step']

# %% Notebook cell 52

tropics_mean = sst.sel(longitude=slice(0., 360.), latitude=slice(-20., 20.)).mean('latitude').mean('longitude')

# %% Notebook cell 53

relative_sst = sst['ssta'] - tropics_mean['ssta']

# %% Notebook cell 54

for i in range(len(relative_sst)):
    nino34 = relative_sst.sel(longitude=slice(190., 240.), latitude=slice(-5., 5.)).mean('latitude').mean('longitude')

# %% Notebook cell 55

nino34 = nino34.to_dataframe()

# %% Notebook cell 56

nino34 = nino34.reset_index()

# %% Notebook cell 57

nino34 = nino34.drop(columns=['step','number','surface','time'])

# %% Notebook cell 58

nino34 = nino34.rename(columns={'valid_time': 'Month', 'ssta': 'Relative SST Anomaly (°C)'})

# %% Notebook cell 59

nino34['Month'] = nino34['Month'].dt.to_period('M')

# %% Notebook cell 60

nino34

# %% Notebook cell 61

nino34.to_csv(_os.path.join(_WORK, 'downloads/ecmwf_sst_relative.csv'))

# %% Notebook cell 62

# Read data from files
sst = pd.read_csv(_os.path.join(_WORK, 'downloads/ecmwf_sst.csv'))
sst_relative = pd.read_csv(_os.path.join(_WORK, 'downloads/ecmwf_sst_relative.csv'))

# Merge the data on the 'Month' column
merged_data = pd.merge(sst, sst_relative, on='Month')

# %% Notebook cell 63

# Drop the column "Unnamed: 0_x"
merged_data = merged_data.drop(columns=["Unnamed: 0_x", "Unnamed: 0_y"])

# %% Notebook cell 64

nino34 = (
    merged_data.style
    .background_gradient(cmap='cmo.balance', vmin=-3, vmax=3)
    .hide(axis="index")
    .set_caption("ECMWF Niño 3.4 index anomalies (°C)")
    .format("{:.2f}", subset=merged_data.select_dtypes(include="number").columns)
    .set_table_styles([
        {
            'selector': 'caption',
            'props': [
                ('color', 'white'),
                ('font-size', '24px'),
                ('font-weight', 'bold'),
                ('background-color', 'black'),
                ('text-align', 'left')
            ]
        },
        {
            'selector': 'thead',
            'props': [
                ('color', 'white'),
                ('font-size', '20px'),
                ('text-align', 'left'),
                ('background-color', 'black'),
                ("border", "0.25px solid gray")
            ]
        }
    ])
    .set_properties(**{
        'text-align': 'right',
        'font-size': '30px',
        'font-weight': 'normal',
        'color': 'white',
        'border': '0.25px solid gray',
        'padding': '6px',
        'background-color': 'black'
    })
)

# %% Notebook cell 65

# nino34

# %% Notebook cell 66

import matplotlib
matplotlib.colormaps.get_cmap = lambda name: matplotlib.colormaps[name]

# %% Notebook cell 67

dfi.export(nino34,_os.path.join(_WORK, 'downloads/ecmwf_nino34_{}-relative.png').format(this_month))
dfi.export(nino34,_os.path.join(_WORK, 'copernicus_imagery/ecmwf_nino34-relative.png'))