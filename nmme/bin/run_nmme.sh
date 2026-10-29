#!/usr/bin/env bash
set -euo pipefail

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$RUNNER_DIR/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_ROOT/.." && pwd)"
SCRIPT_PATH="$PROJECT_ROOT/scripts/download_plot_nmme.py"
PYTHON_BIN="${PYTHON_BIN:-python}"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/nmme}"
SHAPEFILES_DIR="${SHAPEFILES_DIR:-$WORK_ROOT/shapefiles}"
export WORK_ROOT SHAPEFILES_DIR
# shellcheck source=../../lib/forecast_month.sh
source "$REPO_ROOT/lib/forecast_month.sh"
require_forecast_month

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "ERROR: Python script not found: $SCRIPT_PATH" >&2
  exit 1
fi

"$PYTHON_BIN" "$REPO_ROOT/lib/regions.py" --out "$SHAPEFILES_DIR"

args=(
  --base-download "$WORK_ROOT"
  --shapefiles "$SHAPEFILES_DIR"
)
if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  args+=(--skip-upload)
fi

"$PYTHON_BIN" "$SCRIPT_PATH" "${args[@]}" "$@"
status=$?

if [[ "$status" -eq 0 && "${KEEP_WORK:-0}" != "1" && "${SKIP_UPLOAD:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
fi
exit "$status"
