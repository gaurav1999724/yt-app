"""Compose final MP4 with FFmpeg: B-roll + voice + burned captions."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from pipeline.captions import write_ass, write_srt
from pipeline.config import Config
from pipeline.tts import TtsResult


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "ffmpeg not found on PATH. Install FFmpeg and restart the shell."
        )
    return ffmpeg


def _probe_duration(path: Path) -> float:
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


def _make_segment(
    ffmpeg: str,
    media: Path,
    duration: float,
    width: int,
    height: int,
    out: Path,
) -> None:
    """Scale/crop media to exact size and duration."""
    is_image = media.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps=30,format=yuv420p"
    )
    if is_image:
        cmd = [
            ffmpeg,
            "-y",
            "-loop",
            "1",
            "-i",
            str(media),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    else:
        cmd = [
            ffmpeg,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(media),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out),
        ]
    subprocess.run(cmd, check=True, capture_output=True)


def compose_video(
    run_dir: Path,
    cfg: Config,
    tts: TtsResult,
    broll_paths: list[Path],
    beat_spoken: list[str],
) -> Path:
    ffmpeg = _require_ffmpeg()
    width, height = cfg.width, cfg.height
    total = tts.duration
    if total <= 0:
        total = _probe_duration(tts.audio_path) or 5.0

    n = max(len(broll_paths), 1)
    # Allocate time proportional to spoken word counts
    weights = [max(len(s.split()), 1) for s in beat_spoken] or [1]
    if len(weights) < n:
        weights += [1] * (n - len(weights))
    weights = weights[:n]
    wsum = sum(weights)
    durations = [total * (w / wsum) for w in weights]
    # Fix float drift
    durations[-1] += total - sum(durations)

    work = Path(tempfile.mkdtemp(prefix="ytcompose_"))
    try:
        segment_files: list[Path] = []
        for i, media in enumerate(broll_paths[:n]):
            seg = work / f"seg_{i:02d}.mp4"
            _make_segment(ffmpeg, media, durations[i], width, height, seg)
            segment_files.append(seg)

        concat_list = work / "concat.txt"
        concat_list.write_text(
            "\n".join(f"file '{p.as_posix()}'" for p in segment_files) + "\n",
            encoding="utf-8",
        )
        silent_video = work / "video_silent.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_list),
                "-c",
                "copy",
                str(silent_video),
            ],
            check=True,
            capture_output=True,
        )

        srt_path = run_dir / "captions.srt"
        ass_path = run_dir / "captions.ass"
        write_srt(tts.words, srt_path)
        write_ass(tts.words, ass_path, width, height)
        # Copy into work dir so ffmpeg can use a simple relative path (Windows-safe)
        work_ass = work / "captions.ass"
        work_ass.write_text(ass_path.read_text(encoding="utf-8"), encoding="utf-8")

        out_path = run_dir / "video.mp4"
        base_cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(tts.audio_path),
        ]
        encode_tail = [
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
        burned = False
        if tts.words:
            for vf in ("ass=captions.ass", "subtitles=captions.ass"):
                result = subprocess.run(
                    base_cmd + ["-vf", vf] + encode_tail,
                    capture_output=True,
                    cwd=str(work),
                )
                if result.returncode == 0:
                    burned = True
                    break
        if not burned:
            subprocess.run(base_cmd + encode_tail, check=True, capture_output=True)

        meta = {
            "path": str(out_path),
            "duration": total,
            "width": width,
            "height": height,
            "format": cfg.video_format,
            "segments": len(segment_files),
        }
        (run_dir / "video.meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        return out_path
    finally:
        shutil.rmtree(work, ignore_errors=True)
