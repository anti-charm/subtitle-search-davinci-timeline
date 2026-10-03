# Privacy

Subtitle Search runs on your computer. It has no account, telemetry, analytics,
crash upload, cloud service, AI service, remote logging, or automatic update check.
There are no third-party Python runtime dependencies. Your media and subtitles
are not uploaded by the application.

## Local data

The app reads subtitle files under the library folder you choose. It finds video
filenames there and probes selected videos locally with your installed `ffprobe`
when you export. Original media and subtitles are not modified or copied into
the app's settings directory.

A SQLite database stores:

- Absolute subtitle/video paths for manual pairing overrides.
- The saved path to the ffprobe executable.
- Light/Dark theme and title-style preferences, plus the style schema version.

It does not store subtitle contents, video/audio contents, search history, or
exported timelines. Search results and preview text remain in memory while the
app is running. These items can still be visible on your screen or in OS memory.

The database is at `%LOCALAPPDATA%\SubtitleDavinci\pairings.sqlite3` on Windows
(the user home directory is the fallback if LOCALAPPDATA is unavailable), or
`~/.subdav/pairings.sqlite3` on other systems. It is not encrypted. Windows uses
the directory's inherited permissions. On POSIX, a newly created settings folder
uses owner-only access and the database uses mode `0600`.

To erase saved state, close the app and delete `pairings.sqlite3` and any SQLite
sidecar files alongside it. The next launch creates fresh defaults. OS backups,
cloud-synced folders, and snapshots may retain older copies.

## Exported timelines disclose information

**Every exported FCPXML contains absolute `file://` media paths, media filenames,
clip timing, and the timeline name (normally your search term). Exports with
editable titles also contain the complete selected subtitle entries.** Clips-only
exports do not include subtitle entry text, but their paths and names are still
sensitive. The export dialog and completion message remind you of this.

The export is a plain XML file saved where you choose. Review it before sending
it to anyone, posting an issue, or publishing it. Keep exports and the pairing
database out of public repositories. Sharing a redacted timeline may prevent
Resolve from finding the original media. The application does not upload exports.

## External tools and filesystem access

FFprobe is launched without a shell, with a local-file protocol allowlist and a
30-second timeout. HTTP and other FFmpeg network protocols are blocked. This is
not an operating-system network sandbox: UNC paths, mounted network drives,
filesystem links, and external tools can still involve OS/network activity.
For an offline workflow use trusted files on a local disk, a trusted updated
ffprobe executable, and OS firewall controls if strict network isolation is needed.

**Install FFmpeg...** is optional and runs only after you click it and confirm.
WinGet contacts its configured source and the package distributor, downloads
software, and uses its own logs and installation behavior. Installing Python,
development tools, and downloading GitHub releases also use their normal services.

## Safe support reports

Use invented filenames and short synthetic subtitles. Do not attach real media,
your database, unredacted exports, or screenshots of personal folder names.
`python -m subdav --check` prints the detected ffprobe path; redact it before
sharing. Read [SECURITY.md](SECURITY.md) for private vulnerability reporting.
