#!/usr/bin/env bash
# Write CDS credentials for this job only. The workflow deletes the file afterwards.
set -euo pipefail

if [[ -z "${CDSAPI_KEY:-}" ]]; then
  echo "CDSAPI_KEY secret is not set." >&2
  exit 1
fi

umask 077
url="${CDSAPI_URL:-https://cds.climate.copernicus.eu/api}"
if [[ -z "$url" ]]; then
  url="https://cds.climate.copernicus.eu/api"
fi
printf 'url: %s\nkey: %s\n' "$url" "$CDSAPI_KEY" > "${HOME}/.cdsapirc"
