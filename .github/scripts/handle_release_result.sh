#!/usr/bin/env bash
# Publish the heartbeat and, when the month is not ready, dispatch the next check.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
action="${WAIT_ACTION:-}"
exit_code="${PROCESS_EXIT_CODE:-}"
process_outcome="${PROCESS_OUTCOME:-}"
upload_outcome="${UPLOAD_OUTCOME:-}"
upload="${UPLOAD_TO_S3:-false}"
scheduled="${SCHEDULED_INPUT:-false}"
target_month="${RESOLVED_TARGET_MONTH:-}"
message="${WAIT_MESSAGE:-}"
interval="${DATA_WAIT_INTERVAL_SECONDS:-1800}"

outcome="fail"
heartbeat=""
heartbeat_message=""
requeue="false"
delay="0"

if [[ "$exit_code" == "75" ]]; then
  requeue="true"
  delay="$interval"
  minutes=$((interval / 60))
  heartbeat="waiting"
  heartbeat_message="${target_month} was not available when the job ran. The next check is in ${minutes} minutes."
elif [[ "$action" == "requeue" ]]; then
  requeue="true"
  heartbeat="waiting"
  heartbeat_message="${message:-${target_month} is not available yet. The next run will check again.}"
elif [[ "$action" == "process" && "$process_outcome" == "success" ]]; then
  if [[ "$upload" == "true" && "$upload_outcome" != "success" ]]; then
    heartbeat="failure"
    heartbeat_message="Processing finished, but the production upload failed."
  else
    outcome="ok"
    heartbeat="success"
    heartbeat_message="Workflow completed and production uploads succeeded."
  fi
elif [[ "$action" == "give_up" || "$action" == "error" ]]; then
  heartbeat="failure"
  heartbeat_message="${message:-The monthly data was still unavailable when retries stopped.}"
elif [[ -z "$action" ]]; then
  heartbeat="failure"
  heartbeat_message="The availability check failed before it could retry."
else
  heartbeat="failure"
  heartbeat_message="${message:-Processing or production upload failed.}"
fi

if [[ "$requeue" == "true" ]]; then
  if [[ -z "$target_month" ]]; then
    echo "Cannot queue another check without a target month." >&2
    heartbeat="failure"
    heartbeat_message="The retry did not record which month it was waiting for."
    requeue="false"
    outcome="fail"
  else
    echo "Queueing the next check for ${target_month} (startup delay ${delay}s)."
    GH_TOKEN="${GH_TOKEN:-${GITHUB_TOKEN:-}}" gh workflow run "${WORKFLOW_FILE:?}" \
      --ref "${GITHUB_REF_NAME:?}" \
      -f "upload_to_s3=${upload}" \
      -f "scheduled=${scheduled}" \
      -f "wait_for_data=true" \
      -f "target_month=${target_month}" \
      -f "startup_delay_seconds=${delay}"
    outcome="ok"
  fi
fi

if [[ "$upload" == "true" && -n "$heartbeat" ]]; then
  RETRY_UNTIL="${RETRY_UNTIL:-}" bash "$root/.github/scripts/report_status.sh" "$heartbeat" "$heartbeat_message"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "outcome=${outcome}" >> "$GITHUB_OUTPUT"
fi
echo "Release result: ${outcome}"
