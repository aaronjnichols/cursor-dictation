from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from PySide6.QtCore import (
    QObject,
    QRunnable,
    Qt,
    QThread,
    QThreadPool,
    Signal,
    Slot,
)

from cursor_dictation.core.models import RecordedAudio, Transcript, TranscriptionRequest


class _Transcriber(Protocol):
    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript: ...


class _WorkerSignals(QObject):
    succeeded = Signal(str, object)
    failed = Signal(str, object)


class _TranscriptionWorker(QRunnable):
    def __init__(
        self,
        engine_provider: Callable[[], _Transcriber],
        request: TranscriptionRequest,
        signals: _WorkerSignals,
    ) -> None:
        super().__init__()
        self._engine_provider = engine_provider
        self._request = request
        self._signals = signals

    @Slot()
    def run(self) -> None:
        try:
            engine = self._engine_provider()
            transcript = engine.transcribe(
                self._request.audio,
                self._request.language,
                self._request.vocabulary,
            )
        except Exception as error:
            self._signals.failed.emit(self._request.session_id, error)
            return
        self._signals.succeeded.emit(self._request.session_id, transcript)


SuccessCallback = Callable[[str, Transcript], None]
FailureCallback = Callable[[str, Exception], None]


class QtTranscriptionQueue(QObject):
    """Runs inference off the UI thread and completes callbacks on the Qt owner thread."""

    def __init__(
        self,
        engine_provider: Callable[[], _Transcriber],
        *,
        thread_pool: QThreadPool | None = None,
    ) -> None:
        super().__init__()
        self._engine_provider = engine_provider
        self._thread_pool = thread_pool or QThreadPool(self)
        self._thread_pool.setMaxThreadCount(1)
        self._callbacks: dict[str, tuple[SuccessCallback, FailureCallback]] = {}
        self._signals = _WorkerSignals(self)
        connection = Qt.ConnectionType.QueuedConnection
        self._signals.succeeded.connect(self._complete_success, connection)
        self._signals.failed.connect(self._complete_failure, connection)

    def submit(
        self,
        request: TranscriptionRequest,
        on_success: SuccessCallback,
        on_failure: FailureCallback,
    ) -> None:
        if QThread.currentThread() is not self.thread():
            raise RuntimeError("Transcription jobs must be submitted from the Qt owner thread.")
        if request.session_id in self._callbacks:
            raise ValueError(f"A transcription job already uses {request.session_id}.")
        self._callbacks[request.session_id] = (on_success, on_failure)
        self._thread_pool.start(_TranscriptionWorker(self._engine_provider, request, self._signals))

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        return self._thread_pool.waitForDone(timeout_ms)

    @Slot(str, object)
    def _complete_success(self, session_id: str, value: object) -> None:
        callbacks = self._callbacks.pop(session_id, None)
        if callbacks is None:
            return
        if not isinstance(value, Transcript):
            callbacks[1](session_id, TypeError("Transcription worker returned an invalid result."))
            return
        callbacks[0](session_id, value)

    @Slot(str, object)
    def _complete_failure(self, session_id: str, value: object) -> None:
        callbacks = self._callbacks.pop(session_id, None)
        if callbacks is None:
            return
        error = value if isinstance(value, Exception) else RuntimeError(str(value))
        callbacks[1](session_id, error)
