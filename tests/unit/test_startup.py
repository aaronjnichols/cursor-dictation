from __future__ import annotations

from dataclasses import dataclass

from cursor_dictation.platform.windows.startup import StartupManager, quote_windows_argument


@dataclass
class FakeRegistry:
    value: str | None = None
    delete_count: int = 0

    def read(self, name: str) -> str | None:
        return self.value

    def write(self, name: str, value: str) -> None:
        self.value = value

    def delete(self, name: str) -> None:
        self.delete_count += 1
        self.value = None


def test_enable_writes_quoted_executable_and_startup_flag() -> None:
    registry = FakeRegistry()
    manager = StartupManager(registry, "C:\\Program Files\\Cursor Dictation\\Cursor Dictation.exe")

    manager.set_enabled(True)

    assert registry.value == '"C:\\Program Files\\Cursor Dictation\\Cursor Dictation.exe" --startup'
    assert manager.is_enabled()


def test_disable_removes_only_owned_value() -> None:
    registry = FakeRegistry(value='"C:\\Other App\\other.exe"')
    manager = StartupManager(registry, "C:\\Cursor Dictation\\app.exe")

    manager.set_enabled(False)

    assert registry.value == '"C:\\Other App\\other.exe"'
    assert registry.delete_count == 0


def test_quote_windows_argument_escapes_embedded_quotes() -> None:
    assert quote_windows_argument('C:\\odd "folder"\\app.exe') == '"C:\\odd \\"folder\\"\\app.exe"'
