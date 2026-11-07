#!/usr/bin/env python3
"""Moisture tracking payload and page. These do not call CDS."""

from __future__ import annotations

import base64
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from lib.moisture_tracking import (
    HIGHLIGHT_COLORS,
    _lookup,
    build_payload,
    pack_percent,
    render,
    year_labels,
)


def _grid(times, values, lats, lons) -> xr.Dataset:
    data = np.asarray(values, dtype=float)
    return xr.Dataset(
        {"tcw": (("valid_time", "latitude", "longitude"), data)},
        coords={"valid_time": list(times), "latitude": lats, "longitude": lons},
    )


class MoistureTrackingTests(unittest.TestCase):
    def test_area_weights_follow_latitude(self) -> None:
        ds = _grid(
            [pd.Timestamp("2026-09-01")],
            [[[10.0, 10.0], [40.0, 40.0]]],
            [60.0, 0.0],
            [0.0, 10.0],
        )
        self.assertAlmostEqual(_lookup(ds)[(2026, 9)], 30 / 25.4, places=6)

    def test_rank_one_is_the_highest_september(self) -> None:
        payload = self._september_payload()
        self.assertEqual(payload["inchesText"], "1.10 in.")
        self.assertEqual(payload["rank"], "Rank 1 of 3 in 2026")
        self.assertEqual(payload["rankPlace"], 1)
        self.assertEqual(payload["dipYear"], 2022)
        self.assertEqual(payload["monthYear"], "September 2026")
        self.assertEqual(payload["mapTitle"], "Precipitable water percentage of average")
        self.assertEqual(payload["monthTitle"], "Precipitable water in September")
        self.assertEqual(payload["range"], "September moistening stripes")
        self.assertEqual(
            payload["yearTitle"],
            "Precipitable water in September 2026 compared to historical levels",
        )
        self.assertNotIn("yearHead", payload)
        self.assertNotIn("yearDek", payload)
        series = payload["cycle"]["series"]
        self.assertEqual([item["year"] for item in series], [2023, 2024, 2025, 2026])
        history = payload["history"]
        self.assertEqual(history[0], [2022, 1, 1.0])
        self.assertEqual(history[-1], [2026, 9, 1.1])
        self.assertEqual(len(history), 4 * 12 + 9)
        self.assertEqual([row[1] for row in history if row[0] == 2026], list(range(1, 10)))
        self.assertEqual([item["color"] for item in series], list(HIGHLIGHT_COLORS))
        self.assertEqual(series[-1]["color"], "#CC79A7")
        self.assertEqual(len(series[-1]["values"]), 9)
        self.assertEqual(len(series[0]["values"]), 12)

    def test_titles_name_the_month(self) -> None:
        self.assertEqual(
            year_labels(2026, 12),
            (
                "Precipitable water in December",
                "Precipitable water in December 2026 compared to historical levels",
            ),
        )
        self.assertEqual(
            year_labels(2026, 9),
            (
                "Precipitable water in September",
                "Precipitable water in September 2026 compared to historical levels",
            ),
        )

    def test_map_bytes_keep_a_coarse_grid(self) -> None:
        perc = xr.DataArray(
            [[80.0, 100.0], [120.0, np.nan]],
            dims=("latitude", "longitude"),
            coords={"latitude": [10.0, -10.0], "longitude": [0.0, 180.0]},
        )
        packed = pack_percent(perc)
        self.assertEqual(packed["nlat"], 2)
        self.assertEqual(packed["nlon"], 2)
        self.assertLess(packed["dlat"], 0)
        self.assertEqual(packed["lon0"], 0.0)
        raw = base64.b64decode(packed["grid"])
        self.assertEqual(list(raw), [80, 100, 120, 255])

    def test_page_is_large_type_and_short_copy(self) -> None:
        html = render(self._september_payload())
        self.assertIn("<title>Moisture tracking</title>", html)
        self.assertNotIn('<h2 id="title">', html)
        self.assertIn("clamp(26px, 3.8vw, 38px)", html)
        self.assertNotIn("clamp(56px, 8vw, 92px)", html)
        self.assertNotIn('class="subnav"', html)
        self.assertIn('href="/climate/moisture-tracking" aria-current="page">Tracking</a>', html)
        self.assertIn('href="/climate/moisture-trends">Trends</a>', html)
        self.assertIn('src="/climate_imagery/moisture_coasts.js?v=1"', html)
        self.assertNotIn("[276.92,42.3]", html)
        self.assertIn('<p class="dek">Rank 1 of 3 in 2026</p>', html)
        self.assertLess(html.index('id="map"'), html.index("Precipitable water percentage of average"))
        map_head = html[html.index('id="map"'):html.index('id="month"')]
        self.assertIn("<h3 class=\"plot-title\">Precipitable water percentage of average</h3>", map_head)
        self.assertIn('<p class="dek">September 2026</p>', map_head)
        self.assertLess(map_head.index("Precipitable water percentage of average"), map_head.index(">September 2026<"))
        self.assertNotIn("<h3>September 2026</h3>", map_head)
        self.assertIn("Precipitable water percentage of average", html)
        self.assertIn('"70%"', html)
        self.assertIn("BROWN_CAP", html)
        self.assertIn("TEAL_CAP", html)
        self.assertIn("const TEAL = [48, 136, 166]", html)
        self.assertIn("const TEAL_DEEP = [40, 90, 107]", html)
        self.assertIn("const TEAL_CAP = [12, 74, 95]", html)
        self.assertNotIn("const TEAL_CAP = [26, 47, 54]", html)
        self.assertIn("amount / 0.62", html)
        self.assertIn("const delta = value - median", html)
        self.assertIn("reach * 0.1", html)
        self.assertNotIn("TEAL_SOFT", html)
        self.assertNotIn("BLUE_CAP", html)
        self.assertNotIn("createLinearGradient", html)
        month_head = html[html.index('id="month"'):html.index('id="year"')]
        self.assertIn(">Precipitable water in September<", month_head)
        self.assertIn('data-csv="month"', month_head)
        self.assertIn(">Data<", month_head)
        self.assertIn(">Download<", month_head)
        self.assertLess(month_head.index(">Download<"), month_head.index(">Data<"))
        self.assertNotIn(">Save<", month_head)
        self.assertIn("Rank 1 of 3 in 2026", month_head)
        self.assertLess(month_head.index("Precipitable water in September"), month_head.index("Rank 1 of 3 in 2026"))
        self.assertNotIn("1.10 in.", month_head)
        self.assertNotIn('class="hero"', html)
        self.assertNotIn("DATA.inchesText", html)
        self.assertIn("Precipitable water in September 2026 compared to historical levels", html)
        self.assertIn(
            'const MONTHS = ["Jan.", "Feb.", "March", "April", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]',
            html,
        )
        self.assertIn("const monthCount = 4", html)
        self.assertIn("Math.round((i * 11) / (monthCount - 1))", html)
        self.assertIn("free / gaps", html)
        stripes = html[html.index('id="stripes"'):html.index('id="decile"')]
        self.assertIn(">September moistening stripes<", stripes)
        self.assertIn('<h3 class="plot-title">September moistening stripes</h3>', stripes)
        self.assertNotIn("Moistening stripes,", html)
        self.assertIn("yearTicks(DATA.start, DATA.year, 40)", html)
        self.assertIn("yearTicks(DATA.start, DATA.year, 20)", html)
        self.assertIn("year <= end; year += gap", html)
        self.assertNotIn("end - 6", html)
        self.assertIn('percentileLines("90th"', html)
        self.assertIn('percentileLines("10th"', html)
        self.assertIn('" percentile · "', html)
        self.assertIn('"percentile"', html)
        self.assertNotIn("String(DATA.dipYear)", html)
        self.assertNotIn("Percent of average", html)
        self.assertNotIn("Through September", html)
        self.assertNotIn("The year", html)
        self.assertNotIn("yearHead", html)
        self.assertNotIn("yearDek", html)
        self.assertIn("Rank 1 of 3", html)
        self.assertIn("1.10 in.", html)
        self.assertIn("ERA5 total column water, compared with the 1991–2020 average.", html)
        self.assertIn("moisture-tracking-map.png", html)
        self.assertIn("moisture-tracking-month.png", html)
        self.assertIn("moisture-tracking-year.png", html)
        self.assertIn("moisture-tracking-stripes.png", html)
        self.assertIn("moisture-tracking-upper-decile.png", html)
        self.assertEqual(html.count(">Download<"), 5)
        self.assertEqual(html.count(">Data<"), 2)
        self.assertNotIn(">Save<", html)
        self.assertIn('data-csv="year"', html)
        self.assertNotIn('data-csv="map"', html)
        self.assertNotIn('data-csv="stripes"', html)
        self.assertIn("moisture-tracking-month.csv", html)
        self.assertIn("moisture-tracking-year.csv", html)
        self.assertIn("precipitable_water_inches", html)
        self.assertIn("DATA.history", html)
        year_csv = html[html.index("function yearCsv()"):html.index("document.body.addEventListener")]
        self.assertIn('const rows = [["", ...years]]', year_csv)
        self.assertIn("CSV_MONTHS.forEach", year_csv)
        self.assertNotIn("precipitable_water_inches", year_csv)
        self.assertNotIn("lowest_inches", html)
        self.assertNotIn("highest_inches", html)
        self.assertNotIn("average_inches", html)
        self.assertNotIn('series.year + "_inches"', html)
        year_head = html[html.index('id="year"'):html.index('id="stripes"')]
        self.assertLess(year_head.index(">Download<"), year_head.index(">Data<"))
        self.assertIn("const logoH = 84", html)
        self.assertIn("const markH = 42", html)
        self.assertIn("bottom - markH", html)
        self.assertIn("drawLogo(ctx, cardW - pad, cardH - 28, colors, 42)", html)
        self.assertNotIn("flex-direction: column", html)
        self.assertNotIn('fillText("benweather.com"', html)
        self.assertNotIn("width - pad - logoW, pad", html)
        self.assertIn('tick === topTick ? " in."', html)
        self.assertIn("toBlob", html)
        self.assertIn("const scale = 3", html)
        self.assertIn("const SCALE_LO = 70", html)
        self.assertIn("const SCALE_HI = 130", html)
        self.assertIn("const SCALE_STEP = 5", html)
        self.assertIn("map: [1400, 980]", html)
        self.assertIn("month: [1400, 860]", html)
        self.assertIn("year: [1400, 920]", html)
        self.assertIn("stripes: [1400, 500]", html)
        self.assertIn("decile: [1400, 820]", html)
        self.assertIn("xOf(end), yOf(latest.values[end])", html)
        self.assertIn("fitSize(ctx, DATA.range, textW, 48, 28, 700)", html)
        self.assertIn('["decile-canvas", "decile", drawDecile]', html)
        self.assertIn("/atmospheric_moisture/datawrapper/upper_decile_precip_coverage.csv", html)
        self.assertIn("Upper-decile precipitation is the share of the planet where rainfall exceeded that location's 90th percentile for the month.", html)
        self.assertIn("The series could not be loaded.", html)
        self.assertIn('cache: "no-store"', html)
        self.assertNotIn("const size = 1200", html)
        self.assertNotIn("cycle.lo[1] + cycle.hi[1]", html)
        self.assertIn("Drier", html)
        self.assertIn("Wetter", html)
        self.assertNotIn("const COASTS =", html)
        self.assertIn("function drawCharts()", html)
        self.assertIn('typeof COASTS !== "undefined"', html)
        coasts = (Path(__file__).resolve().parents[1] / "lib" / "moisture_tracking_coasts.js").read_text(encoding="utf-8")
        self.assertGreater(len(coasts), 1_000_000)
        lakes = coasts.split("const LAKES =", 1)[1]
        self.assertLess(len(lakes), 80_000)
        self.assertIn("[276.92,42.3]", lakes)
        self.assertIn("drawAll();", html)
        self.assertNotIn("design study", html.lower())
        self.assertNotIn("Mock", html)
        self.assertNotIn("crossorigin", html)
        self.assertNotIn("Rank:", html)
        self.assertNotIn("toDataURL", html)
        self.assertIn('src="/latest_posts/brand/bnw-brick-black.png"', html)
        self.assertIn('srcset="/latest_posts/brand/bnw-brick-offwhite.png"', html)

    def _september_payload(self) -> dict:
        lats = [60.0, 0.0]
        lons = [0.0, 10.0]
        septembers = {
            2022: 20.0,
            2025: 25.4,
            2026: 27.94,
        }
        month_times = [pd.Timestamp(year=year, month=9, day=1) for year in septembers]
        month_values = [np.full((2, 2), value) for value in septembers.values()]
        month_ds = _grid(month_times, month_values, lats, lons)
        monthly_times = []
        monthly_values = []
        for year in (2022, 2023, 2024, 2025):
            for month in range(1, 13):
                monthly_times.append(pd.Timestamp(year=year, month=month, day=1))
                monthly_values.append(np.full((2, 2), 25.4))
        for month in range(1, 10):
            monthly_times.append(pd.Timestamp(year=2026, month=month, day=1))
            monthly_values.append(np.full((2, 2), 27.94))
        monthly_ds = _grid(monthly_times, monthly_values, lats, lons)
        perc = xr.DataArray(
            np.full((2, 2), 100.0),
            dims=("latitude", "longitude"),
            coords={"latitude": lats, "longitude": lons},
        )
        return build_payload(perc, month_ds, monthly_ds, pd.Timestamp("2026-09-01"))


if __name__ == "__main__":
    unittest.main()
