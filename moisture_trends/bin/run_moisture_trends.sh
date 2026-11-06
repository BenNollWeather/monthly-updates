#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$BUNDLE_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/moisture-trends}"

AWS_BIN="${AWS_BIN:-aws}"
AWS_BUCKET="${AWS_BUCKET:-bennollweather}"
if [[ -z "${AWS_PROFILE+x}" ]]; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    AWS_PROFILE=""
  else
    AWS_PROFILE="bennollweather"
  fi
fi

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""

if [[ "${USE_SYSTEM_PYTHON:-0}" != "1" ]]; then
  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base)"
    # shellcheck disable=SC1091
    source "${conda_base}/etc/profile.d/conda.sh"
    conda_env="${CONDA_ENV:-moisture-trends}"
    if ! conda env list | awk '{print $1}' | grep -qx "$conda_env"; then
      conda create -n "$conda_env" python="${PYTHON_VERSION:-3.12}" -y
    fi
    conda activate "$conda_env"
    PYTHON_BIN="$(command -v python)"
  fi
fi

mkdir -p "$WORK_ROOT"

"$PYTHON_BIN" "$REPO_DIR/lib/moisture_trends.py" --work "$WORK_ROOT" "$@"

if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  echo "Upload skipped because SKIP_UPLOAD=1."
  exit 0
fi

upload() {
  if [[ -n "$AWS_PROFILE" ]]; then
    AWS_PROFILE="$AWS_PROFILE" "$@"
  else
    "$@"
  fi
}

upload "$AWS_BIN" s3 cp "$WORK_ROOT/index.html" "s3://$AWS_BUCKET/moisture-trends" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "no-cache, no-store, must-revalidate" \
  --only-show-errors
gzip -c "$WORK_ROOT/data.bin" | upload "$AWS_BIN" s3 cp - "s3://$AWS_BUCKET/moisture-trends/data.bin" \
  --content-encoding gzip \
  --content-type "application/octet-stream" \
  --cache-control "public, max-age=86400" \
  --only-show-errors

if [[ "${KEEP_WORK:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
fi
