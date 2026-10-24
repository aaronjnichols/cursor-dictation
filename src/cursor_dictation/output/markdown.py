from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from cursor_dictation.core.models import DeliveryMethod, DeliveryResult


def validate_frontmatter(source: str) -> str:
    """Accept YAML properties without document delimiters and preserve their formatting."""
    if not isinstance(source, str):
        raise TypeError("Markdown properties must be text")
    source = source.strip()
    if not source:
        return ""
    if any(line.strip() in {"---", "..."} for line in source.splitlines()):
        raise ValueError("Enter YAML properties without the --- delimiters.")
    try:
        properties = yaml.safe_load(source)
    except yaml.YAMLError as error:
        raise ValueError("Markdown properties must be valid YAML.") from error
    if not isinstance(properties, dict) or any(
        not isinstance(key, str) or not key.strip() for key in properties
    ):
        raise ValueError("Markdown properties must be a YAML mapping with named properties.")
    return source


def save_markdown(text: str, folder: str | None, frontmatter: str = "") -> DeliveryResult:
    if not folder:
        raise ValueError("Choose a Markdown folder in Settings first.")
    directory = Path(folder).expanduser()
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError("Choose an existing absolute Markdown folder in Settings.")
    properties = validate_frontmatter(frontmatter)
    content = (f"---\n{properties}\n---\n\n" if properties else "") + text.strip() + "\n"
    stem = datetime.now().strftime("Dictation %Y-%m-%d %H-%M-%S")
    for index in range(1, 10001):
        suffix = "" if index == 1 else f" ({index})"
        path = directory / f"{stem}{suffix}.md"
        try:
            stream = path.open("x", encoding="utf-8", newline="\n")
        except FileExistsError:
            continue
        try:
            with stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            with suppress(OSError):
                path.unlink()
            raise
        return DeliveryResult.ok(DeliveryMethod.MARKDOWN_FILE)
    raise OSError("Could not choose an unused Markdown filename.")
