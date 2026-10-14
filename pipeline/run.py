"""CLI for the faceless YouTube pipeline.

Stages:
  init     create a run folder from an idea
  render   TTS + B-roll + captions + thumb -> READY_FOR_REVIEW
  approve  mark STATUS=APPROVED (ship it)
  upload   YouTube upload (requires APPROVED)
  status   print STATUS
  all-render  init (if needed) + render
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pipeline.broll import resolve_broll
from pipeline.compose import compose_video
from pipeline.config import Config, load_config
from pipeline.script_parse import parse_script_file
from pipeline.status import (
    APPROVED,
    DRAFT,
    READY,
    RENDERING,
    approve,
    read_status,
    write_status,
)
from pipeline.thumb import render_from_package, render_thumbnail
from pipeline.tts import synthesize
from pipeline.upload import upload_run


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (s or "run")[:n]


def _new_run_dir(cfg: Config, idea: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{_slug(idea)}-{uuid.uuid4().hex[:6]}"
    run_dir = cfg.output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def cmd_init(args: argparse.Namespace, cfg: Config) -> int:
    idea = args.idea or "नई वीडियो आईडिया"
    run_dir = Path(args.from_dir) if args.from_dir else _new_run_dir(cfg, idea)
    run_dir.mkdir(parents=True, exist_ok=True)

    idea_path = run_dir / "idea.json"
    if not idea_path.exists():
        idea_path.write_text(
            json.dumps(
                {
                    "idea": idea,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "format": cfg.video_format,
                    "language": cfg.language,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    if args.script_file:
        text = Path(args.script_file).read_text(encoding="utf-8")
        (run_dir / "script.md").write_text(text, encoding="utf-8")
    elif args.script_text:
        (run_dir / "script.md").write_text(args.script_text, encoding="utf-8")
    elif not (run_dir / "script.md").exists():
        # Minimal placeholder the agent/skills should replace
        (run_dir / "script.md").write_text(
            f"# स्क्रिप्ट\n\n{idea}\n\n"
            f"[ON SCREEN: {idea}]\n\n"
            "इस वीडियो का असली पॉइंट साफ शब्दों में ये है।\n",
            encoding="utf-8",
        )

    if args.package_json:
        (run_dir / "package.json").write_text(
            Path(args.package_json).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    elif not (run_dir / "package.json").exists():
        words = re.findall(r"[A-Za-z0-9]{3,}|[\u0900-\u097F]{2,}", idea)[:3]
        if words and all(ord(ch) < 128 for ch in "".join(words)):
            thumb = " ".join(words).upper()
        else:
            thumb = " ".join(words) if words else "नई वीडियो"
        (run_dir / "package.json").write_text(
            json.dumps(
                {
                    "title": idea[:70],
                    "thumbnail_text": thumb,
                    "thumbnail_brief": f"हाई कंट्रास्ट टेक्स्ट: {thumb}",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    if args.seo_json:
        (run_dir / "seo.json").write_text(
            Path(args.seo_json).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    elif not (run_dir / "seo.json").exists():
        (run_dir / "seo.json").write_text(
            json.dumps(
                {
                    "title": idea[:70],
                    "description": f"{idea}\n\n#Shorts #हिंदी"
                    if cfg.video_format == "shorts"
                    else idea,
                    "tags": [],
                    "category_id": "22",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    write_status(run_dir, DRAFT)
    print(str(run_dir))
    return 0


def cmd_render(args: argparse.Namespace, cfg: Config) -> int:
    if not args.from_dir:
        print("--from-dir is required for render", file=sys.stderr)
        return 2
    run_dir = Path(args.from_dir)
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 1

    write_status(run_dir, RENDERING)
    try:
        script_path = run_dir / "script.md"
        if not script_path.exists():
            raise FileNotFoundError("script.md missing — run init or write a script first")

        parsed = parse_script_file(script_path)
        audio_path = run_dir / "audio.mp3"
        print(f"TTS ({cfg.tts_voice})...")
        tts = synthesize(parsed.full_spoken, cfg.tts_voice, audio_path)
        print(f"Audio duration: {tts.duration:.1f}s")

        queries = [b.on_screen for b in parsed.beats]
        spoken_parts = [b.spoken for b in parsed.beats]
        weights = [max(len(s.split()), 1) for s in spoken_parts]
        wsum = sum(weights) or 1
        beat_durs = [tts.duration * (w / wsum) for w in weights]

        print("Fetching B-roll...")
        broll_paths = resolve_broll(queries, cfg, run_dir, beat_durs)

        print("Composing video...")
        video_path = compose_video(run_dir, cfg, tts, broll_paths, spoken_parts)
        print(f"Video: {video_path}")

        print("Rendering thumbnail...")
        thumb_path = render_from_package(run_dir, cfg)
        print(f"Thumb: {thumb_path}")

        write_status(run_dir, READY, note="preview video.mp4 and thumb.png")
        print("STATUS=READY_FOR_REVIEW")
        print("ship it, or change it?")
        return 0
    except Exception as exc:  # noqa: BLE001
        write_status(run_dir, "FAILED", note=str(exc))
        print(f"Render failed: {exc}", file=sys.stderr)
        return 1


def cmd_approve(args: argparse.Namespace, cfg: Config) -> int:
    if not args.from_dir:
        print("--from-dir is required", file=sys.stderr)
        return 2
    run_dir = Path(args.from_dir)
    current = read_status(run_dir)
    if current not in (READY, APPROVED):
        print(
            f"Cannot approve from STATUS={current or '(empty)'}. "
            "Render until READY_FOR_REVIEW first.",
            file=sys.stderr,
        )
        return 1
    approve(run_dir)
    print(f"STATUS=APPROVED ({run_dir})")
    return 0


def cmd_upload(args: argparse.Namespace, cfg: Config) -> int:
    if not args.from_dir:
        print("--from-dir is required", file=sys.stderr)
        return 2
    run_dir = Path(args.from_dir)
    try:
        result = upload_run(run_dir, cfg, privacy=args.privacy)
    except PermissionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def cmd_status(args: argparse.Namespace, cfg: Config) -> int:
    if not args.from_dir:
        print("--from-dir is required", file=sys.stderr)
        return 2
    run_dir = Path(args.from_dir)
    print(read_status(run_dir) or "(no STATUS)")
    return 0


def cmd_thumb_only(args: argparse.Namespace, cfg: Config) -> int:
    if not args.from_dir:
        print("--from-dir is required", file=sys.stderr)
        return 2
    run_dir = Path(args.from_dir)
    path = render_from_package(run_dir, cfg)
    if args.thumb_text:
        path = render_thumbnail(run_dir, cfg, args.thumb_text)
    print(path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Faceless YouTube pipeline (approve-then-upload)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--from-dir", help="Existing run directory")
        sp.add_argument("--idea", help="Idea / working title for a new run")

    sp = sub.add_parser("init", help="Create run folder + seed files")
    add_common(sp)
    sp.add_argument("--script-file", help="Copy this file to script.md")
    sp.add_argument("--script-text", help="Write this string to script.md")
    sp.add_argument("--package-json", help="Copy to package.json")
    sp.add_argument("--seo-json", help="Copy to seo.json")

    sp = sub.add_parser("render", help="Render audio/video/thumb -> READY_FOR_REVIEW")
    add_common(sp)

    sp = sub.add_parser("approve", help="Mark run APPROVED (ship it)")
    add_common(sp)

    sp = sub.add_parser("upload", help="Upload APPROVED run to YouTube")
    add_common(sp)
    sp.add_argument(
        "--privacy",
        choices=["private", "unlisted", "public"],
        help="Override UPLOAD_PRIVACY",
    )

    sp = sub.add_parser("status", help="Print STATUS")
    add_common(sp)

    sp = sub.add_parser("thumb", help="Re-render thumbnail only")
    add_common(sp)
    sp.add_argument("--thumb-text", help="Override thumbnail text")

    sp = sub.add_parser(
        "all-render",
        help="init (if needed) + render; stops at READY_FOR_REVIEW",
    )
    add_common(sp)
    sp.add_argument("--script-file")
    sp.add_argument("--script-text")
    sp.add_argument("--package-json")
    sp.add_argument("--seo-json")

    return p


def main(argv: list[str] | None = None) -> int:
    # Allow `python -m pipeline.run` and `python -m pipeline`
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config()
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        return cmd_init(args, cfg)
    if args.command == "render":
        return cmd_render(args, cfg)
    if args.command == "approve":
        return cmd_approve(args, cfg)
    if args.command == "upload":
        return cmd_upload(args, cfg)
    if args.command == "status":
        return cmd_status(args, cfg)
    if args.command == "thumb":
        return cmd_thumb_only(args, cfg)
    if args.command == "all-render":
        if not args.from_dir:
            idea = args.idea or "नई वीडियो आईडिया"
            args.from_dir = str(_new_run_dir(cfg, idea))
        rc = cmd_init(args, cfg)
        if rc != 0:
            return rc
        return cmd_render(args, cfg)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
