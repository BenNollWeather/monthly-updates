#!/usr/bin/env bash
set -euo pipefail

RUNNER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$RUNNER_DIR/.." && pwd)"
SCRIPT_PATH="$PROJECT_ROOT/scripts/moisture_monitor.py"
PYTHON_BIN="${PYTHON_BIN:-python}"

WORK_ROOT="${WORK_ROOT:-${TMPDIR:-/tmp}/monthly-updates/era5-moisture-monitor}"
START_YEAR="${START_YEAR:-1940}"
GRID="${GRID:-1.0}"
MODE="${MODE:-dark}"
DPI="${DPI:-300}"
RAW_DIR="$WORK_ROOT/downloads"
OUTPUT="${OUTPUT:-$WORK_ROOT/imagery/era5_moisture_monitor.png}"
AWS_BIN="${AWS_BIN:-aws}"
AWS_BUCKET="${AWS_BUCKET:-bennollweather}"
AWS_PREFIX="${AWS_PREFIX:-atmospheric_moisture}"

if [[ -z "${TARGET_MONTH:-}" ]]; then
  TARGET_MONTH="$("$PYTHON_BIN" -c 'from datetime import date; today=date.today(); year, month=today.year, today.month-1
if month < 1:
    year, month = year-1, 12
print(f"{year:04d}-{month:02d}")')"
fi

if [[ -z "${AWS_PROFILE:-}" ]]; then
  unset AWS_PROFILE
fi
for _ca in REQUESTS_CA_BUNDLE CURL_CA_BUNDLE AWS_CA_BUNDLE; do
  if [[ -z "${!_ca:-}" ]]; then
    unset "$_ca"
  fi
done

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "ERROR: Python script not found: $SCRIPT_PATH" >&2
  exit 1
fi
if [[ ! "$TARGET_MONTH" =~ ^[0-9]{4}-(0[1-9]|1[0-2])$ ]]; then
  echo "TARGET_MONTH must be YYYY-MM; got: $TARGET_MONTH" >&2
  exit 2
fi

END_YEAR="${TARGET_MONTH:0:4}"
END_MONTH="${TARGET_MONTH:5:2}"
mkdir -p "$RAW_DIR" "$(dirname "$OUTPUT")"

if [[ "${SKIP_DOWNLOAD:-0}" != "1" ]]; then
  # Each run fetches the whole span, so do not reuse an older partial download.
  rm -f "$RAW_DIR"/era5_moisture_monthly_*.nc "$RAW_DIR"/era5_precip_monthly_*.nc
  "$PYTHON_BIN" "$SCRIPT_PATH" download \
    --out-dir "$RAW_DIR" \
    --start-year "$START_YEAR" \
    --end-year "$END_YEAR" \
    --end-month "$END_MONTH" \
    --grid "$GRID"
fi

"$PYTHON_BIN" "$SCRIPT_PATH" build \
  --input "$RAW_DIR/era5_moisture_monthly_*.nc" \
  --output "$OUTPUT" \
  --mode "$MODE" \
  --dpi "$DPI" \
  --expect-month "$TARGET_MONTH"

if [[ "${SKIP_UPLOAD:-0}" != "1" ]]; then
  upload_cmd=(
    "$PYTHON_BIN" "$SCRIPT_PATH" upload
    --output "$OUTPUT"
    --aws-bin "$AWS_BIN"
    --bucket "$AWS_BUCKET"
    --prefix "$AWS_PREFIX"
  )
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    upload_cmd+=(--aws-profile "$AWS_PROFILE")
  fi
  "${upload_cmd[@]}"
fi

if [[ "${KEEP_WORK:-0}" != "1" && "${SKIP_UPLOAD:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
fi
