"""Text-to-speech via edge-tts with natural Hindi pacing.

edge-tts 7.x emits SentenceBoundary (not WordBoundary). We expand each
sentence into approximate per-word timings for burned captions.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

import edge_tts

from pipeline.hindi_speech import prepare_spoken_text, split_spoken_chunks


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


async def _synthesize_chunk(
    text: str,
    voice: str,
    audio_path: Path,
    *,
    rate: str,
    pitch: str,
) -> TtsResult:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
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


def _make_silence(path: Path, seconds: float = 0.22) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        path.write_bytes(b"")
        return path
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            f"{seconds:.3f}",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _concat_audio(parts: list[Path], out_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        # Fallback: raw concat of mp3 bytes (imperfect but better than nothing)
        with open(out_path, "wb") as out:
            for p in parts:
                out.write(p.read_bytes())
        return
    work = out_path.parent
    lst = work / "concat_audio.txt"
    lst.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts) + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


async def _synthesize(
    text: str,
    voice: str,
    audio_path: Path,
    *,
    rate: str,
    pitch: str,
    language: str,
) -> TtsResult:
    spoken = prepare_spoken_text(text, language=language)
    chunks = split_spoken_chunks(spoken, max_chars=120)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    # Single short line — one shot
    if len(chunks) <= 1:
        return await _synthesize_chunk(
            spoken, voice, audio_path, rate=rate, pitch=pitch
        )

    work = Path(tempfile.mkdtemp(prefix="yttts_"))
    try:
        silence = _make_silence(work / "silence.mp3", 0.20)
        media_parts: list[Path] = []
        all_words: list[WordTiming] = []
        cursor = 0.0
        for i, chunk in enumerate(chunks):
            part_path = work / f"part_{i:02d}.mp3"
            result = await _synthesize_chunk(
                chunk, voice, part_path, rate=rate, pitch=pitch
            )
            for w in result.words:
                all_words.append(
                    WordTiming(word=w.word, start=w.start + cursor, end=w.end + cursor)
                )
            media_parts.append(part_path)
            cursor += result.duration
            if i < len(chunks) - 1:
                media_parts.append(silence)
                cursor += 0.20
        _concat_audio(media_parts, audio_path)
        duration = _probe_audio_duration(audio_path) or cursor
        if not all_words:
            all_words = _estimate_words(spoken, duration)
        return TtsResult(audio_path=audio_path, duration=duration, words=all_words)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _run_coro(coro):
    """asyncio.run() fails inside FastAPI's event loop — use a fresh thread then."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def synthesize(
    text: str,
    voice: str,
    audio_path: Path,
    *,
    rate: str = "-12%",
    pitch: str = "-2Hz",
    language: str = "hi",
) -> TtsResult:
    result = _run_coro(
        _synthesize(
            text,
            voice,
            audio_path,
            rate=rate,
            pitch=pitch,
            language=language,
        )
    )
    timings_path = audio_path.with_suffix(".words.json")
    timings_path.write_text(
        json.dumps([asdict(w) for w in result.words], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    meta = {
        "duration": result.duration,
        "voice": voice,
        "rate": rate,
        "pitch": pitch,
        "language": language,
        "words_file": str(timings_path.name),
        "word_count": len(result.words),
        "prepared_preview": prepare_spoken_text(text, language=language)[:240],
    }
    audio_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result
