from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from cursor_dictation.core.hotkeys import HotkeyParseError, parse_hotkey

CURRENT_SCHEMA_VERSION = 1

_HOTKEY_FIELDS = (
    "hold_to_talk_hotkey",
    "toggle_recording_hotkey",
    "record_and_copy_hotkey",
    "cancel_hotkey",
)
_OPTIONAL_TEXT_FIELDS = ("microphone_device_id", "model_path")
_BOOLEAN_FIELDS = ("sound_cues_enabled", "history_enabled", "launch_at_sign_in")


@dataclass(frozen=True, slots=True)
class AppSettings:
    schema_version: int = CURRENT_SCHEMA_VERSION
    hold_to_talk_hotkey: str = "Ctrl+Alt+Space"
    toggle_recording_hotkey: str = "Ctrl+Alt+D"
    record_and_copy_hotkey: str = "Ctrl+Alt+C"
    cancel_hotkey: str = "Ctrl+Alt+Escape"
    microphone_device_id: str | None = None
    model_path: str | None = None
    sound_cues_enabled: bool = True
    history_enabled: bool = False
    launch_at_sign_in: bool = False

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int:
            raise TypeError("schema_version must be an integer")
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {CURRENT_SCHEMA_VERSION}, got {self.schema_version}"
            )

        normalized_hotkeys: list[tuple[int, int]] = []
        for field_name in _HOTKEY_FIELDS:
            value = getattr(self, field_name)
            _validate_required_text(field_name, value)
            try:
                hotkey = parse_hotkey(value)
            except HotkeyParseError as error:
                raise ValueError(f"{field_name}: {error}") from error
            normalized_hotkeys.append((hotkey.modifiers, hotkey.virtual_key))
        if len(set(normalized_hotkeys)) != len(normalized_hotkeys):
            raise ValueError("configured hotkeys must be distinct")

        for field_name in _OPTIONAL_TEXT_FIELDS:
            value = getattr(self, field_name)
            if value is not None:
                _validate_required_text(field_name, value)

        for field_name in _BOOLEAN_FIELDS:
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be a boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "hold_to_talk_hotkey": self.hold_to_talk_hotkey,
            "toggle_recording_hotkey": self.toggle_recording_hotkey,
            "record_and_copy_hotkey": self.record_and_copy_hotkey,
            "cancel_hotkey": self.cancel_hotkey,
            "microphone_device_id": self.microphone_device_id,
            "model_path": self.model_path,
            "sound_cues_enabled": self.sound_cues_enabled,
            "history_enabled": self.history_enabled,
            "launch_at_sign_in": self.launch_at_sign_in,
        }

    @classmethod
    def from_dict(cls, values: Mapping[str, object]) -> AppSettings:
        allowed_fields = set(cls().to_dict())
        unknown_fields = sorted(set(values) - allowed_fields)
        if unknown_fields:
            joined = ", ".join(unknown_fields)
            raise ValueError(f"unknown settings fields: {joined}")

        defaults = cls().to_dict()
        combined = defaults | dict(values)
        return cls(
            schema_version=_integer_value(combined, "schema_version"),
            hold_to_talk_hotkey=_string_value(combined, "hold_to_talk_hotkey"),
            toggle_recording_hotkey=_string_value(combined, "toggle_recording_hotkey"),
            record_and_copy_hotkey=_string_value(combined, "record_and_copy_hotkey"),
            cancel_hotkey=_string_value(combined, "cancel_hotkey"),
            microphone_device_id=_optional_string_value(combined, "microphone_device_id"),
            model_path=_optional_string_value(combined, "model_path"),
            sound_cues_enabled=_boolean_value(combined, "sound_cues_enabled"),
            history_enabled=_boolean_value(combined, "history_enabled"),
            launch_at_sign_in=_boolean_value(combined, "launch_at_sign_in"),
        )


def _validate_required_text(field_name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field_name} must be non-empty with no surrounding whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError(f"{field_name} cannot contain control characters")


def _integer_value(values: Mapping[str, object], field_name: str) -> int:
    value = values[field_name]
    if type(value) is not int:
        raise TypeError(f"{field_name} must be an integer")
    return value


def _string_value(values: Mapping[str, object], field_name: str) -> str:
    value = values[field_name]
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_string_value(values: Mapping[str, object], field_name: str) -> str | None:
    value = values[field_name]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string or null")
    return value


def _boolean_value(values: Mapping[str, object], field_name: str) -> bool:
    value = values[field_name]
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be a boolean")
    return value
