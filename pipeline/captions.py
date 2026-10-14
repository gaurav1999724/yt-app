"""Build SRT / ASS captions from word timings."""

from __future__ import annotations

from pathlib import Path

from pipeline.fonts import ass_font_name
from pipeline.tts import WordTiming


def _ts_srt(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def _ts_ass(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    cs = int(round(seconds * 100))
    h, rem = divmod(cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def words_to_cues(words: list[WordTiming], max_words: int = 4) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    if not words:
        return cues
    buf: list[WordTiming] = []
    for w in words:
        buf.append(w)
        if len(buf) >= max_words or w.word.endswith((".", "!", "?", "।", "॥")):
            text = " ".join(x.word for x in buf).strip()
            cues.append((buf[0].start, buf[-1].end, text))
            buf = []
    if buf:
        text = " ".join(x.word for x in buf).strip()
        cues.append((buf[0].start, buf[-1].end, text))
    return cues


def write_srt(words: list[WordTiming], path: Path, max_words: int = 4) -> Path:
    cues = words_to_cues(words, max_words=max_words)
    lines: list[str] = []
    for i, (start, end, text) in enumerate(cues, 1):
        lines.append(str(i))
        lines.append(f"{_ts_srt(start)} --> {_ts_srt(end)}")
        lines.append(text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_ass(
    words: list[WordTiming],
    path: Path,
    width: int,
    height: int,
    max_words: int = 4,
) -> Path:
    cues = words_to_cues(words, max_words=max_words)
    fontsize = 72 if height > width else 54
    margin_v = int(height * 0.12)
    fontname = ass_font_name()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for start, end, text in cues:
        safe = text.replace("{", "(").replace("}", ")")
        events.append(
            f"Dialogue: 0,{_ts_ass(start)},{_ts_ass(end)},Default,,0,0,0,,{safe}"
        )
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path
