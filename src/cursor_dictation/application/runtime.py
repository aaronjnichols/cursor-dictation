from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QObject, Qt, QTimer

from cursor_dictation.application.controller import DictationController
from cursor_dictation.audio.recorder import RecordingCompletionReason
from cursor_dictation.core.models import AppState, DeliveryMode, DeliveryResult
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.tray import TrayIcon


class _Signal(Protocol):
    def connect(
        self,
        slot: object,
        connection_type: Qt.ConnectionType = Qt.ConnectionType.AutoConnection,
    ) -> object: ...


class HotkeyPort(Protocol):
    hold_pressed: _Signal
    hold_released: _Signal
    toggle_pressed: _Signal
    copy_pressed: _Signal
    cancel_pressed: _Signal


class CompletionRecorder(Protocol):
    def wait_for_completion(
        self,
        timeout: float | None = None,
    ) -> RecordingCompletionReason | None: ...


class DictationRuntime(QObject):
    def __init__(
        self,
        *,
        controller: DictationController,
        recorder: CompletionRecorder,
        hotkeys: HotkeyPort,
        tray: TrayIcon,
        overlay: StatusOverlay,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._recorder = recorder
        self._tray = tray
        self._overlay = overlay
        self._hold_active = False
        self._enabled = True

        queued = Qt.ConnectionType.QueuedConnection
        hotkeys.hold_pressed.connect(self._hold_pressed, queued)
        hotkeys.hold_released.connect(self._hold_released, queued)
        hotkeys.toggle_pressed.connect(self._toggle_insert, queued)
        hotkeys.copy_pressed.connect(self._toggle_copy, queued)
        hotkeys.cancel_pressed.connect(self._cancel, queued)
        tray.start_insert_requested.connect(self._toggle_insert)
        tray.start_copy_requested.connect(self._toggle_copy)
        tray.cancel_requested.connect(self._cancel)
        controller.add_state_listener(self._state_changed)
        controller.add_completion_listener(self._completed)

        self._completion_timer = QTimer(self)
        self._completion_timer.setInterval(100)
        self._completion_timer.timeout.connect(self.poll_audio_completion)
        self._completion_timer.start()
        self._state_changed(controller.state)

    def close(self) -> None:
        self._completion_timer.stop()
        if self._controller.state is AppState.RECORDING:
            self._controller.cancel()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def poll_audio_completion(self) -> None:
        if self._controller.state is not AppState.RECORDING:
            return
        reason = self._recorder.wait_for_completion(timeout=0)
        if reason in {
            RecordingCompletionReason.LIMIT_REACHED,
            RecordingCompletionReason.CAPTURE_ERROR,
            RecordingCompletionReason.DEVICE_STOPPED,
        }:
            self._hold_active = False
            self._controller.stop_recording()

    def _hold_pressed(self) -> None:
        if not self._can_start():
            return
        if self._hold_active:
            return
        if self._controller.state is AppState.ERROR:
            self._controller.reset_error()
        if self._controller.state is not AppState.IDLE:
            self._overlay.show_busy()
            return
        self._tray.set_recording_mode(DeliveryMode.INSERT)
        self._hold_active = self._controller.start_recording(DeliveryMode.INSERT)

    def _hold_released(self) -> None:
        if not self._hold_active:
            return
        self._hold_active = False
        if self._controller.state is AppState.RECORDING:
            self._controller.stop_recording()

    def _toggle_insert(self) -> None:
        self._toggle(DeliveryMode.INSERT)

    def _toggle_copy(self) -> None:
        if self._controller.state is AppState.ERROR_WITH_TRANSCRIPT:
            if self._controller.copy_recoverable_transcript():
                self._overlay.show_copied()
            else:
                self._overlay.show_error(self._controller.last_error or "Clipboard copy failed")
            return
        self._toggle(DeliveryMode.COPY)

    def _toggle(self, mode: DeliveryMode) -> None:
        state = self._controller.state
        if state is AppState.ERROR:
            self._controller.reset_error()
            state = self._controller.state
        if state is AppState.IDLE:
            if not self._can_start():
                return
            self._tray.set_recording_mode(mode)
            self._controller.start_recording(mode)
        elif state is AppState.RECORDING:
            self._hold_active = False
            self._controller.stop_recording()
        else:
            self._overlay.show_busy()

    def _cancel(self) -> None:
        self._hold_active = False
        if self._controller.state is AppState.ERROR_WITH_TRANSCRIPT:
            self._controller.discard_recoverable_transcript()
            return
        self._controller.cancel()

    def _state_changed(self, state: AppState) -> None:
        self._tray.set_state(state)
        self._overlay.set_state(state)
        if state in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            self._overlay.show_error(self._controller.last_error or "Dictation failed")

    def _completed(self, mode: DeliveryMode, result: DeliveryResult) -> None:
        if mode is DeliveryMode.COPY or result.method.value == "clipboard_copy":
            self._overlay.show_copied()
        else:
            self._overlay.show_inserted()

    def _can_start(self) -> bool:
        if self._enabled:
            return True
        self._overlay.show_error("Close Settings to start dictation")
        return False
