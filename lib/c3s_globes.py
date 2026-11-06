#!/usr/bin/env python3
"""Seasonal outlook globes from Copernicus ensemble-mean anomalies.

Each variable is one CDS request. That request asks for the ensemble mean from
every centre at once, for lead months 2, 3, and 4. A centre missing from the
file is named and left out of that variable. System numbers are read from the
file. A centre that publishes more than one current system gets one vote each.

The initialization month is lead 1 and is not mapped. The three leads are
averaged, then each model votes above or below zero. Snowfall votes only when
that average reaches 1 inch over the season, so a trace does not count. A
centre can publish more than one system, and those system numbers change. Each
system that is still current votes on its own. Two systems are never averaged,
and a new system number is kept instead of being dropped for an older one.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.ap_dates import _ABBR  # noqa: E402
from lib.release_wait import NOT_READY_EXIT, is_fatal, is_not_ready  # noqa: E402

DATASET = "seasonal-postprocessed-single-levels"
LEADS = (2, 3, 4)
NLAT = 181
NLON = 360
LATS = np.linspace(90, -90, NLAT)
LONS = np.arange(NLON, dtype=float)
OCEAN_STRENGTH = 0.42
# m/s of water equivalent -> inches of snow over a 90-day season, 10:1 ratio.
SNOW_INCHES = 39.3701 * 10 * 86400 * 90
SNOW_GATE_INCHES = 1.0

_UNAVAILABLE = (
    "no data",
    "not available",
    "not yet available",
    "none of the data",
    "no matching",
    "invalid request",
    "not a valid",
    "bad request",
    "unknown variable",
    "combination",
    "empty",
)


@dataclass(frozen=True)
class Centre:
    id: str
    name: str
    systems: tuple[str, ...]


@dataclass(frozen=True)
class Field:
    id: str
    name: str
    variable: str
    above: str
    below: str
    phrase_above: str
    phrase_below: str
    colors: tuple[str, str]


# Every id here is requested. The tuple is not a preference order. Which of
# them votes is decided from the file for that month.
CENTRES = (
    Centre("ecmwf", "ECMWF", ("51", "5")),
    Centre("ukmo", "UKMET", ("610", "605", "604")),
    Centre("meteo_france", "Météo-France", ("9", "8")),
    Centre("dwd", "DWD", ("22", "21")),
    Centre("cmcc", "CMCC", ("4", "35")),
    Centre("jma", "JMA", ("4", "3", "2")),
    Centre("ncep", "NCEP", ("2",)),
    Centre("eccc", "ECCC", ("5", "4", "3", "2")),
    Centre("bom", "BOM", ("2",)),
)

# Older id, then the id that replaced it. The last id on a line is the newest
# known one. ECCC has two lines because CanSIPSv3 is two models, not one model
# with a spare version number.
_LINES = {
    "ecmwf": (("4", "5", "51"),),
    "ukmo": (("600", "601", "602", "603", "604", "605", "610"),),
    "meteo_france": (("5", "6", "7", "8", "9"),),
    "dwd": (("2", "21", "22"),),
    "cmcc": (("3", "35", "4"),),
    "jma": (("2", "3", "4"),),
    "ncep": (("2",),),
    "bom": (("2",),),
    "eccc": (("1", "3", "5"), ("2", "4")),
}
_LABELS = {
    ("eccc", "5"): "ECCC GEM5.2-NEMO",
    ("eccc", "4"): "ECCC CanESM5",
    ("eccc", "3"): "ECCC GEM5-NEMO",
    ("eccc", "2"): "ECCC CanCM4i",
    ("eccc", "1"): "ECCC GEM-NEMO",
}

FIELDS = (
    Field("temp", "Air temperatures", "2m_temperature_anomaly", "Warmer", "Cooler", "higher temperatures than average", "lower temperatures than average", ("#b30000", "#053061")),
    Field("sst", "Sea surface temperatures", "sea_surface_temperature_anomaly", "Warmer", "Cooler", "higher sea surface temperatures than average", "lower sea surface temperatures than average", ("#b30000", "#053061")),
    Field("rain", "Rainfall", "total_precipitation_anomalous_rate_of_accumulation", "Wetter", "Drier", "higher rainfall than average", "lower rainfall than average", ("#00441b", "#cc4c02")),
    Field("snow", "Snowfall", "snowfall_anomalous_rate_of_accumulation", "More snow", "Less snow", "more snowfall than average", "less snowfall than average", ("#08589e", "#d94701")),
    Field("dew", "Dew points", "2m_dewpoint_temperature_anomaly", "More humid", "Less humid", "higher humidity than average", "lower humidity than average", ("#023858", "#e34a33")),
    Field("cloud", "Cloud cover", "total_cloud_cover_anomaly", "Cloudier", "Less cloudy", "higher cloud cover than average", "lower cloud cover than average", ("#252525", "#e6550d")),
    Field("mslp", "Air pressure", "mean_sea_level_pressure_anomaly", "Higher", "Lower", "higher air pressure than average", "lower air pressure than average", ("#b30000", "#053061")),
    Field("wind", "Wind", "10m_wind_speed_anomaly", "Windier", "Less windy", "higher wind speeds than average", "lower wind speeds than average", ("#8c510a", "#045a8d")),
)


class Unavailable(Exception):
    """This centre does not publish the requested field."""


class FatalCDS(Exception):
    """The request cannot succeed by trying another centre."""


def add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    month += offset
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    return year, month


def parse_month(value: str) -> date:
    text = value.strip()
    try:
        year_text, month_text = text.split("-")
        year, month = int(year_text), int(month_text)
        if len(year_text) != 4 or not 1 <= month <= 12:
            raise ValueError
        return date(year, month, 1)
    except (ValueError, AttributeError) as exc:
        raise SystemExit(f"Invalid month {value!r}; expected YYYY-MM") from exc


def parse_day(value: str) -> date:
    text = value.strip()
    try:
        year_text, month_text, day_text = text.split("-")
        parsed = date(int(year_text), int(month_text), int(day_text))
    except ValueError as exc:
        raise SystemExit(f"Invalid date {value!r}; expected YYYY-MM-DD") from exc
    if f"{parsed:%Y-%m-%d}" != text:
        raise SystemExit(f"Invalid date {value!r}; expected YYYY-MM-DD")
    return parsed


def resolve_init(today: date, explicit: str = "") -> date:
    """Initialization month whose leads 2-4 are the outlook on this page."""
    if explicit.strip():
        return parse_month(explicit)
    if today.day < 10:
        year, month = add_months(today.year, today.month, -1)
        return date(year, month, 1)
    return date(today.year, today.month, 1)


def season_months(init: date) -> list[date]:
    months = []
    for lead in LEADS:
        year, month = add_months(init.year, init.month, lead - 1)
        months.append(date(year, month, 1))
    return months


def period_label(months: list[date]) -> str:
    first, last = months[0], months[-1]
    left, right = _ABBR[first.month], _ABBR[last.month]
    if first.year == last.year:
        return f"{left}-{right} {first.year}"
    return f"{left} {first.year}-{right} {last.year}"


def headline_title(months: list[date]) -> str:
    """Page title. Month and year stay in AP style, with no comma."""
    first, last = months[0], months[-1]
    return (
        f"Climate headlines from {_ABBR[first.month]} {first.year} "
        f"to {_ABBR[last.month]} {last.year}"
    )


def lat_index(lat: float) -> int:
    index = math.floor((90.0 - lat) + 0.5)
    return max(0, min(NLAT - 1, index))


def lon_index(lon: float) -> int:
    x = lon % 360.0
    if x < 0:
        x += 360.0
    index = math.floor(x + 0.5)
    if index == NLON:
        index = 0
    return index


def majority(above: np.ndarray, voted: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return sign, above-count, and valid-count from per-model boolean grids.

    sign is 1, -1, or 0. A tie, including a cell with no votes, is 0.
    Ocean opacity is not applied here.
    """
    above_count = above.sum(axis=0).astype(np.int16)
    valid = voted.sum(axis=0).astype(np.int16)
    below = valid - above_count
    sign = np.zeros(above_count.shape, dtype=np.int8)
    sign[above_count > below] = 1
    sign[below > above_count] = -1
    return sign, above_count, valid


def model_votes(field: Field, mean: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return above and voted masks for one model's seasonal mean.

    Snowfall counts only at or beyond 1 inch over the 90-day season. A smaller
    anomaly, including a trace in a place that rarely sees snow, does not vote.
    """
    finite = np.isfinite(mean)
    if field.id == "snow":
        keep = finite & (np.abs(mean) * SNOW_INCHES >= SNOW_GATE_INCHES)
    else:
        keep = finite & (mean != 0)
    return keep & (mean > 0), keep


def close_empty_meridian(above: np.ndarray, voted: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    """Fill a longitude column a model left empty while a neighbor has values.

    Nearest interpolation drops longitude 0 when a source grid starts at 0.5°.
    That empty column is the seam. Copy the neighboring column for that model.
    """
    above_bits = _unpack(above, count)
    voted_bits = _unpack(voted, count)
    nlon = voted_bits.shape[-1]
    for bit in range(count):
        missing_frac = (~voted_bits[bit]).mean(axis=0)
        for col in np.flatnonzero(missing_frac >= 0.95):
            right = (int(col) + 1) % nlon
            left = (int(col) - 1) % nlon
            donor = right if voted_bits[bit, :, right].mean() >= voted_bits[bit, :, left].mean() else left
            if float(voted_bits[bit, :, donor].mean()) < 0.5:
                continue
            gap = ~voted_bits[bit, :, col]
            voted_bits[bit, :, col] = np.where(gap, voted_bits[bit, :, donor], voted_bits[bit, :, col])
            above_bits[bit, :, col] = np.where(gap, above_bits[bit, :, donor], above_bits[bit, :, col])
    return pack_bits(above_bits), pack_bits(voted_bits)


def pack_bits(mask: np.ndarray) -> np.ndarray:
    if mask.shape[0] > 16:
        raise SystemExit("A field has more than 16 models, which the page cannot pack.")
    packed = np.zeros(mask.shape[1:], dtype="<u2")
    for index in range(mask.shape[0]):
        packed |= mask[index].astype("<u2") << np.uint16(index)
    return packed


def _b64(values: np.ndarray) -> str:
    raw = np.ascontiguousarray(values).tobytes()
    return base64.b64encode(raw).decode("ascii")


def _weights() -> np.ndarray:
    return np.cos(np.deg2rad(LATS))[:, None]


def field_shares(sign: np.ndarray, land: np.ndarray) -> dict[str, float]:
    weights = _weights()
    lat = LATS[:, None]
    masks = {
        "globe": np.ones(sign.shape, dtype=bool),
        "tropics": np.broadcast_to(np.abs(lat) <= 23.5, sign.shape),
        "north": (lat >= 35) & (land == 1),
    }
    shares: dict[str, float] = {}
    for name, mask in masks.items():
        total = float(np.where(mask, weights, 0.0).sum())
        if total <= 0:
            shares[f"{name}_above"] = 0.0
            shares[f"{name}_below"] = 0.0
            continue
        shares[f"{name}_above"] = float(np.where(mask & (sign == 1), weights, 0.0).sum() / total)
        shares[f"{name}_below"] = float(np.where(mask & (sign == -1), weights, 0.0).sum() / total)
    return shares


@dataclass(frozen=True)
class Lean:
    side: str
    share: float


def domain_lean(summary: dict | None, domain: str) -> Lean | None:
    if not summary or summary.get("models", 0) <= 0:
        return None
    above = float(summary[f"{domain}_above"])
    below = float(summary[f"{domain}_below"])
    if above + below < 0.2:
        return None
    if abs(above - below) < 0.05:
        return Lean("split", max(above, below))
    if above > below:
        return Lean("above", above)
    return Lean("below", below)


def _temperature_sentence(summary: dict | None) -> str | None:
    globe = domain_lean(summary, "globe")
    if globe is None or globe.side == "split":
        if summary and summary.get("models", 0):
            return "Warm and cool forecasts cover similar parts of the planet."
        return None
    phrase = "warmer than average" if globe.side == "above" else "cooler than average"
    if globe.share >= 0.55:
        sentence = f"Most of the planet is forecast {phrase}"
    else:
        sentence = f"The planet leans {phrase}"
    tropics = domain_lean(summary, "tropics")
    if tropics and tropics.side == globe.side:
        if tropics.share >= 0.55:
            return sentence + ", including most of the tropics."
        return sentence + ", including the tropics."
    if tropics and tropics.side not in {"split"} and tropics.side != globe.side:
        other = "warmer than average" if tropics.side == "above" else "cooler than average"
        return sentence + f", while the tropics lean {other}."
    return sentence + "."


def _moisture_sentence(rain: dict | None, dew: dict | None) -> str | None:
    def pick(summary: dict | None) -> tuple[Lean | None, str]:
        tropics = domain_lean(summary, "tropics")
        if tropics and tropics.side != "split":
            return tropics, "tropics"
        globe = domain_lean(summary, "globe")
        if globe and globe.side != "split":
            return globe, "globe"
        return None, ""

    rain_lean, rain_domain = pick(rain)
    dew_lean, dew_domain = pick(dew)
    if (
        rain_lean
        and dew_lean
        and rain_lean.side == dew_lean.side
        and rain_domain == dew_domain
    ):
        phrase = (
            "wetter and more humid than average"
            if rain_lean.side == "above"
            else "drier and less humid than average"
        )
        share = min(rain_lean.share, dew_lean.share)
        if rain_domain == "tropics":
            if share >= 0.55:
                return f"Most of the tropics are forecast {phrase}."
            return f"The tropics lean {phrase}."
        if share >= 0.55:
            return f"Most of the planet is forecast {phrase}."
        return f"The planet leans {phrase}."
    parts = []
    if rain_lean:
        phrase = "wetter than average" if rain_lean.side == "above" else "drier than average"
        where = "The tropics lean" if rain_domain == "tropics" else "Rainfall leans"
        if rain_domain == "tropics":
            parts.append(f"{where} {phrase}.")
        else:
            parts.append(f"Rainfall leans {phrase}.")
    if dew_lean:
        phrase = "more humid than average" if dew_lean.side == "above" else "less humid than average"
        if dew_domain == "tropics":
            parts.append(f"The tropics lean {phrase}.")
        else:
            parts.append(f"Dew points lean {phrase}.")
    return " ".join(parts) if parts else None


def _snow_pressure_sentence(snow: dict | None, pressure: dict | None) -> str | None:
    snow_lean = domain_lean(snow, "north")
    pressure_lean = domain_lean(pressure, "globe")
    snow_text = ""
    if snow_lean and snow_lean.side != "split":
        phrase = "more snow than average" if snow_lean.side == "above" else "less snow than average"
        if snow_lean.share >= 0.55:
            snow_text = f"Most of the northern land is forecast {phrase}"
        else:
            snow_text = f"Northern land leans {phrase}"
    pressure_text = ""
    if pressure_lean and pressure_lean.side != "split":
        word = "Higher" if pressure_lean.side == "above" else "Lower"
        pressure_text = f"{word} pressure is the more common forecast"
    if snow_text and pressure_text:
        return f"{snow_text}, and {pressure_text[0].lower()}{pressure_text[1:]}."
    if snow_text:
        return snow_text + "."
    if pressure_text:
        return pressure_text + "."
    return None


def story_lines(summaries: dict[str, dict]) -> list[str]:
    """Two or three planetary sentences. A split field is left out."""
    lines = []
    for sentence in (
        _temperature_sentence(summaries.get("temp")),
        _moisture_sentence(summaries.get("rain"), summaries.get("dew")),
        _snow_pressure_sentence(summaries.get("snow"), summaries.get("mslp")),
    ):
        if sentence:
            lines.append(sentence)
    if len(lines) < 2:
        wind = domain_lean(summaries.get("wind"), "globe")
        if wind and wind.side != "split":
            phrase = "windier than average" if wind.side == "above" else "less windy than average"
            if wind.share >= 0.55:
                lines.append(f"Most of the planet is forecast {phrase}.")
            else:
                lines.append(f"The planet leans {phrase}.")
    return lines[:3]


def _exception_text(exc: BaseException) -> str:
    parts = []
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(str(current))
        current = current.__cause__ or current.__context__
    return " ".join(parts).lower()


def _is_unavailable(exc: BaseException) -> bool:
    if is_not_ready(exc):
        return True
    text = _exception_text(exc)
    return any(pattern in text for pattern in _UNAVAILABLE)


def _brief(exc: BaseException) -> str:
    text = " ".join(str(exc).split())
    return text[:180]


_CENTRE_ALIASES = (
    ("ecmwf", ("ecmwf", "ecmf", "european centre")),
    ("ukmo", ("ukmo", "met office", "exeter", "egrr")),
    ("meteo_france", ("meteo-france", "meteo france", "météo", "toulouse", "lfpw", "french weather")),
    ("dwd", ("dwd", "offenbach", "deutscher", "edzw")),
    ("cmcc", ("cmcc", "euro-mediterraneo", "cnmc")),
    ("jma", ("jma", "tokyo", "rjtd", "japanese meteorological")),
    ("ncep", ("ncep", "kwbc", "national weather service")),
    ("eccc", ("eccc", "montreal", "cwao", "canadian meteorological")),
    ("bom", ("bom", "bureau of meteorology", "ammc")),
)


def field_request(field: Field, centres: tuple[Centre, ...], init: date) -> dict:
    """Ensemble mean for every selected centre and lead, in one request.

    Every known system id is requested. Which of those ids votes is decided
    from the file, so a number that changes from month to month is still read.
    """
    systems: list[str] = []
    for centre in centres:
        for system in centre.systems:
            if system not in systems:
                systems.append(system)
    return {
        "originating_centre": [centre.id for centre in centres],
        "system": systems,
        "variable": field.variable,
        "product_type": "ensemble_mean",
        "year": f"{init.year}",
        "month": f"{init.month:02d}",
        "leadtime_month": [str(lead) for lead in LEADS],
        "format": "grib",
    }


def match_centre(dataset, centres: tuple[Centre, ...]) -> Centre | None:
    """Map a GRIB message to a centre by its institution text."""
    text = " ".join(
        str(dataset.attrs.get(key, ""))
        for key in ("institution", "centre", "source", "GRIB_centre", "GRIB_centreDescription")
    ).casefold()
    by_id = {centre.id: centre for centre in centres}
    best_id = ""
    best_len = 0
    for centre_id, aliases in _CENTRE_ALIASES:
        if centre_id not in by_id:
            continue
        for alias in aliases:
            if alias in text and len(alias) > best_len:
                best_id = centre_id
                best_len = len(alias)
    if not best_id:
        return None
    return by_id[best_id]


def _is_grib(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(4) == b"GRIB" and path.stat().st_size > 200
    except OSError:
        return False


def retrieve(client, request: dict, target: Path, attempts: int = 4) -> None:
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            if target.exists():
                target.unlink()
            client.retrieve(DATASET, request, str(target))
            if _is_grib(target):
                return
            raise Unavailable(f"response was not a GRIB file ({target.stat().st_size if target.exists() else 0} bytes)")
        except Unavailable:
            raise
        except Exception as exc:
            if is_fatal(exc):
                raise FatalCDS(_brief(exc)) from exc
            if _is_unavailable(exc):
                raise Unavailable(_brief(exc)) from exc
            last = exc
            time.sleep(min(60, 5 * attempt))
    if last is not None:
        raise last
    raise Unavailable("empty response")


def _data_array(dataset):
    for name, values in dataset.data_vars.items():
        if values.ndim >= 2:
            return values
    raise Unavailable("GRIB file had no grid")


class SkipMessage(Exception):
    """This GRIB message cannot be used. Other centres in the file still count."""


def _normalize_system(value) -> str:
    """System id as text. A missing key stays blank and is never renamed."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("ascii", "replace")
    elif not isinstance(value, str):
        item = getattr(value, "item", None)
        if callable(item):
            try:
                value = item()
            except Exception:
                pass
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if len(text) > 2 and text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.casefold() in {"", "undef", "unknown", "nan", "none"}:
        return ""
    return text


def _system_of(dataset) -> str:
    coords = getattr(dataset, "coords", {})
    if "system" in coords:
        values = np.asarray(coords["system"].values).reshape(-1)
        texts = []
        for item in values:
            text = _normalize_system(item)
            if text and text not in texts:
                texts.append(text)
        if len(texts) == 1:
            return texts[0]
    for key, value in getattr(dataset, "attrs", {}).items():
        folded = str(key).casefold().replace("grib_", "")
        if folded in {"system", "systemnumber", "system_number"}:
            text = _normalize_system(value)
            if text:
                return text
    return ""


def _season_month(value, months: list[date]) -> date | None:
    """Month of a validity time, using the same 20-day shift as the snow maps."""
    if value is None:
        return None
    item = np.asarray(value).reshape(-1)
    if item.size != 1:
        return None
    try:
        stamp = np.datetime64(item[0], "D")
    except (ValueError, OSError):
        return None
    if np.isnat(stamp):
        return None
    shifted = stamp - np.timedelta64(20, "D")
    found = date(int(str(shifted)[:4]), int(str(shifted)[5:7]), 1)
    if found in months:
        return found
    return None


def _lead_dim(values) -> str | None:
    for name in ("step", "forecastMonth", "leadtime_month", "time"):
        if name in values.dims and values.sizes[name] > 1:
            return name
    extras = [dim for dim in values.dims if dim not in {"latitude", "lat", "longitude", "lon"}]
    if len(extras) == 1 and values.sizes[extras[0]] > 1:
        return extras[0]
    return None


def _stamp(dataset, values, dim: str | None, index: int):
    for holder in (values, dataset):
        coords = getattr(holder, "coords", None)
        if coords is None or "valid_time" not in coords:
            continue
        coord = coords["valid_time"]
        if dim and dim in coord.dims:
            return coord.isel({dim: index}).values
        if np.asarray(coord.values).size == 1:
            return coord.values
    if "time" in getattr(values, "coords", {}) and "step" in values.coords:
        base = np.asarray(values.coords["time"].values).reshape(-1)
        step = np.asarray(values.coords["step"].values).reshape(-1)
        pick = index if dim == "step" and step.size > 1 else 0
        if base.size >= 1 and step.size > pick:
            try:
                return np.datetime64(base[0], "ns") + step.astype("timedelta64[ns]")[pick]
            except (TypeError, ValueError):
                return None
    return None


def _to_grid(values) -> np.ndarray:
    values = values.squeeze(drop=True)
    lat_name = "latitude" if "latitude" in values.coords else "lat"
    lon_name = "longitude" if "longitude" in values.coords else "lon"
    if lat_name not in values.dims or lon_name not in values.dims:
        raise SkipMessage(f"dims {tuple(values.dims)}")
    extra = [dim for dim in values.dims if dim not in {lat_name, lon_name}]
    if extra:
        raise SkipMessage(f"dims {tuple(values.dims)}")
    longitude = values[lon_name]
    if float(np.nanmin(longitude.values)) < 0:
        values = values.assign_coords({lon_name: (longitude % 360)})
    values = values.sortby(lon_name)
    values = _wrap_longitudes(values, lon_name)
    values = values.interp({lat_name: LATS, lon_name: LONS}, method="nearest")
    grid = np.asarray(values.values, dtype=np.float64)
    if grid.shape != (NLAT, NLON):
        raise SkipMessage(f"grid shape {tuple(grid.shape)}")
    return grid


def _wrap_longitudes(values, lon_name: str):
    """Repeat the edge columns one turn west and east so longitude 0 interpolates."""
    import xarray as xr

    lon = np.asarray(values[lon_name].values, dtype=float)
    if lon.size < 2:
        return values
    west = values.isel({lon_name: [-1]}).assign_coords({lon_name: [float(lon[-1] - 360.0)]})
    east = values.isel({lon_name: [0]}).assign_coords({lon_name: [float(lon[0] + 360.0)]})
    return xr.concat([west, values, east], dim=lon_name)


def _pieces(dataset, months: list[date]) -> list[tuple[date, np.ndarray]]:
    values = _data_array(dataset).load()
    dim = _lead_dim(values)
    if dim is None:
        month = _season_month(_stamp(dataset, values, None, 0), months)
        if month is None:
            raise SkipMessage("no lead month")
        return [(month, _to_grid(values))]
    found = []
    count = int(values.sizes[dim])
    for index in range(count):
        month = _season_month(_stamp(dataset, values, dim, index), months)
        if month is None and count == len(months):
            month = months[index]
        if month not in months:
            continue
        found.append((month, _to_grid(values.isel({dim: index}))))
    if not found:
        raise SkipMessage("none of the three lead months")
    return found


def _indexed_systems(path: Path) -> list[tuple[str, object]]:
    """System values as cfgrib indexes them, in first-seen order.

    The ID is whatever this month's file contains. A missing key stays blank.
    """
    import cfgrib.messages
    from cfgrib.dataset import INDEX_KEYS, open_fileindex

    stream = cfgrib.messages.FileStream(str(path), errors="warn")
    index = open_fileindex(
        stream,
        indexpath="",
        index_keys=list(INDEX_KEYS) + ["time", "step", "system"],
    )
    found: list[tuple[str, object]] = []
    seen: set[str] = set()
    for raw in index["system"]:
        text = _normalize_system(raw)
        if text in seen:
            continue
        seen.add(text)
        found.append((text, raw if text else "undef"))
    return found


def _open_system(path: Path, text: str, raw: object) -> list[tuple]:
    """Open one system. The filter value keeps the type cfgrib stored."""
    import cfgrib

    candidates: list[object] = []
    if text:
        candidates.append(raw)
        if text.isdigit():
            number = int(text)
            if not any(number == item and type(number) is type(item) for item in candidates):
                candidates.append(number)
        if not any(text == item and type(text) is type(item) for item in candidates):
            candidates.append(text)
    else:
        candidates.append("undef")
    last: Exception | None = None
    for value in candidates:
        kwargs = {
            "indexpath": "",
            "read_keys": ["system", "systemNumber"],
            "filter_by_keys": {"system": value},
        }
        try:
            datasets = list(cfgrib.open_datasets(str(path), backend_kwargs=kwargs))
        except Exception as exc:
            last = exc
            continue
        if datasets:
            return [(dataset, text) for dataset in datasets]
    if last is not None:
        print(f"skip system {text or '?'}: {_brief(last)}", flush=True)
    return []


def _open_tagged(path: Path) -> list[tuple]:
    """Open each system that arrived. xarray has no open_datasets; cfgrib does."""
    import cfgrib

    try:
        groups = _indexed_systems(path)
    except Exception as exc:
        raise Unavailable(_brief(exc)) from exc
    if not groups:
        raise Unavailable("GRIB file had no messages")
    # No system id in the file: one open, and the blank id is left blank.
    if len(groups) == 1 and groups[0][0] == "":
        try:
            datasets = list(cfgrib.open_datasets(
                str(path),
                backend_kwargs={"indexpath": "", "read_keys": ["system", "systemNumber"]},
            ))
        except Exception as exc:
            raise Unavailable(_brief(exc)) from exc
        if not datasets:
            raise Unavailable("GRIB file had no messages")
        return [(dataset, _system_of(dataset)) for dataset in datasets]
    tagged = []
    missed = []
    for text, raw in groups:
        found = _open_system(path, text, raw)
        if found:
            tagged.extend(found)
        else:
            missed.append(text or "?")
    if missed:
        print(f"unreadable system {', '.join(missed)}", flush=True)
    if not tagged:
        raise Unavailable("GRIB file had no readable system")
    return tagged


def _split_system_dim(dataset, system: str):
    """Yield one grid group per system when a file still stacks them."""
    dims = getattr(dataset, "dims", {})
    if "system" in dims:
        values = np.asarray(dataset.coords["system"].values).reshape(-1)
        count = int(dataset.sizes["system"])
        for index in range(count):
            text = _normalize_system(values[index]) if index < values.size else ""
            yield dataset.isel(system=index, drop=True), text or system
        return
    yield dataset, system or _system_of(dataset)


def active_system_ids(centre_id: str, present: list[str]) -> list[str]:
    """Which complete system ids vote this month.

    One succession line keeps its newest complete id. An id that is not on that
    line replaces it, because the published number can change. ECCC has two
    lines, so each line keeps its own newest id and an unknown id is extra.
    A blank id is used only when the file has no real system number.
    """
    ordered: list[str] = []
    for system in present:
        if system not in ordered:
            ordered.append(system)
    real = [system for system in ordered if system]
    lines = _LINES.get(centre_id, ())
    known = {system for line in lines for system in line}
    unknown = [system for system in real if system not in known]
    selected: list[str] = []
    if len(lines) > 1:
        for line in lines:
            for system in reversed(line):
                if system in real:
                    selected.append(system)
                    break
        for system in unknown:
            if system not in selected:
                selected.append(system)
    elif unknown:
        selected = list(unknown)
    else:
        line = lines[0] if lines else ()
        for system in reversed(line):
            if system in real:
                selected.append(system)
                break
        if not selected:
            selected = list(real)
    if not selected and "" in ordered:
        selected = [""]
    return selected


def model_name(centre: Centre, system: str) -> str:
    label = _LABELS.get((centre.id, system))
    if label:
        return label
    if not system:
        return centre.name
    lines = _LINES.get(centre.id, ())
    known = {item for line in lines for item in line}
    if len(lines) > 1 or system not in known:
        return f"{centre.name} system {system}"
    return centre.name


def select_models(centre: Centre, samples: list[dict], months: list[date]) -> list[dict]:
    """One entry per current system. Lead months are averaged later, systems are not."""
    by_system: dict[str, dict[date, np.ndarray]] = {}
    order: list[str] = []
    for sample in samples:
        system = _normalize_system(sample.get("system", ""))
        bucket = by_system.setdefault(system, {})
        if system not in order:
            order.append(system)
        bucket[sample["month"]] = sample["grid"]
    ready: dict[str, list[np.ndarray]] = {}
    complete: list[str] = []
    for system in order:
        grids = by_system[system]
        if any(month not in grids for month in months):
            continue
        ready[system] = [grids[month] for month in months]
        complete.append(system)
    return [
        {"system": system, "grids": ready[system], "name": model_name(centre, system)}
        for system in active_system_ids(centre.id, complete)
    ]


def _choose(centre: Centre, samples: list[dict], months: list[date]) -> dict | None:
    """The one selected model, or nothing when a centre contributes zero or several."""
    models = select_models(centre, samples, months)
    if len(models) == 1:
        return models[0]
    return None


def read_centres(path: Path, centres: tuple[Centre, ...], months: list[date]) -> dict:
    """Split one multi-model GRIB into three lead grids per current system."""
    tagged = _open_tagged(path)
    samples = {centre.id: [] for centre in centres}
    try:
        for dataset, system in tagged:
            for piece, piece_system in _split_system_dim(dataset, system):
                label = str(piece.attrs.get("institution") or piece.attrs.get("centre") or "")
                centre = match_centre(piece, centres)
                if centre is None:
                    print(f"unmatched message {label!r}", flush=True)
                    continue
                try:
                    pieces = _pieces(piece, months)
                except SkipMessage as exc:
                    print(f"skip message {centre.id}: {_brief(exc)}", flush=True)
                    continue
                for month, grid in pieces:
                    samples[centre.id].append({"system": piece_system, "month": month, "grid": grid})
                    print(f"message {centre.id} system {piece_system or '?'} {month:%Y-%m}", flush=True)
    finally:
        for dataset, _system in tagged:
            close = getattr(dataset, "close", None)
            if close is not None:
                close()
    chosen = {}
    for centre in centres:
        models = select_models(centre, samples[centre.id], months)
        if models:
            chosen[centre.id] = models
    return chosen


def land_mask(cache: Path) -> np.ndarray:
    if cache.exists():
        loaded = np.load(cache)
        mask = loaded["land"]
        if mask.shape == (NLAT, NLON):
            return mask.astype(np.uint8)
    import cartopy.io.shapereader as shapereader
    from shapely.geometry import Point
    from shapely.ops import unary_union
    from shapely.prepared import prep

    source = shapereader.natural_earth(resolution="50m", category="physical", name="land")
    land = prep(unary_union(list(shapereader.Reader(source).geometries())))
    mask = np.zeros((NLAT, NLON), dtype=np.uint8)
    for i, lat in enumerate(LATS):
        for j, lon in enumerate(LONS):
            x = float(lon if lon <= 180 else lon - 360)
            if land.contains(Point(x, float(lat))):
                mask[i, j] = 1
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, land=mask)
    return mask


def _cache_path(work: Path, init: date, field: Field) -> Path:
    return work / "ready" / f"{init:%Y-%m}_{field.id}.npz"


def _npz_text(value) -> str:
    if isinstance(value, np.ndarray):
        return str(value.item())
    return str(value)


def _load_ready(path: Path, init: date) -> dict | None:
    if not path.exists():
        return None
    loaded = np.load(path, allow_pickle=False)
    if _npz_text(loaded["init"]) != f"{init:%Y-%m}":
        return None
    return {
        "above": loaded["above"],
        "voted": loaded["voted"],
        "models": json.loads(_npz_text(loaded["models"])),
        "absent": json.loads(_npz_text(loaded["absent"])),
    }


def _save_ready(path: Path, init: date, above: np.ndarray, voted: np.ndarray, models: list[dict], absent: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        init=f"{init:%Y-%m}",
        above=above,
        voted=voted,
        models=json.dumps(models),
        absent=json.dumps(absent),
    )


def _open_client():
    import cdsapi

    try:
        return cdsapi.Client(quiet=True, progress=False)
    except TypeError:
        return cdsapi.Client()


def _no_centres(field: Field, init: date, detail: str) -> None:
    raise SystemExit(f"{field.name} returned no centres for {init:%Y-%m}. {detail}")


def fetch_field(client, field: Field, centres: tuple[Centre, ...], init: date, work: Path) -> dict:
    cached = _load_ready(_cache_path(work, init, field), init)
    if cached is not None:
        print(f"reuse {field.id} ({len(cached['models'])} models)", flush=True)
        return cached
    grib_dir = work / "grib" / field.id
    grib_dir.mkdir(parents=True, exist_ok=True)
    path = grib_dir / f"{field.id}.grib"
    request = field_request(field, centres, init)
    months = season_months(init)
    print(
        f"download {field.id} {len(request['originating_centre'])} centres "
        f"leads {','.join(request['leadtime_month'])}",
        flush=True,
    )
    try:
        retrieve(client, request, path)
        chosen = read_centres(path, centres, months)
    except Unavailable as exc:
        path.unlink(missing_ok=True)
        _no_centres(field, init, _brief(exc))
    except FatalCDS:
        path.unlink(missing_ok=True)
        raise
    above_rows = []
    voted_rows = []
    models = []
    absent = []
    for centre in centres:
        picked = chosen.get(centre.id) or []
        if not picked:
            absent.append(centre.name)
            print(f"skip {field.id} {centre.id}: not in the ensemble-mean file", flush=True)
            continue
        for item in picked:
            with np.errstate(invalid="ignore"):
                mean = np.nanmean(np.stack(item["grids"], axis=0), axis=0)
            above_row, voted_row = model_votes(field, mean)
            above_rows.append(above_row)
            voted_rows.append(voted_row)
            models.append({"id": centre.id, "name": item["name"], "system": item["system"]})
            print(f"kept {field.id} {centre.id} system {item['system'] or '?'}", flush=True)
    if not models:
        path.unlink(missing_ok=True)
        _no_centres(field, init, "the file had no complete centre")
    above = np.stack(above_rows, axis=0)
    voted = np.stack(voted_rows, axis=0)
    packed_above, packed_voted = close_empty_meridian(pack_bits(above), pack_bits(voted), above.shape[0])
    _save_ready(_cache_path(work, init, field), init, packed_above, packed_voted, models, absent)
    path.unlink(missing_ok=True)
    return {"above": packed_above, "voted": packed_voted, "models": models, "absent": absent}


def probe_fields(client, fields: tuple[Field, ...], centres: tuple[Centre, ...], init: date, work: Path) -> int:
    """Download one ensemble-mean file per variable and print which centres answered."""
    failures = 0
    work.mkdir(parents=True, exist_ok=True)
    months = season_months(init)
    for field in fields:
        target = work / f"probe_{field.id}.grib"
        try:
            retrieve(client, field_request(field, centres, init), target, attempts=2)
            chosen = read_centres(target, centres, months)
        except Unavailable as exc:
            print(f"NO {field.id}: {_brief(exc)}", flush=True)
            failures += 1
            continue
        except FatalCDS as exc:
            print(f"FATAL {field.id}: {_brief(exc)}", flush=True)
            return 1
        finally:
            target.unlink(missing_ok=True)
        kept = ", ".join(
            centre.id + ":" + "+".join(model["system"] or "?" for model in chosen[centre.id])
            for centre in centres
            if centre.id in chosen
        )
        print(f"OK {field.id} {kept or 'none'}", flush=True)
        if not chosen:
            failures += 1
    return failures


def build_payload(init: date, work: Path, client, fields: tuple[Field, ...], centres: tuple[Centre, ...]) -> dict:
    months = season_months(init)
    land = land_mask(work / "land_50m.npz")
    built = []
    summaries = {}
    for field in fields:
        ready = fetch_field(client, field, centres, init, work)
        above = ready["above"]
        voted = ready["voted"]
        sign, _, _ = majority(_unpack(above, len(ready["models"])), _unpack(voted, len(ready["models"])))
        summary = field_shares(sign, land)
        summary["models"] = len(ready["models"])
        summaries[field.id] = summary
        built.append({
            "id": field.id,
            "name": field.name,
            "above": field.above,
            "below": field.below,
            "phraseAbove": field.phrase_above,
            "phraseBelow": field.phrase_below,
            "colors": list(field.colors),
            "models": ready["models"],
            "absent": ready["absent"],
            "votesAbove": _b64(above),
            "votesCast": _b64(voted),
        })
    return {
        "init": f"{init:%Y-%m}",
        "period": period_label(months),
        "headline": headline_title(months),
        "months": [f"{item:%Y-%m}" for item in months],
        "grid": {"nlat": NLAT, "nlon": NLON},
        "land": _b64(land),
        "oceanStrength": OCEAN_STRENGTH,
        "fields": built,
        "story": story_lines(summaries),
    }


def _unpack(packed: np.ndarray, count: int) -> np.ndarray:
    mask = np.zeros((count, *packed.shape), dtype=bool)
    for index in range(count):
        mask[index] = (packed & np.uint16(1 << index)) != 0
    return mask


def _page_title(payload: dict) -> str:
    headline = payload.get("headline")
    if isinstance(headline, str) and headline.startswith("Climate headlines from "):
        return headline
    parsed = []
    for item in payload.get("months") or []:
        try:
            year, month = str(item).split("-")
            parsed.append(date(int(year), int(month), 1))
        except (ValueError, AttributeError):
            return "Climate headlines"
    if len(parsed) >= 2:
        return headline_title(parsed)
    return "Climate headlines"


def render_page(payload: dict) -> str:
    page = dict(payload)
    page["headline"] = _page_title(page)
    template = (ROOT / "lib" / "c3s_globes_page.html").read_text(encoding="utf-8")
    nav = _site_nav("/climate/headlines")
    seo = _seo("/climate/headlines", page["headline"])
    title = (
        page["headline"]
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        template.replace("__TITLE__", title)
        .replace("__SEO__", seo)
        .replace("__NAV__", nav)
    )


def _site_nav(current: str) -> str:
    def link(href: str, label: str) -> str:
        attr = ' aria-current="page"' if href == current else ""
        return f'<a href="{href}"{attr}>{label}</a>'

    lines = [
        '<details class="menu">',
        "<summary>Latest posts</summary>",
        '<div class="panel">',
        link("/latest_posts", "Latest posts"),
        link("/articles", "Articles"),
        link("/newsletter", "Newsletters"),
        "</div>",
        "</details>",
        '<details class="menu">',
        "<summary>Climate</summary>",
        '<div class="panel">',
        link("/climate/headlines", "Headlines"),
        '<details class="menu">',
        "<summary>Moisture</summary>",
        '<div class="panel">',
        link("/climate/moisture-trends", "Trends"),
        link("/climate/moisture-tracking", "Tracking"),
        "</div>",
        "</details>",
        link("/climate/oceans", "Oceans"),
        "</div>",
        "</details>",
        '<details class="menu">',
        "<summary>Weather</summary>",
        '<div class="panel">',
        '<details class="menu">',
        "<summary>Snow</summary>",
        '<div class="panel">',
        link("/weather/snow-anomaly", "Anomaly"),
        link("/weather/snow-forecast", "Forecast"),
        "</div>",
        "</details>",
        link("/weather/rain", "Precipitation"),
        '<details class="menu">',
        "<summary>Temperatures</summary>",
        '<div class="panel">',
        link("/weather/temperature-maximum", "Maximum"),
        link("/weather/temperature-minimum", "Minimum"),
        "</div>",
        "</details>",
        "</div>",
        "</details>",
        '<details class="menu">',
        "<summary>Graphics</summary>",
        '<div class="panel">',
        '<details class="menu">',
        "<summary>Long range</summary>",
        '<div class="panel">',
        link("/graphics/copernicus", "Copernicus"),
        link("/graphics/snow", "Snow"),
        link("/graphics/nmme", "NMME"),
        "</div>",
        "</details>",
        link("/graphics/moisture", "Moisture"),
        '<details class="menu">',
        "<summary>DeepMind</summary>",
        '<div class="panel">',
        link("/graphics/deepmind", "Storm cards"),
        link("/graphics/hurricane-bot", "Hurricane bot"),
        "</div>",
        "</details>",
        link("/graphics/polar-vortex", "Polar vortex"),
        link("/graphics/climate-stuff", "Climate stuff"),
        "</div>",
        "</details>",
        """<script>
    (function () {
      var nav = document.currentScript.closest("nav");
      document.addEventListener("click", function (event) {
        nav.querySelectorAll("details[open]").forEach(function (menu) {
          if (!menu.contains(event.target)) menu.open = false;
        });
      });
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        nav.querySelectorAll("details[open]").forEach(function (menu) { menu.open = false; });
      });
    })();
    </script>""",
    ]
    inner = "\n".join(f"      {line}" for line in lines)
    return f'<nav aria-label="Sections">\n{inner}\n    </nav>'


def _seo(path: str, title: str) -> str:
    description = "Unique weather and climate graphics and insights from meteorologist Ben Noll."
    canonical = "https://benweather.com" + path
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "name": "BenNollWeather", "url": "https://benweather.com/", "description": description},
            {
                "@type": "Person",
                "name": "Ben Noll",
                "jobTitle": "Meteorologist",
                "email": "bennollweather@gmail.com",
                "url": "https://benweather.com/",
                "sameAs": [
                    "https://x.com/BenNollWeather",
                    "https://www.bennollsays.com",
                    "https://www.washingtonpost.com/people/ben-noll/",
                ],
            },
        ],
    }
    payload = json.dumps(graph, separators=(",", ":")).replace("<", "\\u003c")

    def esc(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    return "\n  ".join([
        f'<meta name="description" content="{esc(description)}">',
        '<meta name="robots" content="index,follow">',
        f'<link rel="canonical" href="{esc(canonical)}">',
        '<meta property="og:site_name" content="BenNollWeather">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{esc(title)}">',
        f'<meta property="og:description" content="{esc(description)}">',
        f'<meta property="og:url" content="{esc(canonical)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{esc(title)}">',
        f'<meta name="twitter:description" content="{esc(description)}">',
        f'<script type="application/ld+json">{payload}</script>',
    ])


def _select(items, names: str, label: str):
    wanted = {item.strip() for item in names.split(",") if item.strip()}
    if not wanted:
        return items
    chosen = tuple(item for item in items if item.id in wanted)
    missing = wanted - {item.id for item in chosen}
    if missing:
        raise SystemExit(f"Unknown {label}: {', '.join(sorted(missing))}")
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the seasonal outlook globes.")
    parser.add_argument("--init", default=os.environ.get("TARGET_MONTH", ""), help="Initialization month YYYY-MM.")
    parser.add_argument("--today", default="", help="Override the calendar date used when --init is blank.")
    parser.add_argument("--work", default="", help="Directory for GRIB files and the finished field cache.")
    parser.add_argument("--html", default="", help="Where to write the page.")
    parser.add_argument("--json", default="", help="Where to write the data file.")
    parser.add_argument("--only", default="", help="Comma-separated field ids.")
    parser.add_argument("--centres", default="", help="Comma-separated centre ids.")
    parser.add_argument("--probe", action="store_true", help="Download lead 2 only and print which systems answer.")
    args = parser.parse_args(argv)

    today = parse_day(args.today) if args.today.strip() else datetime.now(timezone.utc).date()
    init = resolve_init(today, args.init)
    fields = _select(FIELDS, args.only, "field")
    centres = _select(CENTRES, args.centres, "centre")
    work = Path(args.work or os.environ.get("WORK_ROOT") or "/tmp/monthly-updates/c3s-globes").expanduser()
    work.mkdir(parents=True, exist_ok=True)
    print(f"init {init:%Y-%m} period {period_label(season_months(init))}", flush=True)
    try:
        client = _open_client()
    except Exception as exc:
        print(f"Could not open the CDS client: {_brief(exc)}", file=sys.stderr)
        return 1
    try:
        if args.probe:
            return probe_fields(client, fields, centres, init, work / "probe")
        payload = build_payload(init, work, client, fields, centres)
    except FatalCDS as exc:
        print(str(exc), file=sys.stderr)
        return 1
    html_path = Path(args.html or work / "index.html")
    json_path = Path(args.json or work / "data.json")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(render_page(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    print(f"page written {html_path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as exc:
        code = exc.code
        if code is None:
            code = 0
        if code == NOT_READY_EXIT or code == str(NOT_READY_EXIT):
            raise SystemExit(NOT_READY_EXIT)
        raise
