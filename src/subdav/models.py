from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SubtitleEntry:
    index: int
    start_ms: int
    end_ms: int
    text: str
    srt_path: Path
