from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class AppState(StrEnum):
    STARTING = "starting"
    FIRST_RUN_SETUP = "first_run_setup"
    LOADING_MODEL = "loading_model"
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    DELIVERING = "delivering"
    SETTINGS_OPEN = "settings_open"
    ERROR = "error"
    ERROR_WITH_TRANSCRIPT = "error_with_transcript"


class DeliveryMode(StrEnum):
    INSERT = "insert"
    COPY = "copy"


class DeliveryMethod(StrEnum):
    CLIPBOARD_PASTE = "clipboard_paste"
    CLIPBOARD_COPY = "clipboard_copy"
    UNICODE_INPUT = "unicode_input"


@dataclass(frozen=True, slots=True)
class RecordedAudio:
    samples: Sequence[float]
    sample_rate: int
    channels: int

    def __post_init__(self) -> None:
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.sample_rate / self.channels


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    success: bool
    method: DeliveryMethod
    recoverable: bool
    error_code: str | None = None

    @classmethod
    def ok(cls, method: DeliveryMethod) -> DeliveryResult:
        return cls(success=True, method=method, recoverable=False)

    @classmethod
    def failed(
        cls,
        method: DeliveryMethod,
        *,
        error_code: str,
        recoverable: bool,
    ) -> DeliveryResult:
        return cls(
            success=False,
            method=method,
            recoverable=recoverable,
            error_code=error_code,
        )


@dataclass(frozen=True, slots=True)
class TranscriptionRequest:
    session_id: str
    audio: RecordedAudio
    language: str
    vocabulary: tuple[str, ...]
    delivery_mode: DeliveryMode
