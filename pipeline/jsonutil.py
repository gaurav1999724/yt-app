"""Safe JSON helpers for empty / invalid files."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _clean(raw: str | None) -> str:
    text = (raw or "").replace("\ufeff", "").strip()
    # Ignore common non-JSON placeholders people leave in the box
    if text in {"...", "…", "-", "null", "undefined", "None"}:
        return ""
    return text


def load_json_file(path: Path, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    if not path.exists():
        return default
    raw = _clean(path.read_text(encoding="utf-8"))
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def parse_json_text(
    raw: str | None,
    *,
    field: str = "JSON",
    strict: bool = False,
) -> dict:
    """Parse a JSON object.

    Empty / placeholder → {}.
    Invalid: strict=True raises ValueError; strict=False → {}.
    """
    text = _clean(raw)
    if not text:
        return {}
    # Allow single quotes → double quotes for simple cases
    if "'" in text and '"' not in text:
        text = text.replace("'", '"')
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        if not strict:
            return {}
        raise ValueError(
            f"{field} invalid hai: {exc.msg} (line {exc.lineno}). "
            'Valid example: {"title":"मेरा टाइटल","thumbnail_text":"तीन शब्द"}'
        ) from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        if not strict:
            return {}
        raise ValueError(
            f"{field} ek JSON object hona chahiye ({{ ... }}), array/string nahi."
        )
    return data
