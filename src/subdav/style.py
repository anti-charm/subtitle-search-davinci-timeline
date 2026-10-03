from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, fields


def _compact(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.3f}".rstrip("0").rstrip(".")


def to_fcp_color(value: str, alpha: float = 1.0) -> str:
    value = value.strip()
    if not value.startswith("#"):
        parts = value.split()
        if len(parts) == 3:
            parts.append(_compact(alpha))
        return " ".join(parts)

    raw = value[1:]
    if len(raw) not in (6, 8):
        raise ValueError(f"invalid hex colour: {value!r}")
    red = int(raw[0:2], 16) / 255.0
    green = int(raw[2:4], 16) / 255.0
    blue = int(raw[4:6], 16) / 255.0
    actual_alpha = int(raw[6:8], 16) / 255.0 if len(raw) == 8 else alpha
    return " ".join(_compact(channel) for channel in (red, green, blue, actual_alpha))


@dataclass(frozen=True, slots=True)
class TitleStyle:
    # Conservative, movie-like defaults. Arial is widely installed on Windows
    # and supports both Latin and Hebrew without requiring a decorative face.
    font: str = "Arial"
    font_size: int = 48
    font_face: str = "Regular"
    font_color: str = "#FFFFFF"
    stroke_color: str = "#000000"
    stroke_width: float = 0.08
    alignment: str = "center"
    # Fractions of the frame from centre. Negative Y means lower on screen.
    position_y_fraction: float = -0.36
    position_x_fraction: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.font, str) or not self.font.strip() or len(self.font) > 200:
            raise ValueError("invalid font name")
        if type(self.font_size) is not int or not 1 <= self.font_size <= 300:
            raise ValueError("font size must be between 1 and 300")
        if self.font_face not in ("Regular", "Bold", "Italic", "Bold Italic"):
            raise ValueError("invalid font face")
        if self.alignment not in ("left", "center", "right"):
            raise ValueError("invalid alignment")
        for color in (self.font_color, self.stroke_color):
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("colors must be six-digit hex values")
        for value in (self.position_x_fraction, self.position_y_fraction, self.stroke_width):
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("style values must be finite numbers")
        if not (
            -0.45 <= self.position_x_fraction <= 0.45
            and -0.46 <= self.position_y_fraction <= 0.30
            and 0 <= self.stroke_width <= 10
        ):
            raise ValueError("style value outside supported range")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @classmethod
    def from_json(cls, text: str) -> "TitleStyle":
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("title style must be a JSON object")
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    def text_style_attrs(self) -> dict[str, str]:
        attrs = {
            "font": self.font,
            "fontSize": str(self.font_size),
            "fontFace": self.font_face,
            "fontColor": to_fcp_color(self.font_color),
            "alignment": self.alignment,
        }
        if self.stroke_width > 0:
            attrs["strokeColor"] = to_fcp_color(self.stroke_color)
            attrs["strokeWidth"] = _compact(self.stroke_width)
        return attrs

    def transform_position(self, width: int, height: int) -> str:
        if height <= 0:
            return "0 0"
        # FCPXML adjust-transform uses units of 1% of frame height for both axes.
        # Convert our intuitive frame-width X fraction and frame-height Y fraction.
        x_units = 100.0 * (width / height) * self.position_x_fraction
        y_units = 100.0 * self.position_y_fraction
        return f"{_compact(x_units)} {_compact(y_units)}"

    # Compatibility helper for older internal callers; new exports use
    # adjust-transform rather than Basic Title's template-specific Position key.
    def position(self, width: int, height: int) -> str:
        return self.transform_position(width, height)
