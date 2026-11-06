"""Shared model-version configuration for operational monthly scripts."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _config_path() -> Path:
    env_path = os.environ.get("MODEL_VERSIONS_FILE")
    if env_path:
        return Path(env_path).expanduser()
    return Path(__file__).resolve().parents[1] / "config" / "model_versions.json"


def load_model_versions() -> dict:
    path = _config_path()
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


MODEL_VERSIONS = load_model_versions()

ECMWF_SYSTEM = MODEL_VERSIONS["ecmwf"]["system"]
C3S_MULTI_MODEL_SYSTEMS = MODEL_VERSIONS["c3s"]["multi_model_systems"]
C3S_STRATOSPHERE_SYSTEMS = MODEL_VERSIONS["c3s"]["stratosphere_systems"]
C3S_SNOW_SYSTEMS = MODEL_VERSIONS["c3s"]["snow_systems"]
C3S_HEIGHT_SYSTEMS = MODEL_VERSIONS["c3s"]["height_systems"]
C3S_UKMO_SYSTEM = MODEL_VERSIONS["c3s"]["ukmo_system"]
