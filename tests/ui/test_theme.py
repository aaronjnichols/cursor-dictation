from cursor_dictation.ui.theme import COLORS, build_stylesheet


def test_theme_uses_approved_color_tokens() -> None:
    assert COLORS.background == "#151313"
    assert COLORS.primary == "#EDB449"
    assert COLORS.foreground == "#CECDC3"

    stylesheet = build_stylesheet()

    assert COLORS.background in stylesheet
    assert COLORS.primary in stylesheet
    assert COLORS.foreground in stylesheet
