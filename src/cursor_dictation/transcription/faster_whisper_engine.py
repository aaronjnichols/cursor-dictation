from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Protocol, cast

import numpy as np
from numpy.typing import NDArray

from cursor_dictation.core.models import RecordedAudio, Transcript
from cursor_dictation.transcription.engine import (
    EmptyTranscriptError,
    InvalidAudioError,
    InvalidLocalModelError,
    ModelInfo,
    ModelNotLoadedError,
    UnsupportedLanguageError,
)


class _Segment(Protocol):
    text: str


class _WhisperModel(Protocol):
    def transcribe(
        self,
        audio: NDArray[np.float32],
        **kwargs: object,
    ) -> tuple[Iterable[_Segment], object]: ...


ModelFactory = Callable[..., _WhisperModel]


class FasterWhisperEngine:
    def __init__(self, *, model_factory: ModelFactory | None = None) -> None:
        self._model_factory = model_factory or _create_model
        self._model: _WhisperModel | None = None
        self._model_info: ModelInfo | None = None

    @property
    def loaded_model_path(self) -> Path | None:
        return self._model_info.path if self._model_info is not None else None

    def load(self, model_path: Path) -> ModelInfo:
        resolved = model_path.resolve()
        if not resolved.is_dir():
            raise FileNotFoundError(f"Local model directory does not exist: {resolved}")
        required_files = ("model.bin", "config.json", "tokenizer.json")
        missing = tuple(name for name in required_files if not (resolved / name).is_file())
        if missing:
            raise InvalidLocalModelError(
                "Local model is missing required files: " + ", ".join(missing)
            )

        candidate = self._model_factory(
            str(resolved),
            device="cpu",
            compute_type="int8",
            local_files_only=True,
        )
        info = ModelInfo(path=resolved, device="cpu", compute_type="int8")
        self._model = candidate
        self._model_info = info
        return info

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: Sequence[str],
    ) -> Transcript:
        model = self._model
        if model is None:
            raise ModelNotLoadedError("Load a local model before transcribing")
        if language.strip().lower() not in {"en", "english"}:
            raise UnsupportedLanguageError("Cursor Dictation only supports English")
        if audio.sample_rate != 16_000 or audio.channels != 1 or len(audio.samples) == 0:
            raise InvalidAudioError("Whisper input must be non-empty, 16 kHz, mono audio")

        samples = np.asarray(audio.samples, dtype=np.float32).reshape(-1)
        kwargs: dict[str, object] = {"language": "en", "task": "transcribe"}
        prompt = ", ".join(term.strip() for term in vocabulary if term.strip())
        if prompt:
            kwargs["initial_prompt"] = prompt

        segments, _metadata = model.transcribe(samples, **kwargs)
        text = _assemble_segments(segment.text for segment in segments)
        if not text:
            raise EmptyTranscriptError("The recording did not produce any text")
        return Transcript(text=text)


def _create_model(model_path: str, **kwargs: object) -> _WhisperModel:
    from faster_whisper import WhisperModel

    return cast(_WhisperModel, WhisperModel(model_path, **kwargs))


def _assemble_segments(parts: Iterable[str]) -> str:
    text = ""
    punctuation = frozenset(",.;:!?)]}%")
    for part in parts:
        if not part:
            continue
        if not text:
            text = part.lstrip()
            continue
        stripped = part.lstrip()
        if not stripped or text[-1].isspace() or part[0].isspace() or stripped[0] in punctuation:
            text += part
        else:
            text += " " + part
    return text.strip()
