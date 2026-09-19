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


def test_source_launch_can_include_module_arguments() -> None:
    registry = FakeRegistry()
    manager = StartupManager(
        registry,
        "C:\\Python311\\pythonw.exe",
        base_arguments=("-m", "cursor_dictation"),
    )

    manager.set_enabled(True)

    assert registry.value == '"C:\\Python311\\pythonw.exe" -m cursor_dictation --startup'


def test_disable_removes_stale_owned_value_after_executable_moves() -> None:
    registry = FakeRegistry(value='"D:\\Old Folder\\Cursor Dictation.exe" --startup')
    manager = StartupManager(registry, "C:\\New Folder\\Cursor Dictation.exe")

    manager.set_enabled(False)

    assert registry.value is None
    assert registry.delete_count == 1


def test_quote_windows_argument_escapes_embedded_quotes() -> None:
    assert quote_windows_argument('C:\\odd "folder"\\app.exe') == '"C:\\odd \\"folder\\"\\app.exe"'
