#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=operational_lib.sh
source "$SCRIPT_DIR/operational_lib.sh"

ensure_env
mkdir -p "$WORK_DIR" "$IMAGERY_DIR"
cd "$WORK_DIR"
clean_grib_idx

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

clean_grib_idx
upload_imagery "$IMAGERY_DIR" "$AWS_PREFIX"
