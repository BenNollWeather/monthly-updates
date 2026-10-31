#!/usr/bin/env bash
set -euo pipefail

export PYTHONHTTPSVERIFY=0
export CURL_CA_BUNDLE=""
export REQUESTS_CA_BUNDLE=""

: "${OPERATIONAL_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
: "${REPO_ROOT:=$(cd "$OPERATIONAL_DIR/.." && pwd)}"
: "${CONDA_ENV:=operational-monthly}"
: "${AWS_BIN:=aws}"
: "${AWS_BUCKET:=bennollweather}"
: "${AWS_PREFIX:=copernicus_imagery}"
: "${WORK_ROOT:=${TMPDIR:-/tmp}/monthly-updates/operational}"
if [[ -z "${AWS_PROFILE+x}" ]]; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    AWS_PROFILE=""
  else
    AWS_PROFILE="bennollweather"
  fi
fi
: "${SHAPEFILES_DIR:=$WORK_ROOT/shapefiles}"
: "${VP_CLIMO_DIR:=$WORK_ROOT/climo/vp}"
: "${VP_CLIM_START:=1991}"
: "${VP_CLIM_END:=2020}"
: "${VP_CLIMO_SOURCE:=auto}"
: "${IMAGERY_DIR:=$WORK_ROOT/copernicus_imagery}"
: "${WORK_DIR:=$WORK_ROOT/copernicus/operational}"
: "${LOG_DIR:=$WORK_ROOT/logs}"
: "${C3S_ARCHIVE_DIR:=$WORK_ROOT/imagery/c3s}"
: "${PYTHON_BIN:=python}"
# Optional: set MODEL_VERSIONS_FILE to override config/model_versions.json.

mkdir -p "$WORK_ROOT" "$IMAGERY_DIR" "$WORK_DIR" "$LOG_DIR" "$WORK_ROOT/downloads" "$WORK_ROOT/data" "$WORK_ROOT/imagery" "$WORK_ROOT/climate_stuff"

aws_cmd() {
  # An empty CA bundle is how the plot scripts skip local TLS inspection.
  # Current AWS CLI builds reject that empty value, so drop it for AWS calls.
  local -a env_args=()
  local name
  if [[ -n "${AWS_PROFILE}" ]]; then
    env_args+=(AWS_PROFILE="$AWS_PROFILE")
  else
    env_args+=(-u AWS_PROFILE)
  fi
  for name in REQUESTS_CA_BUNDLE CURL_CA_BUNDLE AWS_CA_BUNDLE; do
    if [[ -n "${!name+x}" && -z "${!name}" ]]; then
      env_args+=(-u "$name")
    fi
  done
  env "${env_args[@]}" "$AWS_BIN" "$@"
}

ensure_regions() {
  mkdir -p "$SHAPEFILES_DIR"
  "$PYTHON_BIN" "$REPO_ROOT/lib/regions.py" --out "$SHAPEFILES_DIR"
  export SHAPEFILES_DIR VP_CLIMO_DIR VP_CLIM_START VP_CLIM_END VP_CLIMO_SOURCE WORK_ROOT
}

publish_monitor() {
  local tag="$1"
  mkdir -p "$IMAGERY_DIR/monitor"
  local name src
  for name in superblend_precip_usa_season1.png superblend_precip_atlantic_season1.png superblend_precip_globe_season1.png; do
    src="$IMAGERY_DIR/$name"
    if [[ ! -f "$src" ]]; then
      echo "Missing expected seasonal map: $src" >&2
      return 1
    fi
    cp -f "$src" "$IMAGERY_DIR/monitor/${tag}_${name#superblend_}"
  done
}

cleanup_work() {
  if [[ "${KEEP_WORK:-0}" == "1" || "${SKIP_UPLOAD:-0}" == "1" ]]; then
    return 0
  fi
  rm -rf "$WORK_ROOT"
  echo "Deleted disposable work directory."
}

ensure_env() {
  if [[ "${USE_SYSTEM_PYTHON:-0}" == "1" ]]; then
    PYTHON_BIN="${PYTHON_BIN:-python}"
    return 0
  fi
  local conda_base=""
  if command -v conda >/dev/null 2>&1; then
    conda_base="$(conda info --base)"
  fi
  local conda_sh="${CONDA_SH:-${conda_base}/etc/profile.d/conda.sh}"
  if [[ ! -f "$conda_sh" ]]; then
    echo "Conda is not available. Set USE_SYSTEM_PYTHON=1 to use the current Python." >&2
    exit 1
  fi
  CONDA_SH="$conda_sh"
  # shellcheck disable=SC1090
  source "$conda_sh"

  if ! conda env list | awk '{print $1}' | grep -qx "$CONDA_ENV"; then
    echo "Creating conda environment: $CONDA_ENV"
    conda env create -n "$CONDA_ENV" -f "$OPERATIONAL_DIR/config/environment.yml"
  fi

  conda activate "$CONDA_ENV"
  PYTHON_BIN="$(command -v python)"

  # If the environment already existed but is missing dependencies, update it once
  # from the bundled environment.yml. This avoids failures such as missing legacy
  # notebook imports after a refactor.
  if ! "$PYTHON_BIN" - <<'PYDEPS'
import importlib
mods = [
    "numpy", "pandas", "xarray", "matplotlib", "cartopy", "cfgrib",
    "cdsapi", "cmocean", "metpy", "dateparser", "pygrib", "windspharm",
    "bottleneck", "dataframe_image",
]
missing = []
for mod in mods:
    try:
        importlib.import_module(mod)
    except Exception:
        missing.append(mod)
if missing:
    raise SystemExit("Missing Python dependencies: " + ", ".join(missing))
PYDEPS
  then
    echo "Updating conda environment dependencies: $CONDA_ENV"
    conda env update -n "$CONDA_ENV" -f "$OPERATIONAL_DIR/config/environment.yml" --prune
    conda activate "$CONDA_ENV"
    PYTHON_BIN="$(command -v python)"
  fi
}

run_py() {
  local name="$1"
  local script="$OPERATIONAL_DIR/scripts/${name}.py"
  local log="$LOG_DIR/${name}_$(date +%Y%m%d_%H%M%S).log"
  echo "---- Running ${name}.py ----"
  if [[ ! -f "$script" ]]; then
    echo "Missing script: $script" >&2
    exit 1
  fi
  # Wrap CDS retrieves so a month that has not been published exits 75.
  RELEASE_SCRIPT="$script" RELEASE_ROOT="$REPO_ROOT" "$PYTHON_BIN" -c '
import os
import runpy
import sys
from pathlib import Path
script = Path(os.environ["RELEASE_SCRIPT"]).resolve()
root = Path(os.environ["RELEASE_ROOT"]).resolve()
sys.path.insert(0, str(root))
sys.path.insert(0, str(script.parent))
from lib.cds_not_ready import install
install()
runpy.run_path(str(script), run_name="__main__")
' 2>&1 | tee "$log"
}

clean_grib_idx() {
  mkdir -p "$WORK_DIR"
  find "$WORK_ROOT" \( -name '*.idx' -o -name '*.grib.*.idx' \) -type f -delete || true
}

clean_c3s_imagery() {
  mkdir -p "$IMAGERY_DIR"
  find "$IMAGERY_DIR" -maxdepth 1 -type f -delete || true
  rm -rf "$IMAGERY_DIR/snow" "$IMAGERY_DIR/heatmaps"
  mkdir -p "$IMAGERY_DIR/snow" "$IMAGERY_DIR/heatmaps"
}

stage_snowfall_heatmaps() {
  local source_root="${1:-$C3S_ARCHIVE_DIR}"
  local destination_root="${2:-$IMAGERY_DIR/snow}"
  local retention_months="${SNOW_RETENTION_MONTHS:-2}"

  mkdir -p "$destination_root"

  if [[ ! -d "$source_root" ]]; then
    echo "Snowfall heatmap staging skipped; archive not found: $source_root" >&2
    return 0
  fi

  echo "---- Staging the newest $retention_months snowfall month(s) from $source_root ----"

  local -a retained_months=()
  while IFS= read -r month_dir; do
    [[ -n "$month_dir" ]] && retained_months+=("$month_dir")
  done < <(
    find "$source_root" -type f -path '*/heatmaps/*_snowfall_heatmap.png' -print \
      | sed -E "s#^${source_root%/}/([0-9]{4}-[0-9]{2})/.*#\1#" \
      | grep -E '^[0-9]{4}-[0-9]{2}$' \
      | sort -ru \
      | head -n "$retention_months"
  )

  # Remove previously staged month folders so an old month cannot be re-uploaded.
  find "$destination_root" -mindepth 1 -maxdepth 1 -type d -name '20??-??' -exec rm -rf {} +

  if [[ ${#retained_months[@]} -eq 0 ]]; then
    echo "No snowfall heatmaps were found under $source_root." >&2
    return 0
  fi

  local copied=0
  local month_dir source_file destination_dir
  for month_dir in "${retained_months[@]}"; do
    destination_dir="$destination_root/$month_dir"
    mkdir -p "$destination_dir"

    while IFS= read -r -d '' source_file; do
      cp -f "$source_file" "$destination_dir/$(basename "$source_file")"
      copied=$((copied + 1))
    done < <(find "$source_root/$month_dir/heatmaps" -maxdepth 1 -type f -name '*_snowfall_heatmap.png' -print0 2>/dev/null)
  done

  echo "Retained snowfall months: ${retained_months[*]}"
  echo "Staged $copied snowfall heatmap(s) in $destination_root."
}

prune_s3_snowfall_heatmaps() {
  local prefix="${1:-$AWS_PREFIX}"
  local prefix_clean="${prefix%/}"
  local retention_months="${SNOW_RETENTION_MONTHS:-2}"
  local snow_prefix="${prefix_clean}/snow/"
  local -a month_prefixes=()

  echo "---- Pruning S3 snowfall heatmaps to the newest $retention_months month(s) ----"

  while IFS= read -r month_prefix; do
    [[ -n "$month_prefix" && "$month_prefix" != "None" ]] && month_prefixes+=("$month_prefix")
  done < <(
    aws_cmd s3api list-objects-v2 \
      --bucket "$AWS_BUCKET" \
      --prefix "$snow_prefix" \
      --delimiter '/' \
      --query 'CommonPrefixes[].Prefix' \
      --output text \
      | tr '\t' '\n' \
      | grep -E "^${snow_prefix}[0-9]{4}-[0-9]{2}/$" \
      | sort -r
  )

  if [[ ${#month_prefixes[@]} -le $retention_months ]]; then
    echo "S3 already contains ${#month_prefixes[@]} snowfall month folder(s); nothing to prune."
    return 0
  fi

  local i old_prefix
  for ((i=retention_months; i<${#month_prefixes[@]}; i++)); do
    old_prefix="${month_prefixes[$i]}"
    echo "Deleting old snowfall month: s3://${AWS_BUCKET}/${old_prefix}"
    aws_cmd s3 rm \
      "s3://${AWS_BUCKET}/${old_prefix}" \
      --recursive
  done
}


html_escape() {
  local s="$1"
  s=${s//&/&amp;}
  s=${s//</&lt;}
  s=${s//>/&gt;}
  s=${s//\"/&quot;}
  s=${s//\'/&#39;}
  printf '%s' "$s"
}

generate_s3_index() {
  local prefix="${1:-$AWS_PREFIX}"
  local prefix_clean="${prefix%/}"
  local s3_index="s3://${AWS_BUCKET}/${prefix_clean}/index.html"
  local index_url="https://${AWS_BUCKET}.s3.amazonaws.com/${prefix_clean}/index.html"
  local tmp inventory
  tmp=$(mktemp)
  inventory=$(mktemp)

  echo "---- Generating visual S3 landing page for s3://${AWS_BUCKET}/${prefix_clean}/ ----"

  aws_cmd s3api list-objects-v2 \
    --bucket "$AWS_BUCKET" \
    --prefix "${prefix_clean}/" \
    --query 'Contents[].[Key,LastModified,Size]' \
    --output text > "$inventory"

  python3 - "$inventory" "$tmp" "$AWS_BUCKET" "$prefix_clean" <<'PY_INDEX'
import html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import quote

inventory_path, output_path, bucket, prefix = sys.argv[1:]
base_url = f"https://{bucket}.s3.amazonaws.com"
image_exts = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
items = []
with open(inventory_path, encoding="utf-8") as handle:
    for raw in handle:
        parts = raw.rstrip("\n").split("\t")
        if len(parts) < 3 or parts[0] == "None":
            continue
        key, modified, size_text = parts[:3]
        if key.endswith("/") or key == f"{prefix}/index.html":
            continue
        rel = key[len(prefix) + 1:] if key.startswith(prefix + "/") else key
        suffix = PurePosixPath(key).suffix.lower()
        if suffix not in image_exts:
            continue
        try:
            size = int(size_text)
        except ValueError:
            size = 0
        folder = rel.split("/", 1)[0] if "/" in rel else "c3s"
        # Heartbeat copies live under monitor/. They are not a public gallery.
        if folder == "monitor":
            continue
        stem = PurePosixPath(rel).stem.replace("_", " ").replace("-", " ")
        title = re.sub(r"\s+", " ", stem).strip().title()
        month_match = re.search(r"20\d{2}[-_/](?:0[1-9]|1[0-2])", rel)
        month = month_match.group(0).replace("_", "-").replace("/", "-") if month_match else ""
        url = base_url + "/" + "/".join(quote(part) for part in key.split("/"))
        items.append({"key": key, "rel": rel, "folder": folder, "modified": modified, "size": size, "url": url, "title": title, "month": month, "ext": suffix.lstrip(".").upper()})
items.sort(key=lambda x: (x["modified"], x["key"]), reverse=True)
folders = sorted({x["folder"] for x in items})

def human_size(n):
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024

def display_time(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%b. %-d, %Y · %H:%M UTC")
    except Exception:
        return value

def iso_epoch(value):
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except Exception:
        return 0

folder_copy = {
    "c3s": ("C3S outlooks", "The newest Copernicus seasonal forecast graphics.", "◉"),
    "snow": ("Snowfall heatmaps", "City-by-city C3S snowfall outlooks by forecast month.", "❄"),
    "heatmaps": ("Climate heatmaps", "Seasonal signal dashboards and probability matrices.", "▦"),
}
folder_cards = []
for folder in folders:
    count = sum(1 for item in items if item["folder"] == folder)
    title, desc, icon = folder_copy.get(folder, (folder.replace("_", " ").title(), f"Browse {count:,} archived graphics.", "↗"))
    folder_cards.append(f'<button class="collection" type="button" data-filter="{html.escape(folder.lower(), quote=True)}"><span class="collection-icon">{icon}</span><span><strong>{html.escape(title)}</strong><small>{html.escape(desc)}</small></span><b>{count:,}</b></button>')

cards = []
for i, item in enumerate(items):
    search_blob = " ".join([item["rel"], item["folder"], item["title"], item["month"], item["ext"]]).lower()
    cards.append(f'''<article class="asset" tabindex="0" data-index="{i}" data-search="{html.escape(search_blob, quote=True)}" data-folder="{html.escape(item['folder'].lower(), quote=True)}" data-time="{iso_epoch(item['modified'])}" data-size="{item['size']}"><a class="preview" href="{html.escape(item['url'], quote=True)}" target="_blank" rel="noopener" aria-label="View {html.escape(item['title'], quote=True)}"><img src="{html.escape(item['url'], quote=True)}" alt="{html.escape(item['title'], quote=True)}" loading="lazy"></a><div class="asset-copy"><span class="eyebrow">{html.escape(item['folder'])}</span><a class="asset-title" href="{html.escape(item['url'], quote=True)}" target="_blank" rel="noopener">{html.escape(item['title'])}</a><small>{display_time(item['modified'])} · {human_size(item['size'])} · {item['ext']}</small></div></article>''')

now = datetime.now(timezone.utc).strftime("%B %-d, %Y at %H:%M UTC")
chip_html = ''.join(f'<button class="chip" data-filter="{html.escape(f.lower(), quote=True)}">{html.escape(folder_copy.get(f,(f.replace("_"," ").title(),"",""))[0])}</button>' for f in folders)
short_tabs = {
    "copernicus_imagery": "/copernicus",
    "copernicus_imagery/snow": "/snow",
    "nmme/imagery": "/nmme",
    "atmospheric_moisture": "/moisture",
    "climate_imagery": "/climate",
}
current_tab = short_tabs.get(prefix, "")
def site_nav(current):
    def link(href, label):
        attr = ' aria-current="page"' if href == current else ""
        return f'<a href="{href}"{attr}>{label}</a>'
    script = """
    <script>
    (function () {
      var nav = document.currentScript.closest("nav");
      document.addEventListener("click", function (event) {
        nav.querySelectorAll("details[open]").forEach(function (menu) {
          if (!menu.contains(event.target)) menu.open = false;
        });
      });
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        nav.querySelectorAll("details[open]").forEach(function (menu) { menu.open = false; });
      });
    })();
    </script>"""
    lines = [
        link("/latest_posts", "Latest posts"),
        link("/articles", "Articles"),
        link("/newsletter", "Newsletters"),
        '<details class="menu">',
        "<summary>Graphics</summary>",
        '<div class="panel">',
        '<details class="menu">',
        "<summary>Long range</summary>",
        '<div class="panel">',
        link("/copernicus", "Copernicus"),
        link("/snow", "Snow"),
        link("/nmme", "NMME"),
        "</div>",
        "</details>",
        link("/moisture", "Moisture"),
        link("/deepmind", "DeepMind"),
        link("/polar_vortex", "Polar vortex"),
        link("/climate", "Climate stuff"),
        "</div>",
        "</details>",
        script.strip("\n"),
    ]
    inner = "\n".join(f"      {line}" for line in lines)
    return f'<nav aria-label="Sections">\n{inner}\n    </nav>'

GALLERY_NAV_CSS = """
    nav { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
    nav a, nav summary { color: inherit; text-decoration: none; border: 1px solid #c8ccd2; border-radius: 999px; padding: 7px 11px; background: #fff; font: inherit; cursor: pointer; }
    nav > a, nav > .menu > summary { display: inline-block; }
    nav summary { list-style: none; }
    nav summary::-webkit-details-marker { display: none; }
    nav summary::after { content: ""; display: inline-block; margin-left: 7px; border-width: 4px 4px 0; border-style: solid; border-color: currentColor transparent transparent; vertical-align: 2px; }
    nav a:hover, nav summary:hover, nav summary:focus-visible { text-decoration: underline; }
    nav a[aria-current="page"], nav .menu:has(a[aria-current="page"]) > summary { background: #e7eef8; border-color: #8aa8cc; font-weight: 700; }
    nav .menu { position: relative; }
    nav .panel { position: absolute; z-index: 30; top: calc(100% + 6px); left: 0; display: grid; gap: 6px; min-width: 190px; padding: 8px; border: 1px solid #d9dce1; border-radius: 12px; background: #fff; box-shadow: 0 8px 24px rgba(0,0,0,.12); }
    nav .panel a, nav .panel summary { display: block; text-align: left; }
    nav .menu .menu .panel { position: static; min-width: 0; margin-top: 6px; padding: 0 0 0 8px; border: 0; border-radius: 0; background: transparent; box-shadow: none; }
    @media (max-width: 650px) {
      nav .panel { position: static; margin-top: 6px; box-shadow: none; }
    }
    @media (prefers-color-scheme: dark) {
      nav a, nav summary, nav .panel { background: #1b1e24; border-color: #373c46; }
      nav a[aria-current="page"], nav .menu:has(a[aria-current="page"]) > summary { background: #29394d; border-color: #6086ad; }
      nav .menu .menu .panel { background: transparent; border-color: transparent; }
    }
""".strip("\n")
BRAND_CSS = """
    .brand { display: flex; align-items: center; gap: 20px; }
    .brand-copy { min-width: 0; }
    .brand-mark { flex: none; }
    .brand-mark img { display: block; height: 56px; width: auto; }
    @media (max-width: 650px) {
      .brand { gap: 12px; }
      .brand-mark img { height: 44px; }
    }
""".strip("\n")
BRAND_MARK = """<picture class="brand-mark">
        <source srcset="/latest_posts/brand/bnw-brick-offwhite.png" media="(prefers-color-scheme: dark)">
        <img src="/latest_posts/brand/bnw-brick-black.png" alt="Ben Noll Weather" width="1156" height="508">
      </picture>"""
nav = site_nav(current_tab)
page = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="/latest_posts/brand/favicon-snowflake-black.png" type="image/png" media="(prefers-color-scheme: light)">
  <link rel="icon" href="/latest_posts/brand/favicon-snowflake-offwhite.png" type="image/png" media="(prefers-color-scheme: dark)">
  <title>Weather window shopping by BenNollWeather</title>
  <link rel="stylesheet" href="https://fonts.bunny.net/css?family=libre-franklin:400,600,700">
  <style>
    :root {{ color-scheme: light dark; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Libre Franklin", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f5f7; color: #171717; }}
    header {{ position: sticky; top: 0; z-index: 5; padding: 18px 24px; background: rgba(255,255,255,.96); border-bottom: 1px solid #d9dce1; backdrop-filter: blur(8px); }}
    h1 {{ margin: 0 0 5px; font-size: 27px; }}
    {BRAND_CSS}
    header p {{ margin: 0; color: #5d626a; }}
    {GALLERY_NAV_CSS}
    main {{ padding: 22px; max-width: 1500px; margin: 0 auto; }}
    .controls {{ display: grid; grid-template-columns: minmax(220px,1fr) auto; gap: 10px; margin-bottom: 10px; }}
    input, select, button {{ font: inherit; }}
    .search, .sort {{ border: 1px solid #c8ccd2; border-radius: 9px; padding: 10px 12px; background: #fff; color: inherit; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 7px; margin: 0 0 18px; }}
    .chip {{ border: 1px solid #c8ccd2; border-radius: 999px; padding: 7px 11px; background: #fff; color: inherit; cursor: pointer; }}
    .chip.active {{ background: #e7eef8; border-color: #8aa8cc; }}
    .collections {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(230px,1fr)); gap: 12px; margin-bottom: 24px; }}
    .collection {{ display: grid; grid-template-columns: 1fr auto; gap: 8px; text-align: left; padding: 14px; border: 1px solid #d9dce1; border-radius: 10px; background: #fff; color: inherit; cursor: pointer; }}
    .collection strong, .collection small {{ display: block; }}
    .collection small {{ margin-top: 4px; color: #6a7078; }}
    .collection.active {{ background: #e7eef8; border-color: #8aa8cc; }}
    .gallery-tools {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 0 0 16px; }}
    .count {{ margin: 0; color: #5d626a; }}
    .view-controls {{ display: flex; gap: 6px; }}
    .view-button {{ border: 1px solid #c8ccd2; border-radius: 8px; padding: 7px 10px; background: #fff; color: inherit; cursor: pointer; }}
    .view-button[aria-pressed="true"] {{ background: #e7eef8; border-color: #8aa8cc; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill,minmax(280px,1fr)); gap: 18px; }}
    .asset {{ overflow: hidden; border: 1px solid #d9dce1; border-radius: 10px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.06); }}
    .asset[hidden] {{ display: none !important; }}
    .preview {{ display: flex; min-height: 190px; align-items: center; justify-content: center; background: #e8eaed; }}
    .preview img {{ display: block; width: 100%; height: 230px; object-fit: contain; }}
    .asset-copy {{ padding: 12px 14px 14px; }}
    .eyebrow {{ display: block; margin-bottom: 5px; color: #6a7078; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }}
    .asset-title {{ display: block; overflow-wrap: anywhere; color: #1256a0; font-weight: 700; text-decoration: none; }}
    .asset-title:hover {{ text-decoration: underline; }}
    .asset-copy small {{ display: block; margin-top: 6px; color: #6a7078; font-size: 13px; }}
    .grid.list-view {{ display: block; }}
    .grid.list-view .asset {{ display: grid; grid-template-columns: 110px minmax(0,1fr); margin-bottom: 10px; }}
    .grid.list-view .preview {{ min-height: 84px; }}
    .grid.list-view .preview img {{ height: 84px; }}
    .grid.list-view .asset-copy {{ display: flex; flex-direction: column; justify-content: center; }}
    .empty {{ display: none; padding: 30px; text-align: center; color: #6a7078; }}
    @media (max-width: 650px) {{ .controls {{ grid-template-columns: 1fr; }} .gallery-tools {{ align-items: flex-start; flex-direction: column; }} }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111317; color: #f3f4f6; }}
      header {{ background: rgba(20,22,26,.96); border-color: #333842; }}
      header p, .count, .asset-copy small, .eyebrow, .collection small, .empty {{ color: #aeb4bd; }}
      nav a, .asset, .collection, .chip, .view-button, .search, .sort {{ background: #1b1e24; border-color: #373c46; }}
      .chip.active, .collection.active, .view-button[aria-pressed="true"] {{ background: #29394d; border-color: #6086ad; }}
      .preview {{ background: #242830; }}
      .asset-title {{ color: #7db7ff; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="brand-copy">
        <h1>Weather window shopping by BenNollWeather</h1>
        <p>Bringing weather and climate data to life</p>
      </div>
      {BRAND_MARK}
    </div>
    {nav}
  </header>
  <main>
    <div class="controls"><input id="search" class="search" type="search" placeholder="Search graphics, cities, variables or months…"><select id="sort" class="sort"><option value="newest">Newest</option><option value="oldest">Oldest</option><option value="name">Name</option><option value="size">Largest</option></select></div>
    <div class="chips"><button class="chip active" data-filter="">All</button>{chip_html}</div>
    <section class="collections">{''.join(folder_cards)}</section>
    <div class="gallery-tools"><p id="resultCount" class="count">{len(items):,} images &middot; Updated {html.escape(now)}</p><div class="view-controls"><button id="gridView" class="view-button" type="button" aria-pressed="false">▦ Grid</button><button id="listView" class="view-button" type="button" aria-pressed="true">☰ List</button></div></div>
    <section id="grid" class="grid">{''.join(cards)}</section>
    <p id="empty" class="empty">No graphics match those filters.</p>
  </main>
  <script>
    const gallery=document.getElementById('grid');
    const cards=[...gallery.querySelectorAll('.asset')];
    const search=document.getElementById('search');
    const count=document.getElementById('resultCount');
    const empty=document.getElementById('empty');
    const sort=document.getElementById('sort');
    let activeFilter='';
    function applyFilter(){{
      const q=search.value.trim().toLowerCase();
      let visible=0;
      cards.forEach(card=>{{
        const show=(!activeFilter||card.dataset.folder===activeFilter)&&(!q||card.dataset.search.includes(q));
        card.hidden=!show;
        if(show) visible+=1;
      }});
      count.textContent=`${{visible.toLocaleString()}} image${{visible===1?'':'s'}} · Updated {html.escape(now)}`;
      empty.style.display=visible?'none':'block';
    }}
    function setFilter(value){{
      activeFilter=value;
      document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('active',x.dataset.filter===value));
      document.querySelectorAll('.collection').forEach(x=>x.classList.toggle('active',x.dataset.filter===value));
      applyFilter();
    }}
    function reorder(){{
      const mode=sort.value;
      cards.sort((a,b)=>mode==='oldest'?+a.dataset.time-+b.dataset.time:mode==='name'?a.dataset.search.localeCompare(b.dataset.search):mode==='size'?+b.dataset.size-+a.dataset.size:+b.dataset.time-+a.dataset.time).forEach(card=>gallery.appendChild(card));
      applyFilter();
    }}
    search.addEventListener('input',applyFilter);
    sort.addEventListener('change',reorder);
    document.querySelectorAll('.chip').forEach(x=>x.addEventListener('click',()=>setFilter(x.dataset.filter)));
    document.querySelectorAll('.collection').forEach(x=>x.addEventListener('click',()=>setFilter(x.dataset.filter)));
    const gridView=document.getElementById('gridView');
    const listView=document.getElementById('listView');
    function setView(mode){{
      const list=mode==='list';
      gallery.classList.toggle('list-view',list);
      gridView.setAttribute('aria-pressed',String(!list));
      listView.setAttribute('aria-pressed',String(list));
      localStorage.setItem('weather-gallery-view',mode);
    }}
    gridView.addEventListener('click',()=>setView('grid'));
    listView.addEventListener('click',()=>setView('list'));
    const savedView=localStorage.getItem('weather-gallery-view');
    setView(savedView==='grid'?'grid':'list');
    applyFilter();
  </script>
</body>
</html>'''
with open(output_path, "w", encoding="utf-8") as handle:
    handle.write(page)

PY_INDEX

  aws_cmd s3 cp "$tmp" "$s3_index" \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, no-store, must-revalidate"
  # The S3 REST endpoint has no redirects. Publish the same page at the
  # short key so bennollweather.s3.amazonaws.com/copernicus keeps working.
  # CloudFront still rewrites that path onto the long key.
  if [[ "$prefix_clean" == "copernicus_imagery" ]]; then
    aws_cmd s3 cp "$tmp" "s3://${AWS_BUCKET}/copernicus" \
      --content-type "text/html; charset=utf-8" \
      --cache-control "no-cache, no-store, must-revalidate"
    aws_cmd s3 cp "$tmp" "s3://${AWS_BUCKET}/c3s" \
      --content-type "text/html; charset=utf-8" \
      --cache-control "no-cache, no-store, must-revalidate"
  fi
  rm -f "$tmp" "$inventory"

  echo "Index uploaded: $index_url"
}

refresh_s3_portal() {
  local portal_runner="$SCRIPT_DIR/update_s3_portal_standalone.sh"

  if [[ "${UPDATE_S3_PORTAL:-1}" == "0" ]]; then
    echo "Portal refresh skipped because UPDATE_S3_PORTAL=0."
    return 0
  fi

  if [[ ! -f "$portal_runner" ]]; then
    echo "Portal refresh skipped; runner not found: $portal_runner" >&2
    return 0
  fi

  echo "---- Refreshing S3 graphics portal ----"
  AWS_BIN="$AWS_BIN" \
  AWS_PROFILE="$AWS_PROFILE" \
  AWS_BUCKET="$AWS_BUCKET" \
  USE_SYSTEM_PYTHON="${USE_SYSTEM_PYTHON:-0}" \
  bash "$portal_runner"
}

upload_imagery() {
  if [[ "${SKIP_UPLOAD:-0}" == "1" ]]; then
    echo "Upload skipped because SKIP_UPLOAD=1."
    return 0
  fi
  local local_dir="${1:-$IMAGERY_DIR}"
  local prefix="${2:-$AWS_PREFIX}"
  local s3_path="s3://${AWS_BUCKET}/${prefix%/}/"
  local base_url="https://${AWS_BUCKET}.s3.amazonaws.com/${prefix%/}/"

  if [[ ! -d "$local_dir" ]]; then
    echo "Upload skipped; directory does not exist: $local_dir" >&2
    return 0
  fi

  echo "---- Uploading $local_dir to $s3_path ----"
  local out
  set +e
  out=$(aws_cmd s3 sync "$local_dir" "$s3_path" \
    --exclude '.git/*' --exclude '.gitignore' --exclude '.DS_Store' --exclude '.gitattributes' 2>&1)
  local status=$?
  set -e
  echo "$out"
  if [[ $status -ne 0 ]]; then
    echo "AWS sync failed" >&2
    return $status
  fi

  # Keep only the newest snowfall month folders in S3. This runs after sync so
  # a newly uploaded month is considered before the oldest month is removed.
  prune_s3_snowfall_heatmaps "$prefix"

  echo
  echo "Uploaded file URLs:"
  local any=0
  while IFS= read -r line; do
    if [[ "$line" == *"upload:"* ]]; then
      local s3_file="${line##* to }"
      local rel="${s3_file#$s3_path}"
      echo "${base_url}${rel}"
      any=1
    fi
  done <<< "$out"
  if [[ $any -eq 0 ]]; then
    echo "No new or updated files were uploaded by aws s3 sync."
  fi

  generate_s3_index "$prefix"
  refresh_s3_portal
}
