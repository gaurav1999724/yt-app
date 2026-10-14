"""Parse yt-script style markdown into spoken text and on-screen beats."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


ON_SCREEN_RE = re.compile(r"\[ON SCREEN:\s*(.+?)\]", re.IGNORECASE)


@dataclass
class Beat:
    spoken: str
    on_screen: str


@dataclass
class ParsedScript:
    full_spoken: str
    beats: list[Beat]


def _strip_markup(text: str) -> str:
    text = ON_SCREEN_RE.sub("", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-*]\s+", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_script_text(raw: str) -> ParsedScript:
    """Attach each [ON SCREEN: ...] cue to the following spoken paragraph."""
    lines = raw.splitlines()
    pending_onscreen: str | None = None
    beats: list[Beat] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal pending_onscreen, buf
        spoken = _strip_markup("\n".join(buf))
        buf = []
        if not spoken:
            return
        on_screen = pending_onscreen or _fallback_query(spoken)
        pending_onscreen = None
        beats.append(Beat(spoken=spoken, on_screen=on_screen))

    for line in lines:
        ons = ON_SCREEN_RE.findall(line)
        if ons:
            # Flush any spoken text before this cue
            if any(x.strip() for x in buf):
                flush()
            pending_onscreen = ons[-1].strip()
            # Keep any non-marker text on the same line
            remainder = ON_SCREEN_RE.sub("", line).strip()
            if remainder:
                buf.append(remainder)
            continue
        if not line.strip():
            if any(x.strip() for x in buf):
                flush()
            continue
        # Skip lone title headings without speech value unless nothing else yet
        if re.match(r"^#+\s+", line) and not buf:
            continue
        buf.append(line)

    if any(x.strip() for x in buf):
        flush()

    if not beats:
        spoken = _strip_markup(raw)
        beats = [Beat(spoken=spoken, on_screen=_fallback_query(spoken))]

    full = " ".join(b.spoken for b in beats)
    full = re.sub(r"\s+", " ", full).strip()
    return ParsedScript(full_spoken=full, beats=beats)


def parse_script_file(path: Path) -> ParsedScript:
    return parse_script_text(path.read_text(encoding="utf-8"))


def _fallback_query(spoken: str) -> str:
    # Latin or Devanagari tokens for Unsplash search / slide labels
    words = re.findall(r"[A-Za-z]{4,}|[\u0900-\u097F]{2,}", spoken)
    return " ".join(words[:4]) if words else "technology abstract"
