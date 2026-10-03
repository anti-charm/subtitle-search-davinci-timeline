import argparse
import tkinter as tk

from subdav.app import SubtitleDavinciApp, build_arg_parser, format_ms


def test_format_ms_uses_srt_like_clock_format():
    assert format_ms(91_005) == "00:01:31.005"
    assert format_ms(3_723_004) == "01:02:03.004"


def test_app_class_is_tkinter_application():
    assert issubclass(SubtitleDavinciApp, tk.Tk)


def test_arg_parser_supports_headless_check_flag():
    parser = build_arg_parser()
    assert isinstance(parser, argparse.ArgumentParser)
    assert parser.parse_args(["--check"]).check is True


def test_resolve_saved_ffprobe_uses_persisted_setting(tmp_path):
    from subdav.app import resolve_saved_ffprobe
    from subdav.store import PairingStore

    ffprobe = tmp_path / "ffprobe.exe"
    ffprobe.write_bytes(b"")
    store = PairingStore(tmp_path / "settings.sqlite3")
    store.set_setting("ffprobe_path", str(ffprobe))

    assert resolve_saved_ffprobe(store) == ffprobe.resolve()


def test_app_exposes_ffprobe_setup_actions():
    assert hasattr(SubtitleDavinciApp, "auto_detect_ffprobe")
    assert hasattr(SubtitleDavinciApp, "locate_ffprobe")
    assert hasattr(SubtitleDavinciApp, "install_ffmpeg")


def test_centered_geometry_centers_child_over_parent():
    from subdav.app import centered_geometry

    assert centered_geometry(100, 200, 1200, 800, 500, 400) == "500x400+450+400"


def test_app_exposes_srt_selection_controls_not_movie_popup():
    for method in (
        "select_all_subtitles",
        "clear_subtitle_selection",
        "toggle_subtitle_enabled",
    ):
        assert hasattr(SubtitleDavinciApp, method)
    assert not hasattr(SubtitleDavinciApp, "select_by_movie")


def test_saved_title_style_and_theme_resolve_with_safe_defaults(tmp_path):
    from subdav.app import THEME_NAMES, resolve_saved_theme, resolve_saved_title_style
    from subdav.store import PairingStore
    from subdav.style import TitleStyle

    store = PairingStore(tmp_path / "settings.sqlite3")
    assert resolve_saved_theme(store) == "Light"
    assert resolve_saved_title_style(store) == TitleStyle()

    store.set_setting("theme", "Dark")
    store.set_setting("title_style_schema_version", "2")
    store.set_setting("title_style", TitleStyle(font="David", font_size=48).to_json())
    assert resolve_saved_theme(store) == "Dark"
    assert resolve_saved_title_style(store).font == "David"

    store.set_setting("theme", "NotATheme")
    store.set_setting("title_style", "not-json")
    assert resolve_saved_theme(store) == "Light"
    assert resolve_saved_title_style(store) == TitleStyle()
    assert THEME_NAMES == {"Light", "Dark"}

    store.set_setting("theme", "System")
    assert resolve_saved_theme(store) == "Light"


def test_app_exposes_style_theme_and_both_export_modes():
    for method in (
        "edit_title_style",
        "change_theme",
        "export_clips_only",
        "export_with_titles",
    ):
        assert hasattr(SubtitleDavinciApp, method)


def test_only_light_and_dark_theme_palettes_remain():
    from subdav.app import _THEME_PALETTES

    assert set(_THEME_PALETTES) == {"Light", "Dark"}


class _FakeVar:
    def __init__(self, value):
        self.value = value

    def set(self, value):
        self.value = value


class _FakeScale:
    def __init__(self):
        self.bindings = {}

    def bind(self, event, callback):
        self.bindings[event] = callback


def test_double_click_reset_binding_resets_only_its_variable():
    from subdav.app import bind_double_click_reset

    x_var = _FakeVar(0.27)
    scale = _FakeScale()
    bind_double_click_reset(scale, x_var, 0.0)

    assert "<Double-Button-1>" in scale.bindings
    result = scale.bindings["<Double-Button-1>"](object())
    assert x_var.value == 0.0
    assert result == "break"


def test_old_title_style_schema_is_reset_to_clean_defaults(tmp_path):
    from subdav.app import TITLE_STYLE_SCHEMA_VERSION, resolve_saved_title_style
    from subdav.store import PairingStore
    from subdav.style import TitleStyle

    store = PairingStore(tmp_path / "settings.sqlite3")
    store.set_setting("title_style", TitleStyle(font="Comic Sans MS", font_size=80).to_json())
    assert resolve_saved_title_style(store) == TitleStyle()

    store.set_setting("title_style_schema_version", TITLE_STYLE_SCHEMA_VERSION)
    store.set_setting("title_style", TitleStyle(font="Arial", font_size=42).to_json())
    assert resolve_saved_title_style(store).font_size == 42


def test_preview_seed_prefers_selected_search_result():
    from pathlib import Path

    from subdav.app import preview_seed_text
    from subdav.models import SubtitleEntry
    from subdav.workflow import ResolvedPair, SearchMatch

    first = SearchMatch(
        SubtitleEntry(1, 0, 1000, "First quote", Path("a.srt")),
        ResolvedPair(Path("a.srt"), "exact", Path("a.mp4")),
    )
    second = SearchMatch(
        SubtitleEntry(2, 1000, 2000, "Chosen quote", Path("a.srt")),
        ResolvedPair(Path("a.srt"), "exact", Path("a.mp4")),
    )
    assert preview_seed_text([first, second], selected_index=1) == "Chosen quote"
    assert preview_seed_text([], selected_index=None) == "Sample subtitle"
