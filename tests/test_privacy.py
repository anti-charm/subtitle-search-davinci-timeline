"""Prevent direct application networking and exercise a disposable Windows GUI."""

import ast
import sys
from pathlib import Path

import pytest
from gui_helpers import isolated_gui_test

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_has_no_network_or_telemetry_imports():
    forbidden = {
        "requests",
        "httpx",
        "socket",
        "http",
        "urllib.request",
        "sentry_sdk",
        "telemetry",
        "aiohttp",
        "ftplib",
        "webbrowser",
    }
    for path in (ROOT / "src" / "subdav").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(
                name == blocked or name.startswith(blocked + ".")
                for name in names
                for blocked in forbidden
            ), path.name


@pytest.mark.skipif(sys.platform != "win32", reason="Requires a Windows Tk desktop")
@isolated_gui_test
def test_windows_gui_constructs_with_disposable_state(tmp_path):
    from subdav.app import SubtitleDavinciApp

    app = SubtitleDavinciApp(store_path=tmp_path / "demo.sqlite3")
    try:
        app.withdraw()
        app.update_idletasks()
        assert app.matches == []
        assert app.included == set()
        app.theme_var.set("Dark")
        app.change_theme()
        assert app.store.get_setting("theme") == "Dark"
    finally:
        app.destroy()
