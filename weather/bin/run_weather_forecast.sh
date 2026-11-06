#!/usr/bin/env bash
# Build the weekly rainfall and temperature pages. Upload is the workflow's job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_DIR"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/weather-forecast}"
mkdir -p "$WORK_ROOT"
export WORK_ROOT
export PYTHONUNBUFFERED=1
export MPLBACKEND="${MPLBACKEND:-Agg}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"

python lib/weather_forecast.py --work "$WORK_ROOT"
