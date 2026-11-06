# Moisture trends

Look up a place and see how precipitable water and vapor transport have changed there since 1940. Values are annual averages from ERA5, also shown as a percent of the 1991–2020 average at that location.

## Downloads

Two CDS requests, and no precipitation.

1. Every month of total column water, from 1940 through the last finished year, in one file.
2. Every month of the eastward and northward vapor-flux components, in a second file.

Vapor transport is the annual mean of the monthly magnitudes. If CDS rejects one file as too large, that year range is halved and the pieces are joined back into the same file. The NetCDF files are deleted after the page is written.

## Run

```bash
bash bin/run_moisture_trends.sh
```

The end year is the previous calendar year. Set `TARGET_YEAR` to choose a different finished year.

GitHub Actions workflow `moisture-trends.yml` is dispatch-only. It runs at 03:41 UTC on January 9 and publishes `moisture-trends` and `moisture-trends/data.bin`.

## Notes

- `SKIP_UPLOAD=1` keeps the working files and skips the upload.
- `WORK_ROOT` overrides the temporary directory.
