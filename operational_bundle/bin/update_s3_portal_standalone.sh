#!/usr/bin/env bash
set -euo pipefail

# Build a standalone public graphics portal without modifying operational_lib.sh
# or the existing Copernicus index generator.
#
# Publishes:
#   s3://bennollweather/nmme/imagery/index.html
#   s3://bennollweather/atmospheric_moisture/index.html
#   s3://bennollweather/climate_imagery/index.html
#
# Source content:
#   /nmme/imagery/     <- s3://bennollweather/nmme/imagery/
#   /atmospheric_moisture/ <- s3://bennollweather/atmospheric_moisture/
#   /climate_imagery/  <- s3://bennollweather/climate_imagery/
#
# The existing page at /copernicus_imagery/index.html is patched with
# persistent navigation links after its normal index is regenerated.

# Standalone AWS configuration. These can be overridden with environment variables.
AWS_BIN="${AWS_BIN:-aws}"
if [[ -z "${AWS_PROFILE+x}" ]]; then
  if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
    AWS_PROFILE=""
  else
    AWS_PROFILE="bennollweather"
  fi
fi
AWS_BUCKET="${AWS_BUCKET:-bennollweather}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-https://${AWS_BUCKET}.s3.amazonaws.com}"

if ! command -v "$AWS_BIN" >/dev/null 2>&1; then
  echo "AWS CLI not found: $AWS_BIN" >&2
  exit 1
fi
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

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

upload_html() {
  local local_file="$1"
  local destination_key="$2"

  aws_cmd s3 cp "$local_file" "s3://${AWS_BUCKET}/${destination_key}" \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, no-store, must-revalidate"

  echo "Published: ${PUBLIC_BASE_URL}/${destination_key}"
}

build_gallery() {
  local source_prefix="$1"
  local publish_prefix="$2"
  local page_title="$3"
  local page_description="$4"

  source_prefix="${source_prefix#/}"
  source_prefix="${source_prefix%/}/"
  publish_prefix="${publish_prefix#/}"
  publish_prefix="${publish_prefix%/}"

  local safe_name="${publish_prefix//\//_}"
  local inventory_file="$TMP_DIR/${safe_name}_objects.tsv"
  local html_file="$TMP_DIR/${safe_name}_index.html"

  echo "---- Building /${publish_prefix}/ from s3://${AWS_BUCKET}/${source_prefix} ----"

  aws_cmd s3api list-objects-v2 \
    --bucket "$AWS_BUCKET" \
    --prefix "$source_prefix" \
    --query 'Contents[].[Key,LastModified,Size]' \
    --output text > "$inventory_file"

  python3 - "$inventory_file" "$html_file" "$PUBLIC_BASE_URL" \
    "$source_prefix" "$page_title" "$page_description" <<'PY'
import html
import sys
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import quote

(
    inventory_path,
    output_path,
    public_base_url,
    source_prefix,
    page_title,
    page_description,
) = sys.argv[1:]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
items = []

with open(inventory_path, "r", encoding="utf-8") as handle:
    for raw_line in handle:
        line = raw_line.rstrip("\n")
        if not line or line == "None":
            continue

        parts = line.split("\t")
        if len(parts) < 3:
            continue

        key, modified, size_text = parts[0], parts[1], parts[2]
        if key.endswith("/") or key.endswith("/index.html"):
            continue
        if PurePosixPath(key).suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        relative_name = key[len(source_prefix):] if key.startswith(source_prefix) else key

        # Climate gallery exclusions:
        # - omit the entire coolwx/ directory tree
        # - omit the WeatherNext 3 storm cards (they have their own page)
        # - omit the strat-troposphere coupling stills (they have their own tab)
        # - omit these three top-level image files only
        if source_prefix == "climate_imagery/":
            if relative_name.startswith(("coolwx/", "weathernext3/", "strat_coupling/")):
                continue
            if relative_name in {"storm_tracks.png", "storm_tracks2.png", "DJI_0367.jpg"}:
                continue

        encoded_key = "/".join(quote(part) for part in key.split("/"))
        url = f"{public_base_url.rstrip('/')}/{encoded_key}"

        try:
            size = int(size_text)
        except ValueError:
            size = 0

        items.append(
            {
                "key": key,
                "name": relative_name,
                "modified": modified,
                "size": size,
                "url": url,
            }
        )

items.sort(key=lambda item: (item["modified"], item["key"]), reverse=True)


def human_size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def display_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value

cards = []
for item in items:
    safe_name = html.escape(item["name"])
    safe_url = html.escape(item["url"], quote=True)
    cards.append(
        f"""
        <article class="card">
          <a class="image-link" href="{safe_url}" target="_blank" rel="noopener">
            <img src="{safe_url}" alt="{safe_name}" loading="lazy">
          </a>
          <div class="card-meta">
            <a class="filename" href="{safe_url}" target="_blank" rel="noopener">{safe_name}</a>
            <div class="details">{display_time(item['modified'])} &middot; {human_size(item['size'])}</div>
          </div>
        </article>
        """
    )

empty_state = "" if cards else '<p class="empty">No image files were found in this location.</p>'
generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(page_title)}</title>
  <link rel="stylesheet" href="https://fonts.bunny.net/css?family=libre-franklin:400,600,700">
  <style>
    :root {{ color-scheme: light dark; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Libre Franklin", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f5f7;
      color: #171717;
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 5;
      padding: 18px 24px;
      background: rgba(255,255,255,.96);
      border-bottom: 1px solid #d9dce1;
      backdrop-filter: blur(8px);
    }}
    h1 {{ margin: 0 0 5px; font-size: 25px; }}
    header p {{ margin: 0; color: #5d626a; }}
    nav {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }}
    nav a {{
      color: inherit;
      text-decoration: none;
      border: 1px solid #c8ccd2;
      border-radius: 999px;
      padding: 7px 11px;
      background: #fff;
    }}
    nav a:hover {{ text-decoration: underline; }}
    main {{ padding: 22px; }}
    .count {{ margin: 0 0 16px; color: #5d626a; }}
    .gallery-tools {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin: 0 0 16px; }}
    .view-controls {{ display: flex; gap: 6px; }}
    .view-button {{ border: 1px solid #c8ccd2; border-radius: 8px; padding: 7px 10px; background: #fff; color: inherit; cursor: pointer; }}
    .view-button[aria-pressed="true"] {{ background: #e7eef8; border-color: #8aa8cc; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 18px;
    }}
    .card {{
      overflow: hidden;
      border: 1px solid #d9dce1;
      border-radius: 10px;
      background: #fff;
      box-shadow: 0 2px 8px rgba(0,0,0,.06);
    }}
    .image-link {{
      display: flex;
      min-height: 190px;
      align-items: center;
      justify-content: center;
      background: #e8eaed;
    }}
    img {{ display: block; width: 100%; height: 230px; object-fit: contain; }}
    .card-meta {{ padding: 12px 14px 14px; }}
    .filename {{
      display: block;
      overflow-wrap: anywhere;
      color: #1256a0;
      font-weight: 700;
      text-decoration: none;
    }}
    .filename:hover {{ text-decoration: underline; }}
    .details {{ margin-top: 6px; color: #6a7078; font-size: 13px; }}
    .grid.list-view {{ display: block; }}
    .grid.list-view .card {{ display: grid; grid-template-columns: 110px minmax(0,1fr); margin-bottom: 10px; }}
    .grid.list-view .image-link {{ min-height: 84px; }}
    .grid.list-view img {{ height: 84px; }}
    .grid.list-view .card-meta {{ display: flex; flex-direction: column; justify-content: center; }}
    .empty {{ padding: 30px; text-align: center; }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111317; color: #f3f4f6; }}
      header {{ background: rgba(20,22,26,.96); border-color: #333842; }}
      header p, .count, .details {{ color: #aeb4bd; }}
      nav a, .card, .view-button {{ background: #1b1e24; border-color: #373c46; }}
      .view-button[aria-pressed="true"] {{ background: #29394d; border-color: #6086ad; }}
      .image-link {{ background: #242830; }}
      .filename {{ color: #7db7ff; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(page_title)}</h1>
    <p>{html.escape(page_description)}</p>
    <nav>
      <a href="/copernicus">All graphics</a>
      <a href="/latest_posts">Latest posts</a>
      <a href="/deepmind">DeepMind storm cards</a>
      <a href="/copernicus">C3S</a>
      <a href="/snow">Snow heatmaps</a>
      <a href="/nmme">NMME</a>
      <a href="/moisture">ERA5 moisture</a>
      <a href="/climate">Climate imagery</a>
      <a href="/polar_vortex">Polar vortex</a>
      <a href="/newsletter">Newsletter</a>
    </nav>
  </header>
  <main>
    <div class="gallery-tools"><p class="count">{len(items):,} image{'s' if len(items) != 1 else ''} &middot; Updated {generated}</p><div class="view-controls"><button id="gridView" class="view-button" type="button" aria-pressed="false">▦ Grid</button><button id="listView" class="view-button" type="button" aria-pressed="true">☰ List</button></div></div>
    {empty_state}
    <section id="gallery" class="grid">{''.join(cards)}</section>
  </main>
  <script>const gallery=document.getElementById("gallery");const gridView=document.getElementById("gridView");const listView=document.getElementById("listView");function setView(mode){{const list=mode==="list";gallery.classList.toggle("list-view",list);gridView.setAttribute("aria-pressed",String(!list));listView.setAttribute("aria-pressed",String(list));localStorage.setItem("weather-gallery-view",mode);}}gridView.addEventListener("click",()=>setView("grid"));listView.addEventListener("click",()=>setView("list"));const savedView=localStorage.getItem("weather-gallery-view");setView(savedView==="grid"?"grid":"list");</script>
</body>
</html>
"""

with open(output_path, "w", encoding="utf-8") as handle:
    handle.write(page)
PY

  upload_html "$html_file" "${publish_prefix}/index.html"
  # Same page at the short S3 key. CloudFront rewrites the pretty path
  # onto the long key, so direct S3 links need their own object.
  case "$publish_prefix" in
    copernicus_imagery/snow) upload_html "$html_file" "snow" ;;
    nmme/imagery) upload_html "$html_file" "nmme" ;;
    atmospheric_moisture) upload_html "$html_file" "moisture" ;;
    climate_imagery) upload_html "$html_file" "climate" ;;
  esac
}

build_root_portal() {
  local html_file="$TMP_DIR/root_index.html"

  cat > "$html_file" <<HTML
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Weather window shopping by BenNollWeather</title>
  <link rel="stylesheet" href="https://fonts.bunny.net/css?family=libre-franklin:400,600,700">
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Libre Franklin", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f4f5f7;
      color: #171717;
    }
    main { max-width: 1100px; margin: 0 auto; padding: 48px 22px; }
    h1 { margin: 0 0 8px; font-size: clamp(30px, 5vw, 52px); }
    .intro { margin: 0 0 30px; color: #5d626a; font-size: 18px; }
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 18px;
    }
    .tile {
      display: block;
      min-height: 180px;
      padding: 24px;
      border: 1px solid #d9dce1;
      border-radius: 14px;
      background: #fff;
      color: inherit;
      text-decoration: none;
      box-shadow: 0 3px 12px rgba(0,0,0,.06);
      transition: transform .12s ease, box-shadow .12s ease;
    }
    .tile:hover { transform: translateY(-2px); box-shadow: 0 7px 18px rgba(0,0,0,.10); }
    .tile h2 { margin: 0 0 10px; font-size: 24px; }
    .tile p { margin: 0; color: #626870; line-height: 1.45; }
    .path { margin-top: 18px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }
    footer { margin-top: 28px; color: #717780; font-size: 14px; }
    @media (prefers-color-scheme: dark) {
      body { background: #111317; color: #f3f4f6; }
      .intro, .tile p, footer { color: #aeb4bd; }
      .tile { background: #1b1e24; border-color: #373c46; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Weather window shopping</h1>
    <p class="intro">A visual storefront of seasonal forecasts, climate signals and atmospheric curiosities by BenNollWeather.</p>
    <section class="grid">
      <a class="tile" href="/copernicus_imagery/index.html">
        <h2>C3S</h2>
        <p>Copernicus seasonal forecast graphics and related products.</p>
        <div class="path">/copernicus_imagery</div>
      </a>
      <a class="tile" href="/copernicus_imagery/snow/index.html">
        <h2>Snow heatmaps</h2>
        <p>Monthly city snowfall probability heatmaps from the C3S archive.</p>
        <div class="path">/copernicus_imagery/snow</div>
      </a>
      <a class="tile" href="/nmme/imagery/index.html">
        <h2>NMME</h2>
        <p>North American Multi-Model Ensemble outlook imagery.</p>
        <div class="path">/nmme</div>
      </a>
      <a class="tile" href="/atmospheric_moisture/index.html">
        <h2>ERA5 moisture</h2>
        <p>Atmospheric moisture and precipitable-water imagery.</p>
        <div class="path">/era5</div>
      </a>
      <a class="tile" href="/climate_imagery/index.html">
        <h2>Climate imagery</h2>
        <p>All image outputs stored under the climate imagery archive.</p>
        <div class="path">/climate_imagery</div>
      </a>
    </section>
    <footer>Generated $(date -u '+%Y-%m-%d %H:%M UTC')</footer>
  </main>
</body>
</html>
HTML

  # Root index is intentionally not published because this bucket
  # does not expose top-level index.html publicly.
  :
}


patch_copernicus_index() {
  # The modern Copernicus landing page already contains its own navigation.
  # Do not inject the legacy light navigation block, which clashes with the
  # dark portal theme and can produce unreadable white-on-white buttons.
  echo "---- Copernicus portal already includes navigation; legacy injection skipped ----"
}

# ONLY_GALLERY=<publish prefix> rebuilds just that one page (e.g. a notebook refreshing its own tab); unset = rebuild all.
wanted() { [[ -z "${ONLY_GALLERY:-}" || "${ONLY_GALLERY%/}" == "$1" ]]; }

if wanted "copernicus_imagery/snow"; then
  build_gallery \
    "copernicus_imagery/snow" \
    "copernicus_imagery/snow" \
    "Snowfall heatmaps" \
    "Monthly C3S snowfall heatmaps by city"
fi

if wanted "nmme/imagery"; then
  build_gallery \
    "nmme/imagery" \
    "nmme/imagery" \
    "NMME graphics" \
    "North American Multi-Model Ensemble imagery"
fi

if wanted "atmospheric_moisture"; then
  build_gallery \
    "atmospheric_moisture" \
    "atmospheric_moisture" \
    "ERA5 atmospheric moisture" \
    "Precipitable water imagery and climate extremes"
fi

if wanted "climate_imagery"; then
  build_gallery \
    "climate_imagery" \
    "climate_imagery" \
    "Climate imagery" \
    "Image files from the climate imagery archive"
fi

# NOTE: the "Polar vortex" tab (/climate_imagery/strat_coupling/) is NOT built here. Its card page (index.html), latest.json,
# diagnostics and images are written by oper/ecmwf/strat_troposphere_coupling_ens.ipynb on every run; building a generic
# gallery here would overwrite that page. The tab is still excluded from the generic "Climate imagery" gallery above.

# Root portal omitted: bucket public-read policy does not expose top-level index.html.
if [[ -z "${ONLY_GALLERY:-}" ]]; then
  patch_copernicus_index
fi

echo
echo "Portal update complete."
echo "Home:              ${PUBLIC_BASE_URL}/copernicus_imagery/index.html"
echo "C3S:               ${PUBLIC_BASE_URL}/copernicus_imagery/index.html"
echo "Snow heatmaps:     ${PUBLIC_BASE_URL}/copernicus_imagery/snow/index.html"
echo "NMME:              ${PUBLIC_BASE_URL}/nmme/imagery/index.html"
echo "ERA5 moisture:     ${PUBLIC_BASE_URL}/atmospheric_moisture/index.html"
echo "Climate imagery:   ${PUBLIC_BASE_URL}/climate_imagery/index.html"
echo "Polar vortex:      ${PUBLIC_BASE_URL}/climate_imagery/strat_coupling/index.html"
