from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from cursor_dictation.application.controller import DictationController
from cursor_dictation.core.models import (
    AppState,
    DeliveryMethod,
    DeliveryMode,
    DeliveryResult,
    RecordedAudio,
    Transcript,
    TranscriptionRequest,
)


@dataclass
class FakeRecorder:
    started: list[str | None] = field(default_factory=list)
    stop_count: int = 0
    cancel_count: int = 0

    def start(self, device_id: str | None) -> None:
        self.started.append(device_id)

    def stop(self) -> RecordedAudio:
        self.stop_count += 1
        return RecordedAudio(samples=(0.1, -0.1), sample_rate=16_000, channels=1)

    def cancel(self) -> None:
        self.cancel_count += 1


@dataclass
class FakeTranscriptionQueue:
    requests: list[TranscriptionRequest] = field(default_factory=list)
    _success: Callable[[str, Transcript], None] | None = None
    _failure: Callable[[str, Exception], None] | None = None

    def submit(
        self,
        request: TranscriptionRequest,
        on_success: Callable[[str, Transcript], None],
        on_failure: Callable[[str, Exception], None],
    ) -> None:
        self.requests.append(request)
        self._success = on_success
        self._failure = on_failure

    def succeed(self, text: str) -> None:
        assert self._success is not None
        request = self.requests[-1]
        self._success(request.session_id, Transcript(text=text))

    def fail(self, error: Exception) -> None:
        assert self._failure is not None
        request = self.requests[-1]
        self._failure(request.session_id, error)


@dataclass
class FakeDelivery:
    inserted: list[str] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)

    def insert_at_cursor(self, text: str) -> DeliveryResult:
        self.inserted.append(text)
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_PASTE)

    def copy_to_clipboard(self, text: str) -> DeliveryResult:
        self.copied.append(text)
        return DeliveryResult.ok(DeliveryMethod.CLIPBOARD_COPY)


def make_controller(
    *,
    vocabulary: Callable[[], Sequence[str]] | None = None,
    observer_error: Callable[[Exception], None] | None = None,
) -> tuple[DictationController, FakeRecorder, FakeTranscriptionQueue, FakeDelivery]:
    recorder = FakeRecorder()
    queue = FakeTranscriptionQueue()
    delivery = FakeDelivery()
    controller = DictationController(
        recorder=recorder,
        transcription_queue=queue,
        delivery=delivery,
        vocabulary=vocabulary or (lambda: ("HEC-RAS", "FLO-2D")),
        selected_device=lambda: "microphone-1",
        session_ids=iter(("session-1", "session-2", "session-3")).__next__,
        observer_error=observer_error,
    )
    return controller, recorder, queue, delivery


def test_insert_dictation_runs_one_complete_workflow() -> None:
    controller, recorder, queue, delivery = make_controller()

    assert controller.start_recording(DeliveryMode.INSERT)
    assert controller.state is AppState.RECORDING
    assert recorder.started == ["microphone-1"]

    assert controller.stop_recording()
    assert controller.state is AppState.TRANSCRIBING
    assert queue.requests == [
        TranscriptionRequest(
            session_id="session-1",
            audio=RecordedAudio(samples=(0.1, -0.1), sample_rate=16_000, channels=1),
            language="en",
            vocabulary=("HEC-RAS", "FLO-2D"),
            delivery_mode=DeliveryMode.INSERT,
        )
    ]

    queue.succeed("The final transcript.")

    assert delivery.inserted == ["The final transcript."]
    assert delivery.copied == []
    assert controller.state is AppState.IDLE
    assert controller.last_transcript is None


def test_record_and_copy_does_not_insert() -> None:
    controller, _, queue, delivery = make_controller()

    controller.start_recording(DeliveryMode.COPY)
    controller.stop_recording()
    queue.succeed("Keep this on the clipboard.")

    assert delivery.copied == ["Keep this on the clipboard."]
    assert delivery.inserted == []
    assert controller.state is AppState.IDLE


def test_busy_request_is_rejected_without_starting_another_recording() -> None:
    controller, recorder, _, _ = make_controller()

    controller.start_recording(DeliveryMode.INSERT)

    assert not controller.start_recording(DeliveryMode.COPY)
    assert recorder.started == ["microphone-1"]
    assert controller.state is AppState.RECORDING


def test_cancel_discards_audio_and_invalidates_late_results() -> None:
    controller, recorder, queue, delivery = make_controller()

    controller.start_recording(DeliveryMode.INSERT)
    controller.cancel()

    assert recorder.cancel_count == 1
    assert controller.state is AppState.IDLE
    assert delivery.inserted == []
    assert queue.requests == []


def test_transcription_failure_returns_to_error_without_delivery() -> None:
    controller, _, queue, delivery = make_controller()
    controller.start_recording(DeliveryMode.INSERT)
    controller.stop_recording()

    queue.fail(RuntimeError("model failed"))

    assert controller.state is AppState.ERROR
    assert controller.last_error == "model failed"
    assert delivery.inserted == []


def test_delivery_failure_preserves_transcript_for_copy() -> None:
    controller, _, queue, delivery = make_controller()

    def failed_insert(text: str) -> DeliveryResult:
        delivery.inserted.append(text)
        return DeliveryResult.failed(
            DeliveryMethod.CLIPBOARD_PASTE,
            error_code="paste_failed",
            recoverable=True,
        )

    delivery.insert_at_cursor = failed_insert  # type: ignore[method-assign]
    controller.start_recording(DeliveryMode.INSERT)
    controller.stop_recording()
    queue.succeed("Do not lose this.")

    assert controller.state is AppState.ERROR_WITH_TRANSCRIPT
    assert controller.last_transcript == "Do not lose this."

    assert controller.copy_recoverable_transcript()
    assert delivery.copied == ["Do not lose this."]
    assert controller.state is AppState.IDLE


def test_state_listeners_receive_each_accepted_transition() -> None:
    controller, _, queue, _ = make_controller()
    states: list[AppState] = []
    controller.add_state_listener(states.append)

    controller.start_recording(DeliveryMode.INSERT)
    controller.stop_recording()
    queue.succeed("Done.")

    assert states == [
        AppState.RECORDING,
        AppState.TRANSCRIBING,
        AppState.DELIVERING,
        AppState.IDLE,
    ]


def test_vocabulary_failure_moves_transcription_to_error() -> None:
    def failed_vocabulary() -> Sequence[str]:
        raise RuntimeError("vocabulary unreadable")

    controller, recorder, queue, delivery = make_controller(vocabulary=failed_vocabulary)

    controller.start_recording(DeliveryMode.INSERT)

    assert not controller.stop_recording()
    assert recorder.stop_count == 1
    assert queue.requests == []
    assert delivery.inserted == []
    assert controller.state is AppState.ERROR
    assert controller.last_error == "vocabulary unreadable"


def test_state_listener_failure_does_not_interrupt_workflow() -> None:
    observer_errors: list[Exception] = []
    controller, _, queue, delivery = make_controller(observer_error=observer_errors.append)

    def broken_listener(state: AppState) -> None:
        raise RuntimeError(f"UI failed in {state.value}")

    controller.add_state_listener(broken_listener)
    assert controller.start_recording(DeliveryMode.INSERT)
    assert controller.stop_recording()
    queue.succeed("Still delivered.")

    assert delivery.inserted == ["Still delivered."]
    assert controller.state is AppState.IDLE
    assert len(observer_errors) == 4


def test_cancel_failure_moves_controller_to_error() -> None:
    controller, recorder, _, _ = make_controller()

    def failed_cancel() -> None:
        raise RuntimeError("device would not close")

    recorder.cancel = failed_cancel  # type: ignore[method-assign]
    controller.start_recording(DeliveryMode.INSERT)

    assert not controller.cancel()
    assert controller.state is AppState.ERROR
    assert controller.last_error == "device would not close"


def test_recovery_copy_exception_keeps_transcript_available() -> None:
    controller, _, queue, delivery = make_controller()

    def failed_insert(text: str) -> DeliveryResult:
        return DeliveryResult.failed(
            DeliveryMethod.CLIPBOARD_PASTE,
            error_code="paste_failed",
            recoverable=True,
        )

    def failed_copy(text: str) -> DeliveryResult:
        raise RuntimeError("clipboard locked")

    delivery.insert_at_cursor = failed_insert  # type: ignore[method-assign]
    delivery.copy_to_clipboard = failed_copy  # type: ignore[method-assign]
    controller.start_recording(DeliveryMode.INSERT)
    controller.stop_recording()
    queue.succeed("Keep this available.")

    assert not controller.copy_recoverable_transcript()
    assert controller.state is AppState.ERROR_WITH_TRANSCRIPT
    assert controller.last_transcript == "Keep this available."
    assert controller.last_error == "clipboard locked"
