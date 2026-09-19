from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from cursor_dictation.core.models import RecordedAudio


@dataclass(frozen=True, slots=True)
class AudioDevice:
    id: str
    name: str
    max_input_channels: int
    default_sample_rate: float
    is_default: bool = False


class AudioRecorderError(RuntimeError):
    """Base exception for microphone capture failures."""


class AudioDeviceError(AudioRecorderError):
    """The microphone list or selected device is unavailable."""


class AudioCaptureError(AudioRecorderError):
    """The active input stream stopped before usable audio was complete."""


class RecorderAlreadyRunningError(AudioRecorderError):
    """A recording is already in progress."""


class RecorderNotRunningError(AudioRecorderError):
    """No recording is available to stop."""


class RecordingCompletionReason(StrEnum):
    LIMIT_REACHED = "limit_reached"
    CAPTURE_ERROR = "capture_error"
    DEVICE_STOPPED = "device_stopped"
    MANUAL_STOP = "manual_stop"
    CANCELLED = "cancelled"


class AudioRecorder(Protocol):
    def list_devices(self) -> tuple[AudioDevice, ...]: ...

    def start(self, device_id: str | None) -> None: ...

    def stop(self) -> RecordedAudio: ...

    def cancel(self) -> None: ...

    def wait_for_completion(
        self, timeout: float | None = None
    ) -> RecordingCompletionReason | None: ...
