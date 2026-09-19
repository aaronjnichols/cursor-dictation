from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

from cursor_dictation.core.models import RecordedAudio
from cursor_dictation.transcription.engine import ModelInfo, TranscriptionEngine

_CUSTOM_MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")


class CustomModelValidationError(ValueError):
    """A custom model failed structural, load, or smoke validation."""


class ModelManager:
    def __init__(self, *, engine_factory: Callable[[], TranscriptionEngine]) -> None:
        self._engine_factory = engine_factory
        self._active_engine: TranscriptionEngine | None = None
        self._active_model: ModelInfo | None = None

    @property
    def active_engine(self) -> TranscriptionEngine | None:
        return self._active_engine

    @property
    def active_model(self) -> ModelInfo | None:
        return self._active_model

    def activate_custom(self, path: Path, *, smoke_audio: RecordedAudio) -> ModelInfo:
        resolved = path.resolve()
        _validate_custom_structure(resolved)

        try:
            candidate = self._engine_factory()
            info = candidate.load(resolved)
        except Exception as error:
            raise CustomModelValidationError(f"Custom model load failed: {error}") from error

        try:
            candidate.transcribe(smoke_audio, language="en", vocabulary=())
        except Exception as error:
            raise CustomModelValidationError(f"Custom model smoke test failed: {error}") from error

        self._active_engine = candidate
        self._active_model = info
        return info


def _validate_custom_structure(path: Path) -> None:
    if not path.is_dir():
        raise CustomModelValidationError(f"Custom model directory does not exist: {path}")
    missing = tuple(name for name in _CUSTOM_MODEL_FILES if not (path / name).is_file())
    if missing:
        raise CustomModelValidationError("Custom model is missing: " + ", ".join(missing))

    config = _read_json_object(path / "config.json")
    _read_json_object(path / "tokenizer.json")
    language = config.get("language")
    if language is not None and not _supports_english(language):
        raise CustomModelValidationError("Custom model does not declare English support")


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CustomModelValidationError(f"Could not parse {path.name}") from error
    if not isinstance(raw, dict):
        raise CustomModelValidationError(f"{path.name} must contain a JSON object")
    return cast(dict[str, object], raw)


def _supports_english(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"en", "english"}
    if isinstance(value, list):
        return any(_supports_english(item) for item in value)
    return False
