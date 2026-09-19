from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cursor_dictation.core.models import RecordedAudio, Transcript


@dataclass(frozen=True, slots=True)
class ModelInfo:
    path: Path
    device: str
    compute_type: str


class TranscriptionError(RuntimeError):
    """Base exception for local transcription failures."""


class ModelNotLoadedError(TranscriptionError):
    """Transcription was requested before a model was loaded."""


class InvalidLocalModelError(TranscriptionError):
    """A local model directory is incomplete or cannot stay offline."""


class InvalidAudioError(TranscriptionError):
    """Recorded audio does not match the Whisper input contract."""


class UnsupportedLanguageError(TranscriptionError):
    """Version one only supports English transcription."""


class EmptyTranscriptError(TranscriptionError):
    """The model completed without returning usable text."""


class TranscriptionEngine(Protocol):
    def load(self, model_path: Path) -> ModelInfo: ...

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript: ...
