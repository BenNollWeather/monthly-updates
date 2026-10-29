#!/usr/bin/env bash
# Remove credentials, downloads, and generated files from the runner.
set -u
rm -f "${HOME}/.cdsapirc" /tmp/operational-status.json
if [[ -n "${WORK_ROOT:-}" ]]; then
  rm -rf "${WORK_ROOT}"
fi
rm -rf /tmp/matplotlib /tmp/cartopy /tmp/monthly-updates
echo "Runner cleanup complete."
