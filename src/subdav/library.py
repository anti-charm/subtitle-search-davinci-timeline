from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .pairing import is_downloaded_clip

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".m4v",
    ".webm",
    ".mpg",
    ".mpeg",
    ".mts",
    ".m2ts",
}


@dataclass(frozen=True, slots=True)
class LibraryScan:
    root: Path
    subtitles: tuple[Path, ...]
    videos: tuple[Path, ...]


def scan_library(root: Path, *, downloaded_clips_only: bool = False) -> LibraryScan:
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    subtitles: list[Path] = []
    videos: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.casefold()
        if suffix == ".srt":
            if not downloaded_clips_only or is_downloaded_clip(path):
                subtitles.append(path)
        elif suffix in VIDEO_EXTENSIONS:
            videos.append(path)

    def key(path: Path) -> str:
        return str(path.relative_to(root)).casefold()

    return LibraryScan(root, tuple(sorted(subtitles, key=key)), tuple(sorted(videos, key=key)))
