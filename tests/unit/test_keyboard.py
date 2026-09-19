from __future__ import annotations

import ctypes

import pytest

from cursor_dictation.output.delivery import PartialUnicodeInputError
from cursor_dictation.output.keyboard import INPUT, Win32Keyboard


def test_input_structure_matches_the_windows_abi() -> None:
    expected_size = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28

    assert ctypes.sizeof(INPUT) == expected_size


def test_unicode_failure_reports_only_characters_not_yet_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyboard = Win32Keyboard()
    results = iter((True, False))
    monkeypatch.setattr(keyboard, "_send", lambda *_inputs: next(results))

    with pytest.raises(PartialUnicodeInputError) as captured:
        keyboard.send_unicode("ab")

    assert captured.value.remaining_text == "b"
