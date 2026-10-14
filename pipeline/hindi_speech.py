"""Make Hindi TTS sound closer to natural Indian Hinglish speech."""

from __future__ import annotations

import json
import re
from pathlib import Path

_PRONOUNCE_PATH = Path(__file__).resolve().parent / "pronounce_hi.json"
_PRONOUNCE: dict[str, str] | None = None

_DIGITS_HI = {
    "0": "शून्य",
    "1": "एक",
    "2": "दो",
    "3": "तीन",
    "4": "चार",
    "5": "पाँच",
    "6": "छह",
    "7": "सात",
    "8": "आठ",
    "9": "नौ",
    "10": "दस",
    "11": "ग्यारह",
    "12": "बारह",
    "13": "तेरह",
    "14": "चौदह",
    "15": "पंद्रह",
    "16": "सोलह",
    "17": "सत्रह",
    "18": "अठारह",
    "19": "उन्नीस",
    "20": "बीस",
    "21": "इक्कीस",
    "25": "पच्चीस",
    "30": "तीस",
    "40": "चालीस",
    "50": "पचास",
    "60": "साठ",
    "70": "सत्तर",
    "80": "अस्सी",
    "90": "नब्बे",
    "100": "सौ",
    "1000": "हज़ार",
}


def _load_pronounce() -> dict[str, str]:
    global _PRONOUNCE
    if _PRONOUNCE is None:
        if _PRONOUNCE_PATH.exists():
            _PRONOUNCE = json.loads(_PRONOUNCE_PATH.read_text(encoding="utf-8"))
        else:
            _PRONOUNCE = {}
    return _PRONOUNCE


def _replace_pronunciations(text: str) -> str:
    mapping = _load_pronounce()
    # Longer keys first so "YouTube" wins over "Tube"
    for src in sorted(mapping.keys(), key=len, reverse=True):
        dst = mapping[src]
        text = re.sub(rf"(?<!\w){re.escape(src)}(?!\w)", dst, text)
    return text


def _numbers_to_hindi(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        num = match.group(0)
        if num in _DIGITS_HI:
            return _DIGITS_HI[num]
        # Spell digit-by-digit for years / big IDs (2024 → दो शून्य दो चार feels odd)
        # Prefer natural: keep 2-digit/3-digit word if known, else digit names
        if len(num) <= 2 and num.isdigit():
            n = int(num)
            if str(n) in _DIGITS_HI:
                return _DIGITS_HI[str(n)]
        if len(num) <= 3:
            return " ".join(_DIGITS_HI.get(d, d) for d in num)
        return num

    return re.sub(r"\b\d+\b", repl, text)


def _natural_punctuation(text: str) -> str:
    # AI-ish dashes / ellipses → spoken pauses
    text = text.replace("—", ", ").replace("–", ", ").replace("…", ", ")
    text = text.replace("...", ", ")
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    # Devanagari danda is fine; ensure space after
    text = re.sub(r"。", "। ", text)
    text = re.sub(r"।\s*", "। ", text)
    # Soften ALL CAPS English leftovers into title-ish for TTS
    def _soft_caps(m: re.Match[str]) -> str:
        word = m.group(0)
        if len(word) <= 3:
            return word
        return word.capitalize()

    text = re.sub(r"\b[A-Z]{3,}\b", _soft_caps, text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _hinglish_connectors(text: str) -> str:
    """Light touch: add breath commas after common Hindi connectors."""
    connectors = [
        "लेकिन",
        "क्योंकि",
        "इसलिए",
        "मतलब",
        "असल में",
        "देखो",
        "सुनो",
        "तो दोस्तों",
        "भाई",
        "यानी",
    ]
    for c in connectors:
        text = re.sub(rf"({re.escape(c)})\s+", rf"\1, ", text)
    return text


def prepare_spoken_text(text: str, language: str = "hi") -> str:
    """Rewrite script text so edge-tts Hindi voices pronounce it more naturally."""
    out = (text or "").strip()
    if not out:
        return out
    if not language.lower().startswith("hi"):
        return _natural_punctuation(out)

    out = _replace_pronunciations(out)
    out = _numbers_to_hindi(out)
    out = _natural_punctuation(out)
    out = _hinglish_connectors(out)
    # Avoid stage directions leaking into speech
    out = re.sub(r"\[ON SCREEN:[^\]]*\]", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def split_spoken_chunks(text: str, max_chars: int = 140) -> list[str]:
    """Split into short spoken chunks for more natural pacing."""
    text = (text or "").strip()
    if not text:
        return []
    # Split on sentence enders
    parts = re.split(r"(?<=[।!?\.])\s+", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not buf:
            buf = part
        elif len(buf) + 1 + len(part) <= max_chars:
            buf = f"{buf} {part}"
        else:
            chunks.append(buf)
            buf = part
    if buf:
        chunks.append(buf)
    return chunks or [text]
