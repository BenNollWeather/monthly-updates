#!/usr/bin/env python3
"""Rainfall bins, 10°F temperature bins, and the forecast pages. No GRIB download."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

from lib.weather_forecast import (
    RAIN_COLORS,
    RAIN_EDGES,
    RAIN_LABELS,
    RAIN_PATH,
    RAIN_TITLE,
    AIFS_TEMP_STEPS,
    IFS_TEMP_3H,
    IFS_TEMP_6H,
    TEMP_COLORS,
    TEMP_EDGES,
    TEMP_LABELS,
    MAX_PATH,
    MAX_TITLE,
    MIN_PATH,
    MIN_TITLE,
    _accumulate,
    format_temp,
    liquid_inches,
    product_views,
    rain_bin,
    render_forecast_page,
    temp_bin,
    to_fahrenheit,
)

ROOT = Path(__file__).resolve().parents[1]


def _loaded(rain, tmax, tmin):
    lat = np.array([40.0, 35.0])
    lon = np.array([-100.0, -90.0])
    land = np.ones((2, 2))
    cycle = datetime(2026, 11, 4, 12, 0, 0)
    specs = {
        "ecmwf": {"key": "ecmwf", "model": "ifs", "name": "IFS", "button": "ECMWF"},
        "aifs": {"key": "aifs", "model": "aifs-single", "name": "AIFS", "button": "ECMWF-AIFS"},
    }
    return {
        key: {
            "spec": spec,
            "cycle": cycle,
            "instant": key == "aifs",
            "rain": np.array(rain, dtype=np.float64),
            "tmax": np.array(tmax, dtype=np.float64),
            "tmin": np.array(tmin, dtype=np.float64),
            "lat": lat,
            "lon": lon,
            "land": land,
        }
        for key, spec in specs.items()
    }


class ResolutionTests(unittest.TestCase):
    def test_ifs_uses_the_nine_kilometre_grid_and_aifs_stays_quarter_degree(self):
        from lib.snow_forecast import _latest_cycle as snow_latest
        from lib.snow_forecast import _retrieve
        from lib.weather_forecast import _latest_cycle as weather_latest

        seen = []

        class FakeClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def latest(self, **kwargs):
                seen.append(("latest", self.kwargs["model"], self.kwargs["resol"], kwargs))
                return datetime(2026, 11, 5, 12)

            def retrieve(self, **kwargs):
                seen.append(("retrieve", self.kwargs["model"], self.kwargs["resol"], kwargs))

        with patch("ecmwf.opendata.Client", FakeClient):
            snow_latest("ifs")
            weather_latest("ifs", "tp")
            weather_latest("aifs-single", "2t")
            _retrieve("ifs", "mx2t3", 3, Path("/tmp/ifs-resol-test.grib2"), datetime(2026, 11, 5, 12), ("google",))
            _retrieve(
                "aifs-single", "2t", 6, Path("/tmp/aifs-resol-test.grib2"), datetime(2026, 11, 5, 12), ("google",)
            )

        ifs = [item for item in seen if item[1] == "ifs"]
        aifs = [item for item in seen if item[1] == "aifs-single"]
        self.assertTrue(ifs)
        self.assertTrue(aifs)
        self.assertTrue(all(item[2] == "0p1" for item in ifs))
        self.assertTrue(all(item[2] == "0p25" for item in aifs))
        self.assertTrue(all(item[3].get("levtype") == "sfc" for item in ifs))
        self.assertTrue(all("levtype" not in item[3] for item in aifs))
        self.assertNotIn("0p25", {item[2] for item in ifs})

    def test_folded_extremes_match_nanmax_and_nanmin(self):
        planes = [
            np.array([[1.0, np.nan], [np.nan, 4.0]]),
            np.array([[np.nan, 2.0], [3.0, np.nan]]),
            np.array([[0.0, 9.0], [np.nan, -1.0]]),
        ]
        stack = np.stack(planes)
        folded_max, max_count = _accumulate(planes, np.fmax)
        folded_min, min_count = _accumulate(planes, np.fmin)
        self.assertEqual(max_count, 3)
        self.assertEqual(min_count, 3)
        self.assertTrue(np.allclose(folded_max, np.nanmax(stack, axis=0), equal_nan=True))
        self.assertTrue(np.allclose(folded_min, np.nanmin(stack, axis=0), equal_nan=True))


class BinTests(unittest.TestCase):
    def test_rain_bins_follow_the_stated_breaks(self):
        self.assertEqual(int(rain_bin(0.099)), 0)
        self.assertEqual(int(rain_bin(0.1)), 1)
        self.assertEqual(int(rain_bin(0.25)), 2)
        self.assertEqual(int(rain_bin(0.5)), 3)
        self.assertEqual(int(rain_bin(1)), 4)
        self.assertEqual(int(rain_bin(2)), 5)
        self.assertEqual(int(rain_bin(4)), 6)
        self.assertEqual(int(rain_bin(8)), 7)
        self.assertEqual(int(rain_bin(12)), 7)
        self.assertEqual(len(RAIN_COLORS), len(RAIN_LABELS))
        self.assertEqual(RAIN_LABELS[0], "0.1–0.25 in.")
        self.assertEqual(RAIN_LABELS[-1], "8+")
        self.assertEqual(len(RAIN_EDGES), 7)

    def test_temperature_bins_are_ten_degrees(self):
        self.assertEqual(TEMP_EDGES, (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110))
        self.assertEqual([TEMP_EDGES[index + 1] - TEMP_EDGES[index] for index in range(len(TEMP_EDGES) - 1)], [10] * 11)
        self.assertEqual(len(TEMP_COLORS), len(TEMP_LABELS))
        self.assertEqual(len(TEMP_LABELS), 13)
        self.assertEqual(TEMP_LABELS[0], "−10°F")
        self.assertEqual(TEMP_LABELS[1], "0")
        self.assertEqual(TEMP_LABELS[8], "70")
        self.assertEqual(TEMP_LABELS[-1], "110")
        self.assertFalse(any("–" in label or "<" in label or label.endswith("+") for label in TEMP_LABELS))
        self.assertEqual(TEMP_COLORS[0], "#E4F0FF")
        self.assertEqual(TEMP_COLORS[-1], "#3D0216")
        self.assertEqual(TEMP_COLORS[int(temp_bin(32)) - 1], "#26436F")
        self.assertEqual(int(temp_bin(-40)), 1)
        self.assertEqual(int(temp_bin(-10)), 1)
        self.assertEqual(int(temp_bin(-0.1)), 1)
        self.assertEqual(int(temp_bin(0)), 2)
        self.assertEqual(int(temp_bin(9.9)), 2)
        self.assertEqual(int(temp_bin(10)), 3)
        self.assertEqual(int(temp_bin(29.9)), int(temp_bin(20)))
        self.assertEqual(int(temp_bin(30)), int(temp_bin(32)))
        self.assertEqual(int(temp_bin(32)), int(temp_bin(39.9)))
        self.assertNotEqual(int(temp_bin(39.9)), int(temp_bin(40)))
        self.assertEqual(TEMP_LABELS[int(temp_bin(70)) - 1], "70")
        self.assertEqual(int(temp_bin(70)), int(temp_bin(79.9)))
        self.assertEqual(int(temp_bin(100)), int(temp_bin(109.9)))
        self.assertEqual(TEMP_LABELS[int(temp_bin(110)) - 1], "110")
        self.assertEqual(int(temp_bin(110)), len(TEMP_LABELS))
        self.assertEqual(int(temp_bin(120)), len(TEMP_LABELS))
        self.assertEqual(int(temp_bin(np.nan)), 0)
        self.assertEqual(IFS_TEMP_3H[0], 3)
        self.assertEqual(IFS_TEMP_3H[-1], 144)
        self.assertEqual(len(IFS_TEMP_3H), 48)
        self.assertTrue(all(step % 3 == 0 for step in IFS_TEMP_3H))
        self.assertEqual(IFS_TEMP_6H, (150, 156, 162, 168))
        self.assertEqual(AIFS_TEMP_STEPS[0], 6)
        self.assertEqual(AIFS_TEMP_STEPS[-1], 168)
        self.assertEqual(len(AIFS_TEMP_STEPS), 28)
        self.assertTrue(all(step % 6 == 0 for step in AIFS_TEMP_STEPS))

    def test_units_have_no_snow_ratio(self):
        self.assertAlmostEqual(float(liquid_inches(0.01, "m")), 0.393701)
        self.assertAlmostEqual(float(liquid_inches(10, "kg m**-2")), 0.393701)
        self.assertAlmostEqual(float(to_fahrenheit(273.15, "K")), 32.0)
        self.assertAlmostEqual(float(to_fahrenheit(0, "C")), 32.0)
        self.assertEqual(format_temp(-12.4), "−12°F")
        self.assertEqual(format_temp(87.5), "88°F")
        self.assertEqual(format_temp(0.4), "0°F")


class ShoreTests(unittest.TestCase):
    def test_temperature_follows_the_drawn_shore(self):
        import base64
        from io import BytesIO

        from PIL import Image

        from lib.snow_forecast import FINE, pack_snow

        def packed(value, lat, lon, mask, extent):
            _meta, payload = pack_snow(
                np.array([[value]]),
                np.array([lat]),
                np.array([lon]),
                np.full((1, 1), mask),
                extent=extent,
                classify=temp_bin,
                empty=None,
                vector_land=True,
            )
            return np.array(Image.open(BytesIO(base64.b64decode(payload))))

        inland = packed(75.0, 41.6, -93.6, 0.0, (-94.0, -93.2, 41.2, 42.0))
        self.assertEqual(inland.shape, (FINE, FINE))
        self.assertTrue(np.all(inland == int(temp_bin(75.0))))
        lake = packed(75.0, 44.0, -87.0, 1.0, (-87.4, -86.6, 43.6, 44.4))
        self.assertTrue(np.all(lake == 0))
        # Snow and precipitation keep the model mask. A water mask stays uncolored.
        _meta, payload = pack_snow(
            np.array([[75.0]]),
            np.array([41.6]),
            np.array([-93.6]),
            np.zeros((1, 1)),
            extent=(-94.0, -93.2, 41.2, 42.0),
            classify=temp_bin,
            empty=None,
        )
        masked = np.array(Image.open(BytesIO(base64.b64decode(payload))))
        self.assertTrue(np.all(masked == 0))


class FreezeTests(unittest.TestCase):
    def test_contour_crosses_the_top_edge_at_two_fifths(self):
        from lib.snow_forecast import contour_lines

        lines = contour_lines(
            np.array([[20.0, 50.0], [10.0, 40.0]]),
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
            32.0,
        )
        self.assertEqual(len(lines), 1)
        flat = lines[0]
        self.assertEqual(len(flat), 4)
        ends = sorted([(flat[0], flat[1]), (flat[2], flat[3])])
        # Top edge t = (32-20)/(50-20) = 0.4. Bottom edge t = (32-10)/(40-10).
        self.assertEqual(ends, [(0.4, 1.0), (round((32.0 - 10.0) / (40.0 - 10.0), 3), 0.0)])

    def test_saddle_follows_the_cell_center(self):
        from lib.snow_forecast import contour_lines

        lines = contour_lines(
            np.array([[10.0, 50.0], [50.0, 10.0]]),
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
            32.0,
        )
        ends = []
        for flat in lines:
            self.assertEqual(len(flat), 4)
            ends.append(tuple(sorted([(flat[0], flat[1]), (flat[2], flat[3])])))
        # Center is 30, on the same side as the 10s, so the segments are top–right and left–bottom.
        self.assertCountEqual(
            ends,
            [
                ((0.55, 1.0), (1.0, 0.55)),
                ((0.0, 0.45), (0.45, 0.0)),
            ],
        )

    def test_contour_stops_when_an_endpoint_is_off_land(self):
        from lib.snow_forecast import contour_lines

        lines = contour_lines(
            np.array([[20.0, 50.0], [10.0, 40.0]]),
            np.array([1.0, 0.0]),
            np.array([0.0, 1.0]),
            32.0,
            on_land=np.array([[True, False], [True, True]]),
        )
        self.assertEqual(lines, [])

    def test_sigma_pulls_a_spike_toward_its_neighbors(self):
        from lib.snow_forecast import smooth_contour_field

        values = np.full((9, 9), 20.0)
        values[4, 4] = 80.0
        smoothed = smooth_contour_field(
            values,
            np.linspace(4.0, 0.0, 9),
            np.linspace(0.0, 4.0, 9),
            np.ones((9, 9), dtype=bool),
            1.0,
        )
        self.assertLess(smoothed[4, 4], 55.0)
        self.assertGreater(smoothed[4, 4], 20.0)
        self.assertGreater(smoothed[4, 3], 20.0)
        self.assertLess(smoothed[0, 0], 25.0)


class PageTests(unittest.TestCase):
    def _pages(self):
        loaded = _loaded(
            rain=[[0.05, 1.25], [8.4, 0.2]],
            tmax=[[32.2, 87.4], [101.2, 54.0]],
            tmin=[[-12.2, 41.0], [3.4, 60.2]],
        )
        return loaded, {
            "rain": render_forecast_page(product_views(loaded, "rain"), RAIN_PATH, RAIN_TITLE),
            "max": render_forecast_page(product_views(loaded, "max"), MAX_PATH, MAX_TITLE),
            "min": render_forecast_page(product_views(loaded, "min"), MIN_PATH, MIN_TITLE),
        }

    def test_menu_adds_rain_and_temperature_beside_snow(self):
        _loaded_models, pages = self._pages()
        html = pages["rain"]
        nav = html.split('<nav aria-label="Sections">', 1)[1].split("</nav>", 1)[0]
        weather = nav.split("<summary>Weather</summary>", 1)[1].split("<summary>Graphics</summary>", 1)[0]
        snow = weather.split("<summary>Snow</summary>", 1)[1].split("</details>", 1)[0]
        self.assertIn('href="/weather/snow-forecast">Forecast</a>', snow)
        self.assertNotIn("/weather/rain", snow)
        self.assertNotIn("Temperature", snow)
        self.assertIn('href="/weather/rain" aria-current="page">Precipitation</a>', weather)
        self.assertNotIn(">Rain</a>", weather)
        self.assertIn("<summary>Temperatures</summary>", weather)
        self.assertNotIn("<summary>Temperature</summary>", weather)
        self.assertIn('href="/weather/temperature-maximum">Maximum</a>', weather)
        self.assertIn('href="/weather/temperature-minimum">Minimum</a>', weather)
        self.assertLess(weather.index("Forecast"), weather.index('href="/weather/rain"'))
        self.assertLess(weather.index('href="/weather/rain"'), weather.index("<summary>Temperatures</summary>"))
        self.assertLess(weather.index(">Maximum</a>"), weather.index(">Minimum</a>"))
        long_range = nav.split("<summary>Long range</summary>", 1)[1].split("</details>", 1)[0]
        self.assertNotIn("/weather/rain", long_range)
        self.assertNotIn("temperature-maximum", long_range)

    def test_rain_page_uses_the_nasa_bins(self):
        _loaded_models, pages = self._pages()
        html = pages["rain"]
        payload = json.loads(html.split("const DATA = ", 1)[1].split(";", 1)[0])
        view = payload["views"]["ecmwf"]
        self.assertEqual(list(payload["views"]), ["ecmwf", "aifs"])
        self.assertNotIn("anomaly", payload["views"])
        self.assertEqual(view["kind"], "rain")
        self.assertNotIn("line", payload)
        self.assertEqual(view["ticks"], RAIN_LABELS)
        self.assertEqual(view["colors"], RAIN_COLORS)
        self.assertEqual(view["title"], "Weekly precipitation forecast")
        self.assertEqual(view["filename"], "ecmwf-weekly-precipitation.png")
        self.assertIn("--legend-min:99.4ch", html)
        self.assertIn("function stateLabelRects", html)
        self.assertIn("chosen.lead", html)
        self.assertIn('<link rel="canonical" href="https://benweather.com/weather/rain">', html)
        self.assertIn('id="snow-scale"', html)
        scale = html.split('id="snow-scale"', 1)[1].split("</div>", 2)
        legend = scale[0] + scale[1]
        self.assertIn("0.1–0.25 in.", legend)
        self.assertIn("8+", legend)
        self.assertNotIn("24+", legend)
        self.assertNotIn("0.5–1 in.", legend)
        self.assertIn("shown in inches", view["source"])
        self.assertNotIn("10:1", view["source"])
        self.assertNotIn("snow", view["source"].lower())
        self.assertIn("Maximum", view["rank"])
        self.assertIn("in.", view["rank"])

    def test_temperature_pages_share_ten_degree_bins(self):
        _loaded_models, pages = self._pages()
        maximum = json.loads(pages["max"].split("const DATA = ", 1)[1].split(";", 1)[0])
        minimum = json.loads(pages["min"].split("const DATA = ", 1)[1].split(";", 1)[0])
        self.assertEqual(maximum["views"]["ecmwf"]["ticks"], TEMP_LABELS)
        self.assertEqual(minimum["views"]["aifs"]["ticks"], TEMP_LABELS)
        self.assertEqual(maximum["views"]["ecmwf"]["colors"], minimum["views"]["ecmwf"]["colors"])
        self.assertEqual(maximum["views"]["ecmwf"]["kind"], "temp")
        self.assertEqual(minimum["views"]["aifs"]["kind"], "temp")
        self.assertIn("since the previous step", maximum["views"]["ecmwf"]["source"])
        self.assertIn("highest value", maximum["views"]["ecmwf"]["source"])
        self.assertNotIn("6-hour", maximum["views"]["ecmwf"]["source"])
        self.assertIn("since the previous step", minimum["views"]["ecmwf"]["source"])
        self.assertIn("lowest value", minimum["views"]["ecmwf"]["source"])
        self.assertNotIn("6-hour", minimum["views"]["ecmwf"]["source"])
        self.assertIn("6-hour steps", maximum["views"]["aifs"]["source"])
        self.assertNotIn("6-hour maximum", maximum["views"]["aifs"]["source"])
        self.assertEqual(len(maximum["views"]["ecmwf"]["ticks"]), 13)
        self.assertEqual(len(maximum["views"]["ecmwf"]["colors"]), 13)
        self.assertIn('<link rel="canonical" href="https://benweather.com/weather/temperature-maximum">', pages["max"])
        self.assertIn('href="/weather/temperature-maximum" aria-current="page">Maximum</a>', pages["max"])
        self.assertIn('href="/weather/temperature-minimum" aria-current="page">Minimum</a>', pages["min"])
        self.assertIn("−10°F", pages["max"])
        self.assertIn("--legend-min:93.6ch", pages["max"])
        self.assertIn('<div class="legend-track"><div class="swatches">', pages["max"])
        self.assertIn(".snow-scale .legend-track { width: max(100%, var(--legend-min, 100%));", pages["max"])
        self.assertIn(".snow-scale .swatches, .snow-scale .ticks { width: 100%;", pages["max"])
        self.assertNotIn("&lt;−40", pages["max"])
        self.assertNotIn("120+", pages["max"])
        self.assertNotIn("30–40", pages["min"])
        self.assertIn(">70</span>", pages["max"])
        self.assertIn(">110</span>", pages["max"])
        self.assertIn('ctx.lineWidth = Math.max(2.5, box.w / 450);', pages["max"])
        self.assertNotIn("ctx.lineWidth = Math.max(1.25, box.w / 900);", pages["max"])
        self.assertEqual(minimum.get("line"), "#e7eef6")
        self.assertNotIn("line", maximum)
        self.assertIn('ctx.strokeStyle = DATA.line || "#4a4a4a";', pages["min"])
        rain = json.loads(pages["rain"].split("const DATA = ", 1)[1].split(";", 1)[0])
        for key in ("ecmwf", "aifs"):
            freeze = minimum["views"][key]["freeze"]
            self.assertGreaterEqual(len(freeze), 1)
            self.assertGreaterEqual(len(freeze[0]), 4)
            self.assertEqual(len(freeze[0]) % 2, 0)
            flat = [value for line in freeze for value in line]
            self.assertTrue(all(-110 < lon < -80 for lon in flat[0::2]))
            self.assertTrue(all(30 < lat < 50 for lat in flat[1::2]))
            self.assertNotIn("freeze", maximum["views"][key])
            self.assertNotIn("freeze", rain["views"][key])
        self.assertIn("activeSpec().freeze", pages["min"])
        self.assertIn(
            "setLineDash([Math.max(14, box.w / 70), Math.max(10, box.w / 100)])",
            pages["min"],
        )
        self.assertEqual(minimum.get("freezeColor"), "#FFE500")
        self.assertEqual(minimum.get("freezeCasing"), "#161616")
        self.assertEqual(minimum.get("freezeLabel"), "32°F")
        self.assertNotIn("freezeColor", maximum)
        self.assertNotIn("freezeColor", rain)
        self.assertIn('class="freeze-key"', pages["min"])
        self.assertIn('stroke="#FFE500"', pages["min"])
        self.assertIn(">32°F</span>", pages["min"])
        self.assertNotIn('class="freeze-key"', pages["max"])
        self.assertNotIn('class="freeze-key"', pages["rain"])
        self.assertIn("function snowLegendHeight", pages["min"])
        self.assertNotIn('id="snow-scale" hidden', pages["max"])
        self.assertIn('id="anomaly-ranks" hidden', pages["max"])
        self.assertIn("°F", maximum["views"]["ecmwf"]["rank"])
        self.assertIn("°F", minimum["views"]["ecmwf"]["rank"])
        self.assertTrue(maximum["views"]["ecmwf"]["rank"].startswith("Maximum"))
        self.assertTrue(minimum["views"]["ecmwf"]["rank"].startswith("Minimum"))

    def test_workflow_is_separate_from_snow(self):
        workflow = (ROOT / ".github/workflows/weather-forecast.yml").read_text(encoding="utf-8")
        snow = (ROOT / ".github/workflows/snow-anomaly.yml").read_text(encoding="utf-8")
        self.assertIn("monthly-updates-weather-forecast", workflow)
        self.assertIn("SCHEDULED_EVENT:", workflow)
        self.assertNotIn("cron:", workflow)
        self.assertNotIn("cron:", snow)
        self.assertNotIn("41 15 * * *", workflow)
        self.assertNotIn("41 0,6,12,18 * * *", workflow)
        self.assertIn("s3://bennollweather/rain", workflow)
        self.assertIn("s3://bennollweather/temperature-maximum", workflow)
        self.assertIn("s3://bennollweather/temperature-minimum", workflow)
        self.assertNotIn("temperature-maximum", snow)
        self.assertNotIn("s3://bennollweather/rain", snow)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("| Weekly precipitation | 02:41, 10:41, 14:41, and 22:41 every day |", readme)
        self.assertIn("| Weekly maximum and minimum temperature |", readme)
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["MPLBACKEND"] = "Agg"
        completed = subprocess.run(
            [sys.executable, str(ROOT / "lib" / "weather_forecast.py"), "--help"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("weekly precipitation", completed.stdout.lower())
        for rel in (
            "lib/c3s_globes.py",
            "operational_bundle/bin/operational_lib.sh",
            "operational_bundle/bin/update_s3_portal_standalone.sh",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertLess(text.index('link("/weather/snow-forecast", "Forecast")'), text.index('link("/weather/rain", "Precipitation")'))
            self.assertLess(text.index('link("/weather/rain", "Precipitation")'), text.index('link("/weather/temperature-maximum", "Maximum")'))
            self.assertIn("<summary>Temperatures</summary>", text)
            self.assertNotIn("<summary>Temperature</summary>", text)
            self.assertLess(
                text.index('link("/weather/temperature-maximum", "Maximum")'),
                text.index('link("/weather/temperature-minimum", "Minimum")'),
            )


if __name__ == "__main__":
    unittest.main()
