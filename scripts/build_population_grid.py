#!/usr/bin/env python3
"""Sum WorldPop 2020 1 km counts onto the forecast map's population grid.

State extracts, UN-adjusted, lower 48. The Maryland file includes the
District of Columbia. Alaska and Hawaii are left out. Points are totaled on
0.05° cells inside the map extent, then a cell whose center is outside the
drawn United States land is set to zero.

Source files:
https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/0_ASCII_gridded_XYZ/US_States/
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.population import POP_STEP, POPULATION_GRID  # noqa: E402
from lib.snow_anomaly import EXTENT  # noqa: E402
from lib.snow_forecast import _drawn_land_mask  # noqa: E402

BASE = "https://data.worldpop.org/GIS/Population/Global_2000_2020/2020/0_ASCII_gridded_XYZ/US_States"
# Maryland's extract includes the District of Columbia.
STATES = (
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS",
    "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT",
    "VT", "VA", "WA", "WV", "WI", "WY",
)
CACHE = Path("/tmp/worldpop-2020")


def _url(code: str) -> str:
    return f"{BASE}/US-{code}_ppp_2020_1km_UNadj_ASCII_gridded_XYZ.zip"


def _download(code: str) -> Path:
    dest = CACHE / f"US-{code}.zip"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    subprocess.run(
        ["curl", "-fsSL", "--retry", "3", "--retry-delay", "2", "-o", str(tmp), _url(code)],
        check=True,
    )
    tmp.replace(dest)
    print(f"downloaded {code} ({dest.stat().st_size:,} bytes)", flush=True)
    return dest


def _load_xyz(path: Path) -> np.ndarray:
    with zipfile.ZipFile(path) as archive:
        name = next(item for item in archive.namelist() if item.lower().endswith(".csv"))
        with archive.open(name) as raw:
            header = raw.readline().decode("utf-8", "replace")
        delimiter = "," if "," in header else None
        with archive.open(name) as raw:
            points = np.loadtxt(raw, delimiter=delimiter, skiprows=1, dtype=np.float64)
    if points.ndim == 1:
        points = points.reshape(1, -1)
    if points.shape[1] != 3:
        raise ValueError(f"{path.name} has {points.shape[1]} columns")
    return points


def main() -> int:
    west, east, south, north = EXTENT
    nlon = int(round((east - west) / POP_STEP))
    nlat = int(round((north - south) / POP_STEP))
    people = np.zeros((nlat, nlon), dtype=np.float64)
    CACHE.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_download, code) for code in STATES]
        paths = [future.result() for future in futures]
    raw = 0.0
    for code, path in zip(STATES, paths):
        points = _load_xyz(path)
        lon = points[:, 0]
        lat = points[:, 1]
        count = points[:, 2]
        good = np.isfinite(lon) & np.isfinite(lat) & np.isfinite(count) & (count > 0.0)
        lon = lon[good]
        lat = lat[good]
        count = count[good]
        rows = np.floor((lat - south) / POP_STEP).astype(np.int32)
        cols = np.floor((lon - west) / POP_STEP).astype(np.int32)
        inside = (rows >= 0) & (rows < nlat) & (cols >= 0) & (cols < nlon)
        np.add.at(people, (rows[inside], cols[inside]), count[inside])
        kept = float(count[inside].sum())
        raw += kept
        print(f"{code} {kept / 1e6:.2f} million inside the map", flush=True)
    lat_centers = south + (np.arange(nlat) + 0.5) * POP_STEP
    lon_centers = west + (np.arange(nlon) + 0.5) * POP_STEP
    print("masking cell centers to the drawn land", flush=True)
    on_land = _drawn_land_mask(lat_centers, lon_centers)
    removed = float(people[~on_land].sum())
    people[~on_land] = 0.0
    total = float(people.sum())
    print(
        f"inside the map {raw / 1e6:.2f} million; "
        f"on drawn land {total / 1e6:.2f} million; "
        f"removed {removed / 1e6:.2f} million",
        flush=True,
    )
    if not (250e6 <= total <= 400e6):
        raise SystemExit(f"Population total {total / 1e6:.1f} million is outside 250–400")
    POPULATION_GRID.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        POPULATION_GRID,
        lat=lat_centers,
        lon=lon_centers,
        people=people.astype(np.float32),
    )
    print(f"wrote {POPULATION_GRID} ({POPULATION_GRID.stat().st_size:,} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
