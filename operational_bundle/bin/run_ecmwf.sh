#!/usr/bin/env bash
set -euo pipefail

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=operational_lib.sh
source "$SCRIPT_DIR/operational_lib.sh"

ensure_env
ensure_regions
mkdir -p "$WORK_DIR" "$IMAGERY_DIR"
cd "$WORK_DIR"
clean_grib_idx
if "$PYTHON_BIN" "$REPO_ROOT/lib/vp_climatology.py" --out "$VP_CLIMO_DIR"; then
  run_py vp
else
  echo "Velocity-potential climatology was not built; skipping those maps." >&2
fi

run_py ecmwf_sst
run_py ecmwf_sst_relative
run_py ecmwf_height
run_py ecmwf_jet
run_py ecmwf_rain
run_py ecmwf_snow
run_py sst_heatmap
run_py atmo_heatmap

# Stage generated city snowfall heatmaps into the S3 upload tree.
stage_snowfall_heatmaps

clean_grib_idx
publish_monitor ecmwf
upload_imagery "$IMAGERY_DIR" "$AWS_PREFIX"
cleanup_work
