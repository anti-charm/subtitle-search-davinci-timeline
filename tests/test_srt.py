from pathlib import Path

from subdav.srt import parse_srt, search_entries


def write_srt(tmp_path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    path = tmp_path / "sample.srt"
    path.write_text(text, encoding=encoding)
    return path


def test_parse_standard_and_multiline_srt(tmp_path: Path):
    path = write_srt(
        tmp_path,
        "1\n00:00:01,250 --> 00:00:03,500\nHello world\nsecond line\n\n"
        "2\n01:02:03,004 --> 01:02:04,005\nAnother subtitle\n",
    )

    entries = parse_srt(path)

    assert len(entries) == 2
    assert entries[0].index == 1
    assert entries[0].start_ms == 1250
    assert entries[0].end_ms == 3500
    assert entries[0].text == "Hello world\nsecond line"
    assert entries[0].srt_path == path
    assert entries[1].start_ms == 3_723_004
    assert entries[1].end_ms == 3_724_005


def test_parse_utf8_bom(tmp_path: Path):
    path = tmp_path / "bom.srt"
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nשלום\n", encoding="utf-8-sig")

    entries = parse_srt(path)

    assert entries[0].text == "שלום"


def test_search_is_case_insensitive_and_phrase_based(tmp_path: Path):
    path = write_srt(
        tmp_path,
        "1\n00:00:00,000 --> 00:00:01,000\nHearthstone Dust Refund Strategy\n\n"
        "2\n00:00:02,000 --> 00:00:03,000\nNo match here\n",
    )
    entries = parse_srt(path)

    assert [e.index for e in search_entries(entries, "dust refund")] == [1]
    assert search_entries(entries, "DUST")[0].index == 1


def test_search_whole_word_does_not_match_substring(tmp_path: Path):
    path = write_srt(
        tmp_path,
        "1\n00:00:00,000 --> 00:00:01,000\ndust\n\n2\n00:00:02,000 --> 00:00:03,000\ndusty\n",
    )
    entries = parse_srt(path)

    assert [e.index for e in search_entries(entries, "dust", whole_word=True)] == [1]


def test_search_empty_query_returns_no_matches(tmp_path: Path):
    path = write_srt(tmp_path, "1\n00:00:00,000 --> 00:00:01,000\nhello\n")
    assert search_entries(parse_srt(path), "") == []


def test_parse_windows_hebrew_encoding(tmp_path: Path):
    path = tmp_path / "hebrew-cp1255.srt"
    payload = "1\n00:00:00,100 --> 00:00:01,200\nאבק\n".encode("cp1255")
    path.write_bytes(payload)

    entries = parse_srt(path)

    assert entries[0].text == "אבק"


def test_parse_windows_western_encoding_does_not_turn_accents_into_hebrew(tmp_path: Path):
    path = tmp_path / "western-cp1252.srt"
    payload = "1\n00:00:00,100 --> 00:00:01,200\nCafé résumé\n".encode("cp1252")
    path.write_bytes(payload)

    entries = parse_srt(path)

    assert entries[0].text == "Café résumé"
