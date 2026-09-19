"""In-memory microphone capture."""

from cursor_dictation.audio.recorder import (
    AudioCaptureError,
    AudioDevice,
    AudioDeviceError,
    AudioRecorder,
    RecorderAlreadyRunningError,
    RecorderNotRunningError,
    RecordingCompletionReason,
)
from cursor_dictation.audio.sounddevice_recorder import SoundDeviceRecorder

__all__ = [
    "AudioCaptureError",
    "AudioDevice",
    "AudioDeviceError",
    "AudioRecorder",
    "RecorderAlreadyRunningError",
    "RecorderNotRunningError",
    "RecordingCompletionReason",
    "SoundDeviceRecorder",
]
