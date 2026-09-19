from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping
from contextlib import suppress
from pathlib import Path

from cursor_dictation.settings.schema import CURRENT_SCHEMA_VERSION, AppSettings


class SettingsLoadError(RuntimeError):
    """The settings file exists but cannot be loaded safely."""


class SettingsSaveError(RuntimeError):
    """Settings could not be saved without risking the prior file."""


class SettingsMigrationError(ValueError):
    """Stored settings do not have a supported migration path."""


SettingsMigration = Callable[[dict[str, object]], dict[str, object]]


def _migrate_version_0_to_1(values: dict[str, object]) -> dict[str, object]:
    renamed_fields = {
        "hold_hotkey": "hold_to_talk_hotkey",
        "toggle_hotkey": "toggle_recording_hotkey",
        "copy_hotkey": "record_and_copy_hotkey",
        "startup_enabled": "launch_at_sign_in",
    }
    migrated = dict(values)
    for old_name, new_name in renamed_fields.items():
        if old_name in migrated and new_name not in migrated:
            migrated[new_name] = migrated[old_name]
        migrated.pop(old_name, None)
    migrated["schema_version"] = 1
    return migrated


def _migrate_version_1_to_2(values: dict[str, object]) -> dict[str, object]:
    migrated = dict(values)
    # Version 1 did not preserve provenance. Treat every legacy path as the pinned
    # model until the user explicitly reselects it as custom. This can reject a
    # legacy custom directory, but it cannot silently weaken hash verification.
    migrated["model_source"] = "recommended"
    migrated["schema_version"] = 2
    return migrated


SETTINGS_MIGRATIONS: Mapping[int, SettingsMigration] = {
    0: _migrate_version_0_to_1,
    1: _migrate_version_1_to_2,
}


def migrate_settings_data(values: Mapping[str, object]) -> tuple[dict[str, object], bool]:
    migrated = dict(values)
    raw_version = migrated.get("schema_version", 0)
    if type(raw_version) is not int:
        raise SettingsMigrationError("schema_version must be an integer")
    version = raw_version
    changed = version != CURRENT_SCHEMA_VERSION

    if version > CURRENT_SCHEMA_VERSION:
        raise SettingsMigrationError(
            f"settings schema {version} is newer than supported schema {CURRENT_SCHEMA_VERSION}"
        )
    while version < CURRENT_SCHEMA_VERSION:
        migration = SETTINGS_MIGRATIONS.get(version)
        if migration is None:
            raise SettingsMigrationError(f"no migration exists for settings schema {version}")
        migrated = migration(migrated)
        next_version = migrated.get("schema_version")
        if type(next_version) is not int or next_version <= version:
            raise SettingsMigrationError(f"migration for settings schema {version} is invalid")
        version = next_version

    return migrated, changed


class JsonSettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        try:
            raw_bytes = self.path.read_bytes()
        except FileNotFoundError:
            return AppSettings()
        except OSError as error:
            raise self._load_error(str(error)) from error

        try:
            decoded = raw_bytes.decode("utf-8")
            parsed = json.loads(decoded)
            if not isinstance(parsed, dict):
                raise ValueError("the top-level JSON value must be an object")
            migrated, changed = migrate_settings_data(parsed)
            settings = AppSettings.from_dict(migrated)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise self._load_error(str(error)) from error

        if changed:
            try:
                self.save(settings)
            except SettingsSaveError as error:
                raise self._load_error(f"migration could not be saved: {error}") from error
        return settings

    def save(self, settings: AppSettings) -> None:
        payload = (
            json.dumps(
                settings.to_dict(),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        temporary_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=self.path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        except OSError as error:
            if temporary_path is not None:
                with suppress(OSError):
                    temporary_path.unlink(missing_ok=True)
            raise SettingsSaveError(f"Could not save settings to {self.path}: {error}") from error

    def _load_error(self, detail: str) -> SettingsLoadError:
        return SettingsLoadError(
            f"Could not load settings from {self.path}. The file was left unchanged. "
            f"Please move or fix it, then restart Cursor Dictation. Details: {detail}"
        )
