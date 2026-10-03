from pathlib import Path

from subdav.store import PairingStore


def test_pairing_store_save_read_update_remove_and_persist(tmp_path: Path):
    db = tmp_path / "pairs.sqlite3"
    srt = tmp_path / "פרק 01.srt"
    first = tmp_path / "וידאו 01.mp4"
    second = tmp_path / "וידאו 01.mkv"

    store = PairingStore(db)
    assert store.get_pair(srt) is None
    store.set_pair(srt, first)
    assert store.get_pair(srt) == first.resolve()
    store.set_pair(srt, second)
    assert store.get_pair(srt) == second.resolve()

    reopened = PairingStore(db)
    assert reopened.get_pair(srt) == second.resolve()
    reopened.remove_pair(srt)
    assert reopened.get_pair(srt) is None


def test_store_persists_simple_settings(tmp_path: Path):
    db = tmp_path / "pairs.sqlite3"
    store = PairingStore(db)

    assert store.get_setting("ffprobe_path") is None
    store.set_setting("ffprobe_path", r"C:\\Tools\\ffmpeg\\bin\\ffprobe.exe")

    reopened = PairingStore(db)
    assert reopened.get_setting("ffprobe_path") == r"C:\\Tools\\ffmpeg\\bin\\ffprobe.exe"
