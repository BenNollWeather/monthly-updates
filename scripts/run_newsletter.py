#!/usr/bin/env python3
"""Run the private newsletter publisher against the current archive shape.

The page is still rendered and uploaded by the publishers repository. This
wrapper only accepts Substack's posts envelope before that publisher runs.
A body with no letters still fails, and the publisher leaves the live page
in place.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.newsletter_archive import load_publisher


def main(argv: list[str]) -> int:
    script = Path(argv[1] if len(argv) > 1 else "publishers/publish_newsletter.py")
    if not script.is_file():
        print(f"Newsletter publisher was not found at {script}. The current page was left in place.")
        return 1
    try:
        module = load_publisher(script)
    except (OSError, SyntaxError, RuntimeError) as error:
        print(f"Newsletter check failed ({error}). The current page was left in place.")
        return 1
    publish = getattr(module, "publish", None)
    if not callable(publish):
        print("Newsletter publisher has no publish(). The current page was left in place.")
        return 1
    os.chdir(script.resolve().parent)
    result = publish()
    if result is None:
        return 0
    return int(result)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
