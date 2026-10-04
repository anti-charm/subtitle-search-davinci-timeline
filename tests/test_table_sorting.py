"""Exercise sorting with real tables, stable row identities and private demo state."""

import sys
from types import SimpleNamespace

import pytest
from gui_helpers import isolated_gui_test

from subdav.app import SubtitleDavinciApp


def click_heading(app, tree, column):
    command = tree.heading(column, "command")
    assert command, f"The {column} heading must allow sorting"
    app.tk.call(command)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_table_sorting_keeps_selections_row_identity_and_numeric_times(tmp_path, monkeypatch):
    for name, start in [("A", "00:00:01"), ("B", "100:00:01"), ("C", "10:00:01")]:
        (tmp_path / f"{name}.srt").write_text(
            f"1\n{start},000 --> {start},500\nexample {name}\n", encoding="utf-8"
        )
    (tmp_path / "A.mp4").write_bytes(b"")
    (tmp_path / "C.mp4").write_bytes(b"")
    (tmp_path / "C.mkv").write_bytes(b"")
    app = SubtitleDavinciApp(store_path=tmp_path / "state.sqlite3")
    try:
        app.withdraw()
        app.folder_var.set(str(tmp_path))
        app.scan_folder()
        app.pair_tree.selection_set("0")
        enabled = app.enabled_subtitles.copy()
        click_heading(app, app.pair_tree, "status")
        assert app.pair_tree.get_children() == ("1", "2", "0")
        assert app.pair_tree.selection() == ("0",)
        assert app.enabled_subtitles == enabled
        click_heading(app, app.pair_tree, "status")
        assert app.pair_tree.get_children() == ("0", "2", "1")
        app._refresh_pair_tree()
        assert app.pair_tree.get_children() == ("0", "2", "1")
        assert app.pair_tree.selection() == ("0",)

        app.query_var.set("example")
        app.do_search()
        app.result_tree.selection_set("1")
        app.toggle_result()
        originals = app.matches.copy()
        click_heading(app, app.result_tree, "start")
        assert app.result_tree.get_children() == ("0", "2", "1")
        assert app.result_tree.selection() == ("1",)
        assert app.included == {0, 2}
        assert app.matches == originals  # Display sorting must not reorder the timeline.
        click_heading(app, app.result_tree, "pairing")
        assert app.result_tree.get_children() == ("1", "2", "0")
        app.select_all()
        assert app.result_tree.get_children() == ("1", "2", "0")
        assert app.result_tree.selection() == ("1",)
        assert app.included == {0, 1, 2}
        app.toggle_result(SimpleNamespace(y=0))
        assert app.included == {0, 1, 2}  # Header/empty-area clicks cannot toggle a result.

        # Selecting a visually moved row must still pair the correct SRT.
        chosen = tmp_path / "B.mp4"
        chosen.write_bytes(b"")
        app.pair_tree.selection_set("1")
        monkeypatch.setattr("subdav.app.filedialog.askopenfilename", lambda **_kw: str(chosen))
        app.manual_pair_selected()
        assert app.store.get_pair(tmp_path / "B.srt") == chosen.resolve()
        assert app.store.get_pair(tmp_path / "A.srt") is None
    finally:
        app.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_downloaded_clip_mode_ignores_originals_and_refreshes_new_pairs(tmp_path):
    (tmp_path / "Example.en-orig.srt").write_text(
        "1\n00:40:00,000 --> 00:40:01,000\nexample original\n", encoding="utf-8"
    )
    clips = tmp_path / "clips"
    clips.mkdir()

    def add_clip(n):
        srt = clips / f"Example_match_{n:03d}.srt"
        srt.write_text("1\n00:00:05,000 --> 00:00:06,000\nexample clip\n", encoding="utf-8")
        srt.with_suffix(".mp4").write_bytes(b"")

    add_clip(1)
    app = SubtitleDavinciApp(store_path=tmp_path / "state.sqlite3")
    try:
        app.withdraw()
        app.folder_var.set(str(tmp_path))
        app.clips_only_var.set(True)
        app.scan_folder()
        app.query_var.set("example")
        app.do_search()
        assert len(app.matches) == 1
        assert app.matches[0].entry.start_ms == 5000
        assert app.matches[0].pairing.video_path.name == "Example_match_001.mp4"
        add_clip(2)
        assert len(app.scan.subtitles) == 1
        app.scan_folder()
        app.do_search()
        assert len(app.matches) == 2
        assert all(m.pairing.status == "exact" for m in app.matches)
        assert len(app.enabled_subtitles) == 2
    finally:
        app.destroy()
