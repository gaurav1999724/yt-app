"""Fetch B-roll from Pixabay (default) or Unsplash, with text-slide fallback."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
    # English label — Hind/Nirmala render Latin+Devanagari; keep slides readable
    draw.text((72, 80), f"Beat {beat_index + 1}", font=title_font, fill=accent)

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
    if dest.exists() and dest.stat().st_size > 50_000:
        return dest
    headers = {"User-Agent": "youtube-agent-skill/1.0"}
    tmp = dest.with_suffix(dest.suffix + ".part")
    r = requests.get(url, timeout=90, stream=True, headers=headers)
    r.raise_for_status()
    with open(tmp, "wb") as f:
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                f.write(chunk)
    if tmp.stat().st_size < 10_000:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Download too small: {url}")
    tmp.replace(dest)
    return dest


def _pixabay_video_url(hit: dict) -> str | None:
    videos = hit.get("videos") or {}
    for quality in ("medium", "large", "small", "tiny"):
        entry = videos.get(quality) or {}
        url = entry.get("url")
        if url:
            return url
    return None


def search_pixabay(query: str, cfg: Config) -> Path | None:
    """Prefer Pixabay video clips; fall back to photos. Tries several hits."""
    if not cfg.pixabay_api_key:
        print("  pixabay: no PIXABAY_API_KEY")
        return None
    q = english_search_query(query)
    cache_dir = cfg.cache_dir / "pixabay"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(f"pixabay|{q}|{cfg.video_format}")
    meta_path = cache_dir / f"{key}.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            local = Path(meta["path"])
            if local.exists() and local.stat().st_size > 50_000:
                return local
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    hits: list = []
    try:
        resp = requests.get(
            "https://pixabay.com/api/videos/",
            params={
                "key": cfg.pixabay_api_key,
                "q": q,
                "per_page": 10,
                "safesearch": "true",
            },
            timeout=30,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits") or []
    except requests.RequestException as exc:
        print(f"  pixabay videos error: {exc}")

    for hit in hits[:8]:
        url = _pixabay_video_url(hit)
        if not url:
            continue
        dest = cache_dir / f"{key}.mp4"
        try:
            _download(url, dest)
            meta_path.write_text(
                json.dumps(
                    {
                        "query": query,
                        "search_query": q,
                        "path": str(dest),
                        "type": "video",
                        "provider": "pixabay",
                        "pixabay_id": hit.get("id"),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return dest
        except (requests.RequestException, RuntimeError, OSError) as exc:
            print(f"  pixabay video download fail id={hit.get('id')}: {exc}")
            continue

    orientation = "vertical" if cfg.video_format == "shorts" else "horizontal"
    photos: list = []
    try:
        resp = requests.get(
            "https://pixabay.com/api/",
            params={
                "key": cfg.pixabay_api_key,
                "q": q,
                "image_type": "photo",
                "orientation": orientation,
                "safesearch": "true",
                "per_page": 10,
            },
            timeout=30,
        )
        resp.raise_for_status()
        photos = resp.json().get("hits") or []
    except requests.RequestException as exc:
        print(f"  pixabay photos error: {exc}")
        return None

    for photo in photos[:8]:
        url = photo.get("largeImageURL") or photo.get("webformatURL")
        if not url:
            continue
        dest = cache_dir / f"{key}.jpg"
        try:
            _download(url, dest)
            meta_path.write_text(
                json.dumps(
                    {
                        "query": query,
                        "search_query": q,
                        "path": str(dest),
                        "type": "image",
                        "provider": "pixabay",
                        "pixabay_id": photo.get("id"),
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            return dest
        except (requests.RequestException, RuntimeError, OSError) as exc:
            print(f"  pixabay photo download fail: {exc}")
            continue
    return None


def search_unsplash_photo(query: str, cfg: Config) -> Path | None:
    if not cfg.unsplash_access_key:
        print("  unsplash: no UNSPLASH_ACCESS_KEY")
        return None
    q = english_search_query(query)
    cache_dir = cfg.cache_dir / "unsplash"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(f"unsplash|{q}|{cfg.video_format}")
    meta_path = cache_dir / f"{key}.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            local = Path(meta["path"])
            if local.exists() and local.stat().st_size > 20_000:
                return local
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    orientation = "portrait" if cfg.video_format == "shorts" else "landscape"
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            headers={"Authorization": f"Client-ID {cfg.unsplash_access_key}"},
            params={
                "query": q,
                "per_page": 8,
                "orientation": orientation,
                "content_filter": "high",
            },
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results") or []
    except requests.RequestException as exc:
        print(f"  unsplash error: {exc}")
        return None

    for result in results[:6]:
        urls = result.get("urls") or {}
        url = urls.get("regular") or urls.get("full") or urls.get("small")
        if not url:
            continue
        dest = cache_dir / f"{key}.jpg"
        try:
            _download(url, dest)
        except (requests.RequestException, RuntimeError, OSError) as exc:
            print(f"  unsplash download fail: {exc}")
            continue

        download_loc = (result.get("links") or {}).get("download_location")
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
                    "unsplash_id": result.get("id"),
                    "photographer": (result.get("user") or {}).get("name"),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return dest
    return None


def provider_for_run(run_dir: Path, cfg: Config) -> str:
    idea = load_json_file(run_dir / "idea.json", {})
    if isinstance(idea, dict) and idea.get("broll_provider"):
        return normalize_broll_provider(str(idea["broll_provider"]), cfg.default_broll_provider)
    return cfg.default_broll_provider


def _fetch_stock(query: str, cfg: Config, preferred: str) -> tuple[Path | None, str]:
    """Try preferred provider, then the other. Returns (path, source_label)."""
    order = (
        ("pixabay", "unsplash")
        if preferred == "pixabay"
        else ("unsplash", "pixabay")
    )
    for name in order:
        found = (
            search_pixabay(query, cfg)
            if name == "pixabay"
            else search_unsplash_photo(query, cfg)
        )
        if found is not None:
            return found, name
    return None, "fallback"


def _stage_media(src: Path, dest: Path) -> Path:
    """Copy stock media into the run folder so compose always has a stable path."""
    if src.resolve() == dest.resolve():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


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
    print(f"B-roll provider: {chosen} (auto-fallback to other API if needed)")
    if not cfg.pixabay_api_key and not cfg.unsplash_access_key:
        print("WARNING: No PIXABAY_API_KEY or UNSPLASH_ACCESS_KEY — text slides only")

    manifest_items: list[dict] = []
    for i, query in enumerate(queries):
        dur = beat_durations[i] if i < len(beat_durations) else 3.0
        search_q = english_search_query(query)
        found, source = _fetch_stock(query, cfg, chosen)
        if found is None:
            found = _text_slide(
                out_dir / f"beat_{i:02d}.mp4",
                cfg.width,
                cfg.height,
                max(dur, 2.0),
                search_q,
                i,
            )
            staged = found
        else:
            staged = _stage_media(found, out_dir / f"beat_{i:02d}{found.suffix.lower()}")
        paths.append(staged)
        print(
            f"  beat {i+1}: search={search_q!r} source={source} "
            f"size={staged.stat().st_size}"
        )
        manifest_items.append(
            {
                "query": query,
                "search_query": search_q,
                "path": str(staged),
                "provider": chosen,
                "source": source,
            }
        )

    (run_dir / "broll.json").write_text(
        json.dumps(
            {"provider": chosen, "items": manifest_items},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return paths
