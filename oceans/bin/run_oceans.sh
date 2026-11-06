#!/usr/bin/env bash
# Build the /climate/oceans page. Upload is the workflow's job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_DIR"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/oceans}"
mkdir -p "$WORK_ROOT"
export WORK_ROOT
export PYTHONUNBUFFERED=1
export MPLBACKEND="${MPLBACKEND:-Agg}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib}"
export CARTOPY_DATA_DIR="${CARTOPY_DATA_DIR:-/tmp/cartopy}"

python lib/oceans.py --work "$WORK_ROOT"
