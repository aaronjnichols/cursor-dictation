from __future__ import annotations

from dataclasses import dataclass

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008


class HotkeyParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Hotkey:
    modifiers: int
    virtual_key: int
    canonical: str


@dataclass(frozen=True, slots=True)
class HotkeyBindings:
    hold: Hotkey
    toggle: Hotkey
    copy: Hotkey
    cancel: Hotkey

    @classmethod
    def defaults(cls) -> HotkeyBindings:
        return cls(
            hold=parse_hotkey("Ctrl+Alt+Space"),
            toggle=parse_hotkey("Ctrl+Alt+D"),
            copy=parse_hotkey("Ctrl+Alt+C"),
            cancel=parse_hotkey("Ctrl+Alt+Escape"),
        )


_MODIFIERS = {
    "ctrl": (MOD_CONTROL, "Ctrl"),
    "control": (MOD_CONTROL, "Ctrl"),
    "alt": (MOD_ALT, "Alt"),
    "shift": (MOD_SHIFT, "Shift"),
    "win": (MOD_WIN, "Win"),
    "windows": (MOD_WIN, "Win"),
}
_NAMED_KEYS = {
    "space": (0x20, "Space"),
    "escape": (0x1B, "Escape"),
    "esc": (0x1B, "Escape"),
    "tab": (0x09, "Tab"),
    "enter": (0x0D, "Enter"),
    "backspace": (0x08, "Backspace"),
}


def parse_hotkey(text: str) -> Hotkey:
    tokens = [token.strip() for token in text.split("+")]
    if not tokens or any(not token for token in tokens):
        raise HotkeyParseError("A shortcut must contain modifiers and one key.")

    modifiers = 0
    modifier_names: set[str] = set()
    key: tuple[int, str] | None = None
    for token in tokens:
        normalized = token.casefold()
        if normalized in _MODIFIERS:
            flag, name = _MODIFIERS[normalized]
            modifiers |= flag
            modifier_names.add(name)
            continue
        if key is not None:
            raise HotkeyParseError("A shortcut must contain exactly one non-modifier key.")
        if normalized in _NAMED_KEYS:
            key = _NAMED_KEYS[normalized]
        elif len(token) == 1 and token.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
            key = (ord(token.upper()), token.upper())
        elif normalized.startswith("f") and normalized[1:].isdigit():
            function_number = int(normalized[1:])
            if not 1 <= function_number <= 24:
                raise HotkeyParseError("Function keys must be between F1 and F24.")
            key = (0x6F + function_number, f"F{function_number}")
        else:
            raise HotkeyParseError(f"Unsupported shortcut key: {token}")

    if modifiers == 0 or key is None:
        raise HotkeyParseError("A shortcut must contain modifiers and one key.")
    ordered_names = [name for name in ("Ctrl", "Alt", "Shift", "Win") if name in modifier_names]
    canonical = "+".join((*ordered_names, key[1]))
    return Hotkey(modifiers=modifiers, virtual_key=key[0], canonical=canonical)


def ensure_unique(bindings: HotkeyBindings) -> None:
    values = (bindings.hold, bindings.toggle, bindings.copy, bindings.cancel)
    signatures = {(hotkey.modifiers, hotkey.virtual_key) for hotkey in values}
    if len(signatures) != len(values):
        raise ValueError("Hotkey bindings contain a duplicate shortcut.")
