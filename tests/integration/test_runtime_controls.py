from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from cursor_dictation.application.controller import DictationController
from cursor_dictation.application.runtime import DictationRuntime
from cursor_dictation.audio.recorder import RecordingCompletionReason
from cursor_dictation.core.models import (
    AppState,
    DeliveryMethod,
    DeliveryMode,
    DeliveryResult,
    RecordedAudio,
    Transcript,
    TranscriptionRequest,
)
from cursor_dictation.ui.status_overlay import StatusOverlay
from cursor_dictation.ui.tray import TrayIcon


class FakeHotkeys(QObject):
    hold_pressed = Signal()
    hold_released = Signal()
    toggle_pressed = Signal()
    copy_pressed = Signal()
    cancel_pressed = Signal()


@dataclass
class FakeRecorder:
    starts: int = 0
    stops: int = 0
    cancels: int = 0
    completion: RecordingCompletionReason | None = None

    def start(self, device_id: str | None) -> None:
        self.starts += 1

    def stop(self) -> RecordedAudio:
        self.stops += 1
        self.completion = None
        return RecordedAudio(samples=(0.1,), sample_rate=16_000, channels=1)

    def cancel(self) -> None:
        self.cancels += 1
        self.completion = None

    def wait_for_completion(self, timeout: float | None = None) -> RecordingCompletionReason | None:
        return self.completion


@dataclass
class FakeQueue:
    requests: list[TranscriptionRequest] = field(default_factory=list)

    def submit(
        self,
        request: TranscriptionRequest,
        on_success: Callable[[str, Transcript], None],
        on_failure: Callable[[str, Exception], None],
    ) -> None:
        self.requests.append(request)


class FakeDelivery:
    def insert_at_cursor(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_COPY)


def make_runtime(qtbot):  # type: ignore[no-untyped-def]
    recorder = FakeRecorder()
    queue = FakeQueue()
    controller = DictationController(
        recorder=recorder,
        transcription_queue=queue,
        delivery=FakeDelivery(),
        vocabulary=lambda: (),
        selected_device=lambda: None,
        session_ids=iter(("one", "two", "three", "four")).__next__,
    )
    hotkeys = FakeHotkeys()
    tray = TrayIcon()
    overlay = StatusOverlay()
    qtbot.addWidget(overlay)
    runtime = DictationRuntime(
        controller=controller,
        recorder=recorder,
        hotkeys=hotkeys,
        tray=tray,
        overlay=overlay,
    )
    return runtime, controller, recorder, queue, hotkeys, tray, overlay


def test_hold_to_talk_starts_on_press_and_stops_on_release(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, queue, hotkeys, _, _ = make_runtime(qtbot)

    hotkeys.hold_pressed.emit()
    assert controller.state is AppState.RECORDING
    hotkeys.hold_released.emit()

    assert controller.state is AppState.TRANSCRIBING
    assert recorder.starts == 1
    assert recorder.stops == 1
    assert queue.requests[0].delivery_mode is DeliveryMode.INSERT
    runtime.close()


def test_toggle_and_copy_shortcuts_use_separate_delivery_modes(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, _, queue, hotkeys, _, _ = make_runtime(qtbot)

    hotkeys.copy_pressed.emit()
    assert controller.state is AppState.RECORDING
    hotkeys.copy_pressed.emit()

    assert queue.requests[0].delivery_mode is DeliveryMode.COPY
    runtime.close()


def test_audio_limit_completion_stops_and_transcribes(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, queue, hotkeys, _, _ = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    recorder.completion = RecordingCompletionReason.LIMIT_REACHED

    runtime.poll_audio_completion()

    assert controller.state is AppState.TRANSCRIBING
    assert queue.requests[0].delivery_mode is DeliveryMode.INSERT
    runtime.close()


def test_busy_shortcut_does_not_queue_another_recording(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, overlay = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    hotkeys.toggle_pressed.emit()
    assert controller.state is AppState.TRANSCRIBING

    hotkeys.copy_pressed.emit()

    assert recorder.starts == 1
    assert overlay.status_text == "Transcribing..."
    runtime.close()


def test_disabled_runtime_rejects_hotkeys_while_settings_are_open(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, overlay = make_runtime(qtbot)
    runtime.set_enabled(False)

    hotkeys.toggle_pressed.emit()

    assert controller.state is AppState.IDLE
    assert recorder.starts == 0
    assert overlay.status_text == "Close Settings to start dictation"
    runtime.close()
