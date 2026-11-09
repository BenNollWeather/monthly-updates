#!/usr/bin/env python3
"""People on the contiguous United States drawn on the forecast map.

The grid is WorldPop's 2020 UN-adjusted 1 km counts for the lower 48 and the
District of Columbia, summed to 0.05° cells inside the map extent. Cells whose
centers fall outside that drawn land, including the Great Lakes, are zero.
Alaska and Hawaii are not on the map. Rebuild it with
scripts/build_population_grid.py.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from lib.snow_forecast import _shift_lon

ROOT = Path(__file__).resolve().parents[1]
POPULATION_GRID = ROOT / "assets" / "population" / "conus_worldpop_2020_005deg.npz"
POP_STEP = 0.05
FREEZING_F = 32.0
_POPULATION: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None


def population_grid() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cell-center latitudes, longitudes, and people. Latitudes increase south to north."""
    global _POPULATION
    if _POPULATION is None:
        with np.load(POPULATION_GRID) as data:
            lat = np.asarray(data["lat"], dtype=np.float64)
            lon = np.asarray(data["lon"], dtype=np.float64)
            people = np.asarray(data["people"], dtype=np.float64)
        if people.shape != (lat.size, lon.size):
            raise ValueError(f"Population grid shape {people.shape} does not match the axes")
        _POPULATION = (lat, lon, people)
    return _POPULATION


def _sample_bilinear(values, src_lat, src_lon, dst_lat, dst_lon) -> np.ndarray:
    """Sample a regular lat/lon field at destination centers.

    Centers outside the source axes are NaN. Longitude may arrive as 0–360.
    """
    src_lat = np.asarray(src_lat, dtype=np.float64)
    src_lon = _shift_lon(src_lon)
    dst_lat = np.asarray(dst_lat, dtype=np.float64)
    dst_lon = _shift_lon(dst_lon)
    field = np.asarray(values, dtype=np.float64)
    if field.shape != (src_lat.size, src_lon.size):
        raise ValueError(f"Field shape {field.shape} does not match lat/lon sizes")
    if src_lat.size < 2 or src_lon.size < 2:
        raise ValueError("The temperature field needs at least two rows and two columns")
    lat_order = np.argsort(src_lat)
    lon_order = np.argsort(src_lon)
    lat_values = src_lat[lat_order]
    lon_values = src_lon[lon_order]
    field = field[lat_order][:, lon_order]
    dlat = float(np.median(np.diff(lat_values)))
    dlon = float(np.median(np.diff(lon_values)))
    if dlat <= 0.0 or dlon <= 0.0:
        raise ValueError("The temperature axes are not spaced")
    y_raw = (dst_lat - lat_values[0]) / dlat
    x_raw = (dst_lon - lon_values[0]) / dlon
    valid_y = (y_raw >= -1e-6) & (y_raw <= lat_values.size - 1 + 1e-6)
    valid_x = (x_raw >= -1e-6) & (x_raw <= lon_values.size - 1 + 1e-6)
    y = np.clip(y_raw, 0.0, lat_values.size - 1)
    x = np.clip(x_raw, 0.0, lon_values.size - 1)
    y0 = np.floor(y).astype(np.int32)
    x0 = np.floor(x).astype(np.int32)
    y1 = np.clip(y0 + 1, 0, lat_values.size - 1)
    x1 = np.clip(x0 + 1, 0, lon_values.size - 1)
    y0 = np.clip(y0, 0, lat_values.size - 1)
    x0 = np.clip(x0, 0, lon_values.size - 1)
    wy = (y - y0)[:, None]
    wx = (x - x0)[None, :]
    # A zero weight must not turn a finite sample into NaN when the unused corner is missing.
    north = _blend(field[y0[:, None], x0[None, :]], field[y0[:, None], x1[None, :]], wx)
    south = _blend(field[y1[:, None], x0[None, :]], field[y1[:, None], x1[None, :]], wx)
    sampled = _blend(north, south, wy)
    return np.where(valid_y[:, None] & valid_x[None, :], sampled, np.nan)


def _blend(left: np.ndarray, right: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Linear blend. An unused side is ignored, so a missing neighbor does not erase the other."""
    use_left = weight <= 1e-9
    use_right = weight >= 1.0 - 1e-9
    mixed = left * (1.0 - weight) + right * weight
    return np.where(use_left, left, np.where(use_right, right, mixed))


def freezing_population(values, lat, lon, grid=None) -> float:
    """People whose sampled minimum is at or below 32°F.

    The temperature field is sampled on the population cells. A cell with no
    finite temperature, or one outside the field, is not counted.
    """
    plat, plon, people = population_grid() if grid is None else grid
    sampled = _sample_bilinear(values, lat, lon, plat, plon)
    if sampled.shape != people.shape:
        raise ValueError(f"Sampled field shape {sampled.shape} does not match the population grid")
    cold = np.isfinite(sampled) & (sampled <= FREEZING_F)
    return float(np.asarray(people, dtype=np.float64)[cold].sum())


def freezing_population_note(values, lat, lon, grid=None) -> str:
    """One line for the minimum-temperature download."""
    millions = freezing_population(values, lat, lon, grid=grid) / 1_000_000.0
    return f"Population forecast to experience freezing temperatures: {millions:.1f} million"
