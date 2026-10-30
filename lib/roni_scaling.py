"""Month-of-year factors that put a relative Niño 3.4 index on the traditional scale.

The experimental RONI chart divides each calendar month's traditional Niño 3.4
standard deviation by the standard deviation of (Niño 3.4 anomaly − the raw
tropical-mean SST). A forecast relative anomaly is multiplied by that month's
factor. The relative index subtracts the raw tropical mean, not the tropical
anomaly. ERSST latitudes run from north to south, so the slices start at the
northern edge.
"""

from __future__ import annotations

import ssl
from pathlib import Path
from shutil import copyfileobj
from urllib.request import urlopen

ERSST_URL = "https://downloads.psl.noaa.gov/Datasets/noaa.ersst.v5/sst.mnmean.nc"
CLIM_START = "1991-01-01"
CLIM_END = "2020-12-01"
VARIANCE_START = "1950-01-01"
VARIANCE_END = "2025-12-01"


def download_ersst(dest: Path) -> Path:
    """Download NOAA ERSST v5 next to the other disposable work files."""
    dest = Path(dest)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    context = ssl._create_unverified_context()
    with urlopen(ERSST_URL, context=context) as response, partial.open("wb") as handle:
        copyfileobj(response, handle)
    partial.replace(dest)
    return dest


def nino34_scaling_factors(dataset):
    """Return one factor per calendar month, named ``nino34`` and indexed by month."""
    field = dataset["sst"]
    tropav = (
        field.sel(lat=slice(20, -20), lon=slice(0, 360))
        .mean(dim=("lat", "lon"))
    )
    nino34 = field.sel(lat=slice(5, -5), lon=slice(190, 240)).mean(dim=("lat", "lon"))
    clm = nino34.sel(time=slice(CLIM_START, CLIM_END)).groupby("time.month").mean("time")
    nino34a = nino34.groupby("time.month") - clm
    # Raw tropical mean, matching the experimental RONI chart.
    diff_idx = nino34a - tropav
    window = slice(VARIANCE_START, VARIANCE_END)
    factors = nino34a.sel(time=window).groupby("time.month").std("time") / diff_idx.sel(
        time=window
    ).groupby("time.month").std("time")
    factors.name = "nino34"
    return factors.load()


def scale_by_calendar_month(values, months, factors):
    """Multiply each value by the factor for that calendar month (1-12)."""
    lookup = {
        int(month): float(factors.sel(month=int(month)).values)
        for month in factors["month"].values
    }
    return [float(value) * lookup[int(month)] for value, month in zip(values, months)]
