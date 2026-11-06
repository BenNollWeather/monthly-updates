# ERA5 planetary moisture monitor

One global dashboard from ERA5 monthly fields. It shows total column water and integrated vapor transport for the latest month, the trailing three months, and the rolling twelve months, plus historical stripes for those fields and for precipitation.

## Layout

```text
bin/
  run_era5_moisture_monitor.sh
scripts/
  moisture_monitor.py
```

## Run

From this project folder:

```bash
bash bin/run_era5_moisture_monitor.sh
```

The figure covers the month that just ended. Set `TARGET_MONTH=YYYY-MM` to choose a different month. The download writes three files for that span: precipitable water, the eastward and northward vapor-flux components, and precipitation. It draws the figure and removes those files after a successful upload. Nothing is written into git.

An unfinished final year is requested on its own and appended to those files, because CDS applies one month list to every year in a request.

GitHub Actions workflow `era5-moisture.yml` runs at 00:41 UTC on the 7th. It publishes `atmospheric_moisture/era5_moisture_monitor.png`.

## Notes

A month is compared only with the same month, a three-month window only with the same three months, and a twelve-month window only with windows that end in the same month. Percent anomalies use 1991–2020. Global ranks and stripes use a cosine-latitude weight.

Local deciles use the full history on a shared 1–10 scale. Deciles 4–6 stay neutral. Stipples mark a new local high or low against every earlier like-for-like year. The precipitation stripe multiplies each month by the number of days in that month before summing.

This runner follows the schedule in the repository README.

- `SKIP_UPLOAD=1` keeps the working files and skips the upload.
- `KEEP_WORK=1` keeps them after an upload.
- `SKIP_DOWNLOAD=1` draws from files already in the working directory.
- `WORK_ROOT` overrides the temporary directory.
