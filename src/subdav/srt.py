from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .models import SubtitleEntry

_TIME_RE = re.compile(
    r"^(?P<sh>\d{1,3}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,3}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})(?:\s+.*)?$"
)


def _to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    if int(minutes) >= 60 or int(seconds) >= 60:
        raise ValueError("Invalid SRT timestamp: minutes and seconds must be below 60")
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def _decode_srt(raw: bytes, path: Path) -> str:
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    filename = path.name.casefold()
    if any(tag in filename for tag in (".he.", ".heb.", "hebrew", "cp1255")):
        preferred = ("cp1255", "cp1252", "cp1256")
    elif any(tag in filename for tag in (".ar.", ".ara.", "arabic", "cp1256")):
        preferred = ("cp1256", "cp1252", "cp1255")
    else:
        decoded: dict[str, str] = {}
        for encoding in ("cp1252", "cp1255", "cp1256"):
            try:
                decoded[encoding] = raw.decode(encoding)
            except UnicodeDecodeError:
                continue

        def script_ratio(text: str, lo: str, hi: str) -> float:
            letters = sum(ch.isalpha() for ch in text)
            if not letters:
                return 0.0
            return sum(lo <= ch <= hi for ch in text) / letters

        hebrew = decoded.get("cp1255")
        arabic = decoded.get("cp1256")
        hebrew_ratio = script_ratio(hebrew, "\u0590", "\u05ff") if hebrew else 0.0
        arabic_ratio = script_ratio(arabic, "\u0600", "\u06ff") if arabic else 0.0
        if hebrew_ratio >= 0.45 and hebrew_ratio > arabic_ratio:
            return hebrew
        if arabic_ratio >= 0.45 and arabic_ratio > hebrew_ratio:
            return arabic
        if "cp1252" in decoded:
            return decoded["cp1252"]
        preferred = ("cp1255", "cp1256")

    for encoding in preferred:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Could not decode subtitle file: {path}")


def parse_srt(path: Path) -> list[SubtitleEntry]:
    path = Path(path)
    text = _decode_srt(path.read_bytes(), path).replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    entries: list[SubtitleEntry] = []
    i = 0

    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        try:
            index = int(lines[i].strip())
        except ValueError as exc:
            raise ValueError(f"Invalid SRT index at line {i + 1} in {path}") from exc
        i += 1
        if i >= len(lines):
            raise ValueError(f"Missing SRT timestamp after entry {index} in {path}")

        match = _TIME_RE.match(lines[i].strip())
        if not match:
            raise ValueError(f"Invalid SRT timestamp at line {i + 1} in {path}: {lines[i]!r}")
        i += 1

        start_ms = _to_ms(match["sh"], match["sm"], match["ss"], match["sms"])
        end_ms = _to_ms(match["eh"], match["em"], match["es"], match["ems"])
        if end_ms < start_ms:
            raise ValueError(f"Subtitle entry {index} ends before it starts in {path}")

        body: list[str] = []
        while i < len(lines) and lines[i].strip() != "":
            body.append(lines[i])
            i += 1

        entries.append(
            SubtitleEntry(
                index=index,
                start_ms=start_ms,
                end_ms=end_ms,
                text="\n".join(body),
                srt_path=path,
            )
        )

    return entries


def search_entries(
    entries: Iterable[SubtitleEntry],
    query: str,
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
) -> list[SubtitleEntry]:
    if not query:
        return []

    flags = 0 if case_sensitive else re.IGNORECASE
    if whole_word:
        pattern = re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", flags)
        return [entry for entry in entries if pattern.search(entry.text)]

    if case_sensitive:
        return [entry for entry in entries if query in entry.text]

    folded = query.casefold()
    return [entry for entry in entries if folded in entry.text.casefold()]
