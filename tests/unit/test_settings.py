from __future__ import annotations

import json
import os
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from cursor_dictation.settings.schema import CURRENT_SCHEMA_VERSION, AppSettings
from cursor_dictation.settings.store import JsonSettingsStore, SettingsLoadError, SettingsSaveError


def test_settings_defaults_match_the_approved_controls() -> None:
    settings = AppSettings()

    assert settings.schema_version == CURRENT_SCHEMA_VERSION
    assert settings.hold_to_talk_hotkey == "Ctrl+Alt+Space"
    assert settings.toggle_recording_hotkey == "Ctrl+Alt+D"
    assert settings.record_and_copy_hotkey == "Ctrl+Alt+C"
    assert settings.cancel_hotkey == "Ctrl+Alt+Escape"
    assert settings.microphone_device_id is None
    assert settings.model_path is None
    assert settings.sound_cues_enabled is True
    assert settings.history_enabled is False
    assert settings.launch_at_sign_in is False


def test_settings_are_frozen() -> None:
    settings = AppSettings()

    with pytest.raises(FrozenInstanceError):
        settings.history_enabled = True  # type: ignore[misc]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"hold_to_talk_hotkey": "  "}, "hold_to_talk_hotkey"),
        ({"toggle_recording_hotkey": "Ctrl+Alt+Space"}, "distinct"),
        ({"model_path": ""}, "model_path"),
        ({"microphone_device_id": "\n"}, "microphone_device_id"),
        ({"history_enabled": 1}, "history_enabled"),
        ({"schema_version": 0}, "schema_version"),
        ({"hold_to_talk_hotkey": "not a shortcut"}, "hold_to_talk_hotkey"),
        ({"toggle_recording_hotkey": "Alt+Ctrl+Space"}, "distinct"),
    ],
)
def test_settings_reject_invalid_values(changes: dict[str, object], message: str) -> None:
    defaults = AppSettings()

    with pytest.raises((TypeError, ValueError), match=message):
        replace(defaults, **changes)


def test_missing_settings_file_returns_defaults_without_creating_it(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"

    assert JsonSettingsStore(path).load() == AppSettings()
    assert not path.exists()


def test_settings_round_trip_as_inspectable_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    settings = replace(
        AppSettings(),
        microphone_device_id="usb-microphone",
        model_path=r"C:\models\whisper-small-en",
        history_enabled=True,
        launch_at_sign_in=True,
    )
    store = JsonSettingsStore(path)

    store.save(settings)

    assert store.load() == settings
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == CURRENT_SCHEMA_VERSION
    assert payload["model_path"] == settings.model_path


def test_save_replaces_the_old_file_only_after_complete_json_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("old settings", encoding="utf-8")
    store = JsonSettingsStore(path)
    real_replace = os.replace
    observed: dict[str, object] = {}

    def observe_replace(
        source: str | os.PathLike[str],
        destination: str | os.PathLike[str],
    ) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        observed["source"] = source_path
        observed["destination"] = destination_path
        observed["payload"] = json.loads(source_path.read_text(encoding="utf-8"))
        assert path.read_text(encoding="utf-8") == "old settings"
        real_replace(source_path, destination_path)

    monkeypatch.setattr("cursor_dictation.settings.store.os.replace", observe_replace)

    store.save(replace(AppSettings(), history_enabled=True))

    source = observed["source"]
    assert isinstance(source, Path)
    assert source.parent == path.parent
    assert observed["destination"] == path
    assert observed["payload"] == json.loads(path.read_text(encoding="utf-8"))
    assert not source.exists()


def test_load_migrates_unversioned_prototype_settings_and_rewrites_the_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "hold_hotkey": "Ctrl+Shift+Space",
                "toggle_hotkey": "Ctrl+Shift+D",
                "copy_hotkey": "Ctrl+Shift+C",
                "startup_enabled": True,
                "history_enabled": True,
            }
        ),
        encoding="utf-8",
    )

    settings = JsonSettingsStore(path).load()

    assert settings.hold_to_talk_hotkey == "Ctrl+Shift+Space"
    assert settings.toggle_recording_hotkey == "Ctrl+Shift+D"
    assert settings.record_and_copy_hotkey == "Ctrl+Shift+C"
    assert settings.launch_at_sign_in is True
    assert settings.history_enabled is True
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
    assert "hold_hotkey" not in migrated
    assert "startup_enabled" not in migrated


@pytest.mark.parametrize(
    "content",
    [
        b'{"history_enabled": tru',
        b'{"schema_version": 1, "unexpected": true}',
        b'{"schema_version": 999}',
        b"\xff\xfe",
    ],
)
def test_bad_settings_file_is_preserved_and_error_tells_the_user_what_to_do(
    tmp_path: Path,
    content: bytes,
) -> None:
    path = tmp_path / "settings.json"
    path.write_bytes(content)

    with pytest.raises(SettingsLoadError, match=r"left unchanged.*move or fix") as error:
        JsonSettingsStore(path).load()

    assert str(path) in str(error.value)
    assert path.read_bytes() == content


def test_cleanup_failure_does_not_mask_settings_save_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text("keep this", encoding="utf-8")
    store = JsonSettingsStore(path)

    def failed_replace(source: object, destination: object) -> None:
        raise PermissionError("replace blocked")

    def failed_unlink(self: Path, *, missing_ok: bool = False) -> None:
        raise PermissionError("cleanup blocked")

    monkeypatch.setattr("cursor_dictation.settings.store.os.replace", failed_replace)
    monkeypatch.setattr(Path, "unlink", failed_unlink)

    with pytest.raises(SettingsSaveError, match="Could not save settings") as error:
        store.save(AppSettings())

    assert isinstance(error.value, SettingsSaveError)
    assert path.read_text(encoding="utf-8") == "keep this"
