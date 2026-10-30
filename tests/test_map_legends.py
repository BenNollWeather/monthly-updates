"""Legend units, region-label placement, and the relative Niño scaling factor."""

from __future__ import annotations

import unittest

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from lib.map_style import _add_missing_colorbar, _unit_from_text, apply
from lib.regions import MDR_BOUNDS, REGIONS, region_label_anchors


class UnitTests(unittest.TestCase):
    def test_sentence_case_titles_still_carry_units(self) -> None:
        self.assertEqual(_unit_from_text("ECMWF 500 hPa height anomaly"), "dam")
        self.assertEqual(_unit_from_text("C3S snowfall anomaly"), "in.")
        self.assertEqual(_unit_from_text("500 hPa height anomaly (dam)"), "dam")

    def test_height_colorbar_uses_dam_at_the_sst_label_size(self) -> None:
        apply()
        fig, ax = plt.subplots()
        ax.set_title("ECMWF 500 hPa height anomaly", loc="left")
        ax.contourf(np.zeros((4, 4)), levels=np.linspace(-10, 10, 21), extend="both")
        _add_missing_colorbar(ax)
        labels = [tick.get_text() for tick in fig.axes[-1].get_yticklabels()]
        self.assertEqual(labels, ["−10 dam", "−5 dam", "0 dam", "+5 dam", "+10 dam"])
        self.assertEqual(fig.axes[-1].get_yticklabels()[0].get_fontsize(), 24)
        plt.close(fig)

    def test_snow_colorbar_labels_every_two_inches(self) -> None:
        apply()
        fig, ax = plt.subplots()
        ax.set_title("ECMWF snowfall anomaly", loc="left")
        ax.contourf(np.zeros((4, 4)), levels=np.linspace(-6, 6, 13), extend="both")
        _add_missing_colorbar(ax)
        labels = [tick.get_text() for tick in fig.axes[-1].get_yticklabels()]
        self.assertEqual(
            labels,
            ["−6 in.", "−4 in.", "−2 in.", "0 in.", "+2 in.", "+4 in.", "+6 in."],
        )
        self.assertEqual(fig.axes[-1].get_yticklabels()[0].get_fontsize(), 24)
        plt.close(fig)


class RegionLabelTests(unittest.TestCase):
    def test_each_label_names_its_own_box(self) -> None:
        anchors = {name: (lon, lat) for name, lon, lat in region_label_anchors()}
        self.assertNotIn("3.4", anchors)
        self.assertNotIn("12", anchors)
        self.assertEqual(
            set(anchors),
            {"Niño 4", "Niño 3.4", "Niño 3", "Niño 1+2", "IOD-W", "IOD-E", "Atlantic MDR"},
        )
        self.assertEqual(anchors["Niño 4"][0], 185.0)
        self.assertEqual(anchors["Niño 3.4"][0], 215.0)
        self.assertGreater(anchors["Niño 3.4"][1], anchors["Niño 4"][1] + 8)
        self.assertEqual(anchors["Niño 1+2"][0], 275.0)
        west, _south, east, north = MDR_BOUNDS
        self.assertEqual(anchors["Atlantic MDR"][0], (west + east) / 2)
        self.assertGreater(anchors["Atlantic MDR"][1], north)
        for name, key, lift in (
            ("Niño 4", "nino4", 2.0),
            ("Niño 3", "nino3", 2.0),
            ("IOD-W", "iodw", 2.0),
            ("IOD-E", "iode", 2.0),
        ):
            box_west, _box_south, box_east, box_north = REGIONS[key]
            lon, lat = anchors[name]
            self.assertEqual(lon, (box_west + box_east) / 2)
            self.assertEqual(lat, box_north + lift)

    def test_drawn_labels_do_not_overlap(self) -> None:
        import cartopy.crs as ccrs

        apply()
        fig = plt.figure(figsize=(25, 15))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_global()
        from lib.regions import add_mdr_outline, draw_region_labels

        add_mdr_outline(ax)
        draw_region_labels(ax)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        placed = [(text.get_text(), text.get_window_extent(renderer)) for text in ax.texts]
        self.assertEqual(len(placed), 7)
        for index, (left_name, left_box) in enumerate(placed):
            for right_name, right_box in placed[index + 1 :]:
                self.assertFalse(
                    left_box.overlaps(right_box),
                    f"{left_name} overlaps {right_name}",
                )
        fig.savefig("/tmp/region-labels-global.png", dpi=80, facecolor="black")
        plt.close(fig)

        fig = plt.figure(figsize=(25, 15))
        ax = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree(central_longitude=180))
        ax.set_extent([240, 358, -5, 40])
        add_mdr_outline(ax)
        draw_region_labels(ax, names=("Atlantic MDR",))
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        texts = [text.get_text() for text in ax.texts]
        self.assertEqual(texts, ["Atlantic MDR"])
        fig.savefig("/tmp/region-labels-atlantic.png", dpi=80, facecolor="black")
        plt.close(fig)


class RoniScalingTests(unittest.TestCase):
    def test_factor_uses_the_raw_tropical_mean(self) -> None:
        import pandas as pd
        import xarray as xr

        from lib.roni_scaling import nino34_scaling_factors, scale_by_calendar_month

        times = pd.date_range("1950-01-01", "2020-12-01", freq="MS")
        lat = np.arange(20, -21, -5)
        lon = np.arange(0, 360, 10)
        rng = np.random.default_rng(4)
        values = rng.normal(scale=0.4, size=(len(times), len(lat), len(lon)))
        for index, stamp in enumerate(times):
            values[index] += 0.05 * stamp.month
            if stamp.month in (1, 8):
                lat_index = np.where((lat <= 5) & (lat >= -5))[0]
                lon_index = np.where((lon >= 190) & (lon <= 240))[0]
                values[index][np.ix_(lat_index, lon_index)] += stamp.month / 4
        dataset = xr.Dataset(
            {"sst": (("time", "lat", "lon"), values)},
            coords={"time": times, "lat": lat, "lon": lon},
        )
        factors = nino34_scaling_factors(dataset)
        self.assertEqual(list(factors["month"].values), list(range(1, 13)))
        self.assertTrue(np.isfinite(factors.values).all())

        field = dataset["sst"]
        tropav = field.sel(lat=slice(20, -20), lon=slice(0, 360)).mean(dim=("lat", "lon"))
        nino = field.sel(lat=slice(5, -5), lon=slice(190, 240)).mean(dim=("lat", "lon"))
        clm = nino.sel(time=slice("1991-01-01", "2020-12-01")).groupby("time.month").mean("time")
        ninoa = nino.groupby("time.month") - clm
        window = slice("1950-01-01", "2025-12-01")
        raw = ninoa.sel(time=window).groupby("time.month").std("time") / (
            ninoa - tropav
        ).sel(time=window).groupby("time.month").std("time")
        np.testing.assert_allclose(factors.values, raw.values)
        # A constant-per-month offset does not change the standard deviation, so
        # subtracting the raw mean and subtracting the tropical anomaly produce
        # the same factor. The forecast still multiplies the relative anomaly.
        self.assertGreater(float(np.nanmax(np.abs(factors.values - 1))), 0.05)

        scaled = scale_by_calendar_month([1.0, 2.0], [1, 8], factors)
        self.assertAlmostEqual(scaled[0], 1.0 * float(factors.sel(month=1)))
        self.assertAlmostEqual(scaled[1], 2.0 * float(factors.sel(month=8)))


if __name__ == "__main__":
    unittest.main()
