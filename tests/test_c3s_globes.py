#!/usr/bin/env python3
"""Period, vote, and story tests for the seasonal globes. These do not call CDS."""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import numpy as np

from lib.c3s_globes import (
    CENTRES,
    FIELDS,
    OCEAN_STRENGTH,
    SNOW_INCHES,
    _choose,
    _normalize_system,
    _season_month,
    _to_grid,
    close_empty_meridian,
    field_request,
    field_shares,
    lat_index,
    lon_index,
    majority,
    match_centre,
    model_name,
    model_votes,
    pack_bits,
    headline_title,
    period_label,
    render_page,
    resolve_init,
    season_months,
    select_models,
    story_lines,
)


def shares(globe_above, globe_below, tropics_above, tropics_below, north_above=0.0, north_below=0.0, models=9):
    return {
        "globe_above": globe_above,
        "globe_below": globe_below,
        "tropics_above": tropics_above,
        "tropics_below": tropics_below,
        "north_above": north_above,
        "north_below": north_below,
        "models": models,
    }


class GlobePeriodTests(unittest.TestCase):
    def test_early_november_uses_the_october_initialization(self) -> None:
        init = resolve_init(date(2026, 11, 2), "")
        self.assertEqual(init, date(2026, 10, 1))
        months = season_months(init)
        self.assertEqual([f"{item:%Y-%m}" for item in months], ["2026-11", "2026-12", "2027-01"])
        self.assertEqual(period_label(months), "Nov. 2026-Jan. 2027")

    def test_the_tenth_uses_the_new_initialization(self) -> None:
        init = resolve_init(date(2026, 11, 10), "")
        self.assertEqual(init, date(2026, 11, 1))
        self.assertEqual(period_label(season_months(init)), "Dec. 2026-Feb. 2027")

    def test_explicit_init_overrides_the_calendar(self) -> None:
        init = resolve_init(date(2026, 11, 2), "2026-11")
        self.assertEqual(period_label(season_months(init)), "Dec. 2026-Feb. 2027")

    def test_same_year_range_keeps_one_year(self) -> None:
        self.assertEqual(period_label(season_months(date(2027, 1, 1))), "Feb.-April 2027")

    def test_headline_names_the_first_and_last_month(self) -> None:
        self.assertEqual(
            headline_title(season_months(date(2026, 10, 1))),
            "Climate headlines from Nov. 2026 to Jan. 2027",
        )
        self.assertEqual(
            headline_title(season_months(date(2027, 1, 1))),
            "Climate headlines from Feb. 2027 to April 2027",
        )


class GlobeVoteTests(unittest.TestCase):
    def test_nearest_cell(self) -> None:
        self.assertEqual(lat_index(41.7), 48)
        self.assertEqual(lon_index(-73.9), 286)
        self.assertEqual(lon_index(179.6), 180)
        self.assertEqual(lon_index(359.6), 0)
        self.assertEqual(lat_index(90), 0)
        self.assertEqual(lat_index(-90), 180)

    def test_tie_stays_neutral(self) -> None:
        above = np.zeros((2, 1, 2), dtype=bool)
        voted = np.ones((2, 1, 2), dtype=bool)
        above[:, 0, 0] = True
        above[0, 0, 1] = True
        sign, counts, valid = majority(above, voted)
        self.assertEqual(int(sign[0, 0]), 1)
        self.assertEqual(int(sign[0, 1]), 0)
        self.assertEqual(int(counts[0, 0]), 2)
        self.assertEqual(int(valid[0, 1]), 2)

    def test_story_comes_from_the_areas(self) -> None:
        lines = story_lines({
            "temp": shares(0.70, 0.15, 0.80, 0.10),
            "rain": shares(0.40, 0.30, 0.62, 0.20),
            "dew": shares(0.40, 0.30, 0.66, 0.18),
            "snow": shares(0.20, 0.20, 0.10, 0.10, 0.15, 0.70),
            "mslp": shares(0.58, 0.22, 0.40, 0.30),
        })
        self.assertEqual(lines, [
            "Most of the planet is forecast warmer than average, including most of the tropics.",
            "Most of the tropics are forecast wetter and more humid than average.",
            "Most of the northern land is forecast less snow than average, and higher pressure is the more common forecast.",
        ])
        self.assertNotIn("Most models keep the tropics", " ".join(lines))

    def test_page_keeps_ocean_opacity_out_of_the_votes(self) -> None:
        payload = {
            "init": "2026-10",
            "period": "Nov. 2026-Jan. 2027",
            "months": ["2026-11", "2026-12", "2027-01"],
            "grid": {"nlat": 2, "nlon": 2},
            "land": "AQIDBA==",
            "oceanStrength": OCEAN_STRENGTH,
            "fields": [],
            "story": ["Most of the planet is forecast warmer than average."],
        }
        html = render_page(payload)
        self.assertIn("Climate headlines from Nov. 2026 to Jan. 2027", html)
        self.assertIn('loadJson("/climate/data.json")', html)
        self.assertIn('loadJson("/climate/coast.json")', html)
        self.assertIn('loadJson("/climate/land.json")', html)
        self.assertIn('loadJson("/climate/borders.json")', html)
        self.assertIn('loadJson("/climate/cities.json")', html)
        boot = html.split("function boot()", 1)[1].split("boot();", 1)[0]
        promise = boot.split("Promise.all([", 1)[1].split("])", 1)[0]
        self.assertNotIn("cities.json", promise)
        self.assertIn('loadJson("/climate/data.json")', promise)
        self.assertIn('loadJson("/climate/coast.json")', promise)
        self.assertIn('loadJson("/climate/land.json")', promise)
        self.assertIn('loadJson("/climate/borders.json")', promise)
        self.assertIn("citiesArrived", html)
        self.assertIn("pendingCityQuery", html)
        self.assertIn("Math.max(480, Math.min(fullWidth, Math.round(css * dpr)))", html)
        self.assertNotIn(") : fullWidth", html)
        self.assertNotIn("__PAYLOAD__", html)
        self.assertIn(
            "Discover the climate headlines for your area, based on strong forecast model agreement. "
            "Conditions are compared to what's typical at a given location for the time of year.",
            html,
        )
        self.assertIn("(max-width: 800px)", html)
        self.assertIn('href="/climate/headlines" aria-current="page"', html)
        self.assertIn('<summary>Climate</summary>', html)
        self.assertIn('<summary>Moisture</summary>', html)
        self.assertIn('href="/climate/moisture-trends">Trends</a>', html)
        self.assertIn('<summary>Weather</summary>', html)
        self.assertIn('href="/climate/headlines" aria-current="page">Headlines</a>', html)
        self.assertIn('<summary>Snow</summary>', html)
        self.assertIn('href="/weather/snow-anomaly">Anomaly</a>', html)
        self.assertIn('href="/weather/snow-forecast">Forecast</a>', html)
        self.assertLess(
            html.index("<summary>Moisture</summary>"),
            html.index('href="/climate/oceans">Oceans</a>'),
        )
        self.assertIn('href="/graphics/copernicus">Copernicus</a>', html)
        self.assertIn("Climate headlines", html)
        self.assertNotIn('href="/globes"', html)
        self.assertEqual(OCEAN_STRENGTH, 0.42)
        self.assertIn("payload.oceanStrength", html)
        self.assertIn('field.id === "sst" || land ? 1 : OCEAN_STRENGTH', html)
        self.assertIn('id="words"', html)
        self.assertIn('id="title"', html)
        self.assertIn("<h1>BenNollWeather</h1>", html)
        self.assertIn("Bringing weather and climate data to life", html)
        self.assertNotIn("-webkit-text-stroke", html)
        self.assertIn("0 3px 0 rgba(23, 23, 23, 0.42)", html)
        self.assertIn("0 0 30px color-mix(in srgb, currentColor 74%, transparent)", html)
        self.assertIn("lum < 0.08 && spread < 24", html)
        self.assertIn("Save card", html)
        self.assertIn("climate-headlines-", html)
        self.assertIn("const scale = 3", html)
        self.assertIn('canvas.height = size * scale', html)
        self.assertIn('"Climate headlines for "', html)
        self.assertNotIn('fillText("benweather.com"', html)
        self.assertIn("ctx.drawImage(image, size - pad - logoW, size - pad - logoH, logoW, logoH);", html)
        self.assertNotIn("ctx.drawImage(image, size - pad - logoW, pad, logoW, logoH);", html)
        self.assertIn("function drawPopped(", html)
        self.assertIn("countW: countW, x: 0", html)
        self.assertNotIn("itemGap", html)
        self.assertIn("function refreshSuggest()", html)
        self.assertIn("function searchIsHigh()", html)
        self.assertNotIn("<datalist", html)
        self.assertNotIn("fillCities", html)
        self.assertIn("#111317", html)
        self.assertIn("70 percent", html)
        self.assertIn("agree * 10 < roster * 7", html)
        self.assertNotIn("agree * 4 < roster * 3", html)
        self.assertNotIn("75 percent", html)
        self.assertIn("word-count", html)
        self.assertIn('index === 0 ? " models agree"', html)
        self.assertIn("Snow is not expected.", html)
        self.assertIn('"models predict"} near average snowfall.', html)
        self.assertIn('field.id === "snow" ? field.models.length : vote.n', html)
        self.assertIn('field.id === "snow" ? "near average" : "no value"', html)
        self.assertIn("This location is far from the ocean, so no outlook is provided.", html)
        self.assertIn("farFromOcean(place)", html)
        self.assertIn("function sstCell(", html)
        self.assertIn("const SST_REACH_KM = 220;", html)
        self.assertIn("pointIndex(field, place.lat, place.lon)", html)
        self.assertIn("pointIndex(field, state.place.lat, state.place.lon)", html)
        self.assertIn('if (field.id === "sst") coverLand(ctx, layout.width, layout.mapHeight);', html)
        draw = html.split("function drawMap(", 1)[1].split("function drawCaption(", 1)[0]
        self.assertLess(draw.index("traceCoast("), draw.index('if (field.id !== "sst" && BORDERS)'))
        self.assertIn("strokeBorderLayer", draw[draw.index('if (field.id !== "sst" && BORDERS)'):])
        self.assertIn("function mapFields()", html)
        self.assertIn("return rest.concat(seas);", html)
        self.assertIn("mapFields().forEach", html)
        self.assertNotIn("GeoNames", html)
        self.assertNotIn("Place names beyond the curated list", html)
        self.assertIn("Anomalies use each model's hindcast for 1993-2016. Data is sourced from the Copernicus Climate Change Service.", html)
        self.assertNotIn("one download of every centre's ensemble mean", html)
        with open("lib/c3s_cities.json", encoding="utf-8") as cities_file:
            cities = cities_file.read()
        self.assertIn("Poughkeepsie", cities)
        self.assertIn('["Kingston","N.Y."', cities)
        self.assertIn('["Beacon","N.Y."', cities)
        self.assertNotIn("#3f007d", html)
        self.assertNotIn("#d94801", html)
        self.assertNotIn("No outcome has every model in agreement.", html)
        self.assertNotIn("drawGlobe", html)
        self.assertNotIn("The planet", html)
        self.assertNotIn("Calmer", html)
        self.assertNotIn("Where you are", html)
        self.assertNotIn("scrollIntoView", html)
        self.assertIn("const MAP_SCALE = 8;", html)
        self.assertIn("fillText(field.name", html)
        self.assertIn('const meta = (payload.period || "") + " · " + field.models.length + " models"', html)
        self.assertIn("paintGroup(colors.above, field.above, aboveW)", html)
        self.assertIn("paintGroup(colors.below, field.below, belowW)", html)
        self.assertIn("BORDERS.countries", html)
        self.assertIn("BORDERS.states", html)
        self.assertIn("((lon + 180) % 360 + 360) % 360", html)
        self.assertLess(html.index("traceCoast(ctx, layout.width, layout.mapHeight)"), html.index("BORDERS.countries"))
        self.assertIn('class="map-bitmap"', html)
        self.assertIn('new File([blob], filename, { type: "image/png" })', html)
        self.assertIn('return "climate-headlines-" + name + (period ? "-" + period : "") + ".png"', html)
        self.assertIn('link.download = field ? mapFilename(field) : "climate-headlines.png"', html)
        borders = (Path(__file__).resolve().parents[1] / "lib" / "c3s_borders.json").read_text(encoding="utf-8")
        self.assertIn('"countries":', borders)
        self.assertIn('"states":', borders)
        self.assertIn("[284.62,38.02]", borders)
        self.assertGreater(borders.count("["), 1000)
        self.assertNotIn('width="1440"', html)
        self.assertNotIn("#d5e2ee", html)
        self.assertNotIn("[12, 20, 28]", html)
        self.assertNotIn("invented", html.lower())

    def test_outcome_phrases_name_the_quantity(self) -> None:
        phrases = {field.id: (field.phrase_above, field.phrase_below) for field in FIELDS}
        self.assertEqual(phrases["temp"], ("higher temperatures than average", "lower temperatures than average"))
        self.assertEqual(phrases["rain"], ("higher rainfall than average", "lower rainfall than average"))
        self.assertEqual(phrases["dew"], ("higher humidity than average", "lower humidity than average"))
        self.assertEqual(phrases["snow"], ("more snowfall than average", "less snowfall than average"))
        self.assertEqual(phrases["wind"], ("higher wind speeds than average", "lower wind speeds than average"))
        self.assertEqual(phrases["mslp"], ("higher air pressure than average", "lower air pressure than average"))
        self.assertEqual(phrases["cloud"], ("higher cloud cover than average", "lower cloud cover than average"))
        self.assertEqual(phrases["sst"], ("higher sea surface temperatures than average", "lower sea surface temperatures than average"))
        names = {field.id: (field.name, field.below, field.variable) for field in FIELDS}
        self.assertEqual(names["temp"][0], "Air temperatures")
        self.assertEqual(names["dew"][0], "Dew points")
        self.assertEqual(names["wind"][1], "Less windy")
        self.assertEqual(names["cloud"][2], "total_cloud_cover_anomaly")
        self.assertEqual(names["sst"][2], "sea_surface_temperature_anomaly")

    def test_snow_gate_ignores_a_trace(self) -> None:
        snow = next(field for field in FIELDS if field.id == "snow")
        mean = np.array([[0.0, 1.5 / SNOW_INCHES, -0.4 / SNOW_INCHES, -2.0 / SNOW_INCHES]])
        above, voted = model_votes(snow, mean)
        self.assertEqual(voted.tolist(), [[False, True, False, True]])
        self.assertEqual(above.tolist(), [[False, True, False, False]])

    def test_area_shares_stay_between_zero_and_one(self) -> None:
        sign = np.ones((181, 360), dtype=np.int8)
        land = np.ones((181, 360), dtype=np.uint8)
        result = field_shares(sign, land)
        for key in ("globe_above", "tropics_above", "north_above"):
            self.assertGreater(result[key], 0.9)
            self.assertLessEqual(result[key], 1.0)
        self.assertEqual(result["tropics_below"], 0.0)

    def test_prime_meridian_copies_the_neighboring_column(self) -> None:
        above = np.zeros((1, 4, 3), dtype=bool)
        voted = np.zeros((1, 4, 3), dtype=bool)
        above[0, :, 1] = True
        voted[0, :, 1] = True
        packed_above, packed_voted = close_empty_meridian(pack_bits(above), pack_bits(voted), 1)
        self.assertTrue(np.array_equal(packed_voted[:, 0], packed_voted[:, 1]))
        self.assertTrue(np.array_equal(packed_above[:, 0], packed_above[:, 1]))

    def test_longitude_wrap_fills_the_prime_meridian(self) -> None:
        import xarray as xr

        lons = np.arange(0.5, 360.0, 1.0)
        lats = np.linspace(90, -90, 181)
        data = np.ones((lats.size, lons.size))
        data[:, 0] = 5
        data[:, -1] = 5
        values = xr.DataArray(
            data,
            coords={"latitude": lats, "longitude": lons},
            dims=("latitude", "longitude"),
        )
        grid = _to_grid(values)
        self.assertTrue(np.isfinite(grid[:, 0]).all())
        self.assertTrue(np.allclose(grid[:, 0], 5))
        self.assertTrue(np.allclose(grid[:, 10], 1))


class _Message:
    def __init__(self, institution: str) -> None:
        self.attrs = {"institution": institution}


class GlobeRequestTests(unittest.TestCase):
    def test_one_request_per_variable_includes_every_centre(self) -> None:
        init = date(2026, 10, 1)
        requests = [field_request(field, CENTRES, init) for field in FIELDS]
        self.assertEqual(len(requests), 8)
        variables = {item["variable"] for item in requests}
        self.assertEqual(len(variables), 8)
        self.assertIn("total_cloud_cover_anomaly", variables)
        self.assertIn("sea_surface_temperature_anomaly", variables)
        request = requests[0]
        self.assertEqual(request["product_type"], "ensemble_mean")
        self.assertEqual(request["leadtime_month"], ["2", "3", "4"])
        self.assertEqual(request["originating_centre"], [centre.id for centre in CENTRES])
        self.assertEqual(request["variable"], "2m_temperature_anomaly")
        self.assertIn("51", request["system"])
        self.assertIn("610", request["system"])
        self.assertIn("604", request["system"])
        self.assertIn("5", request["system"])
        self.assertIn("4", request["system"])
        self.assertNotIn("611", request["system"])

    def test_institution_names_stay_one_centre_each(self) -> None:
        names = {
            "ecmwf": "European Centre for Medium-Range Weather Forecasts",
            "ukmo": "U.K. Met Office - Exeter",
            "meteo_france": "French Weather Service - Toulouse",
            "dwd": "Deutscher Wetterdienst",
            "cmcc": "Centro Euro-Mediterraneo sui Cambiamenti Climatici",
            "jma": "Japanese Meteorological Agency - Tokyo",
            "ncep": "US National Weather Service - NCEP",
            "eccc": "Canadian Meteorological Service - Montreal",
            "bom": "Australian Bureau of Meteorology",
        }
        for centre_id, institution in names.items():
            matched = match_centre(_Message(institution), CENTRES)
            self.assertIsNotNone(matched)
            self.assertEqual(matched.id, centre_id)

    def test_two_systems_in_one_file_count_as_one_model(self) -> None:
        centre = next(item for item in CENTRES if item.id == "ukmo")
        months = season_months(date(2026, 10, 1))
        grid = np.zeros((181, 360))
        samples = []
        for system in ("605", "610"):
            for month in months:
                samples.append({"system": system, "month": month, "grid": grid})
        picked = _choose(centre, samples, months)
        self.assertEqual(picked["system"], "610")
        self.assertEqual(len(picked["grids"]), 3)

    def _samples(self, systems: dict[str, float], months, missing=()) -> list[dict]:
        samples = []
        for system, value in systems.items():
            grid = np.full((181, 360), value)
            for month in months:
                if (system, month) in missing:
                    continue
                samples.append({"system": system, "month": month, "grid": grid})
        return samples

    def test_eccc_keeps_both_current_systems(self) -> None:
        centre = next(item for item in CENTRES if item.id == "eccc")
        months = season_months(date(2026, 10, 1))
        models = select_models(centre, self._samples({"5": -2.0, "4": 1.0}, months), months)
        self.assertEqual([item["system"] for item in models], ["5", "4"])
        self.assertEqual([item["name"] for item in models], ["ECCC GEM5.2-NEMO", "ECCC CanESM5"])
        self.assertEqual(float(models[0]["grids"][0][0, 0]), -2.0)
        self.assertEqual(float(models[1]["grids"][0][0, 0]), 1.0)
        self.assertIsNone(_choose(centre, self._samples({"5": -2.0, "4": 1.0}, months), months))

    def test_an_older_system_drops_out_when_its_replacement_is_present(self) -> None:
        months = season_months(date(2026, 10, 1))
        cmcc = next(item for item in CENTRES if item.id == "cmcc")
        meteo = next(item for item in CENTRES if item.id == "meteo_france")
        self.assertEqual(select_models(cmcc, self._samples({"35": 1.0, "4": 3.0}, months), months)[0]["system"], "4")
        self.assertEqual(select_models(meteo, self._samples({"8": 1.0, "9": 3.0}, months), months)[0]["system"], "9")
        eccc = next(item for item in CENTRES if item.id == "eccc")
        only_old = select_models(eccc, self._samples({"3": 1.0, "2": 4.0}, months), months)
        self.assertEqual([item["system"] for item in only_old], ["3", "2"])

    def test_an_unknown_system_number_is_kept(self) -> None:
        months = season_months(date(2026, 10, 1))
        ecmwf = next(item for item in CENTRES if item.id == "ecmwf")
        models = select_models(ecmwf, self._samples({"51": 1.0, "52": -4.0}, months), months)
        self.assertEqual([item["system"] for item in models], ["52"])
        self.assertEqual(models[0]["name"], "ECMWF system 52")
        self.assertEqual(model_name(ecmwf, "51"), "ECMWF")
        eccc = next(item for item in CENTRES if item.id == "eccc")
        extra = select_models(eccc, self._samples({"5": 1.0, "4": 2.0, "6": 3.0}, months), months)
        self.assertEqual([item["system"] for item in extra], ["5", "4", "6"])
        self.assertEqual(extra[2]["name"], "ECCC system 6")

    def test_a_blank_system_id_is_not_renamed(self) -> None:
        months = season_months(date(2026, 10, 1))
        centre = next(item for item in CENTRES if item.id == "ecmwf")
        picked = _choose(centre, self._samples({"": 1.0}, months), months)
        self.assertEqual(picked["system"], "")
        self.assertEqual(picked["name"], "ECMWF")
        self.assertEqual(_normalize_system("undef"), "")
        self.assertEqual(_normalize_system(None), "")
        both = select_models(centre, self._samples({"": 1.0, "51": 2.0}, months), months)
        self.assertEqual([item["system"] for item in both], ["51"])

    def test_a_system_missing_a_lead_does_not_vote(self) -> None:
        centre = next(item for item in CENTRES if item.id == "eccc")
        months = season_months(date(2026, 10, 1))
        samples = self._samples({"5": 1.0, "4": 2.0}, months, missing={("4", months[2])})
        models = select_models(centre, samples, months)
        self.assertEqual([item["system"] for item in models], ["5"])

    def test_a_missing_lead_does_not_vote(self) -> None:
        centre = next(item for item in CENTRES if item.id == "ecmwf")
        months = season_months(date(2026, 10, 1))
        grid = np.zeros((181, 360))
        samples = [
            {"system": "51", "month": months[0], "grid": grid},
            {"system": "51", "month": months[1], "grid": grid},
        ]
        self.assertIsNone(_choose(centre, samples, months))

    def test_validity_time_uses_the_snow_month_shift(self) -> None:
        months = season_months(date(2026, 10, 1))
        self.assertEqual(_season_month(np.datetime64("2026-11-30"), months), date(2026, 11, 1))
        self.assertEqual(_season_month(np.datetime64("2026-12-01"), months), date(2026, 11, 1))
        self.assertEqual(_season_month(np.datetime64("2027-02-01"), months), date(2027, 1, 1))


class ScheduleTests(unittest.TestCase):
    def test_eventbridge_starts_the_headlines(self) -> None:
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/c3s-globes.yml").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("monthly-updates-c3s-globes", workflow)
        self.assertIn("lib/c3s_borders.json s3://bennollweather/climate/borders.json", workflow)
        self.assertNotIn("cron:", workflow)
        self.assertIn("| Climate headlines | 00:47 on the 11th |", readme)


if __name__ == "__main__":
    unittest.main()
