"""Load pipeline configuration from environment / .env files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
PIPELINE_DIR = Path(__file__).resolve().parent

# Prefer project .env, then pipeline/.env
load_dotenv(ROOT / ".env")
load_dotenv(PIPELINE_DIR / ".env")


def _path(value: str | None, default: Path) -> Path:
    if not value:
        return default
    p = Path(value)
    return p if p.is_absolute() else ROOT / p


@dataclass(frozen=True)
class Config:
    unsplash_access_key: str
    youtube_client_secrets: Path
    youtube_token_path: Path
    tts_voice: str
    language: str
    output_dir: Path
    cache_dir: Path
    video_format: str  # shorts | long
    upload_privacy: str
    thumb_bg: str
    thumb_fg: str
    thumb_accent: str

    @property
    def width(self) -> int:
        return 1080 if self.video_format == "shorts" else 1920

    @property
    def height(self) -> int:
        return 1920 if self.video_format == "shorts" else 1080


def load_config() -> Config:
    fmt = os.getenv("VIDEO_FORMAT", "shorts").strip().lower()
    if fmt not in ("shorts", "long"):
        fmt = "shorts"
    privacy = os.getenv("UPLOAD_PRIVACY", "private").strip().lower()
    if privacy not in ("private", "unlisted", "public"):
        privacy = "private"
    language = os.getenv("LANGUAGE", "hi").strip().lower() or "hi"
    default_voice = (
        "hi-IN-MadhurNeural" if language.startswith("hi") else "en-US-GuyNeural"
    )
    return Config(
        unsplash_access_key=os.getenv("UNSPLASH_ACCESS_KEY", "").strip(),
        youtube_client_secrets=_path(
            os.getenv("YOUTUBE_CLIENT_SECRETS"),
            PIPELINE_DIR / "client_secrets.json",
        ),
        youtube_token_path=_path(
            os.getenv("YOUTUBE_TOKEN_PATH"),
            PIPELINE_DIR / "token.json",
        ),
        tts_voice=os.getenv("TTS_VOICE", default_voice).strip() or default_voice,
        language=language,
        output_dir=_path(os.getenv("OUTPUT_DIR"), ROOT / "workspace" / "runs"),
        cache_dir=_path(os.getenv("CACHE_DIR"), ROOT / "workspace" / "cache"),
        video_format=fmt,
        upload_privacy=privacy,
        thumb_bg=os.getenv("THUMB_BG", "#0B1220").strip(),
        thumb_fg=os.getenv("THUMB_FG", "#F5F7FA").strip(),
        thumb_accent=os.getenv("THUMB_ACCENT", "#F5C542").strip(),
    )
