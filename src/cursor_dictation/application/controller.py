from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import suppress

from cursor_dictation.application.ports import (
    AudioRecorder,
    TextDelivery,
    TranscriptHistory,
    TranscriptionQueue,
)
from cursor_dictation.core.events import Event
from cursor_dictation.core.models import (
    AppState,
    DeliveryMode,
    DeliveryResult,
    Transcript,
    TranscriptionRequest,
)
from cursor_dictation.core.state_machine import transition


class DictationController:
    """Coordinates one dictation at a time without depending on Qt or Windows APIs."""

    def __init__(
        self,
        *,
        recorder: AudioRecorder,
        transcription_queue: TranscriptionQueue,
        delivery: TextDelivery,
        vocabulary: Callable[[], Sequence[str]],
        selected_device: Callable[[], str | None],
        session_ids: Callable[[], str],
        observer_error: Callable[[Exception], None] | None = None,
        history: TranscriptHistory | None = None,
        completion_listener: Callable[[DeliveryMode, DeliveryResult, int], None] | None = None,
        initial_state: AppState = AppState.IDLE,
    ) -> None:
        self._recorder = recorder
        self._transcription_queue = transcription_queue
        self._delivery = delivery
        self._vocabulary = vocabulary
        self._selected_device = selected_device
        self._session_ids = session_ids
        self._observer_error = observer_error
        self._history = history
        self._completion_listeners: list[Callable[[DeliveryMode, DeliveryResult, int], None]] = []
        if completion_listener is not None:
            self._completion_listeners.append(completion_listener)
        self._state = initial_state
        self._active_session: str | None = None
        self._delivery_mode: DeliveryMode | None = None
        self._state_listeners: list[Callable[[AppState], None]] = []
        self.last_error: str | None = None
        self.last_transcript: str | None = None

    @property
    def state(self) -> AppState:
        return self._state

    def add_state_listener(self, listener: Callable[[AppState], None]) -> None:
        self._state_listeners.append(listener)

    def add_completion_listener(
        self,
        listener: Callable[[DeliveryMode, DeliveryResult, int], None],
    ) -> None:
        self._completion_listeners.append(listener)

    def start_recording(self, mode: DeliveryMode) -> bool:
        if self._state is not AppState.IDLE:
            return False

        session_id = self._session_ids()
        try:
            self._recorder.start(self._selected_device())
        except Exception as error:
            self.last_error = str(error)
            self._move(Event.OPERATION_FAILED)
            return False

        self._active_session = session_id
        self._delivery_mode = mode
        self.last_error = None
        self.last_transcript = None
        self._move(Event.START_RECORDING)
        return True

    def stop_recording(self) -> bool:
        if self._state is not AppState.RECORDING:
            return False

        session_id = self._require_session()
        mode = self._require_delivery_mode()
        try:
            audio = self._recorder.stop()
        except Exception as error:
            self.last_error = str(error)
            self._move(Event.OPERATION_FAILED)
            return False

        self._move(Event.RECORDING_COMPLETED)
        try:
            request = TranscriptionRequest(
                session_id=session_id,
                audio=audio,
                language="en",
                vocabulary=tuple(self._vocabulary()),
                delivery_mode=mode,
            )
            self._transcription_queue.submit(
                request,
                self._transcription_succeeded,
                self._transcription_failed,
            )
        except Exception as error:
            self._transcription_failed(session_id, error)
            return False
        return True

    def cancel(self) -> bool:
        if self._state is not AppState.RECORDING:
            return False
        try:
            self._recorder.cancel()
        except Exception as error:
            self._active_session = None
            self._delivery_mode = None
            self.last_error = str(error)
            self.last_transcript = None
            self._move(Event.OPERATION_FAILED)
            return False
        self._active_session = None
        self._delivery_mode = None
        self.last_error = None
        self.last_transcript = None
        self._move(Event.CANCEL_REQUESTED)
        return True

    def reset_error(self) -> bool:
        if self._state not in {AppState.ERROR, AppState.ERROR_WITH_TRANSCRIPT}:
            return False
        self.last_error = None
        self.last_transcript = None
        self._move(Event.RESET)
        return True

    def copy_recoverable_transcript(self) -> bool:
        if self._state is not AppState.ERROR_WITH_TRANSCRIPT or self.last_transcript is None:
            return False
        try:
            result = self._delivery.copy_to_clipboard(self.last_transcript)
        except Exception as error:
            self.last_error = str(error)
            return False
        if not result.success:
            self.last_error = result.error_code or "copy_failed"
            return False
        self._active_session = None
        self._delivery_mode = None
        self.last_error = None
        self.last_transcript = None
        self._move(Event.RESET)
        return True

    def discard_recoverable_transcript(self) -> bool:
        if self._state is not AppState.ERROR_WITH_TRANSCRIPT:
            return False
        self._active_session = None
        self._delivery_mode = None
        self.last_error = None
        self.last_transcript = None
        self._move(Event.RESET)
        return True

    def _transcription_succeeded(self, session_id: str, transcript: Transcript) -> None:
        if session_id != self._active_session or self._state is not AppState.TRANSCRIBING:
            return
        text = transcript.text.strip()
        if not text:
            self._transcription_failed(session_id, ValueError("No speech was recognized."))
            return

        mode = self._require_delivery_mode()
        self.last_transcript = text
        self._move(Event.TRANSCRIPT_COMPLETED)
        try:
            result = (
                self._delivery.insert_at_cursor(text)
                if mode is DeliveryMode.INSERT
                else self._delivery.copy_to_clipboard(text)
            )
        except Exception as error:
            self.last_error = str(error)
            self._move(Event.OPERATION_FAILED)
            return

        if not result.success:
            self.last_error = result.error_code or "delivery_failed"
            self._move(Event.OPERATION_FAILED)
            return

        self._active_session = None
        self._delivery_mode = None
        self.last_error = None
        self.last_transcript = None
        self._move(Event.DELIVERY_COMPLETED)
        if self._history is not None:
            try:
                self._history.append(text, mode.value)
            except Exception as error:
                self._report_observer_error(error)
        for listener in tuple(self._completion_listeners):
            try:
                listener(mode, result, len(text.split()))
            except Exception as error:
                self._report_observer_error(error)

    def _transcription_failed(self, session_id: str, error: Exception) -> None:
        if session_id != self._active_session or self._state is not AppState.TRANSCRIBING:
            return
        self._active_session = None
        self._delivery_mode = None
        self.last_error = str(error)
        self.last_transcript = None
        self._move(Event.OPERATION_FAILED)

    def _move(self, event: Event) -> None:
        self._state = transition(self._state, event)
        for listener in tuple(self._state_listeners):
            try:
                listener(self._state)
            except Exception as error:
                self._report_observer_error(error)

    def _report_observer_error(self, error: Exception) -> None:
        if self._observer_error is not None:
            with suppress(Exception):
                self._observer_error(error)

    def _require_session(self) -> str:
        if self._active_session is None:
            raise RuntimeError("The active recording has no session identifier.")
        return self._active_session

    def _require_delivery_mode(self) -> DeliveryMode:
        if self._delivery_mode is None:
            raise RuntimeError("The active recording has no delivery mode.")
        return self._delivery_mode
