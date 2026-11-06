#!/usr/bin/env python3
"""Oceans page decisions. Color tests do not draw a map or download grids."""

from __future__ import annotations

import os
import unittest
from datetime import date
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
from PIL import Image, ImageDraw

from lib.oceans import (
    ICE_HEX,
    MHW_COLORS,
    NODATA_HEX,
    PAGE_PATH,
    _projection,
    _sample_polar_land,
    _signed_longitude,
    day_from_stamp,
    land_cells,
    layer_text,
    make_view,
    mhw_url,
    mur_url,
    paint,
    parse_latest_time,
    prepare,
    project,
    render_map,
    render_page,
    sample_color,
    legend_for,
    legend_html,
    _draw_legend,
    _font,
    _line_height,
)

ROOT = Path(__file__).resolve().parents[1]


class ColorTests(unittest.TestCase):
    def test_anomaly_zero_is_light_and_the_ends_split_blue_and_red(self) -> None:
        zero = sample_color("anomaly", 0)
        warm = sample_color("anomaly", 3)
        cold = sample_color("anomaly", -3)
        self.assertGreater(min(zero[:3]), 200)
        self.assertGreater(warm[0], warm[2])
        self.assertGreater(cold[2], cold[0])
        self.assertGreater(cold[2], 150)
        self.assertEqual(sample_color("anomaly", -6)[:3], cold[:3])
        self.assertEqual(sample_color("anomaly", 8)[:3], sample_color("anomaly", 5)[:3])

    def test_sst_zero_is_blue_and_thirty_is_warm(self) -> None:
        cold = sample_color("sst", 0)
        hot = sample_color("sst", 30)
        self.assertGreater(cold[2], cold[0])
        self.assertGreater(hot[0], hot[2])
        self.assertGreater(hot[0], cold[0])
        self.assertEqual(sample_color("sst", -9)[:3], sample_color("sst", 0)[:3])
        self.assertEqual(sample_color("sst", 40)[:3], sample_color("sst", 32)[:3])
        self.assertNotEqual(sample_color("sst", 0)[:3], sample_color("sst", 16)[:3])

    def test_ice_is_gray_and_not_a_temperature(self) -> None:
        frozen = paint("sst", np.array([[np.nan]]), ice=np.array([[0.2]]))[0, 0]
        open_water = paint("anomaly", np.array([[np.nan]]), ice=np.array([[0.0]]))[0, 0]
        rgb = tuple(int(round(channel * 255)) for channel in frozen[:3])
        self.assertEqual("#%02x%02x%02x" % rgb, ICE_HEX)
        self.assertEqual(float(frozen[3]), 1)
        self.assertEqual(float(open_water[3]), 0)

    def test_marine_heatwave_colors_match_the_categories(self) -> None:
        for category, color in MHW_COLORS.items():
            pixel = sample_color("heatwaves", category)
            rgb = "#%02x%02x%02x" % pixel[:3]
            self.assertEqual(rgb, color)
            self.assertEqual(pixel[3], 255)
        self.assertEqual(paint("heatwaves", np.array([np.nan, -1, 6, 1.4]))[:, 3].tolist(), [0, 0, 0, 0])
        self.assertEqual(sample_color("heatwaves", 0)[3], 255)

    def test_sea_ice_is_not_treated_as_land(self) -> None:
        sst = np.array([[np.nan, 20.0, np.nan]])
        ice = np.array([[0.8, 0.0, np.nan]])
        self.assertEqual(land_cells(sst, ice).tolist(), [[False, False, True]])


class CopyTests(unittest.TestCase):
    def test_the_utc_day_is_the_analysis_day(self) -> None:
        self.assertEqual(day_from_stamp("2026-11-02T09:00:00Z"), date(2026, 11, 2))
        text = layer_text("anomaly", date(2026, 11, 2))
        self.assertIn("Nov. 2, 2026", text["dek"])
        self.assertIn("2003–2014", text["source"])
        self.assertNotIn("Equal Earth", text["source"])
        self.assertNotIn("projection", text["source"].lower())
        self.assertNotIn("1991", text["source"])
        self.assertNotIn("1991", text["alt"])
        heat = layer_text("heatwaves", date(2026, 11, 3))
        self.assertNotIn("none", heat["source"].lower())
        self.assertNotIn("projection", heat["source"].lower())

    def test_each_layer_names_its_own_day(self) -> None:
        heat = layer_text("heatwaves", date(2026, 11, 3))
        self.assertIn("Marine heatwaves for Nov. 3, 2026", heat["dek"])
        self.assertIn("Coral Reef Watch", heat["source"])
        water = layer_text("sst", date(2026, 11, 2))
        self.assertIn("Sea surface temperatures for Nov. 2, 2026", water["dek"])
        self.assertIn("Sea surface temperatures", water["title"])
        anomaly = layer_text("anomaly", date(2026, 11, 2))
        self.assertIn("Sea surface temperature anomalies", anomaly["title"])
        self.assertNotIn("anomaly for", anomaly["dek"])

    def test_latest_time_and_download_urls(self) -> None:
        stamp = parse_latest_time("time\nUTC\n2026-11-02T09:00:00Z\n")
        self.assertEqual(stamp, "2026-11-02T09:00:00Z")
        mur = mur_url(stamp)
        self.assertIn("analysed_sst", mur)
        self.assertIn("sst_anomaly", mur)
        self.assertIn("sea_ice_fraction", mur)
        self.assertIn("jplMURSST42", mur)
        heat = mhw_url("2026-11-03T12:00:00Z", 5)
        self.assertIn("mhw_5km", heat)
        self.assertIn("heatwave_category", heat)
        self.assertIn("[(-89.975):5:(89.775)]", heat)
        self.assertIn("[(-179.975):5:(179.775)]", heat)

    def test_a_0_to_360_axis_is_rewound_to_signed_longitude(self) -> None:
        longitude = np.array([0.0, 90.0, 180.0, 270.0])
        field = np.array([[10.0, 20.0, 30.0, 40.0]])
        shifted, (out,) = _signed_longitude(longitude, (field,))
        self.assertLess(shifted[0], 0)
        self.assertTrue(np.all(np.diff(shifted) > 0))
        self.assertEqual(out[0, np.where(np.isclose(shifted, -90))[0][0]], 40.0)
        self.assertEqual(out[0, np.where(np.isclose(shifted, 90))[0][0]], 20.0)


class PageTests(unittest.TestCase):
    def test_the_page_switches_three_maps_and_downloads_4k(self) -> None:
        views = [
            make_view("anomaly", date(2026, 11, 2)),
            make_view("sst", date(2026, 11, 2)),
            make_view("heatwaves", date(2026, 11, 3)),
        ]
        html = render_page(views, width=2400, height=1200)
        self.assertIn('href="/climate/oceans" aria-current="page">Oceans</a>', html)
        self.assertIn('rel="canonical" href="https://benweather.com/climate/oceans"', html)
        self.assertIn(">Sea temperature anomalies</button>", html)
        self.assertIn(">Sea temperatures</button>", html)
        self.assertIn(">Marine heatwaves</button>", html)
        self.assertIn(">Download</a>", html)
        self.assertNotIn("Download 4K", html)
        self.assertNotIn("<h2>Oceans</h2>", html)
        self.assertIn("Cooler", html)
        self.assertIn("Warmer", html)
        self.assertIn("+5°C", html)
        self.assertIn("−3°C", html)
        self.assertIn("16°C", html)
        self.assertIn("32°C", html)
        self.assertNotIn("−5°C", html)
        self.assertNotIn("+15°C", html)
        self.assertIn("Sea surface temperature anomalies for Nov. 2, 2026", html)
        self.assertIn("cap-low", html)
        self.assertNotIn(">None<", html)
        self.assertIn('download="ocean-sst-anomaly-2026-11-02.png"', html)
        self.assertIn("/climate/oceans/anomaly.png?d=20261102&r=6", html)
        self.assertIn("/climate/oceans/sst.png?d=20261102&r=6", html)
        self.assertIn("/climate/oceans/heatwaves.png?d=20261103&r=6", html)
        self.assertIn("/climate/oceans/heatwaves-4k.png?d=20261103&r=6", html)
        self.assertIn('left:100.00%;transform:translateX(-50%)\\">32°C', html)
        self.assertIn('left:0.00%;transform:translateX(-50%)\\">0°C', html)
        self.assertIn('left:0.00%;transform:translateX(-50%)\\">−3°C', html)
        self.assertNotIn("translateX(0)", html)
        self.assertNotIn("translateX(-100%)", html)
        self.assertNotIn("+32", html)
        self.assertIn("ocean-sst-2026-11-02.png", html)
        self.assertIn("ocean-marine-heatwaves-2026-11-03.png", html)
        self.assertIn("anomaly-4k.png", html)
        self.assertNotIn("Equal Earth", html)
        self.assertIn("2003–2014", html)
        self.assertNotIn("1991–2020", html)
        self.assertIn('id="ocean-map"', html)
        self.assertIn("width: 100%", html)
        self.assertNotIn("#ocean-map { width: 860px", html)
        self.assertLess(html.index(">Sea temperature anomalies</button>"), html.index(">Sea temperatures</button>"))
        self.assertLess(html.index(">Sea temperatures</button>"), html.index(">Marine heatwaves</button>"))
        self.assertIn("scale mhw", html)
        self.assertIn("#7a0177", html)
        self.assertEqual(PAGE_PATH, "/climate/oceans")

    def test_the_sst_end_tick_is_centered_on_the_bar(self) -> None:
        legend = legend_for("sst")
        self.assertEqual([item["label"] for item in legend["ticks"]], ["0°C", "8°C", "16°C", "24°C", "32°C"])
        self.assertEqual([item["t"] for item in legend["ticks"]], [0.0, 0.25, 0.5, 0.75, 1.0])
        page = legend_html("sst")
        self.assertIn('left:0.00%;transform:translateX(-50%)">0°C', page)
        self.assertIn('left:25.00%;transform:translateX(-50%)">8°C', page)
        self.assertIn('left:100.00%;transform:translateX(-50%)">32°C', page)
        anomaly = legend_html("anomaly")
        self.assertIn('left:0.00%;transform:translateX(-50%)">−3°C', anomaly)
        tick_font = _font("bold", 48)
        edge_font = _font("semibold", 48)
        bar_w = 900
        bar_h = 36
        origin_x = 40
        card = Image.new("RGB", (1400, 420), "white")
        draw = ImageDraw.Draw(card)
        _draw_legend(draw, card, legend, "sst", origin_x, 12, bar_w, bar_h, edge_font, tick_font)
        arrow = max(16, int(round(bar_h * 0.72)))
        bar_right = origin_x + arrow + bar_w
        tick_y = 12 + _line_height(edge_font) + 16 + bar_h + 14
        band = card.crop((0, tick_y, card.width, tick_y + _line_height(tick_font) + 4))
        pixels = np.asarray(band)
        ink = np.any(pixels < 200, axis=2)
        columns = np.where(ink.any(axis=0))[0]
        self.assertGreater(len(columns), 0)
        gaps = np.where(np.diff(columns) > 8)[0]
        starts = [int(columns[0])] + [int(columns[index + 1]) for index in gaps]
        ends = [int(columns[index]) for index in gaps] + [int(columns[-1])]
        self.assertEqual(len(starts), 5)
        bar_left = origin_x + arrow
        self.assertLess(abs((starts[0] + ends[0]) / 2 - bar_left), 3)
        self.assertLess(abs((starts[-1] + ends[-1]) / 2 - bar_right), 3)
        for index in range(4):
            self.assertGreater(starts[index + 1], ends[index])

    def test_nav_copies_list_oceans_in_the_climate_menu(self) -> None:
        for rel in (
            "lib/c3s_globes.py",
            "operational_bundle/bin/operational_lib.sh",
            "operational_bundle/bin/update_s3_portal_standalone.sh",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn('link("/climate/oceans", "Oceans")', text)
            self.assertLess(
                text.index('link("/climate/headlines", "Headlines")'),
                text.index('link("/climate/moisture-trends", "Trends")'),
            )
            self.assertLess(
                text.index('link("/climate/moisture-trends", "Trends")'),
                text.index('link("/climate/oceans", "Oceans")'),
            )

    def test_the_job_runs_once_a_day(self) -> None:
        workflow = (ROOT / ".github/workflows/oceans.yml").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("monthly-updates-oceans", workflow)
        self.assertIn("SCHEDULED_EVENT:", workflow)
        self.assertNotIn("cron:", workflow)
        self.assertNotIn("0,6,12,18", workflow)
        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("PRODUCT_ID: oceans", workflow)
        self.assertIn("s3://bennollweather/climate/oceans", workflow)
        self.assertIn("no-cache, no-store, must-revalidate", workflow)
        self.assertIn("public, max-age=86400", workflow)
        self.assertIn("| Oceans | 20:41 every day |", readme)


class MapTests(unittest.TestCase):
    def test_the_oval_is_centered_on_the_pacific(self) -> None:
        self.assertEqual(_projection().proj4_params["lon_0"], 180)

    def test_equal_earth_corners_are_clear(self) -> None:
        lon = np.linspace(-179.5, 179.5, 180)
        lat = np.linspace(-89.5, 89.5, 90)
        rgba = paint("sst", np.full((lat.size, lon.size), 20.0))
        image = render_map(lon, lat, rgba, width=420, coasts=False)
        self.assertGreater(image.size[0], image.size[1])
        self.assertEqual(image.getpixel((0, 0))[3], 0)
        center = image.getpixel((image.size[0] // 2, image.size[1] // 2))
        self.assertGreater(center[3], 200)
        self.assertGreater(center[0], center[2])

    def test_missing_heatwave_water_is_gray_and_land_stays_marble(self) -> None:
        lon = np.linspace(-179.5, 179.5, 180)
        lat = np.linspace(-89.5, 89.5, 90)
        rgba = paint("heatwaves", np.full((lat.size, lon.size), np.nan))
        frame = prepare(420, coasts=False)
        score = np.where(frame.inside, (frame.lons - 20.0) ** 2 + (frame.lats - 5.0) ** 2, 1e9)
        iy, ix = np.unravel_index(int(np.argmin(score)), score.shape)
        land = np.zeros(frame.inside.shape, dtype=bool)
        land[max(0, iy - 2) : iy + 3, max(0, ix - 2) : ix + 3] = True
        land &= frame.inside
        image = project(frame, rgba, lon, lat, land=land, hole=NODATA_HEX)
        gray = tuple(int(NODATA_HEX[index : index + 2], 16) for index in (1, 3, 5))
        center = image.getpixel((image.size[0] // 2, image.size[1] // 2))
        left, top = frame.origin
        africa = image.getpixel((left + ix, top + iy))
        self.assertEqual(center[3], 255)
        self.assertEqual(center[:3], gray)
        self.assertEqual(africa[3], 255)
        self.assertNotEqual(africa[:3], gray)
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_polar_land_is_antarctica_and_greenland_only(self) -> None:
        lons = np.array([[40.0, 20.0, -42.0, -18.0, -70.0, 20.0, -20.0, 0.0, 180.0, 150.0]])
        lats = np.array([[-75.0, -55.0, 72.0, 65.0, 70.0, 86.0, 70.0, -60.0, -70.0, -65.0]])
        hit = _sample_polar_land(lons, lats, np.ones(lons.shape, dtype=bool))
        self.assertEqual(hit[0].tolist(), [True, False, True, False, False, False, False, False, False, False])

    def test_heatwave_poles_paint_marble_on_the_continents(self) -> None:
        lon = np.linspace(-179.5, 179.5, 180)
        lat = np.linspace(-89.5, 89.5, 90)
        rgba = paint("heatwaves", np.full((lat.size, lon.size), np.nan))
        frame = prepare(640, coasts=False)
        land = np.zeros(frame.inside.shape, dtype=bool)
        image = project(frame, rgba, lon, lat, land=land, hole=NODATA_HEX)
        gray = tuple(int(NODATA_HEX[index : index + 2], 16) for index in (1, 3, 5))
        left, top = frame.origin

        def pixel_at(lat0: float, lon0: float):
            score = np.where(frame.inside, (frame.lons - lon0) ** 2 + (frame.lats - lat0) ** 2, 1e9)
            iy, ix = np.unravel_index(int(np.argmin(score)), score.shape)
            return image.getpixel((left + ix, top + iy)), float(frame.lats[iy, ix]), float(frame.lons[iy, ix])

        antarctica, alat, alon = pixel_at(-78, 40)
        greenland, glat, glon = pixel_at(72, -42)
        southern, slat, slon = pixel_at(-55, 20)
        arctic, rlat, rlon = pixel_at(86, 20)
        self.assertLess(abs(alat + 78), 3)
        self.assertLess(abs(alon - 40), 5)
        self.assertEqual(antarctica[3], 255)
        self.assertGreater(min(antarctica[:3]), 200)
        self.assertNotEqual(antarctica[:3], gray)
        self.assertLess(abs(glat - 72), 3)
        self.assertLess(abs(glon + 42), 6)
        self.assertEqual(greenland[3], 255)
        self.assertGreater(min(greenland[:3]), 180)
        self.assertNotEqual(greenland[:3], gray)
        self.assertLess(abs(slat + 55), 3)
        self.assertEqual(southern[:3], gray)
        self.assertLess(abs(rlat - 86), 3)
        self.assertEqual(arctic[:3], gray)
        sea_ice, ilat, ilon = pixel_at(-70, 180)
        self.assertLess(abs(ilat + 70), 3)
        self.assertLess(min(abs(ilon - 180), abs(ilon + 180)), 6)
        self.assertEqual(sea_ice[:3], gray)
        self.assertEqual(image.getpixel((0, 0))[3], 0)


if __name__ == "__main__":
    unittest.main()
