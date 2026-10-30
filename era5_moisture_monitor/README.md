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

The figure covers the month that just ended. Set `TARGET_MONTH=YYYY-MM` to choose a different month. Working files stay in a temporary directory and are removed after a successful upload. Nothing is written into git.

GitHub Actions workflow `era5-moisture.yml` is started by hand. It is not on a schedule. It publishes `atmospheric_moisture/era5_moisture_monitor.png`.

## Notes

A month is compared only with the same month, a three-month window only with the same three months, and a twelve-month window only with windows that end in the same month. Percent anomalies use 1991–2020. Global ranks and stripes use a cosine-latitude weight.

Local deciles use the full history on a shared 1–10 scale. Deciles 4–6 stay neutral. Stipples mark a new local high or low against every earlier like-for-like year. The precipitation stripe multiplies each month by the number of days in that month before summing.

This runner is started by hand. It is not on the monthly schedule.

- `SKIP_UPLOAD=1` keeps the working files and skips the upload.
- `KEEP_WORK=1` keeps them after an upload.
- `SKIP_DOWNLOAD=1` draws from files already in the working directory.
- `WORK_ROOT` overrides the temporary directory.
