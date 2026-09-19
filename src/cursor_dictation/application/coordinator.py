from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import cast
from uuid import uuid4

from PySide6.QtWidgets import QApplication

from cursor_dictation.application.controller import DictationController
from cursor_dictation.application.model_install import DefaultModelInstaller
from cursor_dictation.application.qt_tasks import QtTaskRunner
from cursor_dictation.application.qt_transcription_queue import QtTranscriptionQueue
from cursor_dictation.application.runtime import DictationRuntime, HotkeyPort
from cursor_dictation.audio.recorder import AudioDevice
from cursor_dictation.audio.sounddevice_recorder import SoundDeviceRecorder
from cursor_dictation.core.hotkeys import HotkeyBindings, parse_hotkey
from cursor_dictation.core.models import AppState, DeliveryMode, DeliveryResult, RecordedAudio
from cursor_dictation.diagnostics.logging import SafeEventLogger
from cursor_dictation.output.delivery import WindowsTextDelivery
from cursor_dictation.platform.windows.hotkeys import WindowsHotkeyService
from cursor_dictation.platform.windows.paths import AppPaths
from cursor_dictation.platform.windows.startup import StartupManager
from cursor_dictation.settings.history import JsonlHistoryStore
from cursor_dictation.settings.schema import AppSettings
from cursor_dictation.settings.store import JsonSettingsStore
from cursor_dictation.settings.vocabulary import VocabularyStore
from cursor_dictation.transcription.engine import TranscriptionEngine
from cursor_dictation.transcription.model_manager import ModelManager, PreparedModel
from cursor_dictation.ui.settings_window import SettingsWindow
from cursor_dictation.ui.setup_window import SetupWindow
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.tray import TrayIcon

InstallerFactory = Callable[[Path], DefaultModelInstaller]


class _TaskKind(StrEnum):
    INSTALL = "install"
    STARTUP_MODEL = "startup_model"
    SETTINGS_MODEL = "settings_model"


class ApplicationCoordinator:
    """Owns one process-wide application session and its adapter lifetimes."""

    def __init__(
        self,
        *,
        application: QApplication,
        paths: AppPaths,
        settings_store: JsonSettingsStore,
        vocabulary_store: VocabularyStore,
        history: JsonlHistoryStore,
        recorder: SoundDeviceRecorder,
        model_manager: ModelManager,
        installer_factory: InstallerFactory,
        hotkeys: WindowsHotkeyService,
        startup_manager: StartupManager,
        task_runner: QtTaskRunner,
        delivery: WindowsTextDelivery,
        logger: SafeEventLogger | None = None,
        tray: TrayIcon | None = None,
        overlay: StatusOverlay | None = None,
        setup_window: SetupWindow | None = None,
        settings_window: SettingsWindow | None = None,
    ) -> None:
        self._application = application
        self._paths = paths
        self._settings_store = settings_store
        self._vocabulary_store = vocabulary_store
        self._history = history
        self._recorder = recorder
        self._model_manager = model_manager
        self._installer_factory = installer_factory
        self._default_installer = installer_factory(paths.models_dir)
        self._hotkeys = hotkeys
        self._startup_manager = startup_manager
        self._task_runner = task_runner
        self._delivery = delivery
        self._logger = logger

        self.tray = tray or TrayIcon()
        self.overlay = overlay or StatusOverlay()
        self.setup_window = setup_window or SetupWindow()
        self.settings_window = settings_window or SettingsWindow()

        self._settings = AppSettings()
        self._vocabulary: tuple[str, ...] = ()
        self._devices: tuple[AudioDevice, ...] = ()
        self._state = AppState.STARTING
        self._task_kind: _TaskKind | None = None
        self._pending_installer: DefaultModelInstaller | None = None
        self._pending_settings: tuple[AppSettings, tuple[str, ...]] | None = None
        self._transcription_queue: QtTranscriptionQueue | None = None
        self._controller: DictationController | None = None
        self.runtime: DictationRuntime | None = None
        self._started = False
        self._closing = False

        self.tray.settings_requested.connect(self.show_settings)
        self.tray.quit_requested.connect(self._application.quit)
        self.setup_window.install_requested.connect(self.install_default_model)
        self.setup_window.cancel_requested.connect(self._cancel_setup)
        self.settings_window.save_requested.connect(self.save_settings)
        self.settings_window.close_requested.connect(self._settings_closed)
        self.settings_window.clear_history_requested.connect(self.clear_history)
        self._task_runner.progress.connect(self._task_progress)
        self._task_runner.succeeded.connect(self._task_succeeded)
        self._task_runner.failed.connect(self._task_failed)

    @property
    def state(self) -> AppState:
        return self._state

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self.tray.show()
        try:
            self._settings = self._settings_store.load()
            self._vocabulary = self._vocabulary_store.load()
        except Exception as error:
            self._show_configuration_error(error)
            return

        self._history.enabled = self._settings.history_enabled
        self._refresh_devices()
        self._apply_settings_to_windows()

        if self._settings.model_path is not None:
            self._begin_model_load(Path(self._settings.model_path), custom=True)
            return
        if not self._default_installer.target_directory.exists():
            self._show_setup()
            return
        self._begin_model_load(
            self._default_installer.target_directory,
            custom=False,
            installer=self._default_installer,
        )

    def show_settings(self) -> None:
        self._refresh_devices()
        self._apply_settings_to_windows()
        self.settings_window.set_status("")
        if self.runtime is not None:
            self.runtime.set_enabled(False)
        self._set_state(AppState.SETTINGS_OPEN)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def save_settings(self) -> None:
        if self._task_runner.is_running:
            self.settings_window.set_status(
                "Wait for the current model task to finish.", error=True
            )
            return
        try:
            settings, vocabulary = self.settings_window.collect_settings()
        except (TypeError, ValueError) as error:
            self.settings_window.set_status(str(error), error=True)
            return

        if settings.model_path != self._settings.model_path:
            self._pending_settings = (settings, vocabulary)
            self.settings_window.save_button.setEnabled(False)
            self.settings_window.set_status("Validating the local model...")
            if settings.model_path is None:
                self._begin_model_load(
                    self._default_installer.target_directory,
                    custom=False,
                    installer=self._default_installer,
                    task_kind=_TaskKind.SETTINGS_MODEL,
                )
            else:
                self._begin_model_load(
                    Path(settings.model_path),
                    custom=True,
                    task_kind=_TaskKind.SETTINGS_MODEL,
                )
            return

        self._commit_settings(settings, vocabulary)

    def clear_history(self) -> None:
        try:
            self._history.clear()
        except Exception as error:
            self.settings_window.set_status(f"Could not clear history: {error}", error=True)
            self._log_error("history_clear_failed", error)
            return
        self.settings_window.set_status("History cleared")

    def install_default_model(self) -> None:
        if self._task_runner.is_running:
            return
        models_root = self.setup_window.install_root.resolve()
        installer = self._installer_factory(models_root)
        self._pending_installer = installer
        self._task_kind = _TaskKind.INSTALL
        self.setup_window.set_progress(0, "Preparing download...")

        def install(progress, cancelled):  # type: ignore[no-untyped-def]
            return installer.install(progress=progress, cancel_requested=cancelled)

        self._task_runner.start(install)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self.runtime is not None:
            self.runtime.close()
        if self._transcription_queue is not None:
            self._transcription_queue.shutdown()
        self._task_runner.shutdown()
        self._hotkeys.close()
        self.tray.hide()
        self.overlay.close()
        self.setup_window.close()
        self.settings_window.close()

    def _show_configuration_error(self, error: Exception) -> None:
        self._set_state(AppState.ERROR)
        self.settings_window.apply_settings(AppSettings(), vocabulary=(), devices=())
        self.settings_window.set_status(str(error), error=True)
        self.settings_window.show()
        self.overlay.show_error("Settings could not be loaded")
        self._log_error("configuration_load_failed", error)

    def _show_setup(self, message: str | None = None) -> None:
        self._set_state(AppState.FIRST_RUN_SETUP)
        self.setup_window.set_install_location(self._paths.models_dir)
        self.setup_window.apply_devices(
            self._devices,
            selected_device_id=self._settings.microphone_device_id,
        )
        if message is not None:
            self.setup_window.set_error(message)
        self.setup_window.show()
        self.setup_window.raise_()
        self.setup_window.activateWindow()

    def _begin_model_load(
        self,
        path: Path,
        *,
        custom: bool,
        installer: DefaultModelInstaller | None = None,
        task_kind: _TaskKind = _TaskKind.STARTUP_MODEL,
    ) -> None:
        self._task_kind = task_kind
        if task_kind is _TaskKind.STARTUP_MODEL:
            self._set_state(AppState.LOADING_MODEL)
        self._task_runner.start(
            lambda progress, cancelled: self._prepare_model(
                path,
                custom=custom,
                installer=installer,
                progress=progress,
                cancelled=cancelled,
            )
        )

    def _prepare_model(
        self,
        path: Path,
        *,
        custom: bool,
        installer: DefaultModelInstaller | None,
        progress: Callable[[int, str], None],
        cancelled: Callable[[], bool],
    ) -> PreparedModel:
        progress(5, "Checking local model...")
        if installer is not None and not installer.is_installed():
            raise RuntimeError("The recommended model is missing or failed verification.")
        if cancelled():
            raise RuntimeError("Model loading was cancelled.")
        progress(35, "Loading model on CPU...")
        if custom:
            prepared = self._model_manager.prepare_custom(path, smoke_audio=_smoke_audio())
        else:
            prepared = self._model_manager.prepare_verified(path)
        if cancelled():
            raise RuntimeError("Model loading was cancelled.")
        progress(100, "Model ready")
        return prepared

    def _task_progress(self, percent: int, message: str) -> None:
        if self._task_kind is _TaskKind.INSTALL:
            self.setup_window.set_progress(percent, message)
        elif self._task_kind is _TaskKind.SETTINGS_MODEL:
            self.settings_window.set_status(message)

    def _task_succeeded(self, result: object) -> None:
        task_kind = self._task_kind
        self._task_kind = None
        if task_kind is _TaskKind.INSTALL:
            if not isinstance(result, Path):
                self._task_failed(TypeError("Model installer returned an invalid path."))
                return
            self._installation_succeeded(result)
            return
        if not isinstance(result, PreparedModel):
            self._task_failed(TypeError("Model loader returned an invalid result."))
            return
        if task_kind is _TaskKind.SETTINGS_MODEL:
            pending = self._pending_settings
            self._pending_settings = None
            self.settings_window.save_button.setEnabled(True)
            if pending is None:
                self.settings_window.set_status("The pending settings were lost.", error=True)
                return
            if self._commit_settings(*pending):
                self._model_manager.activate(result)
            return
        self._model_manager.activate(result)
        self._arm_runtime()

    def _task_failed(self, value: object) -> None:
        error = value if isinstance(value, Exception) else RuntimeError(str(value))
        task_kind = self._task_kind
        self._task_kind = None
        self._log_error("background_task_failed", error)
        if task_kind is _TaskKind.INSTALL:
            self.setup_window.set_error(str(error))
            return
        if task_kind is _TaskKind.SETTINGS_MODEL:
            self._pending_settings = None
            self.settings_window.save_button.setEnabled(True)
            self.settings_window.set_status(str(error), error=True)
            return
        if self._settings.model_path is None:
            self._show_setup(str(error))
        else:
            self._set_state(AppState.ERROR)
            self.settings_window.set_status(str(error), error=True)
            self.settings_window.show()
            self.overlay.show_error("The selected model could not be loaded")

    def _installation_succeeded(self, installed_path: Path) -> None:
        model_path = (
            None
            if installed_path.parent.resolve() == self._paths.models_dir.resolve()
            else str(installed_path)
        )
        next_settings = replace(
            self._settings,
            microphone_device_id=self.setup_window.selected_microphone_id,
            model_path=model_path,
        )
        try:
            self._settings_store.save(next_settings)
        except Exception as error:
            self.setup_window.set_error(str(error))
            self._log_error("setup_settings_save_failed", error)
            return
        self._settings = next_settings
        self.setup_window.set_complete()
        self._begin_model_load(installed_path, custom=False)

    def _arm_runtime(self) -> None:
        try:
            self._hotkeys.configure(_bindings(self._settings))
            self._startup_manager.set_enabled(self._settings.launch_at_sign_in)
        except Exception as error:
            self._set_state(AppState.ERROR)
            self.settings_window.set_status(str(error), error=True)
            self.settings_window.show()
            self.overlay.show_error("Global shortcuts could not be registered")
            self._log_error("runtime_arm_failed", error)
            return

        if self.runtime is None:
            self._transcription_queue = QtTranscriptionQueue(self._active_engine)
            self._controller = DictationController(
                recorder=self._recorder,
                transcription_queue=self._transcription_queue,
                delivery=self._delivery,
                vocabulary=lambda: self._vocabulary,
                selected_device=lambda: self._settings.microphone_device_id,
                session_ids=lambda: uuid4().hex,
                observer_error=self._observer_error,
                history=self._history,
                completion_listener=self._completion_feedback,
            )
            self._controller.add_state_listener(self._controller_state_changed)
            self.runtime = DictationRuntime(
                controller=self._controller,
                recorder=self._recorder,
                hotkeys=cast(HotkeyPort, self._hotkeys),
                tray=self.tray,
                overlay=self.overlay,
            )
        else:
            self.runtime.set_enabled(True)
        self.setup_window.close()
        self._set_state(AppState.IDLE)

    def _active_engine(self) -> TranscriptionEngine:
        engine = self._model_manager.active_engine
        if engine is None:
            raise RuntimeError("No local transcription model is active.")
        return engine

    def _commit_settings(
        self,
        settings: AppSettings,
        vocabulary: tuple[str, ...],
    ) -> bool:
        previous_settings = self._settings
        previous_vocabulary = self._vocabulary
        try:
            self._hotkeys.configure(_bindings(settings))
            self._startup_manager.set_enabled(settings.launch_at_sign_in)
            self._vocabulary_store.save(vocabulary)
            self._settings_store.save(settings)
        except Exception as error:
            with suppress(Exception):
                self._hotkeys.configure(_bindings(previous_settings))
            with suppress(Exception):
                self._startup_manager.set_enabled(previous_settings.launch_at_sign_in)
            with suppress(Exception):
                self._vocabulary_store.save(previous_vocabulary)
            self.settings_window.set_status(str(error), error=True)
            self._log_error("settings_save_failed", error)
            return False

        self._settings = settings
        self._vocabulary = vocabulary
        self._history.enabled = settings.history_enabled
        self.settings_window.set_status("Saved")
        if self.runtime is None and self._model_manager.active_engine is not None:
            self._arm_runtime()
        return True

    def _settings_closed(self) -> None:
        if self._closing:
            return
        if self.runtime is not None:
            self.runtime.set_enabled(True)
        next_state = self._controller.state if self._controller is not None else self._state
        self._set_state(next_state)

    def _cancel_setup(self) -> None:
        if self._task_runner.is_running:
            self._task_runner.cancel()
        self._application.quit()

    def _refresh_devices(self) -> None:
        try:
            self._devices = self._recorder.list_devices()
        except Exception as error:
            self._devices = ()
            self._log_error("device_enumeration_failed", error)

    def _apply_settings_to_windows(self) -> None:
        self.settings_window.apply_settings(
            self._settings,
            vocabulary=self._vocabulary,
            devices=self._devices,
        )

    def _set_state(self, state: AppState) -> None:
        self._state = state
        self.tray.set_state(state)
        self.overlay.set_state(state)

    def _controller_state_changed(self, state: AppState) -> None:
        if self.settings_window.isVisible():
            return
        self._state = state
        if state is AppState.RECORDING and self._settings.sound_cues_enabled:
            QApplication.beep()

    def _completion_feedback(self, mode: DeliveryMode, result: DeliveryResult) -> None:
        if self._settings.sound_cues_enabled:
            QApplication.beep()

    def _observer_error(self, error: Exception) -> None:
        self._log_error("observer_failed", error)

    def _log_error(self, event: str, error: Exception) -> None:
        if self._logger is not None:
            self._logger.error(event, error_type=type(error).__name__)


def _bindings(settings: AppSettings) -> HotkeyBindings:
    return HotkeyBindings(
        hold=parse_hotkey(settings.hold_to_talk_hotkey),
        toggle=parse_hotkey(settings.toggle_recording_hotkey),
        copy=parse_hotkey(settings.record_and_copy_hotkey),
        cancel=parse_hotkey(settings.cancel_hotkey),
    )


def _smoke_audio() -> RecordedAudio:
    return RecordedAudio(samples=(0.0,) * 1_600, sample_rate=16_000, channels=1)
