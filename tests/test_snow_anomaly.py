#!/usr/bin/env python3
"""Snowfall anomaly page decisions. These do not download NOAA files."""

from __future__ import annotations

import base64
import json
import os
import unittest
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

from PIL import Image

os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import xarray as xr

from lib.snow_anomaly import (
    CLIMATOLOGY_FIRST_YEAR,
    COLORS,
    OVER,
    SCALE_MAX,
    ChosenDay,
    SeasonRank,
    choose_target,
    ABOVE_LABEL,
    color_for,
    color_index,
    coverage_shares,
    domain_percent,
    format_span,
    nohrsc_url,
    pack_field,
    percent_field,
    rank_seasons,
    render_page,
    season_name,
    source_line,
)

ROOT = Path(__file__).resolve().parents[1]


def _grid(values) -> xr.DataArray:
    array = np.asarray(values, dtype=float)
    return xr.DataArray(
        array,
        dims=("lat", "lon"),
        coords={"lat": np.linspace(40, 35, array.shape[0]), "lon": np.linspace(-100, -90, array.shape[1])},
    )


def _field(values, lat, lon) -> xr.DataArray:
    return xr.DataArray(
        np.asarray(values, dtype=float),
        dims=("lat", "lon"),
        coords={"lat": np.asarray(lat, dtype=float), "lon": np.asarray(lon, dtype=float)},
    )


class UrlTests(unittest.TestCase):
    def test_november_file_stays_in_the_same_year(self):
        self.assertEqual(
            nohrsc_url(2015, date(2026, 11, 4)),
            "https://www.nohrsc.noaa.gov/snowfall/data/201511/"
            "sfav2_CONUS_2015093012_to_2015110412.nc",
        )

    def test_january_file_starts_the_previous_september(self):
        self.assertEqual(
            nohrsc_url(2016, date(2027, 1, 15)),
            "https://www.nohrsc.noaa.gov/snowfall/data/201601/"
            "sfav2_CONUS_2015093012_to_2016011512.nc",
        )


class ChooseTests(unittest.TestCase):
    def test_today_is_used_when_every_year_exists(self):
        chosen = choose_target(date(2026, 11, 5), lambda url: True)
        self.assertEqual(chosen.target, date(2026, 11, 5))
        self.assertEqual(chosen.missing_years, ())
        self.assertEqual(chosen.climatology_years[0], CLIMATOLOGY_FIRST_YEAR)
        self.assertEqual(chosen.climatology_years[-1], 2025)
        self.assertNotIn(2026, chosen.climatology_years)

    def test_a_day_missing_too_many_years_steps_back(self):
        def exists(url: str) -> bool:
            year = int(url.split("sfav2_CONUS_")[1][:4])
            return not (year in (2010, 2011, 2012, 2013) and url.endswith("110512.nc"))

        chosen = choose_target(date(2026, 11, 5), exists, lookback_days=5)
        self.assertEqual(chosen.target, date(2026, 11, 4))
        self.assertEqual(chosen.missing_years, ())

    def test_a_missing_today_file_falls_through_to_the_previous_day(self):
        today = date(2026, 11, 5)
        self.assertEqual(
            nohrsc_url(today.year, today),
            "https://www.nohrsc.noaa.gov/snowfall/data/202611/"
            "sfav2_CONUS_2026093012_to_2026110512.nc",
        )
        chosen = choose_target(
            today,
            lambda url: "to_2026110512" not in url,
            lookback_days=3,
        )
        self.assertEqual(chosen.target, date(2026, 11, 4))
        self.assertEqual(chosen.current_year, 2026)

    def test_no_usable_day_fails(self):
        with self.assertRaises(RuntimeError):
            choose_target(date(2026, 11, 5), lambda url: False, lookback_days=2)


class FieldTests(unittest.TestCase):
    def test_thin_snow_stays_blank_and_a_real_average_is_scored(self):
        clim = _grid([[0.2, 2.0], [3.0, np.nan]])
        current = _grid([[5.0, 1.0], [0.0, 1.0]])
        perc = percent_field(current, clim)
        self.assertTrue(np.isnan(perc.values[0, 0]))
        self.assertEqual(perc.values[0, 1], 50.0)
        self.assertEqual(perc.values[1, 0], 0.0)
        self.assertTrue(np.isnan(perc.values[1, 1]))
        self.assertEqual(domain_percent(current, clim), 25)

    def test_rank_one_is_the_highest_percent(self):
        rows = rank_seasons([(2024, 80), (2025, 120.2), (2026, 120.2)], 2026)
        self.assertEqual([row.year for row in rows], [2026, 2025, 2024])
        self.assertEqual(rows[0].rank, 1)
        self.assertTrue(rows[0].current)
        self.assertEqual(rows[0].percent, 120)
        self.assertEqual(rows[-1].rank, 3)

    def test_coverage_counts_one_hundred_percent_and_weights_area(self):
        lat = np.array([30.0, 50.0])
        lon = np.array([-100.0, -90.0])
        clim = _field([[2.0, 2.0], [2.0, 2.0]], lat, lon)
        current = _field([[3.0, 3.0], [1.0, 2.0]], lat, lon)
        grid = (lat, lon, np.array([[100.0, 50.0], [10.0, 40.0]]))
        land = np.array([[True, False], [True, True]])
        population, area = coverage_shares(current, clim, grid=grid, land=land)
        self.assertEqual(population, int(np.round(140 / 150 * 100)))
        south = np.cos(np.deg2rad(30.0))
        north = np.cos(np.deg2rad(50.0))
        self.assertEqual(area, int(np.round((south + north) / (south + 2 * north) * 100)))
        self.assertGreater(area, 50)

    def test_just_under_one_hundred_percent_is_not_above_average(self):
        lat = np.array([35.0, 40.0])
        lon = np.array([-100.0, -90.0])
        clim = _field([[2.0, 2.0], [2.0, 2.0]], lat, lon)
        current = _field([[1.998, 2.0], [2.0, 2.0]], lat, lon)
        grid = (lat, lon, np.ones((2, 2)))
        land = np.ones((2, 2), dtype=bool)
        population, area = coverage_shares(current, clim, grid=grid, land=land)
        self.assertEqual(population, 75)
        self.assertEqual(area, int(np.round(
            (np.cos(np.deg2rad(40.0)) * 2 + np.cos(np.deg2rad(35.0)))
            / (np.cos(np.deg2rad(35.0)) * 2 + np.cos(np.deg2rad(40.0)) * 2)
            * 100
        )))

    def test_scale_runs_from_brown_to_blue(self):
        def rgb(value: str) -> tuple[int, int, int]:
            return tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))

        low_r, _low_g, low_b = rgb(COLORS[0])
        high_r, _high_g, high_b = rgb(COLORS[-1])
        over_r, _over_g, over_b = rgb(OVER)
        self.assertGreater(low_r, low_b)
        self.assertGreater(high_b, high_r)
        self.assertGreater(over_b, over_r)
        self.assertEqual(len(COLORS), 12)
        self.assertEqual(color_for(0), COLORS[0])
        self.assertEqual(color_index(24.9), 0)
        self.assertEqual(color_index(25), 1)
        self.assertEqual(color_index(99.9), 3)
        self.assertEqual(color_index(100), 4)
        self.assertEqual(color_for(100), "#D4E8F4")
        self.assertEqual(color_for(75), "#F3E6C4")
        tan_r, _tan_g, tan_b = rgb(color_for(99))
        blue_r, _blue_g, blue_b = rgb(color_for(100))
        self.assertGreater(tan_r, tan_b)
        self.assertGreater(blue_b, blue_r)
        self.assertEqual(color_for(50), COLORS[color_index(50)])
        self.assertNotEqual(color_for(40), color_for(180))
        self.assertEqual(color_for(299), COLORS[-1])
        self.assertEqual(color_for(SCALE_MAX), OVER)

    def test_packed_field_keeps_blank_cells_and_the_top_bin(self):
        field = percent_field(
            _grid([[0.0, 4.0], [1.0, 9.0]]),
            _grid([[2.0, 2.0], [2.0, 2.0]]),
        )
        meta, encoded = pack_field(field)
        image = Image.open(BytesIO(base64.b64decode(encoded)))
        self.assertEqual((meta["nlon"], meta["nlat"]), image.size)
        self.assertEqual(list(np.asarray(image).ravel()), [1, color_index(200) + 1, color_index(50) + 1, color_index(450) + 1])


class PageTests(unittest.TestCase):
    def test_dates_use_ap_style_and_an_en_dash(self):
        self.assertEqual(format_span(date(2026, 9, 30), date(2026, 11, 4)), "Sept. 30–Nov. 4, 2026")
        self.assertEqual(format_span(date(2026, 9, 30), date(2027, 1, 8)), "Sept. 30, 2026–Jan. 8, 2027")
        self.assertEqual(season_name(2026, date(2026, 11, 4)), "2026-27")
        self.assertEqual(season_name(2008, date(2008, 11, 4)), "2008-09")
        self.assertEqual(season_name(2027, date(2027, 1, 8)), "2026-27")
        self.assertEqual(season_name(2016, date(2016, 1, 8)), "2015-16")

    def test_page_carries_the_rank_and_the_outlook_link(self):
        rows = rank_seasons([(2008, 70), (2025, 110), (2026, 90)], 2026)
        field = percent_field(_grid([[1.0, 4.0]]), _grid([[2.0, 2.0]]))
        meta, encoded = pack_field(field)
        pop_rows = rank_seasons([(2008, 20), (2025, 40), (2026, 30)], 2026)
        land_rows = rank_seasons([(2008, 10), (2025, 55), (2026, 25)], 2026)
        html = render_page(
            span="Sept. 30–Nov. 4, 2026",
            rank_label="Rank 2 of 3 · 90% of average",
            rows=rows,
            meta=meta,
            field=encoded,
            alt="Snowfall percentage of average from Sept. 30–Nov. 4, 2026.",
            source=source_line(tuple(range(2008, 2026))),
            on=date(2026, 11, 4),
            pop_rows=pop_rows,
            land_rows=land_rows,
        )
        nav = html.split('<nav aria-label="Sections">', 1)[1].split("</nav>", 1)[0]
        long_range = nav.split("<summary>Long range</summary>", 1)[1].split("</details>", 1)[0]
        self.assertIn('<link rel="canonical" href="https://benweather.com/weather/snow-anomaly">', html)
        self.assertIn("Rank 2 of 3 · 90% of average", html)
        self.assertIn("Sept. 30–Nov. 4, 2026", html)
        self.assertIn('id="snow-map"', html)
        self.assertIn(">Download<", html)
        self.assertIn(">Percentage of average snowfall across the U.S.</h2>", html)
        self.assertNotIn("Percentage of average snowfall from", html)
        self.assertIn("Percentage of U.S. population with above-average snowfall", html)
        self.assertIn("Percentage of U.S. land area with above-average snowfall", html)
        self.assertIn('<section class="notes" hidden>', html)
        notes = html.split('<section class="notes" hidden>', 1)[1].split("</section>", 1)[0]
        self.assertNotIn("NOAA/NOHRSC", notes)
        self.assertIn(
            "NOAA/NOHRSC season-to-date snowfall, compared with the "
            "2008–2025 average where that average is at least 1 inch.",
            html,
        )
        self.assertIn('data-file="snowfall-percent-of-average-by-season.png"', html)
        self.assertIn('data-file="snowfall-population-above-average.png"', html)
        self.assertIn('data-file="snowfall-land-area-above-average.png"', html)
        self.assertIn('data-credit="Data: NOAA/NOHRSC"', html)
        self.assertIn("From Sept. 30 to Nov. 4, 2026", html)
        self.assertIn("Population where the average is at least 1 inch.", html)
        self.assertNotIn("2020 population", html)
        self.assertIn("Land area where the average is at least 1 inch.", html)
        self.assertIn("li.now .year { color: #1A548E;", html)
        self.assertIn('data-width="82"', html)
        self.assertIn('data-width="30"', html)
        self.assertIn('data-width="55"', html)
        self.assertIn(f'data-color="{ABOVE_LABEL}"', html)
        self.assertIn("function paintRankCard", html)
        self.assertIn(encoded[:40], html)
        self.assertNotIn("snow_anomaly.png", html)
        latest = nav.split("<summary>Latest posts</summary>", 1)[1].split("</details>", 1)[0]
        weather_menu = nav.split("<summary>Weather</summary>", 1)[1].split("</details>", 1)[0]
        self.assertIn('href="/latest_posts"', latest)
        self.assertIn('href="/articles"', latest)
        self.assertIn('href="/newsletter"', latest)
        self.assertIn("<summary>Snow</summary>", weather_menu)
        self.assertIn('href="/weather/snow-anomaly" aria-current="page">Anomaly</a>', weather_menu)
        self.assertIn('href="/weather/snow-forecast">Forecast</a>', weather_menu)
        self.assertNotIn(">Snow</a>", weather_menu)
        self.assertLess(nav.find('href="/weather/snow-anomaly"'), nav.find("<summary>Long range</summary>"))
        self.assertNotIn("snow-anomaly", long_range)
        self.assertNotIn("snow-forecast", long_range)
        self.assertIn('href="/graphics/snow">Snow</a>', long_range)
        self.assertIn('href="/weather/snow-anomaly" aria-current="page">Anomaly</a>', html)
        self.assertNotIn("nav .panel { position: static", html)
        self.assertIn("nav > details.menu:last-of-type > .panel { left: auto; right: 0; }", html)
        self.assertIn("nav > details.menu { position: static; }", html)
        self.assertIn("nav > details.menu:last-of-type > .panel {\n        left: 0;\n        right: 0;", html)
        self.assertIn('class="break" style="left:100.0000%">300%+</span>', html)
        self.assertIn(".ticks span.break", html)
        self.assertIn('class="now"', html)
        self.assertIn(">2008-09<", html)
        self.assertIn(">2025-26<", html)
        self.assertIn(">2026-27<", html)
        self.assertIn("2008–2025", html)
        self.assertIn("left:33.3333%", html)
        self.assertIn('class="minor" style="left:16.6667%"', html)
        self.assertIn(".ticks span.minor { display: none; }", html)
        self.assertIn("#D4E8F4", html)
        self.assertIn("#F3E6C4", html)
        self.assertIn('id="map-scroll"', html)
        self.assertIn("const width = 3840;", html)
        self.assertIn("tick: 48", html)
        payload = json.loads(html.split("const DATA = ", 1)[1].split(";", 1)[0])
        labels = {row[0]: row for row in payload["labels"]}
        self.assertEqual(labels["LA."][1], -92.55)
        self.assertEqual(labels["LA."][2], 31.3)
        self.assertNotEqual(labels["N.H."][1], labels["N.H."][4])
        self.assertEqual(labels["MICH."][1], labels["MICH."][4])
        self.assertNotIn("ctx.shadowBlur", html)
        self.assertNotIn("shadowOffsetY", html)
        self.assertNotIn("countryHalo", html)
        self.assertIn("function landShadow", html)
        self.assertNotIn("function blurAlpha", html)
        self.assertNotIn("margin / 3", html)
        self.assertIn("const dx = 0.025 * pxPerInch;", html)
        self.assertIn("const dy = 0.04 * pxPerInch;", html)
        self.assertIn("[8, 0.012]", html)
        self.assertIn('sctx.fillStyle = "#000";', html)
        self.assertNotIn("rgba(236, 238, 242", html)
        self.assertNotIn('bctx.filter = "blur(', html)
        self.assertNotIn("line * 2.3", html)
        self.assertNotIn("southernChains", html)
        self.assertNotIn('ctx.rect(box.x, box.y, box.w, box.h);\n    trace(ctx, SNOW_BASE.land, project, true);\n    ctx.fillStyle = ground;\n    ctx.fill("evenodd");', html)
        self.assertIn('SNOW_BASE.lakes.forEach((poly) => {\n        trace(ctx, [poly], project);\n        ctx.fill("evenodd");', html)
        self.assertIn('trace(ctx, [poly], project, true);\n      });\n      ctx.clip("evenodd");', html)
        self.assertIn("ctx.lineWidth = Math.max(2.5, box.w / 450);", html)
        self.assertNotIn("ctx.lineWidth = Math.max(1.25, box.w / 900);", html)
        self.assertIn("onWater(x1, y1) && onWater(x2, y2) && onWater(midLon, midLat)", html)
        self.assertIn("function interiorEdge", html)
        self.assertIn("if (len < 0.4) return false;", html)
        self.assertNotIn("nearSegment(lakeIndex, midLon, midLat, 0.08)", html)
        self.assertIn("snow_basemap.js?v=4", html)
        self.assertNotIn("lines.lakes, project);\n      ctx.clip", html)
        self.assertIn('style="left:6.2500%">0.5–1 in.</span>', html)
        self.assertNotIn('class="unit"', html)
        self.assertIn("font-size: 15px;", html)
        self.assertIn(".snow-scale .ticks { margin-right: 0; font-size: 14px; }", html)
        self.assertIn('ctx.font = "700 " + tickSize + "px \\"Libre Franklin\\", sans-serif";\n    ctx.textAlign = "center";\n    ticks.forEach', html)
        self.assertIn('measure.font = "700 " + fonts.tick', html)
        self.assertNotIn('ctx.textAlign = "left";\n      ctx.fillText(label, x, tickY);', html)
        self.assertEqual(payload["frame"], [-126.55, -65.38, 23.05, 50.92])
        self.assertEqual(payload["extent"], [-125.6, -66.5, 24.0, 49.8])
        self.assertNotIn("SNOW_BASE.lakes.forEach((poly) => {\n      trace(ctx, [poly], project);\n      ctx.fillStyle = \"#fff\";", html)
        self.assertNotIn("Snowfall heatmaps", html)
        self.assertIsInstance(rows[0], SeasonRank)

    def test_forecast_buttons_keep_the_anomaly_and_add_a_pin(self):
        from lib.snow_forecast import MODELS, make_view

        rows = rank_seasons([(2008, 70), (2025, 110), (2026, 90)], 2026)
        field = percent_field(_grid([[1.0, 4.0]]), _grid([[2.0, 2.0]]))
        meta, encoded = pack_field(field)
        lat = np.array([40.0, 35.0])
        lon = np.array([-100.0, -90.0])
        inches = np.array([[0.2, 12.4], [3.0, 1.0]])
        land = np.ones((2, 2))
        cycle = datetime(2026, 11, 4, 18, 0, 0)
        forecasts = {
            spec["key"]: make_view(spec, cycle, inches, lat, lon, land)
            for spec in MODELS
        }
        html = render_page(
            span="Sept. 30–Nov. 4, 2026",
            rank_label="Rank 2 of 3 · 90% of average",
            rows=rows,
            meta=meta,
            field=encoded,
            alt="Snowfall percentage of average from Sept. 30–Nov. 4, 2026.",
            source=source_line(tuple(range(2008, 2026))),
            on=date(2026, 11, 4),
            forecasts=forecasts,
        )
        payload = json.loads(html.split("const DATA = ", 1)[1].split(";", 1)[0])
        self.assertEqual(list(payload["views"]), ["anomaly", "ecmwf", "aifs"])
        self.assertEqual(payload["labels"][0][0], "WASH.")
        self.assertEqual(payload["views"]["anomaly"]["kind"], "anomaly")
        self.assertTrue(payload["views"]["ecmwf"]["smooth"])
        self.assertEqual(payload["views"]["ecmwf"]["pin"]["label"], "12.4 in.")
        self.assertEqual(
            payload["views"]["ecmwf"]["span"],
            "From 1 p.m. Nov. 4 through 1 p.m. Nov. 11, 2026 ET",
        )
        self.assertEqual(payload["views"]["ecmwf"]["title"], "Weekly snowfall forecast")
        self.assertEqual(payload["views"]["ecmwf"]["rank"], "Maximum 12.4 in.")
        self.assertIn("Maximum 12.4 in.", payload["views"]["ecmwf"]["rank"])
        self.assertIn("ECMWF-AIFS", html)
        self.assertIn('href="/weather/snow-anomaly" aria-current="page">Anomaly</a>', html)
        self.assertIn('href="/weather/snow-forecast">Forecast</a>', html)
        self.assertIn('location.replace("/weather/snow-forecast"', html)
        forecast_html = render_page(
            span="Sept. 30–Nov. 4, 2026",
            rank_label="Rank 2 of 3 · 90% of average",
            rows=rows,
            meta=meta,
            field=encoded,
            alt="Snowfall percentage of average from Sept. 30–Nov. 4, 2026.",
            source=source_line(tuple(range(2008, 2026))),
            on=date(2026, 11, 4),
            forecasts=forecasts,
            kind="forecast",
            pop_rows=rank_seasons([(2008, 20), (2026, 30)], 2026),
            land_rows=rank_seasons([(2008, 10), (2026, 25)], 2026),
        )
        self.assertIn('<link rel="canonical" href="https://benweather.com/weather/snow-forecast">', forecast_html)
        self.assertIn("<title>Weekly snowfall forecast</title>", forecast_html)
        self.assertIn('<h2 id="snow-title">Weekly snowfall forecast</h2>', forecast_html)
        self.assertIn('href="/weather/snow-forecast" aria-current="page">Forecast</a>', forecast_html)
        self.assertIn('href="/weather/snow-anomaly">Anomaly</a>', forecast_html)
        self.assertNotIn('href="/weather/snow-anomaly" aria-current="page"', forecast_html)
        self.assertIn(
            '<p class="dek" id="snow-span">From 1 p.m. Nov. 4 through 1 p.m. Nov. 11, 2026 ET</p>',
            forecast_html,
        )
        self.assertNotIn("Next 7 days", forecast_html.split('id="snow-span"', 1)[1].split("</p>", 1)[0])
        rank_line = forecast_html.split('id="snow-rank"', 1)[1].split("</p>", 1)[0]
        self.assertIn("Maximum 12.4 in.", rank_line)
        self.assertNotIn("through", rank_line)
        self.assertIn('id="anomaly-ranks" hidden', forecast_html)
        self.assertNotIn("Percentage of average snowfall across the U.S.", forecast_html)
        self.assertNotIn("Percentage of U.S. population with above-average snowfall", forecast_html)
        self.assertIn('<section class="notes">', forecast_html)
        self.assertNotIn('<section class="notes" hidden>', forecast_html)
        self.assertNotIn("snowfall-population-above-average.png", forecast_html)
        self.assertNotIn("Data: NOAA/NOHRSC", forecast_html)
        self.assertIn('id="anomaly-scale" hidden', forecast_html)
        self.assertIn('id="snow-scale">', forecast_html)
        self.assertIn('<div class="legend-track"><div class="swatches">', forecast_html)
        self.assertIn(".snow-scale .legend-track { width: max(100%, var(--legend-min, 100%));", forecast_html)
        self.assertIn('id="snow-controls">', forecast_html)
        self.assertIn('id="model-row">', forecast_html)
        self.assertIn("Rank 2 of 3 · 90% of average", forecast_html)
        self.assertIn("0.5–1 in.", html)
        self.assertIn("24+", html)
        self.assertIn('id="snow-scale"', html)
        self.assertNotIn('id="snow-menu"', html)
        self.assertNotIn('data-view="forecast"', html)
        self.assertNotIn('data-view="anomaly"', html)
        self.assertIn('id="model-row"', html)
        self.assertNotIn('id="view-row"', html)
        self.assertNotIn(">Inches<", html)
        self.assertNotIn("bezierCurveTo", html)
        self.assertIn("10:1 snow-to-liquid ratio", html)
        self.assertIn("spec.smooth !== false", html)
        self.assertIn(forecasts["aifs"]["field"][:40], html)
        self.assertIn("const width = 3840;", html)
        self.assertIn("tick: 48", html)

    def test_gallery_rebuild_does_not_replace_the_snow_key(self):
        portal = (ROOT / "operational_bundle/bin/update_s3_portal_standalone.sh").read_text(encoding="utf-8")
        library = (ROOT / "operational_bundle/bin/operational_lib.sh").read_text(encoding="utf-8")
        nav = (ROOT / "lib/c3s_globes.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/snow-anomaly.yml").read_text(encoding="utf-8")
        self.assertNotIn('upload_html "$html_file" "snow"', portal)
        self.assertIn('"copernicus_imagery/snow": "/graphics/snow"', portal)
        self.assertIn('"copernicus_imagery/snow": "/graphics/snow"', library)
        self.assertIn('link("/graphics/snow", "Snow")', nav)
        self.assertIn('link("/weather/snow-anomaly", "Anomaly")', nav)
        self.assertIn('link("/weather/snow-forecast", "Forecast")', nav)
        self.assertNotIn("nav .panel { position: static", portal)
        self.assertNotIn("nav .panel { position: static", library)
        self.assertIn("monthly-updates-snow-anomaly", workflow)
        self.assertIn("SCHEDULED_EVENT:", workflow)
        self.assertNotIn("cron:", workflow)
        self.assertNotIn("41 15 * * *", workflow)
        self.assertNotIn("41 0,6,12,18 * * *", workflow)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("| Snowfall percentage of average | 18:41 every day |", readme)
        self.assertIn("| Predicted snowfall | 02:41, 10:41, 14:41, and 22:41 every day |", readme)
        self.assertIn("EventBridge starts the daily snow, rainfall, temperature, and ocean jobs.", readme)
        requirements = (ROOT / "requirements/maps.txt").read_text(encoding="utf-8")
        self.assertIn("ecmwf-opendata", requirements)
        self.assertIn("cfgrib", requirements)
        self.assertIn("ecmwflibs", requirements)
        self.assertIn("s3://bennollweather/snow-anomaly", workflow)
        self.assertIn("s3://bennollweather/snow-forecast", workflow)
        self.assertIn("s3://bennollweather/snow", workflow)
        self.assertIn("climate_imagery/snow_basemap.js", workflow)
        self.assertIn('"snow_anomaly.png"', portal)
        self.assertIn('"snow_counties.png"', portal)
        self.assertIn('"snow_terrain.jpg"', portal)
        self.assertNotIn("snow_anomaly.png", workflow)
        self.assertIn("workflow_dispatch", workflow)

    def test_a_gap_in_the_record_is_named(self):
        text = source_line((2009, 2010, 2012))
        self.assertIn("3 seasons from 2009 to 2012", text)


class BasemapTests(unittest.TestCase):
    def test_basemap_assets_are_present(self):
        script = (ROOT / "lib" / "snow_basemap.js").read_text(encoding="utf-8")
        self.assertTrue(script.startswith("const SNOW_BASE = "))
        self.assertIn('"lakes":', script)
        self.assertIn("snow_terrain.jpg", script)
        self.assertLess(len(script), 1_200_000)
        self.assertGreater((ROOT / "lib" / "snow_terrain.jpg").stat().st_size, 10_000)
        self.assertGreater((ROOT / "lib" / "snow_counties.png").stat().st_size, 10_000)

    def test_great_lakes_are_cut_back_to_the_united_states_shore(self):
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union
        from shapely.validation import make_valid

        script = (ROOT / "lib" / "snow_basemap.js").read_text(encoding="utf-8")
        data = json.loads(script[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))

        def to_poly(poly):
            rings = []
            for ring in poly:
                coords = list(zip(ring[0::2], ring[1::2]))
                if len(coords) >= 4:
                    rings.append(coords)
            if not rings:
                return None
            geom = Polygon(rings[0], rings[1:] if len(rings) > 1 else None)
            return geom if geom.is_valid else make_valid(geom)

        land = unary_union([geom for geom in (to_poly(poly) for poly in data["land"]) if geom])
        water = {
            "Superior": (-87.2, 47.7),
            "Michigan": (-87.0, 44.0),
            "Huron": (-82.4, 44.6),
            "Erie": (-81.2, 42.2),
            "Ontario": (-77.9, 43.6),
            "Georgian Bay": (-80.7, 45.3),
            "Saint Clair": (-82.7, 42.45),
        }
        lakes = unary_union([geom for geom in (to_poly(poly) for poly in data["lakes"]) if geom])
        self.assertTrue(lakes.covers(Point(-82.7, 42.45)))
        for name, (lon, lat) in water.items():
            self.assertFalse(land.covers(Point(lon, lat)), name)
        self.assertTrue(land.covers(Point(-84.15, 43.55)))
        self.assertTrue(land.covers(Point(-92.55, 31.3)))

    def test_the_frame_leaves_room_around_the_country(self):
        from lib.snow_anomaly import EXTENT, FRAME, land_bounds

        script = (ROOT / "lib" / "snow_basemap.js").read_text(encoding="utf-8")
        data = json.loads(script[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))
        terrain = data["terrainExtent"]
        self.assertLess(terrain[0], FRAME[0])
        self.assertGreater(terrain[1], FRAME[1])
        self.assertLess(terrain[2], FRAME[2])
        self.assertGreater(terrain[3], FRAME[3])
        west, east, south, north = land_bounds()
        self.assertGreater(west - FRAME[0], 1.4)
        self.assertGreater(FRAME[1] - east, 1.4)
        self.assertGreater(south - FRAME[2], 1.4)
        self.assertGreater(FRAME[3] - north, 1.4)
        self.assertEqual(EXTENT, (-125.6, -66.5, 24.0, 49.8))

    def test_the_wisconsin_minnesota_line_meets_lake_superior(self):
        from shapely.geometry import Point

        script = (ROOT / "lib" / "snow_basemap.js").read_text(encoding="utf-8")
        data = json.loads(script[len("const SNOW_BASE = ") :].rstrip().rstrip(";"))
        mouth = Point(-92.110, 46.769)
        closest = min(
            Point(lon, lat).distance(mouth)
            for poly in data["states"]
            for ring in poly
            for lon, lat in zip(ring[0::2], ring[1::2])
            if abs(lon + 92.11) < 0.4 and abs(lat - 46.77) < 0.4
        )
        self.assertLess(closest, 0.005)


if __name__ == "__main__":
    unittest.main()
