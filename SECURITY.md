# Security

## Supported versions

Security fixes target the latest `0.2.x` release. This is a pre-1.0 utility;
compatibility and Resolve import behavior may evolve. Update Python, FFmpeg,
and DaVinci Resolve through their official channels.

## Report privately

Use GitHub's **Security > Report a vulnerability** private reporting feature for
this repository when it is available. Do not open a public issue containing a
working exploit, credentials, private paths, subtitles, or media. If private
reporting is unavailable, open only a generic issue asking the maintainer to
provide a private reporting channel; keep sensitive details out of that issue.
No personal email address is required or published by this project.

## What the app protects

- Subprocesses use argument lists, `shell=False`, native executables, and resolved
  paths. Automatic PATH discovery skips relative/current-directory entries.
- Media probing allows FFmpeg's `file` protocol only, requests only the metadata
  needed for export, has a timeout, and validates the returned data.
- SQLite queries use bound parameters and connections close after each operation.
- Export uses XML serialization, rejects illegal XML characters, protects source
  files from overwrite, and replaces a completed temporary output atomically.
- A failed search/scan invalidates earlier results. Numeric episode/title conflicts
  are rejected before fuzzy pairing.
- Repository and release tooling use an explicit public-file allowlist and scan
  for known local paths/email strings and common credential formats. Git author
  and committer identities are checked separately before publication.

These checks reduce specific risks. They do not constitute a sandbox, encryption,
an independent penetration test, or a guarantee that every hostile file is safe.

## Trust boundaries

Python, Tkinter, FFmpeg, WinGet, Resolve, the OS, and any chosen executable must
be trustworthy. A renamed malicious `.exe` remains executable; the app does not
verify digital signatures. Do not select tools from untrusted media folders.
Malformed media is processed by FFmpeg, so keep it updated and use an OS sandbox
for untrusted files. Huge libraries/files can still consume memory or keep the
interface busy. File-only protocols do not prevent OS network-share access.

Local databases and exported XML are not encrypted. Access by other accounts,
malware, backups, cloud sync, or screen capture is outside the application's
protection. See [PRIVACY.md](PRIVACY.md) for exact local data and export contents.

## Development checks

CI runs tests, Ruff, Bandit, dependency vulnerability checks, packaging, and a
wheel smoke check. Actions are pinned to reviewed commit SHAs and run with
read-only repository permission. Pull requests do not receive publishing secrets.
Bandit suppressions are limited to reviewed boundaries: building XML rather
than parsing supplied XML, and explicit subprocess calls without a shell.
