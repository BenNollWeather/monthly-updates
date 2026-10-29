# Operational monthly runners

This bundle contains the two operational runners you need each month:

```bash
bash bin/run_ecmwf.sh
bash bin/run_c3s.sh
```

## What changed

- Only two monthly runners are included: `run_ecmwf.sh` and `run_c3s.sh`.
- No day-of-month warnings are emitted.
- The runners check for the `operational-monthly` conda environment and create it from `config/environment.yml` if needed.
- Working data, downloads, logs, and publish-ready imagery use a temporary directory, `${TMPDIR:-/tmp}/monthly-updates/operational`, unless `WORK_ROOT` is set. The runner deletes that directory after a successful upload. `KEEP_WORK=1` or `SKIP_UPLOAD=1` leaves it in place.

- Publish-ready imagery is written to `$WORK_ROOT/copernicus_imagery`.

- The final step syncs that imagery folder to S3, refreshes the Copernicus index, rebuilds the root graphics portal and the NMME/ERA5/climate galleries, then restores cross-links at the top of the Copernicus page.
- C3S still clears/overwrites publish-ready imagery where the existing workflow did, including normal filename collisions such as `rain`.
- The previous velocity-potential chain has been consolidated into a single script: `scripts/vp.py`. The separate `vp2.py` and `vp3.py` files are removed.

## Environment overrides

You can override defaults when running:

```bash
CONDA_ENV=operational-monthly \
AWS_PROFILE=bennollweather \
AWS_BUCKET=bennollweather \
AWS_PREFIX=copernicus_imagery \
bash bin/run_ecmwf.sh
```

Niño and Indian Ocean region outlines are generated into `$WORK_ROOT/shapefiles` at runtime. The 200 hPa velocity-potential climatology is the published `vp_clim_Mon.nc` set. Each ECMWF run downloads the current month and the next five from `https://bennollweather.s3.amazonaws.com/climate_imagery/climo/vp/`, then deletes them with the work directory. Set `VP_CLIMO_DIR` to reuse files already on disk, or `VP_CLIMO_URL` to change where they are downloaded from.

The generated file index and graphics portal are uploaded after every successful imagery sync:

```text
https://bennollweather.s3.amazonaws.com/index.html
https://bennollweather.s3.amazonaws.com/copernicus_imagery/index.html
https://bennollweather.s3.amazonaws.com/nmme/imagery/index.html
https://bennollweather.s3.amazonaws.com/atmospheric_moisture/index.html
https://bennollweather.s3.amazonaws.com/climate_imagery/index.html
```

Note: the standard S3 REST URL usually will not automatically serve `index.html` at `.../copernicus_imagery/`. Use the explicit `/index.html` URL, or put the bucket behind S3 static website hosting or CloudFront if you want the folder URL to resolve automatically.


## Dependency cleanup

Legacy `import wget` statements were removed from the generated scripts. The bundled environment also now includes a dependency sanity check: if an existing `operational-monthly` environment is missing required packages, the runner updates it from `config/environment.yml` before executing scripts.

## Refreshing the S3 index only

If you have already run the monthly ECMWF/C3S updates and only want to rebuild the browsable S3 file index, run:

```bash
bash bin/update_s3_index.sh
```

This does not rerun any imagery generation. It rebuilds the Copernicus index, root portal, NMME/ERA5/climate galleries, and the navigation links connecting them. It lists existing S3 objects using the configured AWS profile and uploads a fresh:

```text
s3://bennollweather/copernicus_imagery/index.html
```

The generated page includes top-level imagery plus first-level subfolders such as `heatmaps/` and `snow/`.


## Optional portal switch

The portal refresh runs automatically after successful uploads and manual index updates. To skip it for a particular run:

```bash
UPDATE_S3_PORTAL=0 bash bin/run_c3s.sh
```

Portal navigation uses explicit `index.html` links because the S3 REST endpoint does not perform directory-index redirects. For example, use `/nmme/imagery/index.html`, not `/nmme/`.

## Weather window shopping portal

`bin/update_s3_index.sh` now publishes a richer static S3 gallery with a rotating latest-graphic hero, collection filters, search, sorting, masonry and list views, a keyboard-enabled lightbox, zoom, original/download links, and a random-graphic control. The former `Featured` label has been removed; top-level Copernicus graphics are identified as `C3S`.
