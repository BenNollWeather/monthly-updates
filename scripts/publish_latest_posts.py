#!/usr/bin/env python3
"""Publish the ten newest original @BenNollWeather posts to S3.

Replies and reposts are left out. The public profile page only includes the
newest originals, so this keeps a state file and carries forward earlier posts
until newer ones replace them. A check that cannot read the profile leaves the
current page in place.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BUCKET = "bennollweather"
PAGE_KEY = "latest_posts"
STATE_KEY = "latest_posts/state.json"
MEDIA_PREFIX = "latest_posts/media"
PROFILE_URL = "https://x.com/BenNollWeather"
HANDLE = "BenNollWeather"
DISPLAY_NAME = "Ben Noll"
AVATAR_URL = "https://pbs.twimg.com/profile_images/770432803708162048/juiCF3Sp_400x400.jpg"
AVATAR_PATH = f"/{MEDIA_PREFIX}/avatar.jpg"
KEEP = 10
USER_AGENT = "Mozilla/5.0 (compatible; BenNollWeather/latest-posts)"

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
      <a href="/latest_posts" aria-current="page">Latest posts</a>
      <a href="/climate_imagery/weathernext3/index.html">DeepMind storm cards</a>
      <a href="/copernicus_imagery/snow/index.html">Snow heatmaps</a>
      <a href="/nmme/imagery/index.html">NMME</a>
      <a href="/atmospheric_moisture/index.html">ERA5 moisture</a>
      <a href="/climate_imagery/index.html">Climate imagery</a>
      <a href="/climate_imagery/strat_coupling/index.html">Polar vortex</a>
      <a href="/newsletter">Newsletter</a>
""".strip("\n")


def aws(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    command = ["aws", *args]
    return subprocess.run(command, check=check, text=True, capture_output=True)


def fetch_bytes(url: str, timeout: int = 40) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_profile() -> str:
    """Read the public profile. GitHub runners are blocked, so fall back to Jina."""
    try:
        page = fetch_bytes(PROFILE_URL).decode("utf-8", "replace")
        if "full_text" in page and "entry_id" in page:
            return page
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(f"Direct profile fetch failed ({error}). Trying a backup fetch.", file=sys.stderr)
    request = urllib.request.Request(
        "https://r.jina.ai/" + PROFILE_URL,
        headers={
            "User-Agent": USER_AGENT,
            "X-Return-Format": "html",
            "X-Engine": "direct",
            "X-No-Cache": "true",
        },
    )
    with urllib.request.urlopen(request, timeout=50) as response:
        return response.read().decode("utf-8", "replace")


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


def upload_file(path: Path, key: str, content_type: str, cache: str) -> None:
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


def upload_text(text: str, key: str, content_type: str, cache: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(text)
        path = Path(handle.name)
    upload_file(path, key, content_type, cache)
    path.unlink(missing_ok=True)


def ap_stamp(moment: datetime) -> str:
    moment = moment.astimezone(timezone.utc)
    month = AP_MONTHS[moment.month]
    return f"{month} {moment.day}, {moment.year} · {moment:%H:%M} UTC"


def comma(value: int) -> str:
    return f"{value:,}"


def decode_profile_text(value: str) -> str:
    return value.replace("\\\\n", "\n").replace("\\/", "/").replace('\\"', '"')


def _last_match(pattern: str, text: str) -> re.Match | None:
    found = list(re.finditer(pattern, text))
    return found[-1] if found else None


def choose_video(urls: list[str]) -> str | None:
    mp4s = []
    for url in urls:
        clean = url.split("?", 1)[0]
        if clean.endswith(".mp4"):
            mp4s.append(clean)
    if not mp4s:
        return None

    def area(url: str) -> int:
        match = re.search(r"/(\d+)x(\d+)/", url)
        if match:
            return int(match.group(1)) * int(match.group(2))
        if "/tweet_video/" in url:
            return 10**12
        return 0

    return max(mp4s, key=area)


def parse_profile_html(page: str) -> list[dict]:
    parts = re.split(r'entry_id\\":\\"tweet-', page)
    if len(parts) < 2:
        raise RuntimeError("The public profile did not include original posts.")
    ids: list[str] = []
    bodies: list[str] = [parts[0]]
    for part in parts[1:]:
        match = re.match(r"(\d+)", part)
        if not match:
            continue
        ids.append(match.group(1))
        bodies.append(part[match.end() :])
    posts = []
    for post_id, body in zip(ids, bodies):
        text_match = re.search(r'\\"full_text\\":\\"(.*?)\\",\\"', body)
        if not text_match:
            continue
        text = decode_profile_text(text_match.group(1)).strip()
        if text.startswith("RT @"):
            continue
        text_at = text_match.start()
        before = body[max(0, text_at - 2500) : text_at]
        after = body[text_at : text_at + 8000]
        reply = re.search(r'\\"in_reply_to_status_id_str\\":\\"(\d+)\\"', before + after)
        if reply:
            continue
        # The profile shell includes the account creation time. The tweet time
        # is the created_at_ms immediately before full_text.
        created = _last_match(r'\\"created_at_ms\\":(\d+)', before)
        likes = _last_match(r'\\"favorite_count\\":(\d+)', before)
        reposts = _last_match(r'\\"retweet_count\\":(\d+)', before)
        replies = _last_match(r'\\"reply_count\\":(\d+)', before)
        views = re.search(r'\\"views\\":\{\\"count\\":\\"(\d+)\\"', after)
        if not (created and likes and reposts and replies):
            continue
        videos = re.findall(r"https://video\.twimg\.com/[^\\\"\s]+", after)
        photos = re.findall(r"https://pbs\.twimg\.com/media/[A-Za-z0-9_-]+", after)
        video = choose_video(videos)
        photo = photos[0] if photos else None
        if video and "/tweet_video/" in video:
            kind = "gif"
        elif video:
            kind = "video"
        elif photo:
            kind = "photo"
        else:
            kind = None
        remote_poster = poster_for(page, video) if video else None
        moment = datetime.fromtimestamp(int(created.group(1)) / 1000, timezone.utc)
        posts.append(
            {
                "id": post_id,
                "created": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "text": text,
                "likes": int(likes.group(1)),
                "reposts": int(reposts.group(1)),
                "replies": int(replies.group(1)),
                "views": int(views.group(1)) if views else None,
                "kind": kind,
                "media_path": media_path(post_id, kind),
                "poster_path": f"/{MEDIA_PREFIX}/{post_id}-poster.jpg" if video else None,
                "remote_media": video or (photo_url(photo) if photo else None),
                "remote_poster": remote_poster,
                "paragraphs_html": None,
            }
        )
    if not posts:
        raise RuntimeError("The public profile did not include original posts.")
    posts.sort(key=lambda item: item["created"], reverse=True)
    return posts


def photo_url(stem: str) -> str:
    name = stem.rstrip("/").split("/")[-1]
    name = name.split("?", 1)[0]
    if name.endswith(".jpg"):
        name = name[: -len(".jpg")]
    return f"https://pbs.twimg.com/media/{name}?format=jpg&name=large"


def media_path(post_id: str, kind: str | None) -> str | None:
    if kind in {"gif", "video"}:
        return f"/{MEDIA_PREFIX}/{post_id}.mp4"
    if kind == "photo":
        return f"/{MEDIA_PREFIX}/{post_id}.jpg"
    return None


def poster_for(page: str, video: str | None) -> str | None:
    if not video:
        return None
    if "/tweet_video/" in video:
        name = video.rsplit("/", 1)[-1].replace(".mp4", "")
        return f"https://pbs.twimg.com/tweet_video_thumb/{name}?format=jpg&name=large"
    match = re.search(r"/amplify_video/(\d+)/", video)
    if not match:
        return None
    thumb = re.search(
        rf"https://pbs\.twimg\.com/amplify_video_thumb/{match.group(1)}/img/[A-Za-z0-9_-]+",
        page,
    )
    if not thumb:
        return None
    return thumb.group(0) + "?format=jpg&name=large"


def plain_paragraph(fragment: str) -> str:
    text = re.sub(r"<a [^>]*>(.*?)</a>", r"\1", fragment, flags=re.S)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def parse_existing_page(page: str) -> list[dict]:
    posts = []
    for post_id, body in re.findall(r'<article class="post" id="post-(\d+)">(.*?)</article>', page, re.S):
        created = re.search(r'datetime="([^"]+)"', body)
        paragraphs = re.findall(r"<p>(.*?)</p>", body, re.S)
        if not created or not paragraphs:
            continue
        media = re.search(r'<div class="media">(.*?)</div>', body, re.S)
        media_html = media.group(1) if media else ""
        source = re.search(r'<source src="([^"]+)"', media_html)
        image = re.search(r'<img src="([^"]+)"', media_html)
        poster = re.search(r'poster="([^"]+)"', media_html)
        if source and "autoplay" in media_html:
            kind = "gif"
        elif source:
            kind = "video"
        elif image:
            kind = "photo"
        else:
            kind = None

        def stat(label: str) -> int | None:
            match = re.search(rf"<b>([\d,]+)</b> {label}", body)
            return int(match.group(1).replace(",", "")) if match else None

        posts.append(
            {
                "id": post_id,
                "created": created.group(1),
                "text": "\n\n".join(plain_paragraph(item) for item in paragraphs),
                "likes": stat("likes") or 0,
                "reposts": stat("reposts") or 0,
                "replies": stat("repl(?:y|ies)") or 0,
                "views": stat("views"),
                "kind": kind,
                "media_path": source.group(1) if source else (image.group(1) if image else None),
                "poster_path": poster.group(1) if poster else None,
                "remote_media": None,
                "remote_poster": None,
                "paragraphs_html": paragraphs,
            }
        )
    return posts


def load_state() -> tuple[list[dict], bool]:
    """Return saved posts and whether a state file already exists.

    The first publish has to write the page even when the posts match the
    live HTML, so the hourly wording and navigation replace the snapshot.
    """
    raw = download_key(STATE_KEY)
    if raw:
        data = json.loads(raw)
        if isinstance(data, dict) and isinstance(data.get("posts"), list):
            return data["posts"], True
    page = download_key(PAGE_KEY)
    if page:
        return parse_existing_page(page), False
    return [], False


def merge_posts(fresh: list[dict], previous: list[dict]) -> list[dict]:
    by_id = {item["id"]: item for item in previous}
    for item in fresh:
        prior = by_id.get(item["id"])
        if prior and prior.get("text") == item["text"]:
            item["paragraphs_html"] = prior.get("paragraphs_html")
            item["media_path"] = prior.get("media_path") or item["media_path"]
            item["poster_path"] = prior.get("poster_path") or item["poster_path"]
            if prior.get("media_path"):
                item["remote_media"] = None
            if prior.get("poster_path"):
                item["remote_poster"] = None
        by_id[item["id"]] = item
    posts = list(by_id.values())
    posts.sort(key=lambda item: item["created"], reverse=True)
    return posts[:KEEP]


def signature(posts: list[dict]) -> list:
    return [
        (item["id"], item["text"], item["likes"], item["reposts"], item["replies"], item["views"], item.get("kind"))
        for item in posts
    ]


def ensure_asset(url: str | None, key: str, content_type: str) -> bool:
    if not url or object_exists(key):
        return object_exists(key)
    try:
        payload = fetch_bytes(url)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        print(f"Could not download {url}: {error}", file=sys.stderr)
        return False
    suffix = ".jpg" if "image" in content_type else ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(payload)
        path = Path(handle.name)
    upload_file(path, key, content_type, "public, max-age=604800")
    path.unlink(missing_ok=True)
    return True


def ensure_media(posts: list[dict]) -> None:
    ensure_asset(AVATAR_URL, AVATAR_PATH.lstrip("/"), "image/jpeg")
    for post in posts:
        kind = post.get("kind")
        path = post.get("media_path")
        if path and post.get("remote_media"):
            content_type = "video/mp4" if kind in {"gif", "video"} else "image/jpeg"
            if not ensure_asset(post["remote_media"], path.lstrip("/"), content_type):
                post["media_path"] = None
                post["kind"] = None
        poster = post.get("poster_path")
        if poster and post.get("remote_poster"):
            if not ensure_asset(post["remote_poster"], poster.lstrip("/"), "image/jpeg"):
                post["poster_path"] = None


def expand_url(url: str, cache: dict[str, str]) -> str:
    if url in cache:
        return cache[url]
    if "t.co/" not in url:
        cache[url] = url
        return url
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            final = response.geturl()
    except (urllib.error.URLError, TimeoutError, OSError):
        final = url
    cache[url] = final
    return final


def drop_status_permalink(post: dict, cache: dict[str, str]) -> None:
    """X appends a t.co link that only points back at the post itself."""
    match = re.search(r"\s+https://t\.co/\w+\s*$", post["text"])
    if not match:
        return
    final = expand_url(match.group(0).strip(), cache)
    if re.search(rf"(?:twitter|x)\.com/[^/]+/status/{post['id']}(?:$|[/?#])", final):
        post["text"] = post["text"][: match.start()].rstrip()


def link_label(url: str) -> str:
    stripped = re.sub(r"^https?://", "", url).strip("/")
    if len(stripped) > 72:
        return stripped[:69] + "..."
    return stripped


def linkify(text: str, cache: dict[str, str]) -> str:
    pieces = re.split(r"(https?://[^\s<]+|#\w+|@\w+)", text)
    rendered = []
    for piece in pieces:
        if piece.startswith("http://") or piece.startswith("https://"):
            target = expand_url(piece, cache)
            label = link_label(target) if "t.co/" in piece else link_label(piece)
            rendered.append(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')
        elif piece.startswith("#") and len(piece) > 1:
            tag = piece[1:]
            rendered.append(f'<a href="https://x.com/hashtag/{html.escape(tag, quote=True)}">{html.escape(piece)}</a>')
        elif piece.startswith("@") and len(piece) > 1:
            name = piece[1:]
            rendered.append(f'<a href="https://x.com/{html.escape(name, quote=True)}">{html.escape(piece)}</a>')
        else:
            rendered.append(html.escape(piece))
    return "".join(rendered)


def paragraph_html(post: dict, cache: dict[str, str]) -> str:
    stored = post.get("paragraphs_html")
    if stored:
        return "".join(f"<p>{item}</p>" for item in stored)
    blocks = [block.strip() for block in re.split(r"\n+", post["text"]) if block.strip()]
    return "".join(f"<p>{linkify(block, cache)}</p>" for block in blocks)


def media_html(post: dict) -> str:
    path = post.get("media_path")
    if not path:
        return ""
    label = html.escape(post["text"].split("\n", 1)[0][:180], quote=True)
    kind = post.get("kind")
    if kind == "gif":
        poster = f' poster="{html.escape(post["poster_path"], quote=True)}"' if post.get("poster_path") else ""
        inner = (
            f'<video autoplay muted loop playsinline controls preload="metadata"{poster} aria-label="{label}">'
            f'<source src="{html.escape(path, quote=True)}" type="video/mp4"></video>'
        )
    elif kind == "video":
        poster = f' poster="{html.escape(post["poster_path"], quote=True)}"' if post.get("poster_path") else ""
        inner = (
            f'<video controls playsinline preload="metadata"{poster} aria-label="{label}">'
            f'<source src="{html.escape(path, quote=True)}" type="video/mp4"></video>'
        )
    else:
        inner = f'<img src="{html.escape(path, quote=True)}" alt="{label}" loading="lazy">'
    return f'<div class="media">{inner}</div>'


def stats_html(post: dict) -> str:
    replies = post["replies"]
    reply_label = "reply" if replies == 1 else "replies"
    items = [
        f"<li><b>{comma(post['likes'])}</b> likes</li>",
        f"<li><b>{comma(post['reposts'])}</b> reposts</li>",
        f"<li><b>{comma(replies)}</b> {reply_label}</li>",
    ]
    if post.get("views") is not None:
        items.append(f"<li><b>{comma(post['views'])}</b> views</li>")
    return "".join(items)


def render_page(posts: list[dict], checked: datetime) -> str:
    cache: dict[str, str] = {}
    articles = []
    for post in posts:
        moment = datetime.strptime(post["created"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        stamp = ap_stamp(moment)
        status = f"https://x.com/{HANDLE}/status/{post['id']}"
        articles.append(
            f"""
    <article class="post" id="post-{post['id']}">
      <header class="post-head">
        <img class="avatar" src="{AVATAR_PATH}" alt="" width="46" height="46">
        <div class="who">
          <strong>{DISPLAY_NAME}</strong>
          <span class="meta"><a href="https://x.com/{HANDLE}">@{HANDLE}</a> · <a href="{status}"><time datetime="{post['created']}">{stamp}</time></a></span>
        </div>
      </header>
      <div class="post-body">
        {paragraph_html(post, cache)}
      </div>
      {media_html(post)}
      <footer class="post-foot">
        <ul class="stats">
          {stats_html(post)}
        </ul>
        <a class="view-link" href="{status}">View on X</a>
      </footer>
    </article>""".strip("\n")
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Latest posts · Weather window shopping by BenNollWeather</title>
  <meta name="description" content="The 10 newest original posts from @{HANDLE}. Replies and reposts are not included.">
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
    .post {{ overflow: hidden; margin: 0 0 18px; border: 1px solid #d9dce1; border-radius: 12px; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.06); scroll-margin-top: 140px; }}
    .post-head {{ position: static; display: flex; gap: 12px; align-items: center; padding: 16px 18px 0; }}
    .avatar {{ width: 46px; height: 46px; border-radius: 50%; object-fit: cover; background: #e8eaed; }}
    .who {{ min-width: 0; }}
    .who strong {{ display: block; font-size: 15px; line-height: 1.25; }}
    .who .meta {{ display: block; margin-top: 2px; color: #6a7078; font-size: 13px; font-weight: 400; }}
    .who a {{ color: inherit; text-decoration: none; }}
    .who a:hover {{ text-decoration: underline; }}
    .post-body {{ padding: 12px 18px 0; font-size: 17px; line-height: 1.5; }}
    .post-body p {{ margin: 0 0 12px; }}
    .post-body a {{ color: #1256a0; font-weight: 600; }}
    .post-body a:hover {{ text-decoration: underline; }}
    .media {{ display: flex; align-items: center; justify-content: center; margin: 2px 18px 0; overflow: hidden; border-radius: 10px; background: #000; }}
    .media img, .media video {{ display: block; width: 100%; height: auto; max-height: 720px; object-fit: contain; background: #000; }}
    .post-foot {{ display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center; justify-content: space-between; padding: 12px 18px 16px; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 6px 14px; margin: 0; padding: 0; list-style: none; color: #6a7078; font-size: 13px; }}
    .stats b {{ color: #171717; font-weight: 600; }}
    .view-link {{ color: #1256a0; font-size: 13px; font-weight: 700; text-decoration: none; }}
    .view-link:hover {{ text-decoration: underline; }}
    @media (max-width: 650px) {{
      body > header {{ padding: 16px; }}
      h1 {{ font-size: 22px; }}
      main {{ padding: 20px 14px 56px; }}
      .post-head, .post-body, .post-foot {{ padding-left: 14px; padding-right: 14px; }}
      .media {{ margin-left: 14px; margin-right: 14px; }}
    }}
    @media (prefers-color-scheme: dark) {{
      body {{ background: #111317; color: #f3f4f6; }}
      body > header {{ background: #14161a; border-color: #333842; }}
      body > header p, .lede p, .who .meta, .stats {{ color: #aeb4bd; }}
      .lede a, .post-body a, .view-link {{ color: #7db7ff; }}
      nav a, .post {{ background: #1b1e24; border-color: #373c46; }}
      nav a[aria-current="page"] {{ background: #29394d; border-color: #6086ad; }}
      .avatar {{ background: #242830; }}
      .stats b {{ color: #f3f4f6; }}
      .media, .media img, .media video {{ background: #000; }}
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
      <h2>Latest posts</h2>
      <p>The 10 newest posts from <a href="https://x.com/{HANDLE}">@{HANDLE}</a>.</p>
    </div>
{chr(10).join(articles)}
  </main>
  <script>
    document.querySelectorAll("video").forEach(function (video) {{
      function showStill() {{
        var poster = video.getAttribute("poster");
        if (!poster || video.dataset.fellBack) return;
        video.dataset.fellBack = "1";
        var img = document.createElement("img");
        img.src = poster;
        img.alt = video.getAttribute("aria-label") || "";
        video.replaceWith(img);
      }}
      video.addEventListener("error", showStill);
      video.querySelectorAll("source").forEach(function (source) {{
        source.addEventListener("error", showStill);
      }});
      if (video.error) showStill();
    }});
  </script>
</body>
</html>
"""


def publish(profile_html: str | None = None) -> int:
    previous, had_state = load_state()
    try:
        page = profile_html if profile_html is not None else fetch_profile()
        fresh = parse_profile_html(page)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, json.JSONDecodeError) as error:
        print(f"Profile check failed ({error}). The current page was left in place.")
        return 1
    link_cache: dict[str, str] = {}
    for item in fresh:
        drop_status_permalink(item, link_cache)
    posts = merge_posts(fresh, previous)
    if had_state and previous and signature(posts) == signature(previous[:KEEP]):
        print("No post changes. The current page was left in place.")
        return 0
    checked = datetime.now(timezone.utc).replace(microsecond=0)
    ensure_media(posts)
    rendered = render_page(posts, checked)
    upload_text(rendered, PAGE_KEY, "text/html; charset=utf-8", "no-cache, no-store, must-revalidate")
    state = {"checked_utc": checked.strftime("%Y-%m-%dT%H:%M:%SZ"), "posts": posts}
    upload_text(json.dumps(state, ensure_ascii=False, indent=2), STATE_KEY, "application/json; charset=utf-8", "no-cache")
    print(f"Published {len(posts)} posts: " + ", ".join(item["id"] for item in posts))
    return 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--html":
        posts = parse_profile_html(Path(sys.argv[2]).read_text(encoding="utf-8"))
        for post in posts:
            print(post["id"], post["created"], post["kind"], post["likes"], post["text"].split("\n", 1)[0][:70])
        return 0
    return publish()


if __name__ == "__main__":
    raise SystemExit(main())
