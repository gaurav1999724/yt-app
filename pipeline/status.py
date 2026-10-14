"""Run STATUS file helpers. Approval gate lives here."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

READY = "READY_FOR_REVIEW"
APPROVED = "APPROVED"
UPLOADED = "UPLOADED"
DRAFT = "DRAFT"
RENDERING = "RENDERING"
FAILED = "FAILED"


def status_path(run_dir: Path) -> Path:
    return run_dir / "STATUS"


def read_status(run_dir: Path) -> str:
    p = status_path(run_dir)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8").strip().splitlines()[0].strip()


def write_status(run_dir: Path, status: str, note: str = "") -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = f"{status}\n{ts}\n"
    if note:
        body += f"{note}\n"
    status_path(run_dir).write_text(body, encoding="utf-8")


def is_approved(run_dir: Path) -> bool:
    return read_status(run_dir) == APPROVED


def approve(run_dir: Path) -> None:
    write_status(run_dir, APPROVED, note="approved by user ship-it")
