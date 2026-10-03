"""Regression checks for the title editor's frame geometry and font selection."""

import sys
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from gui_helpers import isolated_gui_test

from subdav.app import SubtitleDavinciApp
from subdav.style import TitleStyle


def test_preview_geometry_scales_size_outline_and_position_to_the_frame():
    from subdav.title_preview import preview_geometry

    geometry = preview_geometry(560, 315, 1920, 1080, TitleStyle(font_size=90))
    assert geometry.frame == pytest.approx((0, 0, 560, 315))
    assert geometry.font_pixels == pytest.approx(26.25)
    assert geometry.outline_pixels == pytest.approx(560 / 1920)
    assert geometry.position == pytest.approx((280, 270.9))


def test_preview_letterboxes_and_does_not_clamp_large_text_positions():
    from subdav.title_preview import preview_geometry

    geometry = preview_geometry(
        560,
        315,
        1080,
        1920,
        TitleStyle(
            font_size=170, stroke_width=5, position_x_fraction=-0.45, position_y_fraction=0.3
        ),
    )
    assert geometry.frame == pytest.approx((191.40625, 0, 177.1875, 315))
    assert geometry.font_pixels == pytest.approx(27.890625)
    assert geometry.outline_pixels == pytest.approx(0.8203125)
    assert geometry.position == pytest.approx((200.265625, 63))


@pytest.mark.parametrize("dimensions", [(0, 315, 1920, 1080), (560, 315, 1920, 0)])
def test_preview_rejects_empty_frame_dimensions(dimensions):
    from subdav.title_preview import preview_geometry

    with pytest.raises(ValueError, match="dimensions"):
        preview_geometry(*dimensions, TitleStyle())


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_preview_preserves_multiline_text_and_scales_when_resized():
    from subdav.title_preview import TitlePreview

    root = tk.Tk()
    root.withdraw()
    try:
        preview = TitlePreview(root, width=560, height=315)
        preview.set_title(TitleStyle(font_size=90), "A complete first line!\nAnother line.")
        item = preview.find_withtag("title")[0]
        assert preview.itemcget(item, "text") == "A complete first line!\nAnother line."
        assert preview.coords(item) == pytest.approx([280, 270.9])
        assert int(preview.display_font.cget("size")) == -26
        preview.configure(width=1120, height=630)
        preview.redraw()
        item = preview.find_withtag("title")[0]
        assert preview.coords(item) == pytest.approx([560, 541.8])
        assert int(preview.display_font.cget("size")) == -52
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_preview_uses_first_included_media_dimensions(tmp_path, monkeypatch):
    from pathlib import Path

    from subdav.media import MediaInfo
    from subdav.models import SubtitleEntry
    from subdav.workflow import ResolvedPair, SearchMatch

    app = SubtitleDavinciApp(store_path=tmp_path / "frame.sqlite3")
    app.withdraw()
    try:
        app.matches = [
            SearchMatch(
                SubtitleEntry(1, 0, 1000, "Demo", Path(name + ".srt")),
                ResolvedPair(Path(name + ".srt"), "exact", Path(name + ".mp4")),
            )
            for name in ("wide", "tall")
        ]
        app.ffprobe_path = Path("ffprobe.exe")
        app.included = {1}

        def probe(path, _tool):
            assert path == Path("tall.mp4")
            return MediaInfo(path, 1000, 25, 1, 1080, 1920, False)

        monkeypatch.setattr("subdav.app.probe_media", probe)
        assert app._title_preview_frame() == (1080, 1920, "export frame")
        app.included.clear()
        assert app._title_preview_frame() == (1920, 1080, "reference; no export selection")
    finally:
        app.destroy()


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_editor_does_not_wrap_subtitle_lines_or_use_dpi_dependent_font_points(tmp_path):
    app = SubtitleDavinciApp(store_path=tmp_path / "preview.sqlite3")
    app.withdraw()
    try:
        app.title_style = TitleStyle(font_size=90)
        app.edit_title_style()
        app.update_idletasks()
        canvas = next(widget for widget in widgets(app) if isinstance(widget, tk.Canvas))
        text_items = [item for item in canvas.find_all() if canvas.type(item) == "text"]
        assert text_items
        for item in text_items:
            assert float(canvas.itemcget(item, "width")) == 0
        font = canvas.itemcget(text_items[-1], "font")
        assert int(app.tk.call("font", "configure", font, "-size")) < 0
        font_box = next(widget for widget in widgets(app) if isinstance(widget, ttk.Combobox))
        assert str(font_box.cget("state")) == "readonly"
    finally:
        app.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_font_picker_typing_selects_a_family_without_inserting_text():
    from subdav.title_preview import FontPicker

    root = tk.Tk()
    root.withdraw()
    try:
        picker = FontPicker(root, values=("Arial", "Calibri", "Cambria", "David"))
        picker.current(0)
        picker.on_keypress(SimpleNamespace(char="c", keysym="c", time=1000))
        picker.on_keypress(SimpleNamespace(char="a", keysym="a", time=1100))
        picker.on_keypress(SimpleNamespace(char="m", keysym="m", time=1200))
        assert picker.get() == "Cambria"
        picker.on_keypress(SimpleNamespace(char="d", keysym="d", time=3000))
        assert picker.get() == "David"
        picker.on_keypress(SimpleNamespace(char="z", keysym="z", time=5000))
        assert picker.get() == "David"
        assert str(picker.cget("state")) == "readonly"
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_typing_in_posted_font_dropdown_selects_the_matching_family():
    from subdav.title_preview import FontPicker

    root = tk.Tk()
    try:
        picker = FontPicker(root, values=("Arial", "Calibri", "Cambria", "David"))
        picker.pack()
        picker.current(0)
        root.update()
        root.tk.call("ttk::combobox::Post", str(picker))
        root.update()
        popup = root.tk.call("ttk::combobox::PopdownWindow", str(picker))
        listbox = str(popup) + ".f.l"
        root.tk.call("event", "generate", listbox, "<KeyPress-d>")
        root.update()
        assert picker.get() == "David"
        assert root.tk.call(listbox, "curselection") == (3,)
        root.tk.call("ttk::combobox::Unpost", str(picker))
        root.update()
    finally:
        root.destroy()


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_invalid_style_warning_survives_preview_resize(tmp_path):
    app = SubtitleDavinciApp(store_path=tmp_path / "invalid.sqlite3")
    app.withdraw()
    try:
        app.edit_title_style()
        app.update_idletasks()
        size = next(
            widget
            for widget in widgets(app)
            if isinstance(widget, ttk.Entry) and widget.grid_info().get("row") == 1
        )
        size.delete(0, "end")
        canvas = next(widget for widget in widgets(app) if isinstance(widget, tk.Canvas))
        canvas.redraw()
        texts = [
            canvas.itemcget(item, "text")
            for item in canvas.find_all()
            if canvas.type(item) == "text"
        ]
        assert texts == ["Invalid style values"]
    finally:
        app.destroy()
