"""Local Whisper model loading and transcription."""

from cursor_dictation.transcription.engine import (
    EmptyTranscriptError,
    InvalidAudioError,
    InvalidLocalModelError,
    ModelInfo,
    ModelNotLoadedError,
    TranscriptionEngine,
    UnsupportedLanguageError,
)
from cursor_dictation.transcription.faster_whisper_engine import FasterWhisperEngine

__all__ = [
    "EmptyTranscriptError",
    "FasterWhisperEngine",
    "InvalidAudioError",
    "InvalidLocalModelError",
    "ModelInfo",
    "ModelNotLoadedError",
    "TranscriptionEngine",
    "UnsupportedLanguageError",
]
