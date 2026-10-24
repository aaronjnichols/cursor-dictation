from cursor_dictation.ui.theme import COLORS, build_stylesheet, palette_accent


def test_theme_uses_approved_color_tokens() -> None:
    assert COLORS.background == "#120F0E"
    assert COLORS.primary == "#DA7C47"
    assert COLORS.success == "#76AD4F"
    assert COLORS.foreground == "#C9C5BA"

    stylesheet = build_stylesheet("chamber")

    assert COLORS.background in stylesheet
    assert COLORS.primary in stylesheet
    assert COLORS.foreground in stylesheet


def test_warm_white_palette_applies_to_every_settings_accent() -> None:
    accent = palette_accent("warm_white")
    stylesheet = build_stylesheet("warm_white")

    assert f"background-color: {accent};" in stylesheet
    assert f"selection-background-color: {accent};" in stylesheet
    assert f"color: {accent};" in stylesheet


def test_theme_uses_custom_outlined_checkbox_indicator() -> None:
    stylesheet = build_stylesheet("chamber")

    assert "QCheckBox::indicator:checked" not in stylesheet
    assert "QCheckBox:hover" in stylesheet
    assert "QMainWindow#settingsWindow" in stylesheet
