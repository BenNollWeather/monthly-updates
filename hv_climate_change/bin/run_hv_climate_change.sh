#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/hv-climate}"
IMAGE_DIR="${IMAGE_DIR:-$WORK_ROOT/imagery}"

AWS_BIN="${AWS_BIN:-aws}"
AWS_BUCKET="${AWS_BUCKET:-bennollweather}"
AWS_PREFIX="${AWS_PREFIX:-hv_climate_change}"
if [[ -z "${AWS_PROFILE+x}" ]]; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    AWS_PROFILE=""
  else
    AWS_PROFILE="bennollweather"
  fi
fi

DOWNLOAD_RETRIES="${DOWNLOAD_RETRIES:-3}"
RETRY_SLEEP="${RETRY_SLEEP:-60}"

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""

if [[ "${USE_SYSTEM_PYTHON:-0}" != "1" ]]; then
  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base)"
    # shellcheck disable=SC1091
    source "${conda_base}/etc/profile.d/conda.sh"
    conda_env="${CONDA_ENV:-hv-climate-change}"
    if ! conda env list | awk '{print $1}' | grep -qx "$conda_env"; then
      conda create -n "$conda_env" python="${PYTHON_VERSION:-3.12}" -y
    fi
    conda activate "$conda_env"
    PYTHON_BIN="$(command -v python)"
  fi
fi

mkdir -p "$WORK_ROOT" "$IMAGE_DIR"

"$PYTHON_BIN" "$BUNDLE_DIR/scripts/hv_climate_change.py" \
  --work-root "$WORK_ROOT" \
  --image-dir "$IMAGE_DIR" \
  --download-retries "$DOWNLOAD_RETRIES" \
  --retry-sleep "$RETRY_SLEEP" \
  "$@"

if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  echo "Upload skipped because SKIP_UPLOAD=1."
  exit 0
fi

cmd=( "$AWS_BIN" s3 sync "$IMAGE_DIR" "s3://$AWS_BUCKET/$AWS_PREFIX/" --exclude ".DS_Store" )
if [[ -n "$AWS_PROFILE" ]]; then
  result="$(AWS_PROFILE="$AWS_PROFILE" "${cmd[@]}" 2>&1)" || { echo "$result"; exit 1; }
else
  result="$("${cmd[@]}" 2>&1)" || { echo "$result"; exit 1; }
fi
echo "$result"

if [[ "${KEEP_WORK:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
fi
