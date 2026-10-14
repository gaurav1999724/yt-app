"""Fetch B-roll from Pixabay (default) or Unsplash, with text-slide fallback."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from pipeline.config import Config, normalize_broll_provider
from pipeline.fonts import load_font
from pipeline.jsonutil import load_json_file

# Pixabay/Unsplash search poorly with Devanagari — map to English stock terms
_HINDI_FALLBACK_KEYWORDS = [
    "youtube analytics dashboard",
    "retention graph chart",
    "person scrolling phone",
    "content creator studio",
    "smartphone social media",
    "hook attention closeup",
    "checklist notepad desk",
    "audience watching video",
    "laptop typing workspace",
    "red warning alert screen",
]


def english_search_query(raw: str) -> str:
    """Build an English stock-search query from an ON SCREEN cue."""
    text = (raw or "").strip()
    if not text:
        return "technology abstract"
    # Prefer Latin tokens / quoted English already in the cue
    latin = re.findall(r"[A-Za-z][A-Za-z0-9+\-]{1,}", text)
    if latin:
        return " ".join(latin[:8])
    # Hindi-only cue → stable generic English keyword
    idx = int(hashlib.sha1(text.encode("utf-8")).hexdigest(), 16) % len(
        _HINDI_FALLBACK_KEYWORDS
    )
    return _HINDI_FALLBACK_KEYWORDS[idx]

_FALLBACK_PALETTES = [
    ((20, 40, 90), (245, 197, 66), (245, 247, 250)),
    ((90, 24, 40), (90, 220, 200), (255, 255, 255)),
    ((18, 70, 55), (255, 180, 70), (245, 247, 250)),
    ((55, 30, 90), (255, 120, 160), (255, 255, 255)),
    ((30, 30, 30), (120, 200, 255), (245, 247, 250)),
]


def _cache_key(query: str) -> str:
    return hashlib.sha1(query.lower().encode("utf-8")).hexdigest()[:16]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines[:6]


def _text_slide(
    path: Path,
    width: int,
    height: int,
    seconds: float,
    label: str,
    beat_index: int,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    bg, accent, fg = _FALLBACK_PALETTES[beat_index % len(_FALLBACK_PALETTES)]
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, width, int(height * 0.28)], fill=tuple(max(0, c - 20) for c in bg))
    draw.rectangle([0, height - 24, width, height], fill=accent)
    draw.rectangle([36, 36, 52, height - 36], fill=accent)

    title_font = load_font(72 if height > width else 56)
    body_font = load_font(54 if height > width else 42)
    draw.text((72, 80), f"बीट {beat_index + 1}", font=title_font, fill=accent)

    lines = _wrap(draw, label, body_font, width - 140)
    y = height // 2 - (len(lines) * 70) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=body_font)
        tw = bbox[2] - bbox[0]
        x = (width - tw) // 2
        draw.text((x + 3, y + 3), line, font=body_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=body_font, fill=fg)
        y += 70

    png_path = path.with_suffix(".png")
    img.save(png_path, format="PNG")

    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(png_path),
        "-t",
        f"{max(seconds, 1.0):.3f}",
        "-vf",
        f"scale={width}:{height},fps=30,format=yuv420p",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return path
    except (subprocess.CalledProcessError, FileNotFoundError):
        return png_path


def _download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    headers = {"User-Agent": "youtube-agent-skill/1.0"}
    r = requests.get(url, timeout=60, stream=True, headers=headers)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    return dest


def search_pixabay(query: str, cfg: Config) -> Path | None:
    """Prefer Pixabay video clips; fall back to photos."""
    if not cfg.pixabay_api_key:
        return None
    q = english_search_query(query)
    cache_dir = cfg.cache_dir / "pixabay"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(f"pixabay|{q}|{cfg.video_format}")
    meta_path = cache_dir / f"{key}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        local = Path(meta["path"])
        if local.exists():
            return local
    # 1) Videos
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": cfg.pixabay_api_key,
                "q": q,
                "per_page": 5,
                "safesearch": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits") or []
    except requests.RequestException:
        hits = []

    if hits:
        videos = hits[0].get("videos") or {}
        # Prefer medium HD for Shorts/long
        for quality in ("medium", "large", "small", "tiny"):
            entry = videos.get(quality) or {}
            url = entry.get("url")
            if url:
                dest = cache_dir / f"{key}.mp4"
                _download(url, dest)
                meta_path.write_text(
                    json.dumps(
                        {
                            "query": query,
                            "search_query": q,
                            "path": str(dest),
                            "type": "video",
                            "provider": "pixabay",
                            "pixabay_id": hits[0].get("id"),
                        },
                        indent=2,
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return dest

    # 2) Photos
    orientation = "vertical" if cfg.video_format == "shorts" else "horizontal"
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": cfg.pixabay_api_key,
                "q": q,
                "image_type": "photo",
                "orientation": orientation,
                "safesearch": "true",
                "per_page": 5,
            },
            timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("hits") or []
    except requests.RequestException:
        return None

    if not photos:
        return None
    url = photos[0].get("largeImageURL") or photos[0].get("webformatURL")
    if not url:
        return None
    dest = cache_dir / f"{key}.jpg"
    _download(url, dest)
    meta_path.write_text(
        json.dumps(
            {
                "query": query,
                "search_query": q,
                "path": str(dest),
                "type": "image",
                "provider": "pixabay",
                "pixabay_id": photos[0].get("id"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return dest


def search_unsplash_photo(query: str, cfg: Config) -> Path | None:
    if not cfg.unsplash_access_key:
        return None
    q = english_search_query(query)
    cache_dir = cfg.cache_dir / "unsplash"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(f"unsplash|{q}|{cfg.video_format}")
    meta_path = cache_dir / f"{key}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        local = Path(meta["path"])
        if local.exists():
            return local

    orientation = "portrait" if cfg.video_format == "shorts" else "landscape"
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {cfg.unsplash_access_key}"},
            params={
                "query": q,
                "per_page": 5,
                "orientation": orientation,
                "content_filter": "high",
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except requests.RequestException:
        return None

    if not results:
        return None

    urls = results[0].get("urls") or {}
    url = urls.get("regular") or urls.get("full") or urls.get("small")
    if not url:
        return None

    dest = cache_dir / f"{key}.jpg"
    _download(url, dest)

    download_loc = (results[0].get("links") or {}).get("download_location")
    if download_loc:
        try:
            requests.get(
                download_loc,
                headers={"Authorization": f"Client-ID {cfg.unsplash_access_key}"},
                timeout=15,
            )
        except requests.RequestException:
            pass

    meta_path.write_text(
        json.dumps(
            {
                "query": query,
                "search_query": q,
                "path": str(dest),
                "type": "image",
                "provider": "unsplash",
                "unsplash_id": results[0].get("id"),
                "photographer": (results[0].get("user") or {}).get("name"),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return dest


def provider_for_run(run_dir: Path, cfg: Config) -> str:
    idea = load_json_file(run_dir / "idea.json", {})
    if isinstance(idea, dict) and idea.get("broll_provider"):
        return normalize_broll_provider(str(idea["broll_provider"]), cfg.default_broll_provider)
    return cfg.default_broll_provider


def resolve_broll(
    queries: list[str],
    cfg: Config,
    run_dir: Path,
    beat_durations: list[float],
    provider: str | None = None,
) -> list[Path]:
    """Return one media path per beat from the selected provider."""
    chosen = normalize_broll_provider(provider, cfg.default_broll_provider)
    out_dir = run_dir / "broll"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    print(f"B-roll provider: {chosen}")
    for i, query in enumerate(queries):
        dur = beat_durations[i] if i < len(beat_durations) else 3.0
        search_q = english_search_query(query)
        found = None
        if chosen == "pixabay":
            found = search_pixabay(query, cfg)
        else:
            found = search_unsplash_photo(query, cfg)
        source = "api" if found is not None else "fallback"
        if found is None:
            # Show English search term on fallback slides (Devanagari needs Noto)
            found = _text_slide(
                out_dir / f"beat_{i:02d}.mp4",
                cfg.width,
                cfg.height,
                max(dur, 2.0),
                search_q,
                i,
            )
        paths.append(found)
        print(f"  beat {i+1}: search={search_q!r} source={source}")
    manifest = [
        {
            "query": q,
            "search_query": english_search_query(q),
            "path": str(p),
            "provider": chosen,
        }
        for q, p in zip(queries, paths)
    ]
    (run_dir / "broll.json").write_text(
        json.dumps({"provider": chosen, "items": manifest}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return paths
