from __future__ import annotations

import subprocess
import winreg
from typing import Protocol

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


class RegistryPort(Protocol):
    def read(self, name: str) -> str | None: ...

    def write(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class WinRegistry:
    def read(self, name: str) -> str | None:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                value, _ = winreg.QueryValueEx(key, name)
        except FileNotFoundError:
            return None
        return str(value)

    def write(self, name: str, value: str) -> None:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            access=winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    def delete(self, name: str) -> None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _RUN_KEY,
                access=winreg.KEY_SET_VALUE,
            ) as key:
                winreg.DeleteValue(key, name)
        except FileNotFoundError:
            return


class StartupManager:
    _VALUE_NAME = "Cursor Dictation"

    def __init__(
        self,
        registry: RegistryPort,
        executable_path: str,
        *,
        base_arguments: tuple[str, ...] = (),
    ) -> None:
        self._registry = registry
        arguments = subprocess.list2cmdline([*base_arguments, "--startup"])
        self._command = f"{quote_windows_argument(executable_path)} {arguments}"

    def is_enabled(self) -> bool:
        return self._registry.read(self._VALUE_NAME) == self._command

    def set_enabled(self, enabled: bool) -> None:
        if enabled:
            self._registry.write(self._VALUE_NAME, self._command)
            return
        if self._registry.read(self._VALUE_NAME) == self._command:
            self._registry.delete(self._VALUE_NAME)


def quote_windows_argument(value: str) -> str:
    quoted = subprocess.list2cmdline([value])
    if quoted.startswith('"'):
        return quoted
    return f'"{quoted}"'
