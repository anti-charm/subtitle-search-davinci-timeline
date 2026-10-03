# Example subtitle

`sample.srt` demonstrates the core exact-timestamp rule.

Searching for `dust` finds the first subtitle entry:

- Start: `00:01:31.000`
- End: `00:01:45.000`

The exported source clip uses those same subtitle boundaries with no added padding.

To test automatic pairing, place a real video named `sample.mp4` next to `sample.srt`. The video must be long enough to contain the subtitle timestamp range. A dummy file is not included because timeline export requires valid media metadata from `ffprobe`.
