from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cursor_dictation.transcription.model_manifest import (
    ManifestFormatError,
    ModelFileValidationError,
    load_model_manifest,
    validate_model_files,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_manifest_parses_and_validates_required_file_hashes(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    model_data = b"model-data"
    config_data = b'{"language":"en"}'
    tokenizer_data = b'{"version":"1.0"}'
    (model_dir / "model.bin").write_bytes(model_data)
    (model_dir / "config.json").write_bytes(config_data)
    (model_dir / "tokenizer.json").write_bytes(tokenizer_data)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "whisper-small-en",
                "display_name": "Whisper small.en",
                "repository": "example/whisper-small-en-ct2",
                "revision": "a" * 40,
                "language": "en",
                "approximate_size_bytes": 123,
                "required_files": {
                    "model.bin": _sha256(model_data),
                    "config.json": _sha256(config_data),
                    "tokenizer.json": _sha256(tokenizer_data),
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = load_model_manifest(manifest_path)
    validate_model_files(model_dir, manifest)

    assert manifest.model_id == "whisper-small-en"
    assert manifest.revision == "a" * 40
    assert manifest.required_files["model.bin"] == _sha256(model_data)


def test_file_validation_reports_missing_and_hash_mismatch(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.bin").write_bytes(b"wrong")
    (model_dir / "config.json").write_bytes(b"{}")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "test",
                "display_name": "Test",
                "repository": "example/test",
                "revision": "b" * 40,
                "language": "en",
                "approximate_size_bytes": 1,
                "required_files": {
                    "model.bin": _sha256(b"expected"),
                    "config.json": _sha256(b"{}"),
                    "tokenizer.json": _sha256(b"tokenizer"),
                },
            }
        ),
        encoding="utf-8",
    )
    manifest = load_model_manifest(manifest_path)

    with pytest.raises(ModelFileValidationError) as error:
        validate_model_files(model_dir, manifest)

    assert error.value.missing_files == ("tokenizer.json",)
    assert error.value.hash_mismatches == ("model.bin",)


@pytest.mark.parametrize(
    "required_files",
    [
        {"../model.bin": "0" * 64},
        {".": "0" * 64},
        {"sub/model.bin:stream": "0" * 64},
        {"model.bin": "not-a-hash"},
        {},
    ],
)
def test_manifest_rejects_unsafe_or_invalid_file_entries(
    tmp_path: Path, required_files: dict[str, str]
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "test",
                "display_name": "Test",
                "repository": "example/test",
                "revision": "c" * 40,
                "language": "en",
                "approximate_size_bytes": 1,
                "required_files": required_files,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ManifestFormatError):
        load_model_manifest(path)


def test_manifest_requires_immutable_revision_and_runtime_files(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    base = {
        "schema_version": 1,
        "model_id": "test",
        "display_name": "Test",
        "repository": "example/test",
        "language": "en",
        "approximate_size_bytes": 1,
        "required_files": {
            "model.bin": "0" * 64,
            "config.json": "0" * 64,
            "tokenizer.json": "0" * 64,
        },
    }
    path.write_text(json.dumps({**base, "revision": "main"}), encoding="utf-8")
    with pytest.raises(ManifestFormatError, match="immutable"):
        load_model_manifest(path)

    incomplete_files = dict(base["required_files"])
    incomplete_files.pop("tokenizer.json")
    path.write_text(
        json.dumps({**base, "revision": "d" * 40, "required_files": incomplete_files}),
        encoding="utf-8",
    )
    with pytest.raises(ManifestFormatError, match=r"tokenizer\.json"):
        load_model_manifest(path)


def test_validation_rejects_unhashed_runtime_files(tmp_path: Path) -> None:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    contents = {
        "model.bin": b"model",
        "config.json": b"{}",
        "tokenizer.json": b"{}",
    }
    for name, data in contents.items():
        (model_dir / name).write_bytes(data)
    (model_dir / "preprocessor_config.json").write_text("{}", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "model_id": "test",
                "display_name": "Test",
                "repository": "example/test",
                "revision": "e" * 40,
                "language": "en",
                "approximate_size_bytes": 1,
                "required_files": {name: _sha256(data) for name, data in contents.items()},
            }
        ),
        encoding="utf-8",
    )

    manifest = load_model_manifest(manifest_path)
    with pytest.raises(ModelFileValidationError) as error:
        validate_model_files(model_dir, manifest)

    assert error.value.untracked_runtime_files == ("preprocessor_config.json",)
