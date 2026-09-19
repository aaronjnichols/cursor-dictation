from __future__ import annotations

from cursor_dictation.resources import resource_path


def test_development_resource_path_finds_checked_in_manifest() -> None:
    manifest = resource_path("assets", "models", "default-small-en.json")

    assert manifest.is_file()
    assert manifest.name == "default-small-en.json"
