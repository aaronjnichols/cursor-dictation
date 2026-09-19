from __future__ import annotations

import pytest

from cursor_dictation.platform.windows.hotkeys import (
    Hotkey,
    HotkeyBindings,
    HotkeyParseError,
    ensure_unique,
    parse_hotkey,
)


@pytest.mark.parametrize(
    ("text", "canonical"),
    [
        ("Ctrl+Alt+Space", "Ctrl+Alt+Space"),
        (" alt + ctrl + d ", "Ctrl+Alt+D"),
        ("Ctrl+Shift+F12", "Ctrl+Shift+F12"),
        ("Win+Escape", "Win+Escape"),
    ],
)
def test_parse_hotkey_normalizes_supported_shortcuts(text: str, canonical: str) -> None:
    assert parse_hotkey(text).canonical == canonical


@pytest.mark.parametrize("text", ["", "Ctrl", "Ctrl+Alt+", "Ctrl+Mouse1", "A+B"])
def test_parse_hotkey_rejects_invalid_shortcuts(text: str) -> None:
    with pytest.raises(HotkeyParseError):
        parse_hotkey(text)


def test_duplicate_bindings_are_rejected() -> None:
    duplicate = Hotkey(modifiers=3, virtual_key=32, canonical="Ctrl+Alt+Space")
    bindings = HotkeyBindings(
        hold=duplicate,
        toggle=duplicate,
        copy=parse_hotkey("Ctrl+Alt+C"),
        cancel=parse_hotkey("Ctrl+Alt+Escape"),
    )

    with pytest.raises(ValueError, match="duplicate"):
        ensure_unique(bindings)


def test_default_bindings_match_product_decisions() -> None:
    bindings = HotkeyBindings.defaults()

    assert bindings.hold.canonical == "Ctrl+Alt+Space"
    assert bindings.toggle.canonical == "Ctrl+Alt+D"
    assert bindings.copy.canonical == "Ctrl+Alt+C"
    assert bindings.cancel.canonical == "Ctrl+Alt+Escape"
