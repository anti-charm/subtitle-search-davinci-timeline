from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from tkinter import font as tkfont

from .library import VIDEO_EXTENSIONS, LibraryScan, scan_library
from .media import MediaProbeError, find_ffprobe, launch_ffmpeg_installer, probe_media
from .store import PairingStore
from .style import TitleStyle
from .title_preview import FontPicker, TitlePreview
from .workflow import (
    ResolvedPair,
    SearchMatch,
    SubtitleReadError,
    UnresolvedPairingError,
    export_matches,
    resolve_pairs,
    search_library,
)


def format_ms(milliseconds: int) -> str:
    hours, rem = divmod(milliseconds, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def default_store_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SubtitleDavinci"
    else:
        base = Path.home() / ".subdav"
    return base / "pairings.sqlite3"


def resolve_saved_ffprobe(store: PairingStore) -> Path | None:
    saved = store.get_setting("ffprobe_path")
    return find_ffprobe(saved)


THEME_NAMES = {"Light", "Dark"}
TITLE_STYLE_SCHEMA_VERSION = "2"


def preview_seed_text(matches: list[SearchMatch], selected_index: int | None = None) -> str:
    if selected_index is not None and 0 <= selected_index < len(matches):
        return matches[selected_index].entry.text
    if matches:
        return matches[0].entry.text
    return "Sample subtitle"


_DARK_BASE = {
    "bg": "#181A1F",
    "panel": "#202329",
    "field": "#24272E",
    "fg": "#FFFFFF",
    "muted": "#B8BEC9",
    "outline": "#D6D9DE",
    "select_fg": "#FFFFFF",
}

_THEME_PALETTES = {
    "Light": {
        "bg": "#F3F5F8",
        "panel": "#FFFFFF",
        "field": "#FFFFFF",
        "fg": "#20242A",
        "muted": "#5F6670",
        "outline": "#B7BEC8",
        "accent": "#4A73D9",
        "select_fg": "#FFFFFF",
    },
    "Dark": {**_DARK_BASE, "accent": "#6B8AFD"},
}


def resolve_saved_theme(store: PairingStore) -> str:
    value = store.get_setting("theme") or "Light"
    # v0.1.3 offered a System option. Migrate it to the explicit light theme
    # so the appearance is stable across Windows theme engines.
    if value == "System":
        return "Light"
    return value if value in THEME_NAMES else "Light"


def bind_double_click_reset(scale, variable, default_value: float) -> None:
    """Reset one scale variable to its default on a double left-click."""

    def reset(_event):
        variable.set(default_value)
        return "break"

    scale.bind("<Double-Button-1>", reset)


def centered_geometry(
    parent_x: int,
    parent_y: int,
    parent_width: int,
    parent_height: int,
    child_width: int,
    child_height: int,
) -> str:
    x = max(0, parent_x + (parent_width - child_width) // 2)
    y = max(0, parent_y + (parent_height - child_height) // 2)
    return f"{child_width}x{child_height}+{x}+{y}"


def resolve_saved_title_style(store: PairingStore) -> TitleStyle:
    # v0.1.5 changes units/defaults enough that carrying old saved styles
    # forward would preserve the unreadable legacy look. Reset once.
    if store.get_setting("title_style_schema_version") != TITLE_STYLE_SCHEMA_VERSION:
        return TitleStyle()
    raw = store.get_setting("title_style")
    if not raw:
        return TitleStyle()
    try:
        return TitleStyle.from_json(raw)
    except (TypeError, ValueError, KeyError, OverflowError):
        return TitleStyle()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="subdav",
        description="Search SRT subtitle libraries and export matching clips to DaVinci Resolve FCPXML.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the local Python/Tkinter/ffprobe environment without opening the GUI",
    )
    return parser


class SubtitleDavinciApp(tk.Tk):
    def __init__(self, *, store_path: Path | None = None):
        super().__init__()
        self.title("Subtitle Search -> DaVinci Timeline")
        self.geometry("1220x780")
        self.minsize(900, 620)

        self.store = PairingStore(store_path or default_store_path())
        self.ffprobe_path = resolve_saved_ffprobe(self.store)
        self.title_style = resolve_saved_title_style(self.store)
        self.style_engine = ttk.Style(self)
        self.scan: LibraryScan | None = None
        self.pairs: dict[Path, ResolvedPair] = {}
        self.enabled_subtitles: set[Path] = set()
        self.matches: list[SearchMatch] = []
        self.included: set[int] = set()

        self.folder_var = tk.StringVar()
        self.query_var = tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        self.whole_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Choose a folder containing .srt files and videos.")
        self.ffprobe_var = tk.StringVar()
        self.theme_var = tk.StringVar(value=resolve_saved_theme(self.store))
        self._refresh_ffprobe_status()

        self._build_ui()
        self._apply_theme(self.theme_var.get())

    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        outer.rowconfigure(4, weight=2)

        folder = ttk.LabelFrame(outer, text="Library", padding=8)
        folder.grid(row=0, column=0, sticky="ew")
        folder.columnconfigure(0, weight=1)
        ttk.Entry(folder, textvariable=self.folder_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 6)
        )
        ttk.Button(folder, text="Browse...", command=self.choose_folder).grid(
            row=0, column=1, padx=3
        )
        ttk.Button(folder, text="Scan", command=self.scan_folder).grid(row=0, column=2, padx=3)

        ffmpeg = ttk.Frame(folder)
        ffmpeg.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(7, 0))
        ffmpeg.columnconfigure(1, weight=1)
        ttk.Label(ffmpeg, text="FFmpeg / ffprobe:").grid(row=0, column=0, sticky="w")
        ttk.Label(ffmpeg, textvariable=self.ffprobe_var).grid(
            row=0, column=1, sticky="w", padx=(6, 8)
        )
        ttk.Button(ffmpeg, text="Auto-detect", command=self.auto_detect_ffprobe).grid(
            row=0, column=2, padx=3
        )
        ttk.Button(ffmpeg, text="Locate ffprobe...", command=self.locate_ffprobe).grid(
            row=0, column=3, padx=3
        )
        if sys.platform == "win32":
            ttk.Button(ffmpeg, text="Install FFmpeg...", command=self.install_ffmpeg).grid(
                row=0, column=4, padx=3
            )

        pair_controls = ttk.Frame(outer)
        pair_controls.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        ttk.Label(pair_controls, text="Subtitle / video pairing").pack(side="left")
        ttk.Button(pair_controls, text="Select all SRT", command=self.select_all_subtitles).pack(
            side="left", padx=(10, 3)
        )
        ttk.Button(pair_controls, text="Clear SRT", command=self.clear_subtitle_selection).pack(
            side="left", padx=3
        )
        ttk.Button(pair_controls, text="Pair selected...", command=self.manual_pair_selected).pack(
            side="right", padx=3
        )
        ttk.Button(
            pair_controls, text="Clear manual pair", command=self.clear_manual_pair_selected
        ).pack(side="right", padx=3)

        pair_frame = ttk.Frame(outer)
        pair_frame.grid(row=2, column=0, sticky="nsew")
        pair_frame.columnconfigure(0, weight=1)
        pair_frame.rowconfigure(0, weight=1)
        self.pair_tree = ttk.Treeview(
            pair_frame,
            columns=("use", "subtitle", "status", "video"),
            show="headings",
            height=7,
        )
        self.pair_tree.heading("use", text="Use")
        self.pair_tree.heading("subtitle", text="Subtitle")
        self.pair_tree.heading("status", text="Pairing")
        self.pair_tree.heading("video", text="Video")
        self.pair_tree.column("use", width=52, anchor="center", stretch=False)
        self.pair_tree.column("subtitle", width=280, anchor="w")
        self.pair_tree.column("status", width=110, anchor="center")
        self.pair_tree.column("video", width=500, anchor="w")
        self.pair_tree.bind("<Button-1>", self.toggle_subtitle_enabled)
        pair_scroll = ttk.Scrollbar(pair_frame, orient="vertical", command=self.pair_tree.yview)
        self.pair_tree.configure(yscrollcommand=pair_scroll.set)
        self.pair_tree.grid(row=0, column=0, sticky="nsew")
        pair_scroll.grid(row=0, column=1, sticky="ns")

        search = ttk.LabelFrame(outer, text="Search", padding=8)
        search.grid(row=3, column=0, sticky="ew", pady=(10, 4))
        search.columnconfigure(0, weight=1)
        query = ttk.Entry(search, textvariable=self.query_var)
        query.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        query.bind("<Return>", lambda _event: self.do_search())
        ttk.Checkbutton(search, text="Case sensitive", variable=self.case_var).grid(
            row=0, column=1, padx=4
        )
        ttk.Checkbutton(search, text="Whole word", variable=self.whole_var).grid(
            row=0, column=2, padx=4
        )
        ttk.Button(search, text="Search", command=self.do_search).grid(row=0, column=3, padx=4)

        results = ttk.Frame(outer)
        results.grid(row=4, column=0, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(0, weight=1)
        self.result_tree = ttk.Treeview(
            results,
            columns=("use", "subtitle", "start", "end", "text", "video", "pairing"),
            show="headings",
        )
        headings = {
            "use": "Use",
            "subtitle": "Subtitle",
            "start": "Start",
            "end": "End",
            "text": "Text",
            "video": "Video",
            "pairing": "Pairing",
        }
        for key, title in headings.items():
            self.result_tree.heading(key, text=title)
        self.result_tree.column("use", width=45, anchor="center", stretch=False)
        self.result_tree.column("subtitle", width=170, anchor="w")
        self.result_tree.column("start", width=105, anchor="center", stretch=False)
        self.result_tree.column("end", width=105, anchor="center", stretch=False)
        self.result_tree.column("text", width=360, anchor="w")
        self.result_tree.column("video", width=220, anchor="w")
        self.result_tree.column("pairing", width=90, anchor="center", stretch=False)
        self.result_tree.bind("<Double-1>", self.toggle_result)
        result_scroll_y = ttk.Scrollbar(results, orient="vertical", command=self.result_tree.yview)
        result_scroll_x = ttk.Scrollbar(
            results, orient="horizontal", command=self.result_tree.xview
        )
        self.result_tree.configure(
            yscrollcommand=result_scroll_y.set, xscrollcommand=result_scroll_x.set
        )
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        result_scroll_y.grid(row=0, column=1, sticky="ns")
        result_scroll_x.grid(row=1, column=0, sticky="ew")

        bottom = ttk.Frame(outer)
        bottom.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(bottom, text="Select all results", command=self.select_all).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(bottom, text="Clear results", command=self.clear_selection).pack(
            side="left", padx=4
        )
        ttk.Button(bottom, text="Title style...", command=self.edit_title_style).pack(
            side="left", padx=(10, 4)
        )
        ttk.Label(bottom, text="Appearance:").pack(side="left", padx=(10, 3))
        theme_box = ttk.Combobox(
            bottom,
            textvariable=self.theme_var,
            values=("Light", "Dark"),
            state="readonly",
            width=9,
        )
        theme_box.pack(side="left")
        theme_box.bind("<<ComboboxSelected>>", self.change_theme)
        ttk.Label(bottom, textvariable=self.status_var).pack(side="left", padx=12)

        export_button = ttk.Menubutton(bottom, text="Export FCPXML ▾")
        self.export_menu = tk.Menu(export_button, tearoff=False)
        self.export_menu.add_command(label="Video/audio only", command=self.export_clips_only)
        self.export_menu.add_command(
            label="Video/audio + editable titles", command=self.export_with_titles
        )
        export_button["menu"] = self.export_menu
        export_button.pack(side="right")

    def _apply_theme(self, name: str) -> None:
        if name not in _THEME_PALETTES:
            name = "Light"
            self.theme_var.set(name)

        palette = _THEME_PALETTES[name]
        self.style_engine.theme_use("clam")
        self.configure(background=palette["bg"])

        # Neutral surfaces first. Colored themes use the same dark surfaces and
        # differ only in their accent, which keeps the interface calm.
        self.style_engine.configure("TFrame", background=palette["bg"])
        self.style_engine.configure("TLabel", background=palette["bg"], foreground=palette["fg"])
        self.style_engine.configure(
            "TLabelframe",
            background=palette["bg"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            borderwidth=1,
        )
        self.style_engine.configure(
            "TLabelframe.Label", background=palette["bg"], foreground=palette["fg"]
        )
        self.style_engine.configure(
            "TButton",
            background=palette["panel"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            focuscolor=palette["accent"],
            borderwidth=1,
            padding=(7, 4),
        )
        self.style_engine.map(
            "TButton",
            background=[("active", palette["accent"]), ("pressed", palette["accent"])],
            foreground=[("active", palette["select_fg"]), ("pressed", palette["select_fg"])],
        )
        self.style_engine.configure(
            "TMenubutton",
            background=palette["panel"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            arrowcolor=palette["fg"],
            borderwidth=1,
            padding=(7, 4),
        )
        self.style_engine.map(
            "TMenubutton",
            background=[("active", palette["accent"])],
            foreground=[("active", palette["select_fg"])],
        )
        self.style_engine.configure(
            "TEntry",
            fieldbackground=palette["field"],
            background=palette["field"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            insertcolor=palette["fg"],
            borderwidth=1,
        )
        self.style_engine.configure(
            "TCombobox",
            fieldbackground=palette["field"],
            background=palette["panel"],
            foreground=palette["fg"],
            arrowcolor=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            borderwidth=1,
        )
        self.style_engine.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["field"])],
            foreground=[("readonly", palette["fg"])],
            selectbackground=[("readonly", palette["field"])],
            selectforeground=[("readonly", palette["fg"])],
        )
        self.style_engine.configure(
            "TCheckbutton",
            background=palette["bg"],
            foreground=palette["fg"],
            indicatorbackground=palette["field"],
            indicatorforeground=palette["accent"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            focuscolor=palette["accent"],
        )
        self.style_engine.map(
            "TCheckbutton",
            background=[("active", palette["bg"])],
            foreground=[("active", palette["fg"])],
            indicatorbackground=[("selected", palette["accent"]), ("!selected", palette["field"])],
        )
        self.style_engine.configure(
            "Treeview",
            background=palette["field"],
            fieldbackground=palette["field"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            borderwidth=1,
            rowheight=23,
        )
        self.style_engine.map(
            "Treeview",
            background=[("selected", palette["accent"])],
            foreground=[("selected", palette["select_fg"])],
        )
        self.style_engine.configure(
            "Treeview.Heading",
            background=palette["panel"],
            foreground=palette["fg"],
            bordercolor=palette["outline"],
            lightcolor=palette["outline"],
            darkcolor=palette["outline"],
            relief="flat",
        )
        self.style_engine.map(
            "Treeview.Heading",
            background=[("active", palette["panel"])],
            foreground=[("active", palette["fg"])],
        )
        for style_name in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            self.style_engine.configure(
                style_name,
                background=palette["panel"],
                troughcolor=palette["bg"],
                arrowcolor=palette["fg"],
                bordercolor=palette["outline"],
                lightcolor=palette["outline"],
                darkcolor=palette["outline"],
            )
            self.style_engine.map(style_name, background=[("active", palette["accent"])])

        # Native Tk menus and ttk combobox pop-downs are not controlled by ttk.Style.
        self.option_add("*TCombobox*Listbox.background", palette["field"])
        self.option_add("*TCombobox*Listbox.foreground", palette["fg"])
        self.option_add("*TCombobox*Listbox.selectBackground", palette["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", palette["select_fg"])
        if hasattr(self, "export_menu"):
            self.export_menu.configure(
                background=palette["panel"],
                foreground=palette["fg"],
                activebackground=palette["accent"],
                activeforeground=palette["select_fg"],
                borderwidth=1,
            )

    def change_theme(self, _event=None) -> None:
        name = self.theme_var.get()
        if name not in THEME_NAMES:
            name = "Light"
            self.theme_var.set(name)
        self.store.set_setting("theme", name)
        self._apply_theme(name)

    def edit_title_style(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Editable title style")
        dialog.transient(self)
        dialog.resizable(True, True)

        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        font_var = tk.StringVar(value=self.title_style.font)
        size_var = tk.StringVar(value=str(self.title_style.font_size))
        face_var = tk.StringVar(value=self.title_style.font_face)
        color_var = tk.StringVar(value=self.title_style.font_color)
        stroke_var = tk.StringVar(value=self.title_style.stroke_color)
        stroke_width_var = tk.StringVar(value=f"{self.title_style.stroke_width:g}")
        alignment_var = tk.StringVar(value=self.title_style.alignment)
        x_var = tk.DoubleVar(value=self.title_style.position_x_fraction)
        y_var = tk.DoubleVar(value=self.title_style.position_y_fraction)

        selected_index = None
        selected_rows = self.result_tree.selection() if hasattr(self, "result_tree") else ()
        if selected_rows:
            try:
                selected_index = int(selected_rows[0])
            except (TypeError, ValueError):
                selected_index = None
        preview_text_var = tk.StringVar(value=preview_seed_text(self.matches, selected_index))

        fonts = sorted(set(tkfont.families(self)), key=str.casefold)
        rows = [
            ("Font", FontPicker(body, textvariable=font_var, values=fonts, width=30)),
            ("Font size", ttk.Entry(body, textvariable=size_var, width=12)),
            (
                "Face",
                ttk.Combobox(
                    body,
                    textvariable=face_var,
                    values=("Regular", "Bold", "Italic", "Bold Italic"),
                    state="readonly",
                    width=15,
                ),
            ),
            (
                "Alignment",
                ttk.Combobox(
                    body,
                    textvariable=alignment_var,
                    values=("left", "center", "right"),
                    state="readonly",
                    width=12,
                ),
            ),
            (
                "Outline width (0 = none)",
                ttk.Entry(body, textvariable=stroke_width_var, width=12),
            ),
        ]
        for row, (label, widget) in enumerate(rows):
            ttk.Label(body, text=label + ":").grid(
                row=row, column=0, sticky="w", pady=3, padx=(0, 8)
            )
            widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)

        def choose_colour(variable: tk.StringVar, title: str) -> None:
            chosen = colorchooser.askcolor(color=variable.get(), title=title, parent=dialog)[1]
            if chosen:
                variable.set(chosen.upper())

        color_row = len(rows)
        ttk.Label(body, text="Text color:").grid(
            row=color_row, column=0, sticky="w", pady=3, padx=(0, 8)
        )
        ttk.Entry(body, textvariable=color_var, width=14).grid(
            row=color_row, column=1, sticky="ew", pady=3
        )
        ttk.Button(
            body, text="Choose...", command=lambda: choose_colour(color_var, "Text color")
        ).grid(row=color_row, column=2, padx=(6, 0))

        stroke_row = color_row + 1
        ttk.Label(body, text="Outline color:").grid(
            row=stroke_row, column=0, sticky="w", pady=3, padx=(0, 8)
        )
        ttk.Entry(body, textvariable=stroke_var, width=14).grid(
            row=stroke_row, column=1, sticky="ew", pady=3
        )
        ttk.Button(
            body, text="Choose...", command=lambda: choose_colour(stroke_var, "Outline color")
        ).grid(row=stroke_row, column=2, padx=(6, 0))

        x_row = stroke_row + 1
        ttk.Label(body, text="Horizontal position:").grid(
            row=x_row, column=0, sticky="w", pady=(8, 3), padx=(0, 8)
        )
        x_scale = ttk.Scale(
            body, from_=-0.45, to=0.45, variable=x_var, orient="horizontal", length=300
        )
        x_scale.grid(row=x_row, column=1, columnspan=2, sticky="ew", pady=(8, 3))
        bind_double_click_reset(x_scale, x_var, TitleStyle().position_x_fraction)
        ttk.Label(body, text="Left  ←   center   →  right   (default: 0)").grid(
            row=x_row + 1, column=1, columnspan=2, sticky="w"
        )

        y_row = x_row + 2
        ttk.Label(body, text="Vertical position:").grid(
            row=y_row, column=0, sticky="w", pady=(8, 3), padx=(0, 8)
        )
        y_scale = ttk.Scale(
            body, from_=-0.46, to=0.30, variable=y_var, orient="horizontal", length=300
        )
        y_scale.grid(row=y_row, column=1, columnspan=2, sticky="ew", pady=(8, 3))
        bind_double_click_reset(y_scale, y_var, TitleStyle().position_y_fraction)
        ttk.Label(body, text="Lower  ←   center   →  upper   (default: -0.36)").grid(
            row=y_row + 1, column=1, columnspan=2, sticky="w"
        )

        sample_row = y_row + 2
        ttk.Label(body, text="Preview text:").grid(
            row=sample_row, column=0, sticky="w", pady=(10, 3), padx=(0, 8)
        )
        preview_text = tk.Text(body, height=3, width=40, wrap="none", undo=True)
        preview_text.insert("1.0", preview_text_var.get())
        preview_text.grid(row=sample_row, column=1, sticky="ew", pady=(10, 3))

        def update_sample(_event=None) -> None:
            if preview_text.edit_modified():
                preview_text_var.set(preview_text.get("1.0", "end-1c"))
                preview_text.edit_modified(False)

        preview_text.bind("<<Modified>>", update_sample)
        preview_text.edit_modified(False)

        def use_selected_quote() -> None:
            rows = self.result_tree.selection() if hasattr(self, "result_tree") else ()
            index = None
            if rows:
                try:
                    index = int(rows[0])
                except (TypeError, ValueError):
                    index = None
            quote = preview_seed_text(self.matches, index)
            preview_text.delete("1.0", "end")
            preview_text.insert("1.0", quote)
            preview_text_var.set(quote)

        ttk.Button(body, text="Use selected result", command=use_selected_quote).grid(
            row=sample_row, column=2, padx=(6, 0), pady=(10, 3)
        )

        preview_row = sample_row + 1
        frame_width, frame_height, frame_note = self._title_preview_frame()
        ttk.Label(
            body, text=f"Title preview — {frame_width} × {frame_height} ({frame_note}):"
        ).grid(row=preview_row, column=0, columnspan=3, sticky="w", pady=(10, 4))
        preview = TitlePreview(
            body,
            frame_width=frame_width,
            frame_height=frame_height,
            width=560,
            height=260,
        )
        preview.grid(row=preview_row + 1, column=0, columnspan=3, sticky="nsew")
        body.rowconfigure(preview_row + 1, weight=1)
        ttk.Label(
            body,
            text="Frame-scaled estimate. Resolve may substitute fonts or unsupported bold/italic faces.",
            wraplength=620,
        ).grid(row=preview_row + 2, column=0, columnspan=3, sticky="w", pady=(5, 0))

        def preview_style() -> TitleStyle | None:
            try:
                size = int(size_var.get())
                stroke_width = float(stroke_width_var.get())
                if size <= 0 or stroke_width < 0:
                    return None
                candidate = TitleStyle(
                    font=font_var.get(),
                    font_size=size,
                    font_face=face_var.get(),
                    font_color=color_var.get().strip(),
                    stroke_color=stroke_var.get().strip(),
                    stroke_width=stroke_width,
                    alignment=alignment_var.get(),
                    position_x_fraction=float(x_var.get()),
                    position_y_fraction=float(y_var.get()),
                )
                if candidate.font not in fonts:
                    return None
                candidate.text_style_attrs()
                return candidate
            except (TypeError, ValueError, tk.TclError):
                return None

        def redraw_preview(*_args) -> None:
            parsed = preview_style()
            if parsed is None:
                preview.show_error("Invalid style values")
                return
            preview.set_title(parsed, preview_text_var.get())

        for variable in (
            font_var,
            size_var,
            face_var,
            color_var,
            stroke_var,
            stroke_width_var,
            alignment_var,
            x_var,
            y_var,
            preview_text_var,
        ):
            variable.trace_add("write", redraw_preview)

        buttons = ttk.Frame(body)
        buttons.grid(row=preview_row + 3, column=0, columnspan=3, sticky="ew", pady=(12, 0))

        def apply_defaults() -> None:
            default = TitleStyle()
            font_var.set(default.font)
            size_var.set(str(default.font_size))
            face_var.set(default.font_face)
            color_var.set(default.font_color)
            stroke_var.set(default.stroke_color)
            stroke_width_var.set(f"{default.stroke_width:g}")
            alignment_var.set(default.alignment)
            x_var.set(default.position_x_fraction)
            y_var.set(default.position_y_fraction)

        def save() -> None:
            parsed = preview_style()
            if parsed is None:
                messagebox.showerror(
                    "Invalid title style",
                    "Choose an installed font and check the size, colors, outline width, and position.",
                    parent=dialog,
                )
                return
            self.title_style = parsed
            self.store.set_setting("title_style", parsed.to_json())
            self.store.set_setting("title_style_schema_version", TITLE_STYLE_SCHEMA_VERSION)
            dialog.destroy()
            self.status_var.set("Editable title style saved for future exports.")

        ttk.Button(buttons, text="Reset to default", command=apply_defaults).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Save", command=save).pack(side="right")

        redraw_preview()
        dialog.update_idletasks()
        width = min(max(680, dialog.winfo_reqwidth()), self.winfo_screenwidth() - 60)
        height = min(max(720, dialog.winfo_reqheight()), self.winfo_screenheight() - 100)
        dialog.minsize(min(640, width), min(620, height))
        dialog.geometry(
            centered_geometry(
                self.winfo_rootx(),
                self.winfo_rooty(),
                self.winfo_width(),
                self.winfo_height(),
                width,
                height,
            )
        )
        dialog.grab_set()
        dialog.focus_set()

    def _title_preview_frame(self) -> tuple[int, int, str]:
        # The first included result determines the exported sequence format.
        for index in sorted(self.included):
            if 0 <= index < len(self.matches):
                video = self.matches[index].pairing.video_path
                if video is not None and self.ffprobe_path is not None:
                    try:
                        info = probe_media(video, self.ffprobe_path)
                        return info.width, info.height, "export frame"
                    except (MediaProbeError, OSError, ValueError):
                        return 1920, 1080, "reference; media size unavailable"
                return 1920, 1080, "reference; media size unavailable"
        return 1920, 1080, "reference; no export selection"

    def _refresh_ffprobe_status(self) -> None:
        if self.ffprobe_path is None:
            self.ffprobe_var.set("Not found - install FFmpeg or locate ffprobe.exe")
        else:
            self.ffprobe_var.set(f"Ready: {self.ffprobe_path}")

    def _save_ffprobe(self, path: Path) -> None:
        self.ffprobe_path = path.resolve()
        self.store.set_setting("ffprobe_path", str(self.ffprobe_path))
        self._refresh_ffprobe_status()

    def auto_detect_ffprobe(self) -> None:
        found = find_ffprobe()
        if found is None:
            self.ffprobe_path = None
            self._refresh_ffprobe_status()
            messagebox.showinfo(
                "FFmpeg not found",
                "ffprobe is not installed or could not be found. On Windows, click "
                "'Install FFmpeg...' for automatic installation, or locate ffprobe.exe manually.",
            )
            return
        self._save_ffprobe(found)
        self.status_var.set("FFmpeg/ffprobe detected and ready for export.")

    def locate_ffprobe(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Locate ffprobe executable",
            filetypes=[
                ("ffprobe executable", "ffprobe.exe" if sys.platform == "win32" else "ffprobe"),
                ("All files", "*.*"),
            ],
        )
        if not chosen:
            return
        path = Path(chosen)
        if not path.is_file() or (sys.platform == "win32" and path.suffix.casefold() != ".exe"):
            messagebox.showerror(
                "Invalid ffprobe", "Choose a trusted native ffprobe executable (.exe on Windows)."
            )
            return
        self._save_ffprobe(path)
        self.status_var.set("Saved ffprobe location. Timeline export is ready.")

    def install_ffmpeg(self) -> None:
        if not messagebox.askyesno(
            "Install FFmpeg",
            "Install the Gyan FFmpeg package using Windows Package Manager (winget)?\n\n"
            "A separate installer window may open. When it finishes, click Auto-detect.",
        ):
            return
        try:
            launch_ffmpeg_installer()
        except MediaProbeError as exc:
            messagebox.showerror("Could not start FFmpeg installation", str(exc))
            return
        messagebox.showinfo(
            "FFmpeg installation started",
            "Windows Package Manager has started the FFmpeg installation. "
            "When it finishes, return here and click Auto-detect.",
        )

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Choose subtitle/video library")
        if chosen:
            self.folder_var.set(chosen)
            self.scan_folder()

    def scan_folder(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showerror("No folder", "Choose a library folder first.")
            return
        self.scan = None
        self.pairs = {}
        self.matches = []
        self.included.clear()
        self._refresh_pair_tree()
        self._refresh_result_tree()
        try:
            self.scan = scan_library(Path(folder))
            self.pairs = resolve_pairs(self.scan, self.store)
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.scan = None
            self.pairs = {}
            messagebox.showerror("Scan failed", str(exc))
            return
        self.enabled_subtitles = {srt.resolve() for srt in self.scan.subtitles}
        self._refresh_pair_tree()
        self.matches = []
        self.included.clear()
        self._refresh_result_tree()
        self.status_var.set(
            f"Found {len(self.scan.subtitles)} subtitle files and {len(self.scan.videos)} videos."
        )

    def _refresh_pair_tree(self) -> None:
        self.pair_tree.delete(*self.pair_tree.get_children())
        if self.scan is None:
            return
        for index, srt in enumerate(self.scan.subtitles):
            resolved = srt.resolve()
            pair = self.pairs[resolved]
            video = pair.video_path.name if pair.video_path else "—"
            self.pair_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    "☑" if resolved in self.enabled_subtitles else "☐",
                    srt.name,
                    pair.status,
                    video,
                ),
            )

    def _subtitle_filter_changed(self) -> None:
        self._refresh_pair_tree()
        if self.query_var.get().strip():
            self.do_search()
        else:
            self.matches = []
            self.included.clear()
            self._refresh_result_tree()
            self.status_var.set(
                f"{len(self.enabled_subtitles)} of {len(self.scan.subtitles) if self.scan else 0} subtitle files enabled."
            )

    def toggle_subtitle_enabled(self, event=None) -> str | None:
        if self.scan is None:
            return None
        if event is not None:
            item = self.pair_tree.identify_row(event.y)
            column = self.pair_tree.identify_column(event.x)
            if not item or column != "#1":
                return None
        else:
            selected = self.pair_tree.selection()
            item = selected[0] if selected else None
            if not item:
                return None
        srt = self.scan.subtitles[int(item)].resolve()
        if srt in self.enabled_subtitles:
            self.enabled_subtitles.remove(srt)
        else:
            self.enabled_subtitles.add(srt)
        self._subtitle_filter_changed()
        return "break" if event is not None else None

    def select_all_subtitles(self) -> None:
        if self.scan is None:
            return
        self.enabled_subtitles = {srt.resolve() for srt in self.scan.subtitles}
        self._subtitle_filter_changed()

    def clear_subtitle_selection(self) -> None:
        if self.scan is None:
            return
        self.enabled_subtitles.clear()
        self._subtitle_filter_changed()

    def _selected_srt(self) -> Path | None:
        if self.scan is None:
            return None
        selected = self.pair_tree.selection()
        if not selected:
            return None
        return self.scan.subtitles[int(selected[0])].resolve()

    def manual_pair_selected(self) -> None:
        srt = self._selected_srt()
        if srt is None:
            messagebox.showinfo("Pair video", "Select a subtitle file in the pairing table first.")
            return
        filetypes = [
            ("Video files", " ".join(f"*{ext}" for ext in sorted(VIDEO_EXTENSIONS))),
            ("All files", "*.*"),
        ]
        chosen = filedialog.askopenfilename(
            title=f"Choose video for {srt.name}", filetypes=filetypes
        )
        if not chosen:
            return
        self.store.set_pair(srt, Path(chosen))
        self._recompute_pairs_and_search()

    def clear_manual_pair_selected(self) -> None:
        srt = self._selected_srt()
        if srt is None:
            messagebox.showinfo("Clear pair", "Select a subtitle file first.")
            return
        self.store.remove_pair(srt)
        self._recompute_pairs_and_search()

    def _recompute_pairs_and_search(self) -> None:
        if self.scan is None:
            return
        self.pairs = resolve_pairs(self.scan, self.store)
        self._refresh_pair_tree()
        if self.query_var.get():
            self.do_search()

    def do_search(self) -> None:
        self.matches = []
        self.included.clear()
        self._refresh_result_tree()
        if self.scan is None:
            self.scan_folder()
            if self.scan is None:
                return
        query = self.query_var.get()
        if not query:
            self.matches = []
            self.included.clear()
            self._refresh_result_tree()
            self.status_var.set("Enter a word or phrase to search.")
            return
        try:
            self.matches = search_library(
                self.scan,
                self.pairs,
                query,
                case_sensitive=self.case_var.get(),
                whole_word=self.whole_var.get(),
                enabled_subtitles=self.enabled_subtitles,
            )
        except SubtitleReadError as exc:
            self.status_var.set("Search failed; previous results were cleared.")
            messagebox.showerror("Subtitle read error", str(exc))
            return
        self.included = set(range(len(self.matches)))
        self._refresh_result_tree()
        unresolved = sum(1 for match in self.matches if match.pairing.video_path is None)
        suffix = f"; {unresolved} need video pairing" if unresolved else ""
        self.status_var.set(f"{len(self.matches)} matching subtitle entries{suffix}.")

    def _refresh_result_tree(self) -> None:
        self.result_tree.delete(*self.result_tree.get_children())
        for idx, match in enumerate(self.matches):
            video = match.pairing.video_path.name if match.pairing.video_path else "—"
            text = " ".join(match.entry.text.splitlines())
            self.result_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    "✓" if idx in self.included else "",
                    match.entry.srt_path.name,
                    format_ms(match.entry.start_ms),
                    format_ms(match.entry.end_ms),
                    text,
                    video,
                    match.pairing.status,
                ),
            )

    def toggle_result(self, event=None) -> None:
        item = self.result_tree.identify_row(event.y) if event is not None else None
        if not item:
            selected = self.result_tree.selection()
            item = selected[0] if selected else None
        if item is None:
            return
        idx = int(item)
        if idx in self.included:
            self.included.remove(idx)
        else:
            self.included.add(idx)
        self._refresh_result_tree()
        self.result_tree.selection_set(item)

    def select_all(self) -> None:
        self.included = set(range(len(self.matches)))
        self._refresh_result_tree()

    def clear_selection(self) -> None:
        self.included.clear()
        self._refresh_result_tree()

    def export_timeline(self) -> None:
        self.export_clips_only()

    def export_clips_only(self) -> None:
        self._export_timeline(include_titles=False)

    def export_with_titles(self) -> None:
        self._export_timeline(include_titles=True)

    def _export_timeline(self, *, include_titles: bool) -> None:
        selected = [self.matches[i] for i in sorted(self.included)]
        if not selected:
            messagebox.showinfo("Nothing selected", "Select at least one subtitle match to export.")
            return
        detected = find_ffprobe(self.ffprobe_path)
        if detected is None:
            self.ffprobe_path = None
            self._refresh_ffprobe_status()
            messagebox.showerror(
                "FFmpeg/ffprobe required",
                "Timeline export needs ffprobe. Use 'Install FFmpeg...' on Windows, "
                "or 'Locate ffprobe...' if it is already installed.",
            )
            return
        self._save_ffprobe(detected)
        default_name = (
            "subtitle_compilation_with_titles.fcpxml"
            if include_titles
            else "subtitle_compilation.fcpxml"
        )
        path = filedialog.asksaveasfilename(
            title="Export timeline (contains media paths and selected subtitle text)",
            defaultextension=".fcpxml",
            filetypes=[("Final Cut Pro XML", "*.fcpxml"), ("XML", "*.xml")],
            initialfile=default_name,
        )
        if not path:
            return
        timeline_name = self.query_var.get().strip() or "Subtitle compilation"
        try:
            export_matches(
                selected,
                Path(path),
                timeline_name,
                probe_func=lambda video: probe_media(video, ffprobe=str(self.ffprobe_path)),
                include_titles=include_titles,
                title_style=self.title_style if include_titles else None,
            )
        except (UnresolvedPairingError, MediaProbeError, ValueError, OSError) as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        kind = "clips with editable titles" if include_titles else "clips"
        messagebox.showinfo(
            "Export complete",
            f"Timeline written to:\n{path}\n\n"
            "This file contains absolute media paths, clip names, and your search term; "
            "title exports also contain selected subtitle text. Review it before sharing.",
        )
        self.status_var.set(f"Exported {len(selected)} {kind} to {Path(path).name}.")


def _environment_check() -> int:
    print(f"Python: {sys.version.split()[0]}")
    print("Tkinter: available")
    ffprobe = find_ffprobe()
    if ffprobe:
        print(f"ffprobe: {ffprobe}")
    else:
        print("ffprobe: NOT FOUND (search works; timeline export requires FFmpeg/ffprobe)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.check:
        return _environment_check()
    app = SubtitleDavinciApp()
    app.mainloop()
    return 0
