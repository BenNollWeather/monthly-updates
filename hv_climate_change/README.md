# Hudson Valley climate-change charts

Refactored from `climate_change-hv.ipynb`.

## Run

From the bundle root:

```bash
bash bin/run_hv_climate_change.sh
```

This will:

1. create/activate a conda environment if needed,
2. download ERA5 monthly means into `$WORK_ROOT` (default `${TMPDIR:-/tmp}/monthly-updates/hv-climate`),
3. generate PNG charts in `$WORK_ROOT/imagery`,
4. upload images to S3 under `s3://bennollweather/hv_climate_change/`,
5. delete the work directory after a successful upload, then print the resulting URLs.

## Useful options

Reuse an existing NetCDF or folder of NetCDFs:

```bash
bash bin/run_hv_climate_change.sh --input-file /path/to/hv_cc.nc --skip-download
```

Reuse the existing downloaded file in the work folder:

```bash
bash bin/run_hv_climate_change.sh --skip-download
```

Override AWS prefix:

```bash
AWS_PREFIX=hv_climate_change bash bin/run_hv_climate_change.sh
```


The runner now prints AWS image URLs after upload.


Data caching update: the runner now automatically reuses a valid merged ERA5 file or existing valid per-variable NetCDF files before downloading anything new.


Plot update: percentile dashed lines were removed, trendlines were added, titles were simplified, y-axis units were added, and chart info boxes now sit outside the plotting area.


Plot update: y-axis tick labels now include units, ticks are whole numbers, info boxes and attribution stay inside the axes, titles use sentence case, and CAPE wording is now thunderstorm fuel level.


Plot update: y-axis units now appear only on the top-most tick, moisture ticks can use decimals, CAPE uses J/kg, and low-year wording is variable-specific.


Plot update: y-axis labels are forced visible, units only appear on the top tick, and info-box labels no longer include the word 'years'.


Plot update: y-axis labels are now drawn manually inside the axes so they render reliably, with units only on the top label.


Plot update: compact units (`°F`, `%`) now attach directly to y-axis numbers and info-box values.
