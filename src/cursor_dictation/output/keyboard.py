from __future__ import annotations

import ctypes
from ctypes import wintypes

from cursor_dictation.output.delivery import PartialUnicodeInputError

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11
VK_RETURN = 0x0D
VK_V = 0x56

ULONG_PTR = wintypes.WPARAM


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    # The union must include its largest Windows member. Keeping only
    # KEYBDINPUT makes INPUT eight bytes too small on 64-bit Windows, and
    # SendInput rejects every event with ERROR_INVALID_PARAMETER.
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUT_UNION)]


class Win32Keyboard:
    def __init__(self) -> None:
        self._send_input = ctypes.windll.user32.SendInput
        self._send_input.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self._send_input.restype = wintypes.UINT

    def send_paste(self) -> bool:
        return self._send(
            self._virtual_key(VK_CONTROL),
            self._virtual_key(VK_V),
            self._virtual_key(VK_V, key_up=True),
            self._virtual_key(VK_CONTROL, key_up=True),
        )

    def send_unicode(self, text: str) -> bool:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        for character_index, character in enumerate(normalized):
            if character == "\n":
                try:
                    sent = self._send(
                        self._virtual_key(VK_RETURN),
                        self._virtual_key(VK_RETURN, key_up=True),
                    )
                except Exception as error:
                    raise PartialUnicodeInputError(
                        remaining_text=normalized[character_index:]
                    ) from error
                if not sent:
                    raise PartialUnicodeInputError(remaining_text=normalized[character_index:])
                continue
            encoded = character.encode("utf-16-le")
            for offset in range(0, len(encoded), 2):
                code_unit = int.from_bytes(encoded[offset : offset + 2], "little")
                try:
                    sent = self._send(
                        self._unicode_key(code_unit),
                        self._unicode_key(code_unit, key_up=True),
                    )
                except Exception as error:
                    raise PartialUnicodeInputError(
                        remaining_text=normalized[character_index:]
                    ) from error
                if not sent:
                    raise PartialUnicodeInputError(remaining_text=normalized[character_index:])
        return True

    def _send(self, *inputs: INPUT) -> bool:
        values = (INPUT * len(inputs))(*inputs)
        sent = int(self._send_input(len(values), values, ctypes.sizeof(INPUT)))
        return sent == len(values)

    @staticmethod
    def _virtual_key(virtual_key: int, *, key_up: bool = False) -> INPUT:
        flags = KEYEVENTF_KEYUP if key_up else 0
        return INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=virtual_key,
                wScan=0,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )

    @staticmethod
    def _unicode_key(code_unit: int, *, key_up: bool = False) -> INPUT:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
        return INPUT(
            type=INPUT_KEYBOARD,
            ki=KEYBDINPUT(
                wVk=0,
                wScan=code_unit,
                dwFlags=flags,
                time=0,
                dwExtraInfo=0,
            ),
        )
