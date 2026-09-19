from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Signal

from cursor_dictation.core.hotkeys import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    Hotkey,
    HotkeyBindings,
    HotkeyParseError,
    ensure_unique,
    parse_hotkey,
)

__all__ = [
    "Hotkey",
    "HotkeyBindings",
    "HotkeyParseError",
    "HotkeyRegistrationError",
    "WindowsHotkeyService",
    "ensure_unique",
    "parse_hotkey",
]

MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WH_KEYBOARD_LL = 13


class HotkeyRegistrationError(RuntimeError):
    pass


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, handler: Callable[[int], None]) -> None:
        super().__init__()
        self._handler = handler

    def nativeEventFilter(self, event_type, message):  # type: ignore[no-untyped-def]
        if event_type in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == WM_HOTKEY:
                self._handler(int(native_message.wParam))
        return False, 0


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", wintypes.WPARAM),
    ]


class WindowsHotkeyService(QObject):
    hold_pressed = Signal()
    hold_released = Signal()
    toggle_pressed = Signal()
    copy_pressed = Signal()
    cancel_pressed = Signal()

    _TOGGLE_ID = 4101
    _COPY_ID = 4102
    _CANCEL_ID = 4103

    def __init__(self) -> None:
        super().__init__()
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._bindings: HotkeyBindings | None = None
        self._registered_ids: list[int] = []
        self._hold_down = False
        self._hook: int | None = None
        self._hook_callback: object | None = None
        self._native_filter = _NativeFilter(self._handle_registered_hotkey)
        application = QCoreApplication.instance()
        if application is None:
            raise RuntimeError("A Qt application must exist before registering hotkeys.")
        application.installNativeEventFilter(self._native_filter)

    def configure(self, bindings: HotkeyBindings) -> None:
        ensure_unique(bindings)
        previous = self._bindings
        self.close()
        try:
            self._apply(bindings)
        except Exception:
            self.close()
            if previous is not None:
                self._apply(previous)
            raise

    def close(self) -> None:
        for hotkey_id in self._registered_ids:
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._registered_ids.clear()
        if self._hook:
            self._user32.UnhookWindowsHookEx(self._hook)
            self._hook = None
        self._hook_callback = None
        self._hold_down = False
        self._bindings = None

    def _apply(self, bindings: HotkeyBindings) -> None:
        registered = (
            (self._TOGGLE_ID, bindings.toggle),
            (self._COPY_ID, bindings.copy),
            (self._CANCEL_ID, bindings.cancel),
        )
        for hotkey_id, hotkey in registered:
            result = self._user32.RegisterHotKey(
                None,
                hotkey_id,
                hotkey.modifiers | MOD_NOREPEAT,
                hotkey.virtual_key,
            )
            if not result:
                raise HotkeyRegistrationError(f"Windows rejected the {hotkey.canonical} shortcut.")
            self._registered_ids.append(hotkey_id)
        self._install_hold_hook(bindings.hold)
        self._bindings = bindings

    def _install_hold_hook(self, hold: Hotkey) -> None:
        callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_longlong,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )

        def callback(code: int, message: int, data_pointer: int) -> int:
            if code >= 0:
                data = ctypes.cast(
                    data_pointer,
                    ctypes.POINTER(KBDLLHOOKSTRUCT),
                ).contents
                if data.vkCode == hold.virtual_key:
                    if message in {WM_KEYDOWN, WM_SYSKEYDOWN}:
                        if not self._hold_down and self._modifiers_are_down(hold.modifiers):
                            self._hold_down = True
                            self.hold_pressed.emit()
                    elif message in {WM_KEYUP, WM_SYSKEYUP} and self._hold_down:
                        self._hold_down = False
                        self.hold_released.emit()
            return int(self._user32.CallNextHookEx(self._hook, code, message, data_pointer))

        self._hook_callback = callback_type(callback)
        module = self._kernel32.GetModuleHandleW(None)
        self._hook = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._hook_callback,
            module,
            0,
        )
        if not self._hook:
            raise HotkeyRegistrationError("Windows rejected the hold-to-talk keyboard hook.")

    def _modifiers_are_down(self, modifiers: int) -> bool:
        checks = (
            (MOD_CONTROL, (0x11,)),
            (MOD_ALT, (0x12,)),
            (MOD_SHIFT, (0x10,)),
            (MOD_WIN, (0x5B, 0x5C)),
        )
        for flag, virtual_keys in checks:
            if modifiers & flag and not any(
                self._user32.GetAsyncKeyState(key) & 0x8000 for key in virtual_keys
            ):
                return False
        return True

    def _handle_registered_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == self._TOGGLE_ID:
            self.toggle_pressed.emit()
        elif hotkey_id == self._COPY_ID:
            self.copy_pressed.emit()
        elif hotkey_id == self._CANCEL_ID:
            self.cancel_pressed.emit()
