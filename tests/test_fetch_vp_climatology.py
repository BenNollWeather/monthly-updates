#!/usr/bin/env python3
"""Tests for selecting and downloading the velocity-potential climatology."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from lib.fetch_vp_climatology import fetch, forecast_month_names


NETCDF = b"\x89HDF\r\n\x1a\n" + b"x" * 2048


class ForecastMonthsTest(unittest.TestCase):
    def test_october_wraps_into_the_next_year(self) -> None:
        self.assertEqual(
            forecast_month_names(date(2026, 10, 6)),
            ["Oct", "Nov", "Dec", "Jan", "Feb", "Mar"],
        )

    def test_january_stays_inside_the_year(self) -> None:
        self.assertEqual(
            forecast_month_names(date(2026, 1, 6)),
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
        )

    def test_august_uses_september_abbreviation(self) -> None:
        self.assertEqual(
            forecast_month_names(date(2026, 8, 6))[1],
            "Sep",
        )


class FetchTest(unittest.TestCase):
    def test_downloads_only_the_requested_months(self) -> None:
        calls: list[str] = []

        def read_url(url: str) -> bytes:
            calls.append(url)
            return NETCDF

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            written = fetch(out, ["Oct", "Nov"], "https://example.test/climo/vp", read_url)
            self.assertEqual(
                calls,
                [
                    "https://example.test/climo/vp/vp_clim_Oct.nc",
                    "https://example.test/climo/vp/vp_clim_Nov.nc",
                ],
            )
            self.assertEqual([path.name for path in written], ["vp_clim_Oct.nc", "vp_clim_Nov.nc"])
            fetch(out, ["Oct"], "https://example.test/climo/vp", read_url)
            self.assertEqual(len(calls), 2)

    def test_unknown_month_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                fetch(Path(directory), ["Sept"], "https://example.test/climo/vp", lambda url: NETCDF)

    def test_non_netcdf_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit):
                fetch(Path(directory), ["Oct"], "https://example.test/climo/vp", lambda url: b"nope")
