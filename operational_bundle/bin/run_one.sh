#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash run_one.sh <script_name_without_py>" >&2
  echo "Example: bash run_one.sh height" >&2
  exit 1
fi

TARGET="$1"
shift || true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=operational_lib.sh
source "$SCRIPT_DIR/operational_lib.sh"

ensure_env
mkdir -p "$WORK_DIR" "$IMAGERY_DIR"
cd "$WORK_DIR"

clean_grib_idx
run_py "$TARGET"
clean_grib_idx

upload_imagery "$IMAGERY_DIR" "$AWS_PREFIX"
