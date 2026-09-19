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
