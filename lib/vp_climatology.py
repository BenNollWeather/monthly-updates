"""Build a 200 hPa velocity-potential climatology.

The monthly ECMWF runner does not call this module. It downloads the
published vp_clim_Mon.nc files instead. This builder remains for making a
replacement baseline.

The baseline defaults to 1991-2020. Set VP_CLIM_START and VP_CLIM_END to
change it. Set VP_LEVEL to change the pressure level (default 200, which is
the level the seasonal maps use).

VP_CLIMO_SOURCE:
  auto  ERA5 monthly means through CDS when credentials exist, otherwise the
        public cloud-optimized ERA5 store
  cds   ERA5 pressure-level monthly means
  arco  cloud-optimized ERA5 (WeatherBench 2, from the ARCO-ERA5 archive)

The hourly 0.25-degree ARCO store is about 154 MB per hour because each
chunk holds all 37 levels. This builder uses the 1.5-degree cloud-optimized
copy instead, unless VP_ARCO_ZARR points somewhere else. VP_ARCO_HOURS
chooses which UTC hours are averaged (default 0 and 12).

Raw downloads are deleted after the twelve monthly files are written. Those
files live in the disposable work directory and are not uploaded.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_ARCO_ZARR = (
    "gs://weatherbench2/datasets/era5/"
    "1959-2023_01_10-6h-240x121_equiangular_with_poles_conservative.zarr"
)


def bounds_from_env() -> tuple[int, int, int]:
    start = int(os.environ.get("VP_CLIM_START", "1991"))
    end = int(os.environ.get("VP_CLIM_END", "2020"))
    level = int(os.environ.get("VP_LEVEL", "200"))
    if start > end:
        raise SystemExit("VP_CLIM_START is after VP_CLIM_END.")
    if not 1 <= level <= 1000:
        raise SystemExit("VP_LEVEL must be a pressure in hPa.")
    return start, end, level


def month_path(out_dir: Path, month: int) -> Path:
    return out_dir / f"vp_clim_{_ABBR[month - 1]}.nc"


def climatology_ready(out_dir: Path, start: int, end: int, level: int) -> bool:
    for month in range(1, 13):
        path = month_path(out_dir, month)
        if not path.is_file():
            return False
        try:
            import xarray as xr

            with xr.open_dataset(path) as ds:
                if int(ds.attrs.get("climatology_start", -1)) != start:
                    return False
                if int(ds.attrs.get("climatology_end", -1)) != end:
                    return False
                if int(ds.attrs.get("pressure_hpa", -1)) != level:
                    return False
                if "velocity_potential" not in ds:
                    return False
        except Exception:
            return False
    return True


def build(out_dir: Path, start: int, end: int, level: int, source: str) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    if climatology_ready(out_dir, start, end, level):
        print(f"Velocity-potential climatology already matches {start}-{end} at {level} hPa.")
        return source
    chosen = _resolve_source(source)
    print(f"Building {level} hPa velocity-potential climatology for {start}-{end} from {chosen}.")
    if chosen == "cds":
        try:
            u, v, sampling = _load_cds(out_dir, start, end, level)
        except Exception as exc:
            if source.strip().lower() != "auto":
                raise
            print(f"ERA5 monthly means were unavailable ({type(exc).__name__}). Trying cloud-optimized ERA5.")
            u, v, sampling = _load_arco(start, end, level)
            chosen = "arco"
    else:
        u, v, sampling = _load_arco(start, end, level)
    _write_months(u, v, out_dir, start, end, level, chosen, sampling)
    if not climatology_ready(out_dir, start, end, level):
        raise SystemExit("Velocity-potential climatology is incomplete after writing.")
    print(f"Wrote 12 velocity-potential files to {out_dir}.")
    return chosen


def _resolve_source(source: str) -> str:
    source = source.strip().lower()
    if source in {"cds", "arco"}:
        return source
    if source != "auto":
        raise SystemExit("VP_CLIMO_SOURCE must be auto, cds, or arco.")
    if os.environ.get("CDSAPI_KEY") or Path.home().joinpath(".cdsapirc").is_file():
        return "cds"
    return "arco"


def _load_cds(out_dir: Path, start: int, end: int, level: int):
    import cdsapi

    target = out_dir / "era5_uv_monthly.nc"
    years = [str(year) for year in range(start, end + 1)]
    months = [f"{month:02d}" for month in range(1, 13)]
    request = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["u_component_of_wind", "v_component_of_wind"],
        "pressure_level": [str(level)],
        "year": years,
        "month": months,
        "time": ["00:00"],
        "data_format": "netcdf",
        "download_format": "unarchived",
        "grid": ["1.0", "1.0"],
    }
    client = cdsapi.Client()
    try:
        try:
            client.retrieve("reanalysis-era5-pressure-levels-monthly-means", request, str(target))
        except Exception as exc:
            if "grid" not in str(exc).lower():
                raise
            print("ERA5 monthly-means request with a 1-degree grid was rejected. Retrying on the native grid.")
            request.pop("grid", None)
            client.retrieve("reanalysis-era5-pressure-levels-monthly-means", request, str(target))
        u, v = _open_winds(target)
        return u, v, "monthly_averaged_reanalysis"
    finally:
        target.unlink(missing_ok=True)
        for extra in out_dir.glob("era5_uv_monthly.nc.*"):
            extra.unlink(missing_ok=True)


def _load_arco(start: int, end: int, level: int):
    import xarray as xr

    url = os.environ.get("VP_ARCO_ZARR", _ARCO_ZARR)
    hours = [int(item) for item in os.environ.get("VP_ARCO_HOURS", "0,12").split(",") if item.strip()]
    print(f"Reading cloud-optimized ERA5 from {url} at hours {hours} UTC.")
    store = xr.open_zarr(url, storage_options={"token": "anon"}, consolidated=True)
    try:
        u = store["u_component_of_wind"].sel(level=level, method="nearest")
        v = store["v_component_of_wind"].sel(level=level, method="nearest")
        window = slice(f"{start}-01-01", f"{end}-12-31")
        u = u.sel(time=window)
        v = v.sel(time=window)
        selected = u.time.dt.hour.isin(hours)
        u = u.where(selected, drop=True).groupby("time.month").mean("time").compute()
        v = v.where(selected, drop=True).groupby("time.month").mean("time").compute()
    finally:
        store.close()
    sampling = "calendar-month mean of ERA5 analyses at " + ",".join(str(hour) for hour in hours) + " UTC"
    return u, v, sampling


def _open_winds(path: Path):
    import xarray as xr

    try:
        ds = xr.open_dataset(path)
    except Exception:
        ds = xr.open_dataset(path, engine="cfgrib")
    try:
        u = _monthly_mean(_component(ds, "u", "u_component_of_wind")).load()
        v = _monthly_mean(_component(ds, "v", "v_component_of_wind")).load()
        return u, v
    finally:
        ds.close()


def _component(ds, *names):
    lookup = {name.lower(): name for name in ds.data_vars}
    for name in names:
        if name in ds:
            return ds[name]
        if name in lookup:
            return ds[lookup[name]]
    raise SystemExit(f"ERA5 file has no wind component {names}. Found {list(ds.data_vars)}.")


def _time_name(field):
    for name in ("valid_time", "time", "date"):
        if name in field.dims or name in field.coords:
            return name
    raise SystemExit("ERA5 wind field has no time coordinate.")


def _monthly_mean(field):
    time_name = _time_name(field)
    months = field[time_name].dt.month
    return field.groupby(months).mean(time_name)


def _write_months(u, v, out_dir: Path, start: int, end: int, level: int, source: str, sampling: str) -> None:
    import xarray as xr
    from windspharm.xarray import VectorWind

    for month in range(1, 13):
        uu = _prepare_wind(_select_month(u, month))
        vv = _prepare_wind(_select_month(v, month))
        potential = VectorWind(uu, vv).velocitypotential()
        potential.name = "velocity_potential"
        dataset = xr.Dataset({"velocity_potential": potential})
        dataset.attrs.update(
            {
                "climatology_start": start,
                "climatology_end": end,
                "pressure_hpa": level,
                "source": source,
                "sampling": sampling,
                "baseline": f"{start}-{end}",
            }
        )
        target = month_path(out_dir, month)
        if target.exists():
            target.unlink()
        dataset.to_netcdf(target)
        dataset.close()


def _select_month(field, month: int):
    if "month" in field.dims or "month" in field.coords:
        return field.sel(month=month)
    time_name = _time_name(field)
    return field.sel({time_name: field[time_name].dt.month == month}).mean(time_name)


def _prepare_wind(field):
    field = field.squeeze(drop=True).reset_coords(drop=True)
    rename = {}
    if "lat" in field.dims:
        rename["lat"] = "latitude"
    if "lon" in field.dims:
        rename["lon"] = "longitude"
    if rename:
        field = field.rename(rename)
    if "latitude" not in field.dims or "longitude" not in field.dims:
        raise SystemExit(f"Wind field is missing a lat/lon grid. Dims: {field.dims}")
    field = _coarsen_to_about_one_degree(field)
    longitudes = field["longitude"]
    if float(longitudes.max()) <= 180.0:
        shifted = (longitudes + 360.0) % 360.0
        field = field.assign_coords(longitude=shifted).sortby("longitude")
    longitudes = field["longitude"]
    if abs((float(longitudes[-1]) % 360.0) - (float(longitudes[0]) % 360.0)) < 0.05 and longitudes.size > 1:
        field = field.isel(longitude=slice(0, -1))
    return field.sortby("latitude")


def _coarsen_to_about_one_degree(field):
    latitude = field["latitude"]
    longitude = field["longitude"]
    if latitude.size < 2 or longitude.size < 2:
        return field
    spacing = abs(float(latitude[1] - latitude[0]))
    if spacing >= 0.75:
        return field
    factor = max(1, int(round(1.0 / spacing)))
    return field.coarsen(latitude=factor, longitude=factor, boundary="trim").mean()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build the velocity-potential climatology.")
    parser.add_argument("--out", required=True, help="Directory for vp_clim_Mon.nc files")
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--source", default=None)
    args = parser.parse_args()
    start, end, level = bounds_from_env()
    if args.start is not None:
        start = args.start
    if args.end is not None:
        end = args.end
    source = args.source or os.environ.get("VP_CLIMO_SOURCE", "auto")
    build(Path(args.out), start, end, level, source)


if __name__ == "__main__":
    main()
