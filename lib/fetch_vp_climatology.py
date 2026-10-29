"""Download the published velocity-potential climatology.

Each ECMWF seasonal run needs the current month and the next five. The files
are the published vp_clim_Mon.nc set. They stay in the work directory and are
deleted with it after the maps are drawn.
"""

from __future__ import annotations

import os
import shutil
import ssl
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

DEFAULT_URL = "https://bennollweather.s3.amazonaws.com/climate_imagery/climo/vp"
MONTHS = (
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
_NETCDF_MAGIC = (b"CDF", b"\x89HDF")


def forecast_month_names(today: date | None = None) -> list[str]:
    """Calendar months for leads 1 through 6, starting with today."""
    if today is None:
        today = date.today()
    start = today.month - 1
    return [MONTHS[(start + offset) % 12] for offset in range(6)]


def fetch(out_dir: Path, months: list[str], base_url: str = DEFAULT_URL, read_url=None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for month in months:
        if month not in MONTHS:
            raise SystemExit(f"Unknown climatology month {month!r}. Expected one of {', '.join(MONTHS)}.")
        target = out_dir / f"vp_clim_{month}.nc"
        if _is_netcdf(target):
            print(f"Using existing velocity-potential climatology {target.name}.")
            written.append(target)
            continue
        url = f"{base_url.rstrip('/')}/vp_clim_{month}.nc"
        print(f"Downloading {url}")
        payload = _read(url) if read_url is None else read_url(url)
        _write_netcdf(target, payload, url)
        written.append(target)
    return written


def _read(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "monthly-updates"})
    try:
        with _opener().open(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Climatology file was not available ({exc.code}): {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Climatology download failed: {url} ({exc.reason})") from exc


def _opener() -> urllib.request.OpenerDirector:
    if os.environ.get("PYTHONHTTPSVERIFY", "1") == "0":
        context = ssl._create_unverified_context()
        return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))
    return urllib.request.build_opener()


def _write_netcdf(target: Path, payload: bytes, url: str) -> None:
    if not payload.startswith(_NETCDF_MAGIC) or len(payload) < 1024:
        raise SystemExit(f"Climatology download was not a NetCDF file: {url}")
    temporary = target.with_suffix(".partial")
    try:
        temporary.write_bytes(payload)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _is_netcdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size < 1024:
        return False
    with path.open("rb") as handle:
        return handle.read(8).startswith(_NETCDF_MAGIC)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Download the velocity-potential climatology.")
    parser.add_argument("--out", required=True, help="Directory for vp_clim_Mon.nc files")
    parser.add_argument("--url", default=None, help="Base URL of the published files")
    parser.add_argument(
        "--months",
        default="",
        help="Comma-separated abbreviations such as Oct,Nov. Defaults to the current month and the next five.",
    )
    args = parser.parse_args()
    base_url = args.url or os.environ.get("VP_CLIMO_URL", DEFAULT_URL)
    if args.months.strip():
        months = [item.strip() for item in args.months.split(",") if item.strip()]
    else:
        months = forecast_month_names()
    written = fetch(Path(args.out), months, base_url)
    print(f"Velocity-potential climatology ready: {', '.join(path.name for path in written)}.")


if __name__ == "__main__":
    main()
