#!/usr/bin/env bash
# Check the month this product is supposed to publish. The Python waiter
# repeats the check for a few hours, then tells the workflow to process,
# dispatch another run, or stop.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
python "$root/lib/release_wait.py" \
  --product "${PRODUCT_ID:?}" \
  --target-month "${TARGET_MONTH:-}" \
  --wait "${WAIT_FOR_DATA:-true}" \
  --github-output "${GITHUB_OUTPUT:-}"
