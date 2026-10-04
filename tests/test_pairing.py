from pathlib import Path

from subdav.library import scan_library
from subdav.pairing import normalize_media_stem, suggest_pair


def test_scan_library_finds_subtitles_and_common_video_types(tmp_path: Path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "Episode01.srt").write_text("", encoding="utf-8")
    (tmp_path / "Episode01.mp4").write_bytes(b"")
    (tmp_path / "other.mkv").write_bytes(b"")
    (tmp_path / "ignore.txt").write_text("x", encoding="utf-8")

    scan = scan_library(tmp_path)

    assert [p.name for p in scan.subtitles] == ["Episode01.srt"]
    assert [p.name for p in scan.videos] == ["Episode01.mp4", "other.mkv"]


def test_exact_basename_pairing_wins(tmp_path: Path):
    srt = tmp_path / "Episode01.srt"
    exact = tmp_path / "Episode01.mp4"
    other = tmp_path / "Episode01.1080p.WEBRip.mkv"

    result = suggest_pair(srt, [other, exact])

    assert result.status == "exact"
    assert result.video_path == exact


def test_normalized_pairing_ignores_language_resolution_and_release_tags(tmp_path: Path):
    srt = tmp_path / "Doctor.Who.S05E03.en.srt"
    video = tmp_path / "Doctor Who S05E03 1080p BluRay x264.mkv"

    assert normalize_media_stem(srt.stem) == "doctor who s05e03"
    assert normalize_media_stem(video.stem) == "doctor who s05e03"

    result = suggest_pair(srt, [video])
    assert result.status == "normalized"
    assert result.video_path == video


def test_unrelated_names_are_unresolved(tmp_path: Path):
    srt = tmp_path / "Episode01.srt"
    video = tmp_path / "TotallyDifferentMovie.mp4"

    result = suggest_pair(srt, [video])

    assert result.status == "unresolved"
    assert result.video_path is None


def test_two_equally_plausible_candidates_are_ambiguous_and_not_selected(tmp_path: Path):
    srt = tmp_path / "Show.S01E01.en.srt"
    first = tmp_path / "Show.S01E01.1080p.WEBRip.mp4"
    second = tmp_path / "Show.S01E01.720p.BluRay.mkv"

    result = suggest_pair(srt, [first, second])

    assert result.status == "ambiguous"
    assert result.video_path is None
    assert set(result.candidates) == {first, second}


def test_same_folder_candidate_beats_similar_name_in_other_folder(tmp_path: Path):
    season = tmp_path / "Season 1"
    other = tmp_path / "Other"
    season.mkdir()
    other.mkdir()
    srt = season / "Show S01E02 commentary.srt"
    nearby = season / "Show S01E02.mp4"
    far = other / "Show S01E02.mp4"

    result = suggest_pair(srt, [far, nearby])

    assert result.status in {"normalized", "candidate"}
    assert result.video_path == nearby


def test_movie_pairing_ignores_subtitle_language_year_and_release_group(tmp_path: Path):
    english = tmp_path / "The Help - English.srt"
    hebrew = tmp_path / "The Help - Hebrew.srt"
    video = tmp_path / "The.Help.2011.720p.BrRip.x264.YIFY.mp4"

    assert normalize_media_stem(english.stem) == "the help"
    assert normalize_media_stem(hebrew.stem) == "the help"
    assert normalize_media_stem(video.stem) == "the help"
    assert suggest_pair(english, [video]).video_path == video
    assert suggest_pair(hebrew, [video]).video_path == video


def test_movie_title_that_is_only_a_year_is_not_erased():
    assert normalize_media_stem("1917") == "1917"


def test_downloaded_clip_requires_its_exact_video_not_a_similar_clip(tmp_path):
    srt = tmp_path / "Example show_match_001.srt"
    similar = tmp_path / "Example show_1080p_match_001.mp4"

    result = suggest_pair(srt, [similar])

    assert result.status == "unresolved"
    assert result.video_path is None


def test_downloaded_clip_duplicate_names_prefer_own_folder_or_stay_ambiguous(tmp_path):
    srt = tmp_path / "clips" / "Example_match_001.srt"
    local = srt.with_suffix(".mp4")
    other = tmp_path / "other" / local.name
    third = tmp_path / "third" / local.name

    assert suggest_pair(srt, [other, local]).video_path == local
    result = suggest_pair(srt, [other, third])
    assert result.status == "ambiguous"
    assert result.video_path is None


def test_clip_scan_excludes_originals_and_rescans_new_outputs(tmp_path):
    original = tmp_path / "Example.en-orig.srt"
    original.write_text("", encoding="utf-8")
    clips = tmp_path / "clips"
    clips.mkdir()
    first = clips / "Example_match_001.srt"
    first.write_text("", encoding="utf-8")
    first.with_suffix(".MP4").write_bytes(b"")
    # An orphan video must not be substituted for the missing second video.
    (clips / "Example_match_003.mp4").write_bytes(b"")
    missing = clips / "Example_match_002.srt"
    missing.write_text("", encoding="utf-8")

    scan = scan_library(tmp_path, downloaded_clips_only=True)
    assert [p.name for p in scan.subtitles] == ["Example_match_001.srt", "Example_match_002.srt"]
    assert suggest_pair(first, scan.videos).status == "exact"
    assert suggest_pair(missing, scan.videos).status == "unresolved"

    late = clips / "Example_match_003.srt"
    late.write_text("", encoding="utf-8")
    assert late not in scan.subtitles
    refreshed = scan_library(tmp_path, downloaded_clips_only=True)
    assert late in refreshed.subtitles
    assert suggest_pair(late, refreshed.videos).status == "exact"
    assert original in scan_library(tmp_path).subtitles
