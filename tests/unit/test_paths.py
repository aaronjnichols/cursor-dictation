from __future__ import annotations

from pathlib import Path

import pytest

from cursor_dictation.platform.windows.paths import AppPaths


def test_app_paths_stay_below_local_app_data(tmp_path: Path) -> None:
    paths = AppPaths.from_local_app_data(tmp_path)

    assert paths.root == tmp_path / "CursorDictation"
    assert paths.settings_file == paths.root / "settings.json"
    assert paths.vocabulary_file == paths.root / "vocabulary.txt"
    assert paths.history_file == paths.root / "history.jsonl"
    assert paths.logs_dir == paths.root / "logs"
    assert paths.models_dir == paths.root / "models"
    assert paths.downloads_dir == paths.root / "downloads"


def test_explicit_root_is_used_for_smoke_tests_and_portable_diagnostics(tmp_path: Path) -> None:
    root = tmp_path / "isolated-data"

    paths = AppPaths.from_root(root)

    assert paths.root == root
    assert paths.settings_file == root / "settings.json"
    assert paths.models_dir == root / "models"


def test_ensure_directories_creates_only_owned_folders(tmp_path: Path) -> None:
    paths = AppPaths.from_local_app_data(tmp_path)

    paths.ensure_directories()

    assert paths.root.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.models_dir.is_dir()
    assert paths.downloads_dir.is_dir()
    assert not paths.settings_file.exists()


def test_missing_local_app_data_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    with pytest.raises(RuntimeError, match="LOCALAPPDATA"):
        AppPaths.from_environment()
