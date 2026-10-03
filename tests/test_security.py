"""Regression checks for privacy boundaries and hostile local inputs."""

import json
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from subdav.app import SubtitleDavinciApp, resolve_saved_title_style
from subdav.fcpxml import TimelineClip, export_fcpxml
from subdav.media import MediaInfo, MediaProbeError, probe_media
from subdav.models import SubtitleEntry
from subdav.srt import parse_srt
from subdav.store import PairingStore
from subdav.style import TitleStyle
from subdav.workflow import SubtitleReadError


def payload():
    return {
        "streams": [
            {
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "25/1",
                "r_frame_rate": "25/1",
            }
        ],
        "format": {"duration": "10"},
    }


@pytest.mark.parametrize("name", ["space & semi; quote' שלום.mp4", "-option.mp4"])
def test_probe_treats_paths_as_literal_local_arguments(monkeypatch, tmp_path, name):
    path = tmp_path / name

    def run(command, **kwargs):
        assert isinstance(command, list)
        assert command[-2:] == ["-i", str(path.resolve())]
        assert command[command.index("-protocol_whitelist") + 1] == "file"
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 30
        assert kwargs["encoding"] == "utf-8"
        return subprocess.CompletedProcess(command, 0, json.dumps(payload()), "")

    monkeypatch.setattr(subprocess, "run", run)
    assert probe_media(path, ffprobe=sys.executable).duration_ms == 10_000


@pytest.mark.parametrize("bad", [None, [], 3, {"streams": [None]}, {"streams": {}}, {"format": []}])
def test_probe_rejects_invalid_json_structure(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(bad), ""),
    )
    with pytest.raises(MediaProbeError):
        probe_media(tmp_path / "demo.mp4", ffprobe=sys.executable)


@pytest.mark.parametrize("duration", ["nan", "inf", "-1", "0", {}, "oops"])
def test_probe_rejects_invalid_duration(monkeypatch, tmp_path, duration):
    data = payload()
    data["format"]["duration"] = duration
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(data), ""),
    )
    with pytest.raises(MediaProbeError):
        probe_media(tmp_path / "demo.mp4", ffprobe=sys.executable)


@pytest.mark.parametrize(
    "field,value", [("width", 0), ("height", -1), ("width", "bad"), ("height", [])]
)
def test_probe_rejects_invalid_dimensions(monkeypatch, tmp_path, field, value):
    data = payload()
    data["streams"][0][field] = value
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps(data), ""),
    )
    with pytest.raises(MediaProbeError):
        probe_media(tmp_path / "demo.mp4", ffprobe=sys.executable)


@pytest.mark.parametrize(
    "error", [PermissionError("denied"), subprocess.TimeoutExpired("ffprobe", 30)]
)
def test_probe_wraps_process_failures(monkeypatch, tmp_path, error):
    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(MediaProbeError):
        probe_media(tmp_path / "demo.mp4", ffprobe=sys.executable)


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        '{"font_size": "big"}',
        '{"alignment": "invalid"}',
        '{"position_x_fraction": NaN}',
        '{"font_color": "bad"}',
    ],
)
def test_invalid_saved_styles_restore_safe_defaults(tmp_path, raw):
    from subdav.app import TITLE_STYLE_SCHEMA_VERSION

    store = PairingStore(tmp_path / "state.sqlite3")
    store.set_setting("title_style_schema_version", TITLE_STYLE_SCHEMA_VERSION)
    store.set_setting("title_style", raw)
    assert resolve_saved_title_style(store) == TitleStyle()


@pytest.mark.parametrize("timestamp", ["00:60:00,000", "00:00:60,000"])
def test_invalid_timestamp_components_are_rejected(tmp_path, timestamp):
    path = tmp_path / "invalid.srt"
    path.write_text(f"1\n{timestamp} --> 02:00:00,000\ndemo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timestamp"):
        parse_srt(path)


def demo_clip(tmp_path, text="Demo"):
    video = tmp_path / "demo.mp4"
    subtitle = tmp_path / "demo.srt"
    info = MediaInfo(video, 10_000, 25, 1, 1920, 1080, True, 1, 2, 48000)
    return TimelineClip(SubtitleEntry(1, 0, 1000, text, subtitle), video, info)


def test_export_preserves_unicode_and_escapes_markup(tmp_path):
    text = "<tag> & \"quotes\" 'single' שלום مرحبا 😀"
    clip = demo_clip(tmp_path, text)
    output = tmp_path / "demo.fcpxml"
    export_fcpxml([clip], output, text, include_titles=True)
    root = ET.parse(output).getroot()
    assert root.find(".//title/text/text-style").text == text
    assert root.find(".//project").attrib["name"] == text
    assert root.find(".//media-rep").attrib["src"] == clip.video_path.as_uri()


@pytest.mark.parametrize("control", ["\x00", "\x01", "\ufffe"])
def test_export_rejects_invalid_xml_without_replacing_existing_file(tmp_path, control):
    output = tmp_path / "existing.fcpxml"
    output.write_text("keep this", encoding="utf-8")
    with pytest.raises(ValueError, match="XML"):
        export_fcpxml([demo_clip(tmp_path, "demo" + control)], output, "Demo", include_titles=True)
    assert output.read_text(encoding="utf-8") == "keep this"


def test_export_cannot_overwrite_source_media(tmp_path):
    clip = demo_clip(tmp_path)
    clip.video_path.write_bytes(b"original media")
    with pytest.raises(ValueError):
        export_fcpxml([clip], clip.video_path, "Demo")
    assert clip.video_path.read_bytes() == b"original media"


def test_sql_like_paths_and_settings_roundtrip_without_schema_damage(tmp_path):
    store = PairingStore(tmp_path / "state.sqlite3")
    subtitle = tmp_path / "quote'; DROP TABLE settings; --.srt"
    video = tmp_path / "video'; DROP TABLE pairings; --.mp4"
    store.set_pair(subtitle, video)
    store.set_setting("'; DROP TABLE settings; --", "quotes '; שלום")
    assert store.get_pair(subtitle) == video.resolve()
    assert store.get_setting("'; DROP TABLE settings; --") == "quotes '; שלום"
    store.set_setting("normal", "still works")
    assert store.get_setting("normal") == "still works"


def test_declining_installer_confirmation_starts_no_process(monkeypatch):
    monkeypatch.setattr("subdav.app.messagebox.askyesno", lambda *args, **kw: False)

    def forbidden():
        pytest.fail("Installer ran without consent")

    monkeypatch.setattr("subdav.app.launch_ffmpeg_installer", forbidden)
    SubtitleDavinciApp.install_ffmpeg(object())


def test_failed_search_invalidates_previous_export_selection(monkeypatch):
    variable = SimpleNamespace(get=lambda: "new query", set=lambda value: None)
    app = SimpleNamespace(
        scan=object(),
        pairs={},
        enabled_subtitles=set(),
        matches=[object()],
        included={0},
        query_var=variable,
        case_var=variable,
        whole_var=variable,
        status_var=variable,
        _refresh_result_tree=lambda: None,
    )

    def fail(*args, **kwargs):
        raise SubtitleReadError("invalid demo subtitle")

    monkeypatch.setattr("subdav.app.search_library", fail)
    monkeypatch.setattr("subdav.app.messagebox.showerror", lambda *args: None)
    SubtitleDavinciApp.do_search(app)
    assert app.matches == []
    assert app.included == set()


def test_subframe_entry_at_end_stays_inside_media(tmp_path):
    clip = demo_clip(tmp_path)
    clip = TimelineClip(
        SubtitleEntry(1, 990, 1000, "Demo", clip.entry.srt_path),
        clip.video_path,
        MediaInfo(clip.video_path, 1000, 25, 1, 1920, 1080, False),
    )
    output = tmp_path / "end.fcpxml"
    export_fcpxml([clip], output, "Demo")
    node = ET.parse(output).find(".//asset-clip")
    assert node.attrib["start"] == "24/25s"
    assert node.attrib["duration"] == "1/25s"


@pytest.mark.parametrize(
    "subtitle,video",
    [
        ("Demo Show S01E01.en.srt", "Demo Show S01E02.mp4"),
        ("Demo Show S01E01.en.srt", "Demo Show S09E24.mp4"),
        ("Demo Story 2049.en.srt", "Demo Story.mp4"),
    ],
)
def test_conflicting_numeric_identifiers_are_not_automatically_paired(tmp_path, subtitle, video):
    from subdav.pairing import suggest_pair

    result = suggest_pair(tmp_path / subtitle, [tmp_path / video])
    assert result.video_path is None


@pytest.mark.parametrize("suffix", [".cmd", ".bat"])
def test_probe_rejects_batch_executables_before_process_launch(monkeypatch, tmp_path, suffix):
    command = tmp_path / ("ffprobe" + suffix)
    command.write_text("@echo off\n", encoding="utf-8")

    def forbidden(*args, **kwargs):
        pytest.fail("Batch executable launched")

    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(MediaProbeError, match="executable"):
        probe_media(tmp_path / "demo.mp4", ffprobe=str(command))


def test_ffprobe_discovery_does_not_use_current_directory(monkeypatch, tmp_path):
    from subdav.media import find_ffprobe

    monkeypatch.chdir(tmp_path)
    (tmp_path / "ffprobe.exe").write_bytes(b"untrusted")
    monkeypatch.setenv("PATH", ".")
    monkeypatch.setattr("subdav.media._common_ffprobe_candidates", lambda: ())
    assert find_ffprobe() is None


def test_store_closes_every_database_connection(monkeypatch, tmp_path):
    original = sqlite3.connect
    connections = []

    def connect(*args, **kwargs):
        con = original(*args, **kwargs)
        connections.append(con)
        return con

    monkeypatch.setattr("subdav.store.sqlite3.connect", connect)
    store = PairingStore(tmp_path / "state.sqlite3")
    store.set_setting("demo", "value")
    assert store.get_setting("demo") == "value"
    for con in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            con.execute("SELECT 1")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_new_store_restricts_local_state_permissions(tmp_path):
    store = PairingStore(tmp_path / "private" / "state.sqlite3")
    assert store.db_path.stat().st_mode & 0o777 == 0o600
    assert store.db_path.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize(
    "fps,duration,start,expected_start,expected_duration",
    [
        ((24, 1), 83, 50, "1/24s", "1/24s"),
        ((24, 1), 42, 0, "0s", "1/24s"),
        ((30000, 1001), 33, 0, "0s", "1001/30000s"),
        ((30000, 1001), 67, 40, "1001/30000s", "1001/30000s"),
    ],
)
def test_duration_rounding_preserves_final_complete_frame(
    tmp_path, fps, duration, start, expected_start, expected_duration
):
    from fractions import Fraction

    clip = demo_clip(tmp_path)
    info = MediaInfo(clip.video_path, duration, fps[0], fps[1], 1920, 1080, False)
    clip = TimelineClip(
        SubtitleEntry(1, start, duration, "Demo", clip.entry.srt_path), clip.video_path, info
    )
    output = tmp_path / "fractional.fcpxml"
    export_fcpxml([clip], output, "Demo")
    root = ET.parse(output)
    node = root.find(".//asset-clip")
    assert node.attrib["start"] == expected_start
    assert node.attrib["duration"] == expected_duration
    asset = root.find(".//resources/asset")
    assert Fraction(asset.attrib["duration"][:-1]) >= (
        Fraction(expected_start[:-1]) + Fraction(expected_duration[:-1])
    )
