"""Shared font loading with Hindi (Devanagari) support."""

from __future__ import annotations

from pathlib import Path

from PIL import ImageFont

PIPELINE_DIR = Path(__file__).resolve().parent
BUNDLED_FONT = PIPELINE_DIR / "assets" / "fonts" / "NotoSansDevanagari-Bold.ttf"
BUNDLED_FONT_DIR = PIPELINE_DIR / "assets" / "fonts"

# Prefer bundled Noto first (works on Render + Windows even without system Hindi fonts)
_FONT_CANDIDATES = [
    str(BUNDLED_FONT),
    "C:/Windows/Fonts/Nirmala.ttf",
    "C:/Windows/Fonts/nirmala.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",
    "C:/Windows/Fonts/mangal.ttf",
    "C:/Windows/Fonts/Mangal.ttf",
    "C:/Windows/Fonts/arialuni.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def load_font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def ass_font_name() -> str:
    """Font family name for ASS captions (must match an installed / fontsdir face)."""
    if BUNDLED_FONT.exists():
        return "Noto Sans Devanagari"
    if Path("C:/Windows/Fonts/Nirmala.ttf").exists() or Path(
        "C:/Windows/Fonts/nirmala.ttf"
    ).exists():
        return "Nirmala UI"
    if Path("C:/Windows/Fonts/mangal.ttf").exists() or Path(
        "C:/Windows/Fonts/Mangal.ttf"
    ).exists():
        return "Mangal"
    return "Arial"


def ass_fonts_dir() -> Path | None:
    """Directory to pass to ffmpeg subtitles filter as fontsdir=."""
    if BUNDLED_FONT_DIR.exists():
        return BUNDLED_FONT_DIR
    return None
