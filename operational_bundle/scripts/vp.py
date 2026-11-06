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
from lib.regions import draw_region_labels
"""Single-pass ECMWF velocity-potential workflow.

This consolidates the prior vp3.py -> vp.py -> vp2.py chain into one script.
"""
from pathlib import Path

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


# ---- Former vp3.py: CDS downloads / prep ----
#!/usr/bin/env python3
"""Auto-converted from vp3.ipynb.

Generated for the operational monthly runner. Styling and output filenames are preserved as much as possible.
"""
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


# Configurable VP climatology directory.
VP_CLIMO_DIR = Path(os.environ.get("VP_CLIMO_DIR", str(Path(_WORK) / "climo" / "vp")))

def vp_climo_path(month_name):
    path = VP_CLIMO_DIR / f"vp_clim_{month_name}.nc"
    if not path.exists():
        raise FileNotFoundError(f"Missing VP climatology file: {path}")
    return str(path)


def _on_forecast_grid(clim, target):
    """Put the climatology on the forecast grid before the anomaly is taken."""
    clim = clim.squeeze(drop=True).reset_coords(drop=True)

    def _coord(obj, options):
        for name in options:
            if name in obj.dims or name in obj.coords:
                return name
        raise KeyError(options)

    src_lat = _coord(clim, ("latitude", "lat"))
    src_lon = _coord(clim, ("longitude", "lon"))
    dst_lat = _coord(target, ("latitude", "lat"))
    dst_lon = _coord(target, ("longitude", "lon"))
    if float(clim[src_lon].max()) <= 180.0 and float(target[dst_lon].max()) > 180.0:
        shifted = (clim[src_lon] + 360.0) % 360.0
        clim = clim.assign_coords({src_lon: shifted}).sortby(src_lon)
    if src_lat != dst_lat or src_lon != dst_lon:
        clim = clim.rename({src_lat: dst_lat, src_lon: dst_lon})
        src_lat, src_lon = dst_lat, dst_lon
    return clim.interp({src_lat: target[dst_lat], src_lon: target[dst_lon]}, method="linear")

from model_versions import ECMWF_SYSTEM, C3S_MULTI_MODEL_SYSTEMS, C3S_STRATOSPHERE_SYSTEMS, C3S_SNOW_SYSTEMS, C3S_HEIGHT_SYSTEMS, C3S_UKMO_SYSTEM
# %% Notebook cell 0

import pygrib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
import numpy as np

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from shapely.geometry import box
from cartopy.io import shapereader

# %% Notebook cell 2

import xarray as xr

# %% Notebook cell 3

import os

# %% Notebook cell 4

import cmocean

# %% Notebook cell 5

from glob import glob

# %% Notebook cell 6

from dateparser import parse

# %% Notebook cell 7

import pathlib

# %% Notebook cell 9

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

# %% Notebook cell 10

shape1 = get_shp(os.path.join(shapefiles, 'nino34'))
shape2 = get_shp(os.path.join(shapefiles, 'nino3'))
shape3 = get_shp(os.path.join(shapefiles, 'nino4'))
shape4 = get_shp(os.path.join(shapefiles, 'nino12'))
shape5 = get_shp(os.path.join(shapefiles, 'iode'))
shape6 = get_shp(os.path.join(shapefiles, 'iodw'))
shape7 = get_shp(os.path.join(shapefiles, 'atlantic'))

# %% Notebook cell 12

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 13

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 14

fifth_month

# %% Notebook cell 15

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 16

current_year

# %% Notebook cell 17

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 18

this_month

# %% Notebook cell 20

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 21

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 22

month6

# %% Notebook cell 23

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 25

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/vp").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/vp/{}").format(dl_month)

# %% Notebook cell 26

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 27

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 28

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 30

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-monthly-pressure-levels',
    {
        'originating_centre':'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable':'u_component_of_wind',
        'pressure_level':'200',
        'product_type':'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month':[
            '1','2','3',
            '4','5','6'
        ],
        'format':'grib'
    },
    dl_path/'ec_u.grib')

# %% Notebook cell 31

import cdsapi

c = cdsapi.Client()

c.retrieve(
    'seasonal-monthly-pressure-levels',
    {
        'originating_centre':'ecmwf',
        'system': ECMWF_SYSTEM,
        'variable':'v_component_of_wind',
        'pressure_level':'200',
        'product_type':'ensemble_mean',
        'year':'{}'.format(current_year),
        'month':'{}'.format(this_month),
        'leadtime_month':[
            '1','2','3',
            '4','5','6'
        ],
        'format':'grib'
    },
    dl_path/'ec_v.grib')

# ---- Former vp.py: compute velocity potential anomalies and NetCDF ----
#!/usr/bin/env python3
"""Auto-converted from vp.ipynb.

Generated for the operational monthly runner. Styling and output filenames are preserved as much as possible.
"""
# from __future__ import annotations  # removed from concatenated script
import os
os.environ.setdefault("MPLBACKEND", "Agg")
try:
    import matplotlib
    matplotlib.use("Agg")
except Exception:
    pass

# %% Notebook cell 0

import pygrib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
import numpy as np

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.io import shapereader

# %% Notebook cell 2

import xarray as xr

# %% Notebook cell 3

import os

# %% Notebook cell 4

import cmocean

# %% Notebook cell 5

from glob import glob

# %% Notebook cell 6

from dateparser import parse

# %% Notebook cell 7

import pathlib

# %% Notebook cell 9

shapefiles = _SHAPES

# %% Notebook cell 10

shape1 = get_shp(os.path.join(shapefiles, 'nino34'))
shape2 = get_shp(os.path.join(shapefiles, 'nino3'))
shape3 = get_shp(os.path.join(shapefiles, 'nino4'))
shape4 = get_shp(os.path.join(shapefiles, 'nino12'))
shape5 = get_shp(os.path.join(shapefiles, 'iode'))
shape6 = get_shp(os.path.join(shapefiles, 'iodw'))
shape7 = get_shp(os.path.join(shapefiles, 'atlantic'))

# %% Notebook cell 12

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 13

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 14

fifth_month

# %% Notebook cell 15

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 16

current_year

# %% Notebook cell 17

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 18

this_month

# %% Notebook cell 20

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 21

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 22

month6

# %% Notebook cell 23

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 25

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/vp").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/vp/{}").format(dl_month)

# %% Notebook cell 26

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 27

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 28

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 30

# import cdsapi

# c = cdsapi.Client()

# c.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre':'ecmwf',
#         'system': ECMWF_SYSTEM,
#         'variable':'u_component_of_wind',
#         'pressure_level':'200',
#         'product_type':'ensemble_mean',
#         'year':'{}'.format(current_year),
#         'month':'{}'.format(this_month),
#         'leadtime_month':[
#             '1','2','3',
#             '4','5','6'
#         ],
#         'format':'grib'
#     },
#     dl_path/'ec_u.grib')

# %% Notebook cell 31

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['u_component_of_wind'],
#         'pressure_level': ['200'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ec_u.grib')

# %% Notebook cell 32

# import cdsapi

# c = cdsapi.Client()

# c.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre':'ecmwf',
#         'system': ECMWF_SYSTEM,
#         'variable':'v_component_of_wind',
#         'pressure_level':'200',
#         'product_type':'ensemble_mean',
#         'year':'{}'.format(current_year),
#         'month':'{}'.format(this_month),
#         'leadtime_month':[
#             '1','2','3',
#             '4','5','6'
#         ],
#         'format':'grib'
#     },
#     dl_path/'ec_v.grib')

# %% Notebook cell 33

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['v_component_of_wind'],
#         'pressure_level': ['200'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ec_v.grib')

# %% Notebook cell 34

u = (dl_path/'ec_u.grib')
v = (dl_path/'ec_v.grib')

# %% Notebook cell 35

u = xr.open_dataset(u, engine='cfgrib')
v = xr.open_dataset(v, engine='cfgrib')

# %% Notebook cell 36

u1 = u.isel(step=0)['u']
v1 = v.isel(step=0)['v']

u2 = u.isel(step=1)['u']
v2 = v.isel(step=1)['v']

u3 = u.isel(step=2)['u']
v3 = v.isel(step=2)['v']

u4 = u.isel(step=3)['u']
v4 = v.isel(step=3)['v']

u5 = u.isel(step=4)['u']
v5 = v.isel(step=4)['v']

u6 = u.isel(step=5)['u']
v6 = v.isel(step=5)['v']

# %% Notebook cell 38

from windspharm.xarray import VectorWind

# %% Notebook cell 39

w1 = VectorWind(u1, v1)
w2 = VectorWind(u2, v2)
w3 = VectorWind(u3, v3)
w4 = VectorWind(u4, v4)
w5 = VectorWind(u5, v5)
w6 = VectorWind(u6, v6)

# %% Notebook cell 40

vp_forecast1 = w1.velocitypotential()
vp_forecast2 = w2.velocitypotential()
vp_forecast3 = w3.velocitypotential()
vp_forecast4 = w4.velocitypotential()
vp_forecast5 = w5.velocitypotential()
vp_forecast6 = w6.velocitypotential()

# %% Notebook cell 42

#u_clim = 'u_clim_jul.grib'

# %% Notebook cell 43

#v_clim = 'v_clim_jul.grib'

# %% Notebook cell 44

#u_clim = 'WORK_ROOTe/Downloads/u_clim_may.grib'

# %% Notebook cell 45

#v_clim = 'WORK_ROOTe/Downloads/v_clim_may.grib'

# %% Notebook cell 46

#u_clim = xr.open_mfdataset(u_clim, engine='cfgrib')

# %% Notebook cell 47

#v_clim = xr.open_mfdataset(v_clim, engine='cfgrib')

# %% Notebook cell 48

#u_clim = u_clim.mean('time')

# %% Notebook cell 49

#v_clim = v_clim.mean('time')

# %% Notebook cell 50

#u_clim = u_clim['u']
#v_clim = v_clim['v']

# %% Notebook cell 51

#w_clim = VectorWind(u_clim, v_clim)

# %% Notebook cell 52

#vp_clim = w_clim.velocitypotential()

# %% Notebook cell 53

#vp_clim.plot()

# %% Notebook cell 54

#vp_clim.to_netcdf('vp_clim_jul.nc')

# %% Notebook cell 56

vp_clim1 = vp_climo_path(current_month)
vp_clim2 = vp_climo_path(next_month)
vp_clim3 = vp_climo_path(second_month)
vp_clim4 = vp_climo_path(third_month)
vp_clim5 = vp_climo_path(fourth_month)
vp_clim6 = vp_climo_path(fifth_month)

# %% Notebook cell 57

vp_clim1

# %% Notebook cell 58

vp_clim1 = _on_forecast_grid(xr.open_dataset(vp_clim1)['velocity_potential'], vp_forecast1)
vp_clim2 = _on_forecast_grid(xr.open_dataset(vp_clim2)['velocity_potential'], vp_forecast2)
vp_clim3 = _on_forecast_grid(xr.open_dataset(vp_clim3)['velocity_potential'], vp_forecast3)
vp_clim4 = _on_forecast_grid(xr.open_dataset(vp_clim4)['velocity_potential'], vp_forecast4)
vp_clim5 = _on_forecast_grid(xr.open_dataset(vp_clim5)['velocity_potential'], vp_forecast5)
vp_clim6 = _on_forecast_grid(xr.open_dataset(vp_clim6)['velocity_potential'], vp_forecast6)

# %% Notebook cell 60

vp1 = vp_forecast1-vp_clim1
vp2 = vp_forecast2-vp_clim2
vp3 = vp_forecast3-vp_clim3
vp4 = vp_forecast4-vp_clim4
vp5 = vp_forecast5-vp_clim5
vp6 = vp_forecast6-vp_clim6

# %% Notebook cell 61

import pandas as pd
from datetime import datetime
import subprocess

# Define save path
save_path = _os.path.join(_WORK, "climate_stuff/vp.nc")

# Generate valid_time for next 6 months
current_month = datetime.today().replace(day=1)  # First day of the current month
valid_times = [pd.Timestamp(current_month) + pd.DateOffset(months=i) for i in range(6)]

# List of computed anomalies (vp1 to vp6 assumed to be in memory)
vp_list = [vp1, vp2, vp3, vp4, vp5, vp6]

# Assign valid_time and concatenate along new dimension
for i, ds in enumerate(vp_list):
    ds = ds.expand_dims({'valid_time': [valid_times[i]]})  # Add valid_time as a dimension
    vp_list[i] = ds

vp_combined = xr.concat(vp_list, dim='valid_time')

# Save to NetCDF
vp_combined.to_netcdf(save_path)
print(f"✅ Saved NetCDF file to {save_path}")

# Internal VP AWS sync removed; final runner upload handles all imagery.

# %% Notebook cell 62

# season1 = (vp1+vp2+vp3)/3

# %% Notebook cell 63

# season2 = (vp4+vp5+vp6)/3

# %% Notebook cell 64

# hurr = (vp3+vp4+vp5)/3

# %% Notebook cell 65

# season2.plot()

# %% Notebook cell 66

# lon = vp1['longitude']
# lat = vp1['latitude']
# lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 68

# vp1.load(), vp2.load(), vp3.load(), vp4.load(), vp5.load(), vp6.load(), season1.load(), season2.load(), hurr.load()

# %% Notebook cell 69

# vp1 = vp1.data
# vp2 = vp2.data
# vp3 = vp3.data
# vp4 = vp4.data
# vp5 = vp5.data
# vp6 = vp6.data
# season1 = season1.data
# season2 = season2.data
# hurr = hurr.data

# %% Notebook cell 70

# vp1, cyclic_lons = add_cyclic_point(vp1, coord=lon)
# vp2, cyclic_lons = add_cyclic_point(vp2, coord=lon)
# vp3, cyclic_lons = add_cyclic_point(vp3, coord=lon)
# vp4, cyclic_lons = add_cyclic_point(vp4, coord=lon)
# vp5, cyclic_lons = add_cyclic_point(vp5, coord=lon)
# vp6, cyclic_lons = add_cyclic_point(vp6, coord=lon)
# season1, cyclic_lons = add_cyclic_point(season1, coord=lon)
# season2, cyclic_lons = add_cyclic_point(season2, coord=lon)
# hurr, cyclic_lons = add_cyclic_point(hurr, coord=lon)

# %% Notebook cell 71

# lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 73

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp1, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp1, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month1), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 74

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp2, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp2, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month2), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(next_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 75

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp3, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp3, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month3), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp3.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 76

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp4, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp4, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month4), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp4.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 77

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp5, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp5, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month5), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp5.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 78

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, vp6, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, vp6, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

# #ax.coastlines()

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}'.format(month6), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp6.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}.png'.format(fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 79

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, season1, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, season1, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}-{}'.format(month1, month3), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# #plt.savefig(_os.path.join(_WORK, 'downloads/vp_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}-{}.png'.format(current_month, second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 80

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

# data = plt.contourf(lons, lats, season2, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
# data2 = plt.contour(lons, lats, season2, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# # Add shapefiles
# shape1 = shape1
# shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape1_feature, linewidth=3, zorder = 22)

# 
# shape2 = shape2
# shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape2_feature, linewidth=3, zorder = 22)

# ax.text(.59, .485, 'Niño 3.4', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=17, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))
# ax.text(.68, .485, 'Niño 3', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='square', pad=0.1))

# shape3 = shape3
# shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape3_feature, linewidth=3, zorder = 22)

# 
# shape4 = shape4
# shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape4_feature, linewidth=3, zorder = 22)

# 
# shape5 = shape5
# shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape5_feature, linewidth=3, zorder = 22)

# 
# shape6 = shape6
# shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape6_feature, linewidth=3, zorder = 22)

# 
# shape7 = shape7
# shape7_feature = ShapelyFeature(shp_geometries(shape7), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
# ax.add_feature(shape7_feature, linewidth=3, zorder = 22)

# draw_region_labels(ax)

# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=20, color='white', weight="bold")
# plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
# cbar.ax.tick_params(labelsize=18, color="white", labelcolor="white")
# cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
# cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
# cbar.ax.set_facecolor([1,1,1,0])

# # Set the tick labels to bold
# for label in cbar.ax.get_yticklabels():
#     label.set_weight('bold')

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

# ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

# fig.patch.set_facecolor('k')

# #plt.savefig(_os.path.join(_WORK, 'downloads/vp_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
# plt.savefig(fig_path/'vp_{}-{}.png'.format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# %% Notebook cell 81

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection = ccrs.Robinson(central_longitude=0, globe=None, false_easting=None, false_northing=None))
# #ax = plt.axes(projection=ccrs.PlateCarree())

# #levels = np.linspace(-5000000, 5000000, 60)

# data = plt.contourf(lons, lats, hurr, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())

# data2 = plt.contour(lons, lats, hurr, 2, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

# #ax.coastlines()

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


# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=24, color='white')
# plt.title('{}-{}'.format(month3, month5), loc='right', fontsize=24, color='white')
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.7, aspect=40)
# cbar.ax.tick_params(labelsize=20, color="white", labelcolor="white")
# #cbar.set_label(r'Velocity Potential Anomaly ', fontsize=16)
# cbar.ax.set_yticklabels(['-4', '-2', '0', '2', '4'],fontsize=24)
# cbar.ax.set_facecolor([1,1,1,0])

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

# patches = [Patch(color=color, label=label)
#            for color, label in legend_labels.items()]

# ax.legend(handles=patches,
#           bbox_to_anchor=(0.993, 0.09),
#           facecolor="white",
#           prop=dict(size=16))

# ax.text(0.01, 0.02, 'BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, backgroundcolor='.75', fontsize=18)

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'downloads/vp_hurr.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()

# ---- Former vp2.py: imagery generation ----
#!/usr/bin/env python3
"""Auto-converted from vp2.ipynb.

Generated for the operational monthly runner. Styling and output filenames are preserved as much as possible.
"""
# from __future__ import annotations  # removed from concatenated script
import os
os.environ.setdefault("MPLBACKEND", "Agg")
try:
    import matplotlib
    matplotlib.use("Agg")
except Exception:
    pass

# %% Notebook cell 0

import pygrib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.colors as colors
from matplotlib.patches import Patch
import numpy as np

# %% Notebook cell 1

from cartopy import config
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point
from cartopy.io.shapereader import Reader
from cartopy.feature import ShapelyFeature
from cartopy.io import shapereader

# %% Notebook cell 2

import xarray as xr

# %% Notebook cell 3

import os

# %% Notebook cell 4

import cmocean

# %% Notebook cell 5

from glob import glob

# %% Notebook cell 6

from dateparser import parse

# %% Notebook cell 7

import pathlib

# %% Notebook cell 9

shapefiles = _SHAPES

# %% Notebook cell 10

shape1 = get_shp(os.path.join(shapefiles, 'nino34'))
shape2 = get_shp(os.path.join(shapefiles, 'nino3'))
shape3 = get_shp(os.path.join(shapefiles, 'nino4'))
shape4 = get_shp(os.path.join(shapefiles, 'nino12'))
shape5 = get_shp(os.path.join(shapefiles, 'iode'))
shape6 = get_shp(os.path.join(shapefiles, 'iodw'))
shape7 = get_shp(os.path.join(shapefiles, 'atlantic'))

# %% Notebook cell 12

current_month = parse('0 months ago')
next_month = parse('next month')
second_month = parse('in two months')
third_month = parse('in three months')
fourth_month = parse('in four months')
fifth_month = parse('in five months')

# %% Notebook cell 13

current_month = current_month.strftime("%b")
next_month = next_month.strftime("%b")
second_month = second_month.strftime("%b")
third_month = third_month.strftime("%b")
fourth_month = fourth_month.strftime("%b")
fifth_month = fifth_month.strftime("%b")

# %% Notebook cell 14

fifth_month

# %% Notebook cell 15

current_year = parse('this year')
current_year = current_year.strftime("%Y")

next_year = parse('next year')
next_year = next_year.strftime("%Y")

# %% Notebook cell 16

current_year

# %% Notebook cell 17

this_month = parse('0 months ago')
this_month = this_month.strftime("%m")

# %% Notebook cell 18

this_month

# %% Notebook cell 20

month1 = parse('this month')
month2 = parse('next month')
month3 = parse('in two months')
month4 = parse('in three months')
month5 = parse('in four months')
month6 = parse('in five months')

# %% Notebook cell 21

month1 = month1.strftime("%b %Y")
month2 = month2.strftime("%b %Y")
month3 = month3.strftime("%b %Y")
month4 = month4.strftime("%b %Y")
month5 = month5.strftime("%b %Y")
month6 = month6.strftime("%b %Y")

# %% Notebook cell 22

month6

# %% Notebook cell 23

dl_month = parse('0 months ago')
dl_month = dl_month.strftime("%Y-%m")

# %% Notebook cell 25

fig_path = _os.path.join(_WORK, "imagery/c3s/{}/vp").format(dl_month)
dl_path = _os.path.join(_WORK, "data/c3s/vp/{}").format(dl_month)

# %% Notebook cell 26

fig_path = pathlib.Path(fig_path)
dl_path = pathlib.Path(dl_path)

# %% Notebook cell 27

if fig_path.exists() == False:
    fig_path.mkdir(parents = True)

# %% Notebook cell 28

if dl_path.exists() == False:
    dl_path.mkdir(parents = True)

# %% Notebook cell 29

vp = xr.open_dataset(_os.path.join(_WORK, "climate_stuff/vp.nc"))

# %% Notebook cell 30

vp

# %% Notebook cell 32

# import cdsapi

# c = cdsapi.Client()

# c.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre':'ecmwf',
#         'system': ECMWF_SYSTEM,
#         'variable':'u_component_of_wind',
#         'pressure_level':'200',
#         'product_type':'ensemble_mean',
#         'year':'{}'.format(current_year),
#         'month':'{}'.format(this_month),
#         'leadtime_month':[
#             '1','2','3',
#             '4','5','6'
#         ],
#         'format':'grib'
#     },
#     dl_path/'ec_u.grib')

# %% Notebook cell 33

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['u_component_of_wind'],
#         'pressure_level': ['200'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ec_u.grib')

# %% Notebook cell 34

# import cdsapi

# c = cdsapi.Client()

# c.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre':'ecmwf',
#         'system': ECMWF_SYSTEM,
#         'variable':'v_component_of_wind',
#         'pressure_level':'200',
#         'product_type':'ensemble_mean',
#         'year':'{}'.format(current_year),
#         'month':'{}'.format(this_month),
#         'leadtime_month':[
#             '1','2','3',
#             '4','5','6'
#         ],
#         'format':'grib'
#     },
#     dl_path/'ec_v.grib')

# %% Notebook cell 35

# import cdsapi

# client = cdsapi.Client()
# client.retrieve(
#     'seasonal-monthly-pressure-levels',
#     {
#         'originating_centre': ['ecmwf'],
#         'variable': ['v_component_of_wind'],
#         'pressure_level': ['200'],
#         'product_type': ['ensemble_mean'],
#         'year': [current_year],
#         'month': [this_month],
#         'leadtime_month': ['1', '2', '3', '4', '5', '6'],
#         'data_format': 'grib'
#     }
# ).download(dl_path / 'ec_v.grib')

# %% Notebook cell 36

# u = (dl_path/'ec_u.grib')
# v = (dl_path/'ec_v.grib')

# %% Notebook cell 37

# u = xr.open_dataset(u, engine='cfgrib')
# v = xr.open_dataset(v, engine='cfgrib')

# %% Notebook cell 38

# u1 = u.isel(step=0)['u']
# v1 = v.isel(step=0)['v']

# u2 = u.isel(step=1)['u']
# v2 = v.isel(step=1)['v']

# u3 = u.isel(step=2)['u']
# v3 = v.isel(step=2)['v']

# u4 = u.isel(step=3)['u']
# v4 = v.isel(step=3)['v']

# u5 = u.isel(step=4)['u']
# v5 = v.isel(step=4)['v']

# u6 = u.isel(step=5)['u']
# v6 = v.isel(step=5)['v']

# %% Notebook cell 40

# from windspharm.xarray import VectorWind

# %% Notebook cell 41

# w1 = VectorWind(u1, v1)
# w2 = VectorWind(u2, v2)
# w3 = VectorWind(u3, v3)
# w4 = VectorWind(u4, v4)
# w5 = VectorWind(u5, v5)
# w6 = VectorWind(u6, v6)

# %% Notebook cell 42

# vp_forecast1 = w1.velocitypotential()
# vp_forecast2 = w2.velocitypotential()
# vp_forecast3 = w3.velocitypotential()
# vp_forecast4 = w4.velocitypotential()
# vp_forecast5 = w5.velocitypotential()
# vp_forecast6 = w6.velocitypotential()

# %% Notebook cell 44

#u_clim = 'u_clim_jul.grib'

# %% Notebook cell 45

#v_clim = 'v_clim_jul.grib'

# %% Notebook cell 46

#u_clim = 'WORK_ROOTe/Downloads/u_clim_may.grib'

# %% Notebook cell 47

#v_clim = 'WORK_ROOTe/Downloads/v_clim_may.grib'

# %% Notebook cell 48

#u_clim = xr.open_mfdataset(u_clim, engine='cfgrib')

# %% Notebook cell 49

#v_clim = xr.open_mfdataset(v_clim, engine='cfgrib')

# %% Notebook cell 50

#u_clim = u_clim.mean('time')

# %% Notebook cell 51

#v_clim = v_clim.mean('time')

# %% Notebook cell 52

#u_clim = u_clim['u']
#v_clim = v_clim['v']

# %% Notebook cell 53

#w_clim = VectorWind(u_clim, v_clim)

# %% Notebook cell 54

#vp_clim = w_clim.velocitypotential()

# %% Notebook cell 55

#vp_clim.plot()

# %% Notebook cell 56

#vp_clim.to_netcdf('vp_clim_jul.nc')

# %% Notebook cell 58

# vp_clim1 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(current_month)
# vp_clim2 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(next_month)
# vp_clim3 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(second_month)
# vp_clim4 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(third_month)
# vp_clim5 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(fourth_month)
# vp_clim6 = 'WORK_ROOT/weather/climo/vp/vp_clim_{}.nc'.format(fifth_month)

# %% Notebook cell 59

# vp_clim1

# %% Notebook cell 60

# vp_clim1 = xr.open_dataset(vp_clim1)['velocity_potential']
# vp_clim2 = xr.open_dataset(vp_clim2)['velocity_potential']
# vp_clim3 = xr.open_dataset(vp_clim3)['velocity_potential']
# vp_clim4 = xr.open_dataset(vp_clim4)['velocity_potential']
# vp_clim5 = xr.open_dataset(vp_clim5)['velocity_potential']
# vp_clim6 = xr.open_dataset(vp_clim6)['velocity_potential']

# %% Notebook cell 62

# vp1 = vp_forecast1-vp_clim1
# vp2 = vp_forecast2-vp_clim2
# vp3 = vp_forecast3-vp_clim3
# vp4 = vp_forecast4-vp_clim4
# vp5 = vp_forecast5-vp_clim5
# vp6 = vp_forecast6-vp_clim6

# %% Notebook cell 63

vp1 = vp.isel(valid_time=0)['velocity_potential']
vp2 = vp.isel(valid_time=1)['velocity_potential']
vp3 = vp.isel(valid_time=2)['velocity_potential']
vp4 = vp.isel(valid_time=3)['velocity_potential']
vp5 = vp.isel(valid_time=4)['velocity_potential']
vp6 = vp.isel(valid_time=5)['velocity_potential']

# %% Notebook cell 64

# import pandas as pd
# from datetime import datetime
# import subprocess

# # Define save path
# save_path = _os.path.join(_WORK, "climate_stuff/vp.nc")

# # Generate valid_time for next 6 months
# current_month = datetime.today().replace(day=1)  # First day of the current month
# valid_times = [pd.Timestamp(current_month) + pd.DateOffset(months=i) for i in range(6)]

# # List of computed anomalies (vp1 to vp6 assumed to be in memory)
# vp_list = [vp1, vp2, vp3, vp4, vp5, vp6]

# # Assign valid_time and concatenate along new dimension
# for i, ds in enumerate(vp_list):
#     ds = ds.expand_dims({'valid_time': [valid_times[i]]})  # Add valid_time as a dimension
#     vp_list[i] = ds

# vp_combined = xr.concat(vp_list, dim='valid_time')

# # Save to NetCDF
# vp_combined.to_netcdf(save_path)
# print(f"✅ Saved NetCDF file to {save_path}")

# # Sync the directory to AWS S3
# sync_command = (
#     "aws s3 sync DISPOSABLE/operational_work/climate_stuff "
#     "s3://bennollweather/climate_imagery/ "
#     "--exclude '.git/*' --exclude '.gitignore' --exclude '.DS_Store' --exclude '.gitattributes'"
# )

# try:
#     subprocess.run(sync_command, shell=True, check=True)
#     print("✅ Successfully synced to S3: s3://bennollweather/climate_imagery/")
# except subprocess.CalledProcessError as e:
#     print(f"❌ Failed to sync to AWS S3: {e}")

# %% Notebook cell 65

season1 = (vp1+vp2+vp3)/3

# %% Notebook cell 66

season2 = (vp4+vp5+vp6)/3

# %% Notebook cell 67

hurr = (vp3+vp4+vp5)/3

# %% Notebook cell 68

season2.plot()

# %% Notebook cell 69

lon = vp1['longitude']
lat = vp1['latitude']
lons, lats = np.meshgrid(lon, lat)

# %% Notebook cell 71

vp1.load(), vp2.load(), vp3.load(), vp4.load(), vp5.load(), vp6.load(), season1.load(), season2.load(), hurr.load()

# %% Notebook cell 72

vp1 = vp1.data
vp2 = vp2.data
vp3 = vp3.data
vp4 = vp4.data
vp5 = vp5.data
vp6 = vp6.data
season1 = season1.data
season2 = season2.data
hurr = hurr.data

# %% Notebook cell 73

vp1, cyclic_lons = add_cyclic_point(vp1, coord=lon)
vp2, cyclic_lons = add_cyclic_point(vp2, coord=lon)
vp3, cyclic_lons = add_cyclic_point(vp3, coord=lon)
vp4, cyclic_lons = add_cyclic_point(vp4, coord=lon)
vp5, cyclic_lons = add_cyclic_point(vp5, coord=lon)
vp6, cyclic_lons = add_cyclic_point(vp6, coord=lon)
season1, cyclic_lons = add_cyclic_point(season1, coord=lon)
season2, cyclic_lons = add_cyclic_point(season2, coord=lon)
hurr, cyclic_lons = add_cyclic_point(hurr, coord=lon)

# %% Notebook cell 74

lons, lats = np.meshgrid(cyclic_lons, lat)

# %% Notebook cell 76

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp1, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp1, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month1), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(current_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 77

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp2, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp2, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month2), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(next_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 78

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp3, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp3, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month3), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp3.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 79

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp4, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp4, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month4), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp4.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(third_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 80

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp5, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp5, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month5), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp5.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(fourth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 81

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, vp6, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, vp6, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

#ax.coastlines()

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}'.format(month6), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

try:

    fig.subplots_adjust(bottom=0.12)

except Exception:

    pass

plt.savefig(_os.path.join(_WORK, 'copernicus_imagery/vp6.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}.png'.format(fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 82

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, season1, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, season1, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}-{}'.format(month1, month3), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'downloads/vp_season1.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}-{}.png'.format(current_month, second_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 83

fig = plt.figure(figsize=(25, 15))

ax = plt.axes(projection=ccrs.PlateCarree(central_longitude=180))

data = plt.contourf(lons, lats, season2, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())
data2 = plt.contour(lons, lats, season2, 10, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

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


# Add shapefiles
shape1 = shape1
shape1_feature = ShapelyFeature(shp_geometries(shape1), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape1_feature, linewidth=3, zorder = 22)


shape2 = shape2
shape2_feature = ShapelyFeature(shp_geometries(shape2), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape2_feature, linewidth=3, zorder = 22)


shape3 = shape3
shape3_feature = ShapelyFeature(shp_geometries(shape3), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape3_feature, linewidth=3, zorder = 22)


shape4 = shape4
shape4_feature = ShapelyFeature(shp_geometries(shape4), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape4_feature, linewidth=3, zorder = 22)


shape5 = shape5
shape5_feature = ShapelyFeature(shp_geometries(shape5), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape5_feature, linewidth=3, zorder = 22)


shape6 = shape6
shape6_feature = ShapelyFeature(shp_geometries(shape6), ccrs.PlateCarree(), facecolor='none', edgecolor='k')
ax.add_feature(shape6_feature, linewidth=3, zorder = 22)


mdr_feature = ShapelyFeature(
    [box(280.0, 10.0, 340.0, 20.0)],
    ccrs.PlateCarree(),
    facecolor='none',
    edgecolor='k',
)
ax.add_feature(mdr_feature, linewidth=3, zorder=22)

draw_region_labels(ax)

plt.title('ECMWF 200 hPa velocity potential anomaly', loc='left', fontsize=20, color='white', weight="bold")
plt.title('{}-{}'.format(month4, month6), loc='right', fontsize=20, color='white', weight="bold")
cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.5, aspect=20)
cbar.ax.tick_params(labelsize=18, color="white", labelcolor="white")
cbar.ax.set_yticklabels(['−4', '−2', '0', '+2', '+4'], fontsize=18)
cbar.ax.set_ylabel(r'$\times\,10^{6}$ m$^{2}$ s$^{-1}$', color='white', fontsize=16, fontweight='bold')
cbar.ax.set_facecolor([1,1,1,0])

# Set the tick labels to bold
for label in cbar.ax.get_yticklabels():
    label.set_weight('bold')

# Add a legend for labels
legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

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

ax.text(0.01, 0.02, '@BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, color='white', weight="bold", fontsize=18, bbox=dict(facecolor='k', alpha=0.5, edgecolor='black', boxstyle='round'))

fig.patch.set_facecolor('k')

#plt.savefig(_os.path.join(_WORK, 'downloads/vp_season2.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)
try:
    fig.subplots_adjust(bottom=0.12)
except Exception:
    pass
plt.savefig(fig_path/'vp_{}-{}.png'.format(third_month, fifth_month), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

plt.close("all")

# %% Notebook cell 84

# fig = plt.figure(figsize=(25, 15))

# ax = plt.axes(projection = ccrs.Robinson(central_longitude=0, globe=None, false_easting=None, false_northing=None))
# #ax = plt.axes(projection=ccrs.PlateCarree())

# #levels = np.linspace(-5000000, 5000000, 60)

# data = plt.contourf(lons, lats, hurr, np.arange(-4500000, 5000000, 100000), extend = "both", cmap=cmocean.cm.tarn_r, transform=ccrs.PlateCarree())

# data2 = plt.contour(lons, lats, hurr, 2, vmin=-5000000, vmax=5000000, colors='k', linewidths=1, transform=ccrs.PlateCarree())

# #ax.coastlines()

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


# plt.title('ECMWF 200 hPa Velocity Potential Anomaly ($m^2$/$s^{-1}$ x $10^{6}$)', loc='left', fontsize=24, color='white')
# plt.title('{}-{}'.format(month3, month5), loc='right', fontsize=24, color='white')
# cbar = plt.colorbar(data, ax=ax, ticks=[-4000000,-2000000,0,2000000,4000000], pad=0.01, shrink=0.7, aspect=40)
# cbar.ax.tick_params(labelsize=20, color="white", labelcolor="white")
# #cbar.set_label(r'Velocity Potential Anomaly ', fontsize=16)
# cbar.ax.set_yticklabels(['-4', '-2', '0', '2', '4'],fontsize=24)
# cbar.ax.set_facecolor([1,1,1,0])

# # Add a legend for labels
# legend_labels = {"#488c83": "Rising air", "#cf8a3c": "Sinking air"}

# patches = [Patch(color=color, label=label)
#            for color, label in legend_labels.items()]

# ax.legend(handles=patches,
#           bbox_to_anchor=(0.993, 0.09),
#           facecolor="white",
#           prop=dict(size=16))

# ax.text(0.01, 0.02, 'BenNollWeather', horizontalalignment = 'left', verticalalignment = 'bottom', transform=ax.transAxes, backgroundcolor='.75', fontsize=18)

# fig.patch.set_facecolor('k')

# plt.savefig(_os.path.join(_WORK, 'downloads/vp_hurr.png'), facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.18, dpi=100)

# plt.close()