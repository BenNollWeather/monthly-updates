#!/usr/bin/env python3
"""Wait for the one month a product is supposed to publish.

ERA5 extremes and precipitable water need the month that just ended.
NMME, C3S, and ECMWF seasonal need the forecast issued in the current month.

A GitHub-hosted job cannot stay alive for the whole month, so one run checks
for a few hours and, when the data is still missing, dispatches another run.
Retries stop at the start of the next calendar slot so a later run cannot
publish the following month under this cycle.
"""

from __future__ import annotations

import argparse
import os
import shutil
import ssl
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

NOT_READY_EXIT = 75

# CDS uses these phrases when the requested month has not been published.
_NO_DATA_PATTERNS = (
    "no data",
    "nodata",
    "not available",
    "not yet available",
    "is not available yet",
    "valid combination",
    "none of the data",
    "empty",
)
_FATAL_PATTERNS = (
    "invalid api key",
    "api key",
    "authentication",
    "not authorized",
    "unauthorized",
    "401",
)

ERA5_MONTHLY_DATASET = "reanalysis-era5-single-levels-monthly-means"
SEASONAL_DATASET = "seasonal-postprocessed-single-levels"
C3S_CENTRES = (
    "cmcc",
    "dwd",
    "eccc",
    "ecmwf",
    "jma",
    "meteo_france",
    "ncep",
    "ukmo",
    "bom",
)

# kind previous: the month that just ended. kind current: this month's forecast.
PRODUCTS = {
    "era5-extremes": {"kind": "previous", "probe": "era5", "label": "ERA5 extremes"},
    "era5-pwat": {"kind": "previous", "probe": "era5", "label": "ERA5 precipitable water"},
    "nmme": {"kind": "current", "probe": "nmme", "label": "NMME"},
    "c3s": {"kind": "current", "probe": "c3s", "label": "C3S"},
    "ecmwf-seasonal": {"kind": "current", "probe": "ecmwf", "label": "ECMWF seasonal"},
}


class FatalReleaseError(RuntimeError):
    """The check cannot succeed by waiting, for example a rejected API key."""


class TransientReleaseError(RuntimeError):
    """The check failed for a reason that may clear on a later attempt."""


@dataclass(frozen=True)
class AttemptPlan:
    action: str
    sleep_seconds: int = 0
    message: str = ""


@dataclass(frozen=True)
class WaitResult:
    action: str
    target: date
    retry_until: datetime
    message: str


def exit_not_ready(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(NOT_READY_EXIT)


def is_not_ready(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(pattern in message for pattern in _NO_DATA_PATTERNS)


def is_fatal(exc: BaseException) -> bool:
    message = str(exc).lower()
    return any(pattern in message for pattern in _FATAL_PATTERNS)


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
        raise SystemExit(f"Invalid target month {value!r}; expected YYYY-MM") from exc


def format_month(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def default_target(kind: str, today: date) -> date:
    if kind == "previous":
        year, month = add_months(today.year, today.month, -1)
        return date(year, month, 1)
    if kind != "current":
        raise ValueError(f"Unknown release kind {kind!r}")
    return date(today.year, today.month, 1)


def retry_deadline(kind: str, target: date) -> datetime:
    """UTC instant when this target is no longer the month the product should publish."""
    extra = 2 if kind == "previous" else 1
    year, month = add_months(target.year, target.month, extra)
    return datetime(year, month, 1, tzinfo=timezone.utc)


def month_label(value: date) -> str:
    return value.strftime("%B %Y")


def plan_attempt(
    *,
    ready: bool,
    bug_strikes: int,
    now: datetime,
    started: datetime,
    deadline: datetime,
    interval: timedelta,
    max_wait: timedelta,
    job_timeout: timedelta,
    process_budget: timedelta,
    wait_enabled: bool,
    slept: bool,
    final_check: bool,
    label: str,
    target: date,
) -> AttemptPlan:
    """Decide whether to process, keep sleeping, hand off to a new run, or stop."""
    product_month = f"{label} for {month_label(target)}"
    elapsed = now - started
    remaining = job_timeout - elapsed
    if bug_strikes >= 3:
        return AttemptPlan("error", message=f"The availability check for {product_month} failed repeatedly.")
    if ready and (not slept or remaining >= process_budget):
        return AttemptPlan("process", message=f"{product_month} is available.")
    if ready:
        return AttemptPlan(
            "requeue",
            message=f"{product_month} is available. Starting a fresh run with a full time limit.",
        )
    if not wait_enabled or final_check or now >= deadline:
        return AttemptPlan(
            "give_up",
            message=(
                f"{product_month} was still unavailable at {deadline:%Y-%m-%d %H:%M UTC}, "
                "when this cycle stops so the next month is not published early."
            ),
        )
    next_check = now + interval
    if elapsed + interval > max_wait or remaining - interval < timedelta(minutes=10):
        return AttemptPlan(
            "requeue",
            message=f"{product_month} is not available yet. The next run will check again.",
        )
    if next_check >= deadline:
        pause = max(0, int((deadline - now).total_seconds()))
        return AttemptPlan(
            "sleep",
            sleep_seconds=pause,
            message=f"{product_month} is not available yet. Checking once more at the end of this cycle.",
        )
    minutes = max(1, int(interval.total_seconds() // 60))
    return AttemptPlan(
        "sleep",
        sleep_seconds=int(interval.total_seconds()),
        message=f"{product_month} is not available yet. Checking again in {minutes} minutes.",
    )


def run_wait(
    probe,
    *,
    kind: str,
    label: str,
    target: date,
    clock,
    sleeper,
    interval: timedelta,
    max_wait: timedelta,
    job_timeout: timedelta,
    process_budget: timedelta,
    wait_enabled: bool,
    startup_delay: timedelta = timedelta(0),
) -> WaitResult:
    deadline = retry_deadline(kind, target)
    started = clock()

    def finish(action: str, message: str) -> WaitResult:
        print(message)
        return WaitResult(action, target, deadline, message)

    if startup_delay.total_seconds() > 0 and wait_enabled:
        remaining = (deadline - clock()).total_seconds()
        pause = int(min(startup_delay.total_seconds(), max(0, remaining)))
        if pause > 0:
            print(f"Pausing {pause} seconds before checking {label} for {month_label(target)}.")
            sleeper(pause)
        if clock() >= deadline:
            return finish(
                "give_up",
                f"{label} for {month_label(target)} reached the end of its retry window.",
            )

    slept = False
    bug_strikes = 0
    final_next = False
    while True:
        now = clock()
        if now >= deadline and not final_next:
            return finish(
                "give_up",
                f"{label} for {month_label(target)} reached the end of its retry window.",
            )
        ready = False
        try:
            ready = bool(probe())
            bug_strikes = 0
        except FatalReleaseError as exc:
            return finish("error", f"{label} cannot check {month_label(target)}: {exc}")
        except TransientReleaseError as exc:
            print(f"Availability check failed and will be retried: {exc}")
            ready = False
        except Exception as exc:
            bug_strikes += 1
            print(f"Availability check error ({bug_strikes}/3): {exc}")
            ready = False

        now = clock()
        if ready and kind == "current" and date(now.year, now.month, 1) != date(target.year, target.month, 1):
            return finish(
                "give_up",
                f"{label} is locked to {month_label(target)}, and the UTC month is now {now:%B %Y}.",
            )
        if now >= deadline and not ready:
            return finish(
                "give_up",
                f"{label} for {month_label(target)} reached the end of its retry window.",
            )

        plan = plan_attempt(
            ready=ready,
            bug_strikes=bug_strikes,
            now=now,
            started=started,
            deadline=deadline,
            interval=interval,
            max_wait=max_wait,
            job_timeout=job_timeout,
            process_budget=process_budget,
            wait_enabled=wait_enabled,
            slept=slept,
            final_check=final_next,
            label=label,
            target=target,
        )
        if plan.action != "sleep":
            return finish(plan.action, plan.message)
        print(plan.message)
        sleeper(plan.sleep_seconds)
        slept = True
        final_next = now + timedelta(seconds=plan.sleep_seconds) >= deadline


def _times_in_download(path: Path):
    import zipfile

    import numpy as np
    import pandas as pd
    import xarray as xr

    nc_paths: list[Path]
    tmpdir = None
    if zipfile.is_zipfile(path):
        tmpdir = tempfile.TemporaryDirectory()
        with zipfile.ZipFile(path) as archive:
            archive.extractall(tmpdir.name)
        nc_paths = sorted(Path(tmpdir.name).rglob("*.nc"))
    else:
        nc_paths = [path]
    times: list[pd.Timestamp] = []
    try:
        for nc_path in nc_paths:
            with xr.open_dataset(nc_path) as dataset:
                for name in ("valid_time", "time"):
                    if name in dataset.coords or name in dataset.variables:
                        values = pd.to_datetime(np.asarray(dataset[name].values).ravel())
                        times.extend(value for value in values if not pd.isna(value))
                        break
    finally:
        if tmpdir is not None:
            tmpdir.cleanup()
    return times


def era5_month_available(client, year: int, month: int, probe_dir: Path, attempts: int = 2, sleep_seconds: int = 15) -> bool:
    """Return True when the ERA5 monthly mean for this year and month is on CDS."""
    probe_dir.mkdir(parents=True, exist_ok=True)
    target = probe_dir / f"probe_{year}_{month:02d}.nc"
    request = {
        "product_type": ["monthly_averaged_reanalysis"],
        "variable": ["2m_temperature"],
        "year": [str(year)],
        "month": [f"{month:02d}"],
        "time": ["00:00"],
        "area": [1, 0, 0, 1],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }
    for attempt in range(1, attempts + 1):
        if target.exists():
            target.unlink()
        try:
            client.retrieve(ERA5_MONTHLY_DATASET, request).download(str(target))
            times = _times_in_download(target)
            return any(stamp.year == year and stamp.month == month for stamp in times)
        except FatalReleaseError:
            raise
        except Exception as exc:
            if is_fatal(exc):
                raise FatalReleaseError(str(exc)) from exc
            if is_not_ready(exc):
                return False
            print(f"Availability probe for {year}-{month:02d} failed (attempt {attempt}/{attempts}): {exc}")
            if attempt < attempts:
                time.sleep(sleep_seconds)
            else:
                raise TransientReleaseError(str(exc)) from exc
        finally:
            if target.exists():
                target.unlink()
    return False


def _model_versions() -> dict:
    path = Path(__file__).resolve().parents[1] / "operational_bundle" / "config" / "model_versions.json"
    import json

    return json.loads(path.read_text())


def seasonal_month_available(kind: str, year: int, month: int) -> bool:
    """Return True when this month's seasonal SST anomaly can be retrieved."""
    import cdsapi

    versions = _model_versions()
    if kind == "ecmwf":
        centres = "ecmwf"
        system = versions["ecmwf"]["system"]
    elif kind == "c3s":
        centres = list(C3S_CENTRES)
        system = versions["c3s"]["multi_model_systems"]
    else:
        raise FatalReleaseError(f"Unknown seasonal probe {kind!r}")
    request = {
        "originating_centre": centres,
        "system": system,
        "variable": "sea_surface_temperature_anomaly",
        "product_type": "ensemble_mean",
        "year": f"{year}",
        "month": f"{month:02d}",
        "leadtime_month": "1",
        "format": "grib",
    }
    target_dir = Path(tempfile.mkdtemp(prefix="seasonal-probe-"))
    target = target_dir / "probe.grib"
    try:
        cdsapi.Client().retrieve(SEASONAL_DATASET, request, str(target))
        return target.exists() and target.stat().st_size > 0
    except Exception as exc:
        if is_fatal(exc):
            raise FatalReleaseError(str(exc)) from exc
        if is_not_ready(exc):
            return False
        raise TransientReleaseError(str(exc)) from exc
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def nmme_month_available(year: int, month: int) -> bool:
    """Return True when this month's NMME ensemble-mean files are on CPC."""
    stamp = f"{year}{month:02d}"
    run = f"{stamp}0800"
    base = f"https://ftp.cpc.ncep.noaa.gov/NMME/realtime_anom/ENSMEAN/{run}"
    names = (
        f"NMME.tmpsfc.{stamp}.ENSMEAN.anom.nc",
        f"NMME.prate.{stamp}.ENSMEAN.anom.nc",
        f"NMME.tmp2m.{stamp}.ENSMEAN.anom.nc",
    )
    context = ssl._create_unverified_context()
    for name in names:
        url = f"{base}/{name}"
        request = Request(url, method="GET", headers={"Range": "bytes=0-0"})
        try:
            with urlopen(request, context=context, timeout=120) as response:
                if getattr(response, "status", 200) >= 400:
                    return False
                response.read(1)
        except HTTPError as exc:
            if exc.code == 404:
                return False
            raise TransientReleaseError(f"{url} returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise TransientReleaseError(f"{url} could not be reached: {exc}") from exc
    return True


def build_probe(product_id: str, target: date):
    spec = PRODUCTS[product_id]

    def probe() -> bool:
        print(f"Checking {spec['label']} for {month_label(target)} ...")
        if spec["probe"] == "era5":
            import cdsapi

            probe_dir = Path(tempfile.mkdtemp(prefix="era5-probe-"))
            try:
                return era5_month_available(cdsapi.Client(), target.year, target.month, probe_dir)
            finally:
                shutil.rmtree(probe_dir, ignore_errors=True)
        if spec["probe"] == "nmme":
            return nmme_month_available(target.year, target.month)
        return seasonal_month_available(spec["probe"], target.year, target.month)

    return probe


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return int(raw)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def write_github_output(path: str, values: dict[str, str]) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={str(value).replace(chr(10), ' ')}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wait until a monthly release is available.")
    parser.add_argument("--product", required=True, choices=sorted(PRODUCTS))
    parser.add_argument("--target-month", default=os.environ.get("TARGET_MONTH", ""))
    parser.add_argument("--interval-seconds", type=int, default=_env_int("DATA_WAIT_INTERVAL_SECONDS", 1800))
    parser.add_argument("--max-wait-minutes", type=int, default=_env_int("DATA_MAX_WAIT_MINUTES", 240))
    parser.add_argument("--job-timeout-minutes", type=int, default=_env_int("DATA_JOB_TIMEOUT_MINUTES", 360))
    parser.add_argument("--process-budget-minutes", type=int, default=_env_int("DATA_PROCESS_BUDGET_MINUTES", 60))
    parser.add_argument("--startup-delay-seconds", type=int, default=_env_int("STARTUP_DELAY_SECONDS", 0))
    parser.add_argument("--wait", default=os.environ.get("WAIT_FOR_DATA", "true"))
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args(argv)

    spec = PRODUCTS[args.product]
    today = datetime.now(timezone.utc).date()
    target = parse_month(args.target_month) if args.target_month.strip() else default_target(spec["kind"], today)
    result = run_wait(
        build_probe(args.product, target),
        kind=spec["kind"],
        label=spec["label"],
        target=target,
        clock=lambda: datetime.now(timezone.utc),
        sleeper=time.sleep,
        interval=timedelta(seconds=args.interval_seconds),
        max_wait=timedelta(minutes=args.max_wait_minutes),
        job_timeout=timedelta(minutes=args.job_timeout_minutes),
        process_budget=timedelta(minutes=args.process_budget_minutes),
        wait_enabled=_truthy(args.wait),
        startup_delay=timedelta(seconds=max(0, args.startup_delay_seconds)),
    )
    write_github_output(
        args.github_output,
        {
            "action": result.action,
            "target_month": format_month(result.target),
            "retry_until": result.retry_until.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "message": result.message,
        },
    )
    return 0 if result.action in {"process", "requeue", "give_up", "error"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
