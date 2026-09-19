from __future__ import annotations

import json
from pathlib import Path

import pytest

from cursor_dictation.core.models import RecordedAudio, Transcript
from cursor_dictation.transcription.engine import EmptyTranscriptError, ModelInfo
from cursor_dictation.transcription.model_manager import (
    CustomModelValidationError,
    ModelManager,
)


class FakeEngine:
    def __init__(
        self,
        *,
        load_error: Exception | None = None,
        smoke_error: Exception | None = None,
    ) -> None:
        self.load_error = load_error
        self.smoke_error = smoke_error
        self.loaded_path: Path | None = None
        self.smoke_calls = 0

    def load(self, model_path: Path) -> ModelInfo:
        if self.load_error is not None:
            raise self.load_error
        self.loaded_path = model_path.resolve()
        return ModelInfo(path=model_path.resolve(), device="cpu", compute_type="int8")

    def transcribe(
        self,
        audio: RecordedAudio,
        language: str,
        vocabulary: tuple[str, ...],
    ) -> Transcript:
        self.smoke_calls += 1
        if self.smoke_error is not None:
            raise self.smoke_error
        return Transcript("fixture")


def _write_custom_model(path: Path, *, language: str = "en") -> None:
    path.mkdir()
    (path / "model.bin").write_bytes(b"model")
    (path / "config.json").write_text(json.dumps({"language": language}), encoding="utf-8")
    (path / "tokenizer.json").write_text(json.dumps({"version": "1.0"}), encoding="utf-8")


def _smoke_audio() -> RecordedAudio:
    return RecordedAudio(samples=[0.0], sample_rate=16_000, channels=1)


def test_valid_custom_model_becomes_active_only_after_smoke_test(tmp_path: Path) -> None:
    model_path = tmp_path / "valid"
    _write_custom_model(model_path)
    candidate = FakeEngine()
    manager = ModelManager(engine_factory=lambda: candidate)

    info = manager.activate_custom(model_path, smoke_audio=_smoke_audio())

    assert manager.active_engine is candidate
    assert manager.active_model == info
    assert candidate.smoke_calls == 1


def test_prepared_model_does_not_replace_active_model_until_committed(tmp_path: Path) -> None:
    first_path = tmp_path / "first"
    next_path = tmp_path / "next"
    _write_custom_model(first_path)
    _write_custom_model(next_path)
    first = FakeEngine()
    next_engine = FakeEngine()
    engines = iter((first, next_engine))
    manager = ModelManager(engine_factory=lambda: next(engines))
    manager.activate_custom(first_path, smoke_audio=_smoke_audio())

    prepared = manager.prepare_custom(next_path, smoke_audio=_smoke_audio())

    assert manager.active_engine is first
    manager.activate(prepared)
    assert manager.active_engine is next_engine
    assert manager.active_model == prepared.info


def test_empty_transcript_is_an_acceptable_custom_model_smoke_result(tmp_path: Path) -> None:
    model_path = tmp_path / "valid"
    _write_custom_model(model_path)
    candidate = FakeEngine(smoke_error=EmptyTranscriptError("silence"))
    manager = ModelManager(engine_factory=lambda: candidate)

    info = manager.activate_custom(model_path, smoke_audio=_smoke_audio())

    assert info.path == model_path.resolve()
    assert manager.active_engine is candidate


def test_verified_model_can_be_prepared_without_running_inference(tmp_path: Path) -> None:
    model_path = tmp_path / "verified"
    _write_custom_model(model_path)
    candidate = FakeEngine(smoke_error=RuntimeError("must not transcribe"))
    manager = ModelManager(engine_factory=lambda: candidate)

    prepared = manager.prepare_verified(model_path)
    manager.activate(prepared)

    assert candidate.smoke_calls == 0
    assert manager.active_model == prepared.info


def test_failed_candidate_does_not_replace_active_model(tmp_path: Path) -> None:
    first_path = tmp_path / "first"
    bad_path = tmp_path / "bad"
    _write_custom_model(first_path)
    _write_custom_model(bad_path)
    first = FakeEngine()
    bad = FakeEngine(load_error=RuntimeError("cannot load"))
    engines = iter((first, bad))
    manager = ModelManager(engine_factory=lambda: next(engines))
    manager.activate_custom(first_path, smoke_audio=_smoke_audio())

    with pytest.raises(CustomModelValidationError, match="load"):
        manager.activate_custom(bad_path, smoke_audio=_smoke_audio())

    assert manager.active_engine is first
    assert manager.active_model is not None
    assert manager.active_model.path == first_path.resolve()


def test_failed_smoke_test_does_not_replace_active_model(tmp_path: Path) -> None:
    first_path = tmp_path / "first"
    bad_path = tmp_path / "bad"
    _write_custom_model(first_path)
    _write_custom_model(bad_path)
    first = FakeEngine()
    bad = FakeEngine(smoke_error=RuntimeError("bad inference"))
    engines = iter((first, bad))
    manager = ModelManager(engine_factory=lambda: next(engines))
    manager.activate_custom(first_path, smoke_audio=_smoke_audio())

    with pytest.raises(CustomModelValidationError, match="smoke"):
        manager.activate_custom(bad_path, smoke_audio=_smoke_audio())

    assert manager.active_engine is first


def test_structural_validation_rejects_bad_json_and_non_english_model(tmp_path: Path) -> None:
    bad_json = tmp_path / "bad-json"
    _write_custom_model(bad_json)
    (bad_json / "tokenizer.json").write_text("not json", encoding="utf-8")
    non_english = tmp_path / "multilingual"
    _write_custom_model(non_english, language="fr")
    factory_calls = 0

    def factory() -> FakeEngine:
        nonlocal factory_calls
        factory_calls += 1
        return FakeEngine()

    manager = ModelManager(engine_factory=factory)

    with pytest.raises(CustomModelValidationError, match=r"tokenizer\.json"):
        manager.activate_custom(bad_json, smoke_audio=_smoke_audio())
    with pytest.raises(CustomModelValidationError, match="English"):
        manager.activate_custom(non_english, smoke_audio=_smoke_audio())
    assert factory_calls == 0


def test_structural_validation_requires_ct2_files(tmp_path: Path) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "config.json").write_text("{}", encoding="utf-8")
    (incomplete / "tokenizer.json").write_text("{}", encoding="utf-8")
    manager = ModelManager(engine_factory=FakeEngine)

    with pytest.raises(CustomModelValidationError, match=r"model\.bin"):
        manager.activate_custom(incomplete, smoke_audio=_smoke_audio())
