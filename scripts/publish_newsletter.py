#!/usr/bin/env python3
"""Publish the five newest BenNollWeather letters to S3.

The public Substack archive is the source. A check that cannot read it leaves
the current page in place.
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "bennollweather"
PAGE_KEY = "newsletter"
STATE_KEY = "newsletter/state.json"
ARCHIVE_URL = "https://www.bennollsays.com/api/v1/archive?sort=new&limit=5"
SITE_URL = "https://www.bennollsays.com"
SITE_NAME = "BenNollWeather"
KEEP = 5
USER_AGENT = "Mozilla/5.0 (compatible; BenNollWeather/newsletter)"

AP_MONTHS = {
    1: "Jan.",
    2: "Feb.",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "Aug.",
    9: "Sept.",
    10: "Oct.",
    11: "Nov.",
    12: "Dec.",
}

NAV = """
      <a href="/copernicus_imagery/index.html">All graphics</a>
      <a href="/latest_posts">Latest posts</a>
      <a href="/climate_imagery/weathernext3/index.html">DeepMind storm cards</a>
      <a href="/copernicus_imagery/snow/index.html">Snow heatmaps</a>
      <a href="/nmme/imagery/index.html">NMME</a>
      <a href="/atmospheric_moisture/index.html">ERA5 moisture</a>
      <a href="/climate_imagery/index.html">Climate imagery</a>
      <a href="/climate_imagery/strat_coupling/index.html">Polar vortex</a>
      <a href="/newsletter" aria-current="page">Newsletter</a>
""".strip("\n")


def aws(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["aws", *args], check=check, text=True, capture_output=True)


def fetch_bytes(url: str, timeout: int = 40) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def object_exists(key: str) -> bool:
    result = aws("s3api", "head-object", "--bucket", BUCKET, "--key", key, check=False)
    return result.returncode == 0


def download_key(key: str) -> str | None:
    if not object_exists(key):
        return None
    with tempfile.NamedTemporaryFile(delete=False) as handle:
        path = handle.name
    aws("s3", "cp", f"s3://{BUCKET}/{key}", path, "--only-show-errors")
    return Path(path).read_text(encoding="utf-8")


def upload_text(text: str, key: str, content_type: str, cache: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(text)
        path = Path(handle.name)
    aws(
        "s3",
        "cp",
        str(path),
        f"s3://{BUCKET}/{key}",
        "--content-type",
        content_type,
        "--cache-control",
        cache,
        "--only-show-errors",
    )
    path.unlink(missing_ok=True)


def ap_date(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    return f"{AP_MONTHS[moment.month]} {moment.day}, {moment.year}"


def parse_date(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, tail = text.split(".", 1)
        zone = ""
        if "+" in tail:
            zone = "+" + tail.split("+", 1)[1]
        elif "-" in tail:
            zone = "-" + tail.split("-", 1)[1]
        text = head + zone
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def cover_src(url: str | None) -> str | None:
    if not url:
        return None
    source = url
    marker = "/image/fetch/"
    if "substackcdn.com/image/fetch/" in url:
        rest = url.split(marker, 1)[1]
        for prefix in ("https%3A", "http%3A", "https://", "http://"):
            at = rest.find(prefix)
            if at >= 0:
                source = rest[at:]
                break
        if source.startswith("http://") or source.startswith("https://"):
            source = urllib.parse.quote(source, safe="")
        return "https://substackcdn.com/image/fetch/w_1400,c_limit,f_auto,q_auto:good/" + source
    return "https://substackcdn.com/image/fetch/w_1400,c_limit,f_auto,q_auto:good/" + urllib.parse.quote(url, safe="")


def parse_archive(payload: object) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise RuntimeError("The newsletter archive did not include any letters.")
    letters = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = (item.get("title") or "").strip()
        url = (item.get("canonical_url") or "").strip()
        posted = item.get("post_date")
        if not (title and url and posted):
            continue
        moment = parse_date(str(posted))
        subtitle = (item.get("subtitle") or item.get("description") or "").strip()
        preview = (item.get("truncated_body_text") or "").strip()
        if preview == subtitle:
            preview = ""
        letters.append(
            {
                "id": str(item.get("id") or url),
                "title": title,
                "subtitle": subtitle,
                "preview": preview,
                "url": url,
                "created": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "audience": item.get("audience") or "everyone",
                "cover": cover_src(item.get("cover_image")),
            }
        )
    if not letters:
        raise RuntimeError("The newsletter archive did not include any letters.")
    letters.sort(key=lambda item: item["created"], reverse=True)
    return letters[:KEEP]


def load_state() -> tuple[list[dict], bool]:
    raw = download_key(STATE_KEY)
    if not raw:
        return [], False
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("letters"), list):
        return data["letters"], True
    return [], False


def signature(letters: list[dict]) -> list:
    return [
        (item["id"], item["title"], item["subtitle"], item["preview"], item["audience"], item["cover"])
        for item in letters
    ]


def render_page(letters: list[dict]) -> str:
    articles = []
    for letter in letters:
        moment = datetime.strptime(letter["created"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        stamp = ap_date(moment)
        url = html.escape(letter["url"], quote=True)
        title = html.escape(letter["title"])
        cover = ""
        if letter.get("cover"):
            cover = (
                f'<a class="cover-link" href="{url}">'
                f'<img src="{html.escape(letter["cover"], quote=True)}" alt="{html.escape(letter["title"], quote=True)}">'
                f"</a>"
            )
        subscribers = '<span class="subscribers">Subscribers</span>' if letter.get("audience") == "only_paid" else ""
        dek = f'<p class="dek">{html.escape(letter["subtitle"])}</p>' if letter.get("subtitle") else ""
        preview = f"<p>{html.escape(letter['preview'])}</p>" if letter.get("preview") else ""
        articles.append(
            f"""
    <article class="letter" id="letter-{html.escape(letter['id'], quote=True)}">
      {cover}
      <div class="letter-body">
        <h2><a href="{url}">{title}</a></h2>
        <p class="meta"><time datetime="{letter['created']}">{stamp}</time>{subscribers}</p>
        {dek}
        {preview}
        <a class="read" href="{url}">Read the letter</a>
      </div>
    </article>""".strip("\n")
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Newsletter · Weather window shopping by BenNollWeather</title>
  <meta name="description" content="The five latest newsletters from {SITE_NAME}.">
  <link rel="stylesheet" href="https://fonts.bunny.net/css?family=libre-franklin:400,600,700">
  <style>
    :root {{ color-scheme: light dark; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "Libre Franklin", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f4f5f7; color: #171717; }}
    body > header {{ position: sticky; top: 0; z-index: 20; padding: 18px 24px; background: #fff; border-bottom: 1px solid #d9dce1; }}
    h1 {{ margin: 0 0 5px; font-size: 27px; }}
    body > header p {{ margin: 0; color: #5d626a; }}
    nav {{ margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }}
    nav a {{ color: inherit; text-decoration: none; border: 1px solid #c8ccd2; border-radius: 999px; padding: 7px 11px; background: #fff; }}
    nav a:hover {{ text-decoration: underline; }}
    nav a[aria-current="page"] {{ background: #e7eef8; border-color: #8aa8cc; font-weight: 700; }}
    main {{ max-width: 760px; margin: 0 auto; padding: 28px 20px 72px; }}
    .lede {{ margin: 0 0 22px; }}
    .lede h2 {{ margin: 0 0 6px; font-size: 22px; letter-spacing: -0.01em; }}
    .lede p {{ margin: 0; color: #5d626a; font-size: 15px; line-height: 1.45; }}
    .lede a {{ color: #1256a0; font-weight: 600; text-decoration: none; }}
    .lede a:hover {{ text-decoration: underline; }}
    .letter {{ overflow: hidden; margin: 0 0 18px; border: 1px solid #d9dce1; border-radius: 12px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.06); scroll-margin-top: 140px; }}
    .cover-link {{ display: block; background: #e8eaed; }}
    .cover-link img {{ display: block; width: 100%; height: auto; max-height: 640px; object-fit: contain; }}
    .letter-body {{ padding: 16px 18px 18px; }}
    .letter-body h2 {{ margin: 0 0 6px; font-size: 22px; letter-spacing: -0.02em; line-height: 1.25; }}
    .letter-body h2 a {{ color: inherit; text-decoration: none; }}
    .letter-body h2 a:hover {{ text-decoration: underline; }}
    .meta {{ margin: 0 0 12px; color: #6a7078; font-size: 13px; }}
    .subscribers {{ margin-left: 8px; font-weight: 700; }}
    .dek {{ margin: 0 0 10px; font-size: 17px; line-height: 1.45; }}
    .letter-body p {{ margin: 0 0 12px; font-size: 16px; line-height: 1.5; }}
    .read {{ color: #1256a0; font-size: 14px; font-weight: 700; text-decoration: none; }}
    .read:hover {{ text-decoration: underline; }}
    @media (max-width: 650px) {{
      body > header {{ padding: 16px; }}
      h1 {{ font-size: 22px; }}
      main {{ padding: 20px 14px 56px; }}
      .letter-body {{ padding: 14px; }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111317; color: #f3f4f6; }}
      body > header {{ background: #14161a; border-color: #333842; }}
      body > header p, .lede p, .meta {{ color: #aeb4bd; }}
      .lede a, .read {{ color: #7db7ff; }}
      nav a, .letter {{ background: #1b1e24; border-color: #373c46; }}
      nav a[aria-current="page"] {{ background: #29394d; border-color: #6086ad; }}
      .cover-link {{ background: #111317; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Weather window shopping by BenNollWeather</h1>
    <p>An always-updating gallery of operational weather graphics</p>
    <nav>
{NAV}
    </nav>
  </header>
  <main>
    <div class="lede">
      <h2>Newsletter</h2>
      <p>The five latest newsletters from <a href="{SITE_URL}">{SITE_NAME}</a>.</p>
    </div>
{chr(10).join(articles)}
  </main>
</body>
</html>
"""


def publish() -> int:
    previous, had_state = load_state()
    try:
        payload = json.loads(fetch_bytes(ARCHIVE_URL).decode("utf-8"))
        letters = parse_archive(payload)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError, ValueError) as error:
        print(f"Newsletter check failed ({error}). The current page was left in place.")
        return 1
    if had_state and signature(letters) == signature(previous[:KEEP]):
        print("No newsletter changes. The current page was left in place.")
        return 0
    checked = datetime.now(timezone.utc).replace(microsecond=0)
    upload_text(render_page(letters), PAGE_KEY, "text/html; charset=utf-8", "no-cache, no-store, must-revalidate")
    state = {"checked_utc": checked.strftime("%Y-%m-%dT%H:%M:%SZ"), "letters": letters}
    upload_text(json.dumps(state, ensure_ascii=False, indent=2), STATE_KEY, "application/json; charset=utf-8", "no-cache")
    print("Published " + ", ".join(item["title"] for item in letters))
    return 0


if __name__ == "__main__":
    raise SystemExit(publish())
