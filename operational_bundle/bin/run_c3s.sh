#!/usr/bin/env bash
set -euo pipefail

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=operational_lib.sh
source "$SCRIPT_DIR/operational_lib.sh"
# shellcheck source=../../lib/forecast_month.sh
source "$REPO_ROOT/lib/forecast_month.sh"
require_forecast_month

ensure_env
ensure_regions
mkdir -p "$WORK_DIR" "$IMAGERY_DIR"
cd "$WORK_DIR"

# Preserve original behavior: C3S clears imagery and may overwrite ECMWF-named products like rain.
clean_c3s_imagery
clean_grib_idx

run_py sst
run_py roni
run_py zonal
run_py jet
run_py height
run_py strat
run_py temp
run_py dew
run_py wind
run_py cloud
run_py olr
run_py rain
run_py snow
run_py tables

# Publish every archived monthly snowfall heatmap under /snow/YYYY-MM/.
stage_snowfall_heatmaps

clean_grib_idx
publish_monitor c3s
upload_imagery "$IMAGERY_DIR" "$AWS_PREFIX"
cleanup_work
