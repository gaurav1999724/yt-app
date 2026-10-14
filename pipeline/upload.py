"""Upload a reviewed run to YouTube. Requires STATUS=APPROVED."""

from __future__ import annotations

import json
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from pipeline.config import Config, load_config
from pipeline.status import UPLOADED, is_approved, write_status
from pipeline.youtube_auth import youtube_service


def _load_json(path: Path) -> dict:
    from pipeline.jsonutil import load_json_file

    data = load_json_file(path, {})
    return data if isinstance(data, dict) else {}


def upload_run(run_dir: Path, cfg: Config | None = None, privacy: str | None = None) -> dict:
    cfg = cfg or load_config()
    run_dir = Path(run_dir)

    if not is_approved(run_dir):
        raise PermissionError(
            f"Upload refused: STATUS is not APPROVED in {run_dir / 'STATUS'}. "
            "Ship it first (python -m pipeline approve --from-dir ...)."
        )

    video_path = run_dir / "video.mp4"
    if not video_path.exists():
        raise FileNotFoundError(f"Missing video.mp4 in {run_dir}")

    package = _load_json(run_dir / "package.json")
    seo = _load_json(run_dir / "seo.json")

    title = (package.get("title") or seo.get("title") or "Untitled").strip()[:100]
    description = (seo.get("description") or package.get("description") or "").strip()
    tags = seo.get("tags") or package.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    tags = [str(t)[:30] for t in tags][:15]

    privacy_status = (privacy or cfg.upload_privacy).lower()
    if privacy_status not in ("private", "unlisted", "public"):
        privacy_status = "private"

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(seo.get("category_id") or "22"),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    youtube = youtube_service(cfg)
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"Upload progress: {pct}%")

    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"

    thumb_path = run_dir / "thumb.png"
    if thumb_path.exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumb_path), mimetype="image/png"),
            ).execute()
        except Exception as exc:  # noqa: BLE001 — thumbnail failure should not kill upload
            print(f"Warning: thumbnail upload failed: {exc}")

    result = {
        "video_id": video_id,
        "url": url,
        "title": title,
        "privacy": privacy_status,
    }
    (run_dir / "upload.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_status(run_dir, UPLOADED, note=url)
    return result
