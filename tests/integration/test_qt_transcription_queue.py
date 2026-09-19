from __future__ import annotations

import threading
from collections.abc import Sequence

from cursor_dictation.application.qt_transcription_queue import QtTranscriptionQueue
from cursor_dictation.core.models import (
    DeliveryMode,
    RecordedAudio,
    Transcript,
    TranscriptionRequest,
)


class SuccessfulEngine:
    def __init__(self) -> None:
        self.worker_thread_id: int | None = None

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        self.worker_thread_id = threading.get_ident()
        return Transcript(text=f"{language}: {vocabulary[0]}")


class FailingEngine:
    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        raise RuntimeError("local inference failed")


def request() -> TranscriptionRequest:
    return TranscriptionRequest(
        session_id="session-1",
        audio=RecordedAudio(samples=(0.1, -0.1), sample_rate=16_000, channels=1),
        language="en",
        vocabulary=("HEC-RAS",),
        delivery_mode=DeliveryMode.INSERT,
    )


def test_success_callback_returns_to_qt_owner_thread(qtbot) -> None:  # type: ignore[no-untyped-def]
    owner_thread_id = threading.get_ident()
    engine = SuccessfulEngine()
    queue = QtTranscriptionQueue(lambda: engine)
    received: list[tuple[str, Transcript, int]] = []

    queue.submit(
        request(),
        lambda session_id, transcript: received.append(
            (session_id, transcript, threading.get_ident())
        ),
        lambda _session_id, error: (_ for _ in ()).throw(error),
    )
    qtbot.waitUntil(lambda: bool(received), timeout=3_000)

    assert engine.worker_thread_id is not None
    assert engine.worker_thread_id != owner_thread_id
    assert received == [("session-1", Transcript(text="en: HEC-RAS"), owner_thread_id)]
    queue.shutdown()


def test_failure_callback_returns_original_exception(qtbot) -> None:  # type: ignore[no-untyped-def]
    queue = QtTranscriptionQueue(FailingEngine)
    failures: list[tuple[str, Exception]] = []

    queue.submit(
        request(),
        lambda _session_id, _transcript: None,
        lambda session_id, error: failures.append((session_id, error)),
    )
    qtbot.waitUntil(lambda: bool(failures), timeout=3_000)

    assert failures[0][0] == "session-1"
    assert isinstance(failures[0][1], RuntimeError)
    assert str(failures[0][1]) == "local inference failed"
    queue.shutdown()
