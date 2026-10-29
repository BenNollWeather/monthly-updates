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
"""Auto-converted from tables.ipynb.

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

# %% Notebook cell 1

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

import pathlib
import os

# %% Notebook cell 3

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 4

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 5

current_year = parse('this year')
current_year = current_year.strftime("%Y")

# %% Notebook cell 6

current_year

# %% Notebook cell 7

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 8

this_month

# %% Notebook cell 9

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 11

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/sst").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/sst/{}").format(dl_month)

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

# %% Notebook cell 18

sst['step'] = pd.to_datetime((pd.to_datetime(sst['valid_time'].to_index()) - pd.Timedelta(days = 13)).strftime("%Y-%m-01"))

# %% Notebook cell 19

sst['valid_time'] = sst['step']

# %% Notebook cell 20

lon = sst['longitude']
lat = sst['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 21

valid_time = sst['valid_time'].dt.strftime('%Y-%m')

# %% Notebook cell 22

valid_time = valid_time.values

# %% Notebook cell 23

sst = sst['ssta']

# %% Notebook cell 26

# for i in range(len(sst)):
#     pelorus = sst.sel(longitude=173.86, latitude=-41.22, method='nearest')

# %% Notebook cell 27

# pelorus = pelorus.to_dataframe()

# %% Notebook cell 28

# pelorus = pelorus.reset_index()

# %% Notebook cell 29

# pelorus = pelorus.drop(columns=['step','number','surface','time','longitude','latitude'])

# %% Notebook cell 30

# pelorus = pelorus.rename(columns={'valid_time': 'Month', 'ssta': 'SST Anomaly (°C)'})

# %% Notebook cell 31

# pelorus['Month'] = pelorus['Month'].dt.to_period('M')

# %% Notebook cell 32

# # Custom formatting function
# def custom_format(value):
#     if isinstance(value, (int, float)):
#         return f"{value:.2f}"
#     return value

# # Assuming pelorus is a DataFrame
# if isinstance(pelorus, pd.DataFrame):
#     pelorus = pelorus.style \
#         .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2) \
#         .hide(axis="index") \
#         .set_caption("Forecast Cook Strait sea-surface temperature anomalies (°C) over the next 6 months") \
#         .format(custom_format) \
#         .set_properties(**{'text-align': 'center', 'font-size': '24px', 'font-weight': 'bold', 'color': 'black'})
# else:
#     print("pelorus is not a DataFrame or Series")

# %% Notebook cell 33

# pelorus

# %% Notebook cell 34

# dfi.export(pelorus,"local-work/weather/cds/sst_imagery/pelorus_sst.png")

# %% Notebook cell 36

# for i in range(len(sst)):
#     nino34 = sst.sel(longitude=slice(190., 240.), latitude=slice(-5., 5.)).mean('latitude').mean('longitude')

# %% Notebook cell 37

# nino34 = nino34.to_dataframe()

# %% Notebook cell 38

# nino34 = nino34.reset_index()

# %% Notebook cell 39

# nino34 = nino34.drop(columns=['step','number','surface','time'])

# %% Notebook cell 40

# nino34 = nino34.rename(columns={'valid_time': 'Month', 'ssta': 'SST Anomaly (°C)'})

# %% Notebook cell 41

# nino34['Month'] = nino34['Month'].dt.to_period('M')

# %% Notebook cell 42

# # Custom formatting function
# def custom_format(value):
#     if isinstance(value, (int, float)):
#         return f"{value:.2f}"
#     return value

# # Assuming nino34 is a DataFrame
# if isinstance(nino34, pd.DataFrame):
#     nino34 = nino34.style \
#         .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2) \
#         .hide(axis="index") \
#         .set_caption("Niño 3.4 index anomalies (°C) over the next 6 months") \
#         .format(custom_format) \
#         .set_properties(**{'text-align': 'center', 'font-size': '24px', 'font-weight': 'bold', 'color': 'black'})
# else:
#     print("nino34 is not a DataFrame or Series")

# %% Notebook cell 43

# nino34

# %% Notebook cell 44

# dfi.export(nino34,"local-work/weather/cds/sst_imagery/nino34_sst.png")

# %% Notebook cell 46

for i in range(len(concats)):
    nino34 = concats.sel(longitude=slice(190., 240.), latitude=slice(-5., 5.)).mean('latitude').mean('longitude')

# %% Notebook cell 47

nino34['step'] = pd.to_datetime((pd.to_datetime(nino34['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

nino34['valid_time'] = nino34['step']

nino34 = nino34.to_dataframe()

nino34 = nino34.reset_index()

nino34 = nino34.drop(columns=['step','number','surface','time'])

nino34 = nino34.rename(columns={'valid_time': 'Month', 'ssta': 'SSTA'})

nino34['Month'] = nino34['Month'].dt.to_period('M')

nino34.sort_values(by=['Month', 'SSTA'], inplace=True)

pivoted = nino34.pivot(index="GCM", columns="Month", values="SSTA")

# %% Notebook cell 48

pivoted.loc['mean'] = pivoted.mean()

# %% Notebook cell 49

pivoted.rename(index = {"Canadian Meteorological Service - Montreal ": "ECCC",
                     "European Centre for Medium-Range Weather Forecasts":"ECMWF",
                     "French Weather Service - Toulouse":"Meteo-France",
                     "Japanese Meteorological Agency - Tokyo ":"JMA",
                     "Offenbach ":"DWD",
                     "Rome ":"CMCC",
                     "U.K. Met Office - Exeter":"UKMET",
                     "US National Weather Service - NCEP ":"NCEP",
                     "mean":"Average", },
                                 inplace = True)

# %% Notebook cell 50

pivoted = pivoted.reset_index()

# %% Notebook cell 51

pivoted.rename(columns={'GCM': ''}, inplace=True)

# %% Notebook cell 52

pivoted2 = pivoted.round(2)

# %% Notebook cell 53

# Custom formatting function
def custom_format(value):
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return value

# Assuming pivoted is a DataFrame
if isinstance(pivoted, pd.DataFrame):
    nino34 = pivoted.style \
        .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2) \
        .hide(axis="index") \
        .set_caption("Niño 3.4 index anomalies (°C) over the next 6 months") \
        .format(custom_format) \
        .set_table_styles([{
            'selector': 'caption',
            'props': [
                ('color', 'k'),
                ('font-size', '18px'),
                ('text-align', 'left')
            ]
        }]) \
        .set_properties(**{'text-align': 'center', 'font-size': '24px', 'font-weight': 'bold', 'color': 'black'})
else:
    print("pivoted is not a DataFrame")

# %% Notebook cell 54

nino34

# %% Notebook cell 55

dfi.export(nino34,_os.path.join(_WORK, 'copernicus_imagery/c3s_nino34-gcm.png'))

# %% Notebook cell 57

# for i in range(len(sst)):
#     nzbox = sst.sel(longitude=slice(165., 179.), latitude=slice(-48., -34.)).mean('latitude').mean('longitude')

# %% Notebook cell 58

# nzbox = nzbox.to_dataframe()

# %% Notebook cell 59

# nzbox = nzbox.reset_index()

# %% Notebook cell 60

# nzbox = nzbox.drop(columns=['step','number','surface','time'])

# %% Notebook cell 61

# nzbox = nzbox.rename(columns={'valid_time': 'Month', 'ssta': 'SST Anomaly (°C)'})

# %% Notebook cell 62

# nzbox['Month'] = nzbox['Month'].dt.to_period('M')

# %% Notebook cell 63

# # Custom formatting function
# def custom_format(value):
#     if isinstance(value, (int, float)):
#         return f"{value:.2f}"
#     return value

# # Assuming nzbox is a DataFrame
# if isinstance(nzbox, pd.DataFrame):
#     nzbox = nzbox.style \
#         .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2) \
#         .hide(axis="index") \
#         .set_caption("New Zealand region SST anomalies (°C) over the next 6 months | [165-179E, 34-48S]") \
#         .format(custom_format) \
#         .set_properties(**{'text-align': 'center', 'font-size': '24px', 'font-weight': 'bold', 'color': 'black'})
# else:
#     print("nzbox is not a DataFrame")

# %% Notebook cell 64

# nzbox

# %% Notebook cell 65

# dfi.export(nzbox,"local-work/weather/cds/sst_imagery/nzbox_sst.png")

# %% Notebook cell 67

for i in range(len(concats)):
    nzbox = concats.sel(longitude=slice(165., 179.), latitude=slice(-48., -34.)).mean('latitude').mean('longitude')

# %% Notebook cell 68

nzbox['step'] = pd.to_datetime((pd.to_datetime(nzbox['valid_time'].to_index()) - pd.Timedelta(days =20)).strftime("%Y-%m-01"))

nzbox['valid_time'] = nzbox['step']

nzbox = nzbox.to_dataframe()

nzbox = nzbox.reset_index()

nzbox = nzbox.drop(columns=['step','number','surface','time'])

nzbox = nzbox.rename(columns={'valid_time': 'Month', 'ssta': 'SSTA'})

nzbox['Month'] = nzbox['Month'].dt.to_period('M')

nzbox.sort_values(by=['Month', 'SSTA'], inplace=True)

pivoted = nzbox.pivot(index="GCM", columns="Month", values="SSTA")

# %% Notebook cell 69

pivoted.loc['mean'] = pivoted.mean()

# %% Notebook cell 70

pivoted.rename(index = {"Canadian Meteorological Service - Montreal ": "ECCC",
                     "European Centre for Medium-Range Weather Forecasts":"ECMWF",
                     "French Weather Service - Toulouse":"Meteo-France",
                     "Japanese Meteorological Agency - Tokyo ":"JMA",
                     "Offenbach ":"DWD",
                     "Rome ":"CMCC",
                     "U.K. Met Office - Exeter":"UKMET",
                     "US National Weather Service - NCEP ":"NCEP",
                     "mean":"Average", },
                                 inplace = True)

# %% Notebook cell 71

pivoted = pivoted.reset_index()

# %% Notebook cell 72

pivoted.rename(columns={'GCM': ''}, inplace=True)

# %% Notebook cell 73

pivoted2 = pivoted.round(2)

# %% Notebook cell 74

# Custom formatting function
def custom_format(value):
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return value

# Assuming pivoted is a DataFrame
if isinstance(pivoted, pd.DataFrame):
    nzbox = pivoted.style \
        .background_gradient(cmap='cmo.balance', vmin=-2, vmax=2) \
        .hide(axis="index") \
        .set_caption("New Zealand region SST anomalies (°C) over the next 6 months [165-179E, 34-48S]") \
        .format(custom_format) \
        .set_table_styles([{
            'selector': 'caption',
            'props': [
                ('color', 'k'),
                ('font-size', '18px'),
                ('text-align', 'left')
            ]
        }]) \
        .set_properties(**{'text-align': 'center', 'font-size': '24px', 'font-weight': 'bold', 'color': 'black'})
else:
    print("pivoted is not a DataFrame")

# %% Notebook cell 75

nzbox

# %% Notebook cell 76

dfi.export(nzbox,_os.path.join(_WORK, 'copernicus_imagery/c3s_nz-gcm.png'))

# %% Notebook cell 78

# # Change to the target directory and perform Git operations
# !cd local-work/weather/cds/ && \
# git add -A && \
# git commit -m "update charts" && \
# git push