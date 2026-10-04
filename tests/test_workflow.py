from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from subdav.library import scan_library
from subdav.media import MediaInfo
from subdav.store import PairingStore
from subdav.workflow import (
    UnresolvedPairingError,
    export_matches,
    resolve_pairs,
    search_library,
)


def write_srt(path: Path, text: str):
    path.write_text(text, encoding="utf-8")


def fake_probe(path: Path) -> MediaInfo:
    return MediaInfo(Path(path), 600_000, 25, 1, 1920, 1080, True)


def test_scan_pair_search_and_export_exact_and_manual_matches(tmp_path: Path):
    exact_srt = tmp_path / "Episode01.srt"
    exact_video = tmp_path / "Episode01.mp4"
    manual_srt = tmp_path / "OddSubtitle.en.srt"
    manual_video = tmp_path / "DifferentVideoName.mp4"
    exact_video.write_bytes(b"")
    manual_video.write_bytes(b"")
    write_srt(exact_srt, "1\n00:01:31,000 --> 00:01:45,000\nHearthstone dust refund strategy\n")
    write_srt(manual_srt, "1\n00:02:00,500 --> 00:02:02,750\nMore dust here\n")

    scan = scan_library(tmp_path)
    store = PairingStore(tmp_path / "pairs.sqlite3")
    store.set_pair(manual_srt, manual_video)
    pairs = resolve_pairs(scan, store)

    assert pairs[exact_srt.resolve()].status == "exact"
    assert pairs[manual_srt.resolve()].status == "manual"

    matches = search_library(scan, pairs, "dust")
    assert len(matches) == 2
    assert [m.entry.start_ms for m in matches] == [91_000, 120_500]

    output = tmp_path / "dust.fcpxml"
    export_matches(matches, output, "Dust", probe_func=fake_probe)

    root = ET.parse(output).getroot()
    nodes = root.findall("./library/event/project/sequence/spine/asset-clip")
    assert [node.attrib["start"] for node in nodes] == ["91s", "3013/25s"]
    assert [node.attrib["duration"] for node in nodes] == ["14s", "56/25s"]


def test_export_blocks_selected_match_with_unresolved_pairing(tmp_path: Path):
    srt = tmp_path / "Unknown.srt"
    write_srt(srt, "1\n00:00:01,000 --> 00:00:02,000\ndust\n")
    (tmp_path / "Other.mp4").write_bytes(b"")

    scan = scan_library(tmp_path)
    pairs = resolve_pairs(scan, PairingStore(tmp_path / "pairs.sqlite3"))
    matches = search_library(scan, pairs, "dust")

    with pytest.raises(UnresolvedPairingError, match="Unknown.srt"):
        export_matches(matches, tmp_path / "nope.fcpxml", "Nope", probe_func=fake_probe)


def test_export_rejects_subtitle_range_past_end_of_video(tmp_path: Path):
    srt = tmp_path / "Episode.srt"
    video = tmp_path / "Episode.mp4"
    video.write_bytes(b"")
    write_srt(srt, "1\n00:00:09,000 --> 00:00:12,000\ndust\n")
    scan = scan_library(tmp_path)
    pairs = resolve_pairs(scan, PairingStore(tmp_path / "pairs.sqlite3"))
    matches = search_library(scan, pairs, "dust")

    def short_probe(path: Path) -> MediaInfo:
        return MediaInfo(Path(path), 10_000, 25, 1, 1920, 1080, True)

    with pytest.raises(ValueError, match="exceeds video duration"):
        export_matches(matches, tmp_path / "invalid.fcpxml", "Invalid", probe_func=short_probe)


def test_export_matches_can_include_editable_titles(tmp_path: Path):
    from subdav.style import TitleStyle

    srt = tmp_path / "Movie - Hebrew.srt"
    video = tmp_path / "Movie.mp4"
    video.write_bytes(b"")
    write_srt(srt, "1\n00:00:01,000 --> 00:00:03,000\nשוקולד מלא\n")
    scan = scan_library(tmp_path)
    pairs = resolve_pairs(scan, PairingStore(tmp_path / "pairs.sqlite3"))
    matches = search_library(scan, pairs, "שוקולד")

    output = tmp_path / "titles.fcpxml"
    export_matches(
        matches,
        output,
        "Chocolate",
        probe_func=fake_probe,
        include_titles=True,
        title_style=TitleStyle(font_size=52),
    )

    root = ET.parse(output).getroot()
    title = root.find("./library/event/project/sequence/spine/asset-clip/title")
    assert title is not None
    assert title.find("./text/text-style").text == "שוקולד מלא"
    assert title.find("./text-style-def/text-style").attrib["fontSize"] == "52"


def test_search_library_can_limit_search_to_enabled_srt_files(tmp_path: Path):
    first = tmp_path / "First.srt"
    second = tmp_path / "Second.srt"
    first_video = tmp_path / "First.mp4"
    second_video = tmp_path / "Second.mp4"
    first_video.write_bytes(b"")
    second_video.write_bytes(b"")
    write_srt(first, "1\n00:00:01,000 --> 00:00:02,000\nchocolate first\n")
    write_srt(second, "1\n00:00:03,000 --> 00:00:04,000\nchocolate second\n")

    scan = scan_library(tmp_path)
    pairs = resolve_pairs(scan, PairingStore(tmp_path / "pairs.sqlite3"))
    matches = search_library(
        scan,
        pairs,
        "chocolate",
        enabled_subtitles={first.resolve()},
    )

    assert [match.entry.srt_path.name for match in matches] == ["First.srt"]


def test_each_downloaded_occurrence_exports_its_own_clip_and_local_range(tmp_path):
    original = tmp_path / "Example.en-orig.srt"
    write_srt(original, "1\n01:00:00,000 --> 01:00:01,000\nexample phrase\n")
    for n in range(1, 6):
        srt = tmp_path / f"Example_match_{n:03d}.srt"
        write_srt(srt, "1\n00:00:05,000 --> 00:00:06,000\nexample phrase\n")
        srt.with_suffix(".mp4").write_bytes(b"")
    scan = scan_library(tmp_path, downloaded_clips_only=True)
    pairs = resolve_pairs(scan, PairingStore(tmp_path / "state.sqlite3"))
    matches = search_library(scan, pairs, "example")
    output = tmp_path / "downloaded.fcpxml"
    export_matches(matches, output, "Downloaded", probe_func=fake_probe, include_titles=True)

    root = ET.parse(output).getroot()
    assets = {a.attrib["id"]: a for a in root.findall("./resources/asset")}
    nodes = root.findall("./library/event/project/sequence/spine/asset-clip")
    assert len(nodes) == len(assets) == 5
    assert [assets[n.attrib["ref"]].attrib["name"] for n in nodes] == [
        "Example_match_001.mp4",
        "Example_match_002.mp4",
        "Example_match_003.mp4",
        "Example_match_004.mp4",
        "Example_match_005.mp4",
    ]
    assert all(n.attrib["start"] == "5s" and n.attrib["duration"] == "1s" for n in nodes)
    assert all(n.find("./title/text/text-style").text == "example phrase" for n in nodes)
    assert all(m.pairing.status == "exact" for m in matches)
    assert original not in [m.entry.srt_path for m in matches]
