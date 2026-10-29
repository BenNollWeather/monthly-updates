# Modular runners

Run from the `bin/` directory.

## Run any one script

```bash
bash run_one.sh height
bash run_one.sh rain
bash run_one.sh sst
```

## Dedicated one-product runners

```bash
bash run_height.sh
bash run_rain.sh
bash run_sst.sh
bash run_temp.sh
bash run_snow.sh
```

Each runner:
1. activates/creates the operational conda environment,
2. runs only that script,
3. cleans GRIB index files,
4. uploads imagery to AWS,
5. refreshes the browsable S3 `index.html`,
6. prints uploaded URLs.

## Grouped runners

```bash
bash run_atmosphere_maps.sh
bash run_ocean_tables.sh
```

## Notes

These runners use `$WORK_ROOT` (default `${TMPDIR:-/tmp}/monthly-updates/operational`). `KEEP_WORK=1` leaves downloaded files there for a faster rerun. Otherwise the directory is deleted after a successful upload.
