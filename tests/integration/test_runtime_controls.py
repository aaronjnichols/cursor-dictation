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
    input_level: float = 0.0

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
    def __init__(self) -> None:
        self.fail_insert = False
        self.copied: list[str] = []

    def insert_at_cursor(self, text: str) -> DeliveryResult:
        if self.fail_insert:
            return DeliveryResult.failed(
                DeliveryMethod.CLIPBOARD_PASTE,
                error_code="paste_failed",
                recoverable=True,
            )
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        self.copied.append(text)
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
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    assert controller.state is AppState.RECORDING
    hotkeys.hold_released.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)

    assert controller.state is AppState.TRANSCRIBING
    assert recorder.starts == 1
    assert recorder.stops == 1
    assert queue.requests[0].delivery_mode is DeliveryMode.INSERT
    runtime.close()


def test_global_hotkey_signal_returns_before_microphone_work_starts(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, _ = make_runtime(qtbot)

    hotkeys.toggle_pressed.emit()

    assert recorder.starts == 0
    assert controller.state is AppState.IDLE
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    assert recorder.starts == 1
    runtime.close()


def test_toggle_and_copy_shortcuts_use_separate_delivery_modes(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, _, queue, hotkeys, _, _ = make_runtime(qtbot)

    hotkeys.copy_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    assert controller.state is AppState.RECORDING
    hotkeys.copy_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)

    assert queue.requests[0].delivery_mode is DeliveryMode.COPY
    runtime.close()


def test_audio_limit_completion_stops_and_transcribes(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, queue, hotkeys, _, _ = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    recorder.completion = RecordingCompletionReason.LIMIT_REACHED

    runtime.poll_audio_completion()

    assert controller.state is AppState.TRANSCRIBING
    assert queue.requests[0].delivery_mode is DeliveryMode.INSERT
    runtime.close()


def test_successful_insert_shows_pixel_completion_with_word_count(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, _, queue, hotkeys, _, overlay = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)
    request = queue.requests[-1]

    controller._transcription_succeeded(  # type: ignore[attr-defined]
        request.session_id,
        Transcript("Three words inserted."),
    )

    assert controller.state is AppState.IDLE
    assert overlay.status_text == "INSERTED"
    assert overlay.detail_text == "3 WORDS"
    assert overlay.visual_mode == "check"
    runtime.close()


def test_runtime_updates_recording_waveform_from_microphone_level(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, overlay = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    recorder.input_level = 1.0

    runtime.poll_audio_completion()

    assert max(overlay.audio_block_heights) == 14
    runtime.close()


def test_busy_shortcut_does_not_queue_another_recording(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, overlay = make_runtime(qtbot)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)
    assert controller.state is AppState.TRANSCRIBING

    hotkeys.copy_pressed.emit()
    qtbot.waitUntil(lambda: overlay.status_text == "WORKING")

    assert recorder.starts == 1
    assert overlay.status_text == "WORKING"
    qtbot.wait(1_700)
    assert overlay.isVisible()
    assert overlay.status_text == "TRANSCRIBING"
    runtime.close()


def test_disabled_runtime_rejects_hotkeys_while_settings_are_open(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, recorder, _, hotkeys, _, overlay = make_runtime(qtbot)
    runtime.set_enabled(False)

    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: overlay.status_text == "SETTINGS ARE OPEN")

    assert controller.state is AppState.IDLE
    assert recorder.starts == 0
    assert overlay.status_text == "SETTINGS ARE OPEN"
    runtime.close()


def test_tray_copy_recovers_transcript_after_delivery_failure(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, _, queue, hotkeys, tray, overlay = make_runtime(qtbot)
    delivery = controller._delivery  # type: ignore[attr-defined]
    assert isinstance(delivery, FakeDelivery)
    delivery.fail_insert = True
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)
    request = queue.requests[-1]
    controller._transcription_succeeded(  # type: ignore[attr-defined]
        request.session_id,
        Transcript("Keep this transcript."),
    )
    assert controller.state is AppState.ERROR_WITH_TRANSCRIPT

    tray.copy_action.trigger()

    assert delivery.copied == ["Keep this transcript."]
    assert controller.state is AppState.IDLE
    assert overlay.status_text == "COPIED"
    runtime.close()


def test_cancel_discards_a_recoverable_transcript(qtbot) -> None:  # type: ignore[no-untyped-def]
    runtime, controller, _, queue, hotkeys, tray, _ = make_runtime(qtbot)
    delivery = controller._delivery  # type: ignore[attr-defined]
    assert isinstance(delivery, FakeDelivery)
    delivery.fail_insert = True
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.RECORDING)
    hotkeys.toggle_pressed.emit()
    qtbot.waitUntil(lambda: controller.state is AppState.TRANSCRIBING)
    request = queue.requests[-1]
    controller._transcription_succeeded(  # type: ignore[attr-defined]
        request.session_id,
        Transcript("No longer needed."),
    )

    tray.cancel_action.trigger()

    assert controller.state is AppState.IDLE
    assert controller.last_transcript is None
    assert tray.start_action.isEnabled()
    runtime.close()
