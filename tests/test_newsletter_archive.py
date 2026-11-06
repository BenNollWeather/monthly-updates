#!/usr/bin/env python3
"""Newsletter archive shape. These tests do not fetch Substack or upload a page."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_newsletter import main
from lib.newsletter_archive import (
    EMPTY_ARCHIVE,
    accepting_parser,
    load_publisher,
    patch_archive_source,
    posts_from_archive,
)


def historical_parse(payload):
    """The list-only check the publisher used when the archive was a bare array."""
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(EMPTY_ARCHIVE)
    letters = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("canonical_url") or "").strip()
        posted = item.get("post_date")
        if title and url and posted:
            letters.append({"title": title, "url": url, "post_date": str(posted)})
    if not letters:
        raise RuntimeError(EMPTY_ARCHIVE)
    return letters


class ArchiveShapeTests(unittest.TestCase):
    def test_bare_list_is_unchanged(self) -> None:
        letters = [{"title": "One"}]
        self.assertIs(posts_from_archive(letters), letters)

    def test_posts_envelope_returns_the_array(self) -> None:
        posts = [{"title": "One"}]
        self.assertIs(posts_from_archive({"posts": posts, "nextCursor": "abc"}), posts)

    def test_empty_and_unrelated_bodies_fail_closed(self) -> None:
        for body in ([], {"posts": []}, {"posts": None}, {"error": "challenge"}, "Just a moment", None, 5):
            with self.assertRaises(RuntimeError) as caught:
                posts_from_archive(body)
            self.assertEqual(str(caught.exception), EMPTY_ARCHIVE)

    def test_historical_parser_reads_the_envelope(self) -> None:
        payload = {
            "posts": [
                {
                    "title": "Rain is on the horizon for the Hudson Desert",
                    "canonical_url": "https://www.bennollsays.com/p/update-729",
                    "post_date": "2026-11-01T12:23:35.229Z",
                }
            ],
            "nextCursor": "cursor",
        }
        letters = accepting_parser(historical_parse)(payload)
        self.assertEqual(letters[0]["title"], "Rain is on the horizon for the Hudson Desert")

    def test_historical_parser_still_rejects_letters_without_required_fields(self) -> None:
        payload = {"posts": [{"title": "Untitled", "subtitle": "no url or date"}]}
        with self.assertRaises(RuntimeError) as caught:
            accepting_parser(historical_parse)(payload)
        self.assertEqual(str(caught.exception), EMPTY_ARCHIVE)

    def test_bare_list_of_real_letters_is_not_parsed_twice(self) -> None:
        calls = []

        def parse_archive(payload):
            calls.append(payload)
            return historical_parse(payload)

        payload = [
            {
                "title": "Another winning weather week",
                "canonical_url": "https://www.bennollsays.com/p/update-728",
                "post_date": "2026-10-25T12:53:25.966Z",
            }
        ]
        accepting_parser(parse_archive)(payload)
        self.assertEqual(len(calls), 1)

    def test_other_runtime_errors_are_not_retried(self) -> None:
        def parse_archive(payload):
            raise RuntimeError("HTTP Error 403: Forbidden")

        with self.assertRaises(RuntimeError) as caught:
            accepting_parser(parse_archive)({"posts": [{"title": "x"}]})
        self.assertEqual(str(caught.exception), "HTTP Error 403: Forbidden")

    def test_parser_that_already_accepts_the_envelope_is_left_alone(self) -> None:
        def parse_archive(payload):
            if isinstance(payload, dict):
                return ["from-envelope", len(payload["posts"])]
            return ["from-list", len(payload)]

        self.assertEqual(
            accepting_parser(parse_archive)({"posts": [{"title": "A"}], "nextCursor": "z"}),
            ["from-envelope", 1],
        )

    def test_source_patch_unwraps_only_the_list_guard(self) -> None:
        source = (
            "def parse_archive(payload):\n"
            "    if not isinstance(payload, list) or not payload:\n"
            '        raise RuntimeError("The newsletter archive did not include any letters.")\n'
            "    letters = payload\n"
            "    if not letters:\n"
            '        raise RuntimeError("The newsletter archive did not include any letters.")\n'
            "    return letters\n"
        )
        patched = patch_archive_source(source)
        self.assertIsNotNone(patched)
        self.assertEqual(patched.count('payload = payload["posts"]'), 1)
        self.assertIn("if not letters:", patched)
        namespace: dict = {}
        exec(patched, namespace)
        self.assertEqual(namespace["parse_archive"]({"posts": [{"id": 1}]})[0]["id"], 1)
        with self.assertRaises(RuntimeError):
            namespace["parse_archive"]({"posts": []})
        self.assertIsNone(patch_archive_source("def publish():\n    return 1\n"))

    def test_loaded_publisher_uses_the_adapted_parser(self) -> None:
        source = (
            "def parse_archive(payload):\n"
            "    if not isinstance(payload, list) or not payload:\n"
            '        raise RuntimeError("The newsletter archive did not include any letters.")\n'
            "    return payload\n"
            "\n"
            "def publish():\n"
            '    return parse_archive({"posts": [{"title": "Kept"}], "nextCursor": "n"})\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish_newsletter.py"
            path.write_text(source, encoding="utf-8")
            module = load_publisher(path)
            self.assertEqual(module.publish(), [{"title": "Kept"}])

    def test_inlined_guard_is_patched_and_still_rejects_an_empty_archive(self) -> None:
        source = (
            "def publish(payload):\n"
            "    if not isinstance(payload, list) or not payload:\n"
            '        raise RuntimeError("The newsletter archive did not include any letters.")\n'
            "    return [item['title'] for item in payload]\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish_newsletter.py"
            path.write_text(source, encoding="utf-8")
            module = load_publisher(path)
            self.assertEqual(module.publish({"posts": [{"title": "Kept"}]}), ["Kept"])
            with self.assertRaises(RuntimeError) as caught:
                module.publish({"posts": []})
            self.assertEqual(str(caught.exception), EMPTY_ARCHIVE)

    def test_runner_refuses_to_publish_without_a_publisher(self) -> None:
        self.assertEqual(main(["run_newsletter.py", "missing/publish_newsletter.py"]), 1)
        source = "def parse_archive(payload):\n    return payload\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish_newsletter.py"
            path.write_text(source, encoding="utf-8")
            self.assertEqual(main(["run_newsletter.py", str(path)]), 1)

    def test_workflow_still_runs_the_private_publisher(self) -> None:
        workflow = Path(".github/workflows/newsletter.yml").read_text(encoding="utf-8")
        self.assertIn("repository: BenNollWeather/benweather-publishers", workflow)
        self.assertIn("python3 scripts/run_newsletter.py publishers/publish_newsletter.py", workflow)
        self.assertNotIn("continue-on-error", workflow)


if __name__ == "__main__":
    unittest.main()
