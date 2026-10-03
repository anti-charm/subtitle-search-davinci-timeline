# Changelog

## Unreleased

- Run each Windows GUI test in a fresh process to isolate Tcl/Tk startup state.
  Preserve all GUI assertions and report child-process failures to CI.

## 0.2.1 - 2026-10-03

- Scale the title preview to the exported timeline frame and its aspect ratio.
  Remove arbitrary font-size limits, desktop-DPI scaling, automatic wrapping,
  position clamping and exaggerated outline thickness. Clip overflowing titles
  at the frame edges, including letterboxed portrait previews.
- Use a multiline preview-text editor and keep subtitle line breaks intact.
- Make the font selector selection-only; typing jumps to installed font families.
- Export explicit bold/italic traits alongside the font-face name.
- Change the default outline width to 1; preserve existing saved styles.
  Keep outlines following user confirmation that they import in Resolve 21.
- Apply title transforms using timeline dimensions for mixed-resolution media.
- Add regression checks for preview geometry, font picking and exported traits.

Resolve's native renderer was not available for this update's automated checks.
The preview is an estimate; verify typography in Resolve after import.

## 0.2.0 - 2026-10-03

First public release, prepared from the supplied 0.1.6 source.

- Harden ffprobe execution: native executable discovery, literal path arguments,
  no shell, local-file protocol restriction, timeout, and metadata validation.
- Reject invalid saved styles and SRT timestamp components.
- Protect original media/subtitles from export overwrite; validate and atomically
  write XML. Preserve Unicode and the shared video/audio frame range.
- Keep short clips at the end of a video inside its available complete frames.
- Clear stale selections after failed searches/scans and reject conflicting
  numeric title/episode identifiers in fuzzy pairing.
- Close SQLite connections and restrict POSIX database permissions.
- Add export privacy reminders, a privacy policy, a security policy, contribution
  guidance, MIT licensing, CI, and allowlisted reproducible release packaging.
- Clarify that title outline/stroke styling is experimental for Resolve FCPXML
  import and must be verified in your Resolve version.

## Development baseline: 0.1.2-0.1.6

The supplied source and README describe development milestones:

- 0.1.2: library/event/project XML structure and Resolve import compatibility fixes.
- 0.1.3: clips-only and editable-title modes plus persistent styling and themes.
- 0.1.4: per-subtitle selection, improved preview, and title placement changes.
- 0.1.5: shared frame-snapped video/audio ranges, audio metadata, and X/Y position.
- 0.1.6: Light/Dark themes only and individual position-slider resets.

These are development notes, not claims that earlier GitHub releases existed.
Native Resolve import acceptance was reported in the supplied handoff; it is
separate from the automated checks performed for this public release.
