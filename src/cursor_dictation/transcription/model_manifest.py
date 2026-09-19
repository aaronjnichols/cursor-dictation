from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import cast

_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
_IMMUTABLE_REVISION_PATTERN = re.compile(r"[0-9a-fA-F]{40}")
_REQUIRED_RUNTIME_FILES = frozenset({"model.bin", "config.json", "tokenizer.json"})


@dataclass(frozen=True, slots=True)
class ModelManifest:
    schema_version: int
    model_id: str
    display_name: str
    repository: str
    revision: str
    language: str
    approximate_size_bytes: int
    required_files: Mapping[str, str]


class ManifestFormatError(ValueError):
    """A model manifest is malformed or unsafe."""


class ModelFileValidationError(ValueError):
    def __init__(
        self,
        *,
        missing_files: tuple[str, ...],
        hash_mismatches: tuple[str, ...],
        untracked_runtime_files: tuple[str, ...] = (),
    ) -> None:
        self.missing_files = missing_files
        self.hash_mismatches = hash_mismatches
        self.untracked_runtime_files = untracked_runtime_files
        details: list[str] = []
        if missing_files:
            details.append("missing: " + ", ".join(missing_files))
        if hash_mismatches:
            details.append("hash mismatch: " + ", ".join(hash_mismatches))
        if untracked_runtime_files:
            details.append("untracked runtime files: " + ", ".join(untracked_runtime_files))
        super().__init__("Model file validation failed. " + "; ".join(details))


def load_model_manifest(path: Path) -> ModelManifest:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManifestFormatError(f"Could not read model manifest: {path}") from error
    if not isinstance(raw, dict):
        raise ManifestFormatError("Model manifest must contain a JSON object")

    data = cast(dict[str, object], raw)
    schema_version = _required_integer(data, "schema_version")
    if schema_version != 1:
        raise ManifestFormatError(f"Unsupported model manifest schema: {schema_version}")
    approximate_size = _required_integer(data, "approximate_size_bytes")
    if approximate_size < 0:
        raise ManifestFormatError("approximate_size_bytes cannot be negative")

    language = _required_string(data, "language").lower()
    if language != "en":
        raise ManifestFormatError("The default model manifest must describe an English model")

    raw_files = data.get("required_files")
    if not isinstance(raw_files, dict) or not raw_files:
        raise ManifestFormatError("required_files must be a non-empty object")
    files: dict[str, str] = {}
    for raw_name, raw_hash in cast(dict[object, object], raw_files).items():
        if not isinstance(raw_name, str) or not _safe_relative_path(raw_name):
            raise ManifestFormatError(f"Unsafe required file path: {raw_name!r}")
        if not isinstance(raw_hash, str) or _SHA256_PATTERN.fullmatch(raw_hash) is None:
            raise ManifestFormatError(f"Invalid SHA-256 for required file: {raw_name}")
        files[raw_name] = raw_hash.lower()

    missing_runtime_entries = sorted(_REQUIRED_RUNTIME_FILES.difference(files))
    if missing_runtime_entries:
        raise ManifestFormatError(
            "required_files is missing runtime files: " + ", ".join(missing_runtime_entries)
        )

    revision = _required_string(data, "revision")
    if _IMMUTABLE_REVISION_PATTERN.fullmatch(revision) is None:
        raise ManifestFormatError("revision must be an immutable 40-character commit hash")

    return ModelManifest(
        schema_version=schema_version,
        model_id=_required_string(data, "model_id"),
        display_name=_required_string(data, "display_name"),
        repository=_required_string(data, "repository"),
        revision=revision.lower(),
        language=language,
        approximate_size_bytes=approximate_size,
        required_files=MappingProxyType(files),
    )


def validate_model_files(model_directory: Path, manifest: ModelManifest) -> None:
    root = model_directory.resolve()
    missing: list[str] = []
    mismatches: list[str] = []
    for relative_name, expected_hash in manifest.required_files.items():
        candidate = root.joinpath(*PurePosixPath(relative_name).parts)
        try:
            resolved_candidate = candidate.resolve()
            inside_root = resolved_candidate.is_relative_to(root)
        except OSError:
            inside_root = False
        if not inside_root or not candidate.is_file():
            missing.append(relative_name)
            continue
        if _sha256(candidate) != expected_hash:
            mismatches.append(relative_name)

    tracked = set(manifest.required_files)
    optional_runtime_files = [root / "preprocessor_config.json"]
    if root.is_dir():
        optional_runtime_files.extend(root.glob("vocabulary.*"))
    untracked = sorted(
        candidate.name
        for candidate in optional_runtime_files
        if candidate.is_file() and candidate.name not in tracked
    )

    if missing or mismatches or untracked:
        raise ModelFileValidationError(
            missing_files=tuple(missing),
            hash_mismatches=tuple(mismatches),
            untracked_runtime_files=tuple(untracked),
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _required_string(data: Mapping[str, object], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ManifestFormatError(f"{name} must be a non-empty string")
    return value.strip()


def _required_integer(data: Mapping[str, object], name: str) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestFormatError(f"{name} must be an integer")
    return value


def _safe_relative_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    return (
        bool(normalized)
        and bool(path.parts)
        and not path.is_absolute()
        and ".." not in path.parts
        and all(":" not in part for part in path.parts)
    )
