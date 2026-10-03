"""A frame-scaled title preview and selection-only font picker, using local Tk."""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass
from tkinter import font as tkfont
from tkinter import ttk

from .style import TitleStyle


@dataclass(frozen=True, slots=True)
class PreviewGeometry:
    frame: tuple[float, float, float, float]
    position: tuple[float, float]
    font_pixels: float
    outline_pixels: float


def preview_geometry(
    viewport_width: int,
    viewport_height: int,
    frame_width: int,
    frame_height: int,
    style: TitleStyle,
) -> PreviewGeometry:
    if min(viewport_width, viewport_height, frame_width, frame_height) <= 0:
        raise ValueError("Preview and frame dimensions must be positive")
    scale = min(viewport_width / frame_width, viewport_height / frame_height)
    width, height = frame_width * scale, frame_height * scale
    left, top = (viewport_width - width) / 2, (viewport_height - height) / 2
    return PreviewGeometry(
        frame=(left, top, width, height),
        position=(
            left + width * (0.5 + style.position_x_fraction),
            top + height * (0.5 - style.position_y_fraction),
        ),
        font_pixels=style.font_size * scale,
        outline_pixels=style.stroke_width * scale,
    )


class FontPicker(ttk.Combobox):
    """Typing searches installed families; it never edits the selected name."""

    def __init__(self, master, **kwargs):
        kwargs["state"] = "readonly"
        super().__init__(master, **kwargs)
        self._prefix = ""
        self._last_key_time = 0
        self._popup_listbox = None
        self.configure(postcommand=self._bind_popup_search)
        self.bind("<KeyPress>", self.on_keypress)
        self.bind("<FocusOut>", lambda _event: self._reset_search())

    def _reset_search(self) -> None:
        self._prefix = ""
        self._last_key_time = 0

    def _bind_popup_search(self) -> None:
        # Tk gives the native popup's listbox keyboard focus while it is posted.
        popup = self.tk.call("ttk::combobox::PopdownWindow", str(self))
        listbox = str(popup) + ".f.l"
        if listbox != self._popup_listbox:
            self._popup_listbox = listbox
            self._bind(("bind", listbox), "<KeyPress>", self.on_keypress, None)

    def on_keypress(self, event):
        if event.keysym == "BackSpace":
            self._prefix = self._prefix[:-1]
            return "break"
        if not event.char or not event.char.isprintable():
            return None
        char = event.char.casefold()
        elapsed = event.time - self._last_key_time
        if elapsed < 0 or elapsed > 1000:
            self._prefix = ""
        self._last_key_time = event.time
        prefix = self._prefix + char
        values = self.cget("values")
        matches = [i for i, value in enumerate(values) if value.casefold().startswith(prefix)]
        if not matches:
            prefix = char
            matches = [i for i, value in enumerate(values) if value.casefold().startswith(prefix)]
        if matches:
            current = self.current()
            if prefix == self._prefix:
                index = next((i for i in matches if i > current), matches[0])
            else:
                index = matches[0]
            self._prefix = prefix
            self.current(index)
            if self._popup_listbox is not None:
                self.tk.call(self._popup_listbox, "selection", "clear", 0, "end")
                self.tk.call(self._popup_listbox, "selection", "set", index)
                self.tk.call(self._popup_listbox, "activate", index)
                self.tk.call(self._popup_listbox, "see", index)
            self.event_generate("<<ComboboxSelected>>")
        return "break"


class TitlePreview(tk.Canvas):
    def __init__(self, master, *, frame_width=1920, frame_height=1080, **kwargs):
        super().__init__(master, background="#17191D", highlightthickness=0, bd=0, **kwargs)
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.style = TitleStyle()
        self.text = "Sample subtitle"
        self.error = None
        self.display_font = tkfont.Font(root=self, family="Arial", size=-1)
        self.bind("<Configure>", lambda _event: self.redraw())

    def set_title(self, style: TitleStyle, text: str) -> None:
        self.style, self.text = style, text
        self.error = None
        self.redraw()

    def show_error(self, message: str) -> None:
        self.error = message
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 1 or height <= 1:
            width, height = int(self.cget("width")), int(self.cget("height"))
        if self.error is not None:
            self.create_text(
                width / 2,
                height / 2,
                text=self.error,
                fill="#FFDDDD",
                font=("Arial", -16, "bold"),
                width=0,
                tags="error",
            )
            return
        geometry = preview_geometry(width, height, self.frame_width, self.frame_height, self.style)
        left, top, frame_width, frame_height = geometry.frame
        self.create_rectangle(
            left,
            top,
            left + frame_width,
            top + frame_height,
            fill="#707070",
            outline="",
            tags="frame",
        )
        self.display_font.configure(
            family=self.style.font,
            # Negative Tk sizes are pixels and are independent of desktop DPI.
            size=-max(1, round(geometry.font_pixels)),
            weight="bold" if "Bold" in self.style.font_face else "normal",
            slant="italic" if "Italic" in self.style.font_face else "roman",
        )
        x, y = geometry.position
        options = {
            "text": self.text,
            "font": self.display_font,
            "anchor": {"left": "w", "center": "center", "right": "e"}[self.style.alignment],
            "justify": self.style.alignment,
            # Resolve Basic Titles preserve explicit lines, with no widget wrap.
            "width": 0,
        }
        radius = geometry.outline_pixels
        if radius > 0:
            for step in range(16):
                angle = 2 * math.pi * step / 16
                self.create_text(
                    x + radius * math.cos(angle),
                    y + radius * math.sin(angle),
                    fill=self.style.stroke_color,
                    tags="outline",
                    **options,
                )
        self.create_text(x, y, fill=self.style.font_color, tags="title", **options)
        # Mask the letterbox areas so text clips at the actual frame edges.
        for bounds in (
            (0, 0, left, height),
            (left + frame_width, 0, width, height),
            (left, 0, left + frame_width, top),
            (left, top + frame_height, left + frame_width, height),
        ):
            self.create_rectangle(*bounds, fill="#17191D", outline="", tags="matte")
