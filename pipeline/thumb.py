"""Render a high-contrast YouTube thumbnail from package brief."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from pipeline.config import Config
from pipeline.fonts import load_font


def _hex_rgb(value: str) -> tuple[int, int, int]:
    h = value.lstrip("#")
    if len(h) != 6:
        return (11, 18, 32)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
) -> tuple[ImageFont.ImageFont | ImageFont.FreeTypeFont, str]:
    raw = (text or "").strip()
    # Latin titles stay loud; Hindi/Devanagari keep original casing
    if raw and all(ord(ch) < 128 for ch in raw):
        raw = raw.upper()
    words = raw.split()
    # Enforce 3-word max for feed readability
    words = words[:3]
    line = " ".join(words) if words else "नई वीडियो"
    size = start_size
    while size >= 36:
        font = load_font(size)
        bbox = draw.textbbox((0, 0), line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font, line
        size -= 4
    return load_font(36), line


def render_thumbnail(
    run_dir: Path,
    cfg: Config,
    thumb_text: str,
    title: str = "",
) -> Path:
    # YouTube recommended custom thumbnail size
    width, height = 1280, 720
    bg = _hex_rgb(cfg.thumb_bg)
    fg = _hex_rgb(cfg.thumb_fg)
    accent = _hex_rgb(cfg.thumb_accent)

    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # Atmospheric blocks (not flat single color)
    draw.rectangle([0, 0, width // 2, height], fill=tuple(max(0, c - 10) for c in bg))
    draw.polygon(
        [(width * 0.45, 0), (width, 0), (width, height), (width * 0.55, height)],
        fill=tuple(min(255, c + 18) for c in bg),
    )
    draw.rectangle([0, height - 18, width, height], fill=accent)
    draw.rectangle([48, 48, 56, height - 48], fill=accent)

    font, line = _fit_text(draw, thumb_text or "नई वीडियो", width - 160, start_size=120)
    bbox = draw.textbbox((0, 0), line, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - tw) // 2
    y = (height - th) // 2 - 20
    # Shadow
    draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
    draw.text((x, y), line, font=font, fill=fg)

    out = run_dir / "thumb.png"
    img.save(out, format="PNG", optimize=True)

    # Feed-size sanity check copy
    feed = img.resize((320, 180), Image.Resampling.LANCZOS)
    feed.save(run_dir / "thumb.feed.png", format="PNG")

    meta = {
        "path": str(out),
        "text": line,
        "title": title,
        "size": [width, height],
    }
    (run_dir / "thumb.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out


def render_from_package(run_dir: Path, cfg: Config) -> Path:
    from pipeline.jsonutil import load_json_file

    package_path = run_dir / "package.json"
    thumb_text = "नई वीडियो"
    title = ""
    data = load_json_file(package_path, {})
    if isinstance(data, dict) and data:
        thumb_text = (
            data.get("thumbnail_text")
            or data.get("thumb")
            or data.get("thumbnail")
            or thumb_text
        )
        title = data.get("title") or ""
    return render_thumbnail(run_dir, cfg, str(thumb_text), title=title)
