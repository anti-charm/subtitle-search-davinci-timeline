from __future__ import annotations

import json
import math
import os

# Trusted local tools are launched with literal arguments and no shell.
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


def _native_executable(path: Path) -> bool:
    suffix = path.suffix.casefold()
    return (
        path.is_file() and suffix not in {".bat", ".cmd"} and (os.name != "nt" or suffix == ".exe")
    )


def _find_native_on_path(tool: str) -> Path | None:
    """Search explicit absolute PATH directories, never the working directory."""
    name = tool + ".exe" if os.name == "nt" else tool
    working_directory = Path.cwd().resolve()
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        base = Path(directory.strip('"'))
        if not base.is_absolute() or base.resolve() == working_directory:
            continue
        candidate = base / name
        if _native_executable(candidate):
            return candidate.resolve()
    return None


def _common_ffprobe_candidates() -> tuple[Path, ...]:
    """Return likely ffprobe locations that do not depend on PATH."""
    if os.name != "nt":
        return ()

    candidates: list[Path] = []
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates.append(local / "Microsoft" / "WinGet" / "Links" / "ffprobe.exe")
    candidates.append(Path.home() / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffprobe.exe")
    candidates.append(Path(r"C:\ffmpeg\bin\ffprobe.exe"))
    candidates.append(Path(r"C:\ProgramData\chocolatey\bin\ffprobe.exe"))

    packages = local / "Microsoft" / "WinGet" / "Packages"
    if packages.exists():
        for package in packages.glob("Gyan.FFmpeg*"):
            candidates.extend(package.glob("**/bin/ffprobe.exe"))

    # Also support a portable copy placed beside the Python executable/app.
    candidates.append(Path(sys.executable).resolve().parent / "ffprobe.exe")
    return tuple(candidates)


def find_ffprobe(configured: Path | str | None = None) -> Path | None:
    """Find ffprobe from a saved override, PATH, or common Windows installs."""
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute() and _native_executable(candidate):
            return candidate.resolve()

    on_path = _find_native_on_path("ffprobe")
    if on_path:
        return Path(on_path).resolve()

    for candidate in _common_ffprobe_candidates():
        if _native_executable(candidate):
            return candidate.resolve()
    return None


def winget_ffmpeg_install_command() -> list[str]:
    """Command used by the Windows GUI for an explicit one-click install."""
    return [
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


def launch_ffmpeg_installer() -> None:
    """Launch the verified WinGet FFmpeg package after an explicit GUI action."""
    installer = _find_native_on_path("winget")
    if installer is None:
        raise MediaProbeError(
            "Windows Package Manager (winget) was not found. Use 'Locate ffprobe...' "
            "if FFmpeg is already installed, or install FFmpeg from ffmpeg.org."
        )
    kwargs: dict[str, int] = {}
    if os.name == "nt" and hasattr(subprocess, "CREATE_NEW_CONSOLE"):
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    command = [str(Path(installer).resolve()), *winget_ffmpeg_install_command()[1:]]
    # Fixed package/source arguments; executable is resolved before launch.
    subprocess.Popen(command, shell=False, **kwargs)  # nosec B603


class MediaProbeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaInfo:
    path: Path
    duration_ms: int
    fps_num: int
    fps_den: int
    width: int
    height: int
    has_audio: bool
    audio_sources: int = 0
    audio_channels: int = 0
    audio_rate: int = 0


def _parse_rate(video_stream: dict) -> tuple[int, int]:
    for key in ("avg_frame_rate", "r_frame_rate"):
        raw = str(video_stream.get(key, "0/0"))
        try:
            rate = Fraction(raw)
        except (ValueError, ZeroDivisionError):
            continue
        if rate > 0:
            return rate.numerator, rate.denominator
    raise MediaProbeError("ffprobe did not report a valid video frame rate")


def probe_media(path: Path, ffprobe: str = "ffprobe") -> MediaInfo:
    executable = (
        find_ffprobe()
        if ffprobe in {"ffprobe", "ffprobe.exe"}
        else Path(ffprobe).expanduser().resolve()
    )
    if executable is None or not _native_executable(executable):
        raise MediaProbeError(
            "A trusted native ffprobe executable is required; batch files are not supported"
        )
    path = Path(path).expanduser().resolve()
    cmd = [
        str(executable),
        "-v",
        "error",
        "-protocol_whitelist",
        "file",
        "-show_entries",
        "stream=codec_type,width,height,avg_frame_rate,r_frame_rate,channels,sample_rate:format=duration",
        "-of",
        "json",
        "-i",
        str(path),
    ]
    try:
        # Filenames remain single literal arguments; remote protocols are blocked.
        completed = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            shell=False,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise MediaProbeError(
            "ffprobe was not found. Install FFmpeg/ffprobe to export timelines; "
            "subtitle searching and manual pairing still work without it."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(
            "ffprobe timed out after 30 seconds; check the selected media"
        ) from exc
    except OSError as exc:
        raise MediaProbeError(f"Could not run ffprobe: {exc}") from exc

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown ffprobe error"
        raise MediaProbeError(f"ffprobe failed for {path}: {detail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(f"ffprobe returned invalid JSON for {path}") from exc

    if not isinstance(payload, dict):
        raise MediaProbeError("ffprobe returned invalid metadata structure")
    streams = payload.get("streams", [])
    metadata = payload.get("format", {})
    if (
        not isinstance(streams, list)
        or not all(isinstance(s, dict) for s in streams)
        or not isinstance(metadata, dict)
    ):
        raise MediaProbeError("ffprobe returned invalid metadata structure")
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    if video is None:
        raise MediaProbeError(f"No video stream found in {path}")

    try:
        duration_s = float(metadata.get("duration"))
        if not math.isfinite(duration_s) or duration_s <= 0:
            raise ValueError("duration must be positive and finite")
    except (TypeError, ValueError) as exc:
        raise MediaProbeError(f"ffprobe did not report a valid duration for {path}") from exc

    fps_num, fps_den = _parse_rate(video)
    try:
        width, height = int(video.get("width")), int(video.get("height"))
        if width <= 0 or height <= 0:
            raise ValueError("dimensions must be positive")
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("ffprobe did not report valid video dimensions") from exc
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    try:
        channel_counts = [int(stream.get("channels") or 0) for stream in audio_streams]
        if any(count < 0 for count in channel_counts):
            raise ValueError("negative channel count")
        audio_channels = sum(channel_counts)
    except (TypeError, ValueError) as exc:
        raise MediaProbeError("ffprobe reported invalid audio channels") from exc
    audio_rate = 0
    for stream in audio_streams:
        try:
            candidate_rate = int(stream.get("sample_rate") or 0)
        except (TypeError, ValueError):
            candidate_rate = 0
        if candidate_rate > 0:
            audio_rate = candidate_rate
            break
    return MediaInfo(
        path=path,
        duration_ms=round(duration_s * 1000),
        fps_num=fps_num,
        fps_den=fps_den,
        width=width,
        height=height,
        has_audio=bool(audio_streams),
        audio_sources=len(audio_streams),
        audio_channels=audio_channels,
        audio_rate=audio_rate,
    )
