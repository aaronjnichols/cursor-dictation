from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from cursor_dictation.transcription.model_manifest import (
    ModelFileValidationError,
    ModelManifest,
    validate_model_files,
)


class ModelInstallError(RuntimeError):
    pass


class InstallCancelled(ModelInstallError):
    pass


ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class SnapshotDownload(Protocol):
    def __call__(
        self,
        *,
        repo_id: str,
        revision: str,
        local_dir: str,
        allow_patterns: tuple[str, ...],
    ) -> str: ...


class DefaultModelInstaller:
    def __init__(
        self,
        *,
        manifest: ModelManifest,
        models_root: Path,
        downloads_root: Path,
        smoke_load: Callable[[Path], object],
        snapshot_download: SnapshotDownload | None = None,
    ) -> None:
        self.manifest = manifest
        self.models_root = models_root
        self.downloads_root = downloads_root
        self._smoke_load = smoke_load
        self._snapshot_download = snapshot_download or _snapshot_download

    @property
    def target_directory(self) -> Path:
        return self.models_root / self.manifest.model_id

    def is_installed(self) -> bool:
        try:
            validate_model_files(self.target_directory, self.manifest)
        except (ModelFileValidationError, OSError):
            return False
        return True

    def install(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancel_requested: CancelCheck | None = None,
    ) -> Path:
        notify = progress or (lambda _percent, _message: None)
        cancelled = cancel_requested or (lambda: False)
        if self.is_installed():
            notify(100, "Model verified")
            return self.target_directory
        if self.target_directory.exists():
            raise ModelInstallError(
                f"An invalid model directory already exists at {self.target_directory}. "
                "Choose a custom model or move that directory before retrying."
            )
        if cancelled():
            raise InstallCancelled("Model installation was cancelled.")

        self.models_root.mkdir(parents=True, exist_ok=True)
        self.downloads_root.mkdir(parents=True, exist_ok=True)
        partial = self.downloads_root / f"{self.manifest.model_id}-{uuid4().hex}.partial"
        partial.mkdir()

        notify(5, "Downloading pinned model files...")
        try:
            self._snapshot_download(
                repo_id=self.manifest.repository,
                revision=self.manifest.revision,
                local_dir=str(partial),
                allow_patterns=tuple(self.manifest.required_files),
            )
        except Exception as error:
            raise ModelInstallError(f"Model download failed: {error}") from error
        if cancelled():
            raise InstallCancelled("Model installation was cancelled.")

        notify(82, "Verifying model files...")
        try:
            validate_model_files(partial, self.manifest)
        except (ModelFileValidationError, OSError) as error:
            raise ModelInstallError(f"Model verification failed: {error}") from error

        notify(90, "Loading model locally...")
        try:
            self._smoke_load(partial)
        except Exception as error:
            raise ModelInstallError(f"Model smoke load failed: {error}") from error
        if cancelled():
            raise InstallCancelled("Model installation was cancelled.")

        try:
            (partial / "cursor-dictation-manifest.json").write_text(
                json.dumps(_manifest_payload(self.manifest), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            os.replace(partial, self.target_directory)
        except OSError as error:
            raise ModelInstallError(f"Could not activate the verified model: {error}") from error
        notify(100, "Model verified")
        return self.target_directory


def _snapshot_download(
    *,
    repo_id: str,
    revision: str,
    local_dir: str,
    allow_patterns: tuple[str, ...],
) -> str:
    from huggingface_hub import snapshot_download

    return str(
        snapshot_download(
            repo_id=repo_id,
            revision=revision,
            local_dir=local_dir,
            allow_patterns=list(allow_patterns),
        )
    )


def _manifest_payload(manifest: ModelManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "model_id": manifest.model_id,
        "display_name": manifest.display_name,
        "repository": manifest.repository,
        "revision": manifest.revision,
        "language": manifest.language,
        "approximate_size_bytes": manifest.approximate_size_bytes,
        "required_files": dict(manifest.required_files),
    }
