from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast
from uuid import uuid4

from PySide6.QtCore import QTimer
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
from cursor_dictation.settings.schema import AppSettings, ModelSource
from cursor_dictation.settings.store import JsonSettingsStore
from cursor_dictation.settings.vocabulary import VocabularyStore
from cursor_dictation.transcription.engine import TranscriptionEngine
from cursor_dictation.transcription.model_manager import ModelManager, PreparedModel
from cursor_dictation.ui.settings_window import SettingsWindow
from cursor_dictation.ui.setup_window import SetupWindow
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.tray import TrayIcon

InstallerFactory = Callable[[Path], DefaultModelInstaller]


class _MicrophoneTestSurface(Protocol):
    @property
    def selected_microphone_id(self) -> str | None: ...

    def set_microphone_test_active(self, active: bool) -> None: ...

    def set_input_level(self, level: float) -> None: ...

    def set_microphone_test_status(self, message: str, *, error: bool = False) -> None: ...


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
        self._pending_settings: tuple[AppSettings, tuple[str, ...]] | None = None
        self._setup_model_switch = False
        self._cancel_model_switch_requested = False
        self._transcription_queue: QtTranscriptionQueue | None = None
        self._controller: DictationController | None = None
        self.runtime: DictationRuntime | None = None
        self._hotkeys_configured = False
        self._fatal_transaction_error = False
        self._started = False
        self._closing = False
        self._microphone_test_active = False
        self._microphone_test_surface: _MicrophoneTestSurface | None = None
        self._microphone_fallback_notified = False
        self._microphone_test_timer = QTimer()
        self._microphone_test_timer.setInterval(100)
        self._microphone_test_timer.timeout.connect(self._poll_microphone_test)
        self._microphone_test_timeout = QTimer()
        self._microphone_test_timeout.setSingleShot(True)
        self._microphone_test_timeout.setInterval(10_000)
        self._microphone_test_timeout.timeout.connect(self._complete_microphone_test)

        self.tray.settings_requested.connect(self.show_settings)
        self.tray.quit_requested.connect(self._application.quit)
        self.setup_window.install_requested.connect(self.install_default_model)
        self.setup_window.cancel_requested.connect(self._cancel_setup)
        self.setup_window.dismiss_requested.connect(self._cancel_setup)
        self.settings_window.save_requested.connect(self.save_settings)
        self.settings_window.close_requested.connect(self._settings_closed)
        self.settings_window.clear_history_requested.connect(self.clear_history)
        self.settings_window.copy_history_requested.connect(self.copy_history_text)
        self.settings_window.microphone_test_requested.connect(
            lambda: self._toggle_microphone_test(self.settings_window)
        )
        self.setup_window.microphone_test_requested.connect(
            lambda: self._toggle_microphone_test(self.setup_window)
        )
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
        self._refresh_history()

        if self._settings.model_source is ModelSource.CUSTOM:
            model_path = Path(self._settings.model_path or "")
            self._begin_model_load(
                model_path,
                custom=True,
            )
            return
        recommended_path = (
            Path(self._settings.model_path)
            if self._settings.model_path is not None
            else self._default_installer.target_directory
        )
        if not recommended_path.exists():
            self._show_setup()
            return
        try:
            installer = self._installer_for_recommended_path(recommended_path)
        except ValueError as error:
            self._set_state(AppState.ERROR)
            self.settings_window.set_status(
                "This model path came from older settings and its source is unknown. "
                "Choose the local model folder again to reselect it as custom.",
                error=True,
            )
            self.settings_window.show()
            self.overlay.show_error("The saved model source must be confirmed")
            self._log_error("legacy_model_source_unknown", error)
            return
        self._begin_model_load(
            recommended_path,
            custom=False,
            installer=installer,
        )

    def show_settings(self) -> None:
        if self.settings_window.isVisible():
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        if self._controller is not None and self._controller.state not in {
            AppState.IDLE,
            AppState.ERROR,
        }:
            self.overlay.show_error("Finish the current dictation before opening Settings")
            return
        self.settings_window.set_status("")
        self._refresh_devices()
        self._apply_settings_to_windows()
        self._refresh_history()
        if self.runtime is not None:
            self.runtime.set_enabled(False)
        self._set_state(AppState.SETTINGS_OPEN)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def save_settings(self) -> None:
        self._stop_microphone_test()
        if self._fatal_transaction_error:
            self.settings_window.set_status(
                "Settings could not be restored safely. Restart Cursor Dictation before "
                "making more changes.",
                error=True,
            )
            return
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

        model_changed = (
            settings.model_path != self._settings.model_path
            or settings.model_source is not self._settings.model_source
            or self._model_manager.active_engine is None
        )
        if model_changed:
            if settings.model_source is ModelSource.RECOMMENDED:
                model_path = (
                    Path(settings.model_path)
                    if settings.model_path is not None
                    else self._default_installer.target_directory
                )
                if not model_path.exists():
                    self._pending_settings = (settings, vocabulary)
                    self._setup_model_switch = True
                    self._cancel_model_switch_requested = False
                    self.settings_window.hide()
                    self._show_setup()
                    return
                installer = self._installer_for_recommended_path(model_path)
            else:
                if settings.model_path is None:
                    self.settings_window.set_status(
                        "Choose a local CTranslate2 model folder.", error=True
                    )
                    return
                model_path = Path(settings.model_path)
                installer = None
            self._pending_settings = (settings, vocabulary)
            self.settings_window.set_editing_enabled(False)
            self.settings_window.set_status("Validating the local model...")
            if settings.model_source is ModelSource.RECOMMENDED:
                self._begin_model_load(
                    model_path,
                    custom=False,
                    installer=installer,
                    task_kind=_TaskKind.SETTINGS_MODEL,
                )
            else:
                self._begin_model_load(
                    model_path,
                    custom=True,
                    task_kind=_TaskKind.SETTINGS_MODEL,
                )
                return
            return

        self._commit_settings(settings, vocabulary)

    def clear_history(self) -> None:
        try:
            self._history.clear()
        except Exception as error:
            self.settings_window.set_status(f"Could not clear history: {error}", error=True)
            self._log_error("history_clear_failed", error)
            return
        self.settings_window.apply_history(())
        self.settings_window.set_status("History cleared")

    def copy_history_text(self, text: str) -> None:
        result = self._delivery.copy_to_clipboard(text)
        if result.success:
            self.settings_window.set_status("Copied")
            return
        self.settings_window.set_status(
            result.error_code or "Could not copy the selected transcript.",
            error=True,
        )

    def install_default_model(self) -> None:
        self._stop_microphone_test()
        if self._task_runner.is_running:
            return
        models_root = self.setup_window.install_root.resolve()
        installer = self._installer_factory(models_root)
        self._task_kind = _TaskKind.INSTALL
        self.setup_window.set_progress(0, "Preparing download...")

        def install(progress, cancelled):  # type: ignore[no-untyped-def]
            return installer.install(progress=progress, cancel_requested=cancelled)

        self._task_runner.start(install)

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._stop_microphone_test()
        if self.runtime is not None:
            self.runtime.close()
        self._hotkeys.close()
        self._hotkeys_configured = False
        self.tray.hide()
        self.overlay.close()
        self.setup_window.close_for_application()
        self.settings_window.set_editing_enabled(True)
        self.settings_window.close()
        if self._transcription_queue is not None and not self._transcription_queue.shutdown():
            self._log_warning("transcription_shutdown_delayed")
            self._transcription_queue.shutdown(-1)
        if not self._task_runner.shutdown():
            self._log_warning("task_shutdown_delayed")
            self._task_runner.shutdown(-1)

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
        selected_microphone_id = (
            self._pending_settings[0].microphone_device_id
            if self._pending_settings is not None
            else self._settings.microphone_device_id
        )
        self.setup_window.apply_devices(
            self._devices,
            selected_device_id=selected_microphone_id,
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
        if self._closing:
            return
        if self._task_kind is _TaskKind.INSTALL:
            self.setup_window.set_progress(percent, message)
        elif self._task_kind is _TaskKind.SETTINGS_MODEL:
            if self.settings_window.isVisible():
                self.settings_window.set_status(message)
            else:
                self.setup_window.set_progress(percent, message)

    def _task_succeeded(self, result: object) -> None:
        if self._closing:
            return
        task_kind = self._task_kind
        if self._cancel_model_switch_requested:
            self._task_kind = None
            self._restore_after_model_switch_cancel()
            return
        if task_kind is _TaskKind.INSTALL:
            if not isinstance(result, Path):
                self._task_failed(TypeError("Model installer returned an invalid path."))
                return
            self._task_kind = None
            self._installation_succeeded(result)
            return
        if not isinstance(result, PreparedModel):
            self._task_failed(TypeError("Model loader returned an invalid result."))
            return
        self._task_kind = None
        if task_kind is _TaskKind.SETTINGS_MODEL:
            pending = self._pending_settings
            self.settings_window.set_editing_enabled(True)
            if pending is None:
                message = "The pending settings were lost."
                if self.settings_window.isVisible():
                    self.settings_window.set_status(message, error=True)
                else:
                    self.setup_window.set_error(message)
                return
            if self._commit_settings(*pending, arm_if_possible=False):
                self._pending_settings = None
                self._model_manager.activate(result)
                if self.runtime is None:
                    if self.settings_window.isVisible():
                        self.settings_window.close()
                    self._arm_runtime(hotkeys_ready=True, sync_startup=False)
                elif self._setup_model_switch:
                    self.runtime.set_enabled(True)
                    self.setup_window.close_for_application()
                    next_state = (
                        self._controller.state if self._controller is not None else AppState.IDLE
                    )
                    self._set_state(next_state)
                self._setup_model_switch = False
            elif not self.settings_window.isVisible() and self.setup_window.isVisible():
                self.setup_window.set_error(
                    self.settings_window.status_text or "Settings could not be saved."
                )
            return
        self._model_manager.activate(result)
        self._arm_runtime()

    def _task_failed(self, value: object) -> None:
        if self._closing:
            return
        error = value if isinstance(value, Exception) else RuntimeError(str(value))
        task_kind = self._task_kind
        self._task_kind = None
        self._log_error("background_task_failed", error)
        if self._cancel_model_switch_requested:
            self._restore_after_model_switch_cancel()
            return
        if task_kind is _TaskKind.INSTALL:
            self.setup_window.set_error(str(error))
            return
        if task_kind is _TaskKind.SETTINGS_MODEL:
            self._pending_settings = None
            self.settings_window.set_editing_enabled(True)
            if self.settings_window.isVisible():
                self.settings_window.set_status(str(error), error=True)
            else:
                self.setup_window.set_error(str(error))
            return
        if self._settings.model_source is ModelSource.RECOMMENDED:
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
        pending = self._pending_settings
        base_settings, pending_vocabulary = pending or (self._settings, self._vocabulary)
        next_settings = replace(
            base_settings,
            microphone_device_id=self.setup_window.selected_microphone_id,
            model_path=model_path,
            model_source=ModelSource.RECOMMENDED,
        )
        self._pending_settings = (next_settings, pending_vocabulary)
        self.setup_window.set_progress(100, "Loading verified model...")
        self._begin_model_load(
            installed_path,
            custom=False,
            task_kind=_TaskKind.SETTINGS_MODEL,
        )

    def _arm_runtime(
        self,
        *,
        hotkeys_ready: bool = False,
        sync_startup: bool = True,
    ) -> None:
        if not hotkeys_ready:
            try:
                self._hotkeys.configure(_bindings(self._settings))
                self._hotkeys_configured = True
            except Exception as error:
                self._set_state(AppState.ERROR)
                self.settings_window.set_status(str(error), error=True)
                self.settings_window.show()
                self.overlay.show_error("Global shortcuts could not be registered")
                self._log_error("runtime_arm_failed", error)
                return
        else:
            self._hotkeys_configured = True

        startup_error: Exception | None = None
        if sync_startup:
            startup_error = self._sync_startup()

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
            self.runtime = DictationRuntime(
                controller=self._controller,
                recorder=self._recorder,
                hotkeys=cast(HotkeyPort, self._hotkeys),
                tray=self.tray,
                overlay=self.overlay,
            )
            self._controller.add_state_listener(self._controller_state_changed)
        else:
            self.runtime.set_enabled(True)
        self.setup_window.close_for_application()
        self._set_state(AppState.IDLE)
        if startup_error is not None:
            self.settings_window.set_status(
                f"Launch at sign-in could not be updated: {startup_error}",
                error=True,
            )
            self.overlay.show_error("Launch at sign-in could not be updated")

    def _active_engine(self) -> TranscriptionEngine:
        engine = self._model_manager.active_engine
        if engine is None:
            raise RuntimeError("No local transcription model is active.")
        return engine

    def _commit_settings(
        self,
        settings: AppSettings,
        vocabulary: tuple[str, ...],
        *,
        arm_if_possible: bool = True,
    ) -> bool:
        previous_settings = self._settings
        previous_vocabulary = self._vocabulary
        had_hotkeys = self._hotkeys_configured
        vocabulary_saved = False
        try:
            self._hotkeys.configure(_bindings(settings))
            self._hotkeys_configured = True
            self._vocabulary_store.save(vocabulary)
            vocabulary_saved = True
            self._settings_store.save(settings)
        except Exception as error:
            rollback_errors: list[Exception] = []
            try:
                if had_hotkeys:
                    self._hotkeys.configure(_bindings(previous_settings))
                    self._hotkeys_configured = True
                else:
                    self._hotkeys.close()
                    self._hotkeys_configured = False
            except Exception as rollback_error:
                rollback_errors.append(rollback_error)
            if vocabulary_saved:
                try:
                    self._vocabulary_store.save(previous_vocabulary)
                except Exception as rollback_error:
                    rollback_errors.append(rollback_error)
            message = str(error)
            if rollback_errors:
                message += "; rollback failed: " + "; ".join(map(str, rollback_errors))
                self._fatal_transaction_error = True
                if self.runtime is not None:
                    self.runtime.set_enabled(False)
                self._set_state(AppState.ERROR)
                self.overlay.show_error("Settings rollback failed")
            self.settings_window.set_status(message, error=True)
            self._log_error("settings_save_failed", error)
            return False

        self._settings = settings
        self._vocabulary = vocabulary
        self._history.enabled = settings.history_enabled
        startup_error = self._sync_startup()
        if startup_error is None:
            self.settings_window.set_status("Saved")
        else:
            self.settings_window.set_status(
                f"Saved, but launch at sign-in could not be updated: {startup_error}",
                error=True,
            )
        if (
            arm_if_possible
            and self.runtime is None
            and self._model_manager.active_engine is not None
        ):
            if self.settings_window.isVisible():
                self.settings_window.close()
            self._arm_runtime(hotkeys_ready=True, sync_startup=False)
        return True

    def _sync_startup(self) -> Exception | None:
        try:
            self._startup_manager.set_enabled(self._settings.launch_at_sign_in)
        except Exception as error:
            self._log_error("startup_sync_failed", error)
            return error
        return None

    def _settings_closed(self) -> None:
        if self._closing:
            return
        self._stop_microphone_test()
        if self._fatal_transaction_error:
            if self.runtime is not None:
                self.runtime.set_enabled(False)
            self._set_state(AppState.ERROR)
            self.overlay.show_error("Restart required after settings rollback failure")
            return
        if self.runtime is not None:
            self.runtime.set_enabled(True)
        if self.runtime is None and self.setup_window.isVisible():
            next_state = AppState.FIRST_RUN_SETUP
        else:
            next_state = self._controller.state if self._controller is not None else self._state
        self._set_state(next_state)

    def _toggle_microphone_test(self, surface: _MicrophoneTestSurface) -> None:
        if self._microphone_test_active:
            self._stop_microphone_test()
            surface.set_microphone_test_status("Microphone test stopped")
            return
        try:
            self._recorder.start(surface.selected_microphone_id)
        except Exception as error:
            surface.set_microphone_test_status(f"Could not test microphone: {error}", error=True)
            self._log_error("microphone_test_failed", error)
            return
        self._microphone_test_active = True
        self._microphone_test_surface = surface
        surface.set_microphone_test_active(True)
        surface.set_microphone_test_status("Listening for 10 seconds...")
        self._microphone_test_timer.start()
        self._microphone_test_timeout.start()

    def _poll_microphone_test(self) -> None:
        if not self._microphone_test_active:
            return
        reason = self._recorder.wait_for_completion(timeout=0)
        if reason is not None:
            surface = self._microphone_test_surface
            self._stop_microphone_test()
            if surface is not None:
                surface.set_microphone_test_status(
                    "The microphone test stopped unexpectedly.", error=True
                )
            return
        if self._microphone_test_surface is not None:
            self._microphone_test_surface.set_input_level(self._recorder.input_level)

    def _stop_microphone_test(self) -> None:
        if not self._microphone_test_active:
            return
        self._microphone_test_timer.stop()
        self._microphone_test_timeout.stop()
        try:
            self._recorder.cancel()
        except Exception as error:
            self._log_error("microphone_test_stop_failed", error)
        finally:
            surface = self._microphone_test_surface
            self._microphone_test_active = False
            self._microphone_test_surface = None
            if surface is not None:
                surface.set_microphone_test_active(False)

    def _complete_microphone_test(self) -> None:
        if not self._microphone_test_active:
            return
        surface = self._microphone_test_surface
        self._stop_microphone_test()
        if surface is not None:
            surface.set_microphone_test_status("Microphone test complete")

    def _cancel_setup(self) -> None:
        self._stop_microphone_test()
        if self._task_runner.is_running:
            self._task_runner.cancel()
            if self._setup_model_switch:
                self._cancel_model_switch_requested = True
                self.setup_window.set_progress(0, "Cancelling model change...")
                return
        if self._setup_model_switch and not self._task_runner.is_running:
            self._restore_after_model_switch_cancel()
            return
        self._application.quit()

    def _restore_after_model_switch_cancel(self) -> None:
        self._pending_settings = None
        self._setup_model_switch = False
        self._cancel_model_switch_requested = False
        self.setup_window.close_for_application()
        if self._fatal_transaction_error:
            if self.runtime is not None:
                self.runtime.set_enabled(False)
            self._set_state(AppState.ERROR)
            self.settings_window.show()
            self.overlay.show_error("Restart required after settings rollback failure")
            return
        if self.runtime is not None:
            self.runtime.set_enabled(True)
            next_state = self._controller.state if self._controller is not None else AppState.IDLE
            self._set_state(next_state)
        else:
            self._set_state(AppState.ERROR)
            self.settings_window.show()

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

    def _refresh_history(self) -> None:
        try:
            records = self._history.load()
        except Exception as error:
            self.settings_window.apply_history(())
            self.settings_window.set_status(f"Could not load history: {error}", error=True)
            self._log_error("history_load_failed", error)
            return
        self.settings_window.apply_history(records)

    def _installer_for_recommended_path(self, model_path: Path) -> DefaultModelInstaller:
        installer = self._installer_factory(model_path.parent)
        if installer.target_directory.resolve() != model_path.resolve():
            raise ValueError(f"Recommended model path is invalid: {model_path}")
        return installer

    def _set_state(self, state: AppState) -> None:
        self._state = state
        self.tray.set_state(state)
        self.overlay.set_state(state)

    def _controller_state_changed(self, state: AppState) -> None:
        if self.settings_window.isVisible():
            return
        self._state = state
        if state is AppState.RECORDING:
            if self._settings.sound_cues_enabled:
                QApplication.beep()
            if self._recorder.used_default_fallback and not self._microphone_fallback_notified:
                self._microphone_fallback_notified = True
                self.overlay.show_error("Selected microphone unavailable; using Windows default")
                self._log_warning("microphone_default_fallback")

    def _completion_feedback(self, mode: DeliveryMode, result: DeliveryResult) -> None:
        if self._settings.sound_cues_enabled:
            QApplication.beep()

    def _observer_error(self, error: Exception) -> None:
        self._log_error("observer_failed", error)

    def _log_error(self, event: str, error: Exception) -> None:
        if self._logger is not None:
            self._logger.error(event, error_type=type(error).__name__)

    def _log_warning(self, event: str) -> None:
        if self._logger is not None:
            self._logger.warning(event)


def _bindings(settings: AppSettings) -> HotkeyBindings:
    return HotkeyBindings(
        hold=parse_hotkey(settings.hold_to_talk_hotkey),
        toggle=parse_hotkey(settings.toggle_recording_hotkey),
        copy=parse_hotkey(settings.record_and_copy_hotkey),
        cancel=parse_hotkey(settings.cancel_hotkey),
    )


def _smoke_audio() -> RecordedAudio:
    return RecordedAudio(samples=(0.0,) * 1_600, sample_rate=16_000, channels=1)
