from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType

import pytest

from cursor_dictation.application.model_install import (
    DefaultModelInstaller,
    InstallCancelled,
    ModelInstallError,
    _snapshot_download,
)
from cursor_dictation.transcription.model_manifest import ModelManifest, load_model_manifest


def manifest_for(files: dict[str, bytes]) -> ModelManifest:
    return ModelManifest(
        schema_version=1,
        model_id="small.en",
        display_name="Whisper small.en",
        repository="owner/model",
        revision="a" * 40,
        language="en",
        approximate_size_bytes=sum(len(value) for value in files.values()),
        required_files=MappingProxyType(
            {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
        ),
    )


def test_checked_in_default_manifest_pins_official_small_en_revision() -> None:
    manifest = load_model_manifest(Path("assets/models/default-small-en.json"))

    assert manifest.model_id == "small.en"
    assert manifest.repository == "Systran/faster-whisper-small.en"
    assert manifest.revision == "d1d751a5f8271d482d14ca55d9e2deeebbae577f"
    assert set(manifest.required_files) == {
        "config.json",
        "model.bin",
        "tokenizer.json",
        "vocabulary.txt",
    }


def make_downloader(
    files: dict[str, bytes],
    observed: dict[str, object],
) -> Callable[..., str]:
    def download(**kwargs: object) -> str:
        observed.update(kwargs)
        local_dir = Path(str(kwargs["local_dir"]))
        for name, value in files.items():
            destination = local_dir / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(value)
        return str(local_dir)

    return download


def test_download_is_pinned_verified_smoke_loaded_and_atomically_activated(
    tmp_path: Path,
) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    manifest = manifest_for(files)
    observed: dict[str, object] = {}
    smoke_paths: list[Path] = []
    installer = DefaultModelInstaller(
        manifest=manifest,
        models_root=tmp_path / "models",
        snapshot_download=make_downloader(files, observed),
        smoke_load=smoke_paths.append,
    )

    installed = installer.install()

    assert installed == tmp_path / "models" / "small.en"
    assert observed["repo_id"] == "owner/model"
    assert observed["revision"] == "a" * 40
    assert set(observed["allow_patterns"]) == set(files)
    assert smoke_paths and smoke_paths[0].parent == tmp_path / "models" / ".downloads"
    assert (installed / "model.bin").read_bytes() == b"model"
    assert (installed / "cursor-dictation-manifest.json").is_file()
    assert installer.is_installed()


def test_existing_verified_model_skips_network_download(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    manifest = manifest_for(files)
    target = tmp_path / "models" / "small.en"
    target.mkdir(parents=True)
    for name, value in files.items():
        (target / name).write_bytes(value)

    def unexpected_download(**kwargs: object) -> str:
        raise AssertionError("network download should not run")

    installer = DefaultModelInstaller(
        manifest=manifest,
        models_root=tmp_path / "models",
        snapshot_download=unexpected_download,
        smoke_load=lambda _path: None,
    )

    assert installer.install() == target


def test_hash_failure_never_creates_selectable_model(tmp_path: Path) -> None:
    expected = {"config.json": b"{}", "model.bin": b"expected", "tokenizer.json": b"{}"}
    downloaded = expected | {"model.bin": b"tampered"}
    installer = DefaultModelInstaller(
        manifest=manifest_for(expected),
        models_root=tmp_path / "models",
        snapshot_download=make_downloader(downloaded, {}),
        smoke_load=lambda _path: None,
    )

    with pytest.raises(ModelInstallError, match="verification"):
        installer.install()

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "models" / ".downloads").glob("*.partial")) == []


def test_invalid_existing_model_is_never_replaced(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    models = tmp_path / "models"
    invalid_existing = models / "small.en"
    invalid_existing.mkdir(parents=True)
    (invalid_existing / "old.txt").write_text("keep", encoding="utf-8")
    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=models,
        snapshot_download=make_downloader(files, {}),
        smoke_load=lambda _path: (_ for _ in ()).throw(RuntimeError("cannot load")),
    )

    with pytest.raises(ModelInstallError, match="already exists"):
        installer.install()

    assert (invalid_existing / "old.txt").read_text(encoding="utf-8") == "keep"


def test_smoke_load_failure_does_not_activate_download(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=tmp_path / "models",
        snapshot_download=make_downloader(files, {}),
        smoke_load=lambda _path: (_ for _ in ()).throw(RuntimeError("cannot load")),
    )

    with pytest.raises(ModelInstallError, match="smoke load"):
        installer.install()

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "models" / ".downloads").glob("*.partial")) == []


def test_cancel_after_download_removes_partial_data(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=tmp_path / "models",
        snapshot_download=make_downloader(files, {}),
        smoke_load=lambda _path: None,
    )

    checks = iter((False, True))
    with pytest.raises(InstallCancelled):
        installer.install(cancel_requested=lambda: next(checks))

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "models" / ".downloads").glob("*.partial")) == []


def test_retry_does_not_accumulate_abandoned_partial_directories(tmp_path: Path) -> None:
    expected = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    attempts = 0

    def download(**kwargs: object) -> str:
        nonlocal attempts
        attempts += 1
        files = expected if attempts == 2 else expected | {"model.bin": b"tampered"}
        return make_downloader(files, {})(**kwargs)

    installer = DefaultModelInstaller(
        manifest=manifest_for(expected),
        models_root=tmp_path / "models",
        snapshot_download=download,
        smoke_load=lambda _path: None,
    )

    with pytest.raises(ModelInstallError, match="verification"):
        installer.install()
    installed = installer.install()

    assert attempts == 2
    assert installed.is_dir()
    assert list((tmp_path / "models" / ".downloads").glob("*.partial")) == []


def test_downloader_can_observe_cancellation_while_transfer_is_active(
    tmp_path: Path,
) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    entered_download = False

    def download(**kwargs: object) -> str:
        nonlocal entered_download
        entered_download = True
        cancel_requested = kwargs["cancel_requested"]
        assert callable(cancel_requested)
        if cancel_requested():
            raise InstallCancelled("Model installation was cancelled.")
        raise AssertionError("cancellation was not forwarded to the downloader")

    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=tmp_path / "models",
        snapshot_download=download,
        smoke_load=lambda _path: None,
    )
    checks = iter((False, True))

    with pytest.raises(InstallCancelled):
        installer.install(cancel_requested=lambda: next(checks))

    assert entered_download
    assert list((tmp_path / "models" / ".downloads").glob("*.partial")) == []


def test_streaming_downloader_checks_for_cancel_between_network_blocks(
    tmp_path: Path,
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    class FakeResponse:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        def iter_content(self, *, chunk_size: int):
            assert chunk_size == 1024 * 1024
            yield b"first"
            yield b"second"

    class FakeSession:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.closed = False

        def get(self, url: str, **kwargs: object) -> FakeResponse:
            assert "owner/model/resolve/" in url
            assert kwargs["stream"] is True
            return FakeResponse()

        def close(self) -> None:
            self.closed = True

    session = FakeSession()
    monkeypatch.setattr("requests.Session", lambda: session)
    checks = iter((False, False, True))

    with pytest.raises(InstallCancelled):
        _snapshot_download(
            repo_id="owner/model",
            revision="a" * 40,
            local_dir=str(tmp_path),
            allow_patterns=("model.bin",),
            expected_size_bytes=11,
            progress=lambda _percent, _message: None,
            cancel_requested=lambda: next(checks),
        )

    assert (tmp_path / "model.bin").read_bytes() == b"first"
    assert session.closed
