from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from cursor_dictation.application.coordinator import ApplicationCoordinator
from cursor_dictation.application.qt_tasks import CancelCheck, ProgressCallback, TaskFunction
from cursor_dictation.audio.recorder import AudioDevice, RecordingCompletionReason
from cursor_dictation.core.hotkeys import HotkeyBindings
from cursor_dictation.core.models import (
    AppState,
    DeliveryMethod,
    DeliveryResult,
    RecordedAudio,
    Transcript,
)
from cursor_dictation.platform.windows.paths import AppPaths
from cursor_dictation.settings.history import JsonlHistoryStore
from cursor_dictation.settings.store import JsonSettingsStore
from cursor_dictation.settings.vocabulary import VocabularyStore
from cursor_dictation.transcription.engine import ModelInfo
from cursor_dictation.transcription.model_manager import ModelManager


class ImmediateTaskRunner(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.is_running = False
        self.cancelled = False

    def start(self, task: TaskFunction) -> None:
        if self.is_running:
            raise RuntimeError("already running")
        self.is_running = True
        self.cancelled = False
        try:
            result = task(self._progress, self._cancel_check)
        except Exception as error:
            self.is_running = False
            self.failed.emit(error)
            return
        self.is_running = False
        self.succeeded.emit(result)

    def cancel(self) -> None:
        self.cancelled = True

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        self.cancel()
        return True

    def _progress(self, percent: int, message: str) -> None:
        self.progress.emit(percent, message)

    def _cancel_check(self) -> bool:
        return self.cancelled


class FakeEngine:
    def __init__(self) -> None:
        self.path: Path | None = None

    def load(self, model_path: Path) -> ModelInfo:
        self.path = model_path.resolve()
        return ModelInfo(path=self.path, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        return Transcript("fixture transcript")


class FakeInstaller:
    def __init__(self, models_root: Path, *, installed: bool) -> None:
        self.target_directory = models_root / "small.en"
        self._installed = installed

    def is_installed(self) -> bool:
        return self._installed

    def install(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCheck | None = None,
    ) -> Path:
        if cancel_requested is not None and cancel_requested():
            raise RuntimeError("cancelled")
        self.target_directory.mkdir(parents=True, exist_ok=True)
        self._installed = True
        if progress is not None:
            progress(100, "Model verified")
        return self.target_directory


class FakeRecorder:
    def __init__(self) -> None:
        self.devices = (
            AudioDevice(
                id="wasapi:built-in",
                name="Built-in microphone",
                max_input_channels=2,
                default_sample_rate=48_000,
                is_default=True,
            ),
        )

    def list_devices(self) -> tuple[AudioDevice, ...]:
        return self.devices

    def start(self, device_id: str | None) -> None:
        pass

    def stop(self) -> RecordedAudio:
        return RecordedAudio(samples=(0.1,), sample_rate=16_000, channels=1)

    def cancel(self) -> None:
        pass

    def wait_for_completion(
        self,
        timeout: float | None = None,
    ) -> RecordingCompletionReason | None:
        return None


class FakeHotkeys(QObject):
    hold_pressed = Signal()
    hold_released = Signal()
    toggle_pressed = Signal()
    copy_pressed = Signal()
    cancel_pressed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.configurations: list[HotkeyBindings] = []
        self.closed = False

    def configure(self, bindings: HotkeyBindings) -> None:
        self.configurations.append(bindings)

    def close(self) -> None:
        self.closed = True


class FakeStartupManager:
    def __init__(self) -> None:
        self.enabled_values: list[bool] = []

    def set_enabled(self, enabled: bool) -> None:
        self.enabled_values.append(enabled)


class FakeDelivery:
    def insert_at_cursor(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_COPY)


def make_coordinator(
    tmp_path: Path, *, installed: bool
) -> tuple[
    ApplicationCoordinator,
    FakeHotkeys,
    JsonSettingsStore,
    VocabularyStore,
    JsonlHistoryStore,
]:
    application = QApplication.instance()
    assert isinstance(application, QApplication)
    paths = AppPaths.from_root(tmp_path / "data")
    paths.ensure_directories()
    settings_store = JsonSettingsStore(paths.settings_file)
    vocabulary_store = VocabularyStore(paths.vocabulary_file)
    history = JsonlHistoryStore(paths.history_file)
    hotkeys = FakeHotkeys()
    manager = ModelManager(engine_factory=FakeEngine)
    default_installer = FakeInstaller(paths.models_dir, installed=installed)
    if installed:
        default_installer.target_directory.mkdir(parents=True)

    def installer_factory(models_root: Path) -> FakeInstaller:
        if models_root.resolve() == paths.models_dir.resolve():
            return default_installer
        return FakeInstaller(models_root, installed=False)

    coordinator = ApplicationCoordinator(
        application=application,
        paths=paths,
        settings_store=settings_store,
        vocabulary_store=vocabulary_store,
        history=history,
        recorder=FakeRecorder(),
        model_manager=manager,
        installer_factory=installer_factory,
        hotkeys=hotkeys,
        startup_manager=FakeStartupManager(),
        task_runner=ImmediateTaskRunner(),
        delivery=FakeDelivery(),
    )
    return coordinator, hotkeys, settings_store, vocabulary_store, history


def test_first_run_waits_for_model_before_enabling_dictation(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)

    coordinator.start()

    assert coordinator.state is AppState.FIRST_RUN_SETUP
    assert coordinator.setup_window.isVisible()
    assert not coordinator.tray.start_action.isEnabled()
    assert hotkeys.configurations == []
    coordinator.close()


def test_installed_model_starts_ready_runtime_and_registers_hotkeys(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, _, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)

    coordinator.start()

    assert coordinator.state is AppState.IDLE
    assert coordinator.runtime is not None
    assert coordinator.tray.start_action.isEnabled()
    assert len(hotkeys.configurations) == 1
    coordinator.close()
    assert hotkeys.closed


def test_first_run_install_persists_microphone_and_becomes_ready(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()
    coordinator.setup_window.microphone.setCurrentIndex(1)

    coordinator.setup_window.install_button.click()

    assert coordinator.state is AppState.IDLE
    assert settings_store.load().microphone_device_id == "wasapi:built-in"
    assert len(hotkeys.configurations) == 1
    coordinator.close()


def test_settings_save_updates_persistence_vocabulary_and_runtime(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, vocabulary_store, history = make_coordinator(
        tmp_path,
        installed=True,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.hold_hotkey.setText("Ctrl+Shift+Space")
    coordinator.settings_window.history_enabled.setChecked(True)
    coordinator.settings_window.vocabulary_editor.setPlainText("HEC-RAS\nFLO-2D")

    coordinator.save_settings()

    assert settings_store.load().hold_to_talk_hotkey == "Ctrl+Shift+Space"
    assert vocabulary_store.load() == ("HEC-RAS", "FLO-2D")
    assert history.enabled
    assert hotkeys.configurations[-1].hold.canonical == "Ctrl+Shift+Space"
    assert coordinator.settings_window.status_text == "Saved"
    coordinator.close()
