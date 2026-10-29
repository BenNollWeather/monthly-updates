#!/usr/bin/env bash
set -euo pipefail

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$RUNNER_DIR/.." && pwd)"
SCRIPT_PATH="$PROJECT_ROOT/scripts/era5_pwat_anomaly.py"
PYTHON_BIN="${PYTHON_BIN:-python}"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/pwat}"
DOWNLOAD_RETRIES="${DOWNLOAD_RETRIES:-3}"
RETRY_SLEEP="${RETRY_SLEEP:-30}"

EXTRA_ARGS=()
if [[ -n "${DATAWRAPPER_DIR:-}" ]]; then
  EXTRA_ARGS+=(--datawrapper-dir "$DATAWRAPPER_DIR")
fi
if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  EXTRA_ARGS+=(--skip-upload)
fi
if [[ -n "${TARGET_MONTH:-}" ]]; then
  EXTRA_ARGS+=(--target-month "$TARGET_MONTH")
fi

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "ERROR: Python script not found: $SCRIPT_PATH" >&2
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_PATH" \
  --image-dir "$WORK_ROOT/imagery" \
  --download-dir "$WORK_ROOT/downloads" \
  --download-retries "$DOWNLOAD_RETRIES" \
  --retry-sleep "$RETRY_SLEEP" \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
  "$@"
status=$?

if [[ "$status" -eq 0 && "${KEEP_WORK:-0}" != "1" && "${SKIP_UPLOAD:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
fi
exit "$status"
