#!/usr/bin/env python3
"""Moisture trends requests, annual means, and page. These do not call CDS."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from lib.moisture_trends import (
    FLUX_VARIABLES,
    GROUPS,
    PWAT_VARIABLE,
    annual_fields,
    annual_pair,
    build_requests,
    download_groups,
    end_year,
    pack_grid,
    render_page,
    unpack_grid,
)


def _field(values, times, lat, lon, name: str) -> xr.DataArray:
    return xr.DataArray(
        np.asarray(values, dtype=np.float32),
        dims=("time", "latitude", "longitude"),
        coords={"time": list(times), "latitude": lat, "longitude": lon},
        name=name,
    )


def _sample_netcdf(path: Path, years, variables) -> None:
    times = [
        pd.Timestamp(year=int(year), month=month, day=1)
        for year in years
        for month in range(1, 13)
    ]
    shape = (len(times), 2, 2)
    data_vars = {}
    for name in variables:
        if name == PWAT_VARIABLE:
            fill = 25.4
        elif "eastward" in name:
            fill = 3.0
        else:
            fill = 4.0
        data_vars[name] = (("time", "latitude", "longitude"), np.full(shape, fill, dtype=np.float32))
    dataset = xr.Dataset(
        data_vars,
        coords={
            "time": times,
            "latitude": np.array([90.0, 89.0]),
            "longitude": np.array([0.0, 359.0]),
        },
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(path)


class MoistureRequestTests(unittest.TestCase):
    def test_end_year_is_the_previous_calendar_year(self) -> None:
        self.assertEqual(end_year(date(2027, 1, 9)), 2026)
        self.assertEqual(end_year(date(2026, 11, 4)), 2025)

    def test_one_download_for_pwat_and_one_for_ivt(self) -> None:
        pwat, flux = build_requests(1940, 2025)
        self.assertEqual([name for name, _ in GROUPS], ["pwat", "flux"])
        self.assertEqual(pwat["variable"], [PWAT_VARIABLE])
        self.assertEqual(flux["variable"], list(FLUX_VARIABLES))
        self.assertEqual(pwat["year"], [str(year) for year in range(1940, 2026)])
        self.assertEqual(pwat["month"], [f"{month:02d}" for month in range(1, 13)])
        self.assertEqual(pwat["time"], ["00:00"])
        self.assertEqual(pwat["product_type"], ["monthly_averaged_reanalysis"])
        self.assertEqual(pwat["data_format"], "netcdf")
        self.assertEqual(pwat["download_format"], "unarchived")
        self.assertEqual(pwat["grid"], [1.0, 1.0])
        for key, value in pwat.items():
            if key != "variable":
                self.assertEqual(flux[key], value)
        joined = " ".join(pwat["variable"] + flux["variable"])
        self.assertNotIn("total_precipitation", joined)
        self.assertNotIn("precip", joined)

    def test_full_span_is_two_files(self) -> None:
        calls = []

        def retrieve(_client, request, target):
            calls.append(list(request["variable"]))
            _sample_netcdf(Path(target), request["year"], request["variable"])

        with tempfile.TemporaryDirectory() as tmp:
            paths = download_groups(object(), Path(tmp), 2020, 2021, retrieve=retrieve)
            inches, transport = annual_fields(paths["pwat"], paths["flux"], 2020, 2021)
        self.assertEqual(calls, [[PWAT_VARIABLE], list(FLUX_VARIABLES)])
        self.assertAlmostEqual(float(inches[0, 0, 0]), 1.0, places=2)
        self.assertAlmostEqual(float(transport[0, 0, 0]), 5.0, places=2)

    def test_an_oversized_request_splits_without_mixing_the_fields(self) -> None:
        calls = []

        def retrieve(_client, request, target):
            if len(request["year"]) > 2:
                raise RuntimeError("cost limits exceeded: Your request is too large")
            calls.append((tuple(request["variable"]), tuple(request["year"]), tuple(request["month"])))
            _sample_netcdf(Path(target), request["year"], request["variable"])

        with tempfile.TemporaryDirectory() as tmp:
            paths = download_groups(object(), Path(tmp), 2020, 2023, retrieve=retrieve)
            inches, transport = annual_fields(paths["pwat"], paths["flux"], 2020, 2023)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0][0], (PWAT_VARIABLE,))
        self.assertEqual(calls[1][0], (PWAT_VARIABLE,))
        self.assertEqual(calls[2][0], FLUX_VARIABLES)
        self.assertEqual(calls[3][0], FLUX_VARIABLES)
        self.assertEqual(calls[0][1], ("2020", "2021"))
        self.assertEqual(calls[1][1], ("2022", "2023"))
        self.assertTrue(all(len(months) == 12 for _, _, months in calls))
        self.assertTrue(all("total_precipitation" not in names for names, _, _ in calls))
        self.assertAlmostEqual(float(inches[3, 0, 359]), 1.0, places=2)
        self.assertAlmostEqual(float(transport[3, 1, 0]), 5.0, places=2)


class MoistureGridTests(unittest.TestCase):
    def test_inches_and_nearest_cell(self) -> None:
        times = pd.date_range("2024-01-01", periods=12, freq="MS")
        pwat = _field(np.full((12, 1, 1), 25.4), times, [42.0], [-74.0], PWAT_VARIABLE)
        east = _field(np.full((12, 1, 1), 3.0), times, [42.0], [-74.0], FLUX_VARIABLES[0])
        north = _field(np.full((12, 1, 1), 4.0), times, [42.0], [-74.0], FLUX_VARIABLES[1])
        inches, transport = annual_pair(pwat, east, north, 2024, 2024)
        self.assertAlmostEqual(float(inches[0, 48, 286]), 1.0, places=5)
        self.assertAlmostEqual(float(transport[0, 48, 286]), 5.0, places=5)
        self.assertTrue(np.isnan(inches[0, 0, 0]))
        blob = pack_grid(inches, transport, 2024, 2024)
        packed = unpack_grid(blob)
        self.assertEqual(packed["start"], 2024)
        self.assertEqual(packed["end"], 2024)
        self.assertEqual(int(packed["pwat"][0, 48, 286]), 100)
        self.assertEqual(int(packed["ivt"][0, 48, 286]), 5)
        self.assertEqual(int(packed["pwat"][0, 0, 0]), 65535)

    def test_ivt_is_the_mean_of_monthly_magnitudes(self) -> None:
        times = pd.date_range("2024-01-01", periods=12, freq="MS")
        east_values = np.zeros((12, 1, 1), dtype=np.float32)
        north_values = np.zeros((12, 1, 1), dtype=np.float32)
        east_values[:6, 0, 0] = 10
        north_values[6:, 0, 0] = 10
        pwat = _field(np.full((12, 1, 1), 25.4), times, [42.0], [286.0], PWAT_VARIABLE)
        east = _field(east_values, times, [42.0], [286.0], FLUX_VARIABLES[0])
        north = _field(north_values, times, [42.0], [286.0], FLUX_VARIABLES[1])
        _, transport = annual_pair(pwat, east, north, 2024, 2024)
        self.assertAlmostEqual(float(transport[0, 48, 286]), 10.0, places=4)

    def test_a_missing_month_stops(self) -> None:
        times = pd.date_range("2024-01-01", periods=11, freq="MS")
        pwat = _field(np.full((11, 1, 1), 25.4), times, [42.0], [286.0], PWAT_VARIABLE)
        east = _field(np.ones((11, 1, 1)), times, [42.0], [286.0], FLUX_VARIABLES[0])
        north = _field(np.ones((11, 1, 1)), times, [42.0], [286.0], FLUX_VARIABLES[1])
        with self.assertRaises(SystemExit) as caught:
            annual_pair(pwat, east, north, 2024, 2024)
        self.assertEqual(caught.exception.code, 75)


class MoisturePageTests(unittest.TestCase):
    def test_page_names_the_place_the_logo_and_the_average(self) -> None:
        html = render_page()
        self.assertIn('href="/climate/moisture-trends" aria-current="page">Trends</a>', html)
        self.assertIn('href="/climate/moisture-tracking">Tracking</a>', html)
        self.assertIn("<summary>Climate</summary>", html)
        self.assertIn("<summary>Moisture</summary>", html)
        self.assertIn('href="/climate/headlines">Headlines</a>', html)
        self.assertIn("<summary>Weather</summary>", html)
        self.assertLess(
            html.index('href="/climate/headlines">Headlines</a>'),
            html.index("<summary>Moisture</summary>"),
        )
        self.assertLess(
            html.index("<summary>Moisture</summary>"),
            html.index('href="/climate/oceans">Oceans</a>'),
        )
        self.assertLess(
            html.index("<summary>Moisture</summary>"),
            html.index("<summary>Graphics</summary>"),
        )
        self.assertIn("See how atmospheric moisture has changed around the world.", html)
        self.assertNotIn('class="subnav"', html)
        self.assertLess(html.index('id="title"'), html.index('class="lede"'))
        self.assertLess(html.index('class="lede"'), html.index('id="finder"'))
        self.assertIn("if (GLOBAL)", html)
        self.assertIn('"start":1940', html)
        boot = html.split("function boot()", 1)[1]
        opened = boot.split("if (GLOBAL)", 1)[1].split("} else {", 1)[0]
        self.assertIn("paint();", opened)
        self.assertNotIn("data.bin", opened)
        self.assertLess(html.index('id="finder"'), html.index('id="story"'))
        self.assertIn("Moisture trends", html)
        self.assertIn("Trend since 1940", html)
        self.assertEqual(html.lower().count("since 1940"), 2)
        self.assertIn('fillText("Average"', html)
        self.assertNotIn('fillText("1991–2020"', html)
        self.assertIn("Trend from ${record.start} to ${record.end}", html)
        self.assertIn('"% above average"', html)
        self.assertIn('"% below average"', html)
        self.assertIn('"Rank " + rank.place + " of " + rank.count', html)
        self.assertNotIn('"Rank: "', html)
        self.assertIn('fillText("Trend line"', html)
        self.assertIn('text + " in " + year', html)
        self.assertIn("yOf(line.end), 4.5", html)
        self.assertNotIn("yOf(anomalies[last])", html)
        self.assertIn("function bandWeight", html)
        self.assertIn("Math.sin(north) - Math.sin(south)", html)
        self.assertNotIn('record.start + "–" + record.end', html)
        self.assertNotIn("GeoNames", html)
        self.assertIn("drawImage(image, size - pad - logoW, pad, logoW, logoH)", html)
        self.assertIn("/moisture-trends/data.bin", html)
        self.assertIn("/climate/cities.json", html)
        self.assertIn("are derived from the ECMWF/ERA5 atmospheric reanalysis, sourced from the Copernicus Climate Change Service.", html)
        self.assertIn("The charts compare conditions each year to the 1991–2020 average and show the linear trend since 1940. Higher moisture levels can increase the risk for extreme rainfall.", html)
        self.assertNotIn("above the 1991–2020 average", html)
        self.assertIn("(value / mean - 1) * 100", html)
        self.assertIn('name: "Global"', html)
        self.assertIn("else showGlobal();", html)
        self.assertIn("rgba(92, 174, 114, 0.34)", html)
        self.assertIn("rgba(180, 134, 78, 0.32)", html)
        self.assertIn('return "+" + rounded + "%"', html)
        self.assertIn("\\u2212", html)
        self.assertIn("width - captionW - dotR - 6", html)
        self.assertNotIn("flat since 1940", html)
        self.assertNotIn('toFixed(2) + " in"', html)
        self.assertIn("moisture-trends-", html)
        self.assertIn("const scale = 3", html)
        self.assertIn("const size = 1200", html)
        self.assertIn("cssWidth < 560", html)
        self.assertNotIn("total_precipitation", html)
        self.assertNotIn("crossorigin", html)
        self.assertIn('src="/latest_posts/brand/bnw-brick-black.png"', html)
        self.assertIn('srcset="/latest_posts/brand/bnw-brick-offwhite.png"', html)

    def test_gallery_nav_copies_include_the_link(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for rel in (
            "operational_bundle/bin/operational_lib.sh",
            "operational_bundle/bin/update_s3_portal_standalone.sh",
            "lib/c3s_globes.py",
        ):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertIn('link("/climate/moisture-trends", "Trends")', text)
            self.assertIn('link("/climate/moisture-tracking", "Tracking")', text)
            self.assertLess(
                text.index('link("/climate/headlines", "Headlines")'),
                text.index('link("/climate/moisture-trends", "Trends")'),
            )
            self.assertLess(
                text.index('link("/climate/moisture-trends", "Trends")'),
                text.index('link("/climate/oceans", "Oceans")'),
            )
            self.assertIn('link("/weather/snow-anomaly", "Anomaly")', text)
            self.assertIn('link("/weather/snow-forecast", "Forecast")', text)
            self.assertIn('link("/graphics/moisture", "Moisture")', text)
            self.assertNotIn('link("/moisture-trends", "Moisture trends")', text)


if __name__ == "__main__":
    unittest.main()
