#!/usr/bin/env python3
"""Write the weather-operations heartbeat for one monthly product."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--product", required=True)
    parser.add_argument("--status", choices=["success", "failure"], required=True)
    parser.add_argument("--started-utc", required=True)
    parser.add_argument("--runtime-seconds", type=int, required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--outputs-json", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--message", default="")
    return parser.parse_args()


def _scheduled_event() -> bool:
    flag = os.getenv("SCHEDULED_EVENT", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    return os.getenv("GITHUB_EVENT_NAME") == "schedule"


def main() -> None:
    args = parse_args()
    payload = {
        "schema_version": 1,
        "product": args.product,
        "status": args.status,
        "scheduled_event": _scheduled_event(),
        "event_name": os.getenv("GITHUB_EVENT_NAME", ""),
        "schedule_utc": args.schedule,
        "started_utc": args.started_utc,
        "completed_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "runtime_seconds": args.runtime_seconds,
        "workflow_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "workflow_run_attempt": os.getenv("GITHUB_RUN_ATTEMPT", ""),
        "workflow_url": (
            f"{os.getenv('GITHUB_SERVER_URL', 'https://github.com')}/"
            f"{os.getenv('GITHUB_REPOSITORY', '')}/actions/runs/{os.getenv('GITHUB_RUN_ID', '')}"
        ),
        "repository": os.getenv("GITHUB_REPOSITORY", ""),
        "commit_sha": os.getenv("GITHUB_SHA", ""),
        "branch": os.getenv("GITHUB_REF_NAME", ""),
        "outputs": json.loads(args.outputs_json),
        "message": args.message,
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({key: payload[key] for key in ("product", "status", "completed_utc", "runtime_seconds")}))


if __name__ == "__main__":
    main()
