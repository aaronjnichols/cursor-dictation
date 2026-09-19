from __future__ import annotations

import ctypes

import pytest

from cursor_dictation.platform.windows.hotkeys import (
    KBDLLHOOKSTRUCT,
    WM_KEYDOWN,
    WM_KEYUP,
    Hotkey,
    HotkeyBindings,
    HotkeyParseError,
    WindowsHotkeyService,
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


def test_hold_hook_consumes_owned_chord_but_chains_unrelated_keys(
    qapp,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    class FakeUser32:
        def __init__(self) -> None:
            self.callback = None
            self.modifiers_down = True
            self.chained = 0

        def RegisterHotKey(self, *_args: object) -> bool:
            return True

        def UnregisterHotKey(self, *_args: object) -> bool:
            return True

        def SetWindowsHookExW(self, _kind, callback, _module, _thread):  # type: ignore[no-untyped-def]
            self.callback = callback
            return 99

        def UnhookWindowsHookEx(self, _hook: object) -> bool:
            return True

        def GetAsyncKeyState(self, _key: int) -> int:
            return 0x8000 if self.modifiers_down else 0

        def CallNextHookEx(self, *_args: object) -> int:
            self.chained += 1
            return 77

    class FakeKernel32:
        def GetModuleHandleW(self, _name: object) -> int:
            return 1

    user32 = FakeUser32()
    monkeypatch.setattr(ctypes.windll, "user32", user32)
    monkeypatch.setattr(ctypes.windll, "kernel32", FakeKernel32())
    service = WindowsHotkeyService()
    bindings = HotkeyBindings.defaults()
    pressed: list[bool] = []
    released: list[bool] = []
    service.hold_pressed.connect(lambda: pressed.append(True))
    service.hold_released.connect(lambda: released.append(True))
    service.configure(bindings)
    callback = user32.callback
    assert callback is not None
    owned = KBDLLHOOKSTRUCT(vkCode=bindings.hold.virtual_key)

    assert callback(0, WM_KEYDOWN, ctypes.addressof(owned)) == 1
    assert callback(0, WM_KEYDOWN, ctypes.addressof(owned)) == 1
    assert pressed == [True]
    assert callback(0, WM_KEYUP, ctypes.addressof(owned)) == 1
    assert released == [True]

    unrelated = KBDLLHOOKSTRUCT(vkCode=ord("A"))
    assert callback(0, WM_KEYDOWN, ctypes.addressof(unrelated)) == 77
    user32.modifiers_down = False
    assert callback(0, WM_KEYDOWN, ctypes.addressof(owned)) == 77
    assert user32.chained == 2
    service.close()
