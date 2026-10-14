"""Thin wrappers around pipeline stages for the UI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.config import Config, load_config
from pipeline.jsonutil import load_json_file, parse_json_text
from pipeline.run import cmd_approve, cmd_init, cmd_render, cmd_upload
from pipeline.status import read_status


def cfg() -> Config:
    return load_config()


def list_runs() -> list[dict]:
    root = cfg().output_dir
    if not root.exists():
        return []
    runs = []
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or path.name.startswith("."):
            continue
        idea = load_json_file(path / "idea.json", {})
        if not isinstance(idea, dict):
            idea = {}
        runs.append(
            {
                "id": path.name,
                "path": str(path),
                "status": read_status(path) or "DRAFT",
                "idea": idea.get("idea") or path.name,
                "has_video": (path / "video.mp4").exists(),
                "has_thumb": (path / "thumb.png").exists(),
            }
        )
    return runs


def run_dir(run_id: str) -> Path:
    path = (cfg().output_dir / run_id).resolve()
    root = cfg().output_dir.resolve()
    if not str(path).startswith(str(root)) or not path.is_dir():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return path


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_package(idea: str) -> dict:
    return {
        "title": (idea or "नई वीडियो")[:70],
        "thumbnail_text": "नई वीडियो",
        "thumbnail_brief": "हाई कंट्रास्ट हिंदी टेक्स्ट",
    }


def _default_seo(idea: str) -> dict:
    return {
        "title": (idea or "नई वीडियो")[:70],
        "description": f"{idea}\n\n#Shorts #हिंदी",
        "tags": [],
        "category_id": "22",
    }


def load_run(run_id: str) -> dict:
    path = run_dir(run_id)
    package_raw = read_text_file(path / "package.json")
    seo_raw = read_text_file(path / "seo.json")
    idea = load_json_file(path / "idea.json", {})
    if not isinstance(idea, dict):
        idea = {}

    package = load_json_file(path / "package.json", {})
    seo = load_json_file(path / "seo.json", {})
    if not isinstance(package, dict):
        package = {}
    if not isinstance(seo, dict):
        seo = {}

    # If files were wiped empty, show usable defaults in the editor
    idea_text = idea.get("idea") or run_id
    if not package_raw.strip():
        package = _default_package(idea_text)
        package_raw = json.dumps(package, indent=2, ensure_ascii=False)
    if not seo_raw.strip():
        seo = _default_seo(idea_text)
        seo_raw = json.dumps(seo, indent=2, ensure_ascii=False)

    return {
        "id": run_id,
        "path": str(path),
        "status": read_status(path) or "DRAFT",
        "idea": idea,
        "script": read_text_file(path / "script.md"),
        "package_raw": package_raw,
        "seo_raw": seo_raw,
        "package": package,
        "seo": seo,
        "upload": load_json_file(path / "upload.json", {}),
        "video_meta": load_json_file(path / "video.meta.json", {}),
        "has_video": (path / "video.mp4").exists(),
        "has_thumb": (path / "thumb.png").exists(),
        "has_audio": (path / "audio.mp3").exists(),
    }


def create_run(
    idea: str,
    script: str = "",
    package_json: str = "",
    seo_json: str = "",
) -> str:
    config = cfg()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    idea_text = idea.strip() or "नई वीडियो आईडिया"
    ns = argparse.Namespace(
        idea=idea_text,
        from_dir=None,
        script_file=None,
        script_text=script.strip() or None,
        package_json=None,
        seo_json=None,
    )
    from pipeline.run import _new_run_dir

    path = _new_run_dir(config, ns.idea)
    ns.from_dir = str(path)
    rc = cmd_init(ns, config)
    if rc != 0:
        raise RuntimeError("init failed")
    if script.strip():
        write_text_file(path / "script.md", script)

    # Invalid / empty optional JSON → defaults (UI should never hard-fail here)
    pkg = parse_json_text(package_json, field="package.json", strict=False)
    if not pkg:
        pkg = _default_package(idea_text)
    write_text_file(
        path / "package.json",
        json.dumps(pkg, indent=2, ensure_ascii=False),
    )

    seo = parse_json_text(seo_json, field="seo.json", strict=False)
    if not seo:
        seo = _default_seo(idea_text)
    write_text_file(
        path / "seo.json",
        json.dumps(seo, indent=2, ensure_ascii=False),
    )
    return path.name


def save_run_files(run_id: str, script: str, package_json: str, seo_json: str) -> None:
    path = run_dir(run_id)
    idea = load_json_file(path / "idea.json", {})
    idea_text = idea.get("idea") if isinstance(idea, dict) else run_id
    idea_text = idea_text or run_id

    pkg = parse_json_text(package_json, field="package.json", strict=False)
    if not pkg:
        pkg = _default_package(str(idea_text))

    seo = parse_json_text(seo_json, field="seo.json", strict=False)
    if not seo:
        seo = _default_seo(str(idea_text))

    write_text_file(path / "script.md", script or "")
    write_text_file(
        path / "package.json",
        json.dumps(pkg, indent=2, ensure_ascii=False),
    )
    write_text_file(
        path / "seo.json",
        json.dumps(seo, indent=2, ensure_ascii=False),
    )


def action_render(run_id: str) -> dict:
    path = run_dir(run_id)
    # Ensure JSON files are never empty before render
    save_run_files(
        run_id,
        read_text_file(path / "script.md"),
        read_text_file(path / "package.json"),
        read_text_file(path / "seo.json"),
    )
    ns = argparse.Namespace(from_dir=str(path), idea=None)
    rc = cmd_render(ns, cfg())
    status = read_status(path)
    note = ""
    status_path = path / "STATUS"
    if status_path.exists():
        lines = status_path.read_text(encoding="utf-8").splitlines()
        if len(lines) >= 3:
            note = lines[2]
    result = {"ok": rc == 0, "status": status, "run_id": run_id}
    if rc != 0:
        result["error"] = note or "Render failed"
    return result


def action_approve(run_id: str) -> dict:
    path = run_dir(run_id)
    ns = argparse.Namespace(from_dir=str(path), idea=None)
    rc = cmd_approve(ns, cfg())
    return {"ok": rc == 0, "status": read_status(path), "run_id": run_id}


def action_upload(run_id: str, privacy: str | None = None) -> dict:
    path = run_dir(run_id)
    ns = argparse.Namespace(from_dir=str(path), idea=None, privacy=privacy)
    rc = cmd_upload(ns, cfg())
    upload = load_json_file(path / "upload.json", {})
    if not isinstance(upload, dict):
        upload = {}
    return {
        "ok": rc == 0,
        "status": read_status(path),
        "run_id": run_id,
        "upload": upload,
    }


def config_summary() -> dict:
    c = cfg()
    return {
        "language": c.language,
        "tts_voice": c.tts_voice,
        "video_format": c.video_format,
        "upload_privacy": c.upload_privacy,
        "output_dir": str(c.output_dir),
        "unsplash_configured": bool(c.unsplash_access_key),
        "youtube_secrets_present": c.youtube_client_secrets.exists(),
        "youtube_token_present": c.youtube_token_path.exists(),
    }
