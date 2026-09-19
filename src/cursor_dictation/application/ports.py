from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from cursor_dictation.core.models import (
    DeliveryResult,
    RecordedAudio,
    Transcript,
    TranscriptionRequest,
)


class AudioRecorder(Protocol):
    def start(self, device_id: str | None) -> None: ...

    def stop(self) -> RecordedAudio: ...

    def cancel(self) -> None: ...


class TranscriptionQueue(Protocol):
    def submit(
        self,
        request: TranscriptionRequest,
        on_success: Callable[[str, Transcript], None],
        on_failure: Callable[[str, Exception], None],
    ) -> None: ...


class TextDelivery(Protocol):
    def insert_at_cursor(self, text: str) -> DeliveryResult: ...

    def copy_to_clipboard(self, text: str) -> DeliveryResult: ...


class TranscriptHistory(Protocol):
    def append(self, text: str, mode: str) -> None: ...
