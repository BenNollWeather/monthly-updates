#!/usr/bin/env bash
set -euo pipefail

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$RUNNER_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
SCRIPT_PATH="$PROJECT_ROOT/scripts/era5_extremes.py"

PYTHON_BIN="${PYTHON_BIN:-python}"
WORK_DIR="${ERA5_EXTREMES_WORK_DIR:-${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/era5-extremes}}"
DOWNLOAD_RETRIES="${DOWNLOAD_RETRIES:-3}"
RETRY_SLEEP="${RETRY_SLEEP:-30}"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "ERROR: Python script not found: $SCRIPT_PATH" >&2
  exit 1
fi

args=(
  --work-dir "$WORK_DIR"
  --download-retries "$DOWNLOAD_RETRIES"
  --retry-sleep "$RETRY_SLEEP"
)
if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  args+=(--skip-upload)
fi
if [[ -n "${TARGET_MONTH:-}" ]]; then
  args+=(--target-month "$TARGET_MONTH")
fi

"$PYTHON_BIN" "$SCRIPT_PATH" "${args[@]}" "$@"
status=$?

if [[ "$status" -eq 0 && "${KEEP_WORK:-0}" != "1" && "${SKIP_UPLOAD:-0}" != "1" ]]; then
  rm -rf "$WORK_DIR"
fi
exit "$status"
