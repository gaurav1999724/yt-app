"""Fetch B-roll photos from Unsplash (with visible text-slide fallback)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from pipeline.config import Config
from pipeline.fonts import load_font

# Distinct fallback palettes so beats are obviously different without Unsplash
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
    """Bright slide with on-screen label — never a blank black frame."""
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


def search_unsplash_photo(query: str, cfg: Config) -> Path | None:
    if not cfg.unsplash_access_key:
        return None
    cache_dir = cfg.cache_dir / "unsplash"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(query + "|" + cfg.video_format)
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
                "query": query,
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

    # Unsplash guidelines: trigger download endpoint when using a photo
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
                "path": str(dest),
                "type": "image",
                "unsplash_id": results[0].get("id"),
                "photographer": (results[0].get("user") or {}).get("name"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return dest


def resolve_broll(
    queries: list[str],
    cfg: Config,
    run_dir: Path,
    beat_durations: list[float],
) -> list[Path]:
    """Return one media path per beat."""
    out_dir = run_dir / "broll"
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, query in enumerate(queries):
        dur = beat_durations[i] if i < len(beat_durations) else 3.0
        found = search_unsplash_photo(query, cfg)
        if found is None:
            found = _text_slide(
                out_dir / f"beat_{i:02d}.mp4",
                cfg.width,
                cfg.height,
                max(dur, 2.0),
                query,
                i,
            )
        paths.append(found)
    manifest = [{"query": q, "path": str(p)} for q, p in zip(queries, paths)]
    (run_dir / "broll.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return paths
