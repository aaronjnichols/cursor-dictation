from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Protocol
from urllib.parse import quote
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
        expected_size_bytes: int,
        progress: ProgressCallback,
        cancel_requested: CancelCheck,
    ) -> str: ...


class DefaultModelInstaller:
    def __init__(
        self,
        *,
        manifest: ModelManifest,
        models_root: Path,
        smoke_load: Callable[[Path], object],
        snapshot_download: SnapshotDownload | None = None,
    ) -> None:
        self.manifest = manifest
        self.models_root = models_root
        self.downloads_root = models_root / ".downloads"
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
        self._remove_abandoned_partials()
        partial = self.downloads_root / f"{self.manifest.model_id}-{uuid4().hex}.partial"
        partial.mkdir()
        try:
            notify(5, "Downloading pinned model files...")
            try:
                self._snapshot_download(
                    repo_id=self.manifest.repository,
                    revision=self.manifest.revision,
                    local_dir=str(partial),
                    allow_patterns=tuple(self.manifest.required_files),
                    expected_size_bytes=self.manifest.approximate_size_bytes,
                    progress=notify,
                    cancel_requested=cancelled,
                )
            except InstallCancelled:
                raise
            except Exception as error:
                if cancelled():
                    raise InstallCancelled("Model installation was cancelled.") from error
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
                raise ModelInstallError(
                    f"Could not activate the verified model: {error}"
                ) from error
        except BaseException:
            self._remove_partial_without_masking_error(partial)
            raise
        notify(100, "Model verified")
        return self.target_directory

    def _remove_abandoned_partials(self) -> None:
        prefix = f"{self.manifest.model_id}-"
        try:
            candidates = tuple(self.downloads_root.iterdir())
        except OSError as error:
            raise ModelInstallError(
                f"Could not inspect incomplete model downloads: {error}"
            ) from error
        for candidate in candidates:
            if candidate.name.startswith(prefix) and candidate.name.endswith(".partial"):
                try:
                    self._remove_partial(candidate)
                except OSError as error:
                    raise ModelInstallError(
                        f"Could not remove incomplete model download: {error}"
                    ) from error

    def _remove_partial_without_masking_error(self, partial: Path) -> None:
        # The operation's original error is more useful than a cleanup failure.
        with suppress(OSError):
            self._remove_partial(partial)

    def _remove_partial(self, partial: Path) -> None:
        downloads_root = self.downloads_root.resolve()
        resolved = partial.resolve()
        if resolved.parent != downloads_root:
            raise OSError(f"Refusing to remove a path outside {downloads_root}")
        if partial.is_symlink() or partial.is_file():
            partial.unlink(missing_ok=True)
        elif partial.exists():
            shutil.rmtree(partial)


def _snapshot_download(
    *,
    repo_id: str,
    revision: str,
    local_dir: str,
    allow_patterns: tuple[str, ...],
    expected_size_bytes: int,
    progress: ProgressCallback,
    cancel_requested: CancelCheck,
) -> str:
    import requests

    root = Path(local_dir)
    downloaded_bytes = 0
    session = requests.Session()
    session.headers["User-Agent"] = "cursor-dictation/0.1"
    try:
        for relative_name in allow_patterns:
            if cancel_requested():
                raise InstallCancelled("Model installation was cancelled.")
            destination = root.joinpath(*relative_name.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            url = (
                f"https://huggingface.co/{quote(repo_id, safe='/')}/resolve/"
                f"{quote(revision, safe='')}/{quote(relative_name, safe='/')}"
            )
            with session.get(
                url,
                stream=True,
                allow_redirects=True,
                timeout=(10, 5),
            ) as response:
                response.raise_for_status()
                with destination.open("wb") as output:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if cancel_requested():
                            raise InstallCancelled("Model installation was cancelled.")
                        if not block:
                            continue
                        output.write(block)
                        downloaded_bytes += len(block)
                        fraction = downloaded_bytes / max(1, expected_size_bytes)
                        percent = 5 + round(min(1.0, fraction) * 75)
                        progress(percent, f"Downloading {relative_name}...")
    finally:
        session.close()
    return str(root)


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
