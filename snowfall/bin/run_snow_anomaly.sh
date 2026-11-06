#!/usr/bin/env bash
# Build the /snow page: the NOAA anomaly plus the latest ECMWF and AIFS 7-day snowfall. Upload is the workflow's job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_DIR"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/snow-anomaly}"
mkdir -p "$WORK_ROOT"
export WORK_ROOT
export PYTHONUNBUFFERED=1
export MPLBACKEND="${MPLBACKEND:-Agg}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"

python lib/snow_anomaly.py --work "$WORK_ROOT"
