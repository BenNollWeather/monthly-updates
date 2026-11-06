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
"""Auto-converted from height.ipynb.

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

# %% Notebook cell 6

from dateparser import parse

# %% Notebook cell 7

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 8

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 9

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 10

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 12

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 13

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 14

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 16

names = ['1','2','3','4','5','6']

# %% Notebook cell 18

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/height").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/height/{}").format(dl_month)

# %% Notebook cell 19

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 20

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 21

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 23

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
        'system': C3S_HEIGHT_SYSTEMS,
        'variable': 'geopotential_anomaly',
        'pressure_level': '500',
        'product_type': 'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month': [
            '1', '2', '3',
            '4', '5', '6',
        ],
        'format': 'grib',
    },
    dl_path/'c3s_500.grib')

# %% Notebook cell 24

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-postprocessed-pressure-levels',
#     {
#         'originating_centre': ['cmcc', 'dwd', 'eccc', 'ecmwf', 'jma', 'meteo_france', 'ncep', 'ukmo'],
#         # 'system': ['1', '2', '5', '8', '21', '35', '600'],
#         'variable': ['geopotential_anomaly'],
#         'pressure_level': ['500'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'c3s_500.grib')

# %% Notebook cell 25

# this loads all dfs at once
df = cfgrib.open_datasets(dl_path/"c3s_500.grib")
lats = np.linspace(-90, 90, 181)
lons = np.linspace(0, 359, 360)
dsets = []
for dataset in df:
    dataset = dataset.interp(latitude = lats,
                   longitude = lons,
                   method ='nearest')
    dataset['za'] = dataset['za'].expand_dims({"GCM":1})
    dataset['GCM'] = (('GCM'),[dataset.attrs['institution']] )
    dsets.append(dataset)
concats = xr.concat(dsets, dim ="GCM")

# Normalize GCM coordinate labels (strip whitespace)
if "GCM" in concats.coords:
    concats = concats.assign_coords(GCM=[str(x).strip() for x in concats.GCM.values])

def select_gcm(ds, *names):
    """Select a GCM robustly using stripped, case-insensitive labels and aliases."""
    if "GCM" not in ds.coords:
        raise KeyError("Dataset has no GCM coordinate")

    labels = [str(x).strip() for x in ds.GCM.values]
    lookup = {label.casefold(): label for label in labels}

    for name in names:
        key = str(name).strip().casefold()
        if key in lookup:
            return ds.sel(GCM=lookup[key])

    # fallback: substring/contains matching for vendor-location variants
    folded_labels = [(label.casefold(), label) for label in labels]
    for name in names:
        key = str(name).strip().casefold()
        for folded, label in folded_labels:
            if key in folded or folded in key:
                return ds.sel(GCM=label)

    raise KeyError(
        "Could not find requested GCM. Requested one of: "
        + ", ".join(str(n) for n in names)
        + ". Available GCMs: "
        + ", ".join(labels)
    )

z500 = concats.mean("GCM")

# %% Notebook cell 27

z500['step'] = pd.to_datetime((pd.to_datetime(z500['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

# %% Notebook cell 28

z500['valid_time'] = z500['step']

# %% Notebook cell 29

valid_time = z500['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 30

valid_time = valid_time.values

# %% Notebook cell 31

# CDS stores geopotential anomaly in m^2/s^2. Decameters use standard gravity.
GEOPOTENTIAL_TO_DAM = 9.80665 * 10
z500 = z500['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 33

lon = z500['longitude']
lat = z500['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 34

z500.load()

# %% Notebook cell 35

z500 = z500.data

# %% Notebook cell 36

z500, cyclic_lons = add_cyclic_point(z500, coord=lon)

# %% Notebook cell 37

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 39

cmap = "RdBu_r"

# %% Notebook cell 41

for i in range(len(z500)):
    fig = plt.figure(figsize=[25,15])
    
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

#     ax = plt.axes(projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=5000000))

    levels = np.linspace(-10, 10, 21)

    data = plt.contourf(lons, lats, z500[i], levels=levels, cmap=cmap, extend='both', transform=ccrs.PlateCarree())
    data2 = plt.contour(lons, lats, z500[i], levels=levels, colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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
    
    plt.title('C3S 500 hPa height anomaly', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=20, color='white', weight="bold")
    
#     cbar = plt.colorbar(data, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.85, aspect=50)
#     cbar.ax.tick_params(labelsize=20, labelcolor="white")
#     cbar.ax.set_facecolor([1,1,1,0])
    
    # Add a legend for labels
    legend_labels = {"#CE5146": "Above average", "#3C8ABE": "Below average"}

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
                   ncol=2                        # Above average and Below average on one row
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

    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_globe_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=200)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'height_{}.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=200)

# %% Notebook cell 42

for i in range(len(z500)):
    fig = plt.figure(figsize=[25,15])
    
    ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))
    ax.set_extent([205, 315, 20, 60])

    levels = np.linspace(-10, 10, 21)

    data = plt.contourf(lons, lats, z500[i], levels=levels, cmap=cmap, extend='both', transform=ccrs.PlateCarree())
    data2 = plt.contour(lons, lats, z500[i], levels=levels, colors='k', linewidths=0.5, transform=ccrs.PlateCarree())

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
    
    plt.title('C3S 500 hPa height anomaly', loc='left', fontsize=24, color='white', weight="bold")
    plt.title('{}'.format(valid_time[i]), loc='right', fontsize=20, color='white', weight="bold")
    
#     cbar = plt.colorbar(data, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.85, aspect=50)
#     cbar.ax.tick_params(labelsize=20, labelcolor="white")
#     cbar.ax.set_facecolor([1,1,1,0])
    
    # Add a legend for labels
    legend_labels = {"#CE5146": "Above average", "#3C8ABE": "Below average"}

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
                   ncol=2                        # Above average and Below average on one row
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

    plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_usa_{}.png').format(names[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
    try:
        fig.subplots_adjust(bottom=0.12)
    except Exception:
        pass
    plt.savefig(fig_path/'height_usa_{}.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 43

# for i in range(len(z500)):
#     fig = plt.figure(figsize=[25,15])
    
# #     ax = plt.axes(projection=ccrs.NorthPolarStereo(central_longitude=-90))
# #     ax.set_extent([-179, 179, 0, 90], crs=ccrs.PlateCarree())
    
#     ax = plt.axes(projection=ccrs.Orthographic(270, 90))

#     levels = np.linspace(-10, 10, 21)

#     data = ax.pcolormesh(lons, lats, z500[i], vmin=-5, vmax=5, cmap=cmap, transform=ccrs.PlateCarree())
#     data2 = plt.contour(lons, lats,  z500[i], 5, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

# #     data = plt.contourf(lons, lats, z500[i], levels=levels, cmap=cmap, extend='both', transform=ccrs.PlateCarree())
# #     data2 = plt.contour(lons, lats, z500[i], levels=levels, colors='k', linewidths=0.5, transform=ccrs.PlateCarree())
    
#     states_provinces = cfeature.NaturalEarthFeature(
#     category='cultural',
#     name='admin_1_states_provinces_lines',
#     scale='50m',
#     facecolor='none')
    
#     ax.add_feature(cfeature.LAND)
#     ax.coastlines(resolution='10m', color='k', linewidth=1)
#     ax.add_feature(cfeature.BORDERS)
#     ax.add_feature(cfeature.LAKES, edgecolor='black', alpha=0.2)
#     ax.add_feature(states_provinces, edgecolor='k', linewidth=1)
    
#     plt.title('C3S 500 hPa Height Anomaly (dam)', loc='left', fontsize=20, color='white')
#     plt.title('{}'.format(valid_time[i]), loc='right', fontsize=20, color='white')
    
#     cbar = plt.colorbar(data, ax=ax, ticks=[-10,-5,0,5,10], pad=0.01, shrink=0.85, aspect=50)
#     cbar.ax.tick_params(labelsize=20, labelcolor="white")
#     cbar.ax.set_facecolor([1,1,1,0])

#     ax.text(0.02, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))
    
#     fig.patch.set_facecolor('k')

#     plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_nh_{}.png').format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
#     plt.savefig(fig_path/'height_nh_{}.png'.format(valid_time[i]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 45

eccc1 = select_gcm(concats, 'Canadian Meteorological Service - Montreal', 'ECCC', 'Canadian Meteorological Service').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
eccc2 = select_gcm(concats, 'Canadian Meteorological Service - Montreal', 'ECCC', 'Canadian Meteorological Service').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
eccc3 = select_gcm(concats, 'Canadian Meteorological Service - Montreal', 'ECCC', 'Canadian Meteorological Service').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 46

cmcc1 = select_gcm(concats, 'Rome', 'CMCC', 'Centro Euro-Mediterraneo sui Cambiamenti Climatici').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
cmcc2 = select_gcm(concats, 'Rome', 'CMCC', 'Centro Euro-Mediterraneo sui Cambiamenti Climatici').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
cmcc3 = select_gcm(concats, 'Rome', 'CMCC', 'Centro Euro-Mediterraneo sui Cambiamenti Climatici').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 47

dwd1 = select_gcm(concats, 'Offenbach', 'DWD', 'Deutscher Wetterdienst').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
dwd2 = select_gcm(concats, 'Offenbach', 'DWD', 'Deutscher Wetterdienst').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
dwd3 = select_gcm(concats, 'Offenbach', 'DWD', 'Deutscher Wetterdienst').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 48

ukmet1 = select_gcm(concats, 'U.K. Met Office - Exeter', 'UK Met Office - Exeter', 'UKMO').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ukmet2 = select_gcm(concats, 'U.K. Met Office - Exeter', 'UK Met Office - Exeter', 'UKMO').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ukmet3 = select_gcm(concats, 'U.K. Met Office - Exeter', 'UK Met Office - Exeter', 'UKMO').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 49

ncep1 = select_gcm(concats, 'US National Weather Service - NCEP', 'NCEP').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ncep2 = select_gcm(concats, 'US National Weather Service - NCEP', 'NCEP').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ncep3 = select_gcm(concats, 'US National Weather Service - NCEP', 'NCEP').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 50

mf1 = select_gcm(concats, 'French Weather Service - Toulouse', 'Meteo France', 'Météo-France', 'Meteo-France').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
mf2 = select_gcm(concats, 'French Weather Service - Toulouse', 'Meteo France', 'Météo-France', 'Meteo-France').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
mf3 = select_gcm(concats, 'French Weather Service - Toulouse', 'Meteo France', 'Météo-France', 'Meteo-France').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 51

ecmwf1 = select_gcm(concats, 'European Centre for Medium-Range Weather Forecasts', 'ECMWF').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ecmwf2 = select_gcm(concats, 'European Centre for Medium-Range Weather Forecasts', 'ECMWF').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
ecmwf3 = select_gcm(concats, 'European Centre for Medium-Range Weather Forecasts', 'ECMWF').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 52

jma1 = select_gcm(concats, 'Japanese Meteorological Agency - Tokyo', 'JMA', 'Tokyo').isel(step = slice(1,3)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
jma2 = select_gcm(concats, 'Japanese Meteorological Agency - Tokyo', 'JMA', 'Tokyo').isel(step = slice(3,5)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM
jma3 = select_gcm(concats, 'Japanese Meteorological Agency - Tokyo', 'JMA', 'Tokyo').isel(step = slice(2,4)).mean('step')['za'] / GEOPOTENTIAL_TO_DAM

# %% Notebook cell 53

lon2 = concats['longitude']
lat2 = concats['latitude']
lons2, lats2 = np.meshgrid(lon2, lat2)

# %% Notebook cell 55

states_provinces = cfeature.NaturalEarthFeature(
category='cultural',
name='admin_1_states_provinces_lines',
scale='50m',
facecolor='none')

def _name_above_globe(ax, name):
    """Keep the agency name above the disk instead of on the limb."""
    ax.text(
        0.5,
        1.08,
        name,
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        color="white",
        weight="bold",
        fontsize=20,
        clip_on=False,
        zorder=40,
    )


def _finish_height_panel(fig, mappable):
    """Park a shorter colorbar under the globes and the season title in the top margin."""
    cax = fig.add_axes([0.28, 0.034, 0.44, 0.016])
    colorbar = fig.colorbar(
        mappable,
        cax=cax,
        orientation="horizontal",
        ticks=[-10, -5, 0, 5, 10],
        drawedges=True,
    )
    colorbar.ax.tick_params(labelsize=24, labelcolor="white")
    for label in colorbar.ax.get_xticklabels():
        label.set_weight("bold")
        label.set_color("white")
    fig.patch.set_facecolor("#000000")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.76, bottom=0.12, wspace=0.04, hspace=0.42)
    season = ""
    for ax in fig.axes:
        getter = getattr(ax, "get_title", None)
        if getter is None:
            continue
        try:
            text = getter(loc="left") or ""
        except TypeError:
            text = ""
        if "height anomaly" in text.lower():
            season = text.strip()
            ax.set_title("", loc="left")
            break
    if season:
        fig.text(
            0.02,
            0.985,
            season,
            ha="left",
            va="top",
            color="white",
            weight="bold",
            fontsize=40,
        )
    fig.text(
        0.02,
        0.042,
        "@BenNollWeather",
        ha="left",
        va="center",
        color="white",
        weight="bold",
        fontsize=20,
    )


# %% Notebook cell 56

fig = plt.figure(figsize=(25, 15))

levels = np.linspace(-10, 10, 21)

# model 1
ax1 = fig.add_subplot(2, 4, 1, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax1.add_feature(cfeature.COASTLINE, edgecolor='k')
ax1.add_feature(cfeature.BORDERS, edgecolor='k')
ax1.add_feature(states_provinces, edgecolor='k')
ax1.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

cmap='RdBu_r'

data = plt.contourf(lons2, lats2, ecmwf1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

ax1.set_title('{}-{} 500 hPa height anomaly (dam)'.format(month2, month4), loc='left', fontsize=28, color='white', weight="bold", pad=64)
_name_above_globe(ax1, 'ECMWF')

# model 2
ax2 = fig.add_subplot(2, 4, 2, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax2.add_feature(cfeature.COASTLINE, edgecolor='k')
ax2.add_feature(cfeature.BORDERS, edgecolor='k')
ax2.add_feature(states_provinces, edgecolor='k')
ax2.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data2 = plt.contourf(lons2, lats2, ukmet1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax2, 'UKMET')

# model 3
ax3 = fig.add_subplot(2, 4, 3, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax3.add_feature(cfeature.COASTLINE, edgecolor='k')
ax3.add_feature(cfeature.BORDERS, edgecolor='k')
ax3.add_feature(states_provinces, edgecolor='k')
ax3.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data3 = plt.contourf(lons2, lats2, ncep1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax3, 'NCEP')

# model 4
ax4 = fig.add_subplot(2, 4, 4, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax4.add_feature(cfeature.COASTLINE, edgecolor='k')
ax4.add_feature(cfeature.BORDERS, edgecolor='k')
ax4.add_feature(states_provinces, edgecolor='k')
ax4.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data4 = plt.contourf(lons2, lats2, jma1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax4, 'JMA')

# model 5
ax5 = fig.add_subplot(2, 4, 5, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax5.add_feature(cfeature.COASTLINE, edgecolor='k')
ax5.add_feature(cfeature.BORDERS, edgecolor='k')
ax5.add_feature(states_provinces, edgecolor='k')
ax5.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data5 = plt.contourf(lons2, lats2, eccc1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax5, 'ECCC')

# model 6
ax6 = fig.add_subplot(2, 4, 6, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax6.add_feature(cfeature.COASTLINE, edgecolor='k')
ax6.add_feature(cfeature.BORDERS, edgecolor='k')
ax6.add_feature(states_provinces, edgecolor='k')
ax6.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data6 = plt.contourf(lons2, lats2, mf1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax6, 'Météo-France')

# model 7
ax7 = fig.add_subplot(2, 4, 7, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax7.add_feature(cfeature.COASTLINE, edgecolor='k')
ax7.add_feature(cfeature.BORDERS, edgecolor='k')
ax7.add_feature(states_provinces, edgecolor='k')
ax7.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data7 = plt.contourf(lons2, lats2, dwd1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax7, 'DWD')

# model 8
ax8 = fig.add_subplot(2, 4, 8, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax8.add_feature(cfeature.COASTLINE, edgecolor='k')
ax8.add_feature(cfeature.BORDERS, edgecolor='k')
ax8.add_feature(states_provinces, edgecolor='k')
ax8.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data8 = plt.contourf(lons2, lats2, cmcc1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax8, 'CMCC')

_finish_height_panel(fig, data6)

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'height_{}_{}.png'.format(valid_time[0], valid_time[2]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 57

fig = plt.figure(figsize=(25, 15))

levels = np.linspace(-10, 10, 21)

# model 1
ax1 = fig.add_subplot(2, 4, 1, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax1.add_feature(cfeature.COASTLINE, edgecolor='k')
ax1.add_feature(cfeature.BORDERS, edgecolor='k')
ax1.add_feature(states_provinces, edgecolor='k')
ax1.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

cmap='RdBu_r'

data = plt.contourf(lons2, lats2, ecmwf2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

ax1.set_title('{}-{} 500 hPa height anomaly (dam)'.format(month4, month6), loc='left', fontsize=28, color='white', weight="bold", pad=64)
_name_above_globe(ax1, 'ECMWF')

# model 2
ax2 = fig.add_subplot(2, 4, 2, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax2.add_feature(cfeature.COASTLINE, edgecolor='k')
ax2.add_feature(cfeature.BORDERS, edgecolor='k')
ax2.add_feature(states_provinces, edgecolor='k')
ax2.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data2 = plt.contourf(lons2, lats2, ukmet2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax2, 'UKMET')

# model 3
ax3 = fig.add_subplot(2, 4, 3, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax3.add_feature(cfeature.COASTLINE, edgecolor='k')
ax3.add_feature(cfeature.BORDERS, edgecolor='k')
ax3.add_feature(states_provinces, edgecolor='k')
ax3.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data3 = plt.contourf(lons2, lats2, ncep2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax3, 'NCEP')

# model 4
ax4 = fig.add_subplot(2, 4, 4, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax4.add_feature(cfeature.COASTLINE, edgecolor='k')
ax4.add_feature(cfeature.BORDERS, edgecolor='k')
ax4.add_feature(states_provinces, edgecolor='k')
ax4.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data4 = plt.contourf(lons2, lats2, jma2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax4, 'JMA')

# model 5
ax5 = fig.add_subplot(2, 4, 5, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax5.add_feature(cfeature.COASTLINE, edgecolor='k')
ax5.add_feature(cfeature.BORDERS, edgecolor='k')
ax5.add_feature(states_provinces, edgecolor='k')
ax5.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data5 = plt.contourf(lons2, lats2, eccc2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax5, 'ECCC')

# model 6
ax6 = fig.add_subplot(2, 4, 6, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax6.add_feature(cfeature.COASTLINE, edgecolor='k')
ax6.add_feature(cfeature.BORDERS, edgecolor='k')
ax6.add_feature(states_provinces, edgecolor='k')
ax6.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data6 = plt.contourf(lons2, lats2, mf2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax6, 'Météo-France')

# model 7
ax7 = fig.add_subplot(2, 4, 7, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax7.add_feature(cfeature.COASTLINE, edgecolor='k')
ax7.add_feature(cfeature.BORDERS, edgecolor='k')
ax7.add_feature(states_provinces, edgecolor='k')
ax7.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data7 = plt.contourf(lons2, lats2, dwd2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax7, 'DWD')

# model 8
ax8 = fig.add_subplot(2, 4, 8, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
ax8.add_feature(cfeature.COASTLINE, edgecolor='k')
ax8.add_feature(cfeature.BORDERS, edgecolor='k')
ax8.add_feature(states_provinces, edgecolor='k')
ax8.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data8 = plt.contourf(lons2, lats2, cmcc2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax8, 'CMCC')

_finish_height_panel(fig, data6)

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'height_{}_{}.png'.format(valid_time[3], valid_time[5]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 59

# fig = plt.figure(figsize=(25, 15))

# levels = np.linspace(-10, 10, 21)

# # model 1
# ax1 = fig.add_subplot(2, 4, 1, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax1.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax1.add_feature(cfeature.BORDERS, edgecolor='k')
# ax1.add_feature(states_provinces, edgecolor='k')
# ax1.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# cmap='RdBu_r'

# data = plt.contourf(lons2, lats2, ecmwf3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('{}-{} 500 hPa Height Anomaly (dam)\n\n'.format(month3, month5), loc='left', fontsize=28, color='white', weight="bold")
# plt.title('ECMWF', loc='center', fontsize=20, color='white', weight="bold")

# # model 2
# ax2 = fig.add_subplot(2, 4, 2, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax2.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax2.add_feature(cfeature.BORDERS, edgecolor='k')
# ax2.add_feature(states_provinces, edgecolor='k')
# ax2.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data2 = plt.contourf(lons2, lats2, ukmet3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('UKMET', loc='center', fontsize=20, color='white', weight="bold")

# # model 3
# ax3 = fig.add_subplot(2, 4, 3, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax3.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax3.add_feature(cfeature.BORDERS, edgecolor='k')
# ax3.add_feature(states_provinces, edgecolor='k')
# ax3.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data3 = plt.contourf(lons2, lats2, ncep3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('NCEP', loc='center', fontsize=20, color='white', weight="bold")

# model 4
# ax4 = fig.add_subplot(2, 4, 4, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax4.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax4.add_feature(cfeature.BORDERS, edgecolor='k')
# ax4.add_feature(states_provinces, edgecolor='k')
# ax4.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data4 = ax4.contourf(lons2, lats2, jma3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('JMA', loc='center', fontsize=20, color='white', weight="bold")

# # model 5
# ax5 = fig.add_subplot(2, 4, 5, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax5.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax5.add_feature(cfeature.BORDERS, edgecolor='k')
# ax5.add_feature(states_provinces, edgecolor='k')
# ax5.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data5 = plt.contourf(lons2, lats2, eccc3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('ECCC', loc='center', fontsize=20, color='white', weight="bold")

# # model 6
# ax6 = fig.add_subplot(2, 4, 6, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax6.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax6.add_feature(cfeature.BORDERS, edgecolor='k')
# ax6.add_feature(states_provinces, edgecolor='k')
# ax6.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data6 = plt.contourf(lons2, lats2, mf3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('Météo-France', loc='center', fontsize=20, color='white', weight="bold")

# # model 7
# ax7 = fig.add_subplot(2, 4, 7, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax7.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax7.add_feature(cfeature.BORDERS, edgecolor='k')
# ax7.add_feature(states_provinces, edgecolor='k')
# ax7.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data7 = plt.contourf(lons2, lats2, dwd3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('DWD', loc='center', fontsize=20, color='white', weight="bold")

# # model 8
# ax8 = fig.add_subplot(2, 4, 8, projection=ccrs.NearsidePerspective(central_longitude=265, central_latitude=50, satellite_height=4000000))
# ax8.add_feature(cfeature.COASTLINE, edgecolor='k')
# ax8.add_feature(cfeature.BORDERS, edgecolor='k')
# ax8.add_feature(states_provinces, edgecolor='k')
# ax8.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

# data8 = plt.contourf(lons2, lats2, cmcc3, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

# plt.title('CMCC', loc='center', fontsize=20, color='white', weight="bold")

# axes2 = fig.add_axes([0.1, -0.05, 0.8, 0.02])
# cm = fig.colorbar(data6, cax=axes2, orientation='horizontal', ticks=[-10,-5,0,5,10], drawedges=True)
# cm.ax.tick_params(labelsize=24, labelcolor="white")

# for label in cm.ax.get_yticklabels():
#     label.set_weight('bold')

# ax4.text(0.15, 1.18, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax4.transAxes, color='white', weight="bold", fontsize=20, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')
# fig.tight_layout()

# # plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_winter.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'height_{}_{}.png'.format(valid_time[2], valid_time[4]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 61

fig = plt.figure(figsize=(25, 15))

levels = np.linspace(-10, 10, 21)

# model 1
ax1 = fig.add_subplot(2, 4, 1, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax1.add_feature(cfeature.COASTLINE, edgecolor='k')
ax1.add_feature(cfeature.BORDERS, edgecolor='k')
ax1.add_feature(states_provinces, edgecolor='k')
ax1.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

cmap='RdBu_r'

data = plt.contourf(lons2, lats2, ecmwf1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

ax1.set_title('{}-{} 500 hPa height anomaly (dam)'.format(month2, month4), loc='left', fontsize=28, color='white', weight="bold", pad=64)
_name_above_globe(ax1, 'ECMWF')

# model 2
ax2 = fig.add_subplot(2, 4, 2, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax2.add_feature(cfeature.COASTLINE, edgecolor='k')
ax2.add_feature(cfeature.BORDERS, edgecolor='k')
ax2.add_feature(states_provinces, edgecolor='k')
ax2.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data2 = plt.contourf(lons2, lats2, ukmet1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax2, 'UKMET')

# model 3
ax3 = fig.add_subplot(2, 4, 3, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax3.add_feature(cfeature.COASTLINE, edgecolor='k')
ax3.add_feature(cfeature.BORDERS, edgecolor='k')
ax3.add_feature(states_provinces, edgecolor='k')
ax3.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data3 = plt.contourf(lons2, lats2, ncep1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax3, 'NCEP')

# model 4
ax4 = fig.add_subplot(2, 4, 4, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax4.add_feature(cfeature.COASTLINE, edgecolor='k')
ax4.add_feature(cfeature.BORDERS, edgecolor='k')
ax4.add_feature(states_provinces, edgecolor='k')
ax4.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data4 = plt.contourf(lons2, lats2, jma1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax4, 'JMA')

# model 5
ax5 = fig.add_subplot(2, 4, 5, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax5.add_feature(cfeature.COASTLINE, edgecolor='k')
ax5.add_feature(cfeature.BORDERS, edgecolor='k')
ax5.add_feature(states_provinces, edgecolor='k')
ax5.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data5 = plt.contourf(lons2, lats2, eccc1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax5, 'ECCC')

# model 6
ax6 = fig.add_subplot(2, 4, 6, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax6.add_feature(cfeature.COASTLINE, edgecolor='k')
ax6.add_feature(cfeature.BORDERS, edgecolor='k')
ax6.add_feature(states_provinces, edgecolor='k')
ax6.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data6 = plt.contourf(lons2, lats2, mf1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax6, 'Météo-France')

# model 7
ax7 = fig.add_subplot(2, 4, 7, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax7.add_feature(cfeature.COASTLINE, edgecolor='k')
ax7.add_feature(cfeature.BORDERS, edgecolor='k')
ax7.add_feature(states_provinces, edgecolor='k')
ax7.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data7 = plt.contourf(lons2, lats2, dwd1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax7, 'DWD')

# model 8
ax8 = fig.add_subplot(2, 4, 8, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax8.add_feature(cfeature.COASTLINE, edgecolor='k')
ax8.add_feature(cfeature.BORDERS, edgecolor='k')
ax8.add_feature(states_provinces, edgecolor='k')
ax8.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data8 = plt.contourf(lons2, lats2, cmcc1, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax8, 'CMCC')

_finish_height_panel(fig, data6)

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_season1_nz.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'sh_height_{}_{}.png'.format(valid_time[0], valid_time[2]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# %% Notebook cell 62

fig = plt.figure(figsize=(25, 15))

levels = np.linspace(-10, 10, 21)

# model 1
ax1 = fig.add_subplot(2, 4, 1, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax1.add_feature(cfeature.COASTLINE, edgecolor='k')
ax1.add_feature(cfeature.BORDERS, edgecolor='k')
ax1.add_feature(states_provinces, edgecolor='k')
ax1.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

cmap='RdBu_r'

data = plt.contourf(lons2, lats2, ecmwf2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

ax1.set_title('{}-{} 500 hPa height anomaly (dam)'.format(month4, month6), loc='left', fontsize=28, color='white', weight="bold", pad=64)
_name_above_globe(ax1, 'ECMWF')

# model 2
ax2 = fig.add_subplot(2, 4, 2, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax2.add_feature(cfeature.COASTLINE, edgecolor='k')
ax2.add_feature(cfeature.BORDERS, edgecolor='k')
ax2.add_feature(states_provinces, edgecolor='k')
ax2.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data2 = plt.contourf(lons2, lats2, ukmet2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax2, 'UKMET')

# model 3
ax3 = fig.add_subplot(2, 4, 3, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax3.add_feature(cfeature.COASTLINE, edgecolor='k')
ax3.add_feature(cfeature.BORDERS, edgecolor='k')
ax3.add_feature(states_provinces, edgecolor='k')
ax3.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data3 = plt.contourf(lons2, lats2, ncep2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax3, 'NCEP')

# model 4
ax4 = fig.add_subplot(2, 4, 4, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax4.add_feature(cfeature.COASTLINE, edgecolor='k')
ax4.add_feature(cfeature.BORDERS, edgecolor='k')
ax4.add_feature(states_provinces, edgecolor='k')
ax4.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data4 = plt.contourf(lons2, lats2, jma2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax4, 'JMA')

# model 5
ax5 = fig.add_subplot(2, 4, 5, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax5.add_feature(cfeature.COASTLINE, edgecolor='k')
ax5.add_feature(cfeature.BORDERS, edgecolor='k')
ax5.add_feature(states_provinces, edgecolor='k')
ax5.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data5 = plt.contourf(lons2, lats2, eccc2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax5, 'ECCC')

# model 6
ax6 = fig.add_subplot(2, 4, 6, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax6.add_feature(cfeature.COASTLINE, edgecolor='k')
ax6.add_feature(cfeature.BORDERS, edgecolor='k')
ax6.add_feature(states_provinces, edgecolor='k')
ax6.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data6 = plt.contourf(lons2, lats2, mf2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax6, 'Météo-France')

# model 7
ax7 = fig.add_subplot(2, 4, 7, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax7.add_feature(cfeature.COASTLINE, edgecolor='k')
ax7.add_feature(cfeature.BORDERS, edgecolor='k')
ax7.add_feature(states_provinces, edgecolor='k')
ax7.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data7 = plt.contourf(lons2, lats2, dwd2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax7, 'DWD')

# model 8
ax8 = fig.add_subplot(2, 4, 8, projection=ccrs.NearsidePerspective(central_longitude=174, central_latitude=-45, satellite_height=4000000))
ax8.add_feature(cfeature.COASTLINE, edgecolor='k')
ax8.add_feature(cfeature.BORDERS, edgecolor='k')
ax8.add_feature(states_provinces, edgecolor='k')
ax8.add_feature(cfeature.LAKES, edgecolor='k', alpha=0.2)

data8 = plt.contourf(lons2, lats2, cmcc2, levels=levels, cmap=cmap, transform=ccrs.PlateCarree(), extend='both')

_name_above_globe(ax8, 'CMCC')

_finish_height_panel(fig, data6)

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/c3s_height_season2_nz.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'sh_height_{}_{}.png'.format(valid_time[3], valid_time[5]), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)