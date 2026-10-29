# ERA5 PWAT anomaly

## Layout

```text
bin/
  run_era5_pwat_anomaly.sh
scripts/
  era5_pwat_anomaly.py
```

## Run

From this project folder:

```bash
bash bin/run_era5_pwat_anomaly.sh
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

Written to `<image-dir>/datawrapper/` (override with `--datawrapper-dir` or the
`DATAWRAPPER_DIR` env var; skip with `--skip-datawrapper`). Because they sit
inside the image directory they are also synced to S3.

- `pwat_monthly_inches_wide.csv` — global cos(lat)-weighted mean PWAT (inches)
  from `monthly_pwat_YYYY_MM.nc`. One row per month dated in the target year
  (`this_year_date`), one column per year 1940–present; future months blank.
- `pwat_monthly_anomaly_pct_wide.csv` — same layout, percent difference from
  the 1991–2020 mean for each calendar month (e.g. 2.15 = 2.15% above average).
- `pwat_record_high_coverage.csv` — `date,pct_of_planet_record_high`, one row
  per year (1940–present) for the target calendar month: percent of the planet
  (cos-latitude area weighted) where that year holds the all-time record high
  PWAT, comparing every year in the record. Shares sum to 100; the latest row
  matches the `record` area in the GeoJSON.
- `pwat_extremes.geojson` — target-month grid areas ranked against the same
  calendar month in every prior year (1940 onward), as three non-overlapping
  MultiPolygon features: `record` (higher than every prior year), `p95`
  (≥95% of prior years lower), `p90` (≥90%). Each carries `label`,
  `pct_of_globe`, and simplestyle `fill`/`stroke` properties. RFC 7946
  winding, lon −180..180. Tune size with `--geojson-simplify` (degrees,
  default 0.1) and `--geojson-min-area` (square degrees, default 0).
