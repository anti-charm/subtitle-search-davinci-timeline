from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

# This module builds XML; it never parses supplied XML.
from xml.etree import ElementTree as ET  # nosec B405

from .media import MediaInfo
from .models import SubtitleEntry
from .style import TitleStyle

BASIC_TITLE_UID = (
    ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
)

_BASIC_TITLE_PARAM_KEYS = {
    "Flatten": "9999/999166631/999166633/2/351",
    "Alignment": "9999/999166631/999166633/2/354/999169573/401",
}


@dataclass(frozen=True, slots=True)
class TimelineClip:
    entry: SubtitleEntry
    video_path: Path
    media: MediaInfo


def _time_from_fraction(value: Fraction) -> str:
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator}s"
    return f"{value.numerator}/{value.denominator}s"


def _ms_time(milliseconds: int) -> str:
    return _time_from_fraction(Fraction(milliseconds, 1000))


def _frame_duration(media: MediaInfo) -> str:
    return _time_from_fraction(Fraction(media.fps_den, media.fps_num))


def _canonical(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _round_positive_fraction(value: Fraction) -> int:
    """Round a non-negative Fraction to the nearest integer, halves upward."""
    if value < 0:
        raise ValueError("frame times must be non-negative")
    return (2 * value.numerator + value.denominator) // (2 * value.denominator)


def _snap_ms_to_frame(milliseconds: int, media: MediaInfo) -> Fraction:
    frame = Fraction(media.fps_den, media.fps_num)
    seconds = Fraction(milliseconds, 1000)
    frame_index = _round_positive_fraction(seconds / frame)
    return frame_index * frame


def _snapped_source_range(clip: TimelineClip) -> tuple[Fraction, Fraction]:
    start = _snap_ms_to_frame(clip.entry.start_ms, clip.media)
    end = _snap_ms_to_frame(clip.entry.end_ms, clip.media)
    frame = Fraction(clip.media.fps_den, clip.media.fps_num)
    # ffprobe duration was rounded to milliseconds. Allow that rounding's
    # half-millisecond uncertainty so 24/29.97 fps final frames are not lost.
    available_frames = Fraction(2 * clip.media.duration_ms + 1, 2000) // frame
    if available_frames < 1:
        raise ValueError("Source media is shorter than one complete video frame")
    available_end = available_frames * frame
    start = min(start, available_end - frame)
    end = min(end, available_end)
    if end <= start:
        end = start + frame
    return start, end


def export_fcpxml(
    clips: Sequence[TimelineClip],
    output_path: Path,
    timeline_name: str,
    *,
    include_titles: bool = False,
    title_style: TitleStyle | None = None,
) -> Path:
    if not clips:
        raise ValueError("At least one timeline clip is required")

    output_path = Path(output_path).expanduser().resolve()
    if output_path.suffix.casefold() not in {".fcpxml", ".xml"}:
        raise ValueError("Choose an .fcpxml or .xml output file")
    for clip in clips:
        if (
            clip.entry.start_ms < 0
            or clip.entry.end_ms < clip.entry.start_ms
            or clip.entry.end_ms > clip.media.duration_ms
        ):
            raise ValueError("Subtitle range is outside the source media duration")
        for source in (clip.video_path, clip.entry.srt_path):
            source = _canonical(source)
            if source == output_path or (
                source.exists() and output_path.exists() and source.samefile(output_path)
            ):
                raise ValueError("Timeline export cannot overwrite source media or subtitles")
        if (
            clip.media.fps_num <= 0
            or clip.media.fps_den <= 0
            or clip.media.width <= 0
            or clip.media.height <= 0
            or clip.media.duration_ms <= 0
        ):
            raise ValueError("Invalid media metadata for timeline export")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("fcpxml", {"version": "1.10"})
    resources = ET.SubElement(root, "resources")

    format_ids: dict[tuple[int, int, int, int], str] = {}
    asset_ids: dict[Path, str] = {}
    next_resource_id = 1

    def get_format_id(info: MediaInfo) -> str:
        nonlocal next_resource_id
        key = (info.fps_num, info.fps_den, info.width, info.height)
        existing = format_ids.get(key)
        if existing:
            return existing
        resource_id = f"r{next_resource_id}"
        next_resource_id += 1
        ET.SubElement(
            resources,
            "format",
            {
                "id": resource_id,
                "frameDuration": _frame_duration(info),
                "width": str(info.width),
                "height": str(info.height),
            },
        )
        format_ids[key] = resource_id
        return resource_id

    # Create format and asset resources once per unique source file, preserving
    # first-use order so output remains deterministic.
    for clip in clips:
        canonical = _canonical(clip.video_path)
        if canonical in asset_ids:
            continue
        format_id = get_format_id(clip.media)
        asset_id = f"r{next_resource_id}"
        next_resource_id += 1
        asset_attrs = {
            "id": asset_id,
            "name": canonical.name,
            "start": "0s",
            "duration": _time_from_fraction(
                max(
                    Fraction(clip.media.duration_ms, 1000),
                    (
                        Fraction(2 * clip.media.duration_ms + 1, 2000)
                        // Fraction(clip.media.fps_den, clip.media.fps_num)
                    )
                    * Fraction(clip.media.fps_den, clip.media.fps_num),
                )
            ),
            "hasVideo": "1",
            "hasAudio": "1" if clip.media.has_audio else "0",
            "format": format_id,
        }
        if clip.media.has_audio:
            if clip.media.audio_sources > 0:
                asset_attrs["audioSources"] = str(clip.media.audio_sources)
            if clip.media.audio_channels > 0:
                asset_attrs["audioChannels"] = str(clip.media.audio_channels)
            if clip.media.audio_rate > 0:
                asset_attrs["audioRate"] = str(clip.media.audio_rate)
        asset = ET.SubElement(resources, "asset", asset_attrs)
        ET.SubElement(
            asset,
            "media-rep",
            {"kind": "original-media", "src": canonical.as_uri()},
        )
        asset_ids[canonical] = asset_id

    title_effect_id: str | None = None
    if include_titles:
        title_effect_id = f"r{next_resource_id}"
        next_resource_id += 1
        ET.SubElement(
            resources,
            "effect",
            {"id": title_effect_id, "name": "Basic Title", "uid": BASIC_TITLE_UID},
        )
        if title_style is None:
            title_style = TitleStyle()

    first_format = get_format_id(clips[0].media)
    snapped_ranges = [_snapped_source_range(clip) for clip in clips]
    snapped_durations = [end - start for start, end in snapped_ranges]
    total_duration = sum(snapped_durations, Fraction(0, 1))

    # Resolve 21 is stricter than Final Cut Pro about project inheritance.
    # Wrap the project in a library/event hierarchy even though FCPXML 1.10
    # permits a top-level project.
    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", {"name": "Subtitle Search"})
    project = ET.SubElement(event, "project", {"name": timeline_name})
    sequence = ET.SubElement(
        project,
        "sequence",
        {
            "format": first_format,
            "duration": _time_from_fraction(total_duration),
            "tcStart": "0s",
            "tcFormat": "NDF",
        },
    )
    spine = ET.SubElement(sequence, "spine")

    timeline_offset = Fraction(0, 1)
    for clip, (source_start, source_end), duration in zip(clips, snapped_ranges, snapped_durations):
        if clip.entry.end_ms < clip.entry.start_ms:
            raise ValueError(f"Subtitle entry {clip.entry.index} ends before it starts")
        canonical = _canonical(clip.video_path)
        attrs = {
            "name": canonical.name,
            "ref": asset_ids[canonical],
            "offset": _time_from_fraction(timeline_offset),
            "start": _time_from_fraction(source_start),
            "duration": _time_from_fraction(duration),
            # Explicitly keep all source media components together. We never
            # emit audioStart/audioDuration split-edit attributes.
            "srcEnable": "all",
        }
        if clip.media.has_audio:
            # asset-clip includes both media components from the referenced
            # asset. audioRole labels the included source audio as dialogue.
            attrs["audioRole"] = "dialogue"
        clip_node = ET.SubElement(spine, "asset-clip", attrs)
        if include_titles:
            if title_effect_id is None or title_style is None:
                raise ValueError("Missing title style or effect")
            style_id = (
                f"ts{clip.entry.index}_{timeline_offset.numerator}_{timeline_offset.denominator}"
            )
            title = ET.SubElement(
                clip_node,
                "title",
                {
                    "ref": title_effect_id,
                    "lane": "1",
                    "name": clip.entry.text[:40],
                    "offset": _time_from_fraction(source_start),
                    "start": "0s",
                    "duration": _time_from_fraction(duration),
                },
            )
            ET.SubElement(
                title,
                "param",
                {
                    "name": "Flatten",
                    "key": _BASIC_TITLE_PARAM_KEYS["Flatten"],
                    "value": "1",
                },
            )
            alignment_label = {"left": "0 (Left)", "center": "1 (Center)", "right": "2 (Right)"}[
                title_style.alignment
            ]
            ET.SubElement(
                title,
                "param",
                {
                    "name": "Alignment",
                    "key": _BASIC_TITLE_PARAM_KEYS["Alignment"],
                    "value": alignment_label,
                },
            )
            text_node = ET.SubElement(title, "text")
            ET.SubElement(text_node, "text-style", {"ref": style_id}).text = clip.entry.text
            style_def = ET.SubElement(title, "text-style-def", {"id": style_id})
            ET.SubElement(style_def, "text-style", title_style.text_style_attrs())
            ET.SubElement(
                title,
                "adjust-transform",
                {"position": title_style.transform_position(clip.media.width, clip.media.height)},
            )
        timeline_offset += duration

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    xml_body = ET.tostring(root, encoding="unicode")
    if any(
        not (
            ch in "\t\n\r"
            or 0x20 <= ord(ch) <= 0xD7FF
            or 0xE000 <= ord(ch) <= 0xFFFD
            or 0x10000 <= ord(ch) <= 0x10FFFF
        )
        for ch in xml_body
    ):
        raise ValueError("Subtitle text or names contain characters invalid in XML")
    contents = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n' + xml_body + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output_path.parent, suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(contents)
        os.replace(temporary, output_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return output_path
