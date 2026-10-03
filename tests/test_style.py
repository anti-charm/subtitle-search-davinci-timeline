import pytest

from subdav.style import TitleStyle, to_fcp_color


def test_title_style_defaults_are_clean_movie_subtitles():
    style = TitleStyle()
    assert style.font == "Arial"
    assert style.font_size == 48
    assert style.font_face == "Regular"
    assert style.font_color == "#FFFFFF"
    assert style.stroke_color == "#000000"
    assert style.stroke_width == 1
    assert style.alignment == "center"
    assert style.position_x_fraction == 0.0
    assert style.position_y_fraction == -0.36


def test_title_style_round_trips_json_and_ignores_unknown_fields():
    style = TitleStyle(font="Arial", font_size=54, font_color="#12AB34", position_y_fraction=-0.2)
    restored = TitleStyle.from_json(style.to_json())
    assert restored == style

    restored_extra = TitleStyle.from_json('{"font":"Arial","font_size":50,"future":123}')
    assert restored_extra.font == "Arial"
    assert restored_extra.font_size == 50


def test_hex_color_is_converted_to_fcpxml_rgba():
    assert to_fcp_color("#FFFFFF") == "1 1 1 1"
    assert to_fcp_color("#000000") == "0 0 0 1"
    assert to_fcp_color("#FF000080") == "1 0 0 0.502"


@pytest.mark.parametrize(
    "face,bold,italic",
    [("Regular", "0", "0"), ("Bold", "1", "0"), ("Italic", "0", "1"), ("Bold Italic", "1", "1")],
)
def test_export_encodes_explicit_font_traits(face, bold, italic):
    attrs = TitleStyle(font_face=face).text_style_attrs()
    assert attrs.get("bold") == bold
    assert attrs.get("italic") == italic


def test_default_outline_is_one_export_unit_and_can_be_disabled():
    assert TitleStyle().text_style_attrs()["strokeWidth"] == "1"
    assert "strokeWidth" not in TitleStyle(stroke_width=0).text_style_attrs()


def test_title_transform_position_uses_fraction_of_frame_and_fcpxml_percent_units():
    # adjust-transform positions are percentages of frame height.
    # Negative UI Y means lower on screen.
    assert TitleStyle().transform_position(1920, 1080) == "0 -36"
    assert (
        TitleStyle(position_x_fraction=0.10, position_y_fraction=0.25).transform_position(
            1920, 1080
        )
        == "17.778 25"
    )
