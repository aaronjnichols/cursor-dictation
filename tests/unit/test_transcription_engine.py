from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from cursor_dictation.core.models import RecordedAudio
from cursor_dictation.transcription.engine import (
    EmptyTranscriptError,
    InvalidAudioError,
    InvalidLocalModelError,
    ModelNotLoadedError,
    UnsupportedLanguageError,
)
from cursor_dictation.transcription.faster_whisper_engine import FasterWhisperEngine


class FakeWhisperModel:
    def __init__(self, segments: list[str]) -> None:
        self._segments = segments
        self.calls: list[tuple[np.ndarray[Any, Any], dict[str, object]]] = []
        self.generator_consumed = False

    def transcribe(
        self, samples: np.ndarray[Any, Any], **kwargs: object
    ) -> tuple[Iterator[SimpleNamespace], object]:
        self.calls.append((samples, kwargs))

        def generate() -> Iterator[SimpleNamespace]:
            for text in self._segments:
                yield SimpleNamespace(text=text)
            self.generator_consumed = True

        return generate(), SimpleNamespace(language="en")


def _audio() -> RecordedAudio:
    return RecordedAudio(samples=[0.0, 0.25, -0.25], sample_rate=16_000, channels=1)


def _model_directory(root: Path, name: str = "model") -> Path:
    model_path = root / name
    model_path.mkdir()
    (model_path / "model.bin").write_bytes(b"model")
    (model_path / "config.json").write_text("{}", encoding="utf-8")
    (model_path / "tokenizer.json").write_text("{}", encoding="utf-8")
    return model_path


def test_load_uses_only_local_cpu_int8_model(tmp_path: Path) -> None:
    model_path = _model_directory(tmp_path, "small.en")
    model = FakeWhisperModel(["Hello."])
    calls: list[tuple[str, dict[str, object]]] = []

    def factory(path: str, **kwargs: object) -> FakeWhisperModel:
        calls.append((path, kwargs))
        return model

    engine = FasterWhisperEngine(model_factory=factory)

    info = engine.load(model_path)

    assert calls == [
        (
            str(model_path),
            {"device": "cpu", "compute_type": "int8", "local_files_only": True},
        )
    ]
    assert info.path == model_path.resolve()
    assert info.device == "cpu"
    assert info.compute_type == "int8"


def test_transcribe_consumes_generator_and_passes_vocabulary_prompt(tmp_path: Path) -> None:
    model_path = _model_directory(tmp_path)
    model = FakeWhisperModel(["  HEC-RAS", " works.", "  "])
    engine = FasterWhisperEngine(model_factory=lambda *_args, **_kwargs: model)
    engine.load(model_path)

    transcript = engine.transcribe(
        _audio(),
        language="en",
        vocabulary=("Atwell", "HEC-RAS"),
    )

    assert transcript.text == "HEC-RAS works."
    assert model.generator_consumed is True
    samples, kwargs = model.calls[-1]
    assert samples.dtype == np.float32
    np.testing.assert_allclose(samples, [0.0, 0.25, -0.25])
    assert kwargs == {
        "language": "en",
        "task": "transcribe",
        "initial_prompt": "Atwell, HEC-RAS",
    }


def test_transcribe_rejects_non_english_language(tmp_path: Path) -> None:
    model_path = _model_directory(tmp_path)
    engine = FasterWhisperEngine(model_factory=lambda *_args, **_kwargs: FakeWhisperModel([]))
    engine.load(model_path)

    with pytest.raises(UnsupportedLanguageError):
        engine.transcribe(_audio(), language="es", vocabulary=())


def test_transcribe_requires_loaded_model() -> None:
    engine = FasterWhisperEngine(model_factory=lambda *_args, **_kwargs: FakeWhisperModel([]))

    with pytest.raises(ModelNotLoadedError):
        engine.transcribe(_audio(), language="en", vocabulary=())


def test_empty_transcript_is_recoverable_error(tmp_path: Path) -> None:
    model_path = _model_directory(tmp_path)
    engine = FasterWhisperEngine(
        model_factory=lambda *_args, **_kwargs: FakeWhisperModel([" ", "\n"])
    )
    engine.load(model_path)

    with pytest.raises(EmptyTranscriptError):
        engine.transcribe(_audio(), language="en", vocabulary=())


def test_failed_load_keeps_previous_model_active(tmp_path: Path) -> None:
    first_path = _model_directory(tmp_path, "first")
    bad_path = _model_directory(tmp_path, "bad")
    first_model = FakeWhisperModel(["Still active."])

    def factory(path: str, **_kwargs: object) -> FakeWhisperModel:
        if path == str(bad_path):
            raise RuntimeError("invalid model")
        return first_model

    engine = FasterWhisperEngine(model_factory=factory)
    engine.load(first_path)

    with pytest.raises(RuntimeError, match="invalid model"):
        engine.load(bad_path)

    assert engine.loaded_model_path == first_path.resolve()
    assert engine.transcribe(_audio(), language="en", vocabulary=()).text == "Still active."


def test_load_rejects_incomplete_directory_before_model_factory(tmp_path: Path) -> None:
    model_path = tmp_path / "incomplete"
    model_path.mkdir()
    (model_path / "model.bin").write_bytes(b"model")
    factory_called = False

    def factory(*_args: object, **_kwargs: object) -> FakeWhisperModel:
        nonlocal factory_called
        factory_called = True
        return FakeWhisperModel([])

    engine = FasterWhisperEngine(model_factory=factory)

    with pytest.raises(InvalidLocalModelError, match=r"config\.json.*tokenizer\.json"):
        engine.load(model_path)
    assert factory_called is False


@pytest.mark.parametrize(
    "audio",
    [
        RecordedAudio(samples=[0.0], sample_rate=48_000, channels=1),
        RecordedAudio(samples=[], sample_rate=16_000, channels=1),
        RecordedAudio(samples=[0.0, 0.0], sample_rate=16_000, channels=2),
    ],
)
def test_transcribe_rejects_audio_outside_16khz_mono_contract(
    tmp_path: Path, audio: RecordedAudio
) -> None:
    model_path = _model_directory(tmp_path)
    model = FakeWhisperModel(["should not run"])
    engine = FasterWhisperEngine(model_factory=lambda *_args, **_kwargs: model)
    engine.load(model_path)

    with pytest.raises(InvalidAudioError):
        engine.transcribe(audio, language="en", vocabulary=())
    assert model.calls == []
