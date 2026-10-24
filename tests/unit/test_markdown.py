from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from cursor_dictation.core.models import DeliveryMethod
from cursor_dictation.output.markdown import save_markdown
from cursor_dictation.settings.schema import AppSettings
from cursor_dictation.settings.store import JsonSettingsStore


def test_save_preserves_yaml_and_unicode_without_overwriting(tmp_path: Path) -> None:
    properties = "tags: [dictation]\nstatus: inbox\nreviewed: false"
    with patch("cursor_dictation.output.markdown.datetime") as clock:
        clock.now.return_value = datetime(2026, 9, 19, 12, 30, 0)
        result = save_markdown("Caf\u00e9 notes.", str(tmp_path), properties)
        save_markdown("Second note", str(tmp_path))
    first = tmp_path / "Dictation 2026-09-19 12-30-00.md"
    second = tmp_path / "Dictation 2026-09-19 12-30-00 (2).md"
    assert result.success and result.method is DeliveryMethod.MARKDOWN_FILE
    assert first.read_text(encoding="utf-8") == f"---\n{properties}\n---\n\nCaf\u00e9 notes.\n"
    assert second.read_text(encoding="utf-8") == "Second note\n"


@pytest.mark.parametrize("properties", ["[one, two]", "tags: [", "---\ntags: []", "true: yes"])
def test_invalid_properties_are_rejected_before_settings_save(properties: str) -> None:
    with pytest.raises(ValueError):
        AppSettings(markdown_frontmatter=properties)


def test_missing_folder_does_not_create_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Choose"):
        save_markdown("Keep this", None)
    with pytest.raises(ValueError, match="existing"):
        save_markdown("Keep this", str(tmp_path / "missing"))
    assert list(tmp_path.iterdir()) == []


def test_failed_write_removes_partial_file(tmp_path: Path) -> None:
    with (
        patch("cursor_dictation.output.markdown.os.fsync", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        save_markdown("Recover me", str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_markdown_settings_roundtrip_and_legacy_defaults(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    settings = AppSettings(markdown_folder=str(tmp_path), markdown_frontmatter="tags: [dictation]")
    store.save(settings)
    assert store.load() == settings
    legacy = settings.to_dict()
    for key in ("markdown_folder", "markdown_frontmatter", "record_to_markdown_hotkey"):
        legacy.pop(key)
    loaded = AppSettings.from_dict(legacy)
    assert loaded.markdown_folder is None
    assert loaded.record_to_markdown_hotkey == "Ctrl+Alt+M"
