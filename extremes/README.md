# ERA5 extremes

## Layout

```text
bin/
  run_era5_extremes.sh
scripts/
  era5_extremes.py
```

## Run

From this project folder:

```bash
bash bin/run_era5_extremes.sh
```

## Notes

This tidy version keeps the existing script behavior and file names. The only intended change is directory organization.

## Target month

The script probes CDS for the most recent month with ERA5 monthly-mean data
(starting with last month and stepping back), then requests that same calendar
month for 1940 through that month's year. If the downloaded data does not end
at that month, the run stops instead of falling back to the previous year.

Options:

- `--target-month YYYY-MM` — force a specific month and skip the probe.
- `--max-lookback N` — how many months back to search (default 6).
- `--skip-download` — reuse the newest month already downloaded (downloads are
  now named by month, e.g. `_2026_08`, so stale files are never reused).

## Datawrapper exports

Written to `<work-dir>/upload_ready/datawrapper/` (so they sync to S3 with the
imagery; skip with `--skip-datawrapper`):

- `upper_decile_precip_coverage.csv` — `date,pct_of_planet`, one row per year
  for the target calendar month (1940–present). Percent of the planet's surface
  (cos-latitude area weighted) where precipitation exceeded that grid cell's
  90th percentile for the month, the same threshold the maps use.
- `upper_decile_precip_areas.geojson` — upper-decile areas for the target month
  as one MultiPolygon feature (RFC 7946, lon −180..180) with `pct_of_planet`
  and simplestyle fill properties. Tune with `--geojson-simplify` (degrees,
  default 0.1) and `--geojson-min-area` (square degrees, default 0).

## Area weighting

All "% of the planet" figures — the map titles, the upper-decile coverage chart
and the CSV — are weighted by cos(latitude), since 0.25° grid cells shrink
toward the poles. The chart and CSV come from the same computation, so they
match exactly. SST percentages are the share of ocean (area-weighted over cells
with valid SST), replacing the old `/0.71` approximation.
