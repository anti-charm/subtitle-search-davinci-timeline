from pathlib import Path
from xml.etree import ElementTree as ET

from subdav.fcpxml import TimelineClip, export_fcpxml
from subdav.media import MediaInfo
from subdav.models import SubtitleEntry


def media(path: Path, *, fps=(25, 1), audio=True, width=1920, height=1080):
    return MediaInfo(
        path,
        600_000,
        fps[0],
        fps[1],
        width,
        height,
        audio,
        audio_sources=1 if audio else 0,
        audio_channels=2 if audio else 0,
        audio_rate=48_000 if audio else 0,
    )


def entry(path: Path, index: int, start: int, end: int, text="dust"):
    return SubtitleEntry(index, start, end, text, path)


def test_export_fcpxml_deduplicates_assets_and_places_clips_consecutively(tmp_path: Path):
    video = tmp_path / "video & one.mp4"
    srt = tmp_path / "video & one.srt"
    clips = [
        TimelineClip(entry(srt, 1, 91_000, 105_000), video, media(video)),
        TimelineClip(entry(srt, 2, 121_500, 123_000), video, media(video)),
    ]
    output = tmp_path / "timeline.fcpxml"

    export_fcpxml(clips, output, "Dust compilation")
    root = ET.parse(output).getroot()

    assets = root.findall("./resources/asset")
    assert len(assets) == 1
    assert assets[0].attrib["hasVideo"] == "1"
    assert assets[0].attrib["hasAudio"] == "1"
    assert assets[0].attrib["audioSources"] == "1"
    assert assets[0].attrib["audioChannels"] == "2"
    assert assets[0].attrib["audioRate"] == "48000"
    assert assets[0].find("media-rep").attrib["src"].startswith("file:")

    nodes = root.findall("./library/event/project/sequence/spine/asset-clip")
    assert len(nodes) == 2
    assert nodes[0].attrib["start"] == "91s"
    assert nodes[0].attrib["duration"] == "14s"
    assert nodes[0].attrib["offset"] == "0s"
    assert nodes[1].attrib["start"] == "3038/25s"
    assert nodes[1].attrib["duration"] == "37/25s"
    assert nodes[1].attrib["offset"] == "14s"
    assert nodes[0].attrib["audioRole"] == "dialogue"


def test_export_preserves_input_order_and_uses_distinct_assets(tmp_path: Path):
    first_video = tmp_path / "B.mp4"
    second_video = tmp_path / "A.mp4"
    clips = [
        TimelineClip(entry(tmp_path / "B.srt", 2, 2_000, 3_000), first_video, media(first_video)),
        TimelineClip(entry(tmp_path / "A.srt", 1, 5_000, 7_000), second_video, media(second_video)),
    ]
    output = tmp_path / "ordered.fcpxml"

    export_fcpxml(clips, output, "Ordered")
    root = ET.parse(output).getroot()

    assert len(root.findall("./resources/asset")) == 2
    nodes = root.findall("./library/event/project/sequence/spine/asset-clip")
    assert [n.attrib["name"] for n in nodes] == ["B.mp4", "A.mp4"]
    assert [n.attrib["offset"] for n in nodes] == ["0s", "1s"]


def test_export_uses_rational_frame_duration_for_ntsc(tmp_path: Path):
    video = tmp_path / "ntsc.mp4"
    clip = TimelineClip(
        entry(tmp_path / "ntsc.srt", 1, 0, 2_000),
        video,
        media(video, fps=(30000, 1001)),
    )
    output = tmp_path / "ntsc.fcpxml"

    export_fcpxml([clip], output, "NTSC")
    root = ET.parse(output).getroot()

    fmt = root.find("./resources/format")
    assert fmt is not None
    assert fmt.attrib["frameDuration"] == "1001/30000s"


def test_subframe_srt_boundaries_are_snapped_once_to_shared_av_frame_grid(tmp_path: Path):
    video = tmp_path / "ntsc.mp4"
    clip = TimelineClip(
        entry(tmp_path / "ntsc.srt", 1, 1_017, 2_000),
        video,
        media(video, fps=(30000, 1001)),
    )
    output = tmp_path / "subframe.fcpxml"

    export_fcpxml([clip], output, "Subframe")
    root = ET.parse(output).getroot()
    node = root.find("./library/event/project/sequence/spine/asset-clip")

    # Source in/out are quantized once to video frames, then the same shared
    # asset-clip timing drives both picture and source audio.
    assert node.attrib["start"] == "1001/1000s"
    assert node.attrib["duration"] == "1001/1000s"
    assert node.attrib["srcEnable"] == "all"
    assert "audioStart" not in node.attrib
    assert "audioDuration" not in node.attrib


def test_no_audio_asset_does_not_claim_audio_role(tmp_path: Path):
    video = tmp_path / "silent.mp4"
    clip = TimelineClip(
        entry(tmp_path / "silent.srt", 1, 0, 1_000), video, media(video, audio=False)
    )
    output = tmp_path / "silent.fcpxml"

    export_fcpxml([clip], output, "Silent")
    root = ET.parse(output).getroot()

    asset = root.find("./resources/asset")
    node = root.find("./library/event/project/sequence/spine/asset-clip")
    assert asset.attrib["hasAudio"] == "0"
    assert "audioRole" not in node.attrib


def test_export_does_not_invent_source_color_space(tmp_path: Path):
    video = tmp_path / "unknown-color.mp4"
    clip = TimelineClip(entry(tmp_path / "unknown-color.srt", 1, 0, 1_000), video, media(video))
    output = tmp_path / "unknown-color.fcpxml"

    export_fcpxml([clip], output, "Unknown color")
    root = ET.parse(output).getroot()

    fmt = root.find("./resources/format")
    assert "colorSpace" not in fmt.attrib


def test_export_wraps_project_in_library_and_event_for_resolve_compatibility(tmp_path: Path):
    video = tmp_path / "video.mp4"
    clip = TimelineClip(entry(tmp_path / "video.srt", 1, 1_000, 2_000), video, media(video))
    output = tmp_path / "resolve.fcpxml"

    export_fcpxml([clip], output, "Resolve timeline")

    xml_text = output.read_text(encoding="utf-8")
    assert "<!DOCTYPE fcpxml>" in xml_text

    root = ET.parse(output).getroot()
    project = root.find("./library/event/project")
    assert project is not None
    assert project.attrib["name"] == "Resolve timeline"
    assert project.find("./sequence/spine/asset-clip") is not None


def test_export_can_add_editable_title_connected_to_each_clip(tmp_path: Path):
    from subdav.style import TitleStyle

    video = tmp_path / "movie.mp4"
    srt = tmp_path / "movie-he.srt"
    clip = TimelineClip(
        entry(srt, 7, 92_448, 96_152, text="הבאתי פאי שוקולד."),
        video,
        media(video),
    )
    output = tmp_path / "with-titles.fcpxml"
    style = TitleStyle()

    export_fcpxml([clip], output, "Chocolate", include_titles=True, title_style=style)
    root = ET.parse(output).getroot()

    effect = root.find("./resources/effect")
    assert effect is not None
    assert effect.attrib["name"] == "Basic Title"
    assert (
        effect.attrib["uid"]
        == ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
    )

    node = root.find("./library/event/project/sequence/spine/asset-clip")
    title = node.find("./title")
    assert title is not None
    assert title.attrib["lane"] == "1"
    assert title.attrib["offset"] == node.attrib["start"]
    assert title.attrib["duration"] == node.attrib["duration"]

    params = {param.attrib["name"]: param.attrib for param in title.findall("./param")}
    assert "Position" not in params
    assert params["Flatten"]["value"] == "1"
    assert params["Alignment"]["value"] == "1 (Center)"
    transform = title.find("./adjust-transform")
    assert transform is not None
    assert transform.attrib["position"] == "0 -36"

    styled = title.find("./text/text-style")
    assert styled is not None
    assert styled.text == "הבאתי פאי שוקולד."

    style_def = title.find("./text-style-def/text-style")
    assert style_def is not None
    assert style_def.attrib["font"] == "Arial"
    assert style_def.attrib["fontSize"] == "48"
    assert style_def.attrib["fontFace"] == "Regular"
    assert style_def.attrib["fontColor"] == "1 1 1 1"
    assert style_def.attrib["strokeColor"] == "0 0 0 1"
    assert style_def.attrib["strokeWidth"] == "1"


def test_export_without_titles_emits_no_title_effect_or_title_nodes(tmp_path: Path):
    video = tmp_path / "movie.mp4"
    clip = TimelineClip(
        entry(tmp_path / "movie.srt", 1, 1_000, 2_000, "hello"), video, media(video)
    )
    output = tmp_path / "plain.fcpxml"

    export_fcpxml([clip], output, "Plain", include_titles=False)
    root = ET.parse(output).getroot()

    assert root.find("./resources/effect") is None
    assert root.find("./library/event/project/sequence/spine/asset-clip/title") is None


def test_mixed_media_titles_use_the_timeline_frame_for_position(tmp_path):
    from dataclasses import replace

    from subdav.style import TitleStyle

    wide = tmp_path / "wide.mp4"
    tall = tmp_path / "tall.mp4"
    clips = [
        TimelineClip(entry(tmp_path / "wide.srt", 1, 0, 1000, "Wide"), wide, media(wide)),
        TimelineClip(
            entry(tmp_path / "tall.srt", 2, 0, 1000, "Tall"),
            tall,
            replace(media(tall), width=1080, height=1920),
        ),
    ]
    output = tmp_path / "mixed.fcpxml"
    export_fcpxml(
        clips,
        output,
        "Mixed",
        include_titles=True,
        title_style=TitleStyle(position_x_fraction=0.1, position_y_fraction=0.25),
    )
    positions = [
        node.get("position") for node in ET.parse(output).findall(".//title/adjust-transform")
    ]
    assert positions == ["17.778 25", "17.778 25"]
