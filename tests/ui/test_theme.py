from cursor_dictation.ui.theme import COLORS, build_stylesheet


def test_theme_uses_approved_color_tokens() -> None:
    assert COLORS.background == "#120F0E"
    assert COLORS.primary == "#DA7C47"
    assert COLORS.success == "#76AD4F"
    assert COLORS.foreground == "#C9C5BA"

    stylesheet = build_stylesheet()

    assert COLORS.background in stylesheet
    assert COLORS.primary in stylesheet
    assert COLORS.foreground in stylesheet
