# Operational monthly bundle

## Updating model version numbers

Edit:

```text
config/model_versions.json
```

The Python scripts read this file at runtime through `scripts/model_versions.py`.

You can also override the file path without editing the bundle:

```bash
MODEL_VERSIONS_FILE=/path/to/model_versions.json bash bin/run_ecmwf.sh
MODEL_VERSIONS_FILE=/path/to/model_versions.json bash bin/run_c3s.sh
```

Main fields:

- `ecmwf.system`: ECMWF system used by the ECMWF-only scripts.
- `c3s.multi_model_systems`: multi-model C3S system list.
- `c3s.height_systems`: C3S height/geopotential system list.
- `c3s.stratosphere_systems`: C3S stratospheric temperature system list.
- `c3s.snow_systems`: C3S snow system list.
- `c3s.ukmo_system`: UKMO single-centre system used by several C3S anomaly scripts.
