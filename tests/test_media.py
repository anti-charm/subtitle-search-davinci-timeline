import json
import subprocess
import sys
from pathlib import Path

import pytest

from subdav.media import MediaProbeError, probe_media


def fake_payload(rate: str, *, duration="12.345", audio=True):
    streams = [
        {
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "avg_frame_rate": rate,
            "r_frame_rate": rate,
        },
    ]
    if audio:
        streams.append({"codec_type": "audio", "channels": 2, "sample_rate": "48000"})
    return {"streams": streams, "format": {"duration": duration}}


@pytest.mark.parametrize(
    "rate,expected",
    [("24/1", (24, 1)), ("25/1", (25, 1)), ("30000/1001", (30000, 1001)), ("60/1", (60, 1))],
)
def test_probe_media_parses_rational_frame_rates(monkeypatch, tmp_path: Path, rate, expected):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"")

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args[0], 0, stdout=json.dumps(fake_payload(rate)), stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    info = probe_media(path, ffprobe=sys.executable)

    assert (info.fps_num, info.fps_den) == expected
    assert info.duration_ms == 12_345
    assert (info.width, info.height) == (1920, 1080)
    assert info.has_audio is True
    assert info.audio_sources == 1
    assert info.audio_channels == 2
    assert info.audio_rate == 48_000
    assert info.path == path


def test_probe_media_reports_missing_ffprobe(monkeypatch, tmp_path: Path):
    path = tmp_path / "video.mp4"

    def missing(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(MediaProbeError, match="ffprobe"):
        probe_media(path, ffprobe=sys.executable)


def test_probe_media_reports_ffprobe_failure(monkeypatch, tmp_path: Path):
    path = tmp_path / "video.mp4"

    def failed(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout="", stderr="bad file")

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(MediaProbeError, match="bad file"):
        probe_media(path, ffprobe=sys.executable)


def test_probe_media_rejects_missing_video_stream(monkeypatch, tmp_path: Path):
    path = tmp_path / "audio.mp4"

    def fake_run(*args, **kwargs):
        payload = {"streams": [{"codec_type": "audio"}], "format": {"duration": "2.0"}}
        return subprocess.CompletedProcess(args[0], 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(MediaProbeError, match="video stream"):
        probe_media(path, ffprobe=sys.executable)


def test_find_ffprobe_prefers_saved_override(monkeypatch, tmp_path: Path):
    from subdav.media import find_ffprobe

    saved = tmp_path / "ffprobe.exe"
    saved.write_bytes(b"")
    monkeypatch.setattr("subdav.media._find_native_on_path", lambda _name: None)

    assert find_ffprobe(saved) == saved.resolve()


def test_find_ffprobe_discovers_common_windows_candidate(monkeypatch, tmp_path: Path):
    from subdav.media import find_ffprobe

    candidate = tmp_path / "Microsoft" / "WinGet" / "Links" / "ffprobe.exe"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"")
    monkeypatch.setattr("subdav.media._find_native_on_path", lambda _name: None)
    monkeypatch.setattr("subdav.media._common_ffprobe_candidates", lambda: (candidate,))

    assert find_ffprobe() == candidate.resolve()


def test_winget_ffmpeg_install_command_uses_current_package_id():
    from subdav.media import winget_ffmpeg_install_command

    assert winget_ffmpeg_install_command() == [
        "winget",
        "install",
        "--id",
        "Gyan.FFmpeg",
        "--exact",
        "--source",
        "winget",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]


def test_launch_ffmpeg_installer_requires_winget(monkeypatch):
    from subdav.media import launch_ffmpeg_installer

    monkeypatch.setattr("subdav.media._find_native_on_path", lambda _name: None)
    with pytest.raises(MediaProbeError, match="winget"):
        launch_ffmpeg_installer()


def test_launch_ffmpeg_installer_starts_verified_winget_package(monkeypatch):
    from subdav.media import launch_ffmpeg_installer, winget_ffmpeg_install_command

    calls = []
    monkeypatch.setattr(
        "subdav.media._find_native_on_path",
        lambda name: r"C:\\Windows\\winget.exe" if name == "winget" else None,
    )
    monkeypatch.setattr(
        "subdav.media.subprocess.Popen", lambda cmd, **kwargs: calls.append((cmd, kwargs))
    )

    launch_ffmpeg_installer()

    assert calls[0][0] == [
        str(Path(r"C:\\Windows\\winget.exe").resolve()),
        *winget_ffmpeg_install_command()[1:],
    ]
    assert calls[0][1]["shell"] is False
