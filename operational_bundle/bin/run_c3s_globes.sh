#!/usr/bin/env bash
# Download each centre, variable, and lead month separately, then publish the globes.
set -euo pipefail

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# A named bennollweather profile is not a working local credential.
# GitHub Actions sets AWS_PROFILE empty and assumes the OIDC role.
if [[ -z "${GITHUB_ACTIONS:-}" && -z "${AWS_PROFILE+x}" ]]; then
  export AWS_PROFILE=""
fi
# shellcheck source=operational_lib.sh
source "$SCRIPT_DIR/operational_lib.sh"
if [[ -z "${WORK_ROOT:-}" || "$WORK_ROOT" == *"/monthly-updates/operational" ]]; then
  WORK_ROOT="${TMPDIR:-/tmp}/monthly-updates/c3s-globes"
fi
ensure_env
mkdir -p "$WORK_ROOT"
cd "$REPO_ROOT"

"$PYTHON_BIN" "$REPO_ROOT/lib/c3s_globes.py" \
  --init "${TARGET_MONTH:-}" \
  --work "$WORK_ROOT/downloads" \
  --html "$WORK_ROOT/index.html" \
  --json "$WORK_ROOT/data.json"

if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
  echo "Upload skipped."
  exit 0
fi

aws_cmd s3 cp "$WORK_ROOT/index.html" "s3://${AWS_BUCKET}/climate" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "no-cache, no-store, must-revalidate"
aws_cmd s3 cp "$WORK_ROOT/data.json" "s3://${AWS_BUCKET}/climate/data.json" \
  --content-type "application/json" \
  --cache-control "no-cache, no-store, must-revalidate"

if [[ "${KEEP_WORK:-0}" != "1" ]]; then
  rm -rf "$WORK_ROOT"
  echo "Deleted disposable work directory."
fi
