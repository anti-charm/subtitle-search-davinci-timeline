from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

_LANGUAGE_TOKENS = {
    "en",
    "eng",
    "english",
    "he",
    "heb",
    "hebrew",
    "ar",
    "ara",
    "arabic",
    "fr",
    "fre",
    "french",
    "de",
    "ger",
    "german",
    "es",
    "spa",
    "spanish",
    "it",
    "ita",
    "italian",
    "pt",
    "por",
    "ru",
    "rus",
    "ja",
    "jpn",
    "ko",
    "kor",
}
_RELEASE_TOKENS = {
    "webrip",
    "webdl",
    "web",
    "bluray",
    "brrip",
    "hdrip",
    "dvdrip",
    "remux",
    "x264",
    "x265",
    "h264",
    "h265",
    "hevc",
    "avc",
    "aac",
    "dts",
    "proper",
    "repack",
    "hdr",
    "sdr",
    "10bit",
    "8bit",
    "nf",
    "amzn",
    "dsnp",
    "hmax",
    "yify",
    "yts",
}
_RESOLUTION_RE = re.compile(r"^(?:\d{3,4}p|\d{3,4}x\d{3,4}|4k|uhd)$", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(?:19\d{2}|20\d{2})$")
_SEPARATOR_RE = re.compile(r"[._\-\[\](){}]+")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class PairSuggestion:
    status: str
    video_path: Path | None
    candidates: tuple[Path, ...] = ()


def normalize_media_stem(name: str) -> str:
    text = _SEPARATOR_RE.sub(" ", name).casefold().strip()
    tokens = [tok for tok in _SPACE_RE.split(text) if tok]
    while tokens and tokens[-1] in _LANGUAGE_TOKENS:
        tokens.pop()
    filtered: list[str] = []
    for index, tok in enumerate(tokens):
        if tok in _RELEASE_TOKENS or _RESOLUTION_RE.match(tok):
            continue
        # Treat a 4-digit number as a release year only when later tokens
        # clearly look like release metadata. This keeps movie titles such
        # as "1917" and "Blade Runner 2049" intact.
        later = tokens[index + 1 :]
        if (
            index > 0
            and _YEAR_RE.match(tok)
            and any(item in _RELEASE_TOKENS or _RESOLUTION_RE.match(item) for item in later)
        ):
            continue
        filtered.append(tok)
    return " ".join(filtered)


def _same_parent(a: Path, b: Path) -> bool:
    try:
        return a.parent.resolve() == b.parent.resolve()
    except OSError:
        return a.parent == b.parent


def _candidate_score(srt_path: Path, video_path: Path) -> float:
    left = normalize_media_stem(srt_path.stem)
    right = normalize_media_stem(video_path.stem)
    if not left or not right:
        return 0.0
    # Episode numbers and numeric title identifiers must agree before fuzzy
    # similarity may accept a pairing. Metadata numbers were removed above.
    if tuple(map(int, re.findall(r"\d+", left))) != tuple(map(int, re.findall(r"\d+", right))):
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    parent_bonus = 0.08 if _same_parent(srt_path, video_path) else 0.0
    return min(1.0, 0.55 * ratio + 0.37 * overlap + parent_bonus)


def suggest_pair(srt_path: Path, videos: Sequence[Path]) -> PairSuggestion:
    srt_path = Path(srt_path)
    videos = tuple(Path(v) for v in videos)

    exact = [v for v in videos if v.stem.casefold() == srt_path.stem.casefold()]
    if len(exact) == 1:
        return PairSuggestion("exact", exact[0], tuple(exact))
    if len(exact) > 1:
        same_dir = [v for v in exact if _same_parent(srt_path, v)]
        if len(same_dir) == 1:
            return PairSuggestion("exact", same_dir[0], tuple(exact))
        return PairSuggestion("ambiguous", None, tuple(exact))

    target = normalize_media_stem(srt_path.stem)
    normalized = [v for v in videos if normalize_media_stem(v.stem) == target and target]
    if len(normalized) == 1:
        return PairSuggestion("normalized", normalized[0], tuple(normalized))
    if len(normalized) > 1:
        same_dir = [v for v in normalized if _same_parent(srt_path, v)]
        if len(same_dir) == 1:
            return PairSuggestion("normalized", same_dir[0], tuple(normalized))
        return PairSuggestion("ambiguous", None, tuple(normalized))

    scored = sorted(
        ((_candidate_score(srt_path, video), video) for video in videos),
        key=lambda item: (-item[0], str(item[1]).casefold()),
    )
    if not scored or scored[0][0] < 0.80:
        return PairSuggestion("unresolved", None, ())

    best_score = scored[0][0]
    plausible = tuple(
        video for score, video in scored if score >= 0.80 and best_score - score <= 0.04
    )
    if len(plausible) > 1:
        same_dir = [v for v in plausible if _same_parent(srt_path, v)]
        if len(same_dir) == 1 and _candidate_score(srt_path, same_dir[0]) > max(
            (_candidate_score(srt_path, v) for v in plausible if v != same_dir[0]), default=0.0
        ):
            return PairSuggestion("normalized", same_dir[0], plausible)
        return PairSuggestion("ambiguous", None, plausible)

    return PairSuggestion("normalized", plausible[0], plausible)
