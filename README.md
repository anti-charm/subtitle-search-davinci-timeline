# Subtitle Search -> DaVinci Timeline

[![CI](https://github.com/anti-charm/subtitle-search-davinci-timeline/actions/workflows/ci.yml/badge.svg)](https://github.com/anti-charm/subtitle-search-davinci-timeline/actions/workflows/ci.yml)

Find a word or phrase across your local SRT library, select the moments you want,
and assemble them into an editable DaVinci Resolve timeline. Original videos and
subtitles stay in place. No accounts, cloud processing, telemetry, or third-party
Python runtime packages.

**[Download v0.2.2](https://github.com/anti-charm/subtitle-search-davinci-timeline/releases/tag/v0.2.2)**
| [Privacy](PRIVACY.md) | [Security](SECURITY.md) | [Changelog](CHANGELOG.md)

> **Sharing warning:** Exported FCPXML includes absolute media paths, filenames,
> clip timing, and your timeline name/search term. Title exports also include the
> full selected subtitle text. Review exports before sharing them.

## Start on Windows

1. Download `subdav-0.2.2-source.zip` from the release and extract the whole ZIP
   into a writable folder. Keep `src`, `examples`, and the launcher together.
2. Install [Python 3.11 or newer](https://www.python.org/downloads/windows/)
   using its normal Windows installer with Tcl/Tk enabled. Ensure `py` or `python`
   is available. No pip packages are needed to run the app from this ZIP.
3. Double-click **run_subtitle_search.bat**.
4. Choose a library folder, **Scan**, review subtitle/video pairing, and **Search**.
5. Select results, then **Export FCPXML** and choose an export mode.

Windows 10/11 is the primary target. Tkinter is required. Searching and manual
pairing work without FFmpeg; timeline export also needs `ffprobe` from FFmpeg.

In the **FFmpeg / ffprobe** row, use **Auto-detect** or **Locate ffprobe...** to
choose a trusted native executable. On Windows, **Install FFmpeg...** offers an
optional, confirmed WinGet installation of `Gyan.FFmpeg`. This contacts the
WinGet source/package distributor. After installation, click **Auto-detect** again.
Never select executables from untrusted media folders.

## From search to Resolve

1. Place related videos and SRT files under one library folder and click **Scan**.
2. Review the pairing table. Exact and normalized names can pair automatically;
   ambiguous or unresolved files need **Pair selected...**. Always review pairings,
   especially different edits or subtitle timings. Manual overrides are saved locally.
3. Use each **Use** checkbox, **Select all SRT**, or **Clear SRT** to choose which
   subtitle files participate. Enter a word or phrase and click **Search**.
4. Search supports Unicode, including Hebrew and Arabic, with optional **Case
   sensitive** and **Whole word** matching. Results follow subtitle-file/time order.
5. Double-click a result to include/exclude it; **Select all results** and **Clear
   results** affect the current results. A failed scan/search clears old selections.
6. Optional: open **Title style...** to change font, size, face, text color,
   alignment, outline, and horizontal/vertical position. The preview fits the
   exported frame's aspect ratio, scales text/outline with the frame, and preserves
   subtitle line breaks. It accepts multiline demo text or **Use selected result**.
   Type in the font selector to jump to an installed font; names cannot be edited.
   Double-click a position slider to reset only that slider. Settings and
   Light/Dark appearance are remembered.
7. Choose **Video/audio only** or **Video/audio + editable titles** and save XML.
8. In DaVinci Resolve, use **File > Import > Timeline** and choose the FCPXML.
   Confirm source frame-rate/import settings, locate original media if needed,
   and inspect the imported timeline before further editing.

| Export mode | Result |
| --- | --- |
| Video/audio only | Selected source moments in consecutive combined A/V clips |
| Video/audio + editable titles | The same clips plus one editable Basic Title containing each complete subtitle entry |

No video is copied or re-encoded. Each A/V clip uses one shared frame-snapped
source range; audio is never given a separate split-edit range. Connected titles
use the same duration. Subframe entries use at least one complete frame, including
near the end of a source file. The timeline references the original media, so keep
those files available to Resolve.

## Titles and compatibility

Default title styling uses Arial Regular, 48 pt, white text, centered at a lower
subtitle position, with a black outline of width **1**. Width **0** disables the
outline. Existing saved styles keep their explicit settings; **Reset to default**
loads the new defaults. Font availability and title rendering depend on your
machine and Resolve version. Titles remain editable rather than burned into media.

Outlines were confirmed visible in user tests in Resolve 21. The preview no
longer exaggerates them by multiplying their width. Bold/italic exports include
both the named face and explicit FCPXML traits. Resolve may substitute unavailable
faces; decorative families sometimes provide only a Regular face. Verify import
using a family that includes the selected face.

The frame dimensions come from the first included result, matching the exported
sequence. If media dimensions cannot be read or nothing is included, the editor
clearly labels its 1920 × 1080 reference frame. Changing the timeline resolution
in Resolve can change the result. The preview is a frame-scaled estimate, not
Resolve's renderer: font metrics, outline rasterization, alignment and
right-to-left shaping may differ. It preserves explicit line breaks and clips
overflow at the frame edges rather than introducing extra wrapped lines.

This is a pre-1.0 tool. Automated tests verify XML structure, escaping, timings,
and local behavior; they do not substitute for a native Resolve import test.
The release audit did not perform a fresh Resolve acceptance test. Prefer source
media with consistent frame rates and verify mixed-rate compilations in Resolve.

## Pairing and supported files

Both tables support column sorting: click a heading once to sort, and again to
reverse it. **Pairing** puts `unresolved`, then `ambiguous`, rows first, followed
by normalized, exact and manual pairs. Time columns sort numerically. Sorting
keeps SRT/result checkboxes and the selected row attached to the same item;
it changes the display order and preserves the existing timeline export order.

### Downloaded clips

For a downloader that creates `Example_match_001.srt` +
`Example_match_001.mp4`, select its **clips output folder** (or a common parent
containing both originals and clips), enable **Downloaded clips only**, and
press **Scan / Refresh**. This mode searches only `_match_NNN.srt` files and
leaves the original full-length SRTs out of the results. A source with five
extracted occurrences becomes five independent SRT/video pairs. The clip's
filename, subtitle text and local timestamps remain available in the results
and exported timeline.

The originals folder can be a sibling of the clips folder. Scanning the originals
folder alone cannot discover files in its sibling: select the clips folder or
their common parent. Refresh after downloads finish; folder changes are not
watched automatically. Newly generated pairs appear without restarting the app.

Automatic pairing of extracted clips requires an exact basename. A missing
video stays unresolved; an orphan video is never substituted for another hit.
Duplicate basenames prefer an exact video in the SRT's directory; otherwise
multiple candidates remain ambiguous for manual review. Manual pairing remains
available. Use the clip's SRT with timestamps relative to that clip, not the
original SRT's long-video timestamps. The exporter rejects ranges past the end
of the chosen video and references media without modifying or re-encoding it.

### Ordinary subtitle libraries

Matching tries exact basenames, normalized names, conservative similarity, then
manual resolution. Known language/release metadata can be removed, but numeric
episode/title conflicts are rejected before fuzzy matching. Several plausible
candidates remain ambiguous. Identical names do not prove identical media edits.

Supported video extensions: `.mp4`, `.mkv`, `.mov`, `.avi`, `.m4v`, `.webm`, `.mpg`,
`.mpeg`, `.mts`, `.m2ts`. Inputs must have usable positive video duration, frame
rate and dimensions. SRT accepts UTF-8/BOM and common legacy Latin, Hebrew and
Arabic encodings; encoding detection is heuristic. Invalid files produce local
errors. The included [sample.srt](examples/sample.srt) is invented demo content;
no media is included.

## Privacy and local state

Manual pairing paths, the ffprobe path, theme, and title style are stored at
`%LOCALAPPDATA%\SubtitleDavinci\pairings.sqlite3` on Windows or
`~/.subdav/pairings.sqlite3` elsewhere. This database is not encrypted and contains
no media/subtitle contents. Close the app and delete the database/sidecars to reset.
See [PRIVACY.md](PRIVACY.md) for the fallback location and backup considerations.

FFprobe runs without a shell, using a file-only protocol allowlist and a timeout.
The app has no upload or telemetry code. Network shares and external tools remain
OS trust boundaries; use local disks and firewall controls for strict isolation.
Keep exports, databases, diagnostics and personal screenshots out of public issues.

## Troubleshooting

| Problem | Try this |
| --- | --- |
| Launcher cannot find Python | Install Python 3.11+ with Tcl/Tk, then reopen the launcher |
| Tkinter is missing | Repair the official Python installation and enable Tcl/Tk |
| FFprobe is missing | Auto-detect, locate a trusted executable, or confirm the optional installer |
| Pairing is unresolved | Check the scanned folder, refresh after downloads, click Pairing to bring problem rows first, then pair manually if needed |
| Originals show instead of downloaded clips | Select the clips output folder or common parent and enable Downloaded clips only |
| Subtitle parsing fails | Repair its index/timestamp/encoding; timestamps use minutes/seconds below 60 |
| Export fails or times out | Check file access and valid metadata; use local media and an updated ffprobe |
| Resolve cannot locate media | Restore the original paths or relink media during import |
| Titles differ from preview | Check installed fonts and adjust native titles in Resolve |

From Command Prompt in the extracted folder, run:

```bat
set PYTHONPATH=%CD%\src
python -m subdav --check
```

This prints Python/Tkinter availability and the detected ffprobe path. Redact that
path before sharing output. Linux/macOS users can install the release wheel into
Python 3.11+ with Tkinter and launch `python -m subdav`; native GUI acceptance is
focused on Windows, with core tests also running on Linux.

## Development and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and checks. Development dependencies
are separate from the dependency-free application. CI covers Windows Python 3.11,
3.12 and 3.14, plus Linux Python 3.12, with tests, formatting, security, privacy,
packaging and an installed-wheel check. Release ZIPs use a reviewed file allowlist.

[MIT license](LICENSE). Copyright 2026 anti-charm. Independent utility; DaVinci
Resolve and FFmpeg belong to their respective owners. This project is not
endorsed by Blackmagic Design. Related local utility: [MPR Collector](https://github.com/anti-charm/mpr-collector).
