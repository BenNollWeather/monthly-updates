#!/usr/bin/env python3
"""Decision tests for monthly release retries. These do not call CDS or CPC."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta, timezone

from lib.release_wait import (
    FatalReleaseError,
    default_target,
    parse_month,
    retry_deadline,
    run_wait,
)


UTC = timezone.utc


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.sleeps: list[int] = []

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: int) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)


def run(probe, clock: Clock, **overrides):
    options = {
        "kind": "previous",
        "label": "ERA5 precipitable water",
        "target": date(2026, 9, 1),
        "clock": clock,
        "sleeper": clock.sleep,
        "interval": timedelta(minutes=30),
        "max_wait": timedelta(hours=1),
        "job_timeout": timedelta(hours=6),
        "process_budget": timedelta(minutes=45),
        "wait_enabled": True,
        "startup_delay": timedelta(0),
    }
    options.update(overrides)
    return run_wait(probe, **options)


class ReleaseWaitTests(unittest.TestCase):
    def test_targets_and_deadlines(self) -> None:
        self.assertEqual(default_target("previous", date(2026, 10, 6)), date(2026, 9, 1))
        self.assertEqual(retry_deadline("previous", date(2026, 9, 1)), datetime(2026, 11, 1, tzinfo=UTC))
        self.assertEqual(default_target("current", date(2026, 10, 8)), date(2026, 10, 1))
        self.assertEqual(retry_deadline("current", date(2026, 10, 1)), datetime(2026, 11, 1, tzinfo=UTC))
        self.assertEqual(default_target("previous", date(2026, 1, 6)), date(2025, 12, 1))
        self.assertEqual(retry_deadline("previous", date(2025, 12, 1)), datetime(2026, 2, 1, tzinfo=UTC))
        self.assertEqual(parse_month("2026-09"), date(2026, 9, 1))

    def test_ready_on_the_first_check_processes(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))
        result = run(lambda: True, clock)
        self.assertEqual(result.action, "process")
        self.assertEqual(clock.sleeps, [])

    def test_missing_month_waits_then_hands_off(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))
        result = run(lambda: False, clock)
        self.assertEqual(result.action, "requeue")
        self.assertGreaterEqual(sum(clock.sleeps), 60 * 60)

    def test_ready_after_a_short_wait_still_processes(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2

        result = run(probe, clock)
        self.assertEqual(result.action, "process")
        self.assertEqual(clock.sleeps, [1800])

    def test_long_job_requeues_after_waiting_so_processing_gets_a_full_window(self) -> None:
        clock = Clock(datetime(2026, 10, 10, 12, 47, tzinfo=UTC))
        calls = {"n": 0}

        def probe() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2

        result = run(
            probe,
            clock,
            kind="current",
            label="C3S",
            target=date(2026, 10, 1),
            process_budget=timedelta(hours=5, minutes=50),
        )
        self.assertEqual(result.action, "requeue")

    def test_startup_delay_does_not_consume_the_processing_window(self) -> None:
        clock = Clock(datetime(2026, 10, 10, 12, 47, tzinfo=UTC))
        result = run(
            lambda: True,
            clock,
            kind="current",
            label="C3S",
            target=date(2026, 10, 1),
            process_budget=timedelta(hours=5, minutes=50),
            startup_delay=timedelta(minutes=30),
        )
        self.assertEqual(result.action, "process")
        self.assertEqual(clock.sleeps, [1800])

    def test_disabled_wait_stops_immediately(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))
        result = run(lambda: False, clock, wait_enabled=False)
        self.assertEqual(result.action, "give_up")
        self.assertEqual(clock.sleeps, [])

    def test_window_ends_at_the_next_cycle(self) -> None:
        clock = Clock(datetime(2026, 10, 31, 23, 50, tzinfo=UTC))
        result = run(lambda: False, clock, interval=timedelta(minutes=30), max_wait=timedelta(hours=4))
        self.assertEqual(result.action, "give_up")
        self.assertLess(sum(clock.sleeps), 30 * 60)

    def test_repeated_check_bugs_stop(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))

        def probe() -> bool:
            raise RuntimeError("probe bug")

        result = run(probe, clock)
        self.assertEqual(result.action, "error")

    def test_fatal_check_stops(self) -> None:
        clock = Clock(datetime(2026, 10, 6, 5, 11, tzinfo=UTC))

        def probe() -> bool:
            raise FatalReleaseError("invalid api key")

        result = run(probe, clock)
        self.assertEqual(result.action, "error")
        self.assertEqual(clock.sleeps, [])


if __name__ == "__main__":
    unittest.main()
