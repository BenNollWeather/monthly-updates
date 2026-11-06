#!/usr/bin/env python3
"""Snowfall forecast bins and units. These do not download GRIB files."""

from __future__ import annotations

import unittest
from datetime import datetime

import numpy as np

import base64
from io import BytesIO

from PIL import Image

from lib.snow_forecast import (
    EDGES,
    FINE,
    SNOW_COLORS,
    SNOW_LABELS,
    _window_phrase,
    domain_max,
    forecast_source,
    make_view,
    pack_snow,
    snow_bin,
    swe_to_inches,
)
from lib.snow_forecast import MODELS


class BinTests(unittest.TestCase):
    def test_breakpoints_open_the_next_category(self):
        self.assertEqual(int(snow_bin(0.49)), 0)
        self.assertEqual(int(snow_bin(0.5)), 1)
        self.assertEqual(int(snow_bin(1)), 2)
        self.assertEqual(int(snow_bin(3)), 3)
        self.assertEqual(int(snow_bin(6)), 4)
        self.assertEqual(int(snow_bin(9)), 5)
        self.assertEqual(int(snow_bin(12)), 6)
        self.assertEqual(int(snow_bin(18)), 7)
        self.assertEqual(int(snow_bin(24)), 8)
        self.assertEqual(int(snow_bin(40)), 8)
        self.assertEqual(len(EDGES), 8)
        self.assertEqual(len(SNOW_COLORS), 8)
        self.assertEqual(SNOW_LABELS[0], "0.5–1 in.")
        self.assertEqual(SNOW_LABELS[-1], "24+")
        self.assertEqual(SNOW_COLORS[0], "#D4E8F4")
        self.assertEqual(SNOW_COLORS[-1], "#0C2248")

    def test_water_and_missing_values_stay_uncolored(self):
        bins = snow_bin([[np.nan, 0.2], [2.0, 24.0]])
        self.assertEqual(bins.tolist(), [[0, 0], [2, 8]])


class UnitTests(unittest.TestCase):
    def test_ifs_metres_and_aifs_kilograms_both_become_inches(self):
        self.assertAlmostEqual(float(swe_to_inches(0.01, "m of water equivalent")), 0.01 * 39.3701 * 10)
        self.assertAlmostEqual(float(swe_to_inches(10, "kg m**-2")), 10 * 0.0393701 * 10)
        self.assertAlmostEqual(float(swe_to_inches(10, "mm")), float(swe_to_inches(10, "kg m**-2")))

    def test_an_unknown_unit_is_rejected(self):
        with self.assertRaises(ValueError):
            swe_to_inches(1, "K")


class MaxTests(unittest.TestCase):
    def test_the_pin_ignores_water_and_uses_the_northern_tie(self):
        lat = np.array([40.0, 35.0])
        lon = np.array([-100.0, -90.0])
        inches = np.array([[8.0, 8.0], [30.0, 8.0]])
        land = np.array([[1.0, 0.2], [0.0, 1.0]])
        pin = domain_max(inches, lat, lon, land)
        self.assertEqual(pin["label"], "8.0 in.")
        self.assertEqual(pin["lat"], 40.0)
        self.assertEqual(pin["lon"], -100.0)

    def test_longitude_past_180_is_shifted_into_the_map(self):
        pin = domain_max([[8.25]], [47.6], [238.3], [[1.0]])
        self.assertAlmostEqual(pin["lon"], -121.7)
        self.assertAlmostEqual(pin["lat"], 47.6)
        self.assertEqual(pin["label"], "8.2 in.")

    def test_a_higher_total_in_canada_is_not_the_maximum(self):
        lat = np.array([49.75, 47.6])
        lon = np.array([-122.5, -121.7])
        inches = np.array([[40.0, 0.0], [0.0, 12.5]])
        land = np.ones((2, 2))
        pin = domain_max(inches, lat, lon, land)
        self.assertAlmostEqual(pin["lat"], 47.6)
        self.assertAlmostEqual(pin["lon"], -121.7)
        self.assertEqual(pin["label"], "12.5 in.")

    def test_the_view_names_the_window_and_the_maximum(self):
        spec = MODELS[0]
        cycle = datetime(2026, 11, 4, 18, 0, 0)
        view = make_view(
            spec,
            cycle,
            np.array([[0.4, 6.0]]),
            np.array([42.0]),
            np.array([-80.0, -75.0]),
            np.ones((1, 2)),
        )
        self.assertEqual(view["button"], "ECMWF")
        self.assertEqual(view["title"], "Weekly snowfall forecast")
        window = "1 p.m. Nov. 4 through 1 p.m. Nov. 11, 2026 ET"
        self.assertEqual(view["span"], f"From {window}")
        self.assertEqual(
            _window_phrase(datetime(2026, 11, 4, 18)),
            window,
        )
        self.assertEqual(
            _window_phrase(datetime(2026, 11, 4, 12)),
            "7 a.m. Nov. 4 through 7 a.m. Nov. 11, 2026 ET",
        )
        self.assertEqual(
            _window_phrase(datetime(2026, 11, 5, 0)),
            "7 p.m. Nov. 4 through 7 p.m. Nov. 11, 2026 ET",
        )
        self.assertNotIn(window, view["rank"])
        self.assertNotIn("Next 7 days", view["span"])
        self.assertNotIn("18z", view["rank"])
        self.assertEqual(view["rank"], "Maximum 6.0 in.")
        self.assertIn("Weekly snowfall forecast", view["alt"])
        self.assertIn(window, view["alt"])
        self.assertIn("1 p.m. ET Nov. 4, 2026 run", view["source"])
        self.assertNotIn("18z", view["source"])
        self.assertIn("7 days", view["source"])
        self.assertEqual(view["pin"]["lon"], -75.0)
        self.assertTrue(view["smooth"])
        self.assertEqual(view["nlat"], FINE)
        self.assertEqual(view["nlon"], 2 * FINE)
        self.assertIn("10:1", view["source"])
        self.assertIn("ECMWF IFS", forecast_source("IFS", cycle))
        self.assertEqual(view["colors"], list(SNOW_COLORS))
        self.assertGreater(len(view["field"]), 20)

    def test_categories_follow_a_resampled_ramp_through_the_model_cell(self):
        meta, payload = pack_snow(
            np.array([[0.0, 30.0]]),
            np.array([41.0]),
            np.array([-100.0, -99.75]),
            np.ones((1, 2)),
        )
        self.assertEqual(meta["nlat"], FINE)
        self.assertEqual(meta["nlon"], 2 * FINE)
        image = Image.open(BytesIO(base64.b64decode(payload)))
        self.assertEqual(image.size, (2 * FINE, FINE))
        values = set(image.get_flattened_data())
        self.assertIn(8, values)
        self.assertTrue(any(1 <= value <= 7 for value in values))
        drawn_west = meta["lonWest"] - (meta["lonEast"] - meta["lonWest"]) / (meta["nlon"] - 1) / 2
        drawn_east = meta["lonEast"] + (meta["lonEast"] - meta["lonWest"]) / (meta["nlon"] - 1) / 2
        self.assertAlmostEqual(drawn_west, -100.125, places=4)
        self.assertAlmostEqual(drawn_east, -99.625, places=4)
