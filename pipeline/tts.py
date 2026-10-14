"""Text-to-speech via edge-tts with caption timings.

edge-tts 7.x emits SentenceBoundary (not WordBoundary). We expand each
sentence into approximate per-word timings for burned captions.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import edge_tts


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class TtsResult:
    audio_path: Path
    duration: float
    words: list[WordTiming]


def _probe_audio_duration(path: Path) -> float:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        out = subprocess.check_output(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            text=True,
        ).strip()
        return float(out)
    except (subprocess.CalledProcessError, ValueError):
        return 0.0


def _expand_sentence(text: str, start: float, end: float) -> list[WordTiming]:
    tokens = [t for t in text.split() if t.strip()]
    if not tokens:
        return []
    span = max(end - start, 0.05)
    slot = span / len(tokens)
    words: list[WordTiming] = []
    for i, token in enumerate(tokens):
        w_start = start + i * slot
        w_end = start + (i + 1) * slot
        words.append(WordTiming(word=token, start=w_start, end=w_end))
    return words


def _estimate_words(text: str, duration: float) -> list[WordTiming]:
    tokens = [t for t in text.split() if t.strip()]
    if not tokens:
        return []
    duration = max(duration, 0.5)
    slot = duration / len(tokens)
    return [
        WordTiming(word=tok, start=i * slot, end=(i + 1) * slot)
        for i, tok in enumerate(tokens)
    ]


async def _synthesize(text: str, voice: str, audio_path: Path) -> TtsResult:
    communicate = edge_tts.Communicate(text, voice)
    words: list[WordTiming] = []
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            kind = chunk["type"]
            if kind == "audio":
                audio_file.write(chunk["data"])
            elif kind == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                end = (chunk["offset"] + chunk["duration"]) / 10_000_000
                words.append(WordTiming(word=chunk["text"], start=start, end=end))
            elif kind == "SentenceBoundary":
                start = chunk["offset"] / 10_000_000
                end = (chunk["offset"] + chunk["duration"]) / 10_000_000
                words.extend(_expand_sentence(chunk.get("text") or "", start, end))

    duration = _probe_audio_duration(audio_path)
    if duration <= 0:
        duration = words[-1].end if words else max(1.0, len(text.split()) / 2.5)
    if not words:
        words = _estimate_words(text, duration)

    return TtsResult(audio_path=audio_path, duration=duration, words=words)


def _run_coro(coro):
    """asyncio.run() fails inside FastAPI's event loop — use a fresh thread then."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def synthesize(text: str, voice: str, audio_path: Path) -> TtsResult:
    result = _run_coro(_synthesize(text, voice, audio_path))
    timings_path = audio_path.with_suffix(".words.json")
    timings_path.write_text(
        json.dumps([asdict(w) for w in result.words], indent=2),
        encoding="utf-8",
    )
    meta = {
        "duration": result.duration,
        "voice": voice,
        "words_file": str(timings_path.name),
        "word_count": len(result.words),
    }
    audio_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    return result
