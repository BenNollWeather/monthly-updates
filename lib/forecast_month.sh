#!/usr/bin/env bash
# Forecast scripts read the UTC calendar month from the clock. A retry that
# crosses into the next month would request the wrong issuance.

require_forecast_month() {
  if [[ -z "${TARGET_MONTH:-}" ]]; then
    return 0
  fi
  local clock_month
  clock_month="$(date -u +%Y-%m)"
  if [[ "$clock_month" != "$TARGET_MONTH" ]]; then
    echo "This forecast run is locked to ${TARGET_MONTH}. The UTC month is now ${clock_month}, so the scripts would request the wrong issuance." >&2
    exit 75
  fi
}
