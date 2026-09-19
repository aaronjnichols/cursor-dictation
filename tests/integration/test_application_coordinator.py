from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from threading import Event

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
from cursor_dictation.settings.schema import AppSettings, ModelSource
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
        self.shutdown_calls: list[int] = []

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
        self.shutdown_calls.append(timeout_ms)
        self.cancel()
        return True

    def _progress(self, percent: int, message: str) -> None:
        self.progress.emit(percent, message)

    def _cancel_check(self) -> bool:
        return self.cancelled


class FakeEngine:
    def __init__(
        self,
        *,
        load_error: Exception | None = None,
        transcribe_gate: Event | None = None,
    ) -> None:
        self.path: Path | None = None
        self.load_error = load_error
        self.transcribe_gate = transcribe_gate

    def load(self, model_path: Path) -> ModelInfo:
        if self.load_error is not None:
            raise self.load_error
        self.path = model_path.resolve()
        return ModelInfo(path=self.path, device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        if self.transcribe_gate is not None:
            self.transcribe_gate.wait(timeout=5)
        return Transcript("fixture transcript")


class FakeInstaller:
    def __init__(self, models_root: Path, *, installed: bool) -> None:
        self.target_directory = models_root / "small.en"
        self._installed = installed

    def is_installed(self) -> bool:
        installed_files_are_valid = (
            self.target_directory / "cursor-dictation-manifest.json"
        ).is_file() and (self.target_directory / "model.bin").read_bytes() == b"verified-model"
        return self._installed or installed_files_are_valid

    def install(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCheck | None = None,
    ) -> Path:
        if cancel_requested is not None and cancel_requested():
            raise RuntimeError("cancelled")
        self.target_directory.mkdir(parents=True, exist_ok=True)
        (self.target_directory / "model.bin").write_bytes(b"verified-model")
        (self.target_directory / "cursor-dictation-manifest.json").write_text(
            "{}",
            encoding="utf-8",
        )
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
        self.started_device: str | None = None
        self.cancel_count = 0
        self.input_level = 0.42
        self.is_recording = False

    def list_devices(self) -> tuple[AudioDevice, ...]:
        return self.devices

    def start(self, device_id: str | None) -> None:
        self.started_device = device_id
        self.is_recording = True

    def stop(self) -> RecordedAudio:
        return RecordedAudio(samples=(0.1,), sample_rate=16_000, channels=1)

    def cancel(self) -> None:
        self.cancel_count += 1
        self.is_recording = False

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
        self.error: Exception | None = None
        self.configure_errors: list[Exception | None] = []

    def configure(self, bindings: HotkeyBindings) -> None:
        if self.configure_errors:
            error = self.configure_errors.pop(0)
            if error is not None:
                raise error
        if self.error is not None:
            raise self.error
        self.configurations.append(bindings)

    def close(self) -> None:
        self.closed = True


class FakeStartupManager:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.enabled_values: list[bool] = []
        self.error = error

    def set_enabled(self, enabled: bool) -> None:
        if self.error is not None:
            raise self.error
        self.enabled_values.append(enabled)


class FakeDelivery:
    def insert_at_cursor(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_COPY)


def make_coordinator(
    tmp_path: Path,
    *,
    installed: bool,
    startup_error: Exception | None = None,
    model_load_error: Exception | None = None,
    transcribe_gate: Event | None = None,
    task_runner: ImmediateTaskRunner | None = None,
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
    manager = ModelManager(
        engine_factory=lambda: FakeEngine(
            load_error=model_load_error,
            transcribe_gate=transcribe_gate,
        )
    )
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
        startup_manager=FakeStartupManager(error=startup_error),
        task_runner=task_runner or ImmediateTaskRunner(),
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


def test_first_run_setup_can_test_selected_microphone(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    recorder = coordinator._recorder  # type: ignore[attr-defined]
    assert isinstance(recorder, FakeRecorder)
    coordinator.start()
    coordinator.setup_window.microphone.setCurrentIndex(1)

    coordinator.setup_window.test_microphone_button.click()
    coordinator._poll_microphone_test()  # type: ignore[attr-defined]

    assert recorder.started_device == "wasapi:built-in"
    assert coordinator.setup_window.input_level.value() == 42
    coordinator._complete_microphone_test()  # type: ignore[attr-defined]
    assert coordinator.setup_window.progress_text == "Microphone test complete"
    assert recorder.cancel_count == 1
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


def test_first_run_model_load_failure_returns_setup_to_a_retryable_state(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, settings_store, _, _ = make_coordinator(
        tmp_path,
        installed=False,
        model_load_error=RuntimeError("engine could not load"),
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()

    coordinator.setup_window.install_button.click()

    assert coordinator.setup_window.isVisible()
    assert coordinator.setup_window.install_button.isEnabled()
    assert "engine could not load" in coordinator.setup_window.progress_text
    assert coordinator.runtime is None
    assert settings_store.load() == AppSettings()
    coordinator.close()


def test_first_run_settings_write_failure_returns_setup_to_a_retryable_state(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()

    monkeypatch.setattr(
        settings_store,
        "save",
        lambda _settings: (_ for _ in ()).throw(OSError("settings file is locked")),
    )
    coordinator.setup_window.install_button.click()

    assert coordinator.setup_window.isVisible()
    assert coordinator.setup_window.install_button.isEnabled()
    assert "settings file is locked" in coordinator.setup_window.progress_text
    assert coordinator.runtime is None
    coordinator.close()


def test_first_run_custom_model_save_arms_runtime(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    custom_model = tmp_path / "custom-model"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text(
        json.dumps({"language": "en"}),
        encoding="utf-8",
    )
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.set_custom_model_path(custom_model)

    coordinator.save_settings()

    assert coordinator.runtime is not None
    assert settings_store.load().model_path == str(custom_model)
    assert settings_store.load().model_source is ModelSource.CUSTOM
    assert len(hotkeys.configurations) == 1
    assert coordinator.state is AppState.IDLE
    assert not coordinator.settings_window.isVisible()
    coordinator.close()


def test_first_run_hotkey_conflict_does_not_persist_custom_model_settings(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    custom_model = tmp_path / "custom-model"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.set_custom_model_path(custom_model)
    hotkeys.error = RuntimeError("shortcut already in use")

    coordinator.save_settings()

    assert coordinator.runtime is None
    assert settings_store.load() == AppSettings()
    assert "shortcut" in coordinator.settings_window.status_text
    coordinator.close()


def test_startup_hotkey_failure_can_be_repaired_without_enabling_behind_settings(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    hotkeys.error = RuntimeError("shortcut already in use")
    coordinator.start()
    assert coordinator.runtime is None
    assert coordinator.settings_window.isVisible()
    hotkeys.error = None
    coordinator.settings_window.hold_hotkey.setText("Ctrl+Shift+Space")

    coordinator.save_settings()

    assert coordinator.runtime is not None
    assert coordinator.state is AppState.IDLE
    assert not coordinator.settings_window.isVisible()
    assert settings_store.load().hold_to_talk_hotkey == "Ctrl+Shift+Space"
    coordinator.close()


def test_external_recommended_install_is_verified_again_on_restart(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    external_root = tmp_path / "external-models"
    first, _, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(first.setup_window)
    qtbot.addWidget(first.settings_window)
    qtbot.addWidget(first.overlay)
    first.start()
    first.setup_window.set_install_location(external_root)
    first.setup_window.install_button.click()
    assert first.state is AppState.IDLE
    assert settings_store.load().model_path == str(external_root / "small.en")
    assert settings_store.load().model_source is ModelSource.RECOMMENDED
    first.close()

    restarted, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(restarted.setup_window)
    qtbot.addWidget(restarted.settings_window)
    qtbot.addWidget(restarted.overlay)
    restarted.start()

    assert restarted.state is AppState.IDLE
    assert restarted.runtime is not None
    restarted.close()


def test_tampered_external_recommended_install_is_rejected_on_restart(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    external_root = tmp_path / "external-models"
    first, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(first.setup_window)
    qtbot.addWidget(first.settings_window)
    qtbot.addWidget(first.overlay)
    first.start()
    first.setup_window.set_install_location(external_root)
    first.setup_window.install_button.click()
    first.close()
    (external_root / "small.en" / "model.bin").write_bytes(b"tampered")

    restarted, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(restarted.setup_window)
    qtbot.addWidget(restarted.settings_window)
    qtbot.addWidget(restarted.overlay)
    restarted.start()

    assert restarted.state is AppState.FIRST_RUN_SETUP
    assert restarted.runtime is None
    assert "verification" in restarted.setup_window.progress_text.lower()
    restarted.close()


def test_recommended_provenance_survives_deleted_marker_and_rejects_tampering(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    external_root = tmp_path / "external-models"
    first, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(first.setup_window)
    qtbot.addWidget(first.settings_window)
    qtbot.addWidget(first.overlay)
    first.start()
    first.setup_window.set_install_location(external_root)
    first.setup_window.install_button.click()
    first.close()
    model = external_root / "small.en"
    (model / "cursor-dictation-manifest.json").unlink()
    (model / "model.bin").write_bytes(b"tampered")

    restarted, _, _, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(restarted.setup_window)
    qtbot.addWidget(restarted.settings_window)
    qtbot.addWidget(restarted.overlay)
    restarted.start()

    assert restarted.state is AppState.FIRST_RUN_SETUP
    assert restarted.runtime is None
    restarted.close()


def test_missing_custom_model_can_fall_back_to_recommended_setup(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    settings_store.save(
        replace(
            AppSettings(),
            model_path=str(tmp_path / "deleted-custom-model"),
            model_source=ModelSource.CUSTOM,
        )
    )
    coordinator.start()
    assert coordinator.state is AppState.ERROR

    coordinator.settings_window.use_default_model_button.click()
    coordinator.save_settings()

    assert settings_store.load().model_source is ModelSource.CUSTOM
    assert coordinator.state is AppState.FIRST_RUN_SETUP
    assert coordinator.setup_window.isVisible()
    coordinator.setup_window.install_button.click()
    assert settings_store.load().model_path is None
    assert settings_store.load().model_source is ModelSource.RECOMMENDED
    assert coordinator.state is AppState.IDLE
    coordinator.close()


def test_legacy_custom_model_path_opens_settings_for_explicit_reselection(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    custom_model = tmp_path / "legacy-custom-model"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator, _, settings_store, _, _ = make_coordinator(tmp_path, installed=False)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    settings_store.path.write_text(
        json.dumps({"schema_version": 1, "model_path": str(custom_model)}),
        encoding="utf-8",
    )

    coordinator.start()

    assert coordinator.state is AppState.ERROR
    assert coordinator.settings_window.isVisible()
    assert "reselect" in coordinator.settings_window.status_text.lower()
    coordinator.settings_window.set_custom_model_path(custom_model)
    coordinator.save_settings()
    assert coordinator.state is AppState.IDLE
    assert settings_store.load().model_source is ModelSource.CUSTOM
    coordinator.close()


def test_recommended_install_commits_all_pending_settings_after_model_load(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    custom_model = tmp_path / "working-custom"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator, _, settings_store, vocabulary_store, _ = make_coordinator(
        tmp_path,
        installed=False,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    settings_store.save(
        replace(
            AppSettings(),
            model_path=str(custom_model),
            model_source=ModelSource.CUSTOM,
        )
    )
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.use_default_model_button.click()
    coordinator.settings_window.hold_hotkey.setText("Ctrl+Shift+Space")
    coordinator.settings_window.microphone.setCurrentIndex(1)
    coordinator.settings_window.vocabulary_editor.setPlainText("HEC-RAS\nFLO-2D")

    coordinator.save_settings()
    assert settings_store.load().model_source is ModelSource.CUSTOM
    coordinator.setup_window.install_button.click()

    saved = settings_store.load()
    assert saved.model_source is ModelSource.RECOMMENDED
    assert saved.hold_to_talk_hotkey == "Ctrl+Shift+Space"
    assert saved.microphone_device_id == "wasapi:built-in"
    assert vocabulary_store.load() == ("HEC-RAS", "FLO-2D")
    assert coordinator.state is AppState.IDLE
    coordinator.close()


def test_cancelling_recommended_model_switch_restores_previous_runtime(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    class HoldSecondTaskRunner(ImmediateTaskRunner):
        def __init__(self) -> None:
            super().__init__()
            self.starts = 0

        def start(self, task: TaskFunction) -> None:
            self.starts += 1
            if self.starts == 2:
                self.is_running = True
                return
            super().start(task)

        def finish_cancelled(self) -> None:
            self.is_running = False
            self.failed.emit(RuntimeError("cancelled"))

    custom_model = tmp_path / "working-custom"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    runner = HoldSecondTaskRunner()
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(
        tmp_path,
        installed=False,
        task_runner=runner,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    settings_store.save(
        replace(
            AppSettings(),
            model_path=str(custom_model),
            model_source=ModelSource.CUSTOM,
        )
    )
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.use_default_model_button.click()
    coordinator.save_settings()
    coordinator.setup_window.install_button.click()
    assert runner.is_running

    coordinator.setup_window.cancel_requested.emit()
    runner.finish_cancelled()

    assert not coordinator.setup_window.isVisible()
    assert coordinator.state is AppState.IDLE
    assert settings_store.load().model_source is ModelSource.CUSTOM
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: coordinator.state is AppState.RECORDING)
    assert coordinator.state is AppState.RECORDING
    hotkeys.cancel_pressed.emit()
    coordinator.close()


def test_model_switch_rollback_failure_stays_fail_closed_after_setup_cancel(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    custom_model = tmp_path / "working-custom"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(
        tmp_path,
        installed=False,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    settings_store.save(
        replace(
            AppSettings(),
            model_path=str(custom_model),
            model_source=ModelSource.CUSTOM,
        )
    )
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.use_default_model_button.click()
    coordinator.save_settings()
    hotkeys.configure_errors = [None, RuntimeError("old shortcut could not be restored")]
    monkeypatch.setattr(
        settings_store,
        "save",
        lambda _settings: (_ for _ in ()).throw(OSError("settings write failed")),
    )

    coordinator.setup_window.install_button.click()
    coordinator.setup_window.cancel_requested.emit()
    hotkeys.toggle_pressed.emit()

    assert coordinator.state is AppState.ERROR
    assert coordinator.settings_window.isVisible()
    assert coordinator.runtime is not None
    assert coordinator.runtime._enabled is False  # type: ignore[attr-defined]
    coordinator.close()


def test_startup_registry_failure_does_not_block_dictation_runtime(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, _, _, _ = make_coordinator(
        tmp_path,
        installed=True,
        startup_error=OSError("registry unavailable"),
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)

    coordinator.start()

    assert coordinator.state is AppState.IDLE
    assert coordinator.runtime is not None
    assert len(hotkeys.configurations) == 1
    assert "sign-in" in coordinator.settings_window.status_text.lower()
    coordinator.close()


def test_settings_cannot_open_during_recording_or_transcription(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    transcribe_gate = Event()
    coordinator, hotkeys, _, _, _ = make_coordinator(
        tmp_path,
        installed=True,
        transcribe_gate=transcribe_gate,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: coordinator.state is AppState.RECORDING)
    assert coordinator.state is AppState.RECORDING

    coordinator.show_settings()

    assert coordinator.state is AppState.RECORDING
    assert not coordinator.settings_window.isVisible()
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: coordinator.state is AppState.TRANSCRIBING)
    assert coordinator.state is AppState.TRANSCRIBING

    coordinator.show_settings()

    assert coordinator.state is AppState.TRANSCRIBING
    assert not coordinator.settings_window.isVisible()
    transcribe_gate.set()
    coordinator.close()


def test_reopening_visible_settings_preserves_unsaved_edits(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, _, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.hold_hotkey.setText("Ctrl+Shift+Space")

    coordinator.show_settings()

    assert coordinator.settings_window.hold_hotkey.text() == "Ctrl+Shift+Space"
    coordinator.close()


def test_invalid_model_task_result_restores_settings_editor(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    class InvalidSecondResultRunner(ImmediateTaskRunner):
        def __init__(self) -> None:
            super().__init__()
            self.starts = 0

        def start(self, task: TaskFunction) -> None:
            self.starts += 1
            if self.starts == 2:
                self.succeeded.emit(object())
                return
            super().start(task)

    runner = InvalidSecondResultRunner()
    coordinator, _, _, _, _ = make_coordinator(
        tmp_path,
        installed=True,
        task_runner=runner,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    custom_model = tmp_path / "custom-model"
    custom_model.mkdir()
    (custom_model / "model.bin").write_bytes(b"model")
    (custom_model / "config.json").write_text('{"language":"en"}', encoding="utf-8")
    (custom_model / "tokenizer.json").write_text("{}", encoding="utf-8")
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.set_custom_model_path(custom_model)

    coordinator.save_settings()

    assert coordinator.settings_window.save_button.isEnabled()
    assert "invalid result" in coordinator.settings_window.status_text
    coordinator.close()


def test_shutdown_waits_for_background_worker_and_ignores_late_callbacks(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    class DelayedShutdownRunner(ImmediateTaskRunner):
        def shutdown(self, timeout_ms: int = 5_000) -> bool:
            self.shutdown_calls.append(timeout_ms)
            return timeout_ms == -1

    runner = DelayedShutdownRunner()
    coordinator, _, _, _, _ = make_coordinator(
        tmp_path,
        installed=False,
        task_runner=runner,
    )
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()

    coordinator.close()
    runner.failed.emit(RuntimeError("late callback"))

    assert runner.shutdown_calls == [5_000, -1]
    assert not coordinator.setup_window.isVisible()
    assert not coordinator.settings_window.isVisible()


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


def test_hotkey_rollback_failure_stays_fail_closed_after_settings_close(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, hotkeys, settings_store, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.hold_hotkey.setText("Ctrl+Shift+Space")
    hotkeys.configure_errors = [None, RuntimeError("old shortcut could not be restored")]
    monkeypatch.setattr(
        settings_store,
        "save",
        lambda _settings: (_ for _ in ()).throw(OSError("settings write failed")),
    )

    coordinator.save_settings()
    coordinator.settings_window.close()
    hotkeys.toggle_pressed.emit()

    assert coordinator.state is AppState.ERROR
    assert "rollback failed" in coordinator.settings_window.status_text
    assert coordinator.runtime is not None
    assert coordinator.runtime._enabled is False  # type: ignore[attr-defined]
    coordinator.close()


def test_settings_history_can_be_copied_and_cleared(qtbot, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, _, _, history = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    history.enabled = True
    history.append("Saved transcript", "copy")
    coordinator.start()

    coordinator.show_settings()
    coordinator.settings_window.history_list.setCurrentRow(0)
    coordinator.settings_window.copy_history_button.click()

    assert coordinator.settings_window.status_text == "Copied"
    coordinator.settings_window.clear_history_button.click()
    assert coordinator.settings_window.history_record_count == 0
    assert history.load() == ()
    coordinator.close()


def test_settings_microphone_test_previews_level_and_stops_on_close(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, _, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    recorder = coordinator._recorder  # type: ignore[attr-defined]
    assert isinstance(recorder, FakeRecorder)
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.microphone.setCurrentIndex(1)

    coordinator.settings_window.test_microphone_button.click()
    coordinator._poll_microphone_test()  # type: ignore[attr-defined]

    assert recorder.started_device == "wasapi:built-in"
    assert coordinator.settings_window.input_level.value() == 42
    coordinator.settings_window.close()
    assert recorder.cancel_count == 1
    assert coordinator.settings_window.input_level.value() == 0
    coordinator.close()


def test_settings_microphone_test_timeout_reports_completion(
    qtbot,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    coordinator, _, _, _, _ = make_coordinator(tmp_path, installed=True)
    qtbot.addWidget(coordinator.setup_window)
    qtbot.addWidget(coordinator.settings_window)
    qtbot.addWidget(coordinator.overlay)
    recorder = coordinator._recorder  # type: ignore[attr-defined]
    assert isinstance(recorder, FakeRecorder)
    coordinator.start()
    coordinator.show_settings()
    coordinator.settings_window.test_microphone_button.click()

    coordinator._complete_microphone_test()  # type: ignore[attr-defined]

    assert recorder.cancel_count == 1
    assert coordinator.settings_window.status_text == "Microphone test complete"
    assert coordinator.settings_window.test_microphone_button.text() == "Test microphone"
    coordinator.close()
