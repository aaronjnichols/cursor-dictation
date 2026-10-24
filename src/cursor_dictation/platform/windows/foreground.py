from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class Win32Foreground:
    def __init__(self) -> None:
        self._get_foreground_window = ctypes.windll.user32.GetForegroundWindow
        self._get_foreground_window.restype = wintypes.HWND
        self._get_window_thread_process_id = ctypes.windll.user32.GetWindowThreadProcessId
        self._get_window_thread_process_id.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self._get_window_thread_process_id.restype = wintypes.DWORD

    def belongs_to_current_process(self) -> bool:
        window = self._get_foreground_window()
        if not window:
            return False
        process_id = wintypes.DWORD()
        self._get_window_thread_process_id(window, ctypes.byref(process_id))
        return process_id.value == os.getpid()


def restore_and_activate_window(handle: int) -> None:
    """Restore a native window, including one first shown by a hidden process."""
    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.ShowWindow(handle, 9)  # SW_RESTORE overrides a hidden/minimized window.
    user32.SetForegroundWindow(handle)
