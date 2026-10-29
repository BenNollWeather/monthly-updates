#!/usr/bin/env bash
# Publish one heartbeat JSON object. Does not upload imagery or downloads.
set -euo pipefail

status="${1:?status}"
message="${2:?message}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
runtime="$(( $(date +%s) - ${RUN_STARTED_EPOCH:-$(date +%s)} ))"

python "${root}/scripts/report_status.py" \
  --product "${PRODUCT_ID}" \
  --status "${status}" \
  --started-utc "${RUN_STARTED_UTC}" \
  --runtime-seconds "${runtime}" \
  --schedule "${PRODUCT_SCHEDULE}" \
  --outputs-json "${PRODUCT_OUTPUTS_JSON}" \
  --message "${message}" \
  --output /tmp/operational-status.json

aws s3 cp /tmp/operational-status.json \
  "${STATUS_S3_PREFIX%/}/${PRODUCT_ID}.json" \
  --only-show-errors
rm -f /tmp/operational-status.json
