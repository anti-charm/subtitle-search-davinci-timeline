from pathlib import Path

from subdav.srt import parse_srt

ROOT = Path(__file__).resolve().parents[1]


def test_distribution_files_and_sample_exist():
    assert (ROOT / "README.md").is_file()
    assert (ROOT / "run_subtitle_search.bat").is_file()
    assert (ROOT / "examples" / "README.md").is_file()
    assert (ROOT / "examples" / "sample.srt").is_file()


def test_sample_srt_demonstrates_exact_timestamp_example():
    entries = parse_srt(ROOT / "examples" / "sample.srt")
    assert entries[0].start_ms == 91_000
    assert entries[0].end_ms == 105_000
    assert "dust" in entries[0].text.casefold()


def test_windows_launcher_runs_src_layout_without_installing_package():
    text = (ROOT / "run_subtitle_search.bat").read_text(encoding="utf-8")
    assert "PYTHONPATH" in text
    assert "-m subdav" in text
