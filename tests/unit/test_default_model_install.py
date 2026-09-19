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
        downloads_root=tmp_path / "downloads",
        snapshot_download=make_downloader(files, observed),
        smoke_load=smoke_paths.append,
    )

    installed = installer.install()

    assert installed == tmp_path / "models" / "small.en"
    assert observed["repo_id"] == "owner/model"
    assert observed["revision"] == "a" * 40
    assert set(observed["allow_patterns"]) == set(files)
    assert smoke_paths and smoke_paths[0].parent == tmp_path / "downloads"
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
        downloads_root=tmp_path / "downloads",
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
        downloads_root=tmp_path / "downloads",
        snapshot_download=make_downloader(downloaded, {}),
        smoke_load=lambda _path: None,
    )

    with pytest.raises(ModelInstallError, match="verification"):
        installer.install()

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "downloads").glob("*.partial"))


def test_invalid_existing_model_is_never_replaced(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    models = tmp_path / "models"
    invalid_existing = models / "small.en"
    invalid_existing.mkdir(parents=True)
    (invalid_existing / "old.txt").write_text("keep", encoding="utf-8")
    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=models,
        downloads_root=tmp_path / "downloads",
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
        downloads_root=tmp_path / "downloads",
        snapshot_download=make_downloader(files, {}),
        smoke_load=lambda _path: (_ for _ in ()).throw(RuntimeError("cannot load")),
    )

    with pytest.raises(ModelInstallError, match="smoke load"):
        installer.install()

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "downloads").glob("*.partial"))


def test_cancel_after_download_leaves_only_partial_data(tmp_path: Path) -> None:
    files = {"config.json": b"{}", "model.bin": b"model", "tokenizer.json": b"{}"}
    installer = DefaultModelInstaller(
        manifest=manifest_for(files),
        models_root=tmp_path / "models",
        downloads_root=tmp_path / "downloads",
        snapshot_download=make_downloader(files, {}),
        smoke_load=lambda _path: None,
    )

    checks = iter((False, True))
    with pytest.raises(InstallCancelled):
        installer.install(cancel_requested=lambda: next(checks))

    assert not (tmp_path / "models" / "small.en").exists()
    assert list((tmp_path / "downloads").glob("*.partial"))
