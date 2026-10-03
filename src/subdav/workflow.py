from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .fcpxml import TimelineClip, export_fcpxml
from .library import LibraryScan
from .media import MediaInfo, probe_media
from .models import SubtitleEntry
from .pairing import suggest_pair
from .srt import parse_srt, search_entries
from .store import PairingStore
from .style import TitleStyle


@dataclass(frozen=True, slots=True)
class ResolvedPair:
    srt_path: Path
    status: str
    video_path: Path | None
    candidates: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchMatch:
    entry: SubtitleEntry
    pairing: ResolvedPair


class UnresolvedPairingError(RuntimeError):
    pass


class SubtitleReadError(RuntimeError):
    pass


def resolve_pairs(scan: LibraryScan, store: PairingStore) -> dict[Path, ResolvedPair]:
    resolved: dict[Path, ResolvedPair] = {}
    for raw_srt in scan.subtitles:
        srt = raw_srt.resolve()
        manual = store.get_pair(srt)
        if manual is not None and manual.exists():
            resolved[srt] = ResolvedPair(srt, "manual", manual.resolve(), (manual.resolve(),))
            continue

        suggestion = suggest_pair(srt, scan.videos)
        resolved[srt] = ResolvedPair(
            srt_path=srt,
            status=suggestion.status,
            video_path=suggestion.video_path.resolve() if suggestion.video_path else None,
            candidates=tuple(p.resolve() for p in suggestion.candidates),
        )
    return resolved


def search_library(
    scan: LibraryScan,
    pairs: Mapping[Path, ResolvedPair],
    query: str,
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    enabled_subtitles: set[Path] | None = None,
) -> list[SearchMatch]:
    results: list[SearchMatch] = []
    enabled = (
        {path.resolve() for path in enabled_subtitles} if enabled_subtitles is not None else None
    )
    for raw_srt in scan.subtitles:
        srt = raw_srt.resolve()
        if enabled is not None and srt not in enabled:
            continue
        try:
            entries = parse_srt(srt)
        except (OSError, UnicodeError, ValueError) as exc:
            raise SubtitleReadError(f"Could not read {srt.name}: {exc}") from exc
        pairing = pairs.get(srt, ResolvedPair(srt, "unresolved", None, ()))
        for entry in search_entries(
            entries,
            query,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
        ):
            results.append(SearchMatch(entry, pairing))

    results.sort(
        key=lambda match: (
            str(match.entry.srt_path).casefold(),
            match.entry.start_ms,
            match.entry.index,
        )
    )
    return results


def export_matches(
    matches: Sequence[SearchMatch],
    output_path: Path,
    timeline_name: str,
    *,
    probe_func: Callable[[Path], MediaInfo] = probe_media,
    include_titles: bool = False,
    title_style: TitleStyle | None = None,
) -> Path:
    if not matches:
        raise ValueError("No subtitle matches are selected for export")

    unresolved = sorted(
        {match.entry.srt_path.name for match in matches if match.pairing.video_path is None}
    )
    if unresolved:
        raise UnresolvedPairingError(
            "Selected matches have unresolved video pairing: " + ", ".join(unresolved)
        )

    media_cache: dict[Path, MediaInfo] = {}
    clips: list[TimelineClip] = []
    for match in matches:
        if match.pairing.video_path is None:
            raise UnresolvedPairingError("Selected match has no video pairing")
        video = match.pairing.video_path.resolve()
        info = media_cache.get(video)
        if info is None:
            info = probe_func(video)
            media_cache[video] = info
        if match.entry.end_ms > info.duration_ms:
            raise ValueError(
                f"Subtitle range {match.entry.srt_path.name} #{match.entry.index} "
                f"ends at {match.entry.end_ms} ms and exceeds video duration "
                f"({info.duration_ms} ms) for {video.name}."
            )
        clips.append(TimelineClip(match.entry, video, info))

    return export_fcpxml(
        clips,
        output_path,
        timeline_name,
        include_titles=include_titles,
        title_style=title_style,
    )
